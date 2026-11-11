import pytest
import pandas as pd
from core.types import Signal
from core.enums import SignalDirection, Timeframe
from strategies.base import BaseStrategy
from risk_management.engine import RiskManager
from configuration.settings import RiskSettings
from backtesting.engine import Backtester


class DummyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("DUMMY")
        self.has_signaled = False

    def generate_signals(self, df, symbol, timeframe):
        # Fire one signal at index 10 — the backtester starts its loop at i=10
        # so this signal will be found and entered at i+1.
        if not self.has_signaled and len(df) >= 12:
            self.has_signaled = True
            return [Signal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                timeframe=Timeframe.H1,
                direction=SignalDirection.LONG,
                entry_price=100.0,
                stop_loss=95.0,
                take_profit=110.0,
                created_at=df.index[10].to_pydatetime(),
            )]
        return []


def test_backtest_take_profit():
    idx = pd.date_range("2024-01-01", periods=15, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "open":  [100.0] * 15,
        "high":  [101.0] * 15,
        "low":   [99.0] * 15,
        "close": [100.0] * 15,
    }, index=idx)
    df.loc[df.index[11], "high"] = 112.0

    specs = {"tick_size": 0.01, "tick_value": 1.0, "contract_size": 100.0,
             "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01}

    backtester = Backtester(
        DummyStrategy(),
        RiskManager(RiskSettings(risk_per_trade_pct=1.0)),
        initial_balance=10000.0,
    )
    result = backtester.run(df, "EURUSD", specs)

    assert result.total_trades == 1
    assert result.winning_trades == 1
    assert result.trades[0].reason == "TAKE_PROFIT"
    assert result.final_balance > 10000.0


def test_backtest_stop_loss():
    idx = pd.date_range("2024-01-01", periods=15, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "open":  [100.0] * 15,
        "high":  [101.0] * 15,
        "low":   [99.0] * 15,
        "close": [100.0] * 15,
    }, index=idx)
    df.loc[df.index[11], "low"] = 90.0

    specs = {"tick_size": 0.01, "tick_value": 1.0, "contract_size": 100.0,
             "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01}

    backtester = Backtester(
        DummyStrategy(),
        RiskManager(RiskSettings(risk_per_trade_pct=1.0)),
        initial_balance=10000.0,
    )
    result = backtester.run(df, "EURUSD", specs)

    assert result.total_trades == 1
    assert result.losing_trades == 1
    assert result.trades[0].reason == "STOP_LOSS"
    assert result.final_balance < 10000.0