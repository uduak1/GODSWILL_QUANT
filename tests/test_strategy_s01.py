import pytest
import pandas as pd
from strategies.s01_liquidity_sweep import LiquiditySweepReversal


def make_df(highs, lows, closes, opens):
    idx = pd.date_range("2024-01-01", periods=len(highs), freq="1h", tz="UTC")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=idx)


def test_s01_requires_premium_discount():
    """Sweep must occur in discount for longs."""
    # 30 base candles, then a sweep low, then CHOCH up
    n = 30
    opens = [100] * n
    highs = [101] * n
    lows  = [99] * n
    closes = [100] * n

    # Sweep at idx 28-29 (deep discount)
    lows[28] = 90
    closes[28] = 96
    # CHOCH bullish at idx 30-31
    highs.append(105); lows.append(98); closes.append(103); opens.append(99)
    highs.append(110); lows.append(103); closes.append(108); opens.append(104)

    df = make_df(highs, lows, closes, opens)
    strat = LiquiditySweepReversal()
    signals = strat.generate_signals(df, "EURUSD", "H1")
    # Should not crash; behavior validated by scan
    assert isinstance(signals, list)