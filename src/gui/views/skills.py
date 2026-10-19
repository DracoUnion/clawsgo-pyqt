"""Skills view — team skill library with install / enable toggles and detail."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import widgets as w
from ..workers import format_error
from ._base import PageView
from ._util import browser, item


class SkillsView(PageView):
    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(facade, user, hub, parent)
        self._skills: list = []
        self._selected: dict | None = None
        self._build()

    # ------------------------------------------------------------------ ui
    def _build(self) -> None:
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(w.h1("技能库"), 1)
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索技能市场…")
        self._search.setMaximumWidth(240)
        self._search.returnPressed.connect(self._search_market)
        head.addWidget(self._search)
        search_btn = w.ghost_button("搜索市场")
        search_btn.clicked.connect(self._search_market)
        head.addWidget(search_btn)
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
        self._title = w.h2("选择一个技能")
        rl.addWidget(self._title)
        self._meta = w.muted("")
        self._meta.setWordWrap(True)
        rl.addWidget(self._meta)
        self._readme = browser()
        rl.addWidget(self._readme, 1)
        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        self._btn_install = w.primary_button("安装")
        self._btn_install.clicked.connect(lambda: self._act("installSkill"))
        self._btn_uninstall = w.ghost_button("卸载")
        self._btn_uninstall.clicked.connect(lambda: self._act("uninstallSkill"))
        self._btn_toggle = w.ghost_button("启用/禁用")
        self._btn_toggle.clicked.connect(self._toggle)
        self._actions.addStretch(1)
        self._actions.addWidget(self._btn_install)
        self._actions.addWidget(self._btn_uninstall)
        self._actions.addWidget(self._btn_toggle)
        rl.addLayout(self._actions)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([280, 640])
        self.body.addWidget(splitter, 1)

    # --------------------------------------------------------------- data
    def refresh(self) -> None:
        self.set_busy(True)
        self.call("getSkills", {}, self._on_skills, self._on_error)

    def _on_skills(self, payload) -> None:
        self.set_busy(False)
        data = payload or {}
        self._skills = data.get("skills") or []
        self._list.clear()
        for s in self._skills:
            state = []
            if s.get("installed"):
                state.append("已安装")
            if s.get("enabled"):
                state.append("已启用")
            label = f"{s.get('title') or s.get('name')}  v{s.get('version')}"
            if state:
                label += "  ·  " + " / ".join(state)
            self._list.addItem(item(label, s))
        if self._skills:
            self._list.setCurrentRow(0)
            self._on_select(self._list.item(0))
        else:
            self._render_skill(None)

    def _on_select(self, it) -> None:
        s = it.data(Qt.ItemDataRole.UserRole)
        if not s:
            return
        self._selected = s
        self._title.setText(s.get("title") or s.get("name") or "技能")
        self._meta.setText(
            f"{s.get('description') or ''}\n\n"
            f"版本 {s.get('version')} · 来源 {s.get('source')} · "
            f"{'已安装' if s.get('installed') else '未安装'} · "
            f"{'已启用' if s.get('enabled') else '已禁用'}")
        self._readme.setMarkdown(s.get("readme") or "_无说明_")
        self.call("getSkillDetail", {"slug": s.get("slug") or s.get("name")},
                  self._on_detail, self._on_error)

    def _on_detail(self, payload) -> None:
        d = (payload or {}).get("detail") or (payload or {}).get("skill")
        if d:
            self._readme.setMarkdown(d.get("readme") or "_无说明_")

    def _render_skill(self, s) -> None:
        self._title.setText("技能库为空" if s is None else (s.get("title") or s.get("name")))
        self._meta.setText("")
        self._readme.setMarkdown("")

    def _act(self, command: str) -> None:
        if not self._selected:
            return
        slug = self._selected.get("slug") or self._selected.get("name")
        self.call(command, {"slug": slug}, lambda _p: self.refresh(), self._on_error)

    def _toggle(self) -> None:
        if not self._selected:
            return
        slug = self._selected.get("slug") or self._selected.get("name")
        enabled = not bool(self._selected.get("enabled"))
        self.call("setSkillEnabled", {"slug": slug, "enabled": enabled},
                  lambda _p: self.refresh(), self._on_error)

    def _search_market(self) -> None:
        q = self._search.text().strip()
        self.call("searchSkillMarket", {"query": q}, self._on_market, self._on_error)

    def _on_market(self, payload) -> None:
        rows = (payload or {}).get("skills") or []
        if not self._search.text().strip():
            return
        self._list.clear()
        for s in rows:
            self._list.addItem(item(f"{s.get('title')} v{s.get('version')}  ·  市场", s))
        if rows:
            self._list.setCurrentRow(0)
            self._on_select(self._list.item(0))
        self.notice("info", f"市场搜索到 {len(rows)} 个技能")

    def _on_error(self, exc) -> None:
        self.set_busy(False)
        self.notice("danger", format_error(exc))
