"""IMarketDataProvider implementation backed by MT5 + SQLite."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from core.enums import Timeframe
from core.exceptions import MarketDataError          # <-- FIX: was missing
from core.interfaces import IMarketDataProvider
from configuration.settings import MT5Settings
from database.connection import Database
from market_data.mt5_gateway import MT5Gateway
from market_data.repository import CandleRepository
from market_data.symbol_resolver import SymbolResolver
from market_data.validation import validate_ohlcv, ValidationReport

logger = logging.getLogger("godswill.market_data.mt5_provider")


class MT5MarketDataProvider(IMarketDataProvider):
    def __init__(
        self,
        mt5_settings: MT5Settings,
        db: Database,
        symbol_suffix: str = "",
        symbol_prefix: str = "",
    ):
        self._settings = mt5_settings
        self._db = db
        self._repo = CandleRepository(db)
        self._resolver = SymbolResolver(
            configured_suffix=symbol_suffix,
            configured_prefix=symbol_prefix,
        )
        self._gateway: MT5Gateway | None = None

    # ------------------------------------------------------------------ #
    # IMarketDataProvider
    # ------------------------------------------------------------------ #

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start=None,
        end=None,
        count: int | None = None,
    ) -> pd.DataFrame:
        resolved = self._resolver.resolve(symbol)
        if resolved is None:
            raise MarketDataError(f"Symbol not found: {symbol}")

        df = self._fetch_and_store(resolved, timeframe, count or 1000)

        if start or end:
            mask = pd.Series(True, index=df.index)
            if start:
                mask &= df.index >= pd.Timestamp(start, tz=timezone.utc)
            if end:
                mask &= df.index <= pd.Timestamp(end, tz=timezone.utc)
            df = df[mask]

        return df

    def get_rates_range(
        self,
        symbol: str,
        timeframe: Timeframe,
        date_from: datetime,
        date_to: datetime,
    ) -> pd.DataFrame:
        resolved = self._resolver.resolve(symbol)
        if resolved is None:
            raise MarketDataError(f"Symbol not found: {symbol}")

        with self._gateway_context() as gw:
            df = gw.get_rates_range(resolved, timeframe, date_from, date_to)

        report = validate_ohlcv(df, resolved, timeframe)
        if not report.is_clean:
            logger.warning("Validation issues for %s/%s:\n%s",
                           resolved, timeframe.value, report.summary())

        self._repo.upsert_candles(resolved, timeframe, df)
        return df

    def get_symbol_specs(self, symbol: str) -> dict:
        resolved = self._resolver.resolve(symbol)
        if resolved is None:
            raise MarketDataError(f"Symbol not found: {symbol}")
        with self._gateway_context() as gw:
            return gw.symbol_specs(resolved)

    def list_available_symbols(self) -> list[str]:
        with self._gateway_context() as gw:
            return gw.list_symbols()

    def list_symbols_matching(self, pattern: str = "") -> list[str]:
        """Return broker symbols whose name contains `pattern` (case-insensitive)."""
        all_names = self.list_available_symbols()
        if not pattern:
            return all_names
        p = pattern.upper()
        return [n for n in all_names if p in n.upper()]

    def validate_and_report(
        self, symbol: str, timeframe: Timeframe, count: int = 5000
    ) -> ValidationReport:
        df = self.get_candles(symbol, timeframe, count=count)
        return validate_ohlcv(df, symbol, timeframe)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _fetch_and_store(
        self, resolved_symbol: str, timeframe: Timeframe, count: int
    ) -> pd.DataFrame:
        with self._gateway_context() as gw:
            df = gw.get_rates(resolved_symbol, timeframe, count=count)

        report = validate_ohlcv(df, resolved_symbol, timeframe)
        if not report.is_clean:
            logger.warning(
                "Validation issues for %s/%s:\n%s",
                resolved_symbol, timeframe.value, report.summary(),
            )

        self._repo.upsert_candles(resolved_symbol, timeframe, df)
        return df

    def _gateway_context(self):
        if self._gateway is None:
            self._gateway = MT5Gateway(self._settings)
        return self._gateway.connection()