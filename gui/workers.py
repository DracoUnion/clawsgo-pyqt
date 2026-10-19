"""Threaded IO for the ClawsGo desktop shell.

Every backend call happens off the GUI thread so the UI never freezes.

Two patterns, both standard Qt and deliberately unmagical:

* ``FuncTask`` (``QThreadPool`` + ``QRunnable`` + signals) — one-shot calls
  (login, a single RPC).
* ``PollEventsWorker`` (a ``QThread`` whose ``run`` loops) — long-lived event
  polling for the Chat view, emitting each polled payload on ``progress``.
"""

from __future__ import annotations

import json
import time

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal, Slot

from service import BackendError


# --------------------------------------------------------------------------
# One-shot tasks
# --------------------------------------------------------------------------
class TaskSignals(QObject):
    done = Signal(object)     # result payload
    failed = Signal(object)   # exception (BackendError or anything else)


class FuncTask(QRunnable):
    """Run ``fn(*args, **kwargs)`` on the global thread pool."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = TaskSignals()

    @Slot()
    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as e:  # deliver every failure to the UI thread
            self.signals.failed.emit(e)
        else:
            self.signals.done.emit(result)


def submit(fn, on_done=None, on_error=None, *args, **kwargs) -> FuncTask:
    """Fire-and-forget ``fn`` on the pool; wire optional slots.

    Callers that need to cancel or observe multiple tasks should keep the
    returned :class:`FuncTask` (and its ``.signals``) alive themselves.
    """
    task = FuncTask(fn, *args, **kwargs)
    if on_done is not None:
        task.signals.done.connect(on_done)
    if on_error is not None:
        task.signals.failed.connect(on_error)
    QThreadPool.globalInstance().start(task)
    return task


class BackendCall:
    """Bound convenience for one backend RPC:

    ``BackendCall(facade, "getHosts").run(on_done=..., on_error=...)``
    """

    def __init__(self, facade, command: str, data: dict | None = None):
        self._facade = facade
        self._command = command
        self._data = data or {}
        self._task: FuncTask | None = None

    def run(self, on_done=None, on_error=None) -> "BackendCall":
        self._task = submit(self._call, on_done, on_error)
        return self

    def _call(self):
        return self._facade.call(self._command, self._data)


# --------------------------------------------------------------------------
# Long-lived polling
# --------------------------------------------------------------------------
class PollEventsWorker(QThread):
    """Polls ``getMessages`` for one conversation until stopped.

    Each polled payload is emitted via :attr:`progress` (queued to whatever
    thread the signal receiver lives on). :meth:`stop` sets a flag and waits
    for the loop to exit — safe to call from the GUI thread.
    """

    progress = Signal(object)
    finished_ok = Signal(object)

    def __init__(self, facade, conversation_id: str, interval_ms: int = 2500):
        super().__init__()
        self._facade = facade
        self._conversation_id = conversation_id
        self._interval = max(0.4, interval_ms / 1000.0)
        self._running = True

    def run(self):  # runs on the worker thread
        while self._running:
            try:
                payload = self._facade.call(
                    "getMessages", {"conversationId": self._conversation_id})
            except BackendError as e:
                payload = {"__error": e}
            except Exception as e:  # never kill the thread on a hiccup
                payload = {"__error": BackendError("POLL_ERROR", str(e), 500)}
            self.progress.emit(payload)
            if not self._running:
                break
            time.sleep(self._interval)
        self.finished_ok.emit(self._conversation_id)

    def stop(self) -> None:
        self._running = False
        self.wait(3000)


# --------------------------------------------------------------------------
# Event hub
# --------------------------------------------------------------------------
class EventHub(QObject):
    """Application-wide signals fed by background pollers.

    The Chat view owns a poller per open conversation and forwards payloads
    here so unrelated views (Home tiles, etc.) can refresh without reaching
    into each other.
    """

    messages_changed = Signal(object)          # {"messages": [...], "total": n}
    conversations_changed = Signal(object)
    domain_changed = Signal(str, object)       # ("tickets", {...}) etc.

    def __init__(self) -> None:
        super().__init__()
        self._pollers: dict[str, PollEventsWorker] = {}

    def start_polling(self, facade, conversation_id: str, interval_ms: int = 2500) -> None:
        self.stop_polling(conversation_id)
        worker = PollEventsWorker(facade, conversation_id, interval_ms)
        worker.progress.connect(self._on_poll_payload)
        worker.finished_ok.connect(self._forget_poller)
        self._pollers[conversation_id] = worker
        worker.start()

    def stop_polling(self, conversation_id: str) -> None:
        worker = self._pollers.pop(conversation_id, None)
        if worker is not None:
            worker.stop()

    @Slot(object)
    def _on_poll_payload(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        if "__error" in payload:
            self.domain_changed.emit("poll_error", payload["__error"])
            return
        self.messages_changed.emit(payload)

    @Slot(object)
    def _forget_poller(self, conversation_id: object) -> None:
        self._pollers.pop(str(conversation_id), None)

    def stop_all(self) -> None:
        for cid in list(self._pollers):
            self.stop_polling(cid)


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def format_error(exc: BaseException) -> str:
    if isinstance(exc, BackendError):
        if exc.status == 0:
            return f"无法连接后端：{exc.message}"
        if exc.code == "UNAUTHORIZED":
            return "登录已过期，请重新登录"
        return exc.message or exc.code
    return str(exc) or exc.__class__.__name__


def fmt_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        t = time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return iso
    return time.strftime("%m-%d %H:%M", t)


def extract_text_parts(parts) -> str:
    """Flatten message.parts into plain text."""
    if not parts:
        return ""
    chunks = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        t = p.get("type")
        if t == "text":
            chunks.append(str(p.get("text", "")))
        elif t == "structured":
            for block in p.get("blocks") or []:
                if isinstance(block, dict):
                    chunks.append(str(block.get("text", "")))
        elif t == "file":
            chunks.append("[文件] " + str(p.get("name", "")))
    return "\n".join(x for x in chunks if x)


def json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
