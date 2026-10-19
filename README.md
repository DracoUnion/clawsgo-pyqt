# ClawsGO Standalone Desktop

`clawsgo-pyqt` is a PySide6 desktop rewrite of the application surface. It intentionally does not copy the React production bundles in `app/assets/` or the marketing site in `site/`.

## Run

From the repository root:

```bash
python main.py
```

The application uses an embedded Python backend (merged into the `gui` package) and starts with seeded demo data. The PyQt app calls the service directly, in-process — no HTTP server is started. Demo accounts:

- User: `13800000000` / `clawsgo2026`
- Admin: `13900000000` / `clawsgo2026`

PySide6 6.x is required. The backend package is stdlib-only and can be smoke-tested without Qt:

```bash
python -m compileall -q gui
python -c "import sys; sys.path.insert(0, '.'); from gui.backend import Backend, command_names; b=Backend(); b.login_password('13800000000','clawsgo2026'); print(len(command_names()), b.call('getOverview'))"
```

Set `QT_QPA_PLATFORM=offscreen` for headless GUI smoke tests. Runtime state is created in `data/` and should not be committed.

## Architecture

- `gui/backend/` — the merged service. `core.py` provides the in-process command facade, demo seed data, auth, conversations, workspace-facing command results, and a shape-preserving fallback for the complete command registry from `contracts/commands.json` (266 names). `__init__.py` exposes the `ServiceFacade` used directly by the shell.
- `gui/` — the dark PySide6 shell, asynchronous worker helpers, login, overview and chat views. The UI is authored natively rather than reusing web assets.

The embedded backend is the migration seam for the remaining domain-by-domain ports. Unsupported desktop-only operations return explicit `available`/`ok` results instead of silently touching the marketing site or web bundles.
