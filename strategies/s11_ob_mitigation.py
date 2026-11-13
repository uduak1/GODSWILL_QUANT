import numpy as np
import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from strategies.base import BaseStrategy


class OBMitigation(BaseStrategy):
    def __init__(self, rr_ratio: float = 3.0, atr_multiplier: float = 1.5, 
                 session_start_hour: int = 7, session_end_hour: int = 17):
        super().__init__("S11_OB_MITIGATION")
        self.rr_ratio = rr_ratio
        self.atr_multiplier = atr_multiplier
        self.session_start = session_start_hour
        self.session_end = session_end_hour

    @staticmethod
    def _calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
        tr = np.zeros_like(closes, dtype=float)
        tr[0] = highs[0] - lows[0]
        tr[1:] = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )
        return pd.Series(tr).rolling(window=period, min_periods=1).mean().to_numpy()

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        if len(df) < 200: # We need at least 200 candles for the EMA
            return signals

        opens = df["open"].to_numpy(dtype=float)
        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)

        # 1. Macro Trend Filter (200 EMA)
        ema_200 = pd.Series(closes).ewm(span=200, adjust=False).mean().to_numpy()
        macro_trend_bullish = closes > ema_200

        # 2. Core STRAT_6_OB Vectorized Signal
        ob_mitigation = np.zeros_like(closes, dtype=bool)
        ob_mitigation[1:] = (
            (closes[:-1] < opens[:-1]) &   # Prev candle bearish
            (closes[1:] > opens[1:]) &     # Current candle bullish
            (closes[1:] > highs[:-1])      # Breaks prev high
        )

        # 3. Session Mask
        hours = df.index.hour.to_numpy()
        session_mask = (hours >= self.session_start) & (hours <= self.session_end)

        # 4. Volatility Mask
        atr = self._calculate_atr(highs, lows, closes, period=14)
        atr_mean = pd.Series(atr).rolling(window=50, min_periods=1).mean().to_numpy()
        volatility_mask = atr > (atr_mean * 0.8)

        # Combine all filters (OB + Session + Volatility + MACRO TREND)
        valid_signals = ob_mitigation & session_mask & volatility_mask & macro_trend_bullish

        # 5. Generate Signal Objects
        for i in range(1, len(df)):
            if valid_signals[i]:
                entry_price = closes[i]
                sl_distance = atr[i] * self.atr_multiplier
                
                if sl_distance > 0:
                    sl = entry_price - sl_distance
                    tp = entry_price + (sl_distance * self.rr_ratio)
                    
                    signals.append(Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        timeframe=Timeframe(timeframe),
                        direction=SignalDirection.LONG,
                        entry_price=entry_price,
                        stop_loss=sl,
                        take_profit=tp,
                        created_at=df.index[i].to_pydatetime(),
                        reasons=("OB Mitigation", "Session", "ATR", "Macro Trend Up")
                    ))
                    
        return signals