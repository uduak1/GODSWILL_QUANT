import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from strategies.base import BaseStrategy

class MomentumDisplacement(BaseStrategy):
    def __init__(self):
        super().__init__("S13_MOMENTUM_DISPLACEMENT")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        if len(df) < 20:
            return signals

        # Calculate average body size
        df['body'] = abs(df['close'] - df['open'])
        avg_body = df['body'].rolling(window=20).mean()

        for i in range(20, len(df)):
            current = df.iloc[i]
            avg = avg_body.iloc[i]
            
            if pd.isna(avg) or avg == 0:
                continue

            body = current['body']
            
            # 1. Displacement check: Body is at least 1.8x the average
            if body < (avg * 1.8):
                continue

            # 2. Structural Break: Must break the recent 10-candle high/low
            recent_high = df['high'].iloc[i-10:i].max()
            recent_low = df['low'].iloc[i-10:i].min()

            is_bullish = current['close'] > current['open']
            is_bearish = current['close'] < current['open']

            # BULLISH DISPLACEMENT
            if is_bullish and current['close'] > recent_high:
                entry = current['close']
                sl = current['low'] # SL at the low of the massive candle
                risk = entry - sl
                
                if risk > 0:
                    tp = entry + (risk * 2.0) # 1:2 R:R
                    signals.append(Signal(
                        strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                        direction=SignalDirection.LONG, entry_price=entry, stop_loss=sl, take_profit=tp,
                        created_at=df.index[i].to_pydatetime(), reasons=("Bullish Displacement", "10-Candle Breakout")
                    ))

            # BEARISH DISPLACEMENT
            elif is_bearish and current['close'] < recent_low:
                entry = current['close']
                sl = current['high'] # SL at the high of the massive candle
                risk = sl - entry
                
                if risk > 0:
                    tp = entry - (risk * 2.0) # 1:2 R:R
                    signals.append(Signal(
                        strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                        direction=SignalDirection.SHORT, entry_price=entry, stop_loss=sl, take_profit=tp,
                        created_at=df.index[i].to_pydatetime(), reasons=("Bearish Displacement", "10-Candle Breakout")
                    ))

        return signals