"""View package for the ClawsGo desktop shell.

Each module exposes a ``*View`` widget; the main window stacks them under the
``Home`` tab. Views talk to the embedded service through a shared facade
(``service.ServiceFacade``) and stay responsive by delegating IO to
``gui.workers``.
"""

from __future__ import annotations

__all__ = [
    "HomeView",
    "ChatView",
    "SkillsView",
    "HostsView",
    "TeamsView",
    "BillingView",
    "TicketsView",
    "AdminView",
]

from .home import HomeView  # noqa: E402
from .chat import ChatView  # noqa: E402
from .skills import SkillsView  # noqa: E402
from .hosts import HostsView  # noqa: E402
from .teams import TeamsView  # noqa: E402
from .billing import BillingView  # noqa: E402
from .tickets import TicketsView  # noqa: E402
from .admin import AdminView  # noqa: E402
