"""Low-level MT5 connection and data access wrapper.

MetaTrader5 is imported lazily inside connect() so the module can be
imported (and unit tested) without the package installed.

Terminal path resolution (in priority order):
  1. mt5.terminal_path from config.yaml, if set and the file exists
  2. Auto-discovery via market_data.mt5_discovery
  3. MetaTrader5.initialize() with no path (attaches to a running terminal)
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from core.enums import Timeframe
from core.exceptions import MT5ConnectionError, MarketDataError
from configuration.settings import MT5Settings
from market_data.timeframe_map import to_mt5

logger = logging.getLogger("godswill.market_data.mt5_gateway")


def _import_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError as exc:
        raise MT5ConnectionError(
            "MetaTrader5 package not installed. Install with: "
            "python -m pip install MetaTrader5"
        ) from exc


class MT5Gateway:
    def __init__(self, settings: MT5Settings):
        self._settings = settings
        self._connected = False
        self._mt5 = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        if self._connected:
            return

        mt5 = _import_mt5()
        self._mt5 = mt5

        resolved_path = self._resolve_terminal_path()
        if resolved_path:
            logger.info("Using MT5 terminal at %s", resolved_path)
        else:
            logger.info(
                "No terminal path resolved — relying on MetaTrader5's own "
                "auto-connect (a terminal must already be running)."
            )

        kwargs: dict = {"timeout": self._settings.timeout_ms}
        if resolved_path:
            kwargs["path"] = str(resolved_path)
        if self._settings.login:
            kwargs["login"] = self._settings.login
        if self._settings.password:
            kwargs["password"] = self._settings.password
        if self._settings.server:
            kwargs["server"] = self._settings.server

        if not mt5.initialize(**kwargs):
            code, msg = mt5.last_error()
            raise MT5ConnectionError(self._diagnostic_message(code, msg))

        self._connected = True
        logger.info("MT5 connected: %s", self._terminal_info_str())

    def shutdown(self) -> None:
        if self._connected and self._mt5 is not None:
            self._mt5.shutdown()
            self._connected = False
            logger.info("MT5 shutdown")

    @contextmanager
    def connection(self) -> Iterator["MT5Gateway"]:
        self.connect()
        try:
            yield self
        finally:
            self.shutdown()

    # ------------------------------------------------------------------ #
    # Terminal path resolution (no broker assumptions)
    # ------------------------------------------------------------------ #

    def _resolve_terminal_path(self) -> Path | None:
        # 1. Explicit config path (only if it actually exists)
        if self._settings.terminal_path:
            configured = Path(self._settings.terminal_path)
            if configured.exists():
                return configured
            logger.warning(
                "Configured mt5.terminal_path does not exist: %s — "
                "falling back to auto-discovery.",
                configured,
            )

        # 2. Auto-discovery
        from market_data.mt5_discovery import discover_terminal_paths
        candidates = discover_terminal_paths()
        if candidates:
            if len(candidates) > 1:
                logger.info(
                    "Multiple MT5 terminals found (%d); using: %s",
                    len(candidates), candidates[0],
                )
            return candidates[0]

        # 3. Nothing — let MT5 self-resolve
        return None

    def _diagnostic_message(self, code: int, msg: str) -> str:
        from market_data.mt5_discovery import discover_terminal_paths
        candidates = discover_terminal_paths()
        found_str = (
            "\n    ".join(str(p) for p in candidates)
            if candidates
            else "(none — MT5 may not be installed, or is installed but neither "
                 "running nor registered in the MetaQuotes registry)"
        )
        return (
            f"MT5 initialize failed: [{code}] {msg}\n"
            f"\nDiagnostics:\n"
            f"  1. Is a MetaTrader 5 terminal open and logged in?\n"
            f"  2. Is 'Algo Trading' enabled (green button in MT5 toolbar)?\n"
            f"  3. Is XAUUSD visible in MT5 Market Watch?\n"
            f"\nDiscovered terminals:\n    {found_str}\n"
            f"\nTo pin a specific terminal, set 'mt5.terminal_path' in "
            f"configuration/config.yaml."
        )

    # ------------------------------------------------------------------ #
    # Account / terminal
    # ------------------------------------------------------------------ #

    def account_info(self) -> dict:
        info = self._mt5.account_info()
        if info is None:
            raise MT5ConnectionError("account_info returned None")
        return info._asdict()

    def terminal_info(self) -> dict:
        info = self._mt5.terminal_info()
        if info is None:
            raise MT5ConnectionError("terminal_info returned None")
        return info._asdict()

    # ------------------------------------------------------------------ #
    # Symbols
    # ------------------------------------------------------------------ #

    def symbol_info(self, symbol: str) -> dict:
        info = self._mt5.symbol_info(symbol)
        if info is None:
            raise MarketDataError(f"Symbol not found: {symbol}")
        return info._asdict()

    def symbol_specs(self, symbol: str) -> dict:
        raw = self.symbol_info(symbol)
        return {
            "name": raw["name"],
            "point": raw["point"],
            "digits": raw["digits"],
            "tick_size": raw.get("trade_tick_size", raw["point"]),
            "tick_value": raw.get("trade_tick_value", 1.0),
            "volume_min": raw["volume_min"],
            "volume_max": raw["volume_max"],
            "volume_step": raw["volume_step"],
            "contract_size": raw.get("trade_contract_size", 100_000),
            "stops_level": raw.get("trade_stops_level", 0),
            "freeze_level": raw.get("trade_freeze_level", 0),
            "filling_mode": raw.get("filling_mode", 0),
            "trade_mode": raw.get("trade_mode", 0),
            "currency_profit": raw.get("currency_profit", ""),
            "currency_margin": raw.get("currency_margin", ""),
        }

    def list_symbols(self) -> list[str]:
        symbols = self._mt5.symbols_get()
        return [s.name for s in symbols] if symbols else []

    # ------------------------------------------------------------------ #
    # Historical rates
    # ------------------------------------------------------------------ #

    def get_rates(
        self, symbol: str, timeframe: Timeframe,
        count: int = 1000, start_pos: int = 0,
    ) -> pd.DataFrame:
        mt5_tf = to_mt5(timeframe)
        rates = self._mt5.copy_rates_from_pos(symbol, mt5_tf, start_pos, count)
        if rates is None:
            code, msg = self._mt5.last_error()
            raise MarketDataError(
                f"copy_rates_from_pos failed for {symbol}/{timeframe.value}: "
                f"[{code}] {msg}"
            )
        if len(rates) == 0:
            raise MarketDataError(f"No rates returned for {symbol}/{timeframe.value}")
        return self._rates_to_df(rates)

    def get_rates_range(
        self, symbol: str, timeframe: Timeframe,
        date_from: datetime, date_to: datetime,
    ) -> pd.DataFrame:
        mt5_tf = to_mt5(timeframe)
        rates = self._mt5.copy_rates_range(symbol, mt5_tf, date_from, date_to)
        if rates is None:
            code, msg = self._mt5.last_error()
            raise MarketDataError(
                f"copy_rates_range failed for {symbol}/{timeframe.value}: "
                f"[{code}] {msg}"
            )
        if len(rates) == 0:
            raise MarketDataError(
                f"No rates for {symbol}/{timeframe.value} "
                f"between {date_from} and {date_to}"
            )
        return self._rates_to_df(rates)

    @staticmethod
    def _rates_to_df(rates: np.ndarray) -> pd.DataFrame:
        df = pd.DataFrame(rates)
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("timestamp")
        df = df[["open", "high", "low", "close", "tick_volume"]]
        return df.astype({
            "open": "float64", "high": "float64",
            "low": "float64", "close": "float64",
            "tick_volume": "int64",
        })

    def _terminal_info_str(self) -> str:
        try:
            ti = self._mt5.terminal_info() if self._mt5 else None
            if ti:
                return f"{ti.name} build {ti.build} @ {ti.path}"
        except Exception:
            pass
        return "unknown terminal"