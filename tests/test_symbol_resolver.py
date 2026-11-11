from unittest.mock import patch, MagicMock
from market_data.symbol_resolver import SymbolResolver


def _mock_symbol_info(name):
    def fake(symbol):
        if symbol == name:
            info = MagicMock()
            info.visible = True
            return info
        return None
    return fake


@patch("MetaTrader5.symbol_select")
@patch("MetaTrader5.symbol_info")
def test_exact_match(mock_info, mock_select):
    mock_info.side_effect = _mock_symbol_info("XAUUSD")
    r = SymbolResolver()
    assert r.resolve("XAUUSD") == "XAUUSD"


@patch("MetaTrader5.symbol_select")
@patch("MetaTrader5.symbol_info")
def test_configured_suffix(mock_info, mock_select):
    mock_info.side_effect = _mock_symbol_info("XAUUSD.a")
    r = SymbolResolver(configured_suffix=".a")
    assert r.resolve("XAUUSD") == "XAUUSD.a"


@patch("MetaTrader5.symbol_select")
@patch("MetaTrader5.symbol_info")
def test_pattern_fallback(mock_info, mock_select):
    mock_info.side_effect = _mock_symbol_info("XAUUSD.pro")
    r = SymbolResolver()
    assert r.resolve("XAUUSD") == "XAUUSD.pro"


@patch("MetaTrader5.symbols_get")
@patch("MetaTrader5.symbol_select")
@patch("MetaTrader5.symbol_info")
def test_scan_fallback(mock_info, mock_select, mock_symbols):
    mock_info.side_effect = _mock_symbol_info("GOLD")
    sym = MagicMock()
    sym.name = "GOLD"
    mock_symbols.return_value = [sym]
    r = SymbolResolver()
    # Case-insensitive scan finds GOLD for "gold" base? No — GOLD != XAUUSD.
    # Test with a symbol whose name matches case-insensitively
    assert r.resolve("gold") == "GOLD"


@patch("MetaTrader5.symbols_get")
@patch("MetaTrader5.symbol_info")
def test_not_found(mock_info, mock_symbols):
    mock_info.return_value = None
    mock_symbols.return_value = []
    r = SymbolResolver()
    assert r.resolve("NOTREAL") is None