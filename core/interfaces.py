"""Abstract interfaces every implementation must honour."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

import pandas as pd

from .enums import Timeframe
from .types import Signal


class IMarketDataProvider(ABC):
    @abstractmethod
    def get_candles(
        self, symbol: str, timeframe: Timeframe,
        start=None, end=None, count: int | None = None,
    ) -> pd.DataFrame: ...


class IStrategy(ABC):
    """Every trading strategy must implement this interface."""
    strategy_id: str

    @abstractmethod
    def analyze(self, context: dict) -> Sequence[Signal]: ...


class IRiskEngine(ABC):
    @abstractmethod
    def approve(self, proposed_trade: dict) -> tuple[bool, str]: ...


class IExecutionEngine(ABC):
    @abstractmethod
    def submit(self, approved_trade: dict) -> dict: ...


class IBacktester(ABC):
    @abstractmethod
    def run(self, config: dict) -> dict: ...