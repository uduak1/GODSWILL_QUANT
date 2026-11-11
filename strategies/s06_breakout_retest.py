import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from strategies.base import BaseStrategy

class BreakoutRetest(BaseStrategy):
    def __init__(self):
        super().__init__("S06_BREAKOUT_RETEST_TUNED")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        swings = SwingDetector(2, 2).find_swings(df)
        
        # Calculate average body size to measure displacement
        avg_body = (df['close'] - df['open']).abs().mean()
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values
        
        for swing in swings:
            if swing.confirmed_at_index >= len(df) - 2:
                continue
                
            for i in range(swing.confirmed_at_index, len(df)):
                # TUNING: The breakout candle must have a body > 1.5x the average body
                body = abs(closes[i] - opens[i])
                if body < (avg_body * 1.5):
                    continue # Ignore weak breakouts
                
                # Breakout above swing high
                if swing.is_high and closes[i] > swing.price:
                    entry = swing.price
                    sl = entry - (entry * 0.002)
                    tp = entry + (entry - sl) * 2.0
                    signals.append(Signal(
                        strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                        direction=SignalDirection.LONG, entry_price=entry, stop_loss=sl, take_profit=tp,
                        created_at=df.index[i].to_pydatetime(), reasons=("Tuned Breakout", "Displacement")
                    ))
                    break
                    
                # Breakout below swing low
                elif not swing.is_high and closes[i] < swing.price:
                    entry = swing.price
                    sl = entry + (entry * 0.002)
                    tp = entry - (sl - entry) * 2.0
                    signals.append(Signal(
                        strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                        direction=SignalDirection.SHORT, entry_price=entry, stop_loss=sl, take_profit=tp,
                        created_at=df.index[i].to_pydatetime(), reasons=("Tuned Breakout", "Displacement")
                    ))
                    break
        return signals