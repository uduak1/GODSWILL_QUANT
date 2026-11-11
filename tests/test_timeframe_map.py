import MetaTrader5 as mt5
import pytest
from core.enums import Timeframe
from market_data.timeframe_map import to_mt5, from_mt5, is_substituted


def test_all_timeframes_map():
    for tf in Timeframe:
        const = to_mt5(tf)
        assert isinstance(const, int)


def test_m12_substituted():
    assert is_substituted(Timeframe.M12)
    assert to_mt5(Timeframe.M12) == mt5.TIMEFRAME_M15


def test_roundtrip_m15():
    assert from_mt5(to_mt5(Timeframe.M15)) == Timeframe.M15


def test_unknown_constant_raises():
    with pytest.raises(Exception):
        from_mt5(999999)