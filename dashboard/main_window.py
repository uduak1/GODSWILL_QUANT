"""GODSWILL main window — tabbed terminal with live settings editor and analytics."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import yaml

from PySide6.QtCore import QThread, QTimer, Qt, Signal as QtSignal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from configuration.settings import Settings, MT5Settings, resolve_config_path
from market_data.mt5_gateway import MT5Gateway
from database.connection import Database

logger = logging.getLogger("godswill.dashboard.main_window")


class MT5ConnectWorker(QThread):
    finished = QtSignal(bool, str)
    account_info = QtSignal(dict)

    def __init__(self, gateway: MT5Gateway):
        super().__init__()
        self.gateway = gateway

    def run(self):
        try:
            self.gateway.connect()
            acc = self.gateway.account_info()
            self.finished.emit(True, "MT5 connected")
            self.account_info.emit(acc)
        except Exception as e:
            self.finished.emit(False, f"MT5 error: {e}")


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, db: Database, db_version: int):
        super().__init__()
        self.settings = settings
        self.db = db
        self.db_version = db_version
        self.gateway = MT5Gateway(settings.mt5)
        self._worker = None
        self._charts_tab = None
        self._analytics_tab = None

        self.setWindowTitle(f"GODSWILL PRO TRADING TERMINAL  (DB v{db_version})")
        self.resize(1500, 900)

        self._build_ui()
        self._start_timer()

    # ------------------------------------------------------------------ #

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #1e1e1e; color: #00FF00;")
        header.setFixedHeight(50)
        h = QHBoxLayout(header)
        h.setContentsMargins(15, 0, 15, 0)

        title = QLabel("GODSWILL INSTITUTIONAL QUANT ENGINE")
        title.setStyleSheet("font-size: 18px; font-weight: bold; letter-spacing: 2px;")
        h.addWidget(title)
        h.addStretch()

        self.lbl_status = QLabel("DISCONNECTED")
        self.lbl_status.setStyleSheet("color: #EF5350; font-weight: bold; font-size: 12px;")
        h.addWidget(self.lbl_status)

        self.btn_connect = QPushButton("Connect MT5")
        self.btn_connect.clicked.connect(self._connect_mt5)
        h.addWidget(self.btn_connect)

        main_layout.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 0; background: #252525; }
            QTabBar::tab { background: #2b2b2b; color: #ccc;
                           padding: 8px 16px; font-weight: bold; }
            QTabBar::tab:selected { background: #3a3a3a; color: #00FF00; }
        """)
        main_layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_dashboard_tab(), "Dashboard")

        placeholder = QWidget()
        QVBoxLayout(placeholder).addWidget(QLabel("Click this tab to load charts (~5 sec)."))
        self.tabs.addTab(placeholder, "Charts")

        self.tabs.addTab(self._build_signals_tab(), "Signals")
        self.tabs.addTab(self._build_settings_tab(), "Settings")
        
        # NEW: Analytics tab
        self.tabs.addTab(self._build_analytics_tab(), "Analytics")

        self.tabs.currentChanged.connect(self._on_tab_change)

    def _build_dashboard_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(15, 15, 15, 15)

        self.lbl_account = QLabel("Not connected")
        self.lbl_account.setStyleSheet(
            "font-size: 14px; color: #00FF00; padding: 10px; "
            "background: #1e1e1e; border: 1px solid #333;"
        )
        v.addWidget(self.lbl_account)

        self.table = QTableWidget(13, 4)
        self.table.setHorizontalHeaderLabels(["Symbol", "TF", "Strategy", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        from research.validation import FROZEN_PORTFOLIO
        for i, (sym, tf, sid) in enumerate(FROZEN_PORTFOLIO):
            self.table.setItem(i, 0, QTableWidgetItem(sym))
            self.table.setItem(i, 1, QTableWidgetItem(tf))
            self.table.setItem(i, 2, QTableWidgetItem(sid))
            self.table.setItem(i, 3, QTableWidgetItem("Active"))

        v.addWidget(self.table)
        return w

    def _build_signals_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(15, 15, 15, 15)

        self.signals_table = QTableWidget(0, 5)
        self.signals_table.setHorizontalHeaderLabels(
            ["Time (UTC)", "Symbol", "TF", "Direction", "Strategy"]
        )
        self.signals_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        v.addWidget(self.signals_table)
        return w

    def _build_settings_tab(self):
        """Full editable settings panel with save to config.yaml."""
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 0; background: #252525; }")

        content = QWidget()
        content.setStyleSheet("background: #252525;")
        v = QVBoxLayout(content)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(15)

        # ---------- Application ----------
        grp_app = QGroupBox("Application")
        grp_app.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #00FF00; "
            "border: 1px solid #444; margin-top: 12px; padding-top: 12px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }"
        )
        form_app = QFormLayout()

        self.cb_environment = QComboBox()
        self.cb_environment.addItems(["demo", "backtest", "live"])
        self.cb_environment.setCurrentText(self.settings.app.environment)
        self.cb_environment.setToolTip(
            "demo = paper trade, live = real money. "
            "Live requires explicit confirmation in Phase 10."
        )
        form_app.addRow("Environment:", self.cb_environment)

        self.cb_log_level = QComboBox()
        self.cb_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.cb_log_level.setCurrentText(self.settings.app.log_level)
        form_app.addRow("Log level:", self.cb_log_level)

        grp_app.setLayout(form_app)
        v.addWidget(grp_app)

        # ---------- Risk Management ----------
        grp_risk = QGroupBox("Risk Management")
        grp_risk.setStyleSheet(grp_app.styleSheet())
        form_risk = QFormLayout()

        self.sp_risk_pct = QDoubleSpinBox()
        self.sp_risk_pct.setRange(0.10, 5.00)
        self.sp_risk_pct.setSingleStep(0.05)
        self.sp_risk_pct.setDecimals(2)
        self.sp_risk_pct.setSuffix(" %")
        self.sp_risk_pct.setValue(self.settings.risk.risk_per_trade_pct)
        form_risk.addRow("Risk per trade (% of balance):", self.sp_risk_pct)

        self.sp_fixed_risk = QDoubleSpinBox()
        self.sp_fixed_risk.setRange(0, 50000)
        self.sp_fixed_risk.setSingleStep(10)
        self.sp_fixed_risk.setDecimals(2)
        self.sp_fixed_risk.setPrefix("$ ")
        self.sp_fixed_risk.setSpecialValueText("$0 — use % instead")
        self.sp_fixed_risk.setValue(self.settings.risk.fixed_risk_amount or 0)
        form_risk.addRow("Fixed risk per trade:", self.sp_fixed_risk)

        self.sp_max_positions = QSpinBox()
        self.sp_max_positions.setRange(1, 20)
        self.sp_max_positions.setValue(self.settings.risk.max_open_positions)
        form_risk.addRow("Max open positions:", self.sp_max_positions)

        self.sp_max_daily = QDoubleSpinBox()
        self.sp_max_daily.setRange(0.5, 20.0)
        self.sp_max_daily.setSingleStep(0.5)
        self.sp_max_daily.setDecimals(2)
        self.sp_max_daily.setSuffix(" %")
        self.sp_max_daily.setValue(self.settings.risk.max_daily_loss_pct)
        form_risk.addRow("Max daily loss:", self.sp_max_daily)

        self.sp_max_weekly = QDoubleSpinBox()
        self.sp_max_weekly.setRange(1.0, 50.0)
        self.sp_max_weekly.setSingleStep(1.0)
        self.sp_max_weekly.setDecimals(2)
        self.sp_max_weekly.setSuffix(" %")
        self.sp_max_weekly.setValue(self.settings.risk.max_weekly_loss_pct)
        form_risk.addRow("Max weekly loss:", self.sp_max_weekly)

        self.sp_max_dd = QDoubleSpinBox()
        self.sp_max_dd.setRange(5.0, 50.0)
        self.sp_max_dd.setSingleStep(1.0)
        self.sp_max_dd.setDecimals(2)
        self.sp_max_dd.setSuffix(" %")
        self.sp_max_dd.setValue(self.settings.risk.max_drawdown_pct)
        form_risk.addRow("Max account drawdown:", self.sp_max_dd)

        self.sp_min_rr = QDoubleSpinBox()
        self.sp_min_rr.setRange(1.0, 5.0)
        self.sp_min_rr.setSingleStep(0.1)
        self.sp_min_rr.setDecimals(2)
        self.sp_min_rr.setValue(self.settings.risk.min_reward_risk)
        form_risk.addRow("Min reward:risk ratio:", self.sp_min_rr)

        grp_risk.setLayout(form_risk)
        v.addWidget(grp_risk)

        # ---------- MT5 Connection ----------
        grp_mt5 = QGroupBox("MT5 Connection")
        grp_mt5.setStyleSheet(grp_app.styleSheet())
        form_mt5 = QFormLayout()

        self.txt_terminal_path = QLineEdit()
        self.txt_terminal_path.setPlaceholderText("(auto-detect any installed MT5)")
        if self.settings.mt5.terminal_path:
            self.txt_terminal_path.setText(str(self.settings.mt5.terminal_path))
        form_mt5.addRow("Terminal path:", self.txt_terminal_path)

        self.txt_login = QLineEdit()
        self.txt_login.setPlaceholderText("(use currently logged-in account)")
        if self.settings.mt5.login:
            self.txt_login.setText(str(self.settings.mt5.login))
        form_mt5.addRow("Login:", self.txt_login)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText("(leave blank)")
        if self.settings.mt5.password:
            self.txt_password.setText(self.settings.mt5.password)
        form_mt5.addRow("Password:", self.txt_password)

        self.txt_server = QLineEdit()
        self.txt_server.setPlaceholderText("(e.g., ICMarketsSC-Demo)")
        if self.settings.mt5.server:
            self.txt_server.setText(self.settings.mt5.server)
        form_mt5.addRow("Server:", self.txt_server)

        grp_mt5.setLayout(form_mt5)
        v.addWidget(grp_mt5)

        # ---------- Action buttons ----------
        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setStyleSheet(
            "background: #0055FF; color: white; font-weight: bold; "
            "padding: 10px 24px; border-radius: 4px;"
        )
        self.btn_reload = QPushButton("Reload from Disk")
        self.btn_reload.setStyleSheet("padding: 10px 24px;")
        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.setStyleSheet("padding: 10px 24px; color: #FFA726;")

        btn_row.addWidget(self.btn_save)
        btn_row.addWidget(self.btn_reload)
        btn_row.addWidget(self.btn_reset)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self.lbl_settings_status = QLabel("")
        self.lbl_settings_status.setStyleSheet("color: #00FF00; font-size: 12px; padding: 10px;")
        self.lbl_settings_status.setWordWrap(True)
        v.addWidget(self.lbl_settings_status)

        # ---------- System info (read-only) ----------
        grp_info = QGroupBox("System Info (read-only)")
        grp_info.setStyleSheet(grp_app.styleSheet())
        form_info = QFormLayout()

        cfg_path = resolve_config_path()
        form_info.addRow("Active config:", QLabel(str(cfg_path) if cfg_path else "(none)"))
        form_info.addRow("Data dir:", QLabel(str(self.settings.app.data_dir)))
        form_info.addRow("DB path:", QLabel(str(self.settings.database.path)))
        form_info.addRow("Log file:", QLabel(str(self.settings.app.data_dir / "godswill.log")))

        grp_info.setLayout(form_info)
        v.addWidget(grp_info)

        v.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Wire buttons
        self.btn_save.clicked.connect(self._save_settings)
        self.btn_reload.clicked.connect(self._reload_settings)
        self.btn_reset.clicked.connect(self._reset_settings)

        return w

    def _build_analytics_tab(self):
        """Lazy-loaded analytics dashboard."""
        from dashboard.analytics_tab import AnalyticsTab
        return AnalyticsTab(self.gateway, self.settings)

    # ------------------------------------------------------------------ #
    # Settings save/reload
    # ------------------------------------------------------------------ #

    def _save_settings(self):
        """Write current form values to configuration/config.yaml."""
        try:
            cfg_path = Path("configuration/config.yaml")
            cfg_path.parent.mkdir(parents=True, exist_ok=True)

            data = {}
            if cfg_path.exists():
                try:
                    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    data = {}

            # App
            data.setdefault("app", {})
            data["app"]["name"] = self.settings.app.name
            data["app"]["environment"] = self.cb_environment.currentText()
            data["app"]["data_dir"] = str(self.settings.app.data_dir)
            data["app"]["log_level"] = self.cb_log_level.currentText()

            # Database
            data.setdefault("database", {})
            data["database"]["path"] = str(self.settings.database.path)

            # Risk
            data.setdefault("risk", {})
            data["risk"]["risk_per_trade_pct"] = float(self.sp_risk_pct.value())
            fixed = float(self.sp_fixed_risk.value())
            data["risk"]["fixed_risk_amount"] = fixed if fixed > 0 else None
            data["risk"]["max_open_positions"] = int(self.sp_max_positions.value())
            data["risk"]["max_daily_loss_pct"] = float(self.sp_max_daily.value())
            data["risk"]["max_weekly_loss_pct"] = float(self.sp_max_weekly.value())
            data["risk"]["max_drawdown_pct"] = float(self.sp_max_dd.value())
            data["risk"]["min_reward_risk"] = float(self.sp_min_rr.value())

            # MT5
            data.setdefault("mt5", {})
            tp = self.txt_terminal_path.text().strip()
            data["mt5"]["terminal_path"] = tp if tp else None
            lg = self.txt_login.text().strip()
            data["mt5"]["login"] = int(lg) if lg.isdigit() else None
            pw = self.txt_password.text().strip()
            data["mt5"]["password"] = pw if pw else None
            sv = self.txt_server.text().strip()
            data["mt5"]["server"] = sv if sv else None
            data["mt5"]["timeout_ms"] = self.settings.mt5.timeout_ms

            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)

            self.settings = Settings.load(cfg_path)

            ts = datetime.now().strftime("%H:%M:%S")
            self.lbl_settings_status.setText(
                f"[OK] Saved at {ts} to {cfg_path}. "
                f"Restart any running 'live' engine to pick up new risk settings."
            )
            self.lbl_settings_status.setStyleSheet("color: #00FF00; font-size: 12px; padding: 10px;")
        except Exception as exc:
            self.lbl_settings_status.setText(f"[ERROR] Save failed: {exc}")
            self.lbl_settings_status.setStyleSheet("color: #EF5350; font-size: 12px; padding: 10px;")
            logger.error(f"settings save failed: {exc}", exc_info=True)

    def _reload_settings(self):
        """Re-read config.yaml and refresh all form widgets."""
        try:
            cfg_path = resolve_config_path()
            new_settings = Settings.load(cfg_path)
            self.settings = new_settings

            self.cb_environment.setCurrentText(new_settings.app.environment)
            self.cb_log_level.setCurrentText(new_settings.app.log_level)

            self.sp_risk_pct.setValue(new_settings.risk.risk_per_trade_pct)
            self.sp_fixed_risk.setValue(new_settings.risk.fixed_risk_amount or 0)
            self.sp_max_positions.setValue(new_settings.risk.max_open_positions)
            self.sp_max_daily.setValue(new_settings.risk.max_daily_loss_pct)
            self.sp_max_weekly.setValue(new_settings.risk.max_weekly_loss_pct)
            self.sp_max_dd.setValue(new_settings.risk.max_drawdown_pct)
            self.sp_min_rr.setValue(new_settings.risk.min_reward_risk)

            self.txt_terminal_path.setText(str(new_settings.mt5.terminal_path or ""))
            self.txt_login.setText(str(new_settings.mt5.login or ""))
            self.txt_password.setText(new_settings.mt5.password or "")
            self.txt_server.setText(new_settings.mt5.server or "")

            self.lbl_settings_status.setText(f"[OK] Reloaded from {cfg_path}.")
            self.lbl_settings_status.setStyleSheet("color: #00FF00; font-size: 12px; padding: 10px;")
        except Exception as exc:
            self.lbl_settings_status.setText(f"[ERROR] Reload failed: {exc}")
            self.lbl_settings_status.setStyleSheet("color: #EF5350; font-size: 12px; padding: 10px;")

    def _reset_settings(self):
        """Reset form to safe defaults (does not save until you click Save)."""
        try:
            defaults = Settings()
            self.cb_environment.setCurrentText(defaults.app.environment)
            self.cb_log_level.setCurrentText(defaults.app.log_level)
            self.sp_risk_pct.setValue(defaults.risk.risk_per_trade_pct)
            self.sp_fixed_risk.setValue(defaults.risk.fixed_risk_amount or 0)
            self.sp_max_positions.setValue(defaults.risk.max_open_positions)
            self.sp_max_daily.setValue(defaults.risk.max_daily_loss_pct)
            self.sp_max_weekly.setValue(defaults.risk.max_weekly_loss_pct)
            self.sp_max_dd.setValue(defaults.risk.max_drawdown_pct)
            self.sp_min_rr.setValue(defaults.risk.min_reward_risk)
            self.txt_terminal_path.setText("")
            self.txt_login.setText("")
            self.txt_password.setText("")
            self.txt_server.setText("")
            self.lbl_settings_status.setText(
                "[INFO] Form reset to defaults. Click 'Save Settings' to persist."
            )
            self.lbl_settings_status.setStyleSheet("color: #FFA726; font-size: 12px; padding: 10px;")
        except Exception as exc:
            self.lbl_settings_status.setText(f"[ERROR] Reset failed: {exc}")

    # ------------------------------------------------------------------ #

    def _on_tab_change(self, idx: int):
        if idx == 1 and self._charts_tab is None:
            try:
                from dashboard.chart_widget import MultiChartWindow
                self._charts_tab = MultiChartWindow(self.gateway, self.db)
                self.tabs.removeTab(1)
                self.tabs.insertTab(1, self._charts_tab, "Charts")
                self.tabs.setCurrentIndex(1)
            except Exception as exc:
                logger.error(f"chart load failed: {exc}", exc_info=True)

    def _connect_mt5(self):
        self.lbl_status.setText("CONNECTING...")
        self.lbl_status.setStyleSheet("color: #FFA726; font-weight: bold;")
        self._worker = MT5ConnectWorker(self.gateway)
        self._worker.finished.connect(self._on_connected)
        self._worker.account_info.connect(self._on_account)
        self._worker.start()

    def _on_connected(self, ok: bool, msg: str):
        if ok:
            self.lbl_status.setText("CONNECTED")
            self.lbl_status.setStyleSheet("color: #00FF00; font-weight: bold;")
        else:
            self.lbl_status.setText("ERROR")
            self.lbl_status.setStyleSheet("color: #EF5350; font-weight: bold;")
            self.lbl_account.setText(msg)

    def _on_account(self, acc: dict):
        if acc:
            self.lbl_account.setText(
                f"Account: {acc['login']}  |  "
                f"Balance: ${acc['balance']:,.2f}  |  "
                f"Equity: ${acc['equity']:,.2f}  |  "
                f"Free Margin: ${acc['margin_free']:,.2f}  |  "
                f"Server: {acc['server']}"
            )

    def _start_timer(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh_signals)
        self._timer.start(10_000)

    def _refresh_signals(self):
        try:
            with self.db.connection() as conn:
                rows = conn.execute(
                    """SELECT created_at, symbol, timeframe, direction,
                              strategy_id
                       FROM signals ORDER BY created_at DESC LIMIT 100"""
                ).fetchall()
            self.signals_table.setRowCount(len(rows))
            for i, r in enumerate(rows):
                self.signals_table.setItem(i, 0, QTableWidgetItem(r[0][:19]))
                self.signals_table.setItem(i, 1, QTableWidgetItem(r[1]))
                self.signals_table.setItem(i, 2, QTableWidgetItem(r[2]))
                self.signals_table.setItem(i, 3, QTableWidgetItem(r[3]))
                self.signals_table.setItem(i, 4, QTableWidgetItem(r[4]))
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self.gateway.shutdown()
        except Exception:
            pass
        event.accept()