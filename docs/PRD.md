# Product Requirements Document — Pocket Option Signal Bot

- **Document version:** 1.0 — Implemented MVP
- **Status:** MVP implemented and verified (see §14 traceability)
- **Last updated:** October 21, 2026
- **Final delivery step (owner requirement):** *Signals are generated and pushed to a Telegram bot.*

> **Risk & compliance notice.** Binary options are high-risk speculative products; most retail
> traders lose money, and no signal system can guarantee profits. This product is an
> **educational signal generator, not financial advice and not an auto-trader**. It is not
> affiliated with Pocket Option. Users must verify that online Forex/binary-options trading is
> permitted where they live (e.g., in India, RBI/SEBI rules restrict such trading on offshore
> platforms) and must never trade money they cannot afford to lose. Pocket Option has **no
> official public API**; this product therefore never claims to read Pocket Option's own feed
> or to place trades. The user reads the Telegram signal and decides manually.

---

## 0. Project Definition

| Attribute | Definition |
|---|---|
| Project name | Pocket Option Signal Bot |
| Primary goal | Generate transparent, indicator-based CALL/PUT trade signals for Pocket Option assets/timeframes and **push them to the user's Telegram bot/chat**, then track each signal's outcome. |
| Target users | (A) Retail Pocket Option trader who wants timely, explainable signals on Telegram. (B) Owner/operator (often the same person) who configures pairs, thresholds and the Telegram bot. |
| Core stack | Frontend: React + TypeScript + Vite. Backend: Python + FastAPI. DB: SQLite by default, PostgreSQL via `DATABASE_URL`. Delivery: Telegram Bot API. Optional live candles: Twelve Data. |
| Budget | Zero-config/free-tier friendly: no paid service required (simulated candles built in). Optional Twelve Data free tier for live Forex/crypto candles. |
| Hosting constraints | Single small API process + static frontend; SQLite needs no separate DB server. Suitable for a free-tier VM/container. |
| External dependencies | Telegram Bot API (required for real delivery); Twelve Data (optional). |
| Compliance | No auto-trading; no Pocket Option credentials handled; secrets server-side only; risk disclaimers on every signal; user responsible for local legality. |

### 0.1 Definition of completion (met)
1. A user can generate a signal and receive it on Telegram without engineering help.
2. Inputs are validated on UI **and** backend; signals/deliveries persist in the DB.
3. Weak setups are labelled **NO-TRADE** and never auto-pushed (no false "tradeable" claims).
4. Unconfigured Telegram ⇒ explicit **DRY_RUN** status, never a fake "sent".
5. Outcomes (WIN/LOSS/DRAW) are settled automatically after expiry; stats are honest.
6. Core workflow covered by automated tests (35 backend + 4 frontend) and CI.

### 0.2 Provisional assumptions closed here
- Pairs: major Forex, Gold, BTC/ETH + Pocket Option-style **OTC** variants (16 assets).
- Timeframes: 1m/5m/15m/1h charts; expiry 1–60 minutes (default 2m).
- Auth: optional `API_KEY` header guard for mutating endpoints (single-owner tool; no public signup in MVP).
- Data: deterministic simulator by default; Twelve Data when a key is provided. Responses always state `data_source`.

---

## 1. Vision, Problem, Value

**Vision.** A Pocket Option trader should get a clear, explainable signal — pair, direction,
expiry, entry, confidence and *why* — delivered where they already are (Telegram), in time to
act, with an honest record of how past signals performed.

**Problems solved.** (1) Traders stare at charts and still enter late/randomly. (2) Most "signal
bots" are black boxes that hide losses and promise unrealistic win rates. (3) No single place
shows signal → delivery → outcome traceability.

**Value.** Simplicity (one click or fully automatic), transparency (every indicator vote shown,
NO-TRADE when indicators disagree), accountability (every signal settled and counted).

**Explicit non-promise.** The bot does **not** promise any win rate or profit. Historical
win-rate in the dashboard is computed only from this bot's own settled signals.

## 2. Objectives / Non-objectives

| ID | Objective | Result |
|---|---|---|
| OBJ-01 | Generate CALL/PUT signals with rationale | Multi-indicator vote (EMA/RSI/MACD/Bollinger/Stochastic/momentum) |
| OBJ-02 | Push signals to Telegram | Bot API delivery with retry, idempotency, delivery log |
| OBJ-03 | Avoid bad signals | Confidence threshold + ≥60% agreement gate ⇒ NO-TRADE |
| OBJ-04 | Measure honesty | Auto-settlement WIN/LOSS/DRAW, win-rate stats |
| OBJ-05 | Run unattended | Auto mode: watchlist cycle + auto-push + result push |
| OBJ-06 | Stay free/simple | Zero-config simulator, SQLite, single process |

