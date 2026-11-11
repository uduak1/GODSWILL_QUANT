"""Data quality checks for OHLCV DataFrames."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from core.enums import Timeframe


@dataclass
class ValidationReport:
    symbol: str
    timeframe: Timeframe
    total_rows: int = 0
    duplicate_timestamps: int = 0
    missing_candles: int = 0
    ohlc_violations: int = 0
    non_positive_prices: int = 0
    non_monotonic_time: bool = False
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return (
            self.duplicate_timestamps == 0
            and self.ohlc_violations == 0
            and self.non_positive_prices == 0
            and not self.non_monotonic_time
            and len(self.errors) == 0
        )

    def summary(self) -> str:
        lines = [
            f"Validation [{self.symbol} {self.timeframe.value}]: "
            f"{self.total_rows} rows, "
            f"{self.first_ts} → {self.last_ts}",
            f"  duplicates: {self.duplicate_timestamps}",
            f"  missing: {self.missing_candles} (expected gap check skipped for range queries)",
            f"  OHLC violations: {self.ohlc_violations}",
            f"  non-positive: {self.non_positive_prices}",
            f"  monotonic: {not self.non_monotonic_time}",
        ]
        if self.errors:
            lines.append(f"  errors: {self.errors}")
        return "\n".join(lines)


def validate_ohlcv(
    df: pd.DataFrame,
    symbol: str,
    timeframe: Timeframe,
    expected_freq: str | None = None,
) -> ValidationReport:
    """Run full validation. Does not raise — returns a report."""
    report = ValidationReport(symbol=symbol, timeframe=timeframe)
    report.total_rows = len(df)

    if df.empty:
        report.errors.append("empty dataframe")
        return report

    report.first_ts = df.index[0].to_pydatetime()
    report.last_ts = df.index[-1].to_pydatetime()

    # Monotonic timestamps
    if not df.index.is_monotonic_increasing:
        report.non_monotonic_time = True
        report.errors.append("timestamps not monotonically increasing")

    # Duplicates
    dup_count = int(df.index.duplicated().sum())
    report.duplicate_timestamps = dup_count
    if dup_count:
        report.errors.append(f"{dup_count} duplicate timestamps")

    # OHLC integrity
    ohlc_bad = (
        (df["high"] < df["low"])
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
    )
    report.ohlc_violations = int(ohlc_bad.sum())
    if report.ohlc_violations:
        report.errors.append(f"{report.ohlc_violations} OHLC violations")

    # Non-positive prices
    price_cols = ["open", "high", "low", "close"]
    non_positive = (df[price_cols] <= 0).any(axis=1)
    report.non_positive_prices = int(non_positive.sum())
    if report.non_positive_prices:
        report.errors.append(f"{report.non_positive_prices} non-positive prices")

    return report


def expected_bar_timedelta(timeframe: Timeframe) -> pd.Timedelta:
    """Expected duration between consecutive bars (approximate for M12/M20)."""
    mapping = {
        Timeframe.M1: pd.Timedelta(minutes=1),
        Timeframe.M5: pd.Timedelta(minutes=5),
        Timeframe.M12: pd.Timedelta(minutes=12),
        Timeframe.M15: pd.Timedelta(minutes=15),
        Timeframe.M20: pd.Timedelta(minutes=20),
        Timeframe.M30: pd.Timedelta(minutes=30),
        Timeframe.H1: pd.Timedelta(hours=1),
        Timeframe.H4: pd.Timedelta(hours=4),
        Timeframe.D1: pd.Timedelta(days=1),
        Timeframe.W1: pd.Timedelta(weeks=1),
    }
    return mapping[timeframe]


def find_gaps(
    df: pd.DataFrame,
    timeframe: Timeframe,
    max_gap_multiplier: int = 3,
) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    """Return list of (gap_start, gap_end, missing_count) for gaps larger than
    `max_gap_multiplier` × expected bar duration."""
    if len(df) < 2:
        return []

    expected = expected_bar_timedelta(timeframe)
    threshold = expected * max_gap_multiplier
    deltas = df.index.to_series().diff()
    
    gaps = []
    # FIXED FOR PANDAS 3.x: Iterate directly over the items to avoid mask length mismatch
    for idx, delta in deltas.items():
        if pd.isna(delta):
            continue
        if delta > threshold:
            pos = df.index.get_loc(idx)
            prev_idx = df.index[pos - 1]
            missing = int(delta / expected) - 1
            gaps.append((prev_idx, idx, missing))

    return gaps