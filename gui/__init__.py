"""ClawsGo desktop shell.

A PySide6-based desktop UI for the clawsgo app. The backend service is a
separate top-level package (``service``) called directly, in-process — no HTTP
server is started. The UI talks to it through a thin facade
(``service.ServiceFacade``).

Run it with:

    python main.py
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["run"]


def run(argv: list[str] | None = None) -> int:
    """Convenience entry point: build the app, show the login window, run."""
    from .app import build_app, show_login

    app, window = build_app(argv)
    show_login(window)
    return app.exec()
