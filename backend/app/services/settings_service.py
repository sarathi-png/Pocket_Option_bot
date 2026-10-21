"""Runtime settings persisted in DB, layered over env defaults.

The Telegram token set via the dashboard is stored server-side only and is
always returned masked by the API (PRD §4.3: never expose secrets to clients).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Setting

_KEYS = [
    "telegram_bot_token",
    "telegram_chat_id",
    "auto_enabled",
    "auto_push_telegram",
    "min_confidence",
    "watchlist",
    "auto_interval_seconds",
    "default_timeframe",
    "default_expiry_minutes",
]


def _env_defaults() -> dict:
    env = get_settings()
    return {
        "telegram_bot_token": env.telegram_bot_token,
        "telegram_chat_id": env.telegram_chat_id,
        "auto_enabled": "true" if env.auto_signals_enabled else "false",
        "auto_push_telegram": "true" if env.auto_push_telegram else "false",
        "min_confidence": str(env.min_confidence),
        "watchlist": json.dumps(env.watchlist_list),
        "auto_interval_seconds": str(env.auto_interval_seconds),
        "default_timeframe": env.default_timeframe,
        "default_expiry_minutes": str(env.default_expiry_minutes),
    }


def get_raw(db: Session) -> dict[str, str]:
    values = _env_defaults()
    for row in db.query(Setting).filter(Setting.key.in_(_KEYS)).all():
        values[row.key] = row.value
    return values


def get(db: Session) -> dict:
    raw = get_raw(db)
    try:
        watchlist = json.loads(raw["watchlist"])
        if not isinstance(watchlist, list):
            watchlist = get_settings().watchlist_list
    except (ValueError, TypeError):
        watchlist = get_settings().watchlist_list
    return {
        "telegram_bot_token": raw["telegram_bot_token"].strip(),
        "telegram_chat_id": raw["telegram_chat_id"].strip(),
        "auto_enabled": raw["auto_enabled"].lower() == "true",
        "auto_push_telegram": raw["auto_push_telegram"].lower() == "true",
        "min_confidence": _int(raw["min_confidence"], 60, 50, 95),
        "watchlist": [str(p).upper() for p in watchlist],
        "auto_interval_seconds": _int(raw["auto_interval_seconds"], 60, 30, 3600),
        "default_timeframe": raw["default_timeframe"] if raw["default_timeframe"] in ("1m", "5m", "15m", "1h") else "1m",
        "default_expiry_minutes": _int(raw["default_expiry_minutes"], 2, 1, 60),
    }


def _int(value: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (ValueError, TypeError):
        return default


def update(db: Session, changes: dict) -> dict:
    """Persist provided keys. Empty token value means 'keep existing' (handled by caller)."""
    for key, value in changes.items():
        if key not in _KEYS or value is None:
            continue
        text = json.dumps(value) if key == "watchlist" else str(value).lower() if isinstance(value, bool) else str(value)
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=text))
        else:
            row.value = text
    db.commit()
    return get(db)


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return f"••••{value[-4:]}" if len(value) > 4 else "••••"


def mask_chat_id(value: str) -> str:
    if not value:
        return ""
    return f"…{value[-4:]}" if len(value) > 4 else value
