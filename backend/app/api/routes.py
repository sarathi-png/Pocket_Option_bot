"""HTTP routes — thin handlers delegating to services (PRD §6.3/§6.5)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.core.config import get_settings
from app.core.errors import AppError
from app.db import get_db
from app.models import Decision, DeliveryStatus, Outcome, Signal, TelegramDelivery
from app.schemas import (
    CandlesOut,
    GenerateSignalRequest,
    PaginatedSignals,
    PairOut,
    PushRequest,
    SettingsOut,
    SettingsUpdateIn,
    SignalOut,
    StatsOut,
    TelegramSettingsIn,
    TelegramStatusOut,
    validate_timeframe,
)
from app.services import evaluator, settings_service, signal_engine, telegram
from app.services.indicators import ema_series
from app.services.market_data import PAIRS, get_pair, provider
from app.services.scheduler import scheduler

router = APIRouter(prefix="/api/v1")


def _telegram_status(db: Session) -> TelegramStatusOut:
    cfg = settings_service.get(db)
    sent = db.query(func.count(TelegramDelivery.id)).filter(TelegramDelivery.status == DeliveryStatus.SENT).scalar() or 0
    return TelegramStatusOut(
        configured=bool(cfg["telegram_bot_token"] and cfg["telegram_chat_id"]),
        bot_token_masked=settings_service.mask_secret(cfg["telegram_bot_token"]),
        chat_id_masked=settings_service.mask_chat_id(cfg["telegram_chat_id"]),
        deliveries_sent=int(sent),
    )


def _settings_out(db: Session) -> SettingsOut:
    cfg = settings_service.get(db)
    return SettingsOut(
        auto_enabled=cfg["auto_enabled"],
        auto_push_telegram=cfg["auto_push_telegram"],
        min_confidence=cfg["min_confidence"],
        watchlist=cfg["watchlist"],
        auto_interval_seconds=cfg["auto_interval_seconds"],
        default_timeframe=cfg["default_timeframe"],
        default_expiry_minutes=cfg["default_expiry_minutes"],
        telegram=_telegram_status(db),
    )


def _get_signal_or_404(db: Session, signal_id: str) -> Signal:
    signal = db.get(Signal, signal_id)
    if signal is None:
        raise AppError("SIGNAL_NOT_FOUND", f"No signal with id '{signal_id}'.", status_code=404)
    return signal


# ---------------------------------------------------------------- health
@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    cfg = settings_service.get(db)
    return {
        "status": "ok",
        "service": get_settings().app_name,
        "version": "1.0.0",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "telegram_configured": bool(cfg["telegram_bot_token"] and cfg["telegram_chat_id"]),
        "auto_enabled": cfg["auto_enabled"],
        "scheduler_running": scheduler.running,
        "market_data": "twelvedata" if get_settings().twelve_data_api_key else "simulated (set TWELVE_DATA_API_KEY for live Forex/crypto candles)",
        "disclaimer": signal_engine.DISCLAIMER,
    }


# ---------------------------------------------------------------- market
@router.get("/pairs", response_model=list[PairOut])
def list_pairs() -> list[PairOut]:
    return [PairOut(symbol=p.symbol, display=p.display, category=p.category, decimals=p.decimals) for p in PAIRS]


@router.get("/candles", response_model=CandlesOut)
async def get_candles(pair: str = "EURUSD", timeframe: str = "1m", limit: int = Query(default=80, ge=20, le=300)) -> CandlesOut:
    validate_timeframe(timeframe)
    info = get_pair(pair)
    if info is None:
        raise AppError("PAIR_NOT_FOUND", f"Unknown pair '{pair}'. See GET /api/v1/pairs.", status_code=404)
    candles, source = await provider.get_candles(info.symbol, timeframe, limit=limit)
    closes = [c.close for c in candles]
    return CandlesOut(
        pair=info.symbol,
        timeframe=timeframe,
        data_source=source,
        candles=[c.to_dict() for c in candles],
        ema9=[round(v, info.decimals) for v in ema_series(closes, 9)],
        ema21=[round(v, info.decimals) for v in ema_series(closes, 21)],
    )


# ---------------------------------------------------------------- signals
@router.post("/signals/generate", response_model=SignalOut, status_code=201, dependencies=[Depends(require_api_key)])
async def generate_signal(payload: GenerateSignalRequest, db: Session = Depends(get_db)) -> SignalOut:
    cfg = settings_service.get(db)
    signal = await signal_engine.generate_signal(
        db,
        pair=payload.pair,
        timeframe=payload.timeframe,
        expiry_minutes=payload.expiry_minutes,
        min_confidence=cfg["min_confidence"],
        source="manual",
    )
    if payload.push_telegram:
        if signal.decision == Decision.TRADE:
            await telegram.push_signal(db, signal)
            db.refresh(signal)
    return SignalOut.from_model(signal)


@router.get("/signals", response_model=PaginatedSignals)
def list_signals(
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    pair: str | None = None,
    outcome: str | None = None,
    decision: str | None = None,
) -> PaginatedSignals:
    evaluator.evaluate_due_signals(db)  # settle anything expired before listing
    q = db.query(Signal)
    if pair:
        q = q.filter(Signal.pair == pair.strip().upper().replace("/", ""))
    if outcome:
        try:
            q = q.filter(Signal.outcome == Outcome(outcome.upper()))
        except ValueError:
            raise AppError("VALIDATION_ERROR", f"Unknown outcome filter '{outcome}'.", status_code=422) from None
    if decision:
        try:
            q = q.filter(Signal.decision == Decision(decision.upper()))
        except ValueError:
            raise AppError("VALIDATION_ERROR", f"Unknown decision filter '{decision}'.", status_code=422) from None
    total = q.count()
    items = q.order_by(Signal.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedSignals(items=[SignalOut.from_model(s) for s in items], total=total, page=page, page_size=page_size)


@router.get("/signals/{signal_id}", response_model=SignalOut)
def get_signal(signal_id: str, db: Session = Depends(get_db)) -> SignalOut:
    signal = _get_signal_or_404(db, signal_id)
    signal = evaluator.evaluate_signal(db, signal)
    return SignalOut.from_model(signal)


@router.post("/signals/{signal_id}/push-telegram", dependencies=[Depends(require_api_key)])
async def push_signal_telegram(signal_id: str, payload: PushRequest, db: Session = Depends(get_db)) -> dict:
    signal = _get_signal_or_404(db, signal_id)
    delivery = await telegram.push_signal(db, signal, force=payload.force)
    return {"delivery": telegram.delivery_to_dict(delivery), "signal": SignalOut.from_model(signal).model_dump(mode="json")}


@router.post("/signals/{signal_id}/evaluate", response_model=SignalOut, dependencies=[Depends(require_api_key)])
def evaluate_signal(signal_id: str, db: Session = Depends(get_db)) -> SignalOut:
    signal = _get_signal_or_404(db, signal_id)
    signal = evaluator.evaluate_signal(db, signal)
    return SignalOut.from_model(signal)


# ---------------------------------------------------------------- telegram
@router.get("/telegram/status", response_model=TelegramStatusOut)
def telegram_status(db: Session = Depends(get_db)) -> TelegramStatusOut:
    return _telegram_status(db)


@router.put("/telegram/settings", response_model=TelegramStatusOut, dependencies=[Depends(require_api_key)])
def update_telegram_settings(payload: TelegramSettingsIn, db: Session = Depends(get_db)) -> TelegramStatusOut:
    if payload.clear:
        settings_service.update(db, {"telegram_bot_token": "", "telegram_chat_id": ""})
    else:
        changes: dict = {}
        if payload.bot_token.strip():
            changes["telegram_bot_token"] = payload.bot_token.strip()
        if payload.chat_id.strip():
            changes["telegram_chat_id"] = payload.chat_id.strip()
        if changes:
            settings_service.update(db, changes)
    return _telegram_status(db)


@router.post("/telegram/test", dependencies=[Depends(require_api_key)])
async def telegram_test(db: Session = Depends(get_db)) -> dict:
    text = (
        "<b>✅ Pocket Option Signal Bot connected</b>\n"
        "Your Telegram delivery is working. Generated signals will arrive here.\n"
        f"<i>{signal_engine.DISCLAIMER}</i>"
    )
    delivery = await telegram.push_text(db, text, kind="test")
    return {"delivery": telegram.delivery_to_dict(delivery)}


@router.get("/telegram/deliveries")
def list_deliveries(db: Session = Depends(get_db), limit: int = Query(default=20, ge=1, le=100)) -> dict:
    rows = db.query(TelegramDelivery).order_by(TelegramDelivery.created_at.desc()).limit(limit).all()
    return {"items": [telegram.delivery_to_dict(d) for d in rows]}


# ---------------------------------------------------------------- settings / auto
@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)) -> SettingsOut:
    return _settings_out(db)


@router.put("/settings", response_model=SettingsOut, dependencies=[Depends(require_api_key)])
def update_settings(payload: SettingsUpdateIn, db: Session = Depends(get_db)) -> SettingsOut:
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "watchlist" in changes:
        unknown = [p for p in changes["watchlist"] if get_pair(p) is None]
        if unknown:
            raise AppError("VALIDATION_ERROR", f"Unknown pairs in watchlist: {', '.join(unknown)}.", status_code=422)
        if not changes["watchlist"]:
            raise AppError("VALIDATION_ERROR", "Watchlist must contain at least one pair.", status_code=422)
    if changes:
        settings_service.update(db, changes)
    return _settings_out(db)


@router.post("/auto/run-once", dependencies=[Depends(require_api_key)])
async def auto_run_once() -> dict:
    summary = await scheduler.run_cycle()
    return {"summary": summary, "cycles": scheduler.cycles}


@router.get("/auto/status")
def auto_status(db: Session = Depends(get_db)) -> dict:
    cfg = settings_service.get(db)
    return {
        "scheduler_running": scheduler.running,
        "auto_enabled": cfg["auto_enabled"],
        "auto_push_telegram": cfg["auto_push_telegram"],
        "cycles_completed": scheduler.cycles,
        "last_run": scheduler.last_run_summary,
    }


# ---------------------------------------------------------------- stats
@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)) -> StatsOut:
    evaluator.evaluate_due_signals(db)
    total = db.query(func.count(Signal.id)).scalar() or 0
    trade = db.query(func.count(Signal.id)).filter(Signal.decision == Decision.TRADE).scalar() or 0
    counts = {o: db.query(func.count(Signal.id)).filter(Signal.outcome == o).scalar() or 0 for o in Outcome}
    settled = counts[Outcome.WIN] + counts[Outcome.LOSS]
    win_rate = round(counts[Outcome.WIN] / settled * 100, 1) if settled else None
    avg_conf = db.query(func.avg(Signal.confidence)).scalar()
    deliveries = {
        s: db.query(func.count(TelegramDelivery.id)).filter(TelegramDelivery.status == s).scalar() or 0
        for s in DeliveryStatus
    }
    by_pair_rows = (
        db.query(Signal.pair, func.count(Signal.id), func.avg(Signal.confidence))
        .group_by(Signal.pair)
        .order_by(func.count(Signal.id).desc())
        .all()
    )
    return StatsOut(
        total_signals=int(total),
        trade_signals=int(trade),
        no_trade_signals=int(total - trade),
        pending=int(counts[Outcome.PENDING]),
        wins=int(counts[Outcome.WIN]),
        losses=int(counts[Outcome.LOSS]),
        draws=int(counts[Outcome.DRAW]),
        win_rate_pct=win_rate,
        avg_confidence=round(float(avg_conf), 1) if avg_conf is not None else None,
        telegram_sent=int(deliveries[DeliveryStatus.SENT]),
        telegram_failed=int(deliveries[DeliveryStatus.FAILED]),
        telegram_dry_run=int(deliveries[DeliveryStatus.DRY_RUN]),
        by_pair=[
            {"pair": p, "signals": int(c), "avg_confidence": round(float(a), 1) if a else None}
            for p, c, a in by_pair_rows
        ],
    )
