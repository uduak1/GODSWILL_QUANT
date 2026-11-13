import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from strategies.base import BaseStrategy

class DXYOrderBlockConfluence(BaseStrategy):
    def __init__(self, rr_ratio: float = 3.0, atr_multiplier: float = 1.5, 
                 session_start_hour: int = 7, session_end_hour: int = 17,
                 dxy_symbol: str = "EURUSD"): # Using EURUSD as DXY proxy
        super().__init__("S12_DXY_OB_CONFLUENCE")
        self.rr_ratio = rr_ratio
        self.atr_multiplier = atr_multiplier
        self.session_start = session_start_hour
        self.session_end = session_end_hour
        self.dxy_symbol = dxy_symbol

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

    @staticmethod
    def _calculate_ema(closes: np.ndarray, period: int = 50) -> np.ndarray:
        return pd.Series(closes).ewm(span=period, adjust=False).mean().to_numpy()

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        if len(df) < 50:
            return signals

        # 1. Fetch Proxy Data internally
        from market_data.timeframe_map import to_mt5
        tf_mt5 = to_mt5(Timeframe(timeframe))
        
        dxy_rates = mt5.copy_rates_from_pos(self.dxy_symbol, tf_mt5, 0, len(df))
        if dxy_rates is None or len(dxy_rates) < 50:
            return signals
            
        df_dxy = pd.DataFrame(dxy_rates)
        # Force the first column to be named 'time' to prevent KeyError
        df_dxy.rename(columns={df_dxy.columns[0]: "time"}, inplace=True)
        df_dxy['time'] = pd.to_datetime(df_dxy['time'], unit='s', utc=True)
        
        # 2. Align Dataframes by time
        df_asset = df.reset_index()
        # Force the first column to be named 'time' to prevent KeyError
        df_asset.rename(columns={df_asset.columns[0]: "time"}, inplace=True)
        
        # Ensure both time columns are timezone-aware UTC
        if df_asset['time'].dt.tz is None:
            df_asset['time'] = df_asset['time'].dt.tz_localize('UTC')
        else:
            df_asset['time'] = df_asset['time'].dt.tz_convert('UTC')

        merged = pd.merge(df_asset, df_dxy, on="time", suffixes=("_asset", "_dxy"), how="inner")
        
        if merged.empty or "time" not in merged.columns:
            return signals

        opens = merged["open_asset"].to_numpy(dtype=float)
        highs = merged["high_asset"].to_numpy(dtype=float)
        lows = merged["low_asset"].to_numpy(dtype=float)
        closes = merged["close_asset"].to_numpy(dtype=float)
        dxy_closes = merged["close_dxy"].to_numpy(dtype=float)

        # 3. STRAT_8_DXY_BIAS Macro Filter (INVERTED FOR EURUSD)
        dxy_ema = self._calculate_ema(dxy_closes, period=50)
        # EURUSD above EMA = USD is weak = Bullish for assets
        dxy_bullish_bias = dxy_closes > dxy_ema  

        # 4. STRAT_6_OB Order Block Mitigation Signal
        ob_mitigation = np.zeros_like(closes, dtype=bool)
        ob_mitigation[1:] = (
            (closes[:-1] < opens[:-1]) &   # Prev candle bearish
            (closes[1:] > opens[1:]) &     # Current candle bullish
            (closes[1:] > highs[:-1])      # Breaks prev high
        )

        # 5. Session & Volatility Masks
        hours = merged["time"].dt.hour.to_numpy()
        session_mask = (hours >= self.session_start) & (hours <= self.session_end)

        atr = self._calculate_atr(highs, lows, closes, period=14)
        atr_mean = pd.Series(atr).rolling(window=50, min_periods=1).mean().to_numpy()
        volatility_mask = atr > (atr_mean * 0.8)

        # Combined Signal Matrix
        valid_signals = ob_mitigation & dxy_bullish_bias & session_mask & volatility_mask

        # 6. Generate Signal Objects
        for i in range(1, len(merged)):
            if valid_signals[i]:
                entry_price = closes[i]
                sl_distance = atr[i] * self.atr_multiplier
                
                if sl_distance > 0:
                    sl = entry_price - sl_distance
                    tp = entry_price + (sl_distance * self.rr_ratio)
                    created_at = merged["time"].iloc[i].to_pydatetime()
                    
                    signals.append(Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        timeframe=Timeframe(timeframe),
                        direction=SignalDirection.LONG,
                        entry_price=entry_price,
                        stop_loss=sl,
                        take_profit=tp,
                        created_at=created_at,
                        reasons=("EURUSD Proxy Bias", "OB Mitigation", "ATR Volatility")
                    ))
                    
        return signals