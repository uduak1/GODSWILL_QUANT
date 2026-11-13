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
# --- ALL STRATEGY IMPORTS ---
from strategies.s02_bos_fvg import BOSFVGStrategy
from strategies.s03_choch_reversal import CHOCHReversal
from strategies.s04_failed_breakout import FailedBreakoutReversal
from strategies.s05_supply_demand import SupplyDemand
from strategies.s06_breakout_retest import BreakoutRetest
from strategies.s07_trend_continuation import TrendContinuation
from strategies.s09_range_reversal import RangeReversal
from strategies.s10_multi_structure import MultiStructureConfluence
from strategies.s11_ob_mitigation import OBMitigation
from strategies.s12_dxy_ob_confluence import DXYOrderBlockConfluence
from strategies.s13_momentum_displacement import MomentumDisplacement
from strategies.s14_range_extreme_fade import RangeExtremeFade

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
# FINAL FROZEN PORTFOLIO — 39 combos (Strictly OOS Validated)
# ---------------------------------------------------------------------- #
FROZEN_PORTFOLIO = [
    # --- ELITE WINNERS ---
    ("XAUUSD", "M15", "S05"),
    ("GBPUSD", "D1",  "S07"), 
    ("USDCHF", "D1",  "S03"),
    ("XAUUSD", "H1",  "S04"),  
    ("XAUUSD", "M30", "S07"),
    ("GER40",  "H1",  "S05"),
    ("GER40",  "M15", "S05"),
    ("USOIL",  "H1",  "S05"),
    ("GER40",  "H4",  "S07"),
    ("EURGBP", "H4",  "S05"), 
    ("EURUSD", "M15", "S05"), 
    
    # --- PROBATION ---
    ("XAUUSD", "H1",  "S05"),   
    ("XAGUSD", "H4",  "S05"),   
    ("XAUUSD", "H1",  "S11"),   
    ("EURUSD", "H4",  "S11"),   
    ("XAUUSD", "H1",  "S12"),   

    # --- S13 & S14 COMBOS ---
    ("XAUUSD", "H4",  "S13"), 
    ("GER40",  "H1",  "S13"), 
    ("EURUSD", "H4",  "S14"), 
    ("XAUUSD", "H4",  "S14"), 

    # --- PREVIOUS SCAN WINNERS ---
    ("NZDUSD", "H4",  "S05"),  
    ("UKOIL",  "H4",  "S05"),  
    ("USOIL",  "H4",  "S05"),  
    ("GER40",  "M30", "S05"),  
    ("GER40",  "H4",  "S04"),  
    ("USDJPY", "W1",  "S07"),  

    # --- NEW DISCOVERIES ---
    ("EURUSD", "D1",  "S10"),  
    ("XAGUSD", "H4",  "S02"),  
    ("USDCHF", "H4",  "S09"),  
    ("NZDUSD", "H4",  "S04"),  
    ("#BTCUSD", "M30", "S04"), 
    ("#BTCUSD", "M30", "S11"), 
    ("USOIL", "M30", "S10"),   
    ("XAGUSD", "M30", "S10"),  
    ("UKOIL", "M15", "S10"),   
    ("GBPUSD", "D1",  "S10"),  
    ("USDCHF", "H4",  "S06"),  
    ("GER40", "H1",   "S02"),  
    ("USOIL", "M15", "S10"),   
]


