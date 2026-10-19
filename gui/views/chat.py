"""Chat view — conversations, messages, composer.

Backend contract (mirrors ``server/api/chat.mjs``):

* ``getConversations`` → {"conversations": [...], "total"}
* ``getMessages``      → {"messages": [...], "total"}   (desc, page 0 = newest)
* ``sendMessage``      → {userMessage, assistantMessage, conversation}
* ``updateConversation`` / ``archiveConversation`` / ``deleteConversation``
"""

from __future__ import annotations

import datetime
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import theme, widgets as w
from ..workers import extract_text_parts, fmt_time, format_error
from ._base import PageView


class ChatView(PageView):
    """Two-pane chat: conversation list on the left, thread on the right."""

    conversation_opened = Signal(str)

    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(facade, user, hub, parent)
        self._conversations: list = []
        self._all_messages: dict[str, list] = {}
        self._current_id: str | None = None
        self._build()

    # ------------------------------------------------------------------ ui
    def _build(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ----- left: conversations -------------------------------------
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 8, 0)
        left_lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(6)
        title = w.h2("会话")
        head.addWidget(title, 1)
        new_btn = w.primary_button("新会话")
        new_btn.setFixedWidth(76)
        new_btn.clicked.connect(self._new_conversation)
        head.addWidget(new_btn)
        left_lay.addLayout(head)

        self._conv_search = QLineEdit()
        self._conv_search.setPlaceholderText("搜索会话…")
        self._conv_search.textChanged.connect(self._filter_conversations)
        left_lay.addWidget(self._conv_search)

        self._conv_list = QListWidget()
        self._conv_list.itemClicked.connect(self._on_conv_clicked)
        self._conv_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._conv_list.customContextMenuRequested.connect(self._conv_menu)
        left_lay.addWidget(self._conv_list, 1)

        # ----- right: thread --------------------------------------------
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(8, 0, 0, 0)
        right_lay.setSpacing(10)

        self._thread_title = w.h2("选择或新建一个会话")
        right_lay.addWidget(self._thread_title)

        self._thread_scroll = QScrollArea()
        self._thread_scroll.setWidgetResizable(True)
        self._thread_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._thread_container = QWidget()
        self._thread_lay = _ThreadLayout(self._thread_container)
        self._thread_lay.setContentsMargins(0, 0, 0, 0)
        self._thread_lay.setSpacing(6)
        self._thread_lay.addStretch(1)
        self._thread_scroll.setWidget(self._thread_container)
        right_lay.addWidget(self._thread_scroll, 1)

        composer = QWidget()
        comp_lay = QVBoxLayout(composer)
        comp_lay.setContentsMargins(0, 0, 0, 0)
        comp_lay.setSpacing(8)
        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("输入消息，Enter 发送（Ctrl+Enter 换行）")
        self._input.setMaximumHeight(110)
        self._input.setMinimumHeight(48)
        comp_lay.addWidget(self._input)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._send_btn = w.primary_button("发送")
        self._send_btn.setFixedWidth(96)
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._send)
        hint = w.faint("Enter 发送 · Ctrl+Enter 换行")
        row.addWidget(hint, 1)
        row.addWidget(self._send_btn)
        comp_lay.addLayout(row)
        right_lay.addWidget(composer)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([300, 700])
        self.body.addWidget(splitter, 1)

    # -------------------------------------------------------------- refresh
    def refresh(self) -> None:
        self.set_busy(True)
        self.call("getConversations", {"limit": 200}, self._on_conversations,
                  self._on_load_error)

    def _on_conversations(self, payload: object) -> None:
        self.set_busy(False)
        data = payload or {}
        rows = data.get("conversations") or []
        self._conversations = rows
        self._render_conv_list()
        if self._current_id is None and rows:
            self._open_conversation(rows[0]["id"])
        else:
            self._render_conv_list()

    def _render_conv_list(self) -> None:
        self._conv_list.clear()
        query = self._conv_search.text().strip().lower()
        selected = self._current_id
        for c in self._conversations:
            if query and query not in (c.get("title") or "").lower():
                continue
            title = c.get("title") or "未命名会话"
            preview = c.get("lastMessagePreview") or ""
            when = fmt_time(c.get("lastMessageAt") or c.get("updatedAt"))
            cid = c.get("id")
            item = QListWidgetItem(f"{title}\n{preview[:60]}\n{when}")
            item.setData(Qt.ItemDataRole.UserRole, cid)
            item.setToolTip(f"{title} · 更新于 {when}")
            if cid == selected:
                self._conv_list.setCurrentItem(item)
            self._conv_list.addItem(item)

    def _filter_conversations(self, _text: str) -> None:
        self._render_conv_list()

    def _on_conv_clicked(self, item) -> None:
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self._open_conversation(cid)

    def _conv_menu(self, pos) -> None:
        item = self._conv_list.itemAt(pos)
        if item is None:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        if not cid:
            return
        menu = QMenu(self)
        rename_action = menu.addAction("重命名")
        archive_action = menu.addAction("归档")
        delete_action = menu.addAction("删除会话")
        chosen = menu.exec(self._conv_list.mapToGlobal(pos))
        if chosen is rename_action:
            self._rename_conversation(cid)
        elif chosen is archive_action:
            self._archive_conversation(cid)
        elif chosen is delete_action:
            self._delete_conversation(cid)

    def _rename_conversation(self, cid: str) -> None:
        from PySide6.QtWidgets import QInputDialog

        conv = next((c for c in self._conversations if c.get("id") == cid), None)
        title = conv.get("title") if conv else ""
        new_title, ok = QInputDialog.getText(self, "重命名会话", "新标题：", text=title)
        if ok and new_title.strip():
            self.call("updateConversation", {"conversationId": cid,
                                             "title": new_title.strip()},
                      self.refresh, self._on_load_error)

    def _archive_conversation(self, cid: str) -> None:
        self.call("archiveConversation", {"conversationId": cid},
                  self.refresh, self._on_load_error)

    def _delete_conversation(self, cid: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        resp = QMessageBox.question(
            self, "删除会话", "确定删除这个会话？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if resp == QMessageBox.StandardButton.Yes:
            self.call("deleteConversation", {"conversationId": cid},
                      self._on_deleted, self._on_load_error)

    def _on_deleted(self, _payload: object) -> None:
        if self._current_id is not None:
            self._all_messages.pop(self._current_id, None)
        self._current_id = None
        self.refresh()

    # ------------------------------------------------------------- messages
    def _open_conversation(self, cid: str) -> None:
        self._current_id = cid
        self._send_btn.setEnabled(True)
        conv = next((c for c in self._conversations if c.get("id") == cid), None)
        self._thread_title.setText(conv.get("title") if conv else "会话")
        self._thread_title.setToolTip(cid)
        self.conversation_opened.emit(cid)

        if cid in self._all_messages:
            self._render_thread()
            return

        self._render_loading()
        self.call("getMessages", {"conversationId": cid}, self._on_messages,
                  self._on_load_error)

    def _on_messages(self, payload: object) -> None:
        data = payload or {}
        rows = data.get("messages") or []
        if self._current_id:
            self._all_messages[self._current_id] = rows
            self._render_thread()

    def _render_thread(self) -> None:
        if self._current_id is None:
            return
        rows = list(reversed(self._all_messages.get(self._current_id) or []))
        self._thread_lay.clear_thread()
        for m in rows:
            text = extract_text_parts(m.get("parts"))
            when = fmt_time(m.get("createdAt"))
            self._thread_lay.add_widget_bubble(text, m.get("role"), when)
        self._thread_lay.addStretch(1)
        self._scroll_to_bottom()

    def _render_loading(self) -> None:
        self._thread_lay.clear_thread()
        self._thread_lay.addWidget(w.muted("加载消息…"))
        self._thread_lay.addStretch(1)

    def _scroll_to_bottom(self) -> None:
        sb = self._thread_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # -------------------------------------------------------------- compose
    def _new_conversation(self) -> None:
        self._current_id = "c-" + uuid.uuid4().hex[:12]
        self._all_messages[self._current_id] = []
        self._thread_title.setText("新会话")
        self._send_btn.setEnabled(True)
        self._render_thread()
        self._input.setFocus()
        self.conversation_opened.emit(self._current_id)
        self._render_conv_list()

    def _send(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or not self._current_id:
            return
        self._input.clear()
        self._set_sending(True)
        cid = self._current_id

        optimistic = {
            "id": "um-" + uuid.uuid4().hex[:12], "role": "user",
            "parts": [{"type": "text", "text": text}],
            "createdAt": datetime.datetime.now().isoformat() + "Z",
            "streamId": None,
        }
        self._all_messages.setdefault(cid, []).append(optimistic)
        self._render_thread()

        payload = {
            "conversationId": cid,
            "text": text,
            "messageId": "um-" + uuid.uuid4().hex[:12],
            "assistantMessageId": "am-" + uuid.uuid4().hex[:12],
        }
        self.call("sendMessage", payload,
                  lambda _p: self._on_sent(cid),
                  lambda e: self._on_send_failed(cid, e))

    def _on_sent(self, cid: str) -> None:
        self._set_sending(False)
        self._refresh_messages(cid)

    def _on_send_failed(self, cid: str, exc: object) -> None:
        self._set_sending(False)
        self.notice("danger", format_error(exc))
        self._refresh_messages(cid)

    def _set_sending(self, busy: bool) -> None:
        self._send_btn.setEnabled(not busy)
        self._send_btn.setText("发送中…" if busy else "发送")
        self._input.setEnabled(not busy)

    def _refresh_messages(self, cid: str) -> None:
        self.call("getMessages", {"conversationId": cid}, self._on_messages,
                  self._on_load_error)

    # ------------------------------------------------------------ polling
    def on_show(self) -> None:
        if not self.page_ready:
            self.refresh()
            self.page_ready = True

    def start_polling(self, cid: str) -> None:
        if self.hub is not None:
            self.hub.start_polling(self.facade, cid)

    def stop_polling(self) -> None:
        if self.hub is not None and self._current_id:
            self.hub.stop_polling(self._current_id)

    def _on_load_error(self, exc: object) -> None:
        self.set_busy(False)
        self.notice("danger", format_error(exc))


# -- bubble rendering ------------------------------------------------------
def _bubble_widget(text: str, role: str, when: str) -> QWidget:
    bubble = QFrame()
    if role == "user":
        bubble.setStyleSheet(
            f"QFrame {{ background: {theme.ACCENT_SOFT}; border: 1px solid {theme.BORDER};"
            f" border-radius: 10px; }}")
    else:
        bubble.setStyleSheet(
            f"QFrame {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER};"
            f" border-radius: 10px; }}")
    lay = QVBoxLayout(bubble)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(4)
    body_label = QLabel(text)
    body_label.setWordWrap(True)
    body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lay.addWidget(body_label)
    if when:
        meta = w.faint(when)
        meta.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(meta)
    return bubble


class _ThreadLayout(QVBoxLayout):
    """A QVBoxLayout subclass so bubbles can be appended/cleared simply."""

    def clear_thread(self) -> None:
        while self.count():
            item = self.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_widget_bubble(self, text: str, role: str, when: str) -> None:
        # remove any trailing stretch before inserting a new bubble
        if self.count() and self.itemAt(self.count() - 1).spacerItem() is not None:
            self.removeItem(self.itemAt(self.count() - 1))
        self.addWidget(_bubble_widget(text, role, when))
        self.addStretch(1)