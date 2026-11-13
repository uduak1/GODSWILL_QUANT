import pandas as pd
import logging
from core.enums import SignalDirection
from strategies.base import BaseStrategy
from risk_management.engine import RiskManager
from backtesting.types import CompletedTrade, BacktestResult, ActiveTrade

logger = logging.getLogger("godswill.backtesting")


class Backtester:
    def __init__(
        self,
        strategy: BaseStrategy,
        risk_manager: RiskManager,
        initial_balance: float = 10000.0,
        spread_pips: float = 0.0,
        commission_per_lot_roundtrip: float = 2.0,
        slippage_ticks: float = 0.5,
        max_gap_pct: float = 0.005,
        tier_multiplier: float = 1.0,   # <--- MUST BE HERE
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.initial_balance = initial_balance
        self.spread = spread_pips
        self.commission = commission_per_lot_roundtrip
        self.slippage_ticks = slippage_ticks
        self.max_gap_pct = max_gap_pct
        self.tier_multiplier = tier_multiplier  # <--- STORED

    def run(self, df, symbol, symbol_specs, timeframe="H1"):
        all_signals = self.strategy.generate_signals(df, symbol, timeframe)
        signal_map = {sig.created_at: sig for sig in all_signals}

        balance = self.initial_balance
        equity_curve = [balance]
        completed_trades = []
        active_trade = None
        pending_order = None

        tick_size = symbol_specs.get("tick_size", 0.01)
        tick_value = symbol_specs.get("tick_value", 1.0)

        for i in range(10, len(df)):
            current_candle = df.iloc[i]
            current_time = df.index[i].to_pydatetime()

            if pending_order is not None and active_trade is None:
                sig, placed_at = pending_order
                filled, fill_price = self._try_limit_fill(sig, current_candle)

                if filled:
                    volume = self.risk_manager.calculate_volume(
                        balance, sig, symbol_specs,
                        tier_multiplier=self.tier_multiplier  # <--- PASSED
                    )
                    if volume > 0:
                        shift = fill_price - sig.entry_price
                        active_trade = ActiveTrade(
                            signal=sig, volume=volume, entry_time=current_time,
                            entry_price=fill_price, stop_loss=sig.stop_loss + shift,
                            take_profit=sig.take_profit + shift, direction=sig.direction,
                        )
                    pending_order = None
                elif i - placed_at > self._bars_for_24h(timeframe):
                    pending_order = None

            if active_trade is not None:
                hit_sl, hit_tp = self._check_sl_tp_hit(active_trade, current_candle)
                if hit_sl or hit_tp:
                    exit_price = (active_trade.stop_loss if hit_sl else active_trade.take_profit)
                    reason = "STOP_LOSS" if hit_sl else "TAKE_PROFIT"
                    price_diff = abs(exit_price - active_trade.entry_price)
                    money_pnl = (price_diff / tick_size) * tick_value * active_trade.volume
                    if reason == "STOP_LOSS":
                        money_pnl = -money_pnl
                    
                    spread_cost = (self.spread / tick_size) * tick_value * active_trade.volume
                    commission_cost = self.commission * active_trade.volume
                    slippage_cost = (2 * self.slippage_ticks * tick_value * active_trade.volume)
                    money_pnl -= (spread_cost + commission_cost + slippage_cost)
                    balance += money_pnl

                    completed_trades.append(CompletedTrade(
                        symbol=symbol, direction=active_trade.direction,
                        entry_time=active_trade.entry_time, exit_time=current_time,
                        entry_price=active_trade.entry_price, exit_price=exit_price,
                        volume=active_trade.volume, pnl=money_pnl, reason=reason,
                    ))
                    active_trade = None
                    equity_curve.append(balance)

            if active_trade is None and pending_order is None and current_time in signal_map:
                latest_signal = signal_map[current_time]
                approved, _reason = self.risk_manager.approve_trade(latest_signal, current_open_positions=0, daily_pnl_pct=0.0)
                if approved:
                    pending_order = (latest_signal, i)

        winning = [t for t in completed_trades if t.pnl > 0]
        losing = [t for t in completed_trades if t.pnl <= 0]
        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = (gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0)

        peak = equity_curve[0]
        max_dd = 0.0
        for value in equity_curve:
            if value > peak: peak = value
            dd = (peak - value) / peak * 100
            if dd > max_dd: max_dd = dd

        return BacktestResult(
            strategy_id=self.strategy.strategy_id, initial_balance=self.initial_balance,
            final_balance=balance, total_trades=len(completed_trades),
            winning_trades=len(winning), losing_trades=len(losing),
            profit_factor=profit_factor, max_drawdown_pct=max_dd,
            equity_curve=equity_curve, trades=completed_trades,
        )

    def _try_limit_fill(self, signal, candle):
        L = signal.entry_price
        if signal.direction == SignalDirection.SHORT:
            if candle["high"] >= L:
                fill = max(L, candle["open"])
                if abs(fill - L) / L > self.max_gap_pct: return False, 0.0
                if signal.stop_loss <= fill: return False, 0.0
                return True, fill
        else:
            if candle["low"] <= L:
                fill = min(L, candle["open"])
                if abs(fill - L) / L > self.max_gap_pct: return False, 0.0
                if signal.stop_loss >= fill: return False, 0.0
                return True, fill
        return False, 0.0

    @staticmethod
    def _check_sl_tp_hit(active_trade, candle):
        if active_trade.direction == SignalDirection.LONG:
            sl_hit = candle["low"] <= active_trade.stop_loss
            tp_hit = candle["high"] >= active_trade.take_profit
        else:
            sl_hit = candle["high"] >= active_trade.stop_loss
            tp_hit = candle["low"] <= active_trade.take_profit
        if sl_hit: return True, False
        return False, tp_hit

    @staticmethod
    def _bars_for_24h(timeframe):
        bars_per_day = {"M1": 1440, "M5": 288, "M15": 96, "M30": 48, "H1": 24, "H4": 6, "D1": 1, "W1": 1}
        return bars_per_day.get(timeframe, 24)