"""Signal engine: multi-indicator weighted voting (PRD Epic B / CORE-*).

Method (documented so users can judge it — no black box, no win guarantees):
  EMA 9/21 trend · RSI 14 · MACD 12/26/9 · Bollinger 20/2 · Stochastic 14/3
  · short candle momentum. Each indicator votes CALL/PUT/NEUTRAL with a fixed
  weight. Confidence blends vote agreement and vote strength (50..97).
  If agreement < 60% or confidence < the configured threshold the signal is
  marked NO_TRADE and is never auto-pushed to Telegram (CORE-07: the system
  must not present weak setups as tradeable signals).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.core.errors import AppError
from app.models import Decision, Direction, Signal
from app.services import indicators as ind
from app.services.market_data import Candle, get_pair, provider

MIN_CANDLES = 40
MAX_SCORE = 2.0 + 1.5 + 1.5 + 1.25 + 1.25 + 0.5  # sum of max vote weights

DISCLAIMER = (
    "Educational signal only — not financial advice. Binary options are high risk; "
    "you can lose your stake. Past indicator behaviour does not guarantee future results."
)


@dataclass
class Vote:
    indicator: str
    direction: str  # CALL | PUT | NEUTRAL
    weight: float
    detail: str

    def to_dict(self) -> dict:
        return {"indicator": self.indicator, "direction": self.direction, "weight": self.weight, "detail": self.detail}


@dataclass
class Analysis:
    direction: Direction
    confidence: int
    agreement: float
    call_score: float
    put_score: float
    indicators: dict = field(default_factory=dict)
    votes: list[Vote] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def analyze(candles: list[Candle]) -> Analysis:
    if len(candles) < MIN_CANDLES:
        raise AppError(
            "INSUFFICIENT_DATA",
            f"Need at least {MIN_CANDLES} candles to analyse, got {len(candles)}.",
            status_code=422,
        )
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    votes: list[Vote] = []
    snapshot: dict = {}

    # --- EMA 9/21 trend (weight 2.0) ---
    ema9, ema21 = ind.ema(closes, 9), ind.ema(closes, 21)
    snapshot["ema9"], snapshot["ema21"] = _r(ema9), _r(ema21)
    if ema9 is not None and ema21 is not None:
        if ema9 > ema21:
            votes.append(Vote("EMA 9/21", "CALL", 2.0, "EMA9 above EMA21 — short-term uptrend"))
        elif ema9 < ema21:
            votes.append(Vote("EMA 9/21", "PUT", 2.0, "EMA9 below EMA21 — short-term downtrend"))
        else:
            votes.append(Vote("EMA 9/21", "NEUTRAL", 0.0, "EMAs flat — no trend"))

    # --- RSI 14 (max weight 1.5) ---
    rsi_v = ind.rsi(closes, 14)
    snapshot["rsi14"] = _r(rsi_v, 2)
    if rsi_v is not None:
        if rsi_v <= 30:
            votes.append(Vote("RSI 14", "CALL", 1.5, f"RSI {rsi_v:.1f} oversold — bounce likely"))
        elif rsi_v >= 70:
            votes.append(Vote("RSI 14", "PUT", 1.5, f"RSI {rsi_v:.1f} overbought — pullback likely"))
        elif rsi_v > 50:
            votes.append(Vote("RSI 14", "CALL", 0.75, f"RSI {rsi_v:.1f} bullish momentum"))
        elif rsi_v < 50:
            votes.append(Vote("RSI 14", "PUT", 0.75, f"RSI {rsi_v:.1f} bearish momentum"))
        else:
            votes.append(Vote("RSI 14", "NEUTRAL", 0.0, "RSI 50.0 neutral"))

    # --- MACD 12/26/9 (max weight 1.5) ---
    macd_v = ind.macd(closes)
    if macd_v:
        snapshot["macd"] = {k: _r(v) if isinstance(v, float) else v for k, v in macd_v.items()}
        hist, rising = macd_v["histogram"], macd_v["rising"]
        if hist > 0 and rising:
            votes.append(Vote("MACD", "CALL", 1.5, "MACD histogram positive and rising"))
        elif hist < 0 and not rising:
            votes.append(Vote("MACD", "PUT", 1.5, "MACD histogram negative and falling"))
        elif hist > 0:
            votes.append(Vote("MACD", "CALL", 0.75, "MACD histogram positive (fading)"))
        elif hist < 0:
            votes.append(Vote("MACD", "PUT", 0.75, "MACD histogram negative (fading)"))
        else:
            votes.append(Vote("MACD", "NEUTRAL", 0.0, "MACD histogram at zero"))

    # --- Bollinger Bands 20/2 (max weight 1.25) ---
    bb = ind.bollinger(closes)
    if bb:
        snapshot["bollinger"] = {k: _r(v) for k, v in bb.items()}
        pct_b = bb["pct_b"]
        if pct_b <= 0.05:
            votes.append(Vote("Bollinger", "CALL", 1.25, "Price at lower band — mean-reversion up"))
        elif pct_b >= 0.95:
            votes.append(Vote("Bollinger", "PUT", 1.25, "Price at upper band — mean-reversion down"))
        elif closes[-1] > bb["middle"]:
            votes.append(Vote("Bollinger", "CALL", 0.5, "Price above Bollinger midline"))
        elif closes[-1] < bb["middle"]:
            votes.append(Vote("Bollinger", "PUT", 0.5, "Price below Bollinger midline"))

    # --- Stochastic 14/3 (max weight 1.25) ---
    stoch = ind.stochastic(highs, lows, closes)
    if stoch:
        snapshot["stochastic"] = {"k": _r(stoch["k"], 2), "d": _r(stoch["d"], 2)}
        k, d = stoch["k"], stoch["d"]
        if k < 20 and k > d:
            votes.append(Vote("Stochastic", "CALL", 1.25, f"Stochastic {k:.1f} crossing up from oversold"))
        elif k > 80 and k < d:
            votes.append(Vote("Stochastic", "PUT", 1.25, f"Stochastic {k:.1f} crossing down from overbought"))
        elif k > d:
            votes.append(Vote("Stochastic", "CALL", 0.5, f"Stochastic %K {k:.1f} above %D"))
        elif k < d:
            votes.append(Vote("Stochastic", "PUT", 0.5, f"Stochastic %K {k:.1f} below %D"))

    # --- Short candle momentum (weight 0.5) ---
    mom = ind.candle_momentum(closes, 3)
    snapshot["momentum_3"] = _r(mom, 6)
    if mom is not None and mom != 0:
        direction = "CALL" if mom > 0 else "PUT"
        votes.append(Vote("Momentum", direction, 0.5, f"Last 3 candles moved {mom * 100:+.3f}%"))

    call_score = sum(v.weight for v in votes if v.direction == "CALL")
    put_score = sum(v.weight for v in votes if v.direction == "PUT")
    total = call_score + put_score
    direction = Direction.CALL if call_score >= put_score else Direction.PUT
    winner = max(call_score, put_score)
    agreement = winner / total if total > 0 else 0.5
    strength = winner / MAX_SCORE if MAX_SCORE else 0.0
    confidence = int(round((0.65 * agreement + 0.35 * strength) * 100))
    confidence = max(50, min(97, confidence))

    reasoning = [
        f"{'▲' if v.direction == 'CALL' else '▼' if v.direction == 'PUT' else '•'} {v.indicator}: {v.detail}"
        for v in votes
    ]
    return Analysis(
        direction=direction,
        confidence=confidence,
        agreement=round(agreement, 3),
        call_score=round(call_score, 2),
        put_score=round(put_score, 2),
        indicators=snapshot,
        votes=votes,
        reasoning=reasoning,
    )


def _r(v: float | None, digits: int = 6) -> float | None:
    return round(v, digits) if isinstance(v, float) else v


async def generate_signal(
    db,
    pair: str,
    timeframe: str,
    expiry_minutes: int,
    min_confidence: int,
    source: str = "manual",
) -> Signal:
    """Fetch candles, analyse, persist and return a Signal (CORE-01..CORE-09)."""
    info = get_pair(pair)
    if info is None:
        raise AppError("PAIR_NOT_FOUND", f"Unknown pair '{pair}'. See GET /api/v1/pairs.", status_code=404)
    candles, data_source = await provider.get_candles(info.symbol, timeframe, limit=120)
    result = analyze(candles)
    decision = (
        Decision.TRADE
        if result.confidence >= min_confidence and result.agreement >= 0.60
        else Decision.NO_TRADE
    )
    now = datetime.now(timezone.utc)
    signal = Signal(
        pair=info.symbol,
        display_pair=info.display,
        direction=result.direction,
        decision=decision,
        timeframe=timeframe,
        expiry_minutes=expiry_minutes,
        confidence=result.confidence,
        entry_price=candles[-1].close,
        data_source=data_source,
        indicators={
            **result.indicators,
            "call_score": result.call_score,
            "put_score": result.put_score,
            "agreement": result.agreement,
        },
        votes=[v.to_dict() for v in result.votes],
        reasoning=result.reasoning,
        source=source,
        created_at=now,
        expires_at=now + timedelta(minutes=expiry_minutes),
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal
