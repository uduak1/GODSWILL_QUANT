import pandas as pd
import logging
from core.enums import SignalDirection
from strategies.base import BaseStrategy
from risk_management.engine import RiskManager
from backtesting.types import CompletedTrade, BacktestResult, ActiveTrade

logger = logging.getLogger("godswill.backtesting")


class Backtester:
    """Event-driven backtester with LIMIT-order fill simulation.

    Realistic features:
      - Signals are treated as LIMIT orders (matches how strategies are written)
      - Fills only if next candle's range crosses signal.entry_price
      - Rejects gap-fills > max_gap_pct (price ran away — cancel order)
      - Shifts SL/TP to preserve strategy's R:R when small gap occurs
      - Deducts spread (round-trip) + commission + slippage per trade
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        risk_manager: RiskManager,
        initial_balance: float = 10000.0,
        spread_pips: float = 0.0,
        commission_per_lot_roundtrip: float = 2.0,
        slippage_ticks: float = 0.5,
        max_gap_pct: float = 0.005,  # reject fills >0.5% away from limit
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.initial_balance = initial_balance
        self.spread = spread_pips
        self.commission = commission_per_lot_roundtrip
        self.slippage_ticks = slippage_ticks
        self.max_gap_pct = max_gap_pct

    def run(
        self,
        df: pd.DataFrame,
        symbol: str,
        symbol_specs: dict,
        timeframe: str = "H1",
    ) -> BacktestResult:

        # ---- 1. Pre-compute all signals (once, O(N)) ----
        all_signals = self.strategy.generate_signals(df, symbol, timeframe)
        signal_map = {sig.created_at: sig for sig in all_signals}

        balance = self.initial_balance
        equity_curve = [balance]
        completed_trades: list[CompletedTrade] = []
        active_trade: ActiveTrade | None = None
        pending_order = None  # (signal, index_placed)

        tick_size = symbol_specs.get("tick_size", 0.01)
        tick_value = symbol_specs.get("tick_value", 1.0)

        # ---- 2. Simulation loop ----
        for i in range(10, len(df)):
            current_candle = df.iloc[i]
            current_time = df.index[i].to_pydatetime()

            # ----- (A) Try to fill pending LIMIT order -----
            if pending_order is not None and active_trade is None:
                sig, placed_at = pending_order
                filled, fill_price = self._try_limit_fill(sig, current_candle)

                if filled:
                    volume = self.risk_manager.calculate_volume(
                        balance, sig, symbol_specs
                    )
                    if volume > 0:
                        # Preserve intended R:R by shifting SL/TP to actual fill
                        shift = fill_price - sig.entry_price
                        active_trade = ActiveTrade(
                            signal=sig,
                            volume=volume,
                            entry_time=current_time,
                            entry_price=fill_price,
                            stop_loss=sig.stop_loss + shift,
                            take_profit=sig.take_profit + shift,
                            direction=sig.direction,
                        )
                    pending_order = None

                # Cancel stale limit after 24h of unfilled
                elif i - placed_at > self._bars_for_24h(timeframe):
                    pending_order = None

            # ----- (B) Manage open trade: check SL/TP -----
            if active_trade is not None:
                hit_sl, hit_tp = self._check_sl_tp_hit(active_trade, current_candle)

                if hit_sl or hit_tp:
                    exit_price = (
                        active_trade.stop_loss if hit_sl
                        else active_trade.take_profit
                    )
                    reason = "STOP_LOSS" if hit_sl else "TAKE_PROFIT"

                    price_diff = abs(exit_price - active_trade.entry_price)
                    money_pnl = (
                        price_diff / tick_size
                    ) * tick_value * active_trade.volume

                    if reason == "STOP_LOSS":
                        money_pnl = -money_pnl

                    # ---- Costs (all correct formulas) ----
                    # Spread: paid once on entry + once on exit = round-trip
                    spread_cost = (
                        self.spread / tick_size
                    ) * tick_value * active_trade.volume

                    # Commission: per lot, round-trip
                    commission_cost = self.commission * active_trade.volume

                    # Slippage: slippage_ticks per side × 2 sides
                    # Each tick costs tick_value per 1.0 lot
                    slippage_cost = (
                        2 * self.slippage_ticks
                        * tick_value
                        * active_trade.volume
                    )

                    money_pnl -= (
                        spread_cost + commission_cost + slippage_cost
                    )
                    balance += money_pnl

                    completed_trades.append(CompletedTrade(
                        symbol=symbol,
                        direction=active_trade.direction,
                        entry_time=active_trade.entry_time,
                        exit_time=current_time,
                        entry_price=active_trade.entry_price,
                        exit_price=exit_price,
                        volume=active_trade.volume,
                        pnl=money_pnl,
                        reason=reason,
                    ))
                    active_trade = None
                    equity_curve.append(balance)

            # ----- (C) Place new pending LIMIT order at this candle's close -----
            if (
                active_trade is None
                and pending_order is None
                and current_time in signal_map
            ):
                latest_signal = signal_map[current_time]
                approved, _reason = self.risk_manager.approve_trade(
                    latest_signal,
                    current_open_positions=0,
                    daily_pnl_pct=0.0,
                )
                if approved:
                    pending_order = (latest_signal, i)

        # ---- 3. Metrics ----
        winning = [t for t in completed_trades if t.pnl > 0]
        losing = [t for t in completed_trades if t.pnl <= 0]
        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0
            else float("inf") if gross_profit > 0
            else 0.0
        )

        peak = equity_curve[0]
        max_dd = 0.0
        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            if dd > max_dd:
                max_dd = dd

        return BacktestResult(
            strategy_id=self.strategy.strategy_id,
            initial_balance=self.initial_balance,
            final_balance=balance,
            total_trades=len(completed_trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            profit_factor=profit_factor,
            max_drawdown_pct=max_dd,
            equity_curve=equity_curve,
            trades=completed_trades,
        )

    # ------------------------------------------------------------------ #
    # Limit order fill simulation with gap protection
    # ------------------------------------------------------------------ #

    def _try_limit_fill(self, signal, candle) -> tuple[bool, float]:
        """Return (filled, fill_price).

        Short limit @ L: fill if candle['high'] >= L.
        Long  limit @ L: fill if candle['low']  <= L.

        Rejects:
          1. Gap fills > max_gap_pct (price ran away — cancel order)
          2. Fills where SL would be on wrong side of entry (defensive)
        """
        L = signal.entry_price

        if signal.direction == SignalDirection.SHORT:
            if candle["high"] >= L:
                fill = max(L, candle["open"])
                # Reject gap fills
                if abs(fill - L) / L > self.max_gap_pct:
                    return False, 0.0
                # Reject if SL is below fill (invalid SHORT)
                if signal.stop_loss <= fill:
                    return False, 0.0
                return True, fill
        else:  # LONG
            if candle["low"] <= L:
                fill = min(L, candle["open"])
                if abs(fill - L) / L > self.max_gap_pct:
                    return False, 0.0
                # Reject if SL is above fill (invalid LONG)
                if signal.stop_loss >= fill:
                    return False, 0.0
                return True, fill
        return False, 0.0

    # ------------------------------------------------------------------ #
    # SL / TP check (conservative: SL wins on ambiguous bars)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_sl_tp_hit(active_trade, candle) -> tuple[bool, bool]:
        if active_trade.direction == SignalDirection.LONG:
            sl_hit = candle["low"] <= active_trade.stop_loss
            tp_hit = candle["high"] >= active_trade.take_profit
        else:  # SHORT
            sl_hit = candle["high"] >= active_trade.stop_loss
            tp_hit = candle["low"] <= active_trade.take_profit
        if sl_hit:
            return True, False  # conservative
        return False, tp_hit

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _bars_for_24h(timeframe: str) -> int:
        """Number of bars to wait before cancelling an unfilled limit order."""
        bars_per_day = {
            "M1": 1440, "M5": 288, "M15": 96, "M30": 48,
            "H1": 24, "H4": 6, "D1": 1, "W1": 1,
        }
        return bars_per_day.get(timeframe, 24)