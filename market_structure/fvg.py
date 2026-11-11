import pandas as pd
from core.types import FairValueGap

class FVGAnalyzer:
    def find_fvgs(self, df: pd.DataFrame) -> list[FairValueGap]:
        fvgs = []
        highs = df['high'].values
        lows = df['low'].values
        
        for i in range(2, len(df)):
            high_1 = highs[i-2]
            low_1 = lows[i-2]
            high_3 = highs[i]
            low_3 = lows[i]
            
            if high_1 < low_3:
                fvgs.append(FairValueGap(index=i, top=low_3, bottom=high_1, is_bullish=True))
            elif low_1 > high_3:
                fvgs.append(FairValueGap(index=i, top=low_1, bottom=high_3, is_bullish=False))
                
        return fvgs