import pytest

MetaTrader5 = pytest.importorskip("MetaTrader5")

from market_data.mt5_gateway import MT5Gateway
from configuration.settings import MT5Settings


@pytest.mark.mt5
def test_connect_shutdown():
    gw = MT5Gateway(MT5Settings())
    try:
        gw.connect()
        info = gw.account_info()
        assert "login" in info
    finally:
        gw.shutdown()


@pytest.mark.mt5
def test_get_rates():
    gw = MT5Gateway(MT5Settings())
    with gw.connection():
        df = gw.get_rates("EURUSD", "H1", count=50)
    assert len(df) == 50
    assert list(df.columns) == ["open", "high", "low", "close", "tick_volume"]