import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from market_structure.structure import StructureAnalyzer
from market_structure.fvg import FVGAnalyzer
from strategies.base import BaseStrategy

class CHOCHReversal(BaseStrategy):
    def __init__(self):
        super().__init__("S03_CHOCH")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        swings = SwingDetector(2, 2).find_swings(df)
        structures = StructureAnalyzer(swings).find_events(df)
        fvgs = FVGAnalyzer().find_fvgs(df)
        
        for structure in structures:
            if "CHOCH" not in structure.event_type:
                continue
                
            is_bullish = "BULLISH" in structure.event_type
            
            # Look for FVG in the same direction of the CHOCH
            for fvg in fvgs:
                if fvg.index in (structure.index, structure.index + 1) and fvg.is_bullish == is_bullish:
                    entry = fvg.bottom + (fvg.top - fvg.bottom) * 0.5
                    sl = fvg.bottom if is_bullish else fvg.top
                    
                    risk = abs(entry - sl)
                    if is_bullish:
                        tp = entry + (risk * 3.0) # 3R target for reversals
                        direction = SignalDirection.LONG
                    else:
                        tp = entry - (risk * 3.0)
                        direction = SignalDirection.SHORT
                        
                    signals.append(Signal(
                        strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                        direction=direction, entry_price=entry, stop_loss=sl, take_profit=tp,
                        created_at=df.index[fvg.index].to_pydatetime(), reasons=("CHOCH", "FVG Retest")
                    ))
                    break
        return signals