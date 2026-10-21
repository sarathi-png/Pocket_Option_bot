"""Consistent API error format (PRD §4.6).

Every error response is:
{ "error": { "code": "...", "message": "...", "request_id": "...", "details": [...] } }
Internal exception details are never returned to clients.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging_setup import get_logger, request_id_var

logger = get_logger("app.errors")


class AppError(Exception):
    """Domain error with a stable machine-readable code."""

    def __init__(self, code: str, message: str, status_code: int = 400, details: list | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


def error_body(code: str, message: str, details: list | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_var.get(),
            "details": details or [],
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
                "code": str(err.get("type", "INVALID")).upper(),
                "message": err.get("msg", "Invalid value."),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body("VALIDATION_ERROR", "Please correct the highlighted fields.", details),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=error_body("INTERNAL_ERROR", "Something went wrong. Please retry; if it persists, check server logs with the request id."),
        )
