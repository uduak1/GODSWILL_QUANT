import pytest
import pandas as pd
import numpy as np
from market_structure.swings import SwingDetector
from market_structure.fvg import FVGAnalyzer

def make_synthetic_df(highs, lows, closes):
    """Utility to quickly build a dataframe for testing."""
    idx = pd.date_range("2024-01-01", periods=len(highs), freq="1h", tz="UTC")
    return pd.DataFrame({"high": highs, "low": lows, "close": closes}, index=idx)

def test_swing_detection_look_ahead():
    # Create a massive spike at index 2. 
    # Candle 0,1,2 (Spike), 3, 4
    # It is a swing high, but we shouldn't know that until candle 4 closes.
    df = make_synthetic_df(
        highs=[10, 10, 50, 10, 10], 
        lows=[5, 5, 5, 5, 5], 
        closes=[7, 7, 7, 7, 7]
    )
    
    detector = SwingDetector(left_bars=2, right_bars=2)
    swings = detector.find_swings(df)
    
    assert len(swings) == 1
    swing = swings[0]
    
    # The high was at index 2, price 50
    assert swing.index == 2
    assert swing.price == 50
    assert swing.is_high is True
    
    # CRITICAL: We can ONLY know this on index 4 (2 + right_bars)
    assert swing.confirmed_at_index == 4

def test_swing_detection_ignores_incomplete():
    # A spike at the very end. We don't know if it's a swing high yet.
    df = make_synthetic_df(
        highs=[10, 10, 10, 50], 
        lows=[5, 5, 5, 5], 
        closes=[7, 7, 7, 7]
    )
    detector = SwingDetector(left_bars=2, right_bars=2)
    swings = detector.find_swings(df)
    
    # No swings found because the spike hasn't been confirmed yet
    assert len(swings) == 0

def test_bullish_fvg():
    # Candle 1 high is 12. Candle 3 low is 15.
    # Gap between 12 and 15.
    df = make_synthetic_df(
        highs=[12, 14, 16], 
        lows=[8, 10, 15], 
        closes=[10, 12, 15]
    )
    analyzer = FVGAnalyzer()
    fvgs = analyzer.find_fvgs(df)
    
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.is_bullish is True
    assert fvg.bottom == 12 # High of candle 1
    assert fvg.top == 15    # Low of candle 3