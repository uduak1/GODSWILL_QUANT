import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from strategies.base import BaseStrategy

class RangeReversal(BaseStrategy):
    def __init__(self):
        super().__init__("S09_RANGE_REVERSAL")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        swings = SwingDetector(2, 2).find_swings(df)
        
        # Find equal highs (within 0.1%) or equal lows
        for i in range(len(swings) - 1):
            s1, s2 = swings[i], swings[i+1]
            if s1.is_high == s2.is_high:
                if abs(s1.price - s2.price) / s1.price < 0.001:
                    # We have a range boundary!
                    # Generate a reversal signal if price sweeps it.
                    if s1.is_high:
                        # Short on sweep of the equal highs
                        entry = s1.price
                        sl = entry * 1.002
                        tp = entry - (sl - entry) * 2.0
                        signals.append(Signal(
                            strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                            direction=SignalDirection.SHORT, entry_price=entry, stop_loss=sl, take_profit=tp,
                            created_at=df.index[s2.confirmed_at_index].to_pydatetime(), reasons=("Equal Highs", "Range Sweep")
                        ))
                    else:
                        # Long on sweep of the equal lows
                        entry = s1.price
                        sl = entry * 0.998
                        tp = entry + (entry - sl) * 2.0
                        signals.append(Signal(
                            strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                            direction=SignalDirection.LONG, entry_price=entry, stop_loss=sl, take_profit=tp,
                            created_at=df.index[s2.confirmed_at_index].to_pydatetime(), reasons=("Equal Lows", "Range Sweep")
                        ))
        return signals