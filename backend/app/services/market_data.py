"""Market data provider.

Pocket Option has no official public API, so this bot NEVER pretends to read
Pocket Option's own feed. Two honest data sources are supported:

1. ``simulated`` (default, zero-config): a deterministic seeded random-walk
   generator per pair/timeframe. Same candle bucket => same candles, which
   makes signals reproducible and outcome evaluation well-defined.
2. ``twelvedata`` (optional): real Forex/crypto candles when
   TWELVE_DATA_API_KEY is configured. Any failure falls back to the
   simulator and the response marks ``data_source`` accordingly (fail safely,
   never silently fake "real" data — PRD R-05/R-11).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.core.logging_setup import get_logger

logger = get_logger("app.market_data")

TIMEFRAMES: dict[str, int] = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
# The simulator is a truncated AR(1) process around each pair's base price:
# deviation(n) = sum_{j=0}^{K-1} phi^j * shock(n-j), with a FIXED K. The price
# at any bucket is therefore an exact pure function of that bucket — every
# overlapping window agrees candle-for-candle, and the exit price used at
# settlement is exactly the close of the expiry candle in the entry series.
_SHOCK_WINDOW = 500  # K above; phi**500 ~= 5e-4, so truncation is negligible
_PHI_PER_MIN = 0.985


@dataclass(frozen=True)
class PairInfo:
    symbol: str
    display: str
    base_price: float
    decimals: int
    volatility: float  # fractional stdev per 1-minute candle
    category: str  # Forex | OTC | Crypto | Commodity
    twelve_symbol: str  # symbol used by Twelve Data ("" = unsupported there)


PAIRS: list[PairInfo] = [
    PairInfo("EURUSD", "EUR/USD", 1.0850, 5, 0.00035, "Forex", "EUR/USD"),
    PairInfo("GBPUSD", "GBP/USD", 1.2720, 5, 0.00040, "Forex", "GBP/USD"),
    PairInfo("USDJPY", "USD/JPY", 155.400, 3, 0.00035, "Forex", "USD/JPY"),
    PairInfo("AUDUSD", "AUD/USD", 0.6590, 5, 0.00040, "Forex", "AUD/USD"),
    PairInfo("USDCAD", "USD/CAD", 1.3680, 5, 0.00035, "Forex", "USD/CAD"),
    PairInfo("USDCHF", "USD/CHF", 0.8840, 5, 0.00035, "Forex", "USD/CHF"),
    PairInfo("EURGBP", "EUR/GBP", 0.8530, 5, 0.00030, "Forex", "EUR/GBP"),
    PairInfo("GBPJPY", "GBP/JPY", 197.600, 3, 0.00045, "Forex", "GBP/JPY"),
    PairInfo("EURJPY", "EUR/JPY", 168.700, 3, 0.00040, "Forex", "EUR/JPY"),
    PairInfo("XAUUSD", "Gold (XAU/USD)", 2385.00, 2, 0.00060, "Commodity", "XAU/USD"),
    PairInfo("BTCUSD", "Bitcoin (BTC/USD)", 97400.00, 2, 0.00120, "Crypto", "BTC/USD"),
    PairInfo("ETHUSD", "Ethereum (ETH/USD)", 3420.00, 2, 0.00150, "Crypto", "ETH/USD"),
    # Pocket Option trades "OTC" variants when real markets are closed. They are
    # broker-generated quotes, so simulated candles are the only honest source.
    PairInfo("EURUSD-OTC", "EUR/USD (OTC)", 1.0850, 5, 0.00045, "OTC", ""),
    PairInfo("GBPUSD-OTC", "GBP/USD (OTC)", 1.2720, 5, 0.00050, "OTC", ""),
    PairInfo("USDJPY-OTC", "USD/JPY (OTC)", 155.400, 3, 0.00045, "OTC", ""),
    PairInfo("AUDCAD-OTC", "AUD/CAD (OTC)", 0.9010, 5, 0.00045, "OTC", ""),
]

PAIR_MAP: dict[str, PairInfo] = {p.symbol: p for p in PAIRS}


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


def normalize_pair(pair: str) -> str:
    return pair.strip().upper().replace("/", "")


def get_pair(pair: str) -> PairInfo | None:
    return PAIR_MAP.get(normalize_pair(pair))


def format_price(pair: str, price: float) -> str:
    info = get_pair(pair)
    decimals = info.decimals if info else 5
    return f"{price:.{decimals}f}"


class MarketDataProvider:
    """Candle access with simulator + optional Twelve Data fallback chain."""

    # -- simulated -------------------------------------------------------
    def _simulate_upto(self, info: PairInfo, timeframe: str, end_index: int, start_index: int) -> list[Candle]:
        tf_seconds = TIMEFRAMES[timeframe]
        tf_minutes = tf_seconds / 60
        vol = info.volatility * math.sqrt(tf_minutes)
        phi = _PHI_PER_MIN**tf_minutes
        k = _SHOCK_WINDOW
        first = start_index - k  # oldest shock that can influence this window

        # Per-bucket seeded draws: (shock, high wiggle, low wiggle, volume).
        # Slow cyclical drift inside the shock creates trends/reversals so
        # indicators can genuinely agree or disagree (not pure coin flips).
        shocks: list[float] = []
        draws: list[tuple[float, float, float]] = []
        for index in range(first, end_index + 1):
            rng = random.Random(f"{info.symbol}|{timeframe}|{index}")
            drift = (math.sin(index / 37.0) * 0.35 + math.sin(index / 113.0) * 0.25) * vol
            shocks.append(rng.gauss(0.0, 1.0) * vol + drift)
            draws.append((abs(rng.gauss(0.0, 1.0)), abs(rng.gauss(0.0, 1.0)), round(rng.uniform(80, 1200), 2)))

        def shock_at(index: int) -> float:
            return shocks[index - first]

        # deviation(start_index - 1) by direct truncated sum, then the exact
        # recurrence D(n) = s(n) + phi * (D(n-1) - phi^(K-1) * s(n-K)).
        deviation = sum((phi**j) * shock_at(start_index - 1 - j) for j in range(k))
        phi_k1 = phi ** (k - 1)
        candles: list[Candle] = []
        for index in range(start_index, end_index + 1):
            open_ = info.base_price * (1 + deviation)
            deviation = shock_at(index) + phi * (deviation - phi_k1 * shock_at(index - k))
            close = info.base_price * (1 + deviation)
            hi_wiggle, lo_wiggle, volume = draws[index - first]
            high = max(open_, close) * (1 + hi_wiggle * vol * 0.4)
            low = min(open_, close) * (1 - lo_wiggle * vol * 0.4)
            r = lambda v: round(v, info.decimals)  # noqa: E731
            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(index * tf_seconds, tz=timezone.utc),
                    open=r(open_),
                    high=r(high),
                    low=r(low),
                    close=r(close),
                    volume=volume,
                )
            )
        return candles

    def simulated_candles(self, pair: str, timeframe: str, limit: int = 120) -> list[Candle]:
        info = get_pair(pair)
        assert info is not None
        tf_seconds = TIMEFRAMES[timeframe]
        now_index = int(datetime.now(timezone.utc).timestamp()) // tf_seconds
        return self._simulate_upto(info, timeframe, now_index, now_index - limit + 1)

    def simulated_candle_at(self, pair: str, timeframe: str, when: datetime) -> Candle | None:
        info = get_pair(pair)
        if info is None:
            return None
        tf_seconds = TIMEFRAMES[timeframe]
        index = int(when.timestamp()) // tf_seconds
        candles = self._simulate_upto(info, timeframe, index, index)
        return candles[0] if candles else None

    # -- Twelve Data (optional real data) --------------------------------
    async def _twelve_candles(self, info: PairInfo, timeframe: str, limit: int) -> list[Candle] | None:
        api_key = get_settings().twelve_data_api_key
        if not api_key or not info.twelve_symbol:
            return None
        interval = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h"}[timeframe]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.twelvedata.com/time_series",
                    params={
                        "symbol": info.twelve_symbol,
                        "interval": interval,
                        "outputsize": limit,
                        "apikey": api_key,
                        "format": "JSON",
                    },
                )
            if resp.status_code != 200:
                logger.warning("Twelve Data HTTP %s for %s; falling back to simulator", resp.status_code, info.symbol)
                return None
            payload = resp.json()
            values = payload.get("values")
            if not values:
                logger.warning("Twelve Data returned no values for %s; falling back to simulator", info.symbol)
                return None
            candles: list[Candle] = []
            for v in reversed(values):  # API returns newest first
                ts = datetime.fromisoformat(v["datetime"]).replace(tzinfo=timezone.utc)
                candles.append(
                    Candle(ts, float(v["open"]), float(v["high"]), float(v["low"]), float(v["close"]),
                           float(v.get("volume") or 0))
                )
            return candles
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("Twelve Data fetch failed for %s (%s); falling back to simulator", info.symbol, type(exc).__name__)
            return None

    # -- public API --------------------------------------------------------
    async def get_candles(self, pair: str, timeframe: str, limit: int = 120) -> tuple[list[Candle], str]:
        """Returns (candles, data_source). data_source is 'twelvedata' or 'simulated'."""
        info = get_pair(pair)
        assert info is not None
        real = await self._twelve_candles(info, timeframe, limit)
        if real:
            return real, "twelvedata"
        return self.simulated_candles(pair, timeframe, limit), "simulated"

    def exit_price(self, pair: str, timeframe: str, when: datetime, fallback_candles: list[Candle] | None = None) -> float | None:
        """Price used to settle a signal at expiry (deterministic in simulated mode)."""
        candle = self.simulated_candle_at(pair, timeframe, when)
        if candle:
            return candle.close
        if fallback_candles:
            return fallback_candles[-1].close
        return None


provider = MarketDataProvider()
