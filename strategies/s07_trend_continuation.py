import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from market_structure.structure import StructureAnalyzer
from market_structure.fvg import FVGAnalyzer
from strategies.base import BaseStrategy

class TrendContinuation(BaseStrategy):
    def __init__(self):
        super().__init__("S07_TREND_CONTINUATION")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        swings = SwingDetector(2, 2).find_swings(df)
        structures = StructureAnalyzer(swings).find_events(df)
        fvgs = FVGAnalyzer().find_fvgs(df)
        
        current_trend = None
        for struct in structures:
            if "BULLISH" in struct.event_type:
                current_trend = "BULLISH"
            elif "BEARISH" in struct.event_type:
                current_trend = "BEARISH"
                
            if current_trend == "BULLISH":
                for fvg in fvgs:
                    if fvg.index >= struct.index and fvg.is_bullish:
                        entry = fvg.bottom + (fvg.top - fvg.bottom) * 0.5
                        sl = fvg.bottom
                        tp = entry + (entry - sl) * 2.0
                        signals.append(Signal(
                            strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                            direction=SignalDirection.LONG, entry_price=entry, stop_loss=sl, take_profit=tp,
                            created_at=df.index[fvg.index].to_pydatetime(), reasons=("Bullish Trend", "FVG Pullback")
                        ))
                        break
                        
            elif current_trend == "BEARISH":
                for fvg in fvgs:
                    if fvg.index >= struct.index and not fvg.is_bullish:
                        entry = fvg.top - (fvg.top - fvg.bottom) * 0.5
                        sl = fvg.top
                        tp = entry - (sl - entry) * 2.0
                        signals.append(Signal(
                            strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                            direction=SignalDirection.SHORT, entry_price=entry, stop_loss=sl, take_profit=tp,
                            created_at=df.index[fvg.index].to_pydatetime(), reasons=("Bearish Trend", "FVG Pullback")
                        ))
                        break
        return signals