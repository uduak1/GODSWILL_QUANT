"""Live signal engine — polls markets, fires trades, persists to DB."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta

from core.enums import SignalDirection, Timeframe
from core.types import Signal
from market_data.mt5_gateway import MT5Gateway
from risk_management.engine import RiskManager
from execution.chart_annotator import ChartAnnotator
from execution.engine import ExecutionEngine
from database.connection import Database
from configuration.settings import Settings

logger = logging.getLogger("godswill.execution.live_engine")


COOLDOWN_HOURS = {
    "M1": 1, "M5": 1, "M15": 2, "M30": 4,
    "H1": 6, "H4": 12, "D1": 48, "W1": 168,
}


class LiveEngine:
    def __init__(self, settings, db, portfolio, poll_seconds=60, dry_run=False):
        self.settings = settings
        self.db = db
        self.portfolio = portfolio
        self.poll_seconds = poll_seconds
        self.dry_run = dry_run

        self.gateway = MT5Gateway(settings.mt5)
        self.annotator = ChartAnnotator()
        self.risk_manager = RiskManager(settings.risk)
        self.execution_engine = ExecutionEngine(self.gateway)

        self._running = False
        self._last_processed = {}
        self._strategies = self._load_strategies()

    def _load_strategies(self):
        from strategies.s03_choch_reversal import CHOCHReversal
        from strategies.s05_supply_demand import SupplyDemand
        from strategies.s06_breakout_retest import BreakoutRetest
        from strategies.s07_trend_continuation import TrendContinuation
        return {
            "S03": CHOCHReversal(),
            "S05": SupplyDemand(),
            "S06": BreakoutRetest(),
            "S07": TrendContinuation(),
        }

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self):
        self._running = True
        mode = "DRY RUN" if self.dry_run else "LIVE EXECUTION"
        logger.info(
            f"[LIVE] engine started in {mode} mode: {len(self.portfolio)} combos, "
            f"poll={self.poll_seconds}s"
        )

        # Connect to MT5 ONCE
        try:
            self.gateway.connect()
            logger.info("[LIVE] MT5 connected (persistent)")
        except Exception as exc:
            logger.error(f"[LIVE] MT5 connect failed: {exc}")
            self._running = False
            return

        if not self.dry_run:
            try:
                count = self.annotator.redraw_from_db(self.db, lookback_days=7)
                logger.info(f"[LIVE] re-drew {count} recent signals from DB")
            except Exception as exc:
                logger.error(f"[LIVE] redraw from DB failed: {exc}")

        logger.info("[LIVE] polling started. Press Ctrl+C to stop.\n")

        try:
            while self._running:
                try:
                    self._poll_once()
                except Exception as exc:
                    logger.error(f"[LIVE] poll error: {exc}", exc_info=True)
                    self._ensure_connected()
                time.sleep(self.poll_seconds)
        except KeyboardInterrupt:
            logger.info("[STOP] engine stopped by user.")
        finally:
            try:
                self.gateway.shutdown()
                logger.info("[LIVE] MT5 disconnected")
            except Exception:
                pass
            self._running = False

    def stop(self):
        self._running = False

    def _ensure_connected(self):
        try:
            if not self.gateway._connected:
                logger.info("[LIVE] reconnecting to MT5...")
                self.gateway.connect()
                logger.info("[LIVE] MT5 reconnected")
        except Exception as exc:
            logger.error(f"[LIVE] reconnect failed: {exc}")

    # ------------------------------------------------------------------ #
    # Polling
    # ------------------------------------------------------------------ #

    def _poll_once(self):
        self._ensure_connected()
        if not self.gateway._connected:
            logger.warning("[LIVE] MT5 not connected — skipping this poll")
            return

        for symbol, tf_str, strat_id in self.portfolio:
            try:
                self._poll_combo(self.gateway, symbol, tf_str, strat_id)
            except Exception as exc:
                logger.error(
                    f"[LIVE] combo {symbol} {tf_str} {strat_id}: {exc}"
                )

    def _poll_combo(self, gw, symbol, tf_str, strat_id):
        tf = Timeframe(tf_str)
        strategy = self._strategies.get(strat_id)
        if strategy is None:
            return

        df_live = gw.get_rates(symbol, tf, count=300)
        if df_live is None or len(df_live) < 50:
            return

        df = df_live.iloc[:-1].copy()
        if len(df) < 50:
            return

        signals = strategy.generate_signals(df, symbol, tf_str)
        if not signals:
            return

        latest_ts = df.index[-1].to_pydatetime()
        combo_key = (symbol, tf_str, strat_id)

        for sig in signals:
            if sig.created_at != latest_ts:
                continue

            last_ts = self._last_processed.get(combo_key)
            if last_ts is not None and sig.created_at <= last_ts:
                continue

            if self._in_cooldown(symbol, sig.direction, tf_str):
                logger.info(
                    f"[COOLDOWN] {symbol} {sig.direction.value} {tf_str} "
                    f"(prev signal within {COOLDOWN_HOURS.get(tf_str, 4)}h)"
                )
                continue

            self._last_processed[combo_key] = sig.created_at

            logger.info(
                f"[SIGNAL] {sig.strategy_id} | {sig.symbol} "
                f"{sig.timeframe.value} | {sig.direction.value} @ "
                f"{sig.entry_price:.5f} | SL {sig.stop_loss:.5f} | "
                f"TP {sig.take_profit:.5f} | R:R {sig.reward_risk:.2f}"
            )

            # Persist signal
            self._persist_signal(sig)

            if not self.dry_run:
                # Chart annotator (currently no-ops due to MT5 API limits)
                try:
                    self.annotator.annotate_signal(sig)
                except Exception as exc:
                    logger.error(f"[LIVE] annotate failed: {exc}")

                # FIRE TRADE
                self._execute_trade(gw, sig)

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    def _execute_trade(self, gw, sig: Signal):
        """Calculate lot size and fire the order."""
        try:
            acc = gw.account_info()
            balance = acc["balance"]
            
            specs = gw.symbol_specs(sig.symbol)
            
            # Calculate exact lot size using the RiskManager
            volume = self.risk_manager.calculate_volume(balance, sig, specs)
            
            if volume <= 0:
                logger.warning(f"[EXEC] ❌ Trade rejected by RiskManager (volume={volume}) for {sig.symbol}")
                return

            # Check max open positions
            # (Simplified for now: just fire the trade)
            
            success = self.execution_engine.execute_signal(sig, volume)
            if not success:
                logger.error(f"[EXEC] ❌ Execution engine failed for {sig.symbol}")
                
        except Exception as exc:
            logger.error(f"[EXEC] ❌ Execution crashed: {exc}", exc_info=True)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _in_cooldown(self, symbol, direction, tf_str):
        hours = COOLDOWN_HOURS.get(tf_str, 4)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.db.connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) FROM signals
                   WHERE symbol = ? AND direction = ? AND created_at >= ?""",
                (symbol, direction.value, cutoff),
            ).fetchone()
            return row[0] > 0

    def _persist_signal(self, signal):
        try:
            with self.db.connection() as conn:
                conn.execute(
                    """INSERT INTO signals
                       (strategy_id, symbol, timeframe, direction,
                        entry_price, stop_loss, take_profit,
                        score, created_at, reasons_json, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        signal.strategy_id, signal.symbol,
                        signal.timeframe.value, signal.direction.value,
                        signal.entry_price, signal.stop_loss,
                        signal.take_profit, signal.score,
                        signal.created_at.isoformat(),
                        json.dumps(list(signal.reasons)),
                        json.dumps(signal.metadata),
                    ),
                )
            logger.info(
                f"[DB] saved {signal.strategy_id} "
                f"{signal.symbol} {signal.timeframe.value}"
            )
        except Exception as exc:
            logger.error(f"[DB] persist failed: {exc}")