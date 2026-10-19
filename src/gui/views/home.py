"""Home view — personal overview + quick actions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QListWidget, QWidget

from .. import widgets as w
from ._base import PageView


class HomeView(PageView):
    """Greeting + stat tiles + recent-conversation list."""

    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(facade, user, hub, parent)
        self._tiles: list[tuple[w.StatTile, str]] = []
        self._recent: list = []
        self._build()

    def _build(self) -> None:
        name = self.user.get("displayName") or self.user.get("name") or "同学"
        greeting = w.h1(f"你好，{name}")
        greeting.setWordWrap(True)
        self.body.addWidget(greeting)
        sub = w.muted("欢迎回来。选择一个入口开始今天的工作。")
        self.body.addWidget(sub)

        self._tiles_grid = QGridLayout()
        self._tiles_grid.setHorizontalSpacing(12)
        self._tiles_grid.setVerticalSpacing(12)
        self.body.addLayout(self._tiles_grid)
        self._make_tiles()
        self.body.addSpacing(6)

        # recent conversations header + refresh
        head = QHBoxLayout()
        head.setSpacing(8)
        title = w.h2("最近会话")
        head.addWidget(title, 1)
        refresh_btn = w.ghost_button("刷新")
        refresh_btn.clicked.connect(self.refresh)
        head.addWidget(refresh_btn, 0)
        self.body.addLayout(head)

        self._recent_list = QListWidget()
        self._recent_list.setMinimumHeight(200)
        self._recent_list.itemClicked.connect(self._on_recent_clicked)
        self.body.addWidget(self._recent_list, 1)

    def _make_tiles(self) -> None:
        specs = [
            ("套餐", "plan", "◇"),
            ("余额", "credits", "◈"),
            ("主机", "hosts", "▣"),
            ("会话", "conversations", "☰"),
            ("工单", "tickets", "⚑"),
            ("团队", "teams", "⬡"),
        ]
        for i, (label, key, icon) in enumerate(specs):
            tile = w.StatTile(label, "—", icon)
            self._tiles.append((tile, key))
            self._tiles_grid.addWidget(tile, i // 3, i % 3)

    # --------------------------------------------------------------- refresh
    def refresh(self) -> None:
        self.set_busy(True)
        self.call("getOverview", {}, self._on_overview, self._on_load_error)
        self.call("getConversations", {"limit": 6}, self._on_conversations,
                  self._on_load_error)

    def _on_overview(self, payload: object) -> None:
        self.set_busy(False)
        data = payload or {}
        ov = data.get("overview") or data
        mapping = {
            "plan": str(ov.get("plan") or data.get("plan") or "—"),
            "credits": str(ov.get("credits") or data.get("credits") or 0),
            "hosts": str(ov.get("hosts") or data.get("hosts") or 0),
            "conversations": str(ov.get("activeConversations")
                                  or data.get("conversations") or 0),
            "tickets": str(ov.get("tickets") or data.get("tickets") or 0),
            "teams": str(ov.get("teams") or data.get("teams") or 0),
        }
        for tile, key in self._tiles:
            tile.set_value(mapping.get(key, "—"))

    def _on_conversations(self, payload: object) -> None:
        data = payload or {}
        rows = data.get("conversations") or []
        self._recent = rows
        self._recent_list.clear()
        for c in rows:
            title = c.get("title") or "未命名会话"
            preview = c.get("lastMessagePreview") or ""
            when = (c.get("lastMessageAt") or c.get("updatedAt") or "")[:10]
            self._recent_list.addItem(
                f"{title}    ·    {preview[:42]}" + (f"    ·    {when}" if when else ""))

    def _on_load_error(self, exc: object) -> None:
        from ..workers import format_error

        self.set_busy(False)
        self.notice("danger", format_error(exc))

    def _on_recent_clicked(self, item) -> None:
        row = self._recent_list.row(item)
        if not (0 <= row < len(self._recent)):
            return
        conv = self._recent[row]
        if self.hub is not None:
            self.hub.conversations_changed.emit(conv)
        from ..main_window import MainWindow

        win = self.window()
        if isinstance(win, MainWindow):
            win.navigate("chat")