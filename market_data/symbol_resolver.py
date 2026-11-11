"""Broker-agnostic symbol discovery.

Key insight: MetaTrader5.symbol_info() returns None for symbols not currently
in Market Watch. The correct flow is:

    symbol_select(name, True)   ->  adds to Market Watch
    symbol_info(name)           ->  now returns real info

This resolver tries that pair on the base name, on prefix/suffix variants,
on common broker patterns, and finally scans the full broker symbol list.
"""
from __future__ import annotations

import logging
from typing import Final

from core.exceptions import MT5ConnectionError

logger = logging.getLogger("godswill.market_data.symbol_resolver")

COMMON_PATTERNS: Final[list[str]] = [
    "{base}", "{base}.US", "{base}.us", "#{base}",
    "{base}_CFD", "{base}.cfd", "{base}.pro",
    "{base}_m", "{base}.m", "{base}.cash",
    "{base}.a", "{base}.b", "{base}xx", "{base}.raw",
    "{base}m", "{base}i", "{base}.i",
]


def _import_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError as exc:
        raise MT5ConnectionError(
            "MetaTrader5 package not installed. Install with: "
            "python -m pip install MetaTrader5"
        ) from exc


class SymbolResolver:
    def __init__(self, configured_suffix: str = "", configured_prefix: str = ""):
        self.suffix = configured_suffix
        self.prefix = configured_prefix

    def resolve(self, base_symbol: str) -> str | None:
        mt5 = _import_mt5()

        # Build candidate list
        candidates: list[str] = [base_symbol]
        if self.prefix or self.suffix:
            candidates.append(f"{self.prefix}{base_symbol}{self.suffix}")
        for pattern in COMMON_PATTERNS:
            c = pattern.format(base=base_symbol)
            if c != base_symbol:
                candidates.append(c)

        # Try each candidate: select + confirm
        for cand in candidates:
            if self._try_activate(mt5, cand):
                if cand != base_symbol:
                    logger.info("Resolved %s → %s", base_symbol, cand)
                return cand

        # Fallback: scan broker's full symbol list for case-insensitive match
        try:
            all_symbols = mt5.symbols_get()
        except Exception as exc:
            logger.warning("symbols_get() failed: %s", exc)
            all_symbols = None

        if all_symbols:
            base_upper = base_symbol.upper()
            for sym in all_symbols:
                try:
                    if sym.name.upper() == base_upper:
                        if self._try_activate(mt5, sym.name):
                            return sym.name
                except Exception:
                    continue

        logger.warning("Symbol not found on this broker: %s", base_symbol)
        return None

    @staticmethod
    def _try_activate(mt5, name: str) -> bool:
        """Select symbol in Market Watch, then confirm the broker knows it.

        symbol_select(name, True) returns False if the symbol doesn't exist
        on the broker — safe to call on unknown names.
        """
        try:
            if not mt5.symbol_select(name, True):
                return False
            return mt5.symbol_info(name) is not None
        except Exception:
            return False