**Non-objectives (MVP):** auto-trading/order placement; Pocket Option login/scraping; paid
subscriptions/multi-tenancy; native mobile apps; martingale money-management advice;
guaranteed-accuracy marketing claims of any kind.

## 3. Personas & primary journey

**Persona A — Trader.** Wants a signal now (or automatically), understands it at a glance,
receives it on Telegram, optionally places the trade manually on Pocket Option, later sees
whether it won.

**Persona B — Operator/owner.** Creates the Telegram bot via @BotFather, pastes token + chat
id, picks watchlist/thresholds, checks delivery failures and win-rate.

**Primary journey:** Open dashboard → pick pair/timeframe/expiry → *Generate & push to
Telegram* → read signal card (direction, confidence, votes, countdown) → receive the same
signal in Telegram → after expiry, outcome settles automatically → (auto mode) result is also
pushed to Telegram → review history/stats. Failure paths: invalid input → field errors;
Telegram unconfigured → dry-run notice; indicator disagreement → NO-TRADE guidance.

## 4. Functional requirements (implemented)

### Epic A — Access (Must-Have, lightweight for single-owner MVP)
- AUTH-01: If `API_KEY` is set, generate/push/settings calls require `X-API-Key`; otherwise open for local use with a startup warning.
- AUTH-02: Telegram token stored server-side only, returned masked (`••••1234`), never logged.

### Epic B — Signal generation (Must-Have)
- CORE-01: Generate a signal for any listed pair × timeframe × expiry from the dashboard or `POST /api/v1/signals/generate`.
- CORE-02: Signal contains direction, decision (TRADE/NO_TRADE), confidence 50–97, entry price, expiry time, indicator snapshot, per-indicator votes and human reasoning.
- CORE-03: Confidence = 0.65·vote-agreement + 0.35·vote-strength; TRADE requires confidence ≥ threshold (default 60) **and** agreement ≥ 60%.
- CORE-04: Backend independently validates pair, timeframe, expiry (Pydantic + domain checks) regardless of client.
- CORE-05: Signals persist with full audit fields; repeated reads return authoritative state.

### Epic C — Telegram delivery (Must-Have — the final step)
- TG-01: Push any signal to the configured chat (`POST /signals/{id}/push-telegram` or `push_telegram=true` at generation).
- TG-02: Message is HTML-formatted: pair, direction, timeframe, expiry, entry, confidence, IST+UTC time, top reasons, risk disclaimer.
- TG-03: Bounded timeout (10s) + up to 3 attempts with backoff on 429/5xx/network errors; 4xx fails fast.
- TG-04: **Idempotent:** re-pushing a SENT signal returns the original delivery (no spam) unless `force=true` at API level.
- TG-05: Unconfigured ⇒ DRY_RUN record + clear UI note. Test-message endpoint verifies setup end-to-end.
- TG-06: Every attempt is logged as a delivery row (status, provider message id, sanitized error code, masked chat id).
- TG-07: In auto mode, settled signals that were SENT also get a result push (WIN/LOSS/DRAW).

### Epic D — Automation & settlement (Must-Have)
- AUTO-01: Background scheduler generates signals for a watchlist every N seconds (30–3600).
- AUTO-02: Only TRADE signals auto-push. SETTLE-01: expired PENDING signals settle to WIN/LOSS/DRAW using the expiry-bucket close from the same data provider.

### Epic E — Dashboard, history, stats (Must-Have)
- UX-01: Live dashboard: candlestick chart + EMA lines, generator, latest signal card with countdown, history table (paginated, click to inspect), stats cards, Telegram + auto panels.
- UX-02: Loading/empty/error states and actionable toasts; duplicate-submit disabled while generating/pushing.

### Epic F — Observability & analytics-lite (Must-Have)
- OPS-01: `GET /api/v1/health`; structured logs with `X-Request-ID` correlation; consistent error body `{error:{code,message,request_id,details}}`.
- OPS-02: Product metrics from DB: signals by decision/outcome/pair, win rate, delivery counts.

## 5. Non-functional requirements

| ID | Requirement | Implementation |
|---|---|---|
| NFR-P01 | Ordinary API p95 < 500 ms locally | In-process indicator math on ≤300 candles; bounded lists/pagination |
| NFR-R01 | One bad pair/cycle must not crash the service | Per-pair try/except in scheduler; global exception handler |
| NFR-R02 | External calls bounded | 10 s timeouts, ≤3 retries, provider fallback to simulator |
| NFR-S01 | No secret leakage | Masked token/chat in API, secrets excluded from logs/errors/previews; CORS allowlist; `X-API-Key` compared in constant time |
| NFR-D01 | Honest states | NO-TRADE gate, DRY_RUN vs SENT, win rate only over settled WIN+LOSS |
| NFR-A11y | Keyboard-usable, labelled controls, non-colour cues (▲/▼ + text) | Semantic labels, focus outlines, aria-live toasts |

