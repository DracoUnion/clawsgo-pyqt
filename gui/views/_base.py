"""Base page widget shared by all stacked views."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from .. import widgets as w
from ..workers import BackendCall, format_error


class PageView(QWidget):
    """Common wiring for a stack page.

    * keeps a reference to the shared facade, user dict and event hub;
    * ``on_show()`` is invoked by the main window every time the view is
      selected, giving each page a natural refresh point;
    * ``call()`` runs one backend RPC off-thread with (optional) success and
      error slots.
    """

    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(parent)
        self.facade = facade
        self.user = user or {}
        self.hub = hub
        self._pending: list = []
        self._loading = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body = QVBoxLayout(self)
        body.setContentsMargins(24, 20, 24, 20)
        body.setSpacing(14)
        self.body = body

        self._status_caption = QLabel("")
        self._status_caption.setObjectName("faint")
        self._status_caption.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._status_caption.hide()

        self.page_ready = False

    # -- hooks --------------------------------------------------------------
    def on_show(self) -> None:
        """Refresh data when the page becomes current. Override in subclasses."""
        if not self.page_ready:
            self.refresh()
            self.page_ready = True
        else:
            self.refresh()

    def refresh(self) -> None:
        """Subclasses override; must be non-blocking."""

    # -- async helper --------------------------------------------------------
    def call(self, command: str, data: dict | None = None,
             on_done=None, on_error=None) -> BackendCall:
        """Run a backend RPC off-thread; slots receive (payload) / (exception)."""
        if on_error is None:
            on_error = self._default_error
        task = BackendCall(self.facade, command, data).run(on_done, on_error)
        self._pending.append(task)
        return task

    def _default_error(self, exc: object) -> None:
        self.set_busy(False)
        self.notice("danger", format_error(exc))

    # -- busy + notices --------------------------------------------------------
    def set_busy(self, busy: bool) -> None:
        self._loading = busy

    def notice(self, kind: str, text: str, *, sticky: bool = True) -> None:
        if not text:
            self._status_caption.hide()
            return
        self._status_caption.setStyleSheet(
            f"color: {kind_color(kind)}; font-size: 9pt;")
        self._status_caption.setText(text)
        self._status_caption.show()
        self._status_caption.setToolTip(text if sticky else "")
        if not sticky:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(6000, self._status_caption.hide)

    def clear_notice(self) -> None:
        self._status_caption.hide()


def kind_color(kind: str) -> str:
    from .. import theme

    return {
        "ok": theme.SUCCESS,
        "warn": theme.WARNING,
        "danger": theme.DANGER,
        "info": theme.INFO,
    }.get(kind, theme.TEXT_MUTED)


class SimpleListView(PageView):
    """A page that renders one list into a ``QListWidget`` with an ID map."""

    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(facade, user, hub, parent)
        self._widget: w.QListWidget | None = None  # type: ignore[attr-defined]
        self._items: list = []

    def map_item(self, index: int) -> dict | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None


def make_cols(widget) -> None:
    """Convenience for table-ish list widgets (kept for future use)."""
    widget.setAlternatingRowColors(True)
    widget.setWordWrap(False)