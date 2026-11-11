import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from strategies.base import BaseStrategy

class SupplyDemand(BaseStrategy):
    def __init__(self):
        super().__init__("S05_SUPPLY_DEMAND")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        swings = SwingDetector(2, 2).find_swings(df)
        avg_body = (df['close'] - df['open']).abs().mean()
        
        for swing in swings:
            # We want a swing that was left behind by a massive move
            if swing.index < 3 or swing.confirmed_at_index >= len(df) - 2:
                continue
                
            # Look for a massive candle within 3 bars of the swing
            for i in range(swing.index, min(swing.index + 3, len(df))):
                body = abs(df['close'].iloc[i] - df['open'].iloc[i])
                if body > (avg_body * 2.0):
                    # We found a strong departure!
                    # Entry is at the 50% of the swing candle (the zone)
                    entry = swing.price
                    
                    if swing.is_high: # Supply Zone
                        sl = entry + (body * 0.5)
                        tp = entry - (sl - entry) * 2.0
                        direction = SignalDirection.SHORT
                    else: # Demand Zone
                        sl = entry - (body * 0.5)
                        tp = entry + (entry - sl) * 2.0
                        direction = SignalDirection.LONG
                        
                    signals.append(Signal(
                        strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                        direction=direction, entry_price=entry, stop_loss=sl, take_profit=tp,
                        created_at=df.index[i].to_pydatetime(), reasons=("Supply/Demand Zone", "Strong Departure")
                    ))
                    break
        return signals