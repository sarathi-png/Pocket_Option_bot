# Architecture — Pocket Option Signal Bot

Modular monolith (PRD §6.1): one FastAPI process + one React SPA + one database.
No queues/caches/microservices until measured need exists.

```
                        ┌──────────────────────────────┐
                        │ Trader / Operator (browser)  │
                        └──────────────┬───────────────┘
                                       │ HTTPS (relative /api)
                        ┌──────────────▼───────────────┐
                        │ Frontend: React + TS + Vite  │
                        │ chart · generator · history  │
                        │ Telegram & auto panels       │
                        └──────────────┬───────────────┘
                                       │ /api/v1 (Vite proxy in dev)
                        ┌──────────────▼───────────────┐
                        │ Backend: FastAPI             │
                        │ routes (thin) → services:    │
                        │  market_data · indicators    │
                        │  signal_engine · telegram    │
                        │  evaluator · scheduler       │
                        │  settings_service · auth     │
                        └─────┬──────────────┬─────────┘
                              │              │
                 ┌────────────▼───┐   ┌──────▼──────────────────┐
                 │ SQLite (dev) / │   │ Telegram Bot API        │──► 📱 Signal + result
                 │ PostgreSQL     │   │ (sendMessage, HTML)     │    in user's chat
                 │ signals,       │   └─────────────────────────┘
                 │ deliveries,    │   ┌─────────────────────────┐
                 │ settings       │   │ Twelve Data (optional)  │
                 └────────────────┘   │ live candles; fallback: │
                                      │ built-in simulator      │
                                      └─────────────────────────┘
```

## Signal flow (the core journey)

1. UI or scheduler requests generation for (pair, timeframe, expiry).
2. `market_data` returns ~120 candles + `data_source` (`twelvedata` or `simulated`).
3. `signal_engine.analyze` computes EMA 9/21, RSI 14, MACD 12/26/9, Bollinger 20/2,
   Stochastic 14/3, 3-candle momentum → weighted votes → direction + confidence.
4. Gate: `TRADE` iff confidence ≥ `min_confidence` **and** vote agreement ≥ 60%, else `NO_TRADE`.
5. Signal persists (entry = last close, `expires_at = now + expiry`).
6. **Telegram push** (manual, at generation, or auto for TRADE): HTML message via Bot API,
   10 s timeout, ≤3 attempts on 429/5xx/network, delivery row recorded. Re-push of a SENT
   signal returns the existing delivery (idempotent). Unconfigured → `DRY_RUN`.
7. After expiry, `evaluator` settles WIN/LOSS/DRAW using the expiry-bucket close.
   In auto mode, settled signals that were SENT get a **result push** to Telegram.

## Deterministic simulator (why it exists)

Pocket Option has no official API, and OTC quotes are broker-generated. The simulator is a
truncated AR(1) around realistic base prices: `deviation(n) = Σ_{j=0..K-1} φ^j·shock(n−j)`,
K=500 fixed, per-bucket seeded shocks (+ slow sine drift for trends). Each bucket's price is
an exact pure function of the bucket, so (a) overlapping windows agree candle-for-candle and
(b) settlement uses exactly the expiry candle from the entry series. Tests lock this in.

## Key decisions (see ADR 0001)

- Pure-Python indicators (no TA-Lib/native deps) for portability.
- Sync SQLAlchemy + async routes only where I/O needs it (Telegram/Twelve Data).
- Settings in DB layered over env → dashboard can reconfigure Telegram/auto without restart;
  secrets masked on read, never logged.
- In-process asyncio scheduler re-reading settings per cycle (no Celery until scale demands).
- Error contract: `{error:{code,message,request_id,details[]}}` for every failure.
- Optional `X-API-Key` guard on mutating endpoints (single-owner MVP; replace with real
  user auth before any multi-user deployment).

## Directory map

```
backend/app/
  main.py            # app, middleware, lifespan, static /app mount
  auth.py            # X-API-Key dependency
  db.py models.py schemas.py
  core/ config.py errors.py logging_setup.py
  api/ routes.py     # all /api/v1 endpoints (thin)
  services/ indicators.py market_data.py signal_engine.py
            telegram.py evaluator.py scheduler.py settings_service.py
backend/tests/       # pytest (indicators, engine, data, telegram, evaluator, API)
frontend/src/
  App.tsx            # state, polling, toasts, layout
  components/ CandleChart.tsx SignalCard.tsx panels.tsx
  lib/ api.ts format.ts (+ vitest)
docs/ PRD.md ARCHITECTURE.md API_CONTRACTS.md RUNBOOK.md ADR/
```
