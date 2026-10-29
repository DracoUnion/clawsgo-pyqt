"""
Application context (zero Qt).

``AppContext`` is assembled by :func:`bootstrap.build_context`. The GUI
receives it and adapts task events into Qt signals; services are never
constructed inside the GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from common.events import EventHub

if TYPE_CHECKING:
    from service import Backend, ServiceFacade
    from tasks import TaskManager


@dataclass
class AppContext:
    """Bundle of run-time services injected at bootstrap time."""

    backend: "Backend"
    events: EventHub
    tasks: "TaskManager"
    services: "ServiceFacade"
    extras: dict[str, Any] = field(default_factory=dict)

    def extra(self, key: str, default: Any = None) -> Any:
        return self.extras.get(key, default)