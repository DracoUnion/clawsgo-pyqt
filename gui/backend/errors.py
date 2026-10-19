"""错误语义 —— server/lib/errors.mjs 的移植。

统一信封：``{"error": {"code", "message"}}``，HTTP 状态由 ``ApiError.status`` 决定。
"""
from __future__ import annotations

from typing import Any, Optional


class ApiError(Exception):
    """带 code/message/status 的业务错误。"""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}

    def __repr__(self) -> str:  # pragma: no cover
        return f"ApiError({self.code!r}, {self.message!r}, {self.status})"


def fail(code: str, message: str, status: int = 400, **extra) -> ApiError:
    """构造（并可直接抛出）的业务错误。"""
    e = ApiError(code, message, status)
    e.extra = extra
    return e


def notFound(what: str = "资源", **extra) -> ApiError:
    e = ApiError("NOT_FOUND", f"{what}不存在", 404)
    e.extra = extra
    return e


def unauthorized(message: str = "未登录", **extra) -> ApiError:
    e = ApiError("UNAUTHORIZED", message, 401)
    e.extra = extra
    return e


def badRequest(message: str, code: str = "BAD_REQUEST", **extra) -> ApiError:
    e = ApiError(code, message, 400)
    e.extra = extra
    return e


def conflict(message: str, code: str = "CONFLICT", **extra) -> ApiError:
    e = ApiError(code, message, 409)
    e.extra = extra
    return e


def forbidden(message: str = "无权访问", **extra) -> ApiError:
    e = ApiError("FORBIDDEN", message, 403)
    e.extra = extra
    return e


def need(cond: bool, code: str, message: str, status: int = 400, **extra) -> None:
    """条件不满足即抛错。"""
    if not cond:
        raise ApiError(code, message, status)


def req(payload: Optional[dict], key: str, code: str = "BAD_REQUEST") -> Any:
    """取必填参数，缺失（None/空串/未定义）抛错。"""
    if not isinstance(payload, dict):
        raise ApiError(code, f"缺少参数 {key}", 400)
    v = payload.get(key)
    if v is None or v == "":
        raise ApiError(code, f"缺少参数 {key}", 400)
    return v
