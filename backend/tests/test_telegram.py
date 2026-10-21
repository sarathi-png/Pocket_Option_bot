import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx

from app.db import SessionLocal
from app.models import Decision, DeliveryStatus, Direction, Signal
from app.services import settings_service, telegram


def _make_signal(db) -> Signal:
    now = datetime.now(timezone.utc)
    signal = Signal(
        pair="EURUSD",
        display_pair="EUR/USD",
        direction=Direction.CALL,
        decision=Decision.TRADE,
        timeframe="1m",
        expiry_minutes=2,
        confidence=78,
        entry_price=1.08542,
        reasoning=["▲ EMA 9/21: EMA9 above EMA21 — short-term uptrend"],
        created_at=now,
        expires_at=now + timedelta(minutes=2),
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal


def test_format_signal_message_contents():
    db = SessionLocal()
    try:
        signal = _make_signal(db)
        text = telegram.format_signal_message(signal)
        assert "EUR/USD" in text
        assert "CALL" in text
        assert "78%" in text
        assert "1.08542" in text
        assert "not financial advice" in text
    finally:
        db.close()


def test_format_result_message_contents():
    from app.models import Outcome

    db = SessionLocal()
    try:
        signal = _make_signal(db)
        signal.outcome = Outcome.WIN
        signal.exit_price = 1.08610
        text = telegram.format_result_message(signal)
        assert "WIN" in text
        assert "1.08542" in text and "1.08610" in text
    finally:
        db.close()


def test_push_without_config_is_dry_run_not_sent():
    """CORE-07: unconfigured Telegram must never claim a successful send."""
    db = SessionLocal()
    try:
        settings_service.update(db, {"telegram_bot_token": "", "telegram_chat_id": ""})
        signal = _make_signal(db)
        delivery = asyncio.run(telegram.push_signal(db, signal))
        assert delivery.status == DeliveryStatus.DRY_RUN
        assert delivery.error_code == "TELEGRAM_NOT_CONFIGURED"
        assert signal.telegram_status == "DRY_RUN"
    finally:
        db.close()


def _mock_transport(ok: bool) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "sendMessage" in str(request.url)
        body = json.loads(request.content)
        assert body["parse_mode"] == "HTML"
        if ok:
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 4242}})
        return httpx.Response(400, json={"ok": False, "error_code": 400})

    return httpx.MockTransport(handler)


def test_push_with_config_sends_and_is_idempotent():
    db = SessionLocal()
    try:
        settings_service.update(db, {"telegram_bot_token": "test-token-123456", "telegram_chat_id": "123456789"})
        signal = _make_signal(db)
        transport = _mock_transport(ok=True)

        first = asyncio.run(telegram.push_signal(db, signal, transport=transport))
        assert first.status == DeliveryStatus.SENT
        assert first.provider_message_id == "4242"
        # Token must never leak into stored previews/errors
        assert "test-token" not in (first.message_preview or "")
        assert "test-token" not in (first.error_code or "")

        # Second push without force returns the same delivery (no duplicate spam, R-12)
        second = asyncio.run(telegram.push_signal(db, signal, transport=transport))
        assert second.id == first.id
        assert signal.telegram_status == "SENT"
    finally:
        settings_service.update(db, {"telegram_bot_token": "", "telegram_chat_id": ""})
        db.close()


def test_push_failure_is_recorded_honestly():
    db = SessionLocal()
    try:
        settings_service.update(db, {"telegram_bot_token": "bad-token-0000", "telegram_chat_id": "999"})
        signal = _make_signal(db)
        delivery = asyncio.run(telegram.push_signal(db, signal, transport=_mock_transport(ok=False)))
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.error_code == "TELEGRAM_HTTP_400"
    finally:
        settings_service.update(db, {"telegram_bot_token": "", "telegram_chat_id": ""})
        db.close()
