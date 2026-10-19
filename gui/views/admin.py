"""Admin view — platform management (users, teams, orders, invoices, codes, tickets).

Visible only to admins; all operations go through the embedded backend.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import widgets as w
from ..workers import format_error
from ._base import PageView
from ._util import ask, item


class AdminView(PageView):
    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(facade, user, hub, parent)
        self._selected: dict = {}  # tab key -> row dict
        self._tabs: dict = {}
        self._build()

    def _build(self) -> None:
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(w.h1("管理后台"), 1)
        refresh = w.ghost_button("刷新")
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh)
        self.body.addLayout(head)

        self._stats = w.muted("")
        self.body.addWidget(self._stats)

        self._tabs_widget = QTabWidget()
        self._make_tabs()
        self.body.addWidget(self._tabs_widget, 1)

    def _make_tabs(self) -> None:
        for key, label, rows in [
            ("users", "用户", ["query", "role", "banned"]),
            ("teams", "团队", ["query"]),
            ("orders", "订单", ["status"]),
            ("invoices", "发票", ["status"]),
            ("codes", "兑换码", ["batch"]),
            ("tickets", "工单", ["status", "query"]),
        ]:
            tab = self._build_tab(key, label)
            self._tabs[key] = tab
            self._tabs_widget.addTab(tab._widget, label)

    def _build_tab(self, key, label):
        holder = _Tab()
        btn_labels = {
            "users": ["封号", "解封", "设为管理员", "设为用户", "充值额度", "授予套餐"],
            "teams": ["查看成员"],
            "orders": ["同步订单"],
            "invoices": ["开具", "驳回"],
            "codes": ["生成兑换码", "作废"],
            "tickets": ["回复", "关闭", "删除"],
        }
        for b in btn_labels.get(key, []):
            btn = w.ghost_button(b)
            btn.clicked.connect(lambda _=False, k=key, act=b: self._tab_action(k, act))
            holder._buttons.addWidget(btn)
        return holder

    # --------------------------------------------------------------- data
    def refresh(self) -> None:
        self.set_busy(True)
        self.call("getOverview", {}, self._on_stats, self._soft_error)
        idx = self._tabs_widget.currentIndex()
        key = ["users", "teams", "orders", "invoices", "codes", "tickets"][idx]
        self._load_tab(self._tabs[key], key)

    def _on_stats(self, payload) -> None:
        data = payload or {}
        ov = data.get("overview") or {}
        self.set_busy(False)
        self._stats.setText(
            f"用户 {data.get('users')} · 团队 {data.get('teams')} · 会话 {data.get('conversations')} · "
            f"主机 {data.get('hosts')} · 工单 {data.get('tickets')} · "
            f"运行 {data.get('runs')} · token {data.get('tokens')} · 收入 ¥{data.get('revenue')}")

    def _load_tab(self, tab, key) -> None:
        self.call(_admin_list_cmd(key), {}, lambda p: self._on_tab(tab, key, p),
                  self._on_error)

    def _on_tab(self, tab, key, payload) -> None:
        self.set_busy(False)
        d = payload or {}
        rows = (d.get(key) or d.get("items") or [])
        tab._list.clear()
        for r in rows:
            tab._list.addItem(item(_row_label(key, r), r))
        if rows:
            tab._list.setCurrentRow(0)
            self._selected[key] = rows[0]

    def _row_selected(self, key) -> dict | None:
        tab = self._tabs[key]
        it = tab._list.currentItem()
        if it:
            self._selected[key] = it.data(Qt.ItemDataRole.UserRole)
        return self._selected.get(key)

    # ------------------------------------------------------------- actions
    def _tab_action(self, key, act) -> None:
        row = self._row_selected(key)
        if key == "codes" and act == "生成兑换码":
            values = ask(self, "生成兑换码", [("count", "数量", "int", 1),
                                           ("credits", "额度", "int", 1000)])
            if values:
                self.call("adminCreateRedeemCodes", values, lambda _p: self._reload(key),
                          self._on_error)
            return
        if not row:
            self.notice("warn", "请先选择一行")
            return
        if key == "users":
            uid = row.get("userId") or row.get("id")
            if act in ("封号", "解封"):
                self.call("banUser" if act == "封号" else "unbanUser",
                          {"userId": uid, "reason": "管理员操作"},
                          lambda _p: self._reload(key), self._on_error)
            elif act in ("设为管理员", "设为用户"):
                self.call("setUserRole",
                          {"userId": uid, "role": "admin" if act == "设为管理员" else "user"},
                          lambda _p: self._reload(key), self._on_error)
            elif act == "充值额度":
                v = ask(self, "充值额度", [("credits", "额度", "int", 1000)])
                if v:
                    self.call("adminTopupCredits", {"userId": uid, "credits": v["credits"]},
                              lambda _p: self._reload(key), self._on_error)
            elif act == "授予套餐":
                v = ask(self, "授予套餐",
                        [("teamId", "团队ID", "text", row.get("id") or ""),
                         ("planId", "套餐", "combo", "pro", ["free", "plus", "pro", "ultra", "team", "enterprise"]),
                         ("months", "月数", "int", 1)])
                if v:
                    self.call("adminGrantPlan", v, lambda _p: self._reload(key), self._on_error)
        elif key == "tickets":
            tid = row.get("id")
            if act == "回复":
                v = ask(self, "回复工单", [("body", "内容", "multiline", "")])
                if v and v.get("body", "").strip():
                    self.call("adminReplyTicket", {"id": tid, "body": v["body"]},
                              lambda _p: self._reload(key), self._on_error)
            elif act == "关闭":
                self.call("adminCloseTicket", {"id": tid}, lambda _p: self._reload(key),
                          self._on_error)
            elif act == "删除":
                self.call("adminDeleteTicket", {"id": tid}, lambda _p: self._reload(key),
                          self._on_error)
        elif key == "invoices" and act in ("开具", "驳回"):
            iid = row.get("id")
            self.call("adminIssueInvoice" if act == "开具" else "adminRejectInvoice",
                      {"invoiceId": iid}, lambda _p: self._reload(key), self._on_error)
        elif key == "codes" and act == "作废":
            self.call("adminDisableRedeemCode", {"id": row.get("id")},
                      lambda _p: self._reload(key), self._on_error)
        elif key == "orders" and act == "同步订单":
            self.call("adminSyncPaymentOrder", {"orderId": row.get("id")},
                      lambda _p: self._reload(key), self._on_error)

    def _reload(self, key) -> None:
        self._load_tab(self._tabs[key], key)

    def _soft_error(self, exc) -> None:
        self.notice("warn", format_error(exc), sticky=False)

    def _on_error(self, exc) -> None:
        self.set_busy(False)
        self.notice("danger", format_error(exc))


def _admin_list_cmd(key) -> str:
    return {
        "users": "adminGetUsers",
        "teams": "adminGetTeams",
        "orders": "adminGetPaymentOrders",
        "invoices": "adminGetInvoices",
        "codes": "adminGetRedeemCodes",
        "tickets": "adminGetTickets",
    }[key]


def _row_label(key, r):
    r = r or {}
    if key == "users":
        return (f"{r.get('name')} · {r.get('phone')} · {r.get('role')} · "
                f"{'封禁' if r.get('banned') else '正常'} · {r.get('plan')}")
    if key == "teams":
        return f"{r.get('name')} · {r.get('plan')} · {r.get('memberCount')} 人 · {r.get('ownerName')}"
    if key == "orders":
        return (f"{r.get('orderNo')} · ¥{r.get('amountCents', 0) / 100:.2f} · "
                f"{r.get('status')} · {r.get('userName')}")
    if key == "invoices":
        return (f"¥{r.get('amount', 0) / 100:.2f} · {r.get('type')} · "
                f"{r.get('status')} · {r.get('invoiceNo') or '—'}")
    if key == "codes":
        return f"{r.get('code')} · {r.get('credits')} · {r.get('status')} · {r.get('batch') or '—'}"
    if key == "tickets":
        return f"{r.get('seq')} · {r.get('subject')} · {r.get('status')} · {r.get('priority')}"
    return str(r)


class _Tab:
    """A simple list + button row used inside the admin tab widget."""

    def __init__(self):
        self._widget = QWidget()
        lay = QVBoxLayout(self._widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._list = QListWidget()
        lay.addWidget(self._list, 1)
        self._buttons = QHBoxLayout()
        self._buttons.addStretch(1)
        lay.addLayout(self._buttons)