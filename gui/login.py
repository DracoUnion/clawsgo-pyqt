"""Login window for the ClawsGo desktop shell.

Two auth modes mirror the web app:
* password  — ``POST /api/auth/sign-in/phone-number``
* OTP       — ``POST /api/auth/phone-number/send-otp`` then ``.../verify``

Demo credentials (from ``server/lib/seed.mjs``): phone ``13800000000``,
password ``clawsgo2026``; OTP is any 6 digits (dev code echoed back when the
backend runs with ``CLAWSGO_DEV_OTP=1``). Admin: ``13900000000`` / ``clawsgo2026``.

All backend IO happens off the GUI thread via ``gui.workers``.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import widgets as w
from service import DEMO_PASSWORD, DEMO_PHONE
from .workers import format_error, submit

_PHONE_RE = re.compile(r"^\d{5,15}$")


class LoginWindow(QDialog):
    """Full-window dialog shown first; emits :attr:`login_ok` on success."""

    login_ok = Signal(object)   # user dict from the backend envelope

    def __init__(self, facade, parent=None):
        super().__init__(parent)
        self._facade = facade
        self._otp_seconds = 0
        self._otp_dev_code: str | None = None
        self._otp_timer = QTimer(self)
        self._otp_timer.setInterval(1000)
        self._otp_timer.timeout.connect(self._otp_tick)
        self._pending: list = []

        self.setWindowTitle("ClawsGo 登录")
        self.resize(460, 560)
        self.setMinimumWidth(400)
        self._build()

    # ------------------------------------------------------------------ ui
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 36, 48, 32)
        root.setSpacing(14)
        root.addStretch(1)

        brand = w.h1("ClawsGo")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(brand)
        sub = w.muted("桌面端 · 会话 / 技能 / 主机 / 协作")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(sub)
        root.addSpacing(10)

        self._mode_tabs = QTabWidget()
        self._mode_tabs.setDocumentMode(True)
        self._mode_tabs.addTab(self._build_password_tab(), "密码登录")
        self._mode_tabs.addTab(self._build_otp_tab(), "验证码登录")
        root.addWidget(self._mode_tabs)

        self._error = w.error_label()
        root.addWidget(self._error)
        self._flash = w.flash_label()
        root.addWidget(self._flash)

        hint = w.faint("演示账号 13800000000 / 密码 clawsgo2026（管理员 13900000000）")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(hint)

        self._login_btn = w.primary_button("登 录")
        self._login_btn.setFixedHeight(40)
        self._login_btn.clicked.connect(self._on_login_clicked)
        root.addWidget(self._login_btn)

        backend_line = w.small(self._backend_hint())
        backend_line.setObjectName("faint")
        backend_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(backend_line)

        root.addStretch(2)

    def _backend_hint(self) -> str:
        base = getattr(self._facade, "_base_url", "")
        if self._facade.is_mock:
            return f"后端未连接（{base}），当前为内置演示数据"
        return f"已连接后端 · {self._facade.backend_name}"

    def _build_password_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 14, 6, 10)
        lay.setSpacing(12)

        self._phone_pw = QLineEdit()
        self._phone_pw.setPlaceholderText("手机号")
        self._phone_pw.setMaxLength(15)
        self._phone_pw.setText(DEMO_PHONE)
        lay.addWidget(w.field("手机号", self._phone_pw))

        pw_row = QWidget()
        pw_row_lay = QHBoxLayout(pw_row)
        pw_row_lay.setContentsMargins(0, 0, 0, 0)
        pw_row_lay.setSpacing(6)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("密码")
        self._password.setText(DEMO_PASSWORD)
        toggle = w.ghost_button("显示")
        toggle.setFixedWidth(52)
        toggle.clicked.connect(self._toggle_password_visibility)
        pw_row_lay.addWidget(self._password, 1)
        pw_row_lay.addWidget(toggle)
        lay.addWidget(w.field("密码", pw_row))
        return page

    def _build_otp_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 14, 6, 10)
        lay.setSpacing(12)

        self._phone_otp = QLineEdit()
        self._phone_otp.setPlaceholderText("手机号")
        self._phone_otp.setMaxLength(15)
        self._phone_otp.setText(DEMO_PHONE)
        lay.addWidget(w.field("手机号", self._phone_otp))

        otp_row = QWidget()
        otp_row_lay = QHBoxLayout(otp_row)
        otp_row_lay.setContentsMargins(0, 0, 0, 0)
        otp_row_lay.setSpacing(6)
        self._otp_code = QLineEdit()
        self._otp_code.setPlaceholderText("6 位验证码")
        self._otp_code.setMaxLength(6)
        self._send_otp_btn = w.primary_button("获取验证码")
        self._send_otp_btn.setFixedWidth(120)
        self._send_otp_btn.clicked.connect(self._on_send_otp)
        otp_row_lay.addWidget(self._otp_code, 1)
        otp_row_lay.addWidget(self._send_otp_btn)
        lay.addWidget(w.field("验证码", otp_row))
        return page

    def _toggle_password_visibility(self) -> None:
        visible = self._password.echoMode() == QLineEdit.EchoMode.Password
        self._password.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)

    # --------------------------------------------------------------- actions
    def _on_send_otp(self) -> None:
        phone = self._phone_otp.text().strip()
        if not _PHONE_RE.match(phone):
            self._show_error("请输入正确的手机号")
            return
        self._clear_flash()
        self._set_busy_send_otp(True)
        task = submit(self._facade.request_otp, self._on_otp_sent,
                      self._on_send_otp_failed, phone)
        self._pending.append(task)

    def _on_otp_sent(self, payload: object) -> None:
        self._set_busy_send_otp(False)
        data = payload or {}
        dev_code = data.get("devCode")
        self._otp_dev_code = str(dev_code) if dev_code else None
        if self._otp_dev_code:
            self._show_flash(f"演示验证码已发送：{self._otp_dev_code}", persist=True)
        self._start_otp_countdown(60)
        self._otp_code.setFocus()
        self._otp_code.clear()

    def _on_send_otp_failed(self, exc: object) -> None:
        self._set_busy_send_otp(False)
        self._show_error(format_error(exc))

    def _start_otp_countdown(self, seconds: int) -> None:
        self._otp_seconds = seconds
        self._send_otp_btn.setText(f"重新获取 ({seconds})")
        self._send_otp_btn.setEnabled(False)
        self._otp_timer.start()

    def _otp_tick(self) -> None:
        self._otp_seconds -= 1
        if self._otp_seconds <= 0:
            self._otp_timer.stop()
            self._send_otp_btn.setEnabled(True)
            self._send_otp_btn.setText("获取验证码")
        else:
            self._send_otp_btn.setText(f"重新获取 ({self._otp_seconds})")

    def _on_login_clicked(self) -> None:
        self._error.hide()
        self._set_login_busy(True)
        mode = self._mode_tabs.currentIndex()  # 0 = password, 1 = otp

        if mode == 1:
            phone = self._phone_otp.text().strip()
            code = self._otp_code.text().strip()
            fn = lambda: self._facade.login_otp(phone, code)  # noqa: E731
        else:
            phone = self._phone_pw.text().strip()
            password = self._password.text()
            fn = lambda: self._facade.login_password(phone, password)  # noqa: E731

        task = submit(fn, self._on_login_ok, self._on_login_failed)
        self._pending.append(task)

    def _on_login_ok(self, payload: object) -> None:
        self._set_login_busy(False)
        data = payload or {}
        user = data.get("user")
        if not user:
            self._show_error("登录成功但未返回用户信息")
            return
        self.login_ok.emit(user)

    def _on_login_failed(self, exc: object) -> None:
        self._set_login_busy(False)
        self._show_error(format_error(exc))

    # ------------------------------------------------------------- helpers
    def _show_error(self, text: str) -> None:
        self._flash.hide()
        self._error.setText(text)
        self._error.show()

    def _show_flash(self, text: str, persist: bool = False) -> None:
        self._error.hide()
        self._flash.setText(text)
        self._flash.show()
        if not persist:
            QTimer.singleShot(5000, self._flash.hide)

    def _clear_flash(self) -> None:
        self._flash.hide()

    def _set_login_busy(self, busy: bool) -> None:
        self._login_btn.setEnabled(not busy)
        self._login_btn.setText("登录中…" if busy else "登 录")
        self.setCursor(Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.ArrowCursor)

    def _set_busy_send_otp(self, busy: bool) -> None:
        self._send_otp_btn.setEnabled(not busy)
        self._send_otp_btn.setText("发送中…" if busy else "获取验证码")

    def closeEvent(self, event) -> None:  # noqa: D401 - Qt hook
        self._otp_timer.stop()
        super().closeEvent(event)