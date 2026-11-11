import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from market_structure.liquidity import LiquidityAnalyzer
from market_structure.structure import StructureAnalyzer
from market_structure.fvg import FVGAnalyzer
from strategies.base import BaseStrategy


class LiquiditySweepReversal(BaseStrategy):
    """S01 — Sweep + CHOCH + FVG reversal.

    Relaxed filters (v2):
      - CHOCH window: 20 bars (was 10)
      - Displacement: 1.1× avg body (was 1.2×)
      - FVG freshness: only invalidate on 50% mitigation (was: any touch)
      - Premium/discount filter: kept (this is the fundamental edge)
    """

    def __init__(self):
        super().__init__("S01_LIQUIDITY_SWEEP_TUNED")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals: list[Signal] = []
        if len(df) < 30:
            return signals

        swings = SwingDetector(left_bars=2, right_bars=2).find_swings(df)
        sweeps = LiquidityAnalyzer(swings).find_sweeps(df)
        structures = StructureAnalyzer(swings).find_events(df)
        fvgs = FVGAnalyzer().find_fvgs(df)

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values
        avg_body = max((df['close'] - df['open']).abs().mean(), 1e-9)

        CHOCH_WINDOW = 20
        DISPLACEMENT_MULT = 1.1
        PD_WINDOW = 50

        for sweep in sweeps:
            # ---- Premium / Discount filter ----
            start = max(0, sweep.index - PD_WINDOW)
            recent_high = highs[start:sweep.index + 1].max()
            recent_low = lows[start:sweep.index + 1].min()
            rng = recent_high - recent_low
            if rng <= 0:
                continue
            sweep_pct = (closes[sweep.index] - recent_low) / rng

            if not sweep.is_buy_side and sweep_pct > 0.55:   # was 0.50 — slight allowance
                continue
            if sweep.is_buy_side and sweep_pct < 0.45:       # was 0.50
                continue

            for structure in structures:
                if structure.index <= sweep.index:
                    continue
                if structure.index > sweep.index + CHOCH_WINDOW:
                    break
                if "CHOCH" not in structure.event_type:
                    continue

                # ---- Displacement requirement ----
                choch_body = abs(closes[structure.index] - opens[structure.index])
                if choch_body < avg_body * DISPLACEMENT_MULT:
                    continue

                is_bullish = "BULLISH" in structure.event_type

                for fvg in fvgs:
                    if fvg.index < structure.index or fvg.index > structure.index + 5:
                        continue
                    if fvg.is_bullish != is_bullish:
                        continue

                    # ---- Relaxed freshness check: only invalidate on 50% mitigation ----
                    fvg_mid = (fvg.top + fvg.bottom) / 2.0
                    invalidated = False
                    for k in range(fvg.index + 1, len(df)):
                        if fvg.is_bullish:
                            if lows[k] <= fvg_mid:      # only fully mitigated
                                invalidated = True
                                break
                        else:
                            if highs[k] >= fvg_mid:
                                invalidated = True
                                break
                    if invalidated:
                        continue

                    # ---- Entry / SL / TP ----
                    if is_bullish:
                        entry = fvg.bottom + (fvg.top - fvg.bottom) * 0.5
                        sweep_wick = min(lows[sweep.index], lows[structure.index])
                        sl = sweep_wick - avg_body * 0.5
                        risk = entry - sl
                        if risk <= 0:
                            continue
                        tp = entry + risk * 2.0
                        direction = SignalDirection.LONG
                    else:
                        entry = fvg.top - (fvg.top - fvg.bottom) * 0.5
                        sweep_wick = max(highs[sweep.index], highs[structure.index])
                        sl = sweep_wick + avg_body * 0.5
                        risk = sl - entry
                        if risk <= 0:
                            continue
                        tp = entry - risk * 2.0
                        direction = SignalDirection.SHORT

                    signals.append(Signal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        timeframe=Timeframe(timeframe),
                        direction=direction,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit=tp,
                        created_at=df.index[fvg.index].to_pydatetime(),
                        reasons=("Sweep", "CHOCH<20", "Displacement", "FVG(50%)",
                                 "Premium/Discount"),
                    ))
                    break

        return signals