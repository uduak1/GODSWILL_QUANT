import pytest
import pandas as pd
from strategies.s02_bos_fvg import BOSFVGStrategy
from strategies.s03_choch_reversal import CHOCHReversal
from strategies.s04_order_block import OrderBlockRetest

def make_synthetic_df(highs, lows, closes, opens):
    idx = pd.date_range("2024-01-01", periods=len(highs), freq="1h", tz="UTC")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=idx)

def test_s02_bos_fvg():
    # Setup: Uptrend, swing high at i=2 (15).
    # i=5: Massive bullish displacement breaking the high (close 16), leaving an FVG.
    opens = [ 8, 10, 13, 14, 12, 13, 16, 20]
    highs = [10, 12, 15, 14, 13, 16, 20, 22]
    lows  = [ 8, 10, 12, 11, 10, 15, 17, 19]
    closes= [ 9, 11, 14, 13, 12, 16, 19, 21]
    
    df = make_synthetic_df(highs, lows, closes, opens)
    strat = BOSFVGStrategy()
    signals = strat.generate_signals(df, "EURUSD", "H1")
    
    assert len(signals) >= 1
    assert signals[0].direction == "LONG"

def test_s03_choch():
    # Setup: 
    # i=2: Swing High at 18.
    # i=5: Swing Low at 8.
    # i=9: BOS Bearish (close 6).
    # i=13: Swing High at 20.
    # i=17: CHOCH Bullish (close 21), leaving an FVG.
    opens = [11, 14, 16, 13, 11,  9,  9, 11, 11,  8,  8, 13, 16, 18, 15, 14, 17, 21, 24, 25]
    highs = [12, 15, 18, 16, 14, 12, 10, 12, 14, 15, 12, 14, 18, 20, 19, 17, 18, 22, 25, 26]
    lows  = [10, 11, 14, 12, 10,  8,  9, 10, 11,  5,  6,  9, 12, 15, 14, 13, 14, 19, 21, 22]
    closes= [11, 14, 16, 13, 11,  9,  9, 11, 13,  6,  8, 13, 16, 18, 15, 14, 17, 21, 24, 25]
    
    df = make_synthetic_df(highs, lows, closes, opens)
    strat = CHOCHReversal()
    signals = strat.generate_signals(df, "EURUSD", "H1")
    
    assert len(signals) >= 1
    assert signals[0].direction == "LONG"
    assert "CHOCH" in signals[0].reasons

def test_s04_order_block():
    # Setup: Same as S03. BOS Bearish at i=9. Candle before it is i=8 (green).
    opens = [11, 14, 16, 13, 11,  9,  9, 11, 11,  8,  8, 13, 16, 18, 15, 14, 17, 21, 24, 25]
    highs = [12, 15, 18, 16, 14, 12, 10, 12, 14, 15, 12, 14, 18, 20, 19, 17, 18, 22, 25, 26]
    lows  = [10, 11, 14, 12, 10,  8,  9, 10, 11,  5,  6,  9, 12, 15, 14, 13, 14, 19, 21, 22]
    closes= [11, 14, 16, 13, 11,  9,  9, 11, 13,  6,  8, 13, 16, 18, 15, 14, 17, 21, 24, 25]
    
    df = make_synthetic_df(highs, lows, closes, opens)
    strat = OrderBlockRetest()
    signals = strat.generate_signals(df, "EURUSD", "H1")
    
    assert len(signals) >= 1
    assert signals[0].direction == "SHORT"