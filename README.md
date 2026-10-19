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

PySide6 6.x is required. The service package is stdlib-only (plus SQLAlchemy) and can be smoke-tested without Qt:

```bash
python -m compileall -q gui service
python -c "import sys; sys.path.insert(0, '.'); from service import Backend, command_names; b=Backend(); b.login_password('13800000000','clawsgo2026'); print(len(command_names()), b.call('getOverview'))"
```

Set `QT_QPA_PLATFORM=offscreen` for headless GUI smoke tests. Runtime state is created in `data/` (a SQLite `backend.db`) and should not be committed.

## Architecture

- `service/` — the merged service. `core.py` provides the in-process command facade over a SQLAlchemy/SQLite store, demo seed data, auth, conversations, skills, hosts, teams, billing, tickets and admin, plus a shape-preserving fallback for the complete command registry from `contracts/commands.json` (266 names). `__init__.py` exposes `ServiceFacade` used directly by the shell.
- `gui/` — the dark PySide6 shell, asynchronous worker helpers, login, home/chat and six domain views (skills, hosts, teams, billing, tickets, admin). The UI is authored natively rather than reusing web assets.

The embedded backend is the migration seam for the remaining domain-by-domain ports. Unsupported desktop-only operations return explicit `available`/`ok` results instead of silently touching the marketing site or web bundles.
