import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from strategies.base import BaseStrategy

class FailedBreakoutReversal(BaseStrategy):
    """
    S04 - Institutional Failed-Breakout Reversal (Liquidity Sweep)
    
    Logic:
    1. Identify structural range (recent swing high and low).
    2. Wait for price to sweep the high/low but close back inside the range (Failed Breakout).
    3. Wait for an opposite displacement candle (body > 60% of range).
    4. Enter in the direction of the displacement.
    """
    def __init__(self):
        super().__init__("S04_FAILED_BREAKOUT")
        self.displacement_body_ratio = 0.60

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        if len(df) < 20:
            return signals

        swings = SwingDetector(2, 2).find_swings(df)
        
        # We need to iterate through the data to find the sequence
        for i in range(5, len(df) - 1):
            current_candle = df.iloc[i]
            next_candle = df.iloc[i+1]
            
            # Find the most recent swing high and low BEFORE this candle
            prior_swings = [s for s in swings if s.confirmed_at_index < i]
            if not prior_swings:
                continue
                
            recent_highs = [s for s in prior_swings if s.is_high]
            recent_lows = [s for s in prior_swings if not s.is_high]
            
            if not recent_highs or not recent_lows:
                continue

            upper_boundary = recent_highs[-1].price
            lower_boundary = recent_lows[-1].price

            # --- BULLISH FAILED BREAKOUT (Sweep Low) ---
            # 1. Current candle sweeps below the lower boundary
            # 2. Closes back above it (Failed breakout)
            if current_candle['low'] < lower_boundary and current_candle['close'] > lower_boundary:
                # 3. Next candle must be a strong bullish displacement
                body_ratio = abs(next_candle['close'] - next_candle['open']) / max((next_candle['high'] - next_candle['low']), 1e-9)
                
                if next_candle['close'] > next_candle['open'] and body_ratio >= self.displacement_body_ratio:
                    entry = next_candle['close']
                    # SL goes below the extreme wick of the failed breakout
                    sl = current_candle['low']
                    risk = entry - sl
                    
                    if risk > 0:
                        tp = entry + (risk * 2.0) # 1:2 R:R
                        signals.append(Signal(
                            strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                            direction=SignalDirection.LONG, entry_price=entry, stop_loss=sl, take_profit=tp,
                            created_at=df.index[i+1].to_pydatetime(), reasons=("Failed Breakout Sweep", "Bullish Displacement")
                        ))

            # --- BEARISH FAILED BREAKOUT (Sweep High) ---
            # 1. Current candle sweeps above the upper boundary
            # 2. Closes back below it (Failed breakout)
            if current_candle['high'] > upper_boundary and current_candle['close'] < upper_boundary:
                # 3. Next candle must be a strong bearish displacement
                body_ratio = abs(next_candle['close'] - next_candle['open']) / max((next_candle['high'] - next_candle['low']), 1e-9)
                
                if next_candle['close'] < next_candle['open'] and body_ratio >= self.displacement_body_ratio:
                    entry = next_candle['close']
                    # SL goes above the extreme wick of the failed breakout
                    sl = current_candle['high']
                    risk = sl - entry
                    
                    if risk > 0:
                        tp = entry - (risk * 2.0) # 1:2 R:R
                        signals.append(Signal(
                            strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                            direction=SignalDirection.SHORT, entry_price=entry, stop_loss=sl, take_profit=tp,
                            created_at=df.index[i+1].to_pydatetime(), reasons=("Failed Breakout Sweep", "Bearish Displacement")
                        ))
                        
        return signals