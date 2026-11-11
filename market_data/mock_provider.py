"""Deterministic mock provider for testing without a live MT5 terminal."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

import numpy as np
import pandas as pd

from core.enums import Timeframe
from core.interfaces import IMarketDataProvider


class MockMarketDataProvider(IMarketDataProvider):
    """Generates reproducible OHLCV data via a seeded RNG."""

    def __init__(self, seed: int = 42):
        self._rng = np.random.default_rng(seed)

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start=None,
        end=None,
        count: int | None = None,
    ) -> pd.DataFrame:
        n = count or 500
        start_dt = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
        freq = {
            Timeframe.M1: "1min", Timeframe.M5: "5min",
            Timeframe.M12: "12min", Timeframe.M15: "15min",
            Timeframe.M20: "20min", Timeframe.M30: "30min",
            Timeframe.H1: "1h", Timeframe.H4: "4h",
            Timeframe.D1: "1D", Timeframe.W1: "1W",
        }[timeframe]

        idx = pd.date_range(start=start_dt, periods=n, freq=freq, tz="UTC")
        base = 2000.0 if "XAU" in symbol.upper() else 1.1000
        closes = base + np.cumsum(self._rng.normal(0, base * 0.001, n))
        opens = np.roll(closes, 1)
        opens[0] = base
        highs = np.maximum(opens, closes) + self._rng.uniform(0, base * 0.0005, n)
        lows = np.minimum(opens, closes) - self._rng.uniform(0, base * 0.0005, n)

        return pd.DataFrame(
            {"open": opens, "high": highs, "low": lows,
             "close": closes, "tick_volume": self._rng.integers(100, 10000, n)},
            index=idx,
        )

    def get_symbol_specs(self, symbol: str) -> dict:
        return {
            "name": symbol, "point": 0.01, "digits": 2,
            "tick_size": 0.01, "tick_value": 1.0,
            "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
            "contract_size": 100.0, "stops_level": 0, "freeze_level": 0,
            "filling_mode": 1, "trade_mode": 4,
            "currency_profit": "USD", "currency_margin": "USD",
        }

    def list_available_symbols(self) -> list[str]:
        return ["EURUSD", "XAUUSD", "XAGUSD", "USOIL", "GBPUSD", "USDJPY"]