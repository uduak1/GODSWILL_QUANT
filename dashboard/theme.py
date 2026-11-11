"""Global dark theme stylesheet for GODSWILL desktop app."""
from __future__ import annotations

DARK_THEME_QSS = """
/* ---------- Global ---------- */
QWidget {
    background: #252525;
    color: #ddd;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 12px;
}

QMainWindow, QDialog {
    background: #1e1e1e;
}

/* ---------- Labels ---------- */
QLabel {
    background: transparent;
    color: #ddd;
}

/* ---------- Tabs ---------- */
QTabWidget::pane {
    border: 0;
    background: #252525;
}
QTabBar {
    background: #1e1e1e;
}
QTabBar::tab {
    background: #2b2b2b;
    color: #bbb;
    padding: 8px 16px;
    font-weight: bold;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #3a3a3a;
    color: #00FF00;
}
QTabBar::tab:hover {
    background: #333333;
    color: #fff;
}

/* ---------- Tables ---------- */
QTableWidget, QTableView {
    background: #1e1e1e;
    alternate-background-color: #262626;
    gridline-color: #333;
    color: #ddd;
    selection-background-color: #0055FF;
    selection-color: #fff;
    border: 1px solid #333;
}
QTableWidget::item, QTableView::item {
    background: #1e1e1e;
    color: #ddd;
    padding: 4px;
}
QTableWidget::item:alternate, QTableView::item:alternate {
    background: #262626;
}
QTableWidget::item:selected, QTableView::item:selected {
    background: #0055FF;
    color: #fff;
}

/* Table headers */
QHeaderView {
    background: #2a2a2a;
    color: #00FF00;
}
QHeaderView::section {
    background: #2a2a2a;
    color: #00FF00;
    padding: 6px;
    border: none;
    border-right: 1px solid #333;
    border-bottom: 1px solid #444;
    font-weight: bold;
}
QHeaderView::section:hover {
    background: #333333;
}

/* ---------- Buttons ---------- */
QPushButton {
    background: #2b2b2b;
    color: #ddd;
    border: 1px solid #444;
    padding: 6px 14px;
    border-radius: 4px;
}
QPushButton:hover {
    background: #333333;
    border-color: #666;
}
QPushButton:pressed {
    background: #1e1e1e;
}
QPushButton:disabled {
    color: #666;
    background: #222;
}

/* ---------- Inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background: #1e1e1e;
    color: #eee;
    border: 1px solid #444;
    border-radius: 3px;
    padding: 4px 6px;
    selection-background-color: #0055FF;
    selection-color: #fff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #0055FF;
}

/* ComboBox dropdown */
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background: #1e1e1e;
    color: #eee;
    selection-background-color: #0055FF;
    selection-color: #fff;
    border: 1px solid #444;
}

/* Spin box arrows */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: #333;
    border: 1px solid #444;
    width: 16px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: #444;
}

/* ---------- Group Boxes ---------- */
QGroupBox {
    background: #252525;
    color: #00FF00;
    border: 1px solid #444;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {
    background: #1e1e1e;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #555;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #666;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    background: #1e1e1e;
    height: 12px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #555;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #666;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* ---------- ScrollArea ---------- */
QScrollArea {
    background: #252525;
    border: 0;
}

/* ---------- Message Boxes ---------- */
QMessageBox {
    background: #252525;
    color: #ddd;
}
QMessageBox QLabel {
    color: #ddd;
}
"""


def apply_dark_theme(app):
    """Apply the dark stylesheet to a QApplication instance."""
    app.setStyleSheet(DARK_THEME_QSS)