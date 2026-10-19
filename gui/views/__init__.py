"""View package for the ClawsGo desktop shell.

Each module exposes a ``*View`` widget; the main window stacks them under the
``Home`` tab. Views talk to the embedded service through a shared facade
(``gui.backend.ServiceFacade``) and stay responsive by delegating IO to
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
