"""Embedded ClawsGO service used directly by the desktop shell.

The PySide6 application calls this service in-process. No HTTP server is
started and no HTTP client is used. The module remains stdlib-only so the
service can be imported and smoke-tested without Qt.
"""
from __future__ import annotations

from .core import Backend, BackendEphemeral, backend, command_names, dispatch
from .errors import (
    ApiError,
    badRequest,
    conflict,
    fail,
    forbidden,
    need,
    notFound,
    req,
    unauthorized,
)

DEMO_PHONE = "13800000000"
DEMO_PASSWORD = "clawsgo2026"
ADMIN_PHONE = "13900000000"


class BackendError(Exception):
    """A backend failure with the shape expected by the GUI workers."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class ServiceFacade:
    """Thin in-process facade over the shared embedded service."""

    name = "embedded"
    is_mock = False

    def __init__(self) -> None:
        self._backend = backend
        self._user: dict | None = None

    @property
    def backend_name(self) -> str:
        return self.name

    @property
    def user(self) -> dict | None:
        return self._user

    def login_password(self, phone: str, password: str) -> dict:
        result = self._backend.login_password(phone, password)
        self._user = (result or {}).get("user")
        return result

    def request_otp(self, phone: str) -> dict:
        return self._backend.request_otp(phone)

    def login_otp(self, phone: str, code: str) -> dict:
        result = self._backend.login_otp(phone, code)
        self._user = (result or {}).get("user")
        return result

    def call(self, command: str, data: dict | None = None) -> dict:
        return self._backend.call(command, data)

    def close(self) -> None:
        """Keep the facade API compatible; the in-process service has no socket."""
        return None


def commandNames():
    return command_names()


__all__ = [
    "Backend",
    "BackendEphemeral",
    "BackendError",
    "ApiError",
    "ServiceFacade",
    "backend",
    "command_names",
    "commandNames",
    "dispatch",
    "DEMO_PHONE",
    "DEMO_PASSWORD",
    "ADMIN_PHONE",
    "badRequest",
    "conflict",
    "fail",
    "forbidden",
    "need",
    "notFound",
    "req",
    "unauthorized",
]
