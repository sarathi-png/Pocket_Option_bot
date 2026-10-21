"""Environment configuration (PRD §7.4: validated at startup, explicit failure)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Pocket Option Signal Bot"
    database_url: str = "sqlite:///./data/signals.db"

    # If set, mutating endpoints require the X-API-Key header (PRD Epic A / §4.3).
    api_key: str = ""

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Telegram defaults (can be overridden at runtime via the settings API / dashboard).
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Automation defaults (also runtime-overridable, persisted in DB).
    auto_signals_enabled: bool = False
    auto_push_telegram: bool = False
    auto_interval_seconds: int = 60
    min_confidence: int = 60
    watchlist: str = "EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD"
    default_timeframe: str = "1m"
    default_expiry_minutes: int = 2

    # Optional real market-data provider; empty = built-in simulator.
    twelve_data_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def watchlist_list(self) -> list[str]:
        return [p.strip().upper() for p in self.watchlist.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
