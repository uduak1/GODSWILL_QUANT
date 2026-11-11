"""Analytics tab — equity curve, drawdown chart, and strategy comparison."""
from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QThread, Qt, Signal as QtSignal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from market_data.mt5_gateway import MT5Gateway
from risk_management.engine import RiskManager
from backtesting.engine import Backtester

logger = logging.getLogger("godswill.dashboard.analytics_tab")

SPREADS = {
    "XAUUSD": 0.25, "XAGUSD": 0.03,
    "USOIL": 0.03, "UKOIL": 0.03,
    "EURUSD": 0.00015, "GBPUSD": 0.00015,
    "AUDUSD": 0.00015, "USDCHF": 0.00015,
    "USDCAD": 0.00015, "USDJPY": 0.015,
    "NZDUSD": 0.00015, "EURGBP": 0.00020,
    "#BTCUSD": 30.0, "#ETHUSD": 2.5,
    "GER40": 1.0,
}

COMMISSIONS = {
    "XAUUSD": 4.0, "XAGUSD": 4.0, "USOIL": 4.0, "UKOIL": 4.0,
    "EURUSD": 0.0, "GBPUSD": 0.0, "AUDUSD": 0.0, "USDCHF": 0.0,
    "USDCAD": 0.0, "USDJPY": 0.0, "NZDUSD": 0.0, "EURGBP": 0.0,
    "#BTCUSD": 8.0, "#ETHUSD": 6.0, "GER40": 4.0,
}

SLIPPAGE = {
    "XAUUSD": 1.0, "XAGUSD": 1.0, "USOIL": 1.5, "UKOIL": 1.5,
    "EURUSD": 0.5, "GBPUSD": 0.8, "AUDUSD": 0.8, "USDCHF": 0.8,
    "USDCAD": 0.8, "USDJPY": 0.8, "NZDUSD": 1.0, "EURGBP": 0.8,
    "#BTCUSD": 3.0, "#ETHUSD": 3.0, "GER40": 2.0,
}


class BacktestWorker(QThread):
    progress = QtSignal(int, int, str)
    finished = QtSignal(object)
    error = QtSignal(str)

    def __init__(self, gateway: MT5Gateway, portfolio, risk_config, candle_count: int = 3000):
        super().__init__()
        self.gateway = gateway
        self.portfolio = portfolio
        self.risk_config = risk_config
        self.candle_count = candle_count

    def run(self):
        try:
            from core.enums import Timeframe
            from strategies.s03_choch_reversal import CHOCHReversal
            from strategies.s05_supply_demand import SupplyDemand
            from strategies.s07_trend_continuation import TrendContinuation

            strategies = {
                "S03": CHOCHReversal(),
                "S05": SupplyDemand(),
                "S07": TrendContinuation(),
            }

            results = []
            total = len(self.portfolio)

            for i, (symbol, tf_str, strat_id) in enumerate(self.portfolio, 1):
                self.progress.emit(i, total, f"Backtesting {symbol} {tf_str} {strat_id}...")
                try:
                    tf = Timeframe(tf_str)
                    strategy = strategies.get(strat_id)
                    if strategy is None:
                        continue

                    specs = self.gateway.symbol_specs(symbol)
                    df = self.gateway.get_rates(symbol, tf, count=self.candle_count)
                    if df is None or len(df) < 100:
                        continue

                    spread = SPREADS.get(symbol, 0.0)
                    commission = COMMISSIONS.get(symbol, 2.0)
                    slippage = SLIPPAGE.get(symbol, 1.0)

                    rm = RiskManager(self.risk_config)
                    bt = Backtester(
                        strategy, rm,
                        initial_balance=10000.0,
                        spread_pips=spread,
                        commission_per_lot_roundtrip=commission,
                        slippage_ticks=slippage,
                    )
                    res = bt.run(df, symbol, specs, timeframe=tf.value)

                    results.append({
                        "symbol": symbol,
                        "timeframe": tf_str,
                        "strategy_id": strat_id,
                        "trades": res.total_trades,
                        "win_rate": (res.winning_trades / res.total_trades * 100)
                                    if res.total_trades > 0 else 0,
                        "profit_factor": res.profit_factor,
                        "max_dd": res.max_drawdown_pct,
                        "net_profit": res.final_balance - res.initial_balance,
                        "equity_curve": res.equity_curve,
                        "trade_dates": [t.exit_time for t in res.trades],
                        "trade_pnls": [t.pnl for t in res.trades],
                    })
                except Exception as exc:
                    logger.error(f"backtest failed {symbol} {tf_str} {strat_id}: {exc}")

            self.finished.emit({"results": results})
        except Exception as exc:
            logger.error(f"worker failed: {exc}", exc_info=True)
            self.error.emit(str(exc))


