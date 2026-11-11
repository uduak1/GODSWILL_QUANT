"""Professional candlestick chart widget using PyQtGraph."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPicture
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
)

from core.enums import Timeframe
from market_data.mt5_gateway import MT5Gateway

logger = logging.getLogger("godswill.dashboard.chart_widget")

TIMEFRAME_OPTIONS = ["M5", "M15", "M30", "H1", "H4", "D1"]
COLOR_UP = "#26A69A"
COLOR_DOWN = "#EF5350"
COLOR_BG = "#1e1e1e"


class CandlestickItem(pg.GraphicsObject):
    """Renders OHLC candles efficiently using QPicture."""

    def __init__(self, data: pd.DataFrame):
        super().__init__()
        self.data = data
        self.picture: QPicture | None = None
        self._generate_picture()

    def _generate_picture(self):
        self.picture = QPicture()
        painter = QPainter(self.picture)

        w = 0.35

        for i, row in enumerate(self.data.itertuples()):
            open_, high, low, close = row.open, row.high, row.low, row.close
            is_up = close >= open_
            color = QColor(COLOR_UP) if is_up else QColor(COLOR_DOWN)

            # Cosmetic pen: width is always 1 device pixel regardless of zoom
            pen = QPen(color, 1)
            pen.setCosmetic(True)
            painter.setPen(pen)

            # Wick
            painter.drawLine(QPointF(i, low), QPointF(i, high))

            # Body (filled)
            body_top = max(open_, close)
            body_bot = min(open_, close)
            body_rect = QRectF(
                i - w, body_bot, w * 2, max(body_top - body_bot, 1e-9)
            )
            painter.fillRect(body_rect, color)

            # Outline (also cosmetic)
            painter.drawRect(body_rect)

        painter.end()

    def paint(self, painter, *args):
        if self.picture is not None:
            painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        if len(self.data) == 0:
            return QRectF()
        return QRectF(
            -1, self.data["low"].min(),
            len(self.data) + 2,
            self.data["high"].max() - self.data["low"].min(),
        )


class ChartWidget(QWidget):
    def __init__(self, gateway: MT5Gateway, db, symbol: str = "XAUUSD",
                 timeframe: str = "H1", parent=None):
        super().__init__(parent)
        self.gateway = gateway
        self.db = db
        self.symbol = symbol
        self.timeframe = timeframe
        self.candle_count = 300

        self._build_ui()
        self._refresh()

        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(30_000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        self.txt_symbol = QLineEdit(self.symbol)
        self.txt_symbol.setMaximumWidth(120)
        self.cb_timeframe = QComboBox()
        self.cb_timeframe.addItems(TIMEFRAME_OPTIONS)
        self.cb_timeframe.setCurrentText(self.timeframe)
        self.btn_refresh = QPushButton("Refresh")
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #ccc; font-size: 11px;")

        toolbar.addWidget(QLabel("Symbol:"))
        toolbar.addWidget(self.txt_symbol)
        toolbar.addWidget(QLabel("TF:"))
        toolbar.addWidget(self.cb_timeframe)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch()
        toolbar.addWidget(self.lbl_info)
        layout.addLayout(toolbar)

        self.plot = pg.PlotWidget()
        self.plot.setBackground(COLOR_BG)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setLabel("left", "Price")
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.hideAxis("bottom")

        # Crosshair
        self.vline = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("#888", width=1, style=Qt.DashLine),
        )
        self.hline = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen("#888", width=1, style=Qt.DashLine),
        )
        self.vline.setZValue(1000)
        self.hline.setZValue(1000)
        self.plot.addItem(self.vline, ignoreBounds=True)
        self.plot.addItem(self.hline, ignoreBounds=True)

        self._mouse_proxy = pg.SignalProxy(
            self.plot.scene().sigMouseMoved, rateLimit=60,
            slot=self._on_mouse_move,
        )

        layout.addWidget(self.plot)

        self.btn_refresh.clicked.connect(self._refresh)
        self.cb_timeframe.currentTextChanged.connect(self._on_tf_change)
        self.txt_symbol.returnPressed.connect(self._refresh)

    def _on_tf_change(self, new_tf: str):
        self.timeframe = new_tf
        self._refresh()

    def _on_mouse_move(self, evt):
        pos = evt[0]
        if self.plot.sceneBoundingRect().contains(pos):
            try:
                pt = self.plot.plotItem.vb.mapSceneToView(pos)
                self.vline.setPos(pt.x())
                self.hline.setPos(pt.y())
            except Exception:
                pass

    def _refresh(self):
        try:
            symbol = self.txt_symbol.text().strip().upper()
            self.timeframe = self.cb_timeframe.currentText()
            tf = Timeframe(self.timeframe)

            df = self.gateway.get_rates(symbol, tf, count=self.candle_count)
            if df is None or len(df) < 10:
                self.lbl_info.setText(f"No data for {symbol} {self.timeframe}")
                return

            self.symbol = symbol
            self._draw_candles(df)
            self._draw_signals(df)
            self._draw_sma_overlay(df)

            last = df.iloc[-1]
            self.lbl_info.setText(
                f"{symbol} {self.timeframe} | "
                f"O:{last['open']:.5f} H:{last['high']:.5f} "
                f"L:{last['low']:.5f} C:{last['close']:.5f} | "
                f"{len(df)} candles"
            )
        except Exception as exc:
            logger.error(f"refresh failed: {exc}", exc_info=True)
            self.lbl_info.setText(f"Error: {exc}")

    def _draw_candles(self, df: pd.DataFrame):
        self.plot.clear()

        # Re-add crosshair
        self.vline = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("#888", width=1, style=Qt.DashLine),
        )
        self.hline = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen("#888", width=1, style=Qt.DashLine),
        )
        self.vline.setZValue(1000)
        self.hline.setZValue(1000)
        self.plot.addItem(self.vline, ignoreBounds=True)
        self.plot.addItem(self.hline, ignoreBounds=True)

        candles = CandlestickItem(df.reset_index(drop=True))
        self.plot.addItem(candles)

        self.plot.setYRange(
            df["low"].min(), df["high"].max(), padding=0.02
        )
        self.plot.setXRange(0, len(df) - 1, padding=0.02)

    def _draw_signals(self, df: pd.DataFrame):
        try:
            from research.validation import FROZEN_PORTFOLIO

            matching = [
                sid for sym, tf_str, sid in FROZEN_PORTFOLIO
                if sym == self.symbol and tf_str == self.timeframe
            ]
            if not matching:
                return

            with self.db.connection() as conn:
                rows = conn.execute(
                    """SELECT strategy_id, direction, entry_price, created_at
                       FROM signals
                       WHERE symbol = ? AND timeframe = ?
                       ORDER BY created_at DESC LIMIT 200""",
                    (self.symbol, self.timeframe),
                ).fetchall()

            if not rows:
                return

            timestamp_to_index = {
                pd.Timestamp(ts): i for i, ts in enumerate(df.index)
            }

            long_x, long_y = [], []
            short_x, short_y = [], []
            price_range = df["high"].max() - df["low"].min()
            offset = price_range * 0.005

            for row in rows:
                try:
                    sig_time = pd.Timestamp(row["created_at"])
                    if sig_time.tzinfo is None:
                        sig_time = sig_time.tz_localize("UTC")

                    idx = timestamp_to_index.get(sig_time)
                    if idx is None:
                        nearest = None
                        min_delta = 7200
                        for ts, i in timestamp_to_index.items():
                            delta = abs((ts - sig_time).total_seconds())
                            if delta < min_delta:
                                min_delta = delta
                                nearest = i
                        idx = nearest
                    if idx is None:
                        continue

                    is_long = row["direction"] == "LONG"
                    candle_low = float(df.iloc[idx]["low"])
                    candle_high = float(df.iloc[idx]["high"])

                    if is_long:
                        long_x.append(idx)
                        long_y.append(candle_low - offset)
                    else:
                        short_x.append(idx)
                        short_y.append(candle_high + offset)
                except Exception:
                    continue

            if long_x:
                scatter = pg.ScatterPlotItem(
                    x=long_x, y=long_y, symbol="t1", size=16,
                    brush=QColor(COLOR_UP), pen=pg.mkPen("#000", width=1),
                )
                scatter.setZValue(500)
                self.plot.addItem(scatter)

            if short_x:
                scatter = pg.ScatterPlotItem(
                    x=short_x, y=short_y, symbol="t", size=16,
                    brush=QColor(COLOR_DOWN), pen=pg.mkPen("#000", width=1),
                )
                scatter.setZValue(500)
                self.plot.addItem(scatter)

        except Exception as exc:
            logger.debug(f"_draw_signals failed: {exc}")

    def _draw_sma_overlay(self, df: pd.DataFrame):
        if len(df) < 20:
            return
        sma = df["close"].rolling(20).mean().reset_index(drop=True)
        pen = pg.mkPen("#FFB74D", width=1, style=Qt.DashLine)
        line = self.plot.plot(
            range(len(sma)), sma.values, pen=pen, connect="finite"
        )
        if line is not None:
            line.setZValue(100)


class MultiChartWindow(QWidget):
    def __init__(self, gateway: MT5Gateway, db, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QTabWidget
        from research.validation import FROZEN_PORTFOLIO

        self.gateway = gateway
        self.db = db

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        seen = set()
        for symbol, tf, _sid in FROZEN_PORTFOLIO:
            key = (symbol, tf)
            if key in seen:
                continue
            seen.add(key)
            try:
                chart = ChartWidget(gateway, db, symbol, tf)
                tabs.addTab(chart, f"{symbol} {tf}")
            except Exception as exc:
                logger.error(f"chart build failed {symbol} {tf}: {exc}")
                err = QWidget()
                QVBoxLayout(err).addWidget(QLabel(f"Error: {exc}"))
                tabs.addTab(err, f"{symbol} {tf} (err)")

        layout.addWidget(tabs)