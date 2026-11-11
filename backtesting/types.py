from dataclasses import dataclass
from datetime import datetime
from core.enums import SignalDirection
from core.types import Signal

@dataclass
class ActiveTrade:
    signal: Signal
    volume: float
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    direction: SignalDirection

@dataclass
class CompletedTrade:
    symbol: str
    direction: SignalDirection
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    volume: float
    pnl: float
    reason: str  # "TAKE_PROFIT", "STOP_LOSS", "END_OF_DATA"

@dataclass
class BacktestResult:
    strategy_id: str
    initial_balance: float
    final_balance: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    profit_factor: float
    max_drawdown_pct: float
    equity_curve: list[float]  # <--- ADDED THIS LINE
    trades: list[CompletedTrade]