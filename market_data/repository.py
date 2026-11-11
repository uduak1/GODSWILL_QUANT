"""SQLite persistence for candles with incremental update support."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from core.enums import Timeframe
from database.connection import Database

logger = logging.getLogger("godswill.market_data.repository")


class CandleRepository:
    def __init__(self, db: Database):
        self._db = db

    def upsert_candles(
        self, symbol: str, timeframe: Timeframe, df: pd.DataFrame
    ) -> int:
        """Insert or update rows. Returns rows affected."""
        if df.empty:
            return 0

        rows = [
            (
                symbol,
                timeframe.value,
                ts.isoformat(),
                float(row.open),
                float(row.high),
                float(row.low),
                float(row.close),
                int(row.tick_volume),
            )
            for ts, row in df.iterrows()
        ]

        with self._db.connection() as conn:
            conn.executemany(
                """INSERT INTO candles
                   (symbol, timeframe, ts, open, high, low, close, tick_volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, timeframe, ts) DO UPDATE SET
                     open=excluded.open, high=excluded.high,
                     low=excluded.low, close=excluded.close,
                     tick_volume=excluded.tick_volume""",
                rows,
            )
        logger.info("Upserted %d candles %s/%s", len(rows), symbol, timeframe.value)
        return len(rows)

    def last_timestamp(
        self, symbol: str, timeframe: Timeframe
    ) -> datetime | None:
        with self._db.connection() as conn:
            row = conn.execute(
                """SELECT MAX(ts) FROM candles
                   WHERE symbol = ? AND timeframe = ?""",
                (symbol, timeframe.value),
            ).fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)
        return None

    def load_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Load candles into a DataFrame indexed by UTC timestamp."""
        query = (
            "SELECT ts, open, high, low, close, tick_volume "
            "FROM candles WHERE symbol = ? AND timeframe = ?"
        )
        params: list = [symbol, timeframe.value]

        if start:
            query += " AND ts >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND ts <= ?"
            params.append(end.isoformat())

        query += " ORDER BY ts ASC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self._db.connection() as conn:
            rows = conn.execute(query, params).fetchall()

        if not rows:
            return pd.DataFrame(
                columns=["open", "high", "low", "close", "tick_volume"]
            )

        df = pd.DataFrame(
            [dict(r) for r in rows],
            columns=["ts", "open", "high", "low", "close", "tick_volume"],
        )
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        return df.set_index("ts").astype(
            {"open": float, "high": float, "low": float,
             "close": float, "tick_volume": int}
        )

    def count(self, symbol: str, timeframe: Timeframe) -> int:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM candles WHERE symbol=? AND timeframe=?",
                (symbol, timeframe.value),
            ).fetchone()
        return int(row[0]) if row else 0