"""Draw persistent signal arrows + tooltips on MT5 charts."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5

from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_data.timeframe_map import to_mt5

logger = logging.getLogger("godswill.execution.chart_annotator")


class ChartAnnotator:
    """Draw signal arrows + tooltips on MT5 charts.

    MT5 limitation: chart_object_create with chart_id=0 uses the active
    chart. For multi-chart annotation, we enumerate all open charts and
    find the matching symbol + timeframe.
    """

    COLOR_LONG = 0x00CC00
    COLOR_SHORT = 0x0000FF
    ARROW_LONG = 233
    ARROW_SHORT = 234

    def annotate_signal(self, signal: Signal) -> bool:
        chart_id = self._find_chart(signal.symbol, signal.timeframe)
        if chart_id is None:
            logger.warning(
                f"[WARN] no MT5 chart open for {signal.symbol} "
                f"{signal.timeframe.value}. Open it in MT5 to see arrows."
            )
            return False

        ts = int(signal.created_at.timestamp())
        obj_name = self._obj_name(signal)
        mt5.chart_object_delete(chart_id, obj_name)

        is_long = signal.direction == SignalDirection.LONG
        if not mt5.chart_object_create(
            chart_id, obj_name, mt5.OBJ_ARROW, 0, ts, signal.entry_price, 1.0
        ):
            code, msg = mt5.last_error()
            logger.error(f"[ERROR] chart_object_create failed [{code}] {msg}")
            return False

        mt5.chart_object_set_integer(
            chart_id, obj_name, mt5.OBJPROP_ARROWCODE,
            self.ARROW_LONG if is_long else self.ARROW_SHORT,
        )
        mt5.chart_object_set_integer(
            chart_id, obj_name, mt5.OBJPROP_COLOR,
            self.COLOR_LONG if is_long else self.COLOR_SHORT,
        )
        mt5.chart_object_set_integer(chart_id, obj_name, mt5.OBJPROP_WIDTH, 3)
        mt5.chart_object_set_string(
            chart_id, obj_name, mt5.OBJPROP_TEXT, self._tooltip(signal)
        )
        mt5.chart_redraw(chart_id)
        logger.info(
            f"[OK] annotated {signal.symbol} {signal.timeframe.value} {obj_name}"
        )
        return True

    def annotate_many(self, signals: list[Signal]) -> int:
        return sum(1 for s in signals if self.annotate_signal(s))

    def redraw_from_db(self, db, lookback_days: int = 7) -> int:
        """Re-draw recent signals from DB (persistence across restarts)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        with db.connection() as conn:
            rows = conn.execute(
                """SELECT strategy_id, symbol, timeframe, direction,
                          entry_price, stop_loss, take_profit, created_at,
                          reasons_json, score
                   FROM signals
                   WHERE created_at >= ?
                   ORDER BY created_at ASC""",
                (cutoff.isoformat(),),
            ).fetchall()

        signals: list[Signal] = []
        for row in rows:
            try:
                signals.append(Signal(
                    strategy_id=row["strategy_id"],
                    symbol=row["symbol"],
                    timeframe=Timeframe(row["timeframe"]),
                    direction=SignalDirection(row["direction"]),
                    entry_price=float(row["entry_price"]),
                    stop_loss=float(row["stop_loss"]),
                    take_profit=float(row["take_profit"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    score=float(row["score"] or 0),
                    reasons=tuple(json.loads(row["reasons_json"] or "[]")),
                ))
            except Exception as exc:
                logger.warning(f"[WARN] skipping malformed DB signal: {exc}")

        return self.annotate_many(signals)

    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_chart(symbol: str, timeframe: Timeframe) -> int | None:
        """Enumerate open MT5 charts to find the one matching symbol+timeframe."""
        try:
            target_tf = to_mt5(timeframe)
            cid = mt5.chart_first()
            while cid and cid != 0:
                try:
                    if (
                        mt5.chart_symbol(cid) == symbol
                        and mt5.chart_period(cid) == target_tf
                    ):
                        return cid
                except Exception:
                    pass
                cid = mt5.chart_next()
        except Exception as exc:
            logger.debug(f"chart enumeration failed: {exc}")
        return None

    def _obj_name(self, signal: Signal) -> str:
        return (
            f"GW_{signal.strategy_id}_{signal.symbol}_"
            f"{int(signal.created_at.timestamp())}"
        )

    def _tooltip(self, signal: Signal) -> str:
        """Tooltip shown when hovering over the arrow on MT5 chart.

        Uses ASCII + basic Unicode only (no emojis) for MT5 compatibility.
        """
        is_long = signal.direction == SignalDirection.LONG
        side = "BUY" if is_long else "SELL"
        arrow = ">>" if is_long else "<<"
        lines = [
            f"{arrow} {side} - {signal.strategy_id}",
            f"Symbol: {signal.symbol}  TF: {signal.timeframe.value}",
            f"Entry:  {signal.entry_price:.5f}",
            f"SL:     {signal.stop_loss:.5f}",
            f"TP:     {signal.take_profit:.5f}",
            f"R:R:    {signal.reward_risk:.2f}",
            f"Score:  {signal.score:.0f}/100",
            f"Time:   {signal.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
            "---",
            "Reasons:",
        ]
        for r in signal.reasons:
            lines.append(f"  - {r}")
        return "\n".join(lines)