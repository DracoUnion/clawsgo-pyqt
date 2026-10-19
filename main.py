"""Launch the ClawsGO PySide6 standalone desktop application."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from gui.app import launch


def main() -> int:
    app, _login, _holder = launch()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
