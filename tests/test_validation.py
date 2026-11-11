import pandas as pd
import pytest
from core.enums import Timeframe
from market_data.validation import validate_ohlcv, find_gaps

def _make_df(n=10, freq="15min"):
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "open": [1.0]*n, "high": [1.1]*n,
        "low": [0.9]*n, "close": [1.05]*n,
        "tick_volume": [100]*n,
    }, index=idx)

def test_clean_data_passes():
    report = validate_ohlcv(_make_df(), "EURUSD", Timeframe.M15)
    assert report.is_clean

def test_duplicate_detected():
    df = _make_df()
    df = pd.concat([df, df.iloc[[0]]])
    report = validate_ohlcv(df, "EURUSD", Timeframe.M15)
    assert report.duplicate_timestamps == 1
    assert not report.is_clean

def test_ohlc_violation_detected():
    df = _make_df()
    df.iloc[0, df.columns.get_loc("high")] = 0.5  # high < low
    report = validate_ohlcv(df, "EURUSD", Timeframe.M15)
    assert report.ohlc_violations >= 1

def test_non_positive_detected():
    df = _make_df()
    df.iloc[0, df.columns.get_loc("open")] = -1.0
    report = validate_ohlcv(df, "EURUSD", Timeframe.M15)
    assert report.non_positive_prices == 1

def test_gap_detection():
    df = _make_df(5, freq="15min")
    # Insert a 2-hour gap
    df2 = _make_df(5, freq="15min")
    df2.index = df2.index + pd.Timedelta(hours=3)
    combined = pd.concat([df, df2])
    gaps = find_gaps(combined, Timeframe.M15)
    assert len(gaps) == 1
    assert gaps[0][2] == 7  # Exactly 7 missing bars

def test_empty_df():
    report = validate_ohlcv(pd.DataFrame(), "EURUSD", Timeframe.M15)
    assert not report.is_clean
    assert "empty" in report.errors[0]