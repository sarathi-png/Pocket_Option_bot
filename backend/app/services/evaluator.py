"""Signal outcome evaluation: settle PENDING signals after expiry.

WIN  = price moved in the signalled direction by expiry (CALL: exit > entry)
LOSS = price moved against it · DRAW = exactly equal (stake refunded on PO)
Prices come from the same deterministic provider used at generation time, so
simulated-mode results are reproducible rather than invented.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.logging_setup import get_logger
from app.models import Direction, Outcome, Signal
from app.services.market_data import provider

logger = get_logger("app.evaluator")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def evaluate_signal(db: Session, signal: Signal) -> Signal:
    if signal.outcome != Outcome.PENDING:
        return signal
    if datetime.now(timezone.utc) < _aware(signal.expires_at):
        return signal  # not yet expired — stays PENDING
    exit_price = provider.exit_price(signal.pair, signal.timeframe, _aware(signal.expires_at))
    if exit_price is None:
        return signal
    signal.exit_price = exit_price
    if exit_price == signal.entry_price:
        signal.outcome = Outcome.DRAW
    elif (signal.direction == Direction.CALL and exit_price > signal.entry_price) or (
        signal.direction == Direction.PUT and exit_price < signal.entry_price
    ):
        signal.outcome = Outcome.WIN
    else:
        signal.outcome = Outcome.LOSS
    signal.evaluated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(signal)
    logger.info("Signal %s settled: %s (entry=%s exit=%s)", signal.id[:8], signal.outcome.value, signal.entry_price, exit_price)
    return signal


def evaluate_due_signals(db: Session, limit: int = 200) -> list[Signal]:
    """Settle all expired PENDING signals. Returns signals settled by this call."""
    now = datetime.now(timezone.utc)
    due = (
        db.query(Signal)
        .filter(Signal.outcome == Outcome.PENDING, Signal.expires_at <= now)
        .order_by(Signal.expires_at.asc())
        .limit(limit)
        .all()
    )
    return [evaluate_signal(db, s) for s in due]
