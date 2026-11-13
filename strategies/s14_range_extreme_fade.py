import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from strategies.base import BaseStrategy

class RangeExtremeFade(BaseStrategy):
    def __init__(self):
        super().__init__("S14_RANGE_EXTREME_FADE")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        if len(df) < 50:
            return signals

        for i in range(50, len(df)):
            current = df.iloc[i]
            
            # Find 50-candle range
            recent_df = df.iloc[i-50:i]
            range_high = recent_df['high'].max()
            range_low = recent_df['low'].min()
            range_size = range_high - range_low
            
            if range_size == 0:
                continue
                
            # Premium (Top 15%) and Discount (Bottom 15%)
            premium_zone = range_high - (range_size * 0.15)
            discount_zone = range_low + (range_size * 0.15)

            # Fade the Premium (SHORT)
            if current['high'] >= premium_zone:
                # Bearish Pin bar rejection
                is_bearish_pin = (current['high'] - current['close']) > (current['close'] - current['low']) * 2
                if is_bearish_pin:
                    entry = current['close']
                    sl = current['high'] + (range_size * 0.05) 
                    risk = sl - entry
                    if risk > 0:
                        tp = range_low + (range_size * 0.5) # TP at midline
                        signals.append(Signal(
                            strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                            direction=SignalDirection.SHORT, entry_price=entry, stop_loss=sl, take_profit=tp,
                            created_at=df.index[i].to_pydatetime(), reasons=("Range Premium Fade", "Bearish Pin")
                        ))

            # Fade the Discount (LONG)
            elif current['low'] <= discount_zone:
                # Bullish Pin bar rejection
                is_bullish_pin = (current['close'] - current['low']) > (current['high'] - current['close']) * 2
                if is_bullish_pin:
                    entry = current['close']
                    sl = current['low'] - (range_size * 0.05)
                    risk = entry - sl
                    if risk > 0:
                        tp = range_low + (range_size * 0.5) # TP at midline
                        signals.append(Signal(
                            strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                            direction=SignalDirection.LONG, entry_price=entry, stop_loss=sl, take_profit=tp,
                            created_at=df.index[i].to_pydatetime(), reasons=("Range Discount Fade", "Bullish Pin")
                        ))

        return signals