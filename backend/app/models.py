"""Persistence entities (PRD §6.6, specialized for trading signals).

No secrets are stored on Signal/Delivery rows. The Telegram bot token lives
only in the Setting table / env, is returned masked by the API, and is never logged.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Direction(str, enum.Enum):
    CALL = "CALL"  # price expected UP
    PUT = "PUT"  # price expected DOWN


class Decision(str, enum.Enum):
    TRADE = "TRADE"
    NO_TRADE = "NO_TRADE"  # indicators disagree / confidence below threshold


class Outcome(str, enum.Enum):
    PENDING = "PENDING"
    WIN = "WIN"
    LOSS = "LOSS"
    DRAW = "DRAW"


class DeliveryStatus(str, enum.Enum):
    SENT = "SENT"
    FAILED = "FAILED"
    DRY_RUN = "DRY_RUN"  # Telegram not configured: message formatted but NOT sent


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    pair: Mapped[str] = mapped_column(String(20), index=True)
    display_pair: Mapped[str] = mapped_column(String(40), default="")
    direction: Mapped[Direction] = mapped_column(Enum(Direction))
    decision: Mapped[Decision] = mapped_column(Enum(Decision), default=Decision.TRADE, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), default="1m")
    expiry_minutes: Mapped[int] = mapped_column(Integer, default=2)
    confidence: Mapped[int] = mapped_column(Integer, default=50)  # 50..97
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[Outcome] = mapped_column(Enum(Outcome), default=Outcome.PENDING, index=True)
    data_source: Mapped[str] = mapped_column(String(20), default="simulated")  # simulated | twelvedata
    indicators: Mapped[dict] = mapped_column(JSON, default=dict)
    votes: Mapped[list] = mapped_column(JSON, default=list)
    reasoning: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | auto
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    deliveries: Mapped[list["TelegramDelivery"]] = relationship(back_populates="signal", cascade="all, delete-orphan")

    @property
    def telegram_status(self) -> str:
        """Latest delivery status: SENT > DRY_RUN > FAILED > NOT_SENT."""
        if not self.deliveries:
            return "NOT_SENT"
        statuses = {d.status for d in self.deliveries}
        for preferred in (DeliveryStatus.SENT, DeliveryStatus.DRY_RUN, DeliveryStatus.FAILED):
            if preferred in statuses:
                return preferred.value
        return "NOT_SENT"


class TelegramDelivery(Base):
    __tablename__ = "telegram_deliveries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    signal_id: Mapped[str | None] = mapped_column(ForeignKey("signals.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="signal")  # signal | test
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus), index=True)
    chat_id_masked: Mapped[str] = mapped_column(String(40), default="")
    provider_message_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)  # sanitized, no secrets
    message_preview: Mapped[str] = mapped_column(Text, default="")
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    signal: Mapped[Signal | None] = relationship(back_populates="deliveries")


class Setting(Base):
    """Runtime settings (Telegram credentials, automation) editable from the dashboard."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
