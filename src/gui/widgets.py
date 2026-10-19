"""Reusable widgets for the ClawsGo desktop shell.

Everything here is dependency-light — just PySide6 + the theme. View-specific
logic lives in ``gui/views``; this module keeps shared building blocks in one
place: cards, stat tiles, section headers, empty states, badges, and a small
form helper.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme


# --------------------------------------------------------------------------
# Cards & frames
# --------------------------------------------------------------------------
class Card(QFrame):
    """A rounded surface with a hairline border; the unit of the layout."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._body = QVBoxLayout(self)
        self._body.setContentsMargins(16, 14, 16, 14)
        self._body.setSpacing(8)

    def body(self) -> QVBoxLayout:
        return self._body

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self._body.addWidget(widget, stretch)


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("divider")
        self.setFixedHeight(1)


# --------------------------------------------------------------------------
# Labels
# --------------------------------------------------------------------------
def h1(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("h1")
    return lab


def h2(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("h2")
    return lab


def muted(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("muted")
    return lab


def faint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("faint")
    return lab


def small(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("small")
    return lab


def mono(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("mono")
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


# --------------------------------------------------------------------------
# Buttons
# --------------------------------------------------------------------------
def primary_button(text: str, *, danger: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("danger" if danger else "primary")
    return btn


def ghost_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("ghost")
    return btn


# --------------------------------------------------------------------------
# Section header (title + optional action on the right)
# --------------------------------------------------------------------------
class SectionHeader(QWidget):
    def __init__(self, title: str, action: QPushButton | None = None,
                 subtitle: str | None = None):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(2)
        title_label = h2(title)
        left.addWidget(title_label)
        if subtitle:
            left.addWidget(muted(subtitle))
        layout.addLayout(left, 1)

        if action is not None:
            layout.addWidget(action, 0, Qt.AlignmentFlag.AlignRight)


# --------------------------------------------------------------------------
# Stat tile
# --------------------------------------------------------------------------
class StatTile(Card):
    """A small value+label tile used on Home / Admin overviews."""

    def __init__(self, label: str, value: str = "—", icon: str = "•"):
        super().__init__()
        self._value_label = h2(value)
        self._value_label.setObjectName("h2")
        row = QHBoxLayout()
        row.setSpacing(8)
        icon_label = QLabel(icon)
        icon_label.setObjectName("faint")
        row.addWidget(icon_label)
        row.addWidget(self._value_label, 1)
        self._body.addLayout(row)
        self._body.addWidget(muted(label))

    def set_value(self, value: str) -> None:
        self._value_label.setText(str(value))


# --------------------------------------------------------------------------
# Badges
# --------------------------------------------------------------------------
class Badge(QLabel):
    COLORS = {
        "ok": theme.SUCCESS,
        "warn": theme.WARNING,
        "err": theme.DANGER,
        "info": theme.INFO,
    }

    def __init__(self, text: str, kind: str = "info"):
        super().__init__(text)
        self._kind = kind
        self.setObjectName("badge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(20)
        self.setMinimumWidth(46)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_style()

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self._apply_style()

    def _apply_style(self) -> None:
        color = self.COLORS.get(self._kind, theme.INFO)
        self.setStyleSheet(
            f"QLabel {{ background: rgba({int(color[1:3],16)},{int(color[3:5],16)},"
            f"{int(color[5:7],16)},0.14); color: {color}; border-radius: 6px;"
            f" padding: 1px 8px; font-size: 9pt; }}")


def status_badge(status: str | None) -> Badge:
    """Map common backend status strings onto badge kinds."""
    s = (status or "").lower()
    if s in ("running", "online", "active", "paid", "open", "ok", "resolved", "done"):
        return Badge(s, "ok")
    if s in ("pending", "processing", "queued", "awaiting", "verifying"):
        return Badge(s, "warn")
    if s in ("stopped", "offline", "banned", "closed", "failed", "error", "refunded"):
        return Badge(s, "err")
    return Badge(s or "—", "info")


# --------------------------------------------------------------------------
# Empty state
# --------------------------------------------------------------------------
class EmptyState(Card):
    def __init__(self, title: str, hint: str | None = None,
                 icon: str = "◌", action: QPushButton | None = None):
        super().__init__()
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label = QLabel(icon)
        icon_label.setObjectName("h1")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.addWidget(icon_label)
        title_label = h2(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.addWidget(title_label)
        if hint:
            hint_label = muted(hint)
            hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint_label.setWordWrap(True)
            self._body.addWidget(hint_label)
        if action:
            self._body.addWidget(action, 0, Qt.AlignmentFlag.AlignCenter)


# --------------------------------------------------------------------------
# Simple form (label on top, widget below)
# --------------------------------------------------------------------------
def field(label_text: str, widget: QWidget) -> QWidget:
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)
    lab = small(label_text)
    lab.setObjectName("faint")
    lay.addWidget(lab)
    lay.addWidget(widget)
    return wrap


def grid_rows(rows: list[tuple[QLabel, QWidget]]) -> QGridLayout:
    """2-column label/value grid, labels right-aligned and muted."""
    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(6)
    for i, (label, widget) in enumerate(rows):
        lab = QLabel(label)
        lab.setObjectName("muted")
        lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(lab, i, 0)
        grid.addWidget(widget, i, 1)
    grid.setColumnStretch(1, 1)
    return grid


def error_label() -> QLabel:
    lab = QLabel("")
    lab.setObjectName("errorText")
    lab.setStyleSheet(
        f"QLabel#errorText {{ color: {theme.DANGER}; font-size: 9pt; }}")
    lab.setWordWrap(True)
    lab.hide()
    return lab


def flash_label() -> QLabel:
    lab = QLabel("")
    lab.setObjectName("flash")
    lab.setStyleSheet(
        f"QLabel#flash {{ color: {theme.SUCCESS}; font-size: 9pt; }}")
    lab.setWordWrap(True)
    lab.hide()
    return lab
