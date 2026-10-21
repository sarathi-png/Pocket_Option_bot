# API Contracts — `/api/v1`

Interactive docs: ` /docs` (OpenAPI) when the backend runs. All errors use:

```json
{ "error": { "code": "PAIR_NOT_FOUND", "message": "…", "request_id": "…", "details": [] } }
```

Mutating endpoints (`POST`/`PUT`) require header `X-API-Key` **iff** the server sets `API_KEY`.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service status, telegram/auto flags, market-data mode |
| GET | `/pairs` | 16 assets (Forex/Crypto/Commodity/OTC) with display names + decimals |
| GET | `/candles?pair=&timeframe=&limit=` | OHLC + EMA9/EMA21 series + `data_source` |
| POST | `/signals/generate` | Generate signal. Body: `{pair,timeframe,expiry_minutes,push_telegram}` → 201 `Signal` |
| GET | `/signals?page=&page_size=&pair=&outcome=&decision=` | Paginated history (auto-settles due signals first) |
| GET | `/signals/{id}` | One signal (auto-settles if due) |
| POST | `/signals/{id}/push-telegram` | **Push signal to Telegram.** Body `{force?:bool}` → `{delivery, signal}`. Idempotent unless forced |
| POST | `/signals/{id}/evaluate` | Settle now if expired (else stays PENDING) |
| GET | `/telegram/status` | `{configured, bot_token_masked, chat_id_masked, deliveries_sent}` |
| PUT | `/telegram/settings` | `{bot_token?, chat_id?, clear?}` — blank field = keep current |
| POST | `/telegram/test` | Send connectivity test message → `{delivery}` |
| GET | `/telegram/deliveries?limit=` | Recent deliveries (signal/test/result, SENT/FAILED/DRY_RUN) |
| GET | `/settings` | Automation settings + telegram status |
| PUT | `/settings` | Update `auto_enabled, auto_push_telegram, min_confidence (50–95), watchlist, auto_interval_seconds (30–3600), default_timeframe, default_expiry_minutes` |
| POST | `/auto/run-once` | Run one scheduler cycle now → `{summary, cycles}` |
| GET | `/auto/status` | Scheduler running? cycles, last summary |
| GET | `/stats` | Totals, wins/losses/draws/pending, `win_rate_pct` (null until settled), avg confidence, delivery counts, by-pair |

## Signal object (abridged)

```json
{
  "id": "…", "pair": "EURUSD", "display_pair": "EUR/USD",
  "direction": "CALL", "decision": "TRADE",
  "timeframe": "1m", "expiry_minutes": 2, "confidence": 75,
  "entry_price": 1.08445, "exit_price": null, "outcome": "PENDING",
  "data_source": "simulated",
  "indicators": { "ema9": …, "rsi14": …, "macd": {…}, "bollinger": {…},
                  "call_score": …, "put_score": …, "agreement": … },
  "votes": [ { "indicator": "EMA 9/21", "direction": "CALL", "weight": 2.0, "detail": "…" } ],
  "reasoning": ["▲ EMA 9/21: …"],
  "telegram_status": "NOT_SENT | SENT | FAILED | DRY_RUN",
  "created_at": "…", "expires_at": "…", "evaluated_at": null
}
```

## Delivery object

```json
{ "id": "…", "signal_id": "…|null", "kind": "signal|test|result",
  "status": "SENT|FAILED|DRY_RUN", "provider_message_id": "123|null",
  "error_code": "TELEGRAM_HTTP_400|NETWORK_…|TELEGRAM_NOT_CONFIGURED|null",
  "attempt_count": 1, "message_preview": "…", "note": "…(dry-run only)" }
```

## Error codes

`VALIDATION_ERROR` (422, with field details) · `PAIR_NOT_FOUND` (404) · `SIGNAL_NOT_FOUND` (404) ·
`INSUFFICIENT_DATA` (422) · `UNAUTHORIZED` (401) · `INTERNAL_ERROR` (500, details withheld).
