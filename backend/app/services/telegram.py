"""Telegram delivery — the final step: generated signals pushed to the bot.

Behaviour guarantees (PRD §7.9, §9.1, R-12):
- Bounded timeouts + bounded retries with backoff on 429/5xx/network errors.
- Idempotent push: re-pushing an already-SENT signal returns the existing
  delivery instead of spamming the chat (unless force=True).
- Fail safely: when no token/chat is configured the message is formatted and
  recorded as DRY_RUN — the UI/API never claims it was sent (CORE-07).
- Secrets are never logged or returned; errors are sanitized codes only.
"""
from __future__ import annotations

import asyncio
import html
from datetime import timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from app.core.logging_setup import get_logger
from app.models import DeliveryStatus, Direction, Signal, TelegramDelivery
from app.services import settings_service
from app.services.market_data import format_price
from app.services.signal_engine import DISCLAIMER

logger = get_logger("app.telegram")
_TELEGRAM_API = "https://api.telegram.org"
_IST = ZoneInfo("Asia/Kolkata")


def format_signal_message(signal: Signal) -> str:
    """HTML message for Telegram (parse_mode=HTML). Dynamic values are escaped."""
    is_call = signal.direction == Direction.CALL
    arrow = "🟢 CALL ▲ (UP)" if is_call else "🔴 PUT ▼ (DOWN)"
    created_utc = signal.created_at.astimezone(timezone.utc)
    created_ist = created_utc.astimezone(_IST)
    votes = "\n".join(f"• {html.escape(str(line))}" for line in signal.reasoning[:6])
    decision_line = "" if signal.decision.value == "TRADE" else "\n⚠️ <b>NO-TRADE</b> — indicators disagree, consider skipping."
    return (
        f"<b>📡 Pocket Option Signal</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>Pair:</b> {html.escape(signal.display_pair or signal.pair)}\n"
        f"<b>Direction:</b> {arrow}\n"
        f"<b>Timeframe:</b> {html.escape(signal.timeframe)}  •  <b>Expiry:</b> {signal.expiry_minutes}m\n"
        f"<b>Entry price:</b> {format_price(signal.pair, signal.entry_price)}\n"
        f"<b>Confidence:</b> {signal.confidence}%{decision_line}\n"
        f"<b>Time:</b> {created_ist.strftime('%H:%M:%S')} IST ({created_utc.strftime('%H:%M')} UTC)\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>Why:</b>\n{votes}\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>Data: {html.escape(signal.data_source)} • Signal #{signal.id[:8]}</i>\n"
        f"<i>{html.escape(DISCLAIMER)}</i>"
    )


def format_result_message(signal: Signal) -> str:
    emoji = {"WIN": "✅ WIN", "LOSS": "❌ LOSS", "DRAW": "➖ DRAW"}.get(signal.outcome.value, signal.outcome.value)
    exit_txt = format_price(signal.pair, signal.exit_price) if signal.exit_price is not None else "—"
    return (
        f"<b>🏁 Signal Result</b> — {emoji}\n"
        f"<b>Pair:</b> {html.escape(signal.display_pair or signal.pair)} "
        f"({signal.direction.value}, {signal.expiry_minutes}m expiry)\n"
        f"<b>Entry:</b> {format_price(signal.pair, signal.entry_price)} → <b>Exit:</b> {exit_txt}\n"
        f"<i>Signal #{signal.id[:8]}</i>"
    )


async def _send_message(token: str, chat_id: str, text: str, transport: httpx.AsyncBaseTransport | None = None) -> tuple[bool, str | None, str | None, int]:
    """Returns (ok, provider_message_id, sanitized_error_code, attempts)."""
    url = f"{_TELEGRAM_API}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    last_error: str | None = "UNKNOWN"
    for attempt in range(1, 4):  # max 3 attempts
        try:
            async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return True, str(data.get("result", {}).get("message_id", "")), None, attempt
                last_error = f"TELEGRAM_REJECTED_{data.get('error_code', 'UNKNOWN')}"
            elif resp.status_code in (429, 500, 502, 503, 504):
                last_error = f"TELEGRAM_HTTP_{resp.status_code}"
            else:
                # 400/401/403/404: bad chat id / token / bot blocked — retrying won't help.
                return False, None, f"TELEGRAM_HTTP_{resp.status_code}", attempt
        except httpx.HTTPError as exc:
            last_error = f"NETWORK_{type(exc).__name__}"
        if attempt < 3:
            await asyncio.sleep(0.8 * attempt)  # bounded backoff
    return False, None, last_error, 3


async def push_text(
    db: Session,
    text: str,
    kind: str,
    signal_id: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TelegramDelivery:
    cfg = settings_service.get(db)
    token, chat_id = cfg["telegram_bot_token"], cfg["telegram_chat_id"]
    preview = text[:500]
    if not token or not chat_id:
        delivery = TelegramDelivery(
            signal_id=signal_id, kind=kind, status=DeliveryStatus.DRY_RUN,
            error_code="TELEGRAM_NOT_CONFIGURED", message_preview=preview, attempt_count=0,
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        logger.info("Telegram dry-run (%s): not configured, message recorded but not sent", kind)
        return delivery

    ok, msg_id, error_code, attempts = await _send_message(token, chat_id, text, transport=transport)
    delivery = TelegramDelivery(
        signal_id=signal_id, kind=kind,
        status=DeliveryStatus.SENT if ok else DeliveryStatus.FAILED,
        chat_id_masked=settings_service.mask_chat_id(chat_id),
        provider_message_id=msg_id, error_code=error_code,
        message_preview=preview, attempt_count=attempts,
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    if ok:
        logger.info("Telegram %s sent (message_id=%s)", kind, msg_id)
    else:
        logger.warning("Telegram %s failed: %s", kind, error_code)
    return delivery


async def push_signal(
    db: Session,
    signal: Signal,
    force: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TelegramDelivery:
    """Push a signal once (idempotent). Use force=True to deliberately re-send."""
    if not force:
        already_sent = (
            db.query(TelegramDelivery)
            .filter(TelegramDelivery.signal_id == signal.id, TelegramDelivery.status == DeliveryStatus.SENT)
            .order_by(TelegramDelivery.created_at.desc())
            .first()
        )
        if already_sent is not None:
            return already_sent
    return await push_text(db, format_signal_message(signal), kind="signal", signal_id=signal.id, transport=transport)


async def push_result(
    db: Session,
    signal: Signal,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TelegramDelivery | None:
    """Push the WIN/LOSS/DRAW result for a settled signal (once)."""
    if signal.outcome.value == "PENDING":
        return None
    already = (
        db.query(TelegramDelivery)
        .filter(
            TelegramDelivery.signal_id == signal.id,
            TelegramDelivery.kind == "result",
            TelegramDelivery.status == DeliveryStatus.SENT,
        )
        .first()
    )
    if already is not None:
        return already
    return await push_text(db, format_result_message(signal), kind="result", signal_id=signal.id, transport=transport)


def delivery_to_dict(d: TelegramDelivery) -> dict:
    return {
        "id": d.id,
        "signal_id": d.signal_id,
        "kind": d.kind,
        "status": d.status.value,
        "provider_message_id": d.provider_message_id,
        "error_code": d.error_code,
        "attempt_count": d.attempt_count,
        "message_preview": d.message_preview,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "note": (
            "Telegram is not configured yet — this was a dry run. Add your bot token and chat id "
            "(dashboard → Telegram, or TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars), then push again."
            if d.status == DeliveryStatus.DRY_RUN
            else None
        ),
    }
