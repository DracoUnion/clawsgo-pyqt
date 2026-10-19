"""Small shared helpers for the domain views (dialogs, list rendering)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QListWidgetItem,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import theme


def item(text: str, data=None) -> QListWidgetItem:
    it = QListWidgetItem(text)
    it.setData(Qt.ItemDataRole.UserRole, data)
    return it


def browser():
    """A read-only markdown-capable text browser with the app font."""
    from PySide6.QtWidgets import QTextBrowser

    b = QTextBrowser()
    b.setOpenExternalLinks(False)
    b.setObjectName("detailBrowser")
    b.setStyleSheet(
        f"QTextBrowser {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER};"
        f" border-radius: 8px; padding: 8px; color: {theme.TEXT}; }}")
    return b


def kv_lines(mapping: dict, keys=None) -> str:
    keys = keys or list(mapping.keys())
    lines = []
    for k in keys:
        v = mapping.get(k)
        if v is None or v == "" or v == [] or v == {}:
            continue
        lines.append(f"**{k}**：{v}")
    return "\n\n".join(lines)


class FormDialog(QDialog):
    """A tiny declarative form.

    ``fields`` is a list of ``(key, label, kind, default)`` where kind is one of
    ``text`` | ``int`` | ``combo`` | ``multiline`` | ``list`` (comma string).
    Combo values are passed as ``(default, [options])``.
    """

    def __init__(self, parent, title: str, fields, width: int = 420):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(width, 80 + 34 * len(fields))
        self._widgets = {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)
        for spec in fields:
            key, label, kind, default = spec[:4]
            options = spec[4] if len(spec) > 4 else []
            if kind == "int":
                wdg = QSpinBox()
                wdg.setRange(0, 10_000_000)
                if isinstance(default, int):
                    wdg.setValue(default)
            elif kind == "combo":
                wdg = QComboBox()
                wdg.addItems(options or [])
                if default in options:
                    wdg.setCurrentText(default)
            elif kind == "multiline":
                wdg = QPlainTextEdit()
                wdg.setPlainText(str(default or ""))
                wdg.setMinimumHeight(90)
            else:
                wdg = QLineEdit()
                wdg.setText(str(default or ""))
            self._widgets[key] = (wdg, kind)
            form.addRow(label, wdg)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def values(self) -> dict:
        out = {}
        for key, (wdg, kind) in self._widgets.items():
            if kind == "int":
                out[key] = int(wdg.value())
            elif kind == "combo":
                out[key] = wdg.currentText()
            elif kind == "multiline":
                out[key] = wdg.toPlainText()
            else:
                out[key] = wdg.text()
        return out


def ask(parent, title, fields, width=420):
    dlg = FormDialog(parent, title, fields, width)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.values()
    return None
