# 📡 Pocket Option Signal Bot

Generates transparent, indicator-based **CALL/PUT signals** for Pocket Option assets and
**pushes them to your Telegram bot** — then automatically settles each signal (WIN/LOSS/DRAW)
after expiry so performance stays honest.

> ⚠️ **Please read first.** Binary options are high-risk; most retail traders lose money and
> **no bot can guarantee wins or profits**. This is an **educational signal tool, not financial
> advice and not an auto-trader**. It is not affiliated with Pocket Option, which has no
> official public API — so signals are computed from built-in simulated candles (or optional
> live Twelve Data candles for non-OTC assets) and you must confirm setups on your own chart.
> Check that this kind of trading is legal where you live (in India, RBI/SEBI rules restrict
> offshore Forex/binary-options trading). Never trade money you cannot afford to lose.

![Flow](https://img.shields.io/badge/flow-generate%20%E2%86%92%20Telegram%20%E2%86%92%20settle-blue)

## What it does

- **Signal engine** — EMA 9/21, RSI 14, MACD, Bollinger Bands, Stochastic and candle momentum
  vote with fixed weights. You see every vote and the reasoning — no black box.
- **NO-TRADE gate** — if confidence < your threshold (default 60%) or indicators agree < 60%,
  the signal is labelled `NO_TRADE` and is never auto-pushed.
- **Telegram delivery (the final step)** — one click (or fully automatic) pushes an
  HTML-formatted signal to your chat/channel: pair, direction, timeframe, expiry, entry,
  confidence, IST+UTC time, reasons, disclaimer. Retries, idempotency (no duplicate spam),
  full delivery log, and a safe **dry-run mode** until you configure your bot.
- **Auto mode** — watchlist scheduler generates signals on an interval, auto-pushes TRADE
  signals, settles expired ones and pushes the result back to Telegram.
- **Dashboard** — candlestick chart with EMAs, signal card with live countdown, history,
  win-rate stats (computed only from settled signals), Telegram & automation settings.
- **Assets** — EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, EUR/GBP, GBP/JPY,
  EUR/JPY, Gold, BTC, ETH + `(OTC)` variants. Timeframes 1m/5m/15m/1h, expiry 1–60 min.

## Quickstart

```bash
cp .env.example .env     # optional — defaults work out of the box
make install             # Python venv + npm packages
make backend             # terminal 1 → API on http://localhost:8000 (docs at /docs)
make frontend            # terminal 2 → dashboard on http://localhost:5173
make test                # 35 backend tests + frontend tests + typecheck
```

Open the dashboard, pick a pair, click **📊 Generate signal**.

## Telegram setup (2 minutes)

1. In Telegram, talk to **@BotFather** → `/newbot` → copy the **token**.
2. Open your new bot and send it any message (bots can't message you first).
3. Get your **chat id**: ask **@userinfobot**, or open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id`.
   (For a channel: add the bot as admin, post once, use `@channelname` or the `-100…` id.)
4. Dashboard → **✈️ Telegram delivery** → paste token + chat id → **Save** →
   **Send test message**. Or set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in `.env`.
5. Click **✈️ Generate & push to Telegram** — the signal lands in your chat like this:

```
📡 Pocket Option Signal
Pair: Gold (XAU/USD)
Direction: 🟢 CALL ▲ (UP)
Timeframe: 5m  •  Expiry: 5m
Entry price: 2390.34
Confidence: 70%
Time: 22:58:31 IST (17:28 UTC)
Why:
• ▲ EMA 9/21: EMA9 above EMA21 — short-term uptrend
• ▲ RSI 14: RSI 55.9 bullish momentum
…
```

Until Telegram is configured, pushes are recorded as **DRY_RUN** (with the exact message
preview) — the app never pretends a message was sent.

## Configuration (`.env`, all optional)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/signals.db` | SQLite (zero-config) or PostgreSQL |
| `API_KEY` | *(empty = open, local only)* | If set, generate/push/settings need `X-API-Key` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | *(empty)* | Telegram delivery; dashboard UI can override |
| `MIN_CONFIDENCE` | `60` | TRADE gate (also needs ≥60% vote agreement) |
| `WATCHLIST` | `EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD` | Auto-mode pairs |
| `AUTO_SIGNALS_ENABLED` / `AUTO_PUSH_TELEGRAM` | `false` | Boot defaults; dashboard toggles persist in DB |
| `AUTO_INTERVAL_SECONDS` | `60` | Auto cycle interval (30–3600) |
| `TWELVE_DATA_API_KEY` | *(empty)* | Optional live candles; falls back to simulator |
| `CORS_ORIGINS` | localhost:5173 | Allowed browser origins |

## How a signal is decided

Each indicator votes CALL/PUT with a weight (EMA trend 2.0, RSI ≤1.5, MACD ≤1.5,
Bollinger ≤1.25, Stochastic ≤1.25, momentum 0.5). Direction = heavier side.
Confidence = `0.65 × agreement + 0.35 × strength`, clamped to 50–97. A flat market scores 50
and becomes NO-TRADE. Full method + rules: `backend/app/services/signal_engine.py`,
requirements: [`docs/PRD.md`](docs/PRD.md).

## API (summary — full contract in [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md))

`GET /api/v1/health` · `GET /pairs` · `GET /candles` ·
`POST /signals/generate` · `GET /signals` · `POST /signals/{id}/push-telegram` ·
`POST /telegram/test` · `GET/PUT /settings` · `POST /auto/run-once` · `GET /stats`
Interactive OpenAPI at `http://localhost:8000/docs`.

## Project structure

```
backend/app/   FastAPI: api/routes → services (market_data, indicators, signal_engine,
               telegram, evaluator, scheduler, settings) → SQLAlchemy models
backend/tests/ pytest suites for indicators, engine, data determinism, Telegram, API
frontend/src/  React dashboard (chart, generator, history, Telegram/auto panels)
docs/          PRD · ARCHITECTURE · API_CONTRACTS · RUNBOOK · ADR/0001
```

## Docs

- 📄 [PRD (specialized from the project template)](docs/PRD.md)
- 🏗️ [Architecture](docs/ARCHITECTURE.md) · 📜 [API contracts](docs/API_CONTRACTS.md)
- 🔧 [Runbook — Telegram troubleshooting, ops, production checklist](docs/RUNBOOK.md)

## Responsible use

Signals are probabilistic indicator readings on demo/external data — Pocket Option
(especially OTC) quotes can differ at entry. Use small stakes, a demo account first, your own
chart confirmation and strict risk limits. Past win-rate in this dashboard reflects only this
bot's settled simulated-data signals and does **not** predict live trading results.
