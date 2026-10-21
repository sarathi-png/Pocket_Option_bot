"""API request/response contracts (PRD §6.5). Backend validates everything (VAL-03)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import Signal
from app.services.market_data import TIMEFRAMES

Timeframe = Literal["1m", "5m", "15m", "1h"]


class GenerateSignalRequest(BaseModel):
    pair: str = Field(min_length=3, max_length=20, examples=["EURUSD"])
    timeframe: Timeframe = "1m"
    expiry_minutes: int = Field(default=2, ge=1, le=60)
    push_telegram: bool = False

    @field_validator("pair")
    @classmethod
    def _clean_pair(cls, v: str) -> str:
        return v.strip().upper().replace("/", "")


class PushRequest(BaseModel):
    force: bool = False


class SignalOut(BaseModel):
    id: str
    pair: str
    display_pair: str
    direction: str
    decision: str
    timeframe: str
    expiry_minutes: int
    confidence: int
    entry_price: float
    exit_price: float | None
    outcome: str
    data_source: str
    indicators: dict
    votes: list
    reasoning: list
    source: str
    telegram_status: str
    created_at: datetime
    expires_at: datetime
    evaluated_at: datetime | None

    @classmethod
    def from_model(cls, s: Signal) -> "SignalOut":
        return cls(
            id=s.id,
            pair=s.pair,
            display_pair=s.display_pair or s.pair,
            direction=s.direction.value,
            decision=s.decision.value,
            timeframe=s.timeframe,
            expiry_minutes=s.expiry_minutes,
            confidence=s.confidence,
            entry_price=s.entry_price,
            exit_price=s.exit_price,
            outcome=s.outcome.value,
            data_source=s.data_source,
            indicators=s.indicators or {},
            votes=s.votes or [],
            reasoning=s.reasoning or [],
            source=s.source,
            telegram_status=s.telegram_status,
            created_at=s.created_at,
            expires_at=s.expires_at,
            evaluated_at=s.evaluated_at,
        )


class PaginatedSignals(BaseModel):
    items: list[SignalOut]
    total: int
    page: int
    page_size: int


class PairOut(BaseModel):
    symbol: str
    display: str
    category: str
    decimals: int


class CandleOut(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandlesOut(BaseModel):
    pair: str
    timeframe: str
    data_source: str
    candles: list[CandleOut]
    ema9: list[float | None]
    ema21: list[float | None]


class StatsOut(BaseModel):
    total_signals: int
    trade_signals: int
    no_trade_signals: int
    pending: int
    wins: int
    losses: int
    draws: int
    win_rate_pct: float | None  # None until at least one settled win/loss
    avg_confidence: float | None
    telegram_sent: int
    telegram_failed: int
    telegram_dry_run: int
    by_pair: list[dict]


class TelegramStatusOut(BaseModel):
    configured: bool
    bot_token_masked: str
    chat_id_masked: str
    deliveries_sent: int


class TelegramSettingsIn(BaseModel):
    # Empty string = leave unchanged; send explicit value to set. Use clear=true to remove.
    bot_token: str = ""
    chat_id: str = ""
    clear: bool = False


class SettingsOut(BaseModel):
    auto_enabled: bool
    auto_push_telegram: bool
    min_confidence: int
    watchlist: list[str]
    auto_interval_seconds: int
    default_timeframe: str
    default_expiry_minutes: int
    telegram: TelegramStatusOut


class SettingsUpdateIn(BaseModel):
    auto_enabled: bool | None = None
    auto_push_telegram: bool | None = None
    min_confidence: int | None = Field(default=None, ge=50, le=95)
    watchlist: list[str] | None = None
    auto_interval_seconds: int | None = Field(default=None, ge=30, le=3600)
    default_timeframe: Timeframe | None = None
    default_expiry_minutes: int | None = Field(default=None, ge=1, le=60)

    @field_validator("watchlist")
    @classmethod
    def _clean_watchlist(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned = [p.strip().upper().replace("/", "") for p in v if p.strip()]
        return cleaned[:16]


def validate_timeframe(tf: str) -> str:
    if tf not in TIMEFRAMES:
        from app.core.errors import AppError

        raise AppError("VALIDATION_ERROR", f"Unsupported timeframe '{tf}'. Use one of {sorted(TIMEFRAMES)}.", status_code=422)
    return tf
