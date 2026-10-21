"""Auto-signal scheduler (optional background loop).

Every `auto_interval_seconds`: generate one signal per watchlist pair, push
TRADE signals to Telegram when auto-push is on, settle expired signals and
optionally push their results. Settings are re-read each cycle so dashboard
changes take effect without a restart. The loop never crashes the API —
errors are logged and the next cycle retries (NFR-R01).
"""
from __future__ import annotations

import asyncio

from app.core.logging_setup import get_logger
from app.db import SessionLocal
from app.models import Decision
from app.services import evaluator, settings_service, signal_engine, telegram

logger = get_logger("app.scheduler")


class Scheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self.cycles = 0
        self.last_run_summary = "never run"

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self.running:
            self._task = asyncio.create_task(self._loop())
            logger.info("Auto-signal scheduler started")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Auto-signal scheduler stopped")

    async def run_cycle(self) -> str:
        db = SessionLocal()
        try:
            cfg = settings_service.get(db)
            generated, pushed = 0, 0
            for pair in cfg["watchlist"]:
                try:
                    signal = await signal_engine.generate_signal(
                        db,
                        pair=pair,
                        timeframe=cfg["default_timeframe"],
                        expiry_minutes=cfg["default_expiry_minutes"],
                        min_confidence=cfg["min_confidence"],
                        source="auto",
                    )
                    generated += 1
                    if cfg["auto_push_telegram"] and signal.decision == Decision.TRADE:
                        delivery = await telegram.push_signal(db, signal)
                        if delivery.status.value == "SENT":
                            pushed += 1
                except Exception as exc:  # one bad pair must not stop the cycle
                    logger.warning("Auto-signal failed for %s: %s", pair, type(exc).__name__)
            settled = evaluator.evaluate_due_signals(db)
            results_pushed = 0
            if cfg["auto_push_telegram"]:
                for s in settled:
                    # Only follow up in Telegram for signals the chat actually received
                    if s.telegram_status == "SENT":
                        delivery = await telegram.push_result(db, s)
                        if delivery is not None and delivery.status.value == "SENT":
                            results_pushed += 1
            summary = f"generated={generated} pushed={pushed} settled={len(settled)} results_pushed={results_pushed}"
            self.cycles += 1
            self.last_run_summary = summary
            logger.info("Auto cycle %s: %s", self.cycles, summary)
            return summary
        finally:
            db.close()

    async def _loop(self) -> None:
        while True:
            db = SessionLocal()
            try:
                cfg = settings_service.get(db)
                interval = cfg["auto_interval_seconds"]
                enabled = cfg["auto_enabled"]
            finally:
                db.close()
            if enabled:
                try:
                    await self.run_cycle()
                except Exception as exc:
                    logger.exception("Auto cycle error: %s", type(exc).__name__)
            await asyncio.sleep(interval)


scheduler = Scheduler()
