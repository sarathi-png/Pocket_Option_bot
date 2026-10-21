# ADR 0001 — Initial architecture & key decisions

**Status:** Accepted (MVP, Oct 2026)

## Context
Single-owner Pocket Option signal tool. Must generate explainable signals and push them to
Telegram, run free/zero-config, and never overclaim (no official Pocket Option API exists).

## Decisions
1. **Stack:** React+TS+Vite SPA, FastAPI backend, SQLAlchemy with SQLite default /
   PostgreSQL via `DATABASE_URL`. *Alternatives:* Django/Next.js monolith (heavier),
   server-rendered templates (poorer live dashboard UX).
2. **Signal method:** transparent weighted indicator vote (EMA/RSI/MACD/Bollinger/
   Stochastic/momentum) with confidence + agreement gate → TRADE/NO_TRADE. *Alternative:*
   ML model — rejected for MVP (no labelled data, opaque, overfitting risk).
3. **Market data:** deterministic simulator (truncated AR(1), fixed shock window) default;
   Twelve Data optional with fallback. Responses always carry `data_source`.
   *Alternative:* scraping Pocket Option — rejected (no official API, brittle, ToS risk).
4. **Telegram:** direct Bot API via httpx, idempotent pushes, delivery ledger, dry-run mode.
   *Alternative:* python-telegram-bot polling app — unnecessary; we only send.
5. **Auth:** optional shared `X-API-Key` for mutating endpoints. *Revisit* with real user
   accounts/OAuth before any multi-user or public deployment.
6. **Scheduling:** in-process asyncio loop. *Revisit* (Celery/RQ) if multiple workers or
   heavy backtests are added.
7. **Schema management:** `create_all` for MVP. *Revisit* with Alembic before first
   production schema change.

## Consequences
- Zero paid dependencies; runs on a laptop or free-tier host.
- Simulated/OTC prices will differ from Pocket Option quotes — mitigated by labelling and
  chart-confirmation guidance, not eliminated.
- Single-process scheduler means auto mode pauses while the backend is down; settlements
  catch up on next read/cycle.
