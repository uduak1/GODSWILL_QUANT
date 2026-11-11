import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from strategies.base import BaseStrategy


class DoubleTopBottom(BaseStrategy):
    """S08 — Double Top / Double Bottom reversal.

    Relaxed filters (v2):
      - Peak tolerance: 0.5% (was 0.3%)
      - Pattern height: 0.5% (was 1.0%)
      - Displacement: 1.0× avg body (was 1.2×)
      - Neckline break window: 40 bars (was 30)
      - Trend filter: kept (h_prev < h1 required)
    """

    def __init__(self):
        super().__init__("S08_DOUBLE_TOP_BOTTOM_TUNED")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals: list[Signal] = []
        if len(df) < 20:
            return signals

        swings = SwingDetector(2, 2).find_swings(df)
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values
        avg_body = max((df['close'] - df['open']).abs().mean(), 1e-9)

        swing_highs = [s for s in swings if s.is_high]
        swing_lows = [s for s in swings if not s.is_high]

        PEAK_TOLERANCE = 0.005     # 0.5%
        MIN_PATTERN_HEIGHT = 0.005 # 0.5%
        DISPLACEMENT_MULT = 1.0
        BREAK_WINDOW = 40

        # -----------------------------------------------------------------
        # DOUBLE TOPS → SHORT
        # -----------------------------------------------------------------
        for i in range(2, len(swing_highs)):
            h_prev, h1, h2 = swing_highs[i - 2], swing_highs[i - 1], swing_highs[i]

            # Prior uptrend required
            if h_prev.price >= h1.price * 0.99:
                continue

            # Peaks within tolerance
            if abs(h1.price - h2.price) / h1.price > PEAK_TOLERANCE:
                continue

            # Locate neckline (swing low between peaks)
            neckline = None
            for low in swing_lows:
                if h1.index < low.index < h2.index:
                    neckline = low
                    break
            if neckline is None:
                continue

            # Pattern height
            pattern_height = ((h1.price + h2.price) / 2) - neckline.price
            if pattern_height / neckline.price < MIN_PATTERN_HEIGHT:
                continue

            # Search for displaced break below neckline
            for j in range(h2.confirmed_at_index, min(len(df), h2.confirmed_at_index + BREAK_WINDOW)):
                if closes[j] < neckline.price:
                    body = abs(closes[j] - opens[j])
                    if body < avg_body * DISPLACEMENT_MULT:
                        continue

                    entry = neckline.price
                    sl = h2.price + (h2.price - neckline.price) * 0.1
                    risk = sl - entry
                    if risk <= 0:
                        continue
                    tp = entry - risk * 2.0

                    signals.append(Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        timeframe=Timeframe(timeframe),
                        direction=SignalDirection.SHORT,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit=tp,
                        created_at=df.index[j].to_pydatetime(),
                        reasons=("Double Top", "Uptrend", "Neckline Break", "Displacement"),
                    ))
                    break

        # -----------------------------------------------------------------
        # DOUBLE BOTTOMS → LONG
        # -----------------------------------------------------------------
        for i in range(2, len(swing_lows)):
            l_prev, l1, l2 = swing_lows[i - 2], swing_lows[i - 1], swing_lows[i]

            # Prior downtrend required
            if l_prev.price <= l1.price * 1.01:
                continue

            # Troughs within tolerance
            if abs(l1.price - l2.price) / l1.price > PEAK_TOLERANCE:
                continue

            neckline = None
            for high in swing_highs:
                if l1.index < high.index < l2.index:
                    neckline = high
                    break
            if neckline is None:
                continue

            pattern_height = neckline.price - ((l1.price + l2.price) / 2)
            if pattern_height / neckline.price < MIN_PATTERN_HEIGHT:
                continue

            for j in range(l2.confirmed_at_index, min(len(df), l2.confirmed_at_index + BREAK_WINDOW)):
                if closes[j] > neckline.price:
                    body = abs(closes[j] - opens[j])
                    if body < avg_body * DISPLACEMENT_MULT:
                        continue

                    entry = neckline.price
                    sl = l2.price - (neckline.price - l2.price) * 0.1
                    risk = entry - sl
                    if risk <= 0:
                        continue
                    tp = entry + risk * 2.0

                    signals.append(Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        timeframe=Timeframe(timeframe),
                        direction=SignalDirection.LONG,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit=tp,
                        created_at=df.index[j].to_pydatetime(),
                        reasons=("Double Bottom", "Downtrend", "Neckline Break", "Displacement"),
                    ))
                    break

        return signals