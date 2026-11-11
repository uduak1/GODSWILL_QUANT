from abc import ABC, abstractmethod
import pandas as pd
from core.types import Signal

class BaseStrategy(ABC):
    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, symbol: str, timeframe: str) -> list[Signal]:
        """Analyze the dataframe and return a list of Signal objects."""
        pass