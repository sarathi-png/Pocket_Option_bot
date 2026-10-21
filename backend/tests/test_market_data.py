from app.services.market_data import PAIR_MAP, provider


def test_simulated_candles_are_deterministic_and_consistent():
    """Overlapping windows must agree, so entry/exit prices are consistent."""
    short = provider.simulated_candles("EURUSD", "1m", limit=30)
    long_ = provider.simulated_candles("EURUSD", "1m", limit=90)
    assert len(short) == 30 and len(long_) == 90
    # The last 30 candles of the long window are exactly the short window
    assert [c.to_dict() for c in long_[-30:]] == [c.to_dict() for c in short]


def test_candle_at_matches_series():
    series = provider.simulated_candles("GBPUSD", "5m", limit=20)
    target = series[10]
    fetched = provider.simulated_candle_at("GBPUSD", "5m", target.timestamp)
    assert fetched is not None
    assert fetched.to_dict() == target.to_dict()


def test_prices_stay_near_realistic_base():
    for symbol in ("EURUSD", "USDJPY", "XAUUSD", "BTCUSD"):
        info = PAIR_MAP[symbol]
        candles = provider.simulated_candles(symbol, "1m", limit=120)
        for c in candles:
            assert abs(c.close - info.base_price) / info.base_price < 0.15, (symbol, c.close)
            assert c.low <= min(c.open, c.close) <= max(c.open, c.close) <= c.high


def test_otc_variant_is_independent_series():
    real = provider.simulated_candles("EURUSD", "1m", limit=30)
    otc = provider.simulated_candles("EURUSD-OTC", "1m", limit=30)
    assert [c.close for c in real] != [c.close for c in otc]
