import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from market_structure.liquidity import LiquidityAnalyzer
from market_structure.fvg import FVGAnalyzer
from market_structure.order_block import OrderBlockAnalyzer
from market_structure.structure import StructureAnalyzer
from strategies.base import BaseStrategy

class MultiStructureConfluence(BaseStrategy):
    def __init__(self):
        super().__init__("S10_MULTI_STRUCTURE")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        swings = SwingDetector(2, 2).find_swings(df)
        
        sweeps = LiquidityAnalyzer(swings).find_sweeps(df)
        structures = StructureAnalyzer(swings).find_events(df)
        obs = OrderBlockAnalyzer(structures).find_order_blocks(df)
        fvgs = FVGAnalyzer().find_fvgs(df)
        
        # Find a sweep, followed by a CHOCH, followed by an OB and FVG in the same direction
        for sweep in sweeps:
            for struct in structures:
                if struct.index > sweep.index and "CHOCH" in struct.event_type:
                    is_bullish = "BULLISH" in struct.event_type
                    
                    # Check for OB and FVG near the structure break
                    has_ob = any(ob.is_bullish == is_bullish and abs(ob.index - struct.index) < 5 for ob in obs)
                    has_fvg = any(fvg.is_bullish == is_bullish and abs(fvg.index - struct.index) < 5 for fvg in fvgs)
                    
                    if has_ob and has_fvg:
                        entry = struct.price
                        sl = sweep.swept_level
                        tp = entry + (entry - sl) * 3.0 if is_bullish else entry - (sl - entry) * 3.0
                        direction = SignalDirection.LONG if is_bullish else SignalDirection.SHORT
                        
                        signals.append(Signal(
                            strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                            direction=direction, entry_price=entry, stop_loss=sl, take_profit=tp,
                            created_at=df.index[struct.index].to_pydatetime(), reasons=("Sweep", "CHOCH", "OB", "FVG")
                        ))
                        break
        return signals