class AnalyticsTab(QWidget):
    def __init__(self, gateway: MT5Gateway, settings, parent=None):
        super().__init__(parent)
        self.gateway = gateway
        self.settings = settings
        self._worker: BacktestWorker | None = None
        self._results: list[dict] = []
        self._portfolio_equity: list[float] = []
        self._portfolio_dd: list[float] = []

        self._build_ui()

    def _build_ui(self):
        # Outer layout holds the scroll area
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 0; background: #252525; }")

        # Content widget inside the scroll area
        content = QWidget()
        content.setStyleSheet("background: #252525;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_run = QPushButton("Run Portfolio Backtest")
        self.btn_run.setStyleSheet(
            "background: #0055FF; color: white; font-weight: bold; "
            "padding: 8px 20px; border-radius: 4px;"
        )
        self.btn_run.clicked.connect(self._run_backtest)

        self.lbl_status = QLabel("Click 'Run Portfolio Backtest' to analyze all 13 combos.")
        self.lbl_status.setStyleSheet("color: #ccc; font-size: 12px; padding-left: 10px;")

        toolbar.addWidget(self.btn_run)
        toolbar.addWidget(self.lbl_status)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Stats cards row
        self.stats_row = QHBoxLayout()
        self.stat_widgets = {}
        for key, label in [
            ("net_profit", "Net Profit"), ("win_rate", "Win Rate"),
            ("profit_factor", "Profit Factor"), ("max_dd", "Max Drawdown"),
            ("total_trades", "Total Trades"), ("expectancy", "Expectancy/Trade"),
        ]:
            card = QWidget()
            card.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            
            val_lbl = QLabel("—")
            val_lbl.setStyleSheet("color: #00FF00; font-size: 20px; font-weight: bold;")
            val_lbl.setAlignment(Qt.AlignCenter)
            
            name_lbl = QLabel(label)
            name_lbl.setStyleSheet("color: #999; font-size: 10px;")
            name_lbl.setAlignment(Qt.AlignCenter)
            
            cl.addWidget(val_lbl)
            cl.addWidget(name_lbl)
            
            self.stats_row.addWidget(card)
            self.stat_widgets[key] = val_lbl
        
        layout.addLayout(self.stats_row)

        # Splitter for Charts vs Table (User can drag the divider)
        splitter = QSplitter(Qt.Vertical)

        # Charts row
        charts_widget = QWidget()
        charts_layout = QHBoxLayout(charts_widget)
        charts_layout.setContentsMargins(0, 0, 0, 0)

        eq_box = QVBoxLayout()
        eq_box.addWidget(QLabel("Portfolio Equity Curve", styleSheet="color: #00FF00; font-weight: bold;"))
        self.equity_plot = pg.PlotWidget()
        self.equity_plot.setBackground("#1e1e1e")
        self.equity_plot.showGrid(x=True, y=True, alpha=0.3)
        eq_box.addWidget(self.equity_plot)
        charts_layout.addLayout(eq_box, 2)

        dd_box = QVBoxLayout()
        dd_box.addWidget(QLabel("Drawdown %", styleSheet="color: #EF5350; font-weight: bold;"))
        self.dd_plot = pg.PlotWidget()
        self.dd_plot.setBackground("#1e1e1e")
        self.dd_plot.showGrid(x=True, y=True, alpha=0.3)
        dd_box.addWidget(self.dd_plot)
        charts_layout.addLayout(dd_box, 1)

        splitter.addWidget(charts_widget)

        # Strategy Table widget
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.setContentsMargins(0, 10, 0, 0)
        table_layout.addWidget(QLabel("Strategy Breakdown", styleSheet="color: #00FF00; font-weight: bold;"))

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "TF", "Strategy", "Trades", "Win %", "PF", "Max DD %", "Net P&L"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # Give the table a minimum height so it doesn't shrink to 0
        self.table.setMinimumHeight(250)
        table_layout.addWidget(self.table)

        splitter.addWidget(table_widget)
        
        # Set initial proportions (60% charts, 40% table)
        splitter.setSizes([500, 300])

        layout.addWidget(splitter)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _run_backtest(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self.btn_run.setEnabled(False)
        self.btn_run.setText("Running...")
        self.lbl_status.setText("Starting backtest...")

        from research.validation import FROZEN_PORTFOLIO
        self._worker = BacktestWorker(self.gateway, FROZEN_PORTFOLIO, self.settings.risk, candle_count=3000)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current, total, message):
        self.lbl_status.setText(f"[{current}/{total}] {message}")

    def _on_error(self, msg):
        self.btn_run.setEnabled(True)
        self.btn_run.setText("Run Portfolio Backtest")
        self.lbl_status.setText(f"[ERROR] {msg}")
        self.lbl_status.setStyleSheet("color: #EF5350; font-size: 12px;")

    def _on_finished(self, payload):
        self.btn_run.setEnabled(True)
        self.btn_run.setText("Re-run Backtest")
        self._results = payload["results"]

        if not self._results:
            self.lbl_status.setText("[ERROR] No results — check MT5 connection and symbols.")
            return

        self._compute_portfolio_curve()
        self._draw_charts()
        self._update_stats()
        self._update_table()

        self.lbl_status.setText(f"[OK] Analyzed {len(self._results)} combos on 3000 candles each.")
        self.lbl_status.setStyleSheet("color: #00FF00; font-size: 12px;")

    def _compute_portfolio_curve(self):
        all_trades = []
        for r in self._results:
            for date, pnl in zip(r["trade_dates"], r["trade_pnls"]):
                all_trades.append((date, pnl))
        all_trades.sort(key=lambda x: x[0])

        balance = 10000.0
        equity = [balance]
        for _, pnl in all_trades:
            balance += pnl
            equity.append(balance)
        self._portfolio_equity = equity

        peak = equity[0]
        dd_list = [0.0]
        for v in equity[1:]:
            if v > peak: peak = v
            dd = (peak - v) / peak * 100
            dd_list.append(dd)
        self._portfolio_dd = dd_list

    def _draw_charts(self):
        self.equity_plot.clear()
        eq = np.array(self._portfolio_equity)
        self.equity_plot.plot(np.arange(len(eq)), eq, pen=pg.mkPen("#00FF00", width=2),
                              fillLevel=10000, brush=QColor(0, 255, 0, 30))
        self.equity_plot.setXRange(0, max(len(eq) - 1, 1))

        self.dd_plot.clear()
        dd = np.array(self._portfolio_dd)
        self.dd_plot.plot(np.arange(len(dd)), -dd, pen=pg.mkPen("#EF5350", width=2),
                          fillLevel=0, brush=QColor(239, 83, 80, 50))
        self.dd_plot.setXRange(0, max(len(dd) - 1, 1))

    def _update_stats(self):
        final = self._portfolio_equity[-1]
        net = final - 10000.0
        total_trades = sum(r["trades"] for r in self._results)
        wins = sum(int(r["trades"] * r["win_rate"] / 100) for r in self._results)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        avg_pf = np.mean([r["profit_factor"] for r in self._results if r["profit_factor"] > 0])
        max_dd = max(self._portfolio_dd) if self._portfolio_dd else 0
        expectancy = net / total_trades if total_trades > 0 else 0

        def set_val(key, value, color="#00FF00"):
            self.stat_widgets[key].setText(value)
            self.stat_widgets[key].setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")

        set_val("net_profit", f"${net:+,.0f}", "#00FF00" if net > 0 else "#EF5350")
        set_val("win_rate", f"{win_rate:.1f}%")
        set_val("profit_factor", f"{avg_pf:.2f}")
        set_val("max_dd", f"{max_dd:.1f}%", "#EF5350" if max_dd > 20 else "#FFA726" if max_dd > 10 else "#00FF00")
        set_val("total_trades", str(total_trades))
        set_val("expectancy", f"${expectancy:+.2f}", "#00FF00" if expectancy > 0 else "#EF5350")

    def _update_table(self):
        results_sorted = sorted(self._results, key=lambda r: r["net_profit"], reverse=True)
        self.table.setRowCount(len(results_sorted))
        for i, r in enumerate(results_sorted):
            self.table.setItem(i, 0, QTableWidgetItem(r["symbol"]))
            self.table.setItem(i, 1, QTableWidgetItem(r["timeframe"]))
            self.table.setItem(i, 2, QTableWidgetItem(r["strategy_id"]))
            self.table.setItem(i, 3, QTableWidgetItem(str(r["trades"])))
            self.table.setItem(i, 4, QTableWidgetItem(f"{r['win_rate']:.1f}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{r['profit_factor']:.2f}"))
            self.table.setItem(i, 6, QTableWidgetItem(f"{r['max_dd']:.1f}"))
            
            pnl_item = QTableWidgetItem(f"${r['net_profit']:+,.0f}")
            pnl_item.setForeground(QColor("#00FF00") if r["net_profit"] > 0 else QColor("#EF5350"))
            self.table.setItem(i, 7, pnl_item)