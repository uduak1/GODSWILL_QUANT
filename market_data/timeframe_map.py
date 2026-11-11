"""Bidirectional mapping between GODSWILL Timeframe and MT5 constants."""
from __future__ import annotations

from typing import Final

import MetaTrader5 as mt5

from core.enums import Timeframe
from core.exceptions import MarketDataError


# MT5 does not have native M12 or M20. Some brokers expose them via custom
# timeframes, but the standard API does not. We map to the nearest available
# and flag the substitution so callers know.
TO_MT5: Final[dict[Timeframe, int]] = {
    Timeframe.M1:  mt5.TIMEFRAME_M1,
    Timeframe.M5:  mt5.TIMEFRAME_M5,
    Timeframe.M12: mt5.TIMEFRAME_M15,   # substitution — documented
    Timeframe.M15: mt5.TIMEFRAME_M15,
    Timeframe.M20: mt5.TIMEFRAME_M20,   # may not exist on all brokers
    Timeframe.M30: mt5.TIMEFRAME_M30,
    Timeframe.H1:  mt5.TIMEFRAME_H1,
    Timeframe.H4:  mt5.TIMEFRAME_H4,
    Timeframe.D1:  mt5.TIMEFRAME_D1,
    Timeframe.W1:  mt5.TIMEFRAME_W1,
}

FROM_MT5: Final[dict[int, Timeframe]] = {
    mt5.TIMEFRAME_M1:  Timeframe.M1,
    mt5.TIMEFRAME_M5:  Timeframe.M5,
    mt5.TIMEFRAME_M15: Timeframe.M15,
    mt5.TIMEFRAME_M30: Timeframe.M30,
    mt5.TIMEFRAME_H1:  Timeframe.H1,
    mt5.TIMEFRAME_H4:  Timeframe.H4,
    mt5.TIMEFRAME_D1:  Timeframe.D1,
    mt5.TIMEFRAME_W1:  Timeframe.W1,
}

# Flag M12/M20 as approximations so callers can log or reject.
SUBSTITUTED_TIMEFRAMES: Final[dict[Timeframe, Timeframe]] = {
    Timeframe.M12: Timeframe.M15,
}


def to_mt5(tf: Timeframe) -> int:
    try:
        return TO_MT5[tf]
    except KeyError as exc:
        raise MarketDataError(f"Unsupported timeframe: {tf}") from exc


def from_mt5(constant: int) -> Timeframe:
    try:
        return FROM_MT5[constant]
    except KeyError as exc:
        raise MarketDataError(f"Unknown MT5 timeframe constant: {constant}") from exc


def is_substituted(tf: Timeframe) -> bool:
    return tf in SUBSTITUTED_TIMEFRAMES