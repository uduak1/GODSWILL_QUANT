import pandas as pd
from core.types import SwingPoint

class SwingDetector:
    def __init__(self, left_bars: int = 2, right_bars: int = 2):
        self.left = left_bars
        self.right = right_bars

    def find_swings(self, df: pd.DataFrame) -> list[SwingPoint]:
        swings: list[SwingPoint] = []
        
        # Convert to numpy arrays for massive speed boost
        highs = df['high'].values
        lows = df['low'].values
        
        for i in range(self.left, len(df) - self.right):
            # Check Swing High
            is_high = True
            for j in range(1, self.left + 1):
                if highs[i] <= highs[i - j]: is_high = False; break
            if is_high:
                for j in range(1, self.right + 1):
                    if highs[i] <= highs[i + j]: is_high = False; break
                    
            if is_high:
                swings.append(SwingPoint(
                    index=i, price=highs[i], is_high=True,
                    confirmed_at_index=i + self.right
                ))
                continue

            # Check Swing Low
            is_low = True
            for j in range(1, self.left + 1):
                if lows[i] >= lows[i - j]: is_low = False; break
            if is_low:
                for j in range(1, self.right + 1):
                    if lows[i] >= lows[i + j]: is_low = False; break
                    
            if is_low:
                swings.append(SwingPoint(
                    index=i, price=lows[i], is_high=False,
                    confirmed_at_index=i + self.right
                ))
                
        return swings