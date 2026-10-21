from app.services import indicators as ind


def test_ema_constant_series():
    assert ind.ema([10.0] * 30, 9) == 10.0


def test_ema_insufficient_data():
    assert ind.ema([1.0, 2.0], 9) is None


def test_ema_tracks_uptrend_below_price():
    closes = [float(i) for i in range(1, 51)]
    value = ind.ema(closes, 9)
    assert value is not None and closes[-1] > value > closes[0]


def test_rsi_all_gains_is_100():
    closes = [float(i) for i in range(1, 40)]
    assert ind.rsi(closes) == 100.0


def test_rsi_all_losses_is_0():
    closes = [float(100 - i) for i in range(40)]
    assert ind.rsi(closes) == 0.0


def test_rsi_flat_series_no_crash():
    value = ind.rsi([5.0] * 40)
    assert value is not None and 0 <= value <= 100


def test_rsi_insufficient_data():
    assert ind.rsi([1.0] * 5) is None


def test_macd_uptrend_histogram_positive():
    closes = [100 + i * 0.5 for i in range(60)]
    result = ind.macd(closes)
    assert result is not None and result["macd"] > 0


def test_bollinger_pct_b_bounds():
    closes = [100 + ((i % 5) - 2) for i in range(50)]
    result = ind.bollinger(closes)
    assert result is not None
    assert result["lower"] < result["middle"] < result["upper"]
    assert -0.5 < result["pct_b"] < 1.5


def test_stochastic_at_highs_near_100():
    closes = [float(i) for i in range(1, 40)]
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]
    result = ind.stochastic(highs, lows, closes)
    assert result is not None and result["k"] > 90


def test_momentum_sign():
    assert ind.candle_momentum([1.0, 2.0, 3.0, 4.0], 3) > 0
    assert ind.candle_momentum([4.0, 3.0, 2.0, 1.0], 3) < 0
