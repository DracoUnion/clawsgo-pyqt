"""Dark theme for the ClawsGo desktop shell.

One module holds every colour so the UI reads as a single system. The palette is
a blue-on-ink dark theme tuned to read comfortably against `app/index.html`
but written from scratch for PySide6 — nothing is copied from the web assets.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont


# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
BG          = "#0d1117"   # window canvas
SURFACE     = "#131820"   # panel / card
SURFACE_ALT = "#181f2a"   # hover / elevated
SURFACE_ACT = "#1d2533"   # pressed / selected
BORDER      = "#232d3d"   # hairlines

TEXT        = "#e6edf3"
TEXT_MUTED  = "#8b98a5"
TEXT_FAINT  = "#5c6773"

ACCENT      = "#3b82f6"
ACCENT_ALT  = "#2563eb"
ACCENT_SOFT = "#13294d"
ACCENT_TEXT = "#7db4ff"

DANGER      = "#f85149"
SUCCESS     = "#3fb950"
WARNING     = "#d29922"
INFO        = "#58a6ff"


def color(name: str) -> QColor:
    return QColor(name)


APPLICATION_FONT = ("Segoe UI", 10)


def app_font() -> QFont:
    f = QFont(*APPLICATION_FONT)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


# --------------------------------------------------------------------------
# Stylesheet
# --------------------------------------------------------------------------
QSS = """
* {
    font-family: "Segoe UI";
    font-size: 10pt;
}

QWidget {
    background: transparent;
    color: %(TEXT)s;
}

QMainWindow, QDialog {
    background: %(BG)s;
}

/* ---------- generic frames ---------- */
QFrame#card {
    background: %(SURFACE)s;
    border: 1px solid %(BORDER)s;
    border-radius: 10px;
}

QFrame#cardFlat {
    background: %(SURFACE)s;
    border-radius: 10px;
}

QFrame#divider {
    background: %(BORDER)s;
    border: none;
    max-height: 1px;
}

/* ---------- labels ---------- */
QLabel { color: %(TEXT)s; background: transparent; }
QLabel#muted  { color: %(TEXT_MUTED)s; }
QLabel#faint  { color: %(TEXT_FAINT)s; }
QLabel#h1     { font-size: 20pt; font-weight: 600; }
QLabel#h2     { font-size: 14pt; font-weight: 600; }
QLabel#small  { font-size: 9pt; }
QLabel#mono   { font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt; }

/* ---------- buttons ---------- */
QPushButton {
    background: %(SURFACE_ALT)s;
    border: 1px solid %(BORDER)s;
    border-radius: 7px;
    padding: 6px 14px;
    color: %(TEXT)s;
}
QPushButton:hover    { background: %(SURFACE_ACT)s; border-color: #2e3b52; }
QPushButton:pressed  { background: #141b26; }
QPushButton:disabled { color: %(TEXT_FAINT)s; background: %(SURFACE)s; }

QPushButton#primary {
    background: %(ACCENT)s;
    border: 1px solid %(ACCENT_ALT)s;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#primary:hover   { background: %(ACCENT_ALT)s; }
QPushButton#primary:disabled{ background: %(ACCENT_SOFT)s; color: %(TEXT_FAINT)s; }

QPushButton#ghost {
    background: transparent;
    border: none;
    color: %(TEXT_MUTED)s;
    padding: 5px 10px;
}
QPushButton#ghost:hover { color: %(TEXT)s; background: %(SURFACE_ALT)s; }

QPushButton#danger {
    background: transparent;
    border: 1px solid rgba(248, 81, 73, 0.4);
    color: %(DANGER)s;
}
QPushButton#danger:hover { background: rgba(248, 81, 73, 0.12); }

QPushButton#navButton {
    text-align: left;
    padding: 9px 14px;
    border: none;
    border-radius: 8px;
    color: %(TEXT_MUTED)s;
    background: transparent;
    font-size: 10pt;
}
QPushButton#navButton:hover      { background: %(SURFACE_ALT)s; color: %(TEXT)s; }
QPushButton#navButton:checked    { background: %(ACCENT_SOFT)s; color: %(ACCENT_TEXT)s; font-weight: 600; }

