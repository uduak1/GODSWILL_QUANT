import pandas as pd
from core.types import SwingPoint, MarketStructureEvent

class StructureAnalyzer:
    def __init__(self, swings: list[SwingPoint]):
        self.swings = sorted(swings, key=lambda s: s.index)

    def find_events(self, df: pd.DataFrame) -> list[MarketStructureEvent]:
        events = []
        trend = None
        last_high = None
        last_low = None
        
        closes = df['close'].values # Numpy array speed
        
        swing_iter = iter(self.swings)
        current_swing = next(swing_iter, None)
        
        for i in range(len(df)):
            while current_swing and current_swing.confirmed_at_index <= i:
                if current_swing.is_high: last_high = current_swing
                else: last_low = current_swing
                current_swing = next(swing_iter, None)
            
            close = closes[i]
            
            if trend == "BULLISH" and last_high and close > last_high.price:
                events.append(MarketStructureEvent("BOS_BULLISH", i, last_high.price, last_high.index))
                last_high = None
                
            elif trend == "BEARISH" and last_low and close < last_low.price:
                events.append(MarketStructureEvent("BOS_BEARISH", i, last_low.price, last_low.index))
                last_low = None
                
            elif trend == "BULLISH" and last_low and close < last_low.price:
                events.append(MarketStructureEvent("CHOCH_BEARISH", i, last_low.price, last_low.index))
                trend = "BEARISH"
                last_low = None
                
            elif trend == "BEARISH" and last_high and close > last_high.price:
                events.append(MarketStructureEvent("CHOCH_BULLISH", i, last_high.price, last_high.index))
                trend = "BULLISH"
                last_high = None
                
            elif trend is None:
                if last_high and close > last_high.price:
                    events.append(MarketStructureEvent("BOS_BULLISH", i, last_high.price, last_high.index))
                    trend = "BULLISH"
                    last_high = None
                elif last_low and close < last_low.price:
                    events.append(MarketStructureEvent("BOS_BEARISH", i, last_low.price, last_low.index))
                    trend = "BEARISH"
                    last_low = None
                    
        return events