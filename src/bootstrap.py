"""
Application bootstrap for the ClawsGO desktop shell.

Assembles the zero-Qt service graph (Backend + EventHub + TaskManager +
ServiceFacade) into an ``AppContext`` and returns it. The GUI receives the
context and adapts task events into Qt signals; it never constructs services
itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from common.context import AppContext
from common.events import EventHub
from service import Backend, ServiceFacade
from tasks import TaskManager


def build_context(
    *,
    url: Optional[str] = None,
    max_workers: int = 4,
    extras: Optional[dict[str, Any]] = None,
) -> AppContext:
    """Assemble services and return an :class:`AppContext`.

    ``url`` may be overridden in tests to point the SQLAlchemy backend at a
    temp SQLite file; the default uses :data:`service.core.DATA`.
    """
    events = EventHub()
    tasks = TaskManager(max_workers=max_workers, events=events)
    backend = Backend(url=url) if url is not None else Backend()
    services = ServiceFacade(backend=backend)
    return AppContext(
        backend=backend,
        events=events,
        tasks=tasks,
        services=services,
        extras=extras or {},
    )