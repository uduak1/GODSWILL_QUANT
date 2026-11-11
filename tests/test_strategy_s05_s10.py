import pytest
import pandas as pd
from unittest.mock import patch
from core.types import SwingPoint, MarketStructureEvent, FairValueGap, OrderBlock, LiquiditySweep
from strategies.s05_supply_demand import SupplyDemand
from strategies.s06_breakout_retest import BreakoutRetest
from strategies.s07_trend_continuation import TrendContinuation
from strategies.s08_classical_patterns import DoubleTopBottom
from strategies.s09_range_reversal import RangeReversal
from strategies.s10_multi_structure import MultiStructureConfluence


def make_synthetic_df(n=20, base=10):
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    # Float columns so tests can write fractional prices (e.g. 15.5)
    closes = [float(base)] * n
    opens = [float(base)] * n
    highs = [float(base + 1)] * n
    lows = [float(base - 1)] * n
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes},
        index=idx,
    )


@patch("strategies.s05_supply_demand.SwingDetector.find_swings")
def test_s05_supply_demand(mock_swings):
    mock_swings.return_value = [SwingPoint(index=3, price=15, is_high=True, confirmed_at_index=5)]
    df = make_synthetic_df(10)
    df.loc[df.index[4], "close"] = 5.0
    signals = SupplyDemand().generate_signals(df, "EURUSD", "H1")
    assert len(signals) >= 1
    assert signals[0].direction == "SHORT"


@patch("strategies.s06_breakout_retest.SwingDetector.find_swings")
def test_s06_breakout_retest(mock_swings):
    mock_swings.return_value = [SwingPoint(index=2, price=15, is_high=True, confirmed_at_index=4)]
    df = make_synthetic_df(10)
    df.loc[df.index[5], "close"] = 16.0
    signals = BreakoutRetest().generate_signals(df, "EURUSD", "H1")
    assert len(signals) >= 1
    assert signals[0].direction == "LONG"


@patch("strategies.s07_trend_continuation.SwingDetector.find_swings")
@patch("strategies.s07_trend_continuation.StructureAnalyzer.find_events")
@patch("strategies.s07_trend_continuation.FVGAnalyzer.find_fvgs")
def test_s07_trend_continuation(mock_fvgs, mock_structs, mock_swings):
    mock_structs.return_value = [MarketStructureEvent("BOS_BULLISH", index=5, price=15, origin_swing_index=2)]
    mock_fvgs.return_value = [FairValueGap(index=6, top=18, bottom=16, is_bullish=True)]
    df = make_synthetic_df(10)
    signals = TrendContinuation().generate_signals(df, "EURUSD", "H1")
    assert len(signals) >= 1
    assert signals[0].direction == "LONG"


@patch("strategies.s08_classical_patterns.SwingDetector.find_swings")
def test_s08_double_top(mock_swings):
    # NEW tuned S08 requires:
    #   - 3 swing highs (prior trend filter: h_prev < h1)
    #   - Pullback low between h1 and h2
    #   - Pattern height >= 1%
    #   - Displaced break below neckline
    mock_swings.return_value = [
        SwingPoint(index=2,  price=12, is_high=True,  confirmed_at_index=4),
        SwingPoint(index=5,  price=20, is_high=True,  confirmed_at_index=7),
        SwingPoint(index=8,  price=15, is_high=False, confirmed_at_index=10),
        SwingPoint(index=12, price=20, is_high=True,  confirmed_at_index=14),
    ]

    df = make_synthetic_df(25)
    # Displaced bearish close below neckline (15) at index 16
    df.loc[df.index[16], "open"]  = 15.5
    df.loc[df.index[16], "close"] = 13.0
    df.loc[df.index[16], "high"]  = 15.6
    df.loc[df.index[16], "low"]   = 12.8

    signals = DoubleTopBottom().generate_signals(df, "EURUSD", "H1")
    assert len(signals) >= 1
    assert signals[0].direction == "SHORT"
    assert "Double Top" in signals[0].reasons


@patch("strategies.s09_range_reversal.SwingDetector.find_swings")
def test_s09_range_reversal(mock_swings):
    mock_swings.return_value = [
        SwingPoint(index=1, price=15, is_high=True, confirmed_at_index=3),
        SwingPoint(index=3, price=15, is_high=True, confirmed_at_index=5),
    ]
    df = make_synthetic_df(10)
    signals = RangeReversal().generate_signals(df, "EURUSD", "H1")
    assert len(signals) >= 1
    assert signals[0].direction == "SHORT"


@patch("strategies.s10_multi_structure.SwingDetector.find_swings")
@patch("strategies.s10_multi_structure.StructureAnalyzer.find_events")
@patch("strategies.s10_multi_structure.LiquidityAnalyzer.find_sweeps")
@patch("strategies.s10_multi_structure.OrderBlockAnalyzer.find_order_blocks")
@patch("strategies.s10_multi_structure.FVGAnalyzer.find_fvgs")
def test_s10_multi_structure(mock_fvgs, mock_obs, mock_sweeps, mock_structs, mock_swings):
    mock_sweeps.return_value = [LiquiditySweep(index=4, swept_level=10, is_buy_side=False)]
    mock_structs.return_value = [MarketStructureEvent("CHOCH_BULLISH", index=5, price=15, origin_swing_index=2)]
    mock_obs.return_value = [OrderBlock(index=5, top=16, bottom=14, is_bullish=True)]
    mock_fvgs.return_value = [FairValueGap(index=6, top=18, bottom=16, is_bullish=True)]
    df = make_synthetic_df(10)
    signals = MultiStructureConfluence().generate_signals(df, "EURUSD", "H1")
    assert len(signals) >= 1
    assert signals[0].direction == "LONG"