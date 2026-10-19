"""Teams view — team summary, members and pending invitations."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from .. import widgets as w
from ..workers import format_error
from ._base import PageView
from ._util import ask, item


class TeamsView(PageView):
    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(facade, user, hub, parent)
        self._teams: list = []
        self._team: dict | None = None
        self._members: list = []
        self._selected_member: dict | None = None
        self._build()

    def _build(self) -> None:
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(w.h1("团队与成员"), 1)
        invite = w.primary_button("邀请成员")
        invite.clicked.connect(self._invite)
        head.addWidget(invite)
        refresh = w.ghost_button("刷新")
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh)
        self.body.addLayout(head)

        self._team_label = w.h2("团队")
        self.body.addWidget(self._team_label)
        self._team_meta = w.muted("")
        self._team_meta.setWordWrap(True)
        self.body.addWidget(self._team_meta)

        row = QHBoxLayout()
        row.setSpacing(12)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        ll.addWidget(w.muted("成员"))
        self._members_list = QListWidget()
        self._members_list.itemClicked.connect(self._on_member)
        ll.addWidget(self._members_list, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._btn_remove = w.ghost_button("移除成员")
        self._btn_remove.clicked.connect(self._remove_member)
        self._btn_admin = w.ghost_button("设为管理员")
        self._btn_admin.clicked.connect(lambda: self._set_role("admin"))
        self._btn_member = w.ghost_button("设为成员")
        self._btn_member.clicked.connect(lambda: self._set_role("member"))
        actions.addStretch(1)
        actions.addWidget(self._btn_admin)
        actions.addWidget(self._btn_member)
        actions.addWidget(self._btn_remove)
        ll.addLayout(actions)
        row.addWidget(left, 1)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        rl.addWidget(w.muted("待处理邀请"))
        self._inv_list = QListWidget()
        rl.addWidget(self._inv_list, 1)
        row.addWidget(right, 1)

        self.body.addLayout(row, 1)

    # --------------------------------------------------------------- data
    def refresh(self) -> None:
        self.set_busy(True)
        self.call("getTeams", {}, self._on_teams, self._on_error)

    def _on_teams(self, payload) -> None:
        self.set_busy(False)
        self._teams = (payload or {}).get("teams") or []
        if not self._teams:
            self._team = None
            self._team_label.setText("暂无团队")
            self._team_meta.setText("")
            return
        self._team = self._teams[0]
        t = self._team
        self._team_label.setText(t.get("name") or "团队")
        self._team_meta.setText(
            f"套餐 {t.get('plan')} · 成员 {t.get('memberCount')}/{t.get('memberLimit')} · "
            f"额度 {t.get('creditBalance')} · 我的角色 {t.get('role')}")
        self._load_members()
        self._load_invitations()

    def _load_members(self) -> None:
        if not self._team:
            return
        self.call("getTeamMembers", {"teamId": self._team.get("id")},
                  self._on_members, self._on_error)

    def _on_members(self, payload) -> None:
        self._members = (payload or {}).get("members") or []
        self._members_list.clear()
        for m in self._members:
            label = f"{m.get('name')}  ·  {m.get('role')}  ·  {m.get('email') or m.get('phone') or ''}"
            self._members_list.addItem(item(label, m))

    def _load_invitations(self) -> None:
        if not self._team:
            return
        self.call("getTeamInvitations", {"teamId": self._team.get("id")},
                  self._on_invitations, self._soft_error)

    def _on_invitations(self, payload) -> None:
        rows = (payload or {}).get("invitations") or []
        self._inv_list.clear()
        for inv in rows:
            label = (f"{inv.get('phone') or inv.get('email') or inv.get('inviteeId') or '—'}"
                     f"  ·  {inv.get('role')}  ·  {inv.get('status')}")
            self._inv_list.addItem(item(label, inv))

    # ------------------------------------------------------------- actions
    def _on_member(self, it) -> None:
        self._selected_member = it.data(Qt.ItemDataRole.UserRole)

    def _invite(self) -> None:
        if not self._team:
            return
        values = ask(self, "邀请成员", [
            ("email", "邮箱", "text", ""),
            ("phone", "手机号", "text", ""),
            ("role", "角色", "combo", "member", ["member", "admin"]),
        ])
        if values is None:
            return
        payload = {"teamId": self._team.get("id"), "role": values.get("role")}
        if values.get("email"):
            payload["email"] = values["email"]
        if values.get("phone"):
            payload["phone"] = values["phone"]
        self.call("createTeamInvitation", payload, lambda _p: self._load_invitations(),
                  self._on_error)

    def _remove_member(self) -> None:
        if not (self._team and self._selected_member):
            return
        resp = QMessageBox.question(self, "移除成员", "确定移除该成员？",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)
        if resp == QMessageBox.StandardButton.Yes:
            self.call("removeTeamMember",
                      {"teamId": self._team.get("id"),
                       "userId": self._selected_member.get("userId")},
                      lambda _p: self._load_members(), self._on_error)

    def _set_role(self, role) -> None:
        if not (self._team and self._selected_member):
            return
        self.call("updateTeamMemberRole",
                  {"teamId": self._team.get("id"),
                   "userId": self._selected_member.get("userId"), "role": role},
                  lambda _p: self._load_members(), self._on_error)

    def _soft_error(self, exc) -> None:
        self.notice("warn", format_error(exc), sticky=False)

    def _on_error(self, exc) -> None:
        self.set_busy(False)
        self.notice("danger", format_error(exc))
