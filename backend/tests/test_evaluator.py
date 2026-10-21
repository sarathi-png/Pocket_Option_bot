"""Settlement logic tested against the deterministic candle provider."""
from datetime import timedelta

from app.db import SessionLocal
from app.models import Direction, Outcome, Signal
from app.services import evaluator
from app.services.market_data import provider


def _signal(db, direction: Direction, entry: float, expires_at) -> Signal:
    s = Signal(
        pair="EURUSD",
        display_pair="EUR/USD",
        direction=direction,
        timeframe="1m",
        expiry_minutes=2,
        confidence=70,
        entry_price=entry,
        created_at=expires_at - timedelta(minutes=2),
        expires_at=expires_at,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _find_move(want_up: bool):
    """Find (entry_close, exit_candle) with a clear move in the wanted direction."""
    candles = provider.simulated_candles("EURUSD", "1m", limit=120)
    for i in range(len(candles) - 5):
        entry, exit_c = candles[i].close, candles[i + 5]
        if want_up and exit_c.close > entry:
            return entry, exit_c
        if not want_up and exit_c.close < entry:
            return entry, exit_c
    raise AssertionError("no suitable move in simulated series")


def test_call_wins_when_price_rises_and_put_loses():
    db = SessionLocal()
    try:
        entry, exit_c = _find_move(want_up=True)
        call = _signal(db, Direction.CALL, entry, exit_c.timestamp + timedelta(seconds=10))
        put = _signal(db, Direction.PUT, entry, exit_c.timestamp + timedelta(seconds=10))
        assert evaluator.evaluate_signal(db, call).outcome == Outcome.WIN
        assert evaluator.evaluate_signal(db, put).outcome == Outcome.LOSS
        assert call.exit_price == exit_c.close
        # Idempotent: re-evaluating a settled signal changes nothing
        assert evaluator.evaluate_signal(db, call).outcome == Outcome.WIN
    finally:
        db.close()


def test_put_wins_when_price_falls():
    db = SessionLocal()
    try:
        entry, exit_c = _find_move(want_up=False)
        put = _signal(db, Direction.PUT, entry, exit_c.timestamp + timedelta(seconds=10))
        assert evaluator.evaluate_signal(db, put).outcome == Outcome.WIN
    finally:
        db.close()


def test_unexpired_signal_stays_pending():
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        s = _signal(db, Direction.CALL, 1.0850, future)
        assert evaluator.evaluate_signal(db, s).outcome == Outcome.PENDING
        assert s.exit_price is None
    finally:
        db.close()
