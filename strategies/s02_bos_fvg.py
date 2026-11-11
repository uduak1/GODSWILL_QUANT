import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from market_structure.structure import StructureAnalyzer
from market_structure.fvg import FVGAnalyzer
from strategies.base import BaseStrategy

class BOSFVGStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("S02_BOS_FVG")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        swings = SwingDetector(2, 2).find_swings(df)
        structures = StructureAnalyzer(swings).find_events(df)
        fvgs = FVGAnalyzer().find_fvgs(df)
        
        for structure in structures:
            if "BOS" not in structure.event_type:
                continue
                
            # Check for Displacement: Is the breaking candle body > 1.5x average body?
            body = abs(df['close'].iloc[structure.index] - df['open'].iloc[structure.index])
            avg_body = (df['close'] - df['open']).abs().mean()
            if body < (avg_body * 1.2):
                continue # Not enough momentum
                
            is_bullish = "BULLISH" in structure.event_type
            
            # Find FVG formed during or immediately after the BOS
            for fvg in fvgs:
                if fvg.index in (structure.index, structure.index + 1) and fvg.is_bullish == is_bullish:
                    entry = fvg.bottom + (fvg.top - fvg.bottom) * 0.5
                    
                    if is_bullish:
                        sl = fvg.bottom - (avg_body * 0.5)
                        tp = entry + (entry - sl) * 2.0
                        direction = SignalDirection.LONG
                    else:
                        sl = fvg.top + (avg_body * 0.5)
                        tp = entry - (sl - entry) * 2.0
                        direction = SignalDirection.SHORT
                        
                    signals.append(Signal(
                        strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                        direction=direction, entry_price=entry, stop_loss=sl, take_profit=tp,
                        created_at=df.index[fvg.index].to_pydatetime(), reasons=("BOS", "Displacement", "FVG")
                    ))
                    break
        return signals