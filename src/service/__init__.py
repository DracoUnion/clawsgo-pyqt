"""Embedded ClawsGO service used directly by the desktop shell.

The PySide6 application calls this service in-process. No HTTP server is
started and no HTTP client is used. State is persisted in SQLite via
SQLAlchemy (see :mod:`service.models`). The module remains importable
without Qt so the service can be smoke-tested headlessly.

There is no login step: the embedded backend boots straight into the default
admin identity (see :meth:`service.core.Backend._activate_admin`), so the
shell always runs with the same active profile.
"""
from __future__ import annotations

from .core import (
    Backend,
    BackendEphemeral,
    backend,
    command_names,
    dispatch,
)
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


def _default_backend():
    """Return the module-level singleton backend (compat default).

    ``bootstrap.build_context`` injects a fresh backend instead, which lets
    tests point it at a temp SQLite file without mutating the singleton.
    """
    from .core import backend

    return backend


class BackendError(Exception):
    """A backend failure with the shape expected by the GUI workers."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class ServiceFacade:
    """Thin in-process facade over the embedded service.

    The backend is injected by :func:`bootstrap.build_context`. When no
    backend is passed, the module-level singleton is used (kept for
    backward compatibility with scripts that import the facade directly).
    """

    name = "embedded"
    is_mock = False

    def __init__(self, backend=None) -> None:
        self._backend = backend if backend is not None else _default_backend()
        self._user: dict | None = None

    @property
    def backend_name(self) -> str:
        return self.name

    @property
    def user(self) -> dict | None:
        """The active (boot-time admin) profile, memoized on first access."""
        if self._user is None:
            try:
                self._user = self._backend.current_user()
            except Exception:
                self._user = {}
        return self._user

    def call(self, command: str, data: dict | None = None) -> dict:
        try:
            return self._backend.call(command, data)
        except ApiError as e:
            raise BackendError(e.code, e.message, e.status) from e

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
    "badRequest",
    "conflict",
    "fail",
    "forbidden",
    "need",
    "notFound",
    "req",
    "unauthorized",
]