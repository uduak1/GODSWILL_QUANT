"""Out-of-sample validation for the frozen strategy portfolio."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from core.enums import Timeframe
from market_data.mt5_gateway import MT5Gateway
from risk_management.engine import RiskManager
from backtesting.engine import Backtester
from strategies.s03_choch_reversal import CHOCHReversal
from strategies.s05_supply_demand import SupplyDemand
from strategies.s06_breakout_retest import BreakoutRetest
from strategies.s07_trend_continuation import TrendContinuation

logger = logging.getLogger("godswill.research.validation")


@dataclass
class ValidationResult:
    symbol: str
    timeframe: str
    strategy_id: str
    oos_trades: int
    oos_pf: float
    oos_dd: float
    oos_winrate: float
    oos_net_profit: float
    trades_per_day: float
    passed: bool
    reason: str


# ---------------------------------------------------------------------- #
# FINAL FROZEN PORTFOLIO — 13 OOS-validated combos
# These are the ONLY combos with proven edge after the fixed backtester
# passed strict out-of-sample testing on 2,000 older candles.
# Verified 2026-11-09 with:
#   - LIMIT-order fill simulation (no market fills)
#   - Full costs: spread + commission + slippage
#   - 5× notional cap + 2% risk cap in risk manager
# ---------------------------------------------------------------------- #
FROZEN_PORTFOLIO = [
    # Tier 1 — PF > 1.6 (strong edges)
    ("XAUUSD", "M15", "S05"),
    ("GBPUSD", "H4",  "S07"),
    # Tier 2 — PF 1.3–1.5 (proven, thinner edge)
    ("UKOIL",  "M30", "S05"),
    ("USDCHF", "D1",  "S03"),
    # Tier 3 — PF 1.15–1.3 (marginal, use quarter risk)
    ("GER40",  "H4",  "S07"),
    ("XAGUSD", "M30", "S05"),
    ("GER40",  "H1",  "S05"),
    ("USOIL",  "H1",  "S05"),
    ("EURUSD", "M15", "S05"),
    ("GER40",  "M15", "S05"),
    ("EURGBP", "H1",  "S05"),
    ("XAUUSD", "M30", "S07"),
    ("XAUUSD", "H1",  "S05"),
]


# Risk multiplier per combo — used by live engine + tier logic
# Tier 1 = 1.0×, Tier 2 = 0.5×, Tier 3 = 0.25×
TIER_RISK = {
    ("XAUUSD", "M15", "S05"): 1.00,
    ("GBPUSD", "H4",  "S07"): 1.00,
    ("UKOIL",  "M30", "S05"): 0.50,
    ("USDCHF", "D1",  "S03"): 0.50,
    ("GER40",  "H4",  "S07"): 0.25,
    ("XAGUSD", "M30", "S05"): 0.25,
    ("GER40",  "H1",  "S05"): 0.25,
    ("USOIL",  "H1",  "S05"): 0.25,
    ("EURUSD", "M15", "S05"): 0.25,
    ("GER40",  "M15", "S05"): 0.25,
    ("EURGBP", "H1",  "S05"): 0.25,
    ("XAUUSD", "M30", "S07"): 0.25,
    ("XAUUSD", "H1",  "S05"): 0.25,
}


SPREADS = {
    # Metals
    "XAUUSD": 0.25, "XAGUSD": 0.03,
    # Energy
    "USOIL": 0.03, "UKOIL": 0.03,
    # Forex majors
    "EURUSD": 0.00015, "GBPUSD": 0.00015,
    "AUDUSD": 0.00015, "USDCHF": 0.00015,
    "USDCAD": 0.00015, "USDJPY": 0.015,
    "NZDUSD": 0.00015,
    # Cross pairs (still used for re-validation)
    "EURJPY": 0.020, "GBPJPY": 0.030,
    "EURGBP": 0.00020, "AUDJPY": 0.015,
    "CADJPY": 0.020, "EURCHF": 0.00020,
    # Crypto
    "#BTCUSD": 30.0, "#ETHUSD": 2.5,
    # Index
    "GER40": 1.0,
}

COMMISSION_PER_LOT = {
    "XAUUSD": 4.0, "XAGUSD": 4.0,
    "USOIL": 4.0, "UKOIL": 4.0,
    "EURUSD": 0.0, "GBPUSD": 0.0,
    "AUDUSD": 0.0, "USDCHF": 0.0,
    "USDCAD": 0.0, "USDJPY": 0.0,
    "NZDUSD": 0.0,
    "EURJPY": 0.0, "GBPJPY": 0.0,
    "EURGBP": 0.0, "AUDJPY": 0.0,
    "CADJPY": 0.0, "EURCHF": 0.0,
    "#BTCUSD": 8.0, "#ETHUSD": 6.0,
    "GER40": 4.0,
}

SLIPPAGE_TICKS = {
    "XAUUSD": 1.0, "XAGUSD": 1.0,
    "USOIL": 1.5, "UKOIL": 1.5,
    "EURUSD": 0.5, "GBPUSD": 0.8,
    "AUDUSD": 0.8, "USDCHF": 0.8,
    "USDCAD": 0.8, "USDJPY": 0.8,
    "NZDUSD": 1.0,
    "EURJPY": 1.0, "GBPJPY": 1.5,
    "EURGBP": 0.8, "AUDJPY": 1.0,
    "CADJPY": 1.0, "EURCHF": 1.0,
    "#BTCUSD": 3.0, "#ETHUSD": 3.0,
    "GER40": 2.0,
}

DAYS_PER_1000_CANDLES = {
    "M1": 1000/1440, "M5": 1000/288, "M15": 1000/96, "M30": 1000/48,
    "H1": 1000/24, "H4": 1000/6, "D1": 1000.0, "W1": 7000.0,
}


class PortfolioValidator:
    MIN_OOS_TRADES = 15
    MIN_OOS_PF = 1.15
    MAX_OOS_DD = 25.0
    MIN_TRADES_PER_DAY = 0.01
    SUSPICIOUS_PF = 5.0
    MAX_TRADES_PER_DAY = 4.0

    def __init__(self, gateway: MT5Gateway, risk_manager: RiskManager):
        self.gateway = gateway
        self.risk_manager = risk_manager
        self._strategies = {
            "S03": CHOCHReversal(), "S05": SupplyDemand(),
            "S06": BreakoutRetest(), "S07": TrendContinuation(),
        }

    def validate_all(self, oos_count: int = 2000, in_sample_count: int = 1000):
        results = []
        with self.gateway.connection() as gw:
            for symbol, tf_str, strat_id in FROZEN_PORTFOLIO:
                try:
                    tf = Timeframe(tf_str)
                    specs = gw.symbol_specs(symbol)
                    df = gw.get_rates(
                        symbol, tf, count=oos_count, start_pos=in_sample_count
                    )
                    if df is None or len(df) < 100:
                        logger.warning(f"Skip {symbol} {tf_str}: insufficient OOS data")
                        continue
                    strategy = self._strategies.get(strat_id)
                    if strategy is None:
                        continue

                    spread = SPREADS.get(symbol, 0.0)
                    commission = COMMISSION_PER_LOT.get(symbol, 2.0)
                    slippage = SLIPPAGE_TICKS.get(symbol, 1.0)

                    bt = Backtester(
                        strategy, self.risk_manager,
                        initial_balance=10000.0, spread_pips=spread,
                        commission_per_lot_roundtrip=commission,
                        slippage_ticks=slippage,
                    )
                    res = bt.run(df, symbol, specs, timeframe=tf.value)

                    win_rate = (
                        res.winning_trades / res.total_trades * 100
                        if res.total_trades > 0 else 0
                    )
                    net_profit = res.final_balance - res.initial_balance
                    days = DAYS_PER_1000_CANDLES.get(tf_str, 100) * (oos_count / 1000)
                    tpd = res.total_trades / max(days, 1e-6)
                    passed, reason = self._verdict(res, net_profit, tpd)

                    results.append(ValidationResult(
                        symbol=symbol, timeframe=tf_str, strategy_id=strat_id,
                        oos_trades=res.total_trades, oos_pf=res.profit_factor,
                        oos_dd=res.max_drawdown_pct, oos_winrate=win_rate,
                        oos_net_profit=net_profit, trades_per_day=tpd,
                        passed=passed, reason=reason,
                    ))
                except Exception as exc:
                    logger.error(f"OOS failed {symbol} {tf_str} {strat_id}: {exc}")
        return results

    def _verdict(self, res, net_profit, tpd):
        if res.total_trades < self.MIN_OOS_TRADES:
            return False, f"N={res.total_trades}<{self.MIN_OOS_TRADES}"
        if res.profit_factor > self.SUSPICIOUS_PF:
            return False, f"PF={res.profit_factor:.1f} suspicious"
        if res.profit_factor < self.MIN_OOS_PF:
            return False, f"PF={res.profit_factor:.2f}<{self.MIN_OOS_PF}"
        if res.max_drawdown_pct > self.MAX_OOS_DD:
            return False, f"DD={res.max_drawdown_pct:.1f}%>{self.MAX_OOS_DD}%"
        if net_profit <= 0:
            return False, f"Net ${net_profit:+,.0f}"
        if tpd < self.MIN_TRADES_PER_DAY:
            return False, f"Freq {tpd:.3f}/day<{self.MIN_TRADES_PER_DAY}"
        if tpd > self.MAX_TRADES_PER_DAY:
            return False, f"Freq {tpd:.2f}/day too high"
        return True, (
            f"PASS N={res.total_trades} PF={res.profit_factor:.2f} "
            f"DD={res.max_drawdown_pct:.1f}% {tpd:.2f}/day"
        )

    def save_report(self, results, path):
        payload = {
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "total_combos": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [r.__dict__ for r in results],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)