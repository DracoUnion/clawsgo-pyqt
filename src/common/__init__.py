"""Common zero-Qt building blocks for the ClawsGO desktop shell.

This package never imports PySide6; it is importable headless so the
service and task layers stay testable without a display server. It sits
next to ``service`` / ``gui`` under ``src/`` (see pyproject src-layout).
"""

from common.events import EventHub
from common.context import AppContext

__all__ = ["EventHub", "AppContext"]