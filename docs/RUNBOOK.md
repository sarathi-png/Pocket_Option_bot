# Runbook — Pocket Option Signal Bot

## Run locally (development)

```bash
cp .env.example .env            # optional; defaults work
make install                    # python venv + npm install
make backend                    # terminal 1 → http://localhost:8000  (docs: /docs)
make frontend                   # terminal 2 → http://localhost:5173
make test                       # backend pytest + frontend vitest
```

Manual equivalent:

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cd backend && ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
npm --prefix frontend install && npm --prefix frontend run dev
```

## Configure Telegram (the final delivery step)

1. Telegram → **@BotFather** → `/newbot` → copy the **token**.
2. Open your bot, send it any message first (bots cannot initiate).
3. Get your **chat id**: @userinfobot, or `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id`.
4. Dashboard → *Telegram delivery* → paste token + chat id → **Save** → **Send test message**.
   (Or set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in `.env` before starting the backend.)
5. Generate a signal → **Generate & push to Telegram**. Confirm `SENT` in history.

Until step 4 completes, every push is a recorded **dry-run** (message preview visible via
`GET /api/v1/telegram/deliveries`) — by design, so nothing pretends to be sent.

## Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| Delivery `TELEGRAM_HTTP_400` "chat not found" | Wrong chat id, or user never messaged the bot | Re-check id via getUpdates; message the bot first |
| Delivery `TELEGRAM_HTTP_401/404` | Wrong/revoked bot token | Re-copy from @BotFather (`/mybots` → API Token) |
| Delivery `TELEGRAM_HTTP_403` | Bot blocked/removed, or not admin in channel | Unblock bot / re-add as channel admin |
| `DRY_RUN` forever | Token or chat id missing on the server | Save both in dashboard or env; check `GET /telegram/status` |
| Dashboard "API offline" | Backend down or wrong port | Start backend; frontend proxies `/api` → `localhost:8000` |
| `401 UNAUTHORIZED` | Server has `API_KEY` set | Enter the same key in dashboard → Telegram panel → API key |
| Signals all `NO_TRADE` | Threshold too strict for current market | Lower *Minimum confidence* (default 60) in Auto panel — understand this trades more, weaker setups |
| Prices differ from Pocket Option | Expected: no official PO feed; OTC is broker-generated | Use signals as confirmation with your PO chart; optionally set `TWELVE_DATA_API_KEY` for live non-OTC candles |
| Outcomes stuck `PENDING` | Not yet expired, or backend was down at expiry | They settle on next list/stats/scheduler cycle automatically |

## Operations

- **Health:** `GET /api/v1/health` (status, telegram configured?, scheduler running?).
- **Logs:** structured lines `… [req=<id>] …`; correlate with `X-Request-ID` response header
  and `error.request_id` body field. Tokens/API keys are never logged.
- **Data:** SQLite file `backend/data/signals.db` by default. Back up by copying the file
  while the backend is stopped (or use managed PostgreSQL via `DATABASE_URL` in production).
- **Reset demo data:** stop backend, delete `backend/data/`, restart (tables auto-create).
- **Scheduler:** in-process; enabling *Auto signals* persists in DB and survives restarts.
  Watch `GET /api/v1/auto/status` (`last_run: generated=… pushed=… settled=…`).

## Production checklist (before exposing publicly)

- [ ] Set a strong `API_KEY` (and ideally put real user auth/reverse-proxy auth in front).
- [ ] Serve over HTTPS; restrict `CORS_ORIGINS` to your domain.
- [ ] Use PostgreSQL (`DATABASE_URL=postgresql+psycopg://…`, add `psycopg[binary]`) + backups;
      introduce Alembic migrations before schema changes (MVP uses `create_all`).
- [ ] Build frontend (`npm --prefix frontend run build`) — FastAPI then serves it at `/app`,
      or host `frontend/dist` on any static host with `/api` proxied to the backend.
- [ ] Keep Telegram token in env/secret manager; rotate via @BotFather if leaked.
- [ ] Monitor `/health`, delivery `FAILED` counts (`/stats`), and host CPU/RAM.
- [ ] **Rollback:** redeploy previous git commit; DB schema is additive in MVP. Telegram
      messages already sent cannot be unsent — disable auto-push first in an incident.

`docker-compose.yml` provides backend + frontend(+ optional Postgres profile) for a
single-host deployment.
