"""Billing view — subscription, plans, orders, invoices and redeem codes."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from .. import widgets as w
from ..workers import format_error
from ._base import PageView
from ._util import ask, item


class BillingView(PageView):
    def __init__(self, facade, user, hub=None, parent=None):
        super().__init__(facade, user, hub, parent)
        self._plans: list = []
        self._selected_plan: dict | None = None
        self._build()

    def _build(self) -> None:
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(w.h1("套餐与账单"), 1)
        self._redeem = QLineEdit()
        self._redeem.setPlaceholderText("输入兑换码…")
        self._redeem.setMaximumWidth(220)
        self._redeem.returnPressed.connect(self._redeem_code)
        head.addWidget(self._redeem)
        redeem_btn = w.ghost_button("兑换")
        redeem_btn.clicked.connect(self._redeem_code)
        head.addWidget(redeem_btn)
        refresh = w.ghost_button("刷新")
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh)
        self.body.addLayout(head)

        self._sub = w.h2("订阅")
        self.body.addWidget(self._sub)
        self._sub_meta = w.muted("")
        self._sub_meta.setWordWrap(True)
        self.body.addWidget(self._sub_meta)

        self._plans_list = QListWidget()
        self._plans_list.setMaximumHeight(180)
        self._plans_list.itemClicked.connect(self._on_plan)
        self.body.addWidget(self._plans_list)
        self._plan_meta = w.muted("")
        self._plan_meta.setWordWrap(True)
        self.body.addWidget(self._plan_meta)
        upgrade = w.primary_button("升级/续费（模拟下单）")
        upgrade.clicked.connect(self._upgrade)
        self.body.addWidget(upgrade)

        cols = QHBoxLayout()
        cols.setSpacing(12)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        ll.addWidget(w.muted("支付订单"))
        self._orders = QListWidget()
        ll.addWidget(self._orders, 1)
        cols.addWidget(left, 1)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        head2 = QHBoxLayout()
        head2.setSpacing(8)
        head2.addWidget(w.muted("发票"), 1)
        inv_btn = w.ghost_button("申请发票")
        inv_btn.clicked.connect(self._new_invoice)
        head2.addWidget(inv_btn)
        rl.addLayout(head2)
        self._invoices = QListWidget()
        rl.addWidget(self._invoices, 1)
        cols.addWidget(right, 1)

        self.body.addLayout(cols, 1)

    # --------------------------------------------------------------- data
    def refresh(self) -> None:
        self.set_busy(True)
        self.call("getSubscription", {}, self._on_sub, self._on_error)
        self.call("getPlans", {}, self._on_plans, self._on_error)
        self.call("getPaymentOrders", {}, self._on_orders, self._soft_error)
        self.call("getInvoices", {}, self._on_invoices, self._soft_error)

    def _on_sub(self, payload) -> None:
        self.set_busy(False)
        s = (payload or {}).get("subscription") or {}
        self._sub.setText(f"{s.get('planLabel') or s.get('plan')} 套餐")
        self._sub_meta.setText(
            f"额度 {s.get('creditBalance')} · 月额度 {s.get('monthlyCredits')} · "
            f"到期 {str(s.get('currentPeriodEnd') or '')[:10]} · "
            f"{'可开票' if s.get('canInvoice') else '不可开票'}")

    def _on_plans(self, payload) -> None:
        self._plans = (payload or {}).get("plans") or []
        self._plans_list.clear()
        for p in self._plans:
            label = (f"{p.get('label')}  ¥{p.get('monthlyCents', 0) / 100:.1f}/月 · "
                     f"额度 {p.get('monthlyCredits')} · {p.get('diskGb')}GB")
            self._plans_list.addItem(item(label, p))
        if self._plans:
            self._plans_list.setCurrentRow(0)
            self._on_plan(self._plans_list.item(0))

    def _on_plan(self, it) -> None:
        p = it.data(Qt.ItemDataRole.UserRole)
        self._selected_plan = p
        self._plan_meta.setText(
            f"{p.get('description') or p.get('highlight') or ''} · 模型：{len(p.get('models') or [])} 个")

    def _upgrade(self) -> None:
        if not self._selected_plan:
            return
        plan_id = self._selected_plan.get("planId")
        if not plan_id:
            return
        self.call("createPaymentOrder", {"kind": "plan", "planId": plan_id, "months": 1},
                  lambda _p: self.refresh(), self._on_error)

    def _on_orders(self, payload) -> None:
        rows = (payload or {}).get("orders") or []
        self._orders.clear()
        for o in rows:
            label = (f"{o.get('orderNo')}  ·  {o.get('kind')}/{o.get('planId') or '充值'} · "
                     f"¥{o.get('amountCents', 0) / 100:.2f} · {o.get('status')}")
            self._orders.addItem(item(label, o))

    def _on_invoices(self, payload) -> None:
        rows = (payload or {}).get("invoices") or []
        self._invoices.clear()
        for i in rows:
            label = (f"{i.get('invoiceNo') or '待开具'}  ·  ¥{i.get('amount', 0) / 100:.2f} · "
                     f"{i.get('type')} · {i.get('status')}")
            self._invoices.addItem(item(label, i))

    # ------------------------------------------------------------- actions
    def _redeem_code(self) -> None:
        code = self._redeem.text().strip()
        if not code:
            return
        self.call("redeemCode", {"code": code},
                  lambda p: (self._notice_redeem(p), self.refresh()), self._on_error)

    def _notice_redeem(self, payload) -> None:
        d = payload or {}
        self.notice("ok", f"兑换成功：+{d.get('credits')} 额度，当前余额 {d.get('balance')}")

    def _new_invoice(self) -> None:
        values = ask(self, "申请发票", [
            ("amount", "金额（元）", "int", 2990),
            ("title", "抬头", "text", "演示实验室"),
            ("taxNo", "税号", "text", ""),
            ("type", "类型", "combo", "normal", ["normal", "vat_special"]),
        ])
        if values is None:
            return
        payload = {"amount": values.get("amount", 0) * 100,
                   "title": values.get("title") or "",
                   "taxNo": values.get("taxNo") or "",
                   "type": values.get("type") or "normal"}
        self.call("createInvoice", payload, lambda _p: self.refresh(), self._on_error)

    def _soft_error(self, exc) -> None:
        self.notice("warn", format_error(exc), sticky=False)

    def _on_error(self, exc) -> None:
        self.set_busy(False)
        self.notice("danger", format_error(exc))
