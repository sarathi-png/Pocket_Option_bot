"""Application entrypoint: FastAPI app, middleware, lifespan (PRD §6.2/§7.4)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging_setup import get_logger, new_request_id, setup_logging
from app.db import init_db
from app.services.scheduler import scheduler

setup_logging()
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    init_db()
    if not settings.api_key:
        logger.warning("API_KEY is not set — mutating endpoints are open. Set API_KEY before public deployment.")
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        logger.info("Telegram not configured via env — set it in the dashboard or env vars. Pushes will be DRY_RUN until then.")
    scheduler.start()  # loop itself checks the persisted auto_enabled flag each cycle
    logger.info("%s v%s ready", settings.app_name, __version__)
    yield
    await scheduler.stop()


app = FastAPI(
    title=get_settings().app_name,
    version=__version__,
    description=(
        "Generates Pocket Option trade signals from technical indicators and pushes them to Telegram. "
        "Educational tool only — not financial advice. Binary options are high risk."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_origin_regex=r"https://.*\.e2b\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or new_request_id()
    if request.headers.get("x-request-id"):
        from app.core.logging_setup import request_id_var

        request_id_var.set(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


register_error_handlers(app)
app.include_router(router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "service": get_settings().app_name,
        "docs": "/docs",
        "health": "/api/v1/health",
        "dashboard": "Run the frontend (npm run dev) or build it and it will be served from /app",
    }


# Production convenience: serve the built frontend (frontend/dist) from /app
_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/app", StaticFiles(directory=_dist, html=True), name="frontend")
