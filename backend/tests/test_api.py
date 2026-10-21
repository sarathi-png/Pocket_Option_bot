def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "telegram_configured" in body
    assert resp.headers.get("x-request-id")


def test_pairs_and_candles(client):
    pairs = client.get("/api/v1/pairs").json()
    symbols = {p["symbol"] for p in pairs}
    assert {"EURUSD", "GBPUSD", "XAUUSD", "EURUSD-OTC"} <= symbols

    resp = client.get("/api/v1/candles", params={"pair": "EURUSD", "timeframe": "1m", "limit": 60})
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_source"] == "simulated"
    assert len(body["candles"]) == 60
    assert len(body["ema9"]) == 60


def test_unknown_pair_error_shape(client):
    resp = client.post("/api/v1/signals/generate", json={"pair": "NOPEXX", "timeframe": "1m", "expiry_minutes": 2})
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "PAIR_NOT_FOUND"
    assert err["request_id"]


def test_validation_error_shape(client):
    resp = client.post("/api/v1/signals/generate", json={"pair": "EURUSD", "timeframe": "9x", "expiry_minutes": 2})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]


def test_generate_signal_persists_and_lists(client):
    resp = client.post("/api/v1/signals/generate", json={"pair": "EURUSD", "timeframe": "1m", "expiry_minutes": 2})
    assert resp.status_code == 201, resp.text
    signal = resp.json()
    assert signal["direction"] in ("CALL", "PUT")
    assert signal["decision"] in ("TRADE", "NO_TRADE")
    assert 50 <= signal["confidence"] <= 97
    assert signal["telegram_status"] == "NOT_SENT"
    assert signal["votes"]

    fetched = client.get(f"/api/v1/signals/{signal['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == signal["id"]

    listing = client.get("/api/v1/signals", params={"pair": "EURUSD"}).json()
    assert listing["total"] >= 1


def test_generate_and_push_dry_run_flow(client):
    """End-to-end: generate -> push to Telegram (dry-run until configured)."""
    created = client.post(
        "/api/v1/signals/generate",
        json={"pair": "GBPUSD", "timeframe": "5m", "expiry_minutes": 5},
    ).json()
    resp = client.post(f"/api/v1/signals/{created['id']}/push-telegram", json={})
    assert resp.status_code == 200, resp.text
    delivery = resp.json()["delivery"]
    assert delivery["status"] == "DRY_RUN"
    assert "not configured" in delivery["note"]
    assert "Pocket Option Signal" in delivery["message_preview"]


def test_telegram_test_and_settings_masking(client):
    resp = client.put(
        "/api/v1/telegram/settings",
        json={"bot_token": "111111:AAFakeTokenForTest1234", "chat_id": "555123456"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["bot_token_masked"].endswith("1234")
    assert "AAFakeTokenForTest" not in body["bot_token_masked"]

    status = client.get("/api/v1/telegram/status").json()
    assert status["configured"] is True

    cleared = client.put("/api/v1/telegram/settings", json={"clear": True}).json()
    assert cleared["configured"] is False


def test_settings_roundtrip_and_stats(client):
    resp = client.put("/api/v1/settings", json={"min_confidence": 70, "watchlist": ["EURUSD", "BTCUSD"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["min_confidence"] == 70
    assert body["watchlist"] == ["EURUSD", "BTCUSD"]

    bad = client.put("/api/v1/settings", json={"watchlist": ["WHATXX"]})
    assert bad.status_code == 422

    stats = client.get("/api/v1/stats").json()
    assert stats["total_signals"] >= 1
    assert "win_rate_pct" in stats

    auto = client.get("/api/v1/auto/status").json()
    assert "scheduler_running" in auto
