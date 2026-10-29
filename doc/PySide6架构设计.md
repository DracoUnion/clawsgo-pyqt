# clawsgo-pyqt 架构设计

> ClawsGO Science 独立桌面壳（PySide6）。本文件描述架构对齐后的当前代码结构（2026-10-30）。

## 1. 项目简介

把原 HTTP/服务端 ClawsGO 以嵌入式 SQLite 后端 + PySide6 桌面壳重写为**进程内**应用：无 HTTP 服务、
无登录（内嵌回退到默认管理员）、命令面（`contracts/commands.json`，266 个命令）兼容上游。

变更历史：`bf1a38e` 新增零 Qt 架构层（common/tasks/bootstrap），`launch()` 支持注入 AppContext，
`ServiceFacade.backend` 可注入（测试用临时库隔离）。

## 2. 技术栈与依赖（`pyproject.toml`）

| 项 | 值 |
|---|---|
| Qt 绑定 | PySide6 ≥ 6.5 |
| DB/ORM | SQLAlchemy（SQLite `data/backend.db`，可用 `CLAWSGO_DATA_DIR` 覆盖） |
| LLM | openai（`service/llm.py` OpenAIClient，未配置 key 回落演示智能体） |
| 其他 | json-repair / pyyaml / pydantic / requests |
| 入口 | console script `clawsgo-standalone = main:main` 或 `python src/main.py` |
| 测试 | unittest（backend + 架构层）|

## 3. 目录结构

```text
clawsgo-pyqt/
├─ pyproject.toml            # src-layout（package-dir=src）
├─ contracts/commands.json   # 上游命令契约（266 命令名）
├─ data/                      # 运行时 SQLite（gitignored）
├─ src/
│  ├─ main.py                 # 入口 → gui.app.launch()
│  ├─ bootstrap.py            # build_context()：Backend + EventHub + TaskManager + ServiceFacade → AppContext
│  ├─ common/                 # ★ 零 Qt
│  │  ├─ events.py            # EventHub
│  │  ├─ context.py           # AppContext
│  │  └─ __init__.py
│  ├─ tasks/                  # ★ 零 Qt
│  │  ├─ task.py              # Task/TaskState/TaskManager + TaskCancelled
│  │  └─ __init__.py
│  ├─ service/                # ★ 零 Qt 内嵌后端
│  │  ├─ core.py              # Backend（~2000 行，SQLite/SQLAlchemy + 命令分发 + 种子 + 管理员激活）
│  │  ├─ models.py / shapes.py / plans.py / seed.py / errors.py / llm.py
│  │  └─ __init__.py          # ServiceFacade（backend 可注入）+ BackendError + ApiError
│  ├─ gui/                    # ★ 唯一 PySide6
│  │  ├─ app.py               # launch(ctx=None)：bootstrap → MainWindow；win.ctx 暴露 AppContext
│  │  ├─ main_window.py       # 侧栏导航 + QStackedWidget
│  │  ├─ workers.py           # FuncTask(QRunnable) + PollEventsWorker(QThread)（Qt 线程 IO）
│  │  ├─ views/               # home/chat/skills/hosts/teams/billing/tickets/admin（PageView）
│  │  ├─ theme.py / widgets.py
│  │  └─ __init__.py
│  └─ tests/
│     ├─ test_backend.py      # Backend 全命令冒烟（临时 SQLite + fake LLM）
│     └─ test_arch.py         # EventHub/TaskManager/bootstrap（零 Qt，19 用例含 backend）
```

## 4. 架构分层与依赖方向

```text
gui/ (唯一 PySide6)
 └─ service/facade.py  (ServiceFacade.call(command, data))
     └─ service/core.py  Backend（SQLite 命令分发，零 Qt）
         └─ common/ 零 Qt 基础设施（EventHub/AppContext）
```

`contracts/commands.json` 保持命令面契约；`ServiceFacade` 是 UI 唯一入口。
`gui/workers.py` 把每次 RPC 放入 QThreadPool（QRunnable），`PollEventsWorker` 轮询聊天事件，UI 不阻塞。

## 5. 关键流程

```text
python src/main.py → gui.app.launch()
→ ctx = build_context()           # 无 ctx 时由 bootstrap 装配
→ QApplication + theme.apply_theme
→ user = facade.user（内嵌管理员）
→ MainWindow(facade, user) → win.ctx = ctx（任务/事件可用）
→ app.exec()
```

RPC：页面 `await`-式 `FuncTask(facade.call, cmd, data)` → QRunnable 线程池 → `signals.done/failed` 回 UI。

## 6. 线程模型

| 线程 | 职责 |
|---|---|
| Qt 主线程 | 窗口 / 导航 / 信号槽 |
| QThreadPool（QRunnable） | 每次 RPC（FuncTask） |
| PollEventsWorker（QThread） | 轮询 `getMessages` / 会话事件 |
| TaskManager 池（零 Qt） | 通用后台任务（本仓为 UI 桥预留，业务 RPC 仍走 workers） |

## 7. 配置管理

- 数据目录：`CLAWSGO_DATA_DIR`（默认 `<repo>/data`）。
- LLM：环境变量（`service.llm` 组装 OpenAIClient）。
- 未配置 API Key：sendMessage 回落内置演示智能体（测试确定性）。

## 8. 测试

```bash
python -m unittest discover -s src/tests -t src     # 19 用例
python -m compileall -q src/gui src/service
# offscreen: QT_QPA_PLATFORM=offscreen python -c "from gui.app import launch; ..."
```

## 9. 与参考架构的差距（后续 TODO）

- `service/core.py` Backend 仍是巨型单体（命令 + DB + 种子 + 激活全部内聚）；
  可逐步拆 db/session + 按域 services，保持 commands dispatch 契约不变。
- `service/shapes.py` 为 dict 序列化，可迁 `schemas/`（Pydantic DTO）。
- 无 Alembic（`create_all` 建表）；无 QSettings 偏好存储。
- 业务任务状态仍在 UI 层轮询，可统一经 TaskManager + EventHub。