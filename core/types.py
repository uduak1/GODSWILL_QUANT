"""Lightweight dataclasses shared across modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .enums import SignalDirection, Timeframe


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0


@dataclass(frozen=True, slots=True)
class Signal:
    strategy_id: str
    symbol: str
    timeframe: Timeframe
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    created_at: datetime
    score: float = 0.0
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def reward_risk(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        return reward / risk if risk > 0 else 0.0


# --------------------------------------------------------------------------- #
# Phase 3 — Market Structure Types
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class SwingPoint:
    index: int
    price: float
    is_high: bool
    confirmed_at_index: int


@dataclass(frozen=True, slots=True)
class MarketStructureEvent:
    event_type: str
    index: int
    price: float
    origin_swing_index: int


@dataclass(frozen=True, slots=True)
class FairValueGap:
    index: int
    top: float
    bottom: float
    is_bullish: bool


@dataclass(frozen=True, slots=True)
class LiquiditySweep:
    index: int
    swept_level: float
    is_buy_side: bool


# --------------------------------------------------------------------------- #
# Phase 4 — Strategy Types
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class OrderBlock:
    index: int
    top: float
    bottom: float
    is_bullish: bool