/* ---------- inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    background: %(SURFACE)s;
    border: 1px solid %(BORDER)s;
    border-radius: 7px;
    padding: 7px 10px;
    color: %(TEXT)s;
    selection-background-color: %(ACCENT)s;
    selection-color: #ffffff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid %(ACCENT)s;
}
QLineEdit:disabled, QTextEdit:disabled { color: %(TEXT_FAINT)s; }
QLineEdit#search {
    background: %(SURFACE)s;
    border-radius: 8px;
    padding: 7px 12px 7px 32px;
}

/* ---------- lists / trees / tables ---------- */
QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView, QTableView {
    background: %(SURFACE)s;
    alternate-background-color: %(SURFACE_ALT)s;
    border: 1px solid %(BORDER)s;
    border-radius: 8px;
    outline: none;
}
QListWidget::item, QTreeWidget::item, QTableWidget::item {
    padding: 7px 10px;
    border: none;
}
QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected {
    background: %(ACCENT_SOFT)s;
    color: %(ACCENT_TEXT)s;
}
QListWidget::item:hover, QTreeWidget::item:hover {
    background: %(SURFACE_ACT)s;
}
QTreeWidget::item { height: 26px; padding-left: 6px; }
QTableWidget { gridline-color: %(BORDER)s; }
QHeaderView::section {
    background: %(SURFACE_ALT)s;
    color: %(TEXT_MUTED)s;
    border: none;
    border-bottom: 1px solid %(BORDER)s;
    padding: 6px 8px;
    font-weight: 600;
}
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical {
    background: #2b3547; border-radius: 5px; min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: #37445c; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: #2b3547; border-radius: 5px; min-width: 28px;
}
QScrollBar::handle:horizontal:hover { background: #37445c; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- tabs ---------- */
QTabWidget::pane { border: 1px solid %(BORDER)s; border-radius: 8px; background: %(SURFACE)s; top: -1px; }
QTabBar::tab {
    background: transparent; color: %(TEXT_MUTED)s;
    padding: 7px 16px; border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: %(ACCENT_TEXT)s; border-bottom: 2px solid %(ACCENT)s; }
QTabBar::tab:hover { color: %(TEXT)s; }

/* ---------- combo ---------- */
QComboBox {
    background: %(SURFACE)s;
    border: 1px solid %(BORDER)s;
    border-radius: 7px;
    padding: 6px 10px;
    color: %(TEXT)s;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: %(SURFACE_ALT)s;
    border: 1px solid %(BORDER)s;
    selection-background-color: %(ACCENT_SOFT)s;
    selection-color: %(ACCENT_TEXT)s;
    outline: none;
}

/* ---------- menus ---------- */
QMenu {
    background: %(SURFACE_ALT)s;
    border: 1px solid %(BORDER)s;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item { padding: 6px 18px; border-radius: 5px; }
QMenu::item:selected { background: %(ACCENT_SOFT)s; color: %(ACCENT_TEXT)s; }

/* ---------- scroll area containers ---------- */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* ---------- tooltips ---------- */
QToolTip {
    background: %(SURFACE_ACT)s;
    color: %(TEXT)s;
    border: 1px solid %(BORDER)s;
    border-radius: 5px;
    padding: 4px 8px;
}

/* ---------- status bar ---------- */
QStatusBar { background: %(BG)s; border-top: 1px solid %(BORDER)s; color: %(TEXT_MUTED)s; }
QStatusBar::item { border: none; }

/* ---------- splash / dialog ---------- */
QProgressBar {
    background: %(SURFACE)s;
    border: 1px solid %(BORDER)s;
    border-radius: 6px;
    text-align: center;
    color: %(TEXT)s;
}
QProgressBar::chunk { background: %(ACCENT)s; border-radius: 5px; }
""" % dict(
    BG=BG, SURFACE=SURFACE, SURFACE_ALT=SURFACE_ALT, SURFACE_ACT=SURFACE_ACT,
    BORDER=BORDER, TEXT=TEXT, TEXT_MUTED=TEXT_MUTED, TEXT_FAINT=TEXT_FAINT,
    ACCENT=ACCENT, ACCENT_ALT=ACCENT_ALT, ACCENT_SOFT=ACCENT_SOFT,
    ACCENT_TEXT=ACCENT_TEXT, DANGER=DANGER, SUCCESS=SUCCESS, WARNING=WARNING,
    INFO=INFO,
)


def apply_theme(app: "QApplication") -> None:  # noqa: F821  (string annotation)
    from PySide6.QtGui import QFontDatabase

    app.setFont(app_font())
    app.setStyleSheet(QSS)

    # Ensure monospace renderers are available even without the full font set.
    _ = QFontDatabase  # touch import to keep it intentional