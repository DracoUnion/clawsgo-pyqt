"""Tickets view — support tickets with thread detail and replies."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import widgets as w
from ..workers import format_error
from ._base import PageView
from ._util import ask, browser, item


class TicketsView(PageView):
    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(facade, user, hub, parent)
        self._tickets: list = []
        self._selected: dict | None = None
        self._build()

    def _build(self) -> None:
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(w.h1("客服工单"), 1)
        create = w.primary_button("新建工单")
        create.clicked.connect(self._new)
        head.addWidget(create)
        refresh = w.ghost_button("刷新")
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh)
        self.body.addLayout(head)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.setSpacing(6)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_select)
        ll.addWidget(self._list)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.setSpacing(8)
        self._title = w.h2("选择一个工单")
        rl.addWidget(self._title)
        self._thread = browser()
        rl.addWidget(self._thread, 1)
        self._reply = QPlainTextEdit()
        self._reply.setPlaceholderText("回复内容…")
        self._reply.setMaximumHeight(96)
        rl.addWidget(self._reply)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._btn_reply = w.primary_button("回复")
        self._btn_reply.clicked.connect(self._send_reply)
        row.addStretch(1)
        row.addWidget(self._btn_reply)
        rl.addLayout(row)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([280, 640])
        self.body.addWidget(splitter, 1)

    # --------------------------------------------------------------- data
    def refresh(self) -> None:
        self.set_busy(True)
        self.call("getMyTickets", {}, self._on_tickets, self._on_error)

    def _on_tickets(self, payload) -> None:
        self.set_busy(False)
        self._tickets = (payload or {}).get("tickets") or []
        self._list.clear()
        for t in self._tickets:
            seen = "⚠" if (t.get("unreadCount") or 0) > 0 else " "
            label = (f"{seen} {t.get('subject')}  ·  {t.get('status')} · "
                     f"{t.get('priority')} · {t.get('seq')}")
            self._list.addItem(item(label, t))
        if self._tickets:
            self._list.setCurrentRow(0)
            self._on_select(self._list.item(0))

    def _on_select(self, it) -> None:
        t = it.data(Qt.ItemDataRole.UserRole)
        if not t:
            return
        self._selected = t
        tid = t.get("id")
        self.call("getTicket", {"id": tid}, self._on_detail, self._on_error)

    def _on_detail(self, payload) -> None:
        d = payload or {}
        t = d.get("ticket") or {}
        self._title.setText(f"{t.get('subject')}  [{t.get('status')}]")
        msgs = d.get("messages") or []
        html = []
        for m in msgs:
            who = "客服" if m.get("authorRole") == "admin" else "我"
            html.append(f"**{who}** · {str(m.get('createdAt') or '')[:19]}\n\n{m.get('body')}")
        self._thread.setMarkdown("\n\n---\n\n".join(html) or "_暂无消息_")
        if t.get("id"):
            self.call("markTicketSeen", {"id": t.get("id")}, lambda _p: self.refresh(),
                      self._soft_error)

    # ------------------------------------------------------------- actions
    def _new(self) -> None:
        values = ask(self, "新建工单", [
            ("subject", "标题", "text", ""),
            ("type", "类型", "combo", "general", ["general", "technical", "billing", "account"]),
            ("priority", "优先级", "combo", "normal", ["low", "normal", "high", "urgent"]),
            ("body", "内容", "multiline", ""),
        ])
        if values is None:
            return
        if not values.get("subject").strip() or not values.get("body").strip():
            self.notice("warn", "请填写标题与内容")
            return
        self.call("createTicket", values, lambda _p: self.refresh(), self._on_error)

    def _send_reply(self) -> None:
        if not self._selected:
            return
        body = self._reply.toPlainText().strip()
        if not body:
            return
        self._reply.clear()
        self.call("replyTicket", {"id": self._selected.get("id"), "body": body},
                  lambda _p: self._on_select(self._list.currentItem()), self._on_error)

    def _soft_error(self, exc) -> None:
        self.notice("warn", format_error(exc), sticky=False)

    def _on_error(self, exc) -> None:
        self.set_busy(False)
        self.notice("danger", format_error(exc))