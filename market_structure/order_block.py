import pandas as pd
from core.types import MarketStructureEvent, OrderBlock

class OrderBlockAnalyzer:
    def __init__(self, structures: list[MarketStructureEvent]):
        self.structures = structures

    def find_order_blocks(self, df: pd.DataFrame) -> list[OrderBlock]:
        obs = []
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        
        for structure in self.structures:
            is_bullish = "BULLISH" in structure.event_type
            
            for i in range(structure.index - 1, max(-1, structure.index - 10), -1):
                is_down = closes[i] < opens[i]
                is_up = closes[i] > opens[i]
                
                if is_bullish and is_down:
                    obs.append(OrderBlock(index=i, top=highs[i], bottom=lows[i], is_bullish=True))
                    break
                elif not is_bullish and is_up:
                    obs.append(OrderBlock(index=i, top=highs[i], bottom=lows[i], is_bullish=False))
                    break
        return obs