## 6. Architecture (summary — see ARCHITECTURE.md)

React dashboard → FastAPI (thin routes → services: market_data, indicators, signal_engine,
telegram, evaluator, scheduler, settings) → SQLAlchemy (SQLite/PostgreSQL). Telegram Bot API
and optional Twelve Data sit behind service modules with timeouts/fallbacks. Deterministic
simulated candles (truncated AR(1), fixed shock window) make every bucket reproducible, so
settlement uses exactly the expiry candle close. Scheduler is an in-process asyncio loop
reading persisted settings each cycle.

## 7. Data model (summary)

`Signal` (pair, direction, decision, timeframe, expiry, confidence, entry/exit, outcome,
indicators/votes/reasoning JSON, data_source, timestamps) · `TelegramDelivery` (signal FK,
kind signal/test/result, status SENT/FAILED/DRY_RUN, provider id, sanitized error, attempts) ·
`Setting` (key/value runtime config incl. Telegram credentials and automation).

## 8. Success metrics

- Activation: first real Telegram test message SENT.
- Core success: generated TRADE signals delivered SENT ≥ 99% when Telegram is reachable (excluding user/config errors).
- Honesty: 100% of expired signals settled; win rate displayed only with settled denominator.
- Reliability: scheduler cycles complete without process restart; API error rate < 1% excl. validation.
- **Not a success metric:** trading profit (outside product control; never marketed).

## 9. Risks & fallbacks

| ID | Risk | Mitigation / fallback |
|---|---|---|
| R-01 | Users treat signals as guaranteed profit | Disclaimers everywhere, NO-TRADE gate, honest stats, no win-rate marketing |
| R-02 | No official Pocket Option API / price differs from PO (esp. OTC) | Always label data source; advise chart confirmation; optional live Twelve Data for non-OTC |
| R-03 | Telegram outage/rate limit | Retries + FAILED records + dashboard visibility; signals still in history |
| R-04 | Wrong token/chat id | Test button, 4xx fail-fast with guidance, dry-run default |
| R-05 | Duplicate pushes spam the chat | Idempotent push (R-12 in template) |
| R-06 | Regulatory restrictions (e.g., India) | Compliance notice; no auto-trading; user decides |
| R-07 | Free-tier DB/host limits | SQLite default, pagination, single process |

## 10. Roadmap status

- **Phase 1 (done):** repo/env, backend+frontend foundations, vertical slice generate→persist→display.
- **Phase 2 (done):** full indicator engine, Telegram delivery + settings UI, auto mode, settlement, stats.
- **Phase 3 (done for MVP):** automated tests (unit/API/UI-unit), build verification, docs/runbook, CI. Production hardening (managed Postgres, Alembic migrations, secret manager, alerts) is post-MVP — see RUNBOOK.

## 11. Open decisions

| ID | Decision | Default taken | Owner to confirm |
|---|---|---|---|
| D-01 | Telegram bot token + chat id | Configured by user in dashboard/env (cannot be prefilled) | Product owner |
| D-02 | Live data vs simulator | Simulator; add `TWELVE_DATA_API_KEY` for live non-OTC candles | Product owner |
| D-03 | Public deployment target + `API_KEY` | Local/open by default; set `API_KEY` before exposing | Technical owner |
| D-04 | Default watchlist/thresholds | EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD; 60% min confidence; 60 s cycle | Product owner |

## 14. Traceability (requirement → evidence)

| Area | Evidence |
|---|---|
| Indicators & engine | `backend/tests/test_indicators.py`, `test_signal_engine.py` (uptrend→CALL, downtrend→PUT, flat→50/NO-TRADE) |
| Market consistency | `test_market_data.py` (overlapping windows identical; candle_at matches series) |
| Telegram final step | `test_telegram.py` (format, dry-run honesty, mocked send, idempotency, failure) + live dry-run delivery preview in dashboard |
| API contracts/errors/auth | `test_api.py` (health, validation shape, generate/persist/list, settings masking, stats) |
| Settlement | `test_evaluator.py` (CALL/PUT win/loss vs deterministic candles) |
| Frontend | `src/lib/format.test.ts`, TypeScript build, manual dashboard verification |

**Final acceptance standard (from owner):** *Signals are generated and pushed to the Telegram
bot* — implemented as `generate → (TRADE gate) → Telegram push (SENT/FAILED/DRY_RUN) → settle
→ result push`, demonstrable end-to-end from the dashboard once the owner adds their bot token
and chat id (2-minute BotFather setup in README/RUNBOOK).
