from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import AppError
from app.models import Direction
from app.services.market_data import Candle
from app.services.signal_engine import analyze


def _candles(closes: list[float]) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    prev = closes[0]
    for i, close in enumerate(closes):
        out.append(
            Candle(
                timestamp=start + timedelta(minutes=i),
                open=prev,
                high=max(prev, close) * 1.0005,
                low=min(prev, close) * 0.9995,
                close=close,
                volume=100,
            )
        )
        prev = close
    return out


def test_strong_uptrend_signals_call():
    closes = [1.0800 + i * 0.0004 for i in range(80)]
    result = analyze(_candles(closes))
    assert result.direction == Direction.CALL
    assert result.call_score > result.put_score
    assert 50 <= result.confidence <= 97
    assert result.reasoning  # human-readable why


def test_strong_downtrend_signals_put():
    closes = [1.1200 - i * 0.0004 for i in range(80)]
    result = analyze(_candles(closes))
    assert result.direction == Direction.PUT
    assert result.put_score > result.call_score


def test_insufficient_candles_raises():
    with pytest.raises(AppError) as exc:
        analyze(_candles([1.0] * 10))
    assert exc.value.code == "INSUFFICIENT_DATA"


def test_flat_market_has_minimum_confidence():
    # A perfectly flat market gives indicators nothing to agree on:
    # confidence must stay at the 50 floor so the signal becomes NO_TRADE.
    closes = [1.0850] * 80
    result = analyze(_candles(closes))
    assert result.confidence == 50
    assert result.call_score == 0 and result.put_score == 0
