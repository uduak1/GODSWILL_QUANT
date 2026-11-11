import pandas as pd
from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_structure.swings import SwingDetector
from market_structure.structure import StructureAnalyzer
from market_structure.order_block import OrderBlockAnalyzer
from strategies.base import BaseStrategy

class OrderBlockRetest(BaseStrategy):
    def __init__(self):
        super().__init__("S04_ORDER_BLOCK")

    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        signals = []
        swings = SwingDetector(2, 2).find_swings(df)
        structures = StructureAnalyzer(swings).find_events(df)
        obs = OrderBlockAnalyzer(structures).find_order_blocks(df)
        
        for ob in obs:
            # We want to enter if price retests the OB *after* the structure break
            # But for backtesting, we just generate a signal based on the OB presence and a future retest.
            # To keep it simple: we generate a limit order at the 50% of the OB.
            entry = ob.bottom + (ob.top - ob.bottom) * 0.5
            
            if ob.is_bullish:
                sl = ob.bottom - (ob.top - ob.bottom) * 0.2 # SL slightly below OB
                tp = entry + (entry - sl) * 2.0
                direction = SignalDirection.LONG
            else:
                sl = ob.top + (ob.top - ob.bottom) * 0.2
                tp = entry - (sl - entry) * 2.0
                direction = SignalDirection.SHORT
                
            signals.append(Signal(
                strategy_id=self.strategy_id, symbol=symbol, timeframe=Timeframe(timeframe),
                direction=direction, entry_price=entry, stop_loss=sl, take_profit=tp,
                created_at=df.index[ob.index].to_pydatetime(), reasons=("Order Block", "Retest")
            ))
        return signals