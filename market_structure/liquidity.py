import pandas as pd
from core.types import SwingPoint, LiquiditySweep

class LiquidityAnalyzer:
    def __init__(self, swings: list[SwingPoint]):
        # Sort by confirmation time so we can track active swings efficiently
        self.swings = sorted(swings, key=lambda s: s.confirmed_at_index)

    def find_sweeps(self, df: pd.DataFrame) -> list[LiquiditySweep]:
        sweeps = []
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        
        active_highs = []
        active_lows = []
        s_idx = 0
        
        for i in range(len(df)):
            # Add newly confirmed swings to our active lists
            while s_idx < len(self.swings) and self.swings[s_idx].confirmed_at_index < i:
                sw = self.swings[s_idx]
                if sw.is_high:
                    active_highs.append(sw)
                else:
                    active_lows.append(sw)
                s_idx += 1
            
            # Check if current candle sweeps any active high
            for sw in active_highs:
                if highs[i] > sw.price and closes[i] < sw.price:
                    sweeps.append(LiquiditySweep(i, sw.price, True))
            
            # Check if current candle sweeps any active low
            for sw in active_lows:
                if lows[i] < sw.price and closes[i] > sw.price:
                    sweeps.append(LiquiditySweep(i, sw.price, False))
                    
        return sweeps