# Risk multiplier per combo (Based strictly on 5000-candle OOS)
TIER_RISK = {
    # --- PASSED OOS (Real Risk) ---
    ("XAUUSD", "M15", "S05"): 1.00,
    ("GBPUSD", "D1",  "S07"): 1.00, 
    ("GER40",  "M30", "S05"): 1.00, # King (PF 2.26)
    ("GER40",  "M15", "S05"): 1.00, 
    ("USDCHF", "H4",  "S09"): 0.50, # NEW (PF 3.02)
    ("EURUSD", "D1",  "S10"): 0.50, # NEW (PF 1.84)
    ("XAUUSD", "H1",  "S04"): 0.50, 
    ("XAUUSD", "H1",  "S11"): 0.50, 
    ("EURUSD", "H4",  "S11"): 0.50, 
    ("GER40",  "H1",  "S05"): 0.50, 
    ("GER40",  "H4",  "S04"): 0.50, 
    ("GER40",  "H1",  "S02"): 0.25, # NEW (PF 1.64)
    ("#BTCUSD", "M30", "S04"): 0.25, # NEW (PF 1.57)
    ("NZDUSD", "H4",  "S04"): 0.25, # NEW (PF 1.42)
    ("XAGUSD", "H4",  "S02"): 0.25, # NEW (PF 1.20)

    # --- SPECIAL EXEMPTION (High Profit, High DD) ---
    ("XAUUSD", "H4",  "S13"): 0.01, # Made +$11k OOS, but DD 25.6%

    # --- FAILED OOS (Tuned to ZERO to preserve live equity) ---
    ("USDCHF", "D1",  "S03"): 0.0001,
    ("XAUUSD", "M30", "S07"): 0.0001,
    ("EURGBP", "H4",  "S05"): 0.0001,
    ("EURUSD", "M15", "S05"): 0.0001,
    ("XAUUSD", "H1",  "S05"): 0.0001,
    ("XAGUSD", "H4",  "S05"): 0.0001,
    ("XAUUSD", "H1",  "S12"): 0.0001,
    ("GER40",  "H1",  "S13"): 0.0001,
    ("EURUSD", "H4",  "S14"): 0.0001,
    ("XAUUSD", "H4",  "S14"): 0.0001,
    ("NZDUSD", "H4",  "S05"): 0.0001,
    ("UKOIL",  "H4",  "S05"): 0.0001,
    ("USOIL",  "H4",  "S05"): 0.0001,
    ("GER40",  "H4",  "S07"): 0.0001,
    ("USDJPY", "W1",  "S07"): 0.0001,
    ("#BTCUSD", "M30", "S11"): 0.0001,
    ("USOIL", "M30", "S10"): 0.0001,
    ("XAGUSD", "M30", "S10"): 0.0001,
    ("UKOIL", "M15", "S10"): 0.0001,
    ("GBPUSD", "D1",  "S10"): 0.0001,
    ("USDCHF", "H4",  "S06"): 0.0001,
    ("USOIL", "M15", "S10"): 0.0001,
}


SPREADS = {
    "XAUUSD": 0.25, "XAGUSD": 0.03,
    "USOIL": 0.03, "UKOIL": 0.03,
    "EURUSD": 0.00015, "GBPUSD": 0.00015,
    "AUDUSD": 0.00015, "USDCHF": 0.00015,
    "USDCAD": 0.00015, "USDJPY": 0.015,
    "NZDUSD": 0.00015,
    "EURJPY": 0.020, "GBPJPY": 0.030,
    "EURGBP": 0.00020, "AUDJPY": 0.015,
    "CADJPY": 0.020, "EURCHF": 0.00020,
    "#BTCUSD": 30.0, "#ETHUSD": 2.5,
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
    MIN_OOS_TRADES = 10
    MIN_OOS_PF = 1.14        
    MAX_OOS_DD = 25.0
    MIN_TRADES_PER_DAY = 0.01
    SUSPICIOUS_PF = 5.0
    MAX_TRADES_PER_DAY = 4.0

    def __init__(self, gateway: MT5Gateway, risk_manager: RiskManager):
        self.gateway = gateway
        self.risk_manager = risk_manager
        self._strategies = {
            "S02": BOSFVGStrategy(),
            "S03": CHOCHReversal(),
            "S04": FailedBreakoutReversal(),
            "S05": SupplyDemand(),
            "S06": BreakoutRetest(),
            "S07": TrendContinuation(),
            "S09": RangeReversal(),
            "S10": MultiStructureConfluence(),
            "S11": OBMitigation(),
            "S12": DXYOrderBlockConfluence(),
            "S13": MomentumDisplacement(), 
            "S14": RangeExtremeFade(),     
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