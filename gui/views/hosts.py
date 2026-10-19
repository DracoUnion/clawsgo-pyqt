"""Hosts view — cloud/SSH hosts with status, environment and storage detail."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import widgets as w
from ..workers import format_error
from ._base import PageView
from ._util import ask, browser, item


class HostsView(PageView):
    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(facade, user, hub, parent)
        self._hosts: list = []
        self._selected: dict | None = None
        self._env: dict | None = None
        self._storage: dict | None = None
        self._dirs: dict | None = None
        self._build()

    def _build(self) -> None:
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(w.h1("主机"), 1)
        create = w.primary_button("创建主机")
        create.clicked.connect(self._create)
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
        self._title = w.h2("选择一台主机")
        rl.addWidget(self._title)
        self._meta = w.muted("")
        self._meta.setWordWrap(True)
        rl.addWidget(self._meta)
        self._detail = browser()
        rl.addWidget(self._detail, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._btn_rebuild = w.ghost_button("重建")
        self._btn_rebuild.clicked.connect(lambda: self._act("rebuildHost"))
        self._btn_clean = w.ghost_button("清理缓存")
        self._btn_clean.clicked.connect(lambda: self._act("cleanHostCache"))
        self._btn_probe = w.ghost_button("探测 SSH")
        self._btn_probe.clicked.connect(lambda: self._act("probeSshServers"))
        self._btn_delete = w.primary_button("删除", danger=True)
        self._btn_delete.clicked.connect(self._delete)
        actions.addStretch(1)
        actions.addWidget(self._btn_rebuild)
        actions.addWidget(self._btn_clean)
        actions.addWidget(self._btn_probe)
        actions.addWidget(self._btn_delete)
        rl.addLayout(actions)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([280, 640])
        self.body.addWidget(splitter, 1)

    # --------------------------------------------------------------- data
    def refresh(self) -> None:
        self.set_busy(True)
        self.call("getHosts", {}, self._on_hosts, self._on_error)

    def _on_hosts(self, payload) -> None:
        self.set_busy(False)
        self._hosts = (payload or {}).get("hosts") or []
        self._list.clear()
        for h in self._hosts:
            label = f"{h.get('name')}  ·  {h.get('kind')}  ·  {h.get('status')}"
            self._list.addItem(item(label, h))
        if self._hosts:
            self._list.setCurrentRow(0)
            self._on_select(self._list.item(0))
        else:
            self._render(None)

    def _on_select(self, it) -> None:
        h = it.data(Qt.ItemDataRole.UserRole)
        if not h:
            return
        self._selected = h
        self._env = self._storage = self._dirs = None
        self._render(h)
        hid = h.get("id")
        self.call("getHostEnvironment", {"hostId": hid}, self._on_env, self._soft_error)
        self.call("getHostStorage", {"hostId": hid}, self._on_storage, self._soft_error)
        self.call("getHostDirectories", {"hostId": hid}, self._on_dirs, self._soft_error)

    def _render(self, h) -> None:
        if h is None:
            self._title.setText("暂无主机")
            self._meta.setText("")
            self._detail.setMarkdown("")
            return
        self._title.setText(h.get("name") or "主机")
        self._meta.setText(
            f"{h.get('kind')} · {h.get('status')} · "
            f"{'在线' if h.get('online') else '离线'} · "
            f"{h.get('specLabel') or '—'}\n\n"
            f"镜像 {h.get('image') or '—'} · 工作目录 {h.get('workdir') or '—'}")
        self._render_detail()

    def _render_detail(self) -> None:
        lines = []
        if self._env:
            lines.append("## 环境")
            lines.append(
                f"OS {self._env.get('os')} · kernel {self._env.get('kernel')} · "
                f"python {self._env.get('python')} · node {self._env.get('node')} · "
                f"git {self._env.get('git')}")
            if self._env.get("cuda"):
                lines.append(f"CUDA {self._env.get('cuda')}")
            pkgs = ", ".join(f"{p['name']} {p['version']}" for p in self._env.get("packages") or [])
            if pkgs:
                lines.append(f"包：{pkgs}")
        if self._storage:
            lines.append("\n## 存储")
            lines.append(
                f"已用 {self._storage.get('usedGb')} / {self._storage.get('totalGb')} GB · "
                f"缓存 {self._storage.get('cacheGb')} GB · 工作区 {self._storage.get('workdirGb')} GB")
        if self._dirs:
            lines.append("\n## 目录")
            if self._dirs.get("exists"):
                for e in self._dirs.get("entries") or []:
                    mark = "📁" if e.get("type") == "dir" else "📄"
                    lines.append(f"{mark} {e.get('path')}")
            else:
                lines.append("_路径不存在_")
        self._detail.setMarkdown("\n\n".join(lines) or "_无详情_")

    def _on_env(self, payload) -> None:
        self._env = (payload or {}).get("environment") or payload
        self._render_detail()

    def _on_storage(self, payload) -> None:
        self._storage = (payload or {}).get("storage") or payload
        self._render_detail()

    def _on_dirs(self, payload) -> None:
        self._dirs = payload or {}
        self._render_detail()

    # ------------------------------------------------------------- actions
    def _create(self) -> None:
        values = ask(self, "创建主机", [
            ("kind", "类型", "combo", "cloud", ["cloud", "ssh", "local"]),
            ("name", "名称", "text", ""),
            ("cpu", "CPU (核)", "int", 4),
            ("memoryGb", "内存 (GB)", "int", 8),
            ("diskGb", "磁盘 (GB)", "int", 100),
            ("gpu", "GPU", "text", ""),
            ("hostname", "SSH 主机名（仅 ssh）", "text", ""),
            ("port", "SSH 端口", "int", 22),
            ("username", "SSH 用户", "text", "root"),
        ])
        if values is None:
            return
        payload = {k: v for k, v in values.items() if v not in ("", 0)}
        if values.get("kind") != "ssh":
            for k in ("hostname", "port", "username"):
                payload.pop(k, None)
        self.call("createHost", payload, lambda _p: self.refresh(), self._on_error)

    def _delete(self) -> None:
        if not self._selected:
            return
        resp = QMessageBox.question(self, "删除主机", "确定删除这台主机？",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)
        if resp == QMessageBox.StandardButton.Yes:
            self.call("deleteHost", {"hostId": self._selected.get("id")},
                      lambda _p: self.refresh(), self._on_error)

    def _act(self, command) -> None:
        if not self._selected:
            return
        self.call(command, {"hostId": self._selected.get("id")},
                  lambda _p: self._on_select(self._list.currentItem()), self._on_error)

    def _soft_error(self, exc) -> None:
        self.notice("warn", format_error(exc), sticky=False)

    def _on_error(self, exc) -> None:
        self.set_busy(False)
        self.notice("danger", format_error(exc))
