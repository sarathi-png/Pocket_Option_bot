"""Optional API-key guard for mutating endpoints (PRD Epic A).

If API_KEY is configured, requests must send `X-API-Key: <key>`. If it is not
configured (local development), endpoints are open and a warning is logged at
startup. Read-only GET endpoints stay open so the dashboard can poll freely;
tighten this before exposing the service publicly.
"""
from __future__ import annotations

import hmac

from fastapi import Header

from app.core.config import get_settings
from app.core.errors import AppError


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    configured = get_settings().api_key
    if not configured:
        return
    if x_api_key is None or not hmac.compare_digest(x_api_key, configured):
        raise AppError("UNAUTHORIZED", "Missing or invalid API key.", status_code=401)
