"""Technical indicators in pure Python (no TA-Lib dependency).

All functions return None when there is insufficient data instead of raising,
so the signal engine can treat them as neutral votes (PRD VAL-* / fail safely).
"""
from __future__ import annotations

import math
from statistics import mean, pstdev


def ema_series(values: list[float], period: int) -> list[float]:
    """Exponential moving average series, seeded with the first value."""
    if not values or period <= 0:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return ema_series(values, period)[-1]


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return mean(values[-period:])


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI (latest value, 0..100)."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0 and avg_gain == 0:
        return 50.0  # perfectly flat series = neutral, not "maximally overbought"
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict | None:
    """MACD line / signal line / histogram (latest + previous histogram)."""
    if len(closes) < slow + signal:
        return None
    fast_s = ema_series(closes, fast)
    slow_s = ema_series(closes, slow)
    macd_s = [f - s for f, s in zip(fast_s, slow_s)]
    signal_s = ema_series(macd_s, signal)
    hist = macd_s[-1] - signal_s[-1]
    prev_hist = macd_s[-2] - signal_s[-2] if len(macd_s) > 1 else hist
    return {
        "macd": macd_s[-1],
        "signal": signal_s[-1],
        "histogram": hist,
        "prev_histogram": prev_hist,
        "rising": hist > prev_hist,
    }


def bollinger(closes: list[float], period: int = 20, mult: float = 2.0) -> dict | None:
    """Bollinger Bands + %B (0 = at lower band, 1 = at upper band)."""
    if len(closes) < period:
        return None
    window = closes[-period:]
    mid = mean(window)
    sd = pstdev(window)
    upper, lower = mid + mult * sd, mid - mult * sd
    width = upper - lower
    pct_b = (closes[-1] - lower) / width if width > 0 else 0.5
    return {"upper": upper, "middle": mid, "lower": lower, "pct_b": pct_b}


def stochastic(
    highs: list[float], lows: list[float], closes: list[float], k_period: int = 14, d_period: int = 3
) -> dict | None:
    """Stochastic oscillator %K / %D (latest values, 0..100)."""
    if len(closes) < k_period + d_period:
        return None
    k_values: list[float] = []
    for i in range(k_period - 1, len(closes)):
        hh = max(highs[i - k_period + 1 : i + 1])
        ll = min(lows[i - k_period + 1 : i + 1])
        k_values.append(50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100)
    k_latest = k_values[-1]
    d_latest = mean(k_values[-d_period:])
    return {"k": k_latest, "d": d_latest, "crossed_up": k_latest > d_latest}


def candle_momentum(closes: list[float], lookback: int = 3) -> float | None:
    """Fractional change over the last `lookback` candles."""
    if len(closes) < lookback + 1 or closes[-lookback - 1] == 0:
        return None
    return (closes[-1] - closes[-lookback - 1]) / closes[-lookback - 1]


def is_finite_number(v: float | None) -> bool:
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)
