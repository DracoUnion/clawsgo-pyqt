# ClawsGO Standalone Desktop

`clawsgo-pyqt` is a PySide6 desktop rewrite of the application surface. It intentionally does not copy the React production bundles in `app/assets/` or the marketing site in `site/`.

## Run

From the repository root:

```bash
python src/main.py
```

The application uses an embedded Python backend (merged into the `gui` package) and starts with seeded demo data. The PyQt app calls the service directly, in-process — no HTTP server is started. The backend boots straight into the default admin identity — there is no login step.

PySide6 6.x is required. The service package is stdlib-only (plus SQLAlchemy) and can be smoke-tested without Qt:

```bash
python -m compileall -q src/gui src/service
python -c "import sys; sys.path.insert(0, 'src'); from service import Backend, command_names; b=Backend(); print(len(command_names()), b.call('getOverview'))"
```

Set `QT_QPA_PLATFORM=offscreen` for headless GUI smoke tests. Runtime state is created in `data/` (a SQLite `backend.db`) and should not be committed.

## LLM 配置

所有 LLM 调用统一走 `service.llm.OpenAIClient`（vendored 自 `BookerGptTool/openai.py`，与上游保持 API 兼容）。客户端按环境变量装配，配置方式与 BookerGptTool 一致：

```bash
export OPENAI_API_KEY=sk-...          # API Key；未设置时 sendMessage 回落为内置演示回复
export OPENAI_BASE_URL=http://localhost:5000/v1   # API 地址（OpenAI 兼容网关）
export OPENAI_CHAT_MODEL=glm-4-flash  # 对话模型名，缺省 gpt-3.5-turbo
export OPENAI_NO_THINK=1              # 可选：关闭思考模式（reasoning_effort=none 等）
```

配置了 `OPENAI_API_KEY` 时，`sendMessage` 会把会话历史折叠成 role/content 消息并发起真实对话；未配置时保持原有演示回复，便于离线/测试运行。

## Architecture

- `src/service/` — the merged service. `core.py` provides the in-process command facade over a SQLAlchemy/SQLite store, demo seed data, conversations, skills, hosts, teams, billing, tickets and admin, plus a shape-preserving fallback for the complete command registry from `contracts/commands.json` (266 names). `llm.py` is the vendored `OpenAIClient` (对话/视觉/文生图/工具循环) plus `client_from_env()`/`chat_model()` 装配助手；`sendMessage` 通过它调用真实 LLM，未配置时回落演示回复。`__init__.py` exposes `ServiceFacade` used directly by the shell.
- `src/gui/` — the dark PySide6 shell, asynchronous worker helpers, and home/chat plus six domain views (skills, hosts, teams, billing, tickets, admin). The UI is authored natively rather than reusing web assets.
- `src/main.py` — the launch entry point (also exposed as the `clawsgo-standalone` console script).

The embedded backend is the migration seam for the remaining domain-by-domain ports. Unsupported desktop-only operations return explicit `available`/`ok` results instead of silently touching the marketing site or web bundles.
