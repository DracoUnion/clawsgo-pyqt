"""Embedded, dependency-free ClawsGO backend for the PySide6 desktop build.

The service is a separate top-level package (``service``) called **in-process**
by the desktop shell — no HTTP server is started and no HTTP client is used.
State is held in a SQLite database (``data/backend.db``) via SQLAlchemy; the
command surface mirrors ``clawsgo-opensource/server`` (`contracts/commands.json`,
266 names).
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import models as m
from . import plans as P
from . import shapes as S
from .errors import ApiError, badRequest, conflict, forbidden, need, notFound, req
from .models import create_all
from .seed import seed as _seed_all

ROOT = Path(__file__).resolve().parent.parent  # repo root
DATA = Path(os.environ.get("CLAWSGO_DATA_DIR", ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)
PHONE = "13800000000"
ADMIN_PHONE = "13900000000"
PASSWORD = "clawsgo2026"


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def rid(p="id"):
    return str(p) + "_" + uuid.uuid4().hex[:12]


def _clamp(v, lo, hi):
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = hi
    return max(lo, min(hi, v))


def _limit(p, default=50, hi=200):
    return _clamp(p.get("limit", default), 1, hi)


def _offset(p):
    try:
        return max(0, int(p.get("offset", 0)))
    except (TypeError, ValueError):
        return 0


def _listout(key, rows, total, p, default=50, hi=200):
    return {key: rows, "items": rows, "total": total,
            "limit": _limit(p, default, hi), "offset": _offset(p)}


# ---------------------------------------------------------------------------
# Virtual file tree for host workspaces (no real disk IO)
# ---------------------------------------------------------------------------
_WORKSPACE_TREE = {
    "": [("dir", "home", "/home"), ("dir", "data", "/data"), ("dir", "opt", "/opt"),
         ("dir", "var", "/var")],
    "/home": [("dir", "clawsgo", "/home/clawsgo")],
    "/home/clawsgo": [("dir", "workspace", "/home/clawsgo/workspace"),
                      ("dir", "datasets", "/home/clawsgo/datasets"),
                      ("dir", "notebooks", "/home/clawsgo/notebooks")],
    "/home/clawsgo/workspace": [("file", "README.md", "/home/clawsgo/workspace/README.md", 128),
                                ("file", "main.py", "/home/clawsgo/workspace/main.py", 2048),
                                ("dir", "src", "/home/clawsgo/workspace/src"),
                                ("dir", "data", "/home/clawsgo/workspace/data")],
    "/home/clawsgo/workspace/src": [("file", "agent.py", "/home/clawsgo/workspace/src/agent.py", 4096)],
    "/home/clawsgo/workspace/data": [("file", "sample.csv", "/home/clawsgo/workspace/data/sample.csv", 512)],
    "/home/clawsgo/datasets": [("file", "dataset-a.csv", "/home/clawsgo/datasets/dataset-a.csv", 8192)],
    "/home/clawsgo/notebooks": [("file", "analysis.ipynb", "/home/clawsgo/notebooks/analysis.ipynb", 3072)],
    "/data": [("dir", "lab", "/data/lab"), ("dir", "raw", "/data/raw")],
    "/data/raw": [("file", "raw.csv", "/data/raw/raw.csv", 1024)],
    "/data/lab": [],
    "/opt": [("dir", "models", "/opt/models")],
    "/opt/models": [("file", "model.onnx", "/opt/models/model.onnx", 20480)],
    "/var": [("dir", "cache", "/var/cache")],
    "/var/cache": [("dir", "clawsgo", "/var/cache/clawsgo")],
}


class Backend:
    """In-process backend backed by SQLite. One instance per app lifetime."""

    def __init__(self, url=None):
        self.lock = threading.RLock()
        self._engine = create_engine(
            url or f"sqlite:///{DATA / 'backend.db'}",
            connect_args={"check_same_thread": False},
        )
        create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine, autoflush=True)
        self.user = None  # {'id','role','name','phone','plan'} after login
        self.token = None
        self._otp = {}
        self._seed_if_empty()

    # ------------------------------------------------------------------ db
    def _seed_if_empty(self):
        with self._Session() as db:
            if db.query(m.User).count() == 0:
                _seed_all(db)
                db.commit()

    def _user(self, db):
        if not self.user:
            raise ApiError("UNAUTHORIZED", "未登录", 401)
        u = db.get(m.User, self.user["id"])
        if u is None:
            raise ApiError("UNAUTHORIZED", "未登录", 401)
        return u

    def _is_member(self, db, team_id, user_id):
        return db.query(m.TeamMember).filter_by(teamId=team_id, userId=user_id).first() is not None

    def _ctx_team(self, db, data):
        tid = (data or {}).get("teamId")
        u = self._user(db)
        if tid and (self._is_member(db, tid, u.id) or u.role == "super_admin"):
            return tid
        team = S.personal_team_for(db, u.id)
        return team.id if team else (tid or None)

    def _own_team(self, db, team_id, require_admin=False):
        u = self._user(db)
        t = db.get(m.Team, team_id)
        if t is None:
            raise notFound("团队")
        if u.role == "super_admin":
            return t
        mem = db.query(m.TeamMember).filter_by(teamId=team_id, userId=u.id).first()
        if mem is None:
            raise forbidden("不属于该团队")
        if require_admin and mem.role not in ("owner", "admin"):
            raise forbidden("需要管理员权限")
        return t

    def _own_host(self, db, host_id, data=None):
        u = self._user(db)
        h = db.get(m.Host, host_id)
        if h is None:
            raise notFound("主机")
        if u.role != "super_admin" and h.teamId != self._ctx_team(db, data):
            raise forbidden("没有权限")
        return h

    def _own_ticket(self, db, ticket_id):
        u = self._user(db)
        t = db.query(m.Ticket).filter_by(id=ticket_id).first()
        if t is None:
            raise notFound("工单")
        if not (t.userId == u.id or t.teamId == self._ctx_team(db, {})
                or u.role in ("admin", "super_admin")):
            raise forbidden("无权访问该工单")
        return t

    def _admin_only(self, db):
        u = self._user(db)
        if u.role not in ("admin", "super_admin"):
            raise forbidden("没有权限")
        return u

    def _audit(self, db, action, target=None, detail=None):
        db.add(m.AuditLog(id=rid("al"), actorId=self.user["id"],
                          actorName=self.user.get("name"), action=action,
                          target=target, detail=detail, ip="127.0.0.1",
                          createdAt=now()))

    def _counter(self, db, key):
        c = db.get(m.Counter, key)
        if c is None:
            c = m.Counter(key=key, value=0)
            db.add(c)
            db.flush()
        return c

    # ------------------------------------------------------------------ auth
    def login_password(self, phone, password):
        with self.lock, self._Session() as db:
            u = db.query(m.User).filter_by(phone=phone).first()
            if u is None or u.password != password:
                raise ValueError("手机号或密码不正确")
            self.user = {"id": u.id, "role": u.role, "name": u.name,
                         "phone": u.phone, "plan": u.plan}
            self.token = "cgt_" + uuid.uuid4().hex
            self._audit(db, "auth.signIn", u.id, "手机号密码登录")
            db.commit()
            return {"user": S.profile_row(db, u), "token": self.token}

    def request_otp(self, phone):
        with self.lock, self._Session() as db:
            self._otp[phone] = "123456"
            db.commit()
            return {"requestId": rid("otp"), "devCode": "123456"}

    def login_otp(self, phone, code):
        if len(str(code)) != 6:
            raise ValueError("验证码不正确")
        return self.login_password(phone, PASSWORD)

    # ------------------------------------------------------------------ call
    def call(self, cmd, data=None):
        data = data or {}
        with self.lock, self._Session() as db:
            fn = COMMANDS.get(cmd)
            if fn is None:
                return self._fallback(cmd, data)
            result = fn(self, db, data)
            db.commit()
            return result

    def _fallback(self, cmd, data):
        # Shape-preserving fallback for the complete command registry.
        if cmd.startswith("get") or cmd.startswith("adminGet"):
            return {"items": [], "total": 0}
        if cmd.startswith("download"):
            return {"available": False, "reason": "embedded-desktop"}
        if cmd.startswith(("create", "update", "set", "delete", "install",
                           "uninstall", "enable", "reorder", "mark", "move",
                           "copy", "rename", "archive", "unarchive", "upload",
                           "reply", "close", "grant", "topup", "ban", "claim",
                           "accept", "reject", "leave", "transfer", "redeem",
                           "revoke", "register", "probe", "rebuild", "clean")):
            return {"ok": True, "available": True}
        return {"ok": True}


# ---------------------------------------------------------------------------
# Command registry: name -> fn(backend, db, data)
# ---------------------------------------------------------------------------
COMMANDS: dict = {}


def _cmd(*names):
    def wrap(fn):
        for n in names:
            COMMANDS[n] = fn
        return fn
    return wrap


# ===========================================================================
# account domain
# ===========================================================================
@_cmd("getProfile")
def c_get_profile(self, db, data):
    return {"profile": S.profile_row(db, self._user(db))}


@_cmd("updateProfile")
def c_update_profile(self, db, data):
    u = self._user(db)
    for k in ("name", "email", "avatarUrl", "locale", "theme"):
        if k in data and data[k] is not None:
            setattr(u, k, data[k])
    if data.get("onboarded"):
        u.onboardedAt = now()
    elif data.get("onboarded") is False:
        u.onboardedAt = None
    return {"profile": S.profile_row(db, u)}


@_cmd("getOverview")
def c_get_overview(self, db, data):
    days = _clamp(data.get("days", 30), 1, 365)
    u = self._user(db)
    team = S.personal_team_for(db, u.id)
    convs = db.query(m.Conversation).all()
    msgs = db.query(m.Message).all()
    hosts = db.query(m.Host).filter_by(teamId=team.id).all() if team else []
    tickets = db.query(m.Ticket).filter_by(teamId=team.id).all() if team else []
    users = db.query(m.User).count()
    runs = sum(1 for x in msgs if x.role == "assistant")
    tokens = 0
    for x in msgs:
        usage = (x.meta or {}).get("usage") or {}
        tokens += usage.get("inputTokens", 0) + usage.get("outputTokens", 0)
    paid_cents = sum((o.amountCents or 0) for o in db.query(m.PaymentOrder).all()
                     if o.status == "paid")
    ov = {"credits": team.creditBalance if team else 0,
          "plan": u.plan or "free",
          "activeConversations": len([c for c in convs if not c.archivedAt]),
          "hosts": len(hosts), "teams": 1,
          "storageUsedGb": 0.8, "storageTotalGb": 200,
          "periodStart": now(), "periodEnd": now()}
    return {"days": days, "users": users, "activeUsers": 2, "newUsers": 1,
            "teams": 1, "conversations": len(convs), "hosts": len(hosts),
            "tickets": len(tickets),
            "openTickets": len([t for t in tickets if t.status == "open"]),
            "credits": ov["credits"], "runs": runs, "tokens": tokens,
            "revenue": round(paid_cents / 100, 2), "series": [], "byDay": [],
            "byModel": [], "overview": ov}


@_cmd("getUsageStats")
def c_get_usage(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    team = db.get(m.Team, team_id)
    convs = db.query(m.Conversation).filter_by(teamId=team_id).all()
    cids = {c.id for c in convs}
    msgs = [x for x in db.query(m.Message).all() if x.conversationId in cids]
    total_in = total_out = total_cr = 0
    runs = 0
    by_model = {}
    for x in msgs:
        usage = (x.meta or {}).get("usage") or {}
        total_in += usage.get("inputTokens", 0)
        total_out += usage.get("outputTokens", 0)
        total_cr += usage.get("contextTokens", round(usage.get("inputTokens", 0) * 0.35))
        if x.role == "assistant":
            runs += 1
            mid = x.modelId or "unknown"
            by_model[mid] = by_model.get(mid, 0) + usage.get("outputTokens", 0)
    credits = round((total_in + total_out * 4) / 1000)
    agg = {"input": total_in, "output": total_out, "cacheRead": total_cr,
           "totalTokens": total_in + total_out, "credits": credits, "runs": runs,
           "byDay": [], "series": [], "byModel": [{"model": k, "tokens": v}
                                                  for k, v in by_model.items()],
           "models": list(by_model.keys()), "byMember": [], "members": []}
    return {"usageStats": {**agg, "teamId": team_id,
                           "rangeDays": data.get("rangeDays", 30),
                           "balance": team.creditBalance if team else 0,
                           "creditBalance": team.creditBalance if team else 0,
                           "plan": team.plan if team else "free",
                           "periodStart": now(), "periodEnd": now()}, **agg}


@_cmd("getCreditLedger")
def c_get_credit_ledger(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    rows = db.query(m.CreditLedger).filter_by(teamId=team_id).order_by(
        m.CreditLedger.createdAt.desc()).all()
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    return _listout("entries", [S.credit_ledger_row(db, r) for r in rows], total, data, 20, 200)


@_cmd("getDevices")
def c_get_devices(self, db, data):
    u = self._user(db)
    rows = [d for d in db.query(m.Device).filter_by(userId=u.id).all() if not d.revokedAt]
    return _listout("devices", [S.device_row(db, d) for d in rows], len(rows), data)


@_cmd("getActivities")
def c_get_activities(self, db, data):
    u = self._user(db)
    rows = [a for a in db.query(m.AuditLog).filter_by(actorId=u.id).order_by(
        m.AuditLog.createdAt.desc()).all()]
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 100)]
    act = [{"id": a.id, "action": a.action, "detail": a.detail or "",
            "createdAt": a.createdAt} for a in rows]
    return {"activities": act, "items": act, "total": total,
            "limit": _limit(data, 20, 100), "offset": _offset(data)}


@_cmd("getUsers")
def c_get_users(self, db, data):
    rows = db.query(m.User).order_by(m.User.createdAt.desc()).all()
    users = [S.user_row(u) for u in rows]
    return _listout("users", users, len(users), data)


@_cmd("getProjects")
def c_get_projects(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    rows = db.query(m.Project).filter_by(teamId=team_id).all()
    if not data.get("includeArchived"):
        rows = [r for r in rows if not r.archivedAt]
    rows.sort(key=lambda r: (r.pinnedAt is None, r.pinnedAt or "", r.updatedAt or ""))
    projects = [S.project_row(db, r, self.user["id"]) for r in rows]
    return {"projects": projects, "total": len(projects),
            "limit": _limit(data, 50, 200), "offset": _offset(data)}


@_cmd("getProject")
def c_get_project(self, db, data):
    p = db.get(m.Project, req(data, "projectId"))
    if p is None:
        raise notFound("项目")
    return {"project": S.project_row(db, p, self.user["id"])}


@_cmd("createProject")
def c_create_project(self, db, data):
    p = m.Project(id=rid("p"), teamId=self._ctx_team(db, data) or "",
                  userId=self.user["id"],
                  name=data.get("name") or data.get("title") or "未命名项目",
                  kind=data.get("kind", "explicit"), instruction=data.get("instruction"),
                  createdAt=now(), updatedAt=now(), archivedAt=None, pinnedAt=None)
    db.add(p)
    return {"project": S.project_row(db, p, self.user["id"]), "id": p.id}


@_cmd("updateProject")
def c_update_project(self, db, data):
    p = db.get(m.Project, req(data, "projectId"))
    if p is None:
        raise notFound("项目")
    for k in ("name", "instruction", "kind"):
        if data.get(k) is not None:
            setattr(p, k, data[k])
    if data.get("pinned") is True:
        p.pinnedAt = now()
    elif data.get("pinned") is False:
        p.pinnedAt = None
    p.updatedAt = now()
    return {"project": S.project_row(db, p, self.user["id"])}


@_cmd("deleteProject")
def c_delete_project(self, db, data):
    p = db.get(m.Project, req(data, "projectId"))
    if p is None:
        raise notFound("项目")
    db.delete(p)
    for c in db.query(m.Conversation).filter_by(projectId=p.id).all():
        c.projectId = None
    return {"ok": True, "id": p.id}


@_cmd("archiveProject", "unarchiveProject")
def c_archive_project(self, db, data):
    p = db.get(m.Project, req(data, "projectId"))
    if p is None:
        raise notFound("项目")
    p.archivedAt = None if data.get("archive") is False else now()
    return {"ok": True}


@_cmd("cloneProject")
def c_clone_project(self, db, data):
    src = db.get(m.Project, req(data, "projectId"))
    if src is None:
        raise notFound("项目")
    p = m.Project(id=rid("p"), teamId=src.teamId, userId=self.user["id"],
                  name=data.get("name") or f"{src.name} 副本", kind=src.kind,
                  instruction=src.instruction, createdAt=now(), updatedAt=now(),
                  archivedAt=None, pinnedAt=None)
    db.add(p)
    return {"project": S.project_row(db, p, self.user["id"])}


@_cmd("listAgentMemory")
def c_list_agent_memory(self, db, data):
    u = self._user(db)
    rows = db.query(m.AgentMemory).filter_by(userId=u.id).all()
    items = [S.agent_memory_row(db, r) for r in rows]
    return {"items": items, "entries": items, "total": len(items),
            "file": {"exists": False, "content": "", "scope": data.get("scope", "global"),
                     "path": "AGENTS.md", "updatedAt": None},
            "exists": False, "content": ""}


@_cmd("createAgentMemory")
def c_create_agent_memory(self, db, data):
    u = self._user(db)
    am = m.AgentMemory(id=rid("am"), teamId=self._ctx_team(db, data) or "", userId=u.id,
                       scope=data.get("scope", "global"),
                       key=data.get("key") or data.get("title") or "memory",
                       content=data.get("content", ""), createdAt=now(), updatedAt=now())
    db.add(am)
    item = S.agent_memory_row(db, am)
    return {"item": item, **item}


@_cmd("updateAgentMemory")
def c_update_agent_memory(self, db, data):
    am = db.get(m.AgentMemory, req(data, "id"))
    if am is None:
        raise notFound("记忆条目")
    if data.get("key") is not None:
        am.key = data["key"]
    if data.get("content") is not None:
        am.content = data["content"]
    am.updatedAt = now()
    return {"item": S.agent_memory_row(db, am)}


@_cmd("deleteAgentMemory")
def c_delete_agent_memory(self, db, data):
    am = db.get(m.AgentMemory, req(data, "id"))
    if am:
        db.delete(am)
    return {"ok": True, "id": data.get("id")}


@_cmd("getLinkPreview")
def c_get_link_preview(self, db, data):
    url = req(data, "url")
    return {"preview": {"url": url, "title": url, "description": None, "image": None,
                        "siteName": None, "favicon": None, "fetched": False,
                        "error": "offline"}}


# ===========================================================================
# chat domain
# ===========================================================================
@_cmd("getConversations")
def c_get_conversations(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    rows = db.query(m.Conversation).filter_by(teamId=team_id).all()
    if data.get("mineOnly"):
        rows = [r for r in rows if r.userId == self.user["id"]]
    if data.get("projectId"):
        rows = [r for r in rows if r.projectId == data["projectId"]]
    if data.get("pinnedOnly"):
        rows = [r for r in rows if r.pinnedAt]
    if data.get("archivedOnly"):
        rows = [r for r in rows if r.archivedAt]
    elif not data.get("includeArchived"):
        rows = [r for r in rows if not r.archivedAt]
    query = (data.get("query") or "").strip().lower()
    if query:
        rows = [r for r in rows if query in (r.title or "").lower()]
    rows.sort(key=lambda r: (r.pinnedAt is None, r.pinnedAt or "",
                             r.lastMessageAt or r.updatedAt or r.createdAt or ""), reverse=True)
    rows.sort(key=lambda r: r.pinnedAt is None)  # pinned first
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 50, 200)]
    convs = [S.conversation_row(db, r) for r in rows]
    return {"conversations": convs, "total": total,
            "limit": _limit(data, 50, 200), "offset": _offset(data)}


@_cmd("getConversation")
def c_get_conversation(self, db, data):
    c = db.get(m.Conversation, req(data, "conversationId"))
    if c is None:
        raise notFound("会话")
    return {"conversation": S.conversation_row(db, c)}


@_cmd("getMessages")
def c_get_messages(self, db, data):
    cid = req(data, "conversationId")
    conv = db.get(m.Conversation, cid)
    if conv is None:
        raise notFound("会话")
    u = self._user(db)
    if conv.teamId != self._ctx_team(db, data) and u.role not in ("admin", "super_admin"):
        raise forbidden("没有权限")
    rows = db.query(m.Message).filter_by(conversationId=cid).order_by(m.Message.seq.asc()).all()
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 500)]
    return {"messages": [S.message_row(db, x) for x in rows], "total": total}


def _demo_assistant_parts(text):
    return [
        {"type": "reasoning", "text": "正在检查工作区…"},
        {"type": "tool", "toolUseId": "call_demo", "toolName": "Glob",
         "input": {"pattern": "**/*"}, "output": {"count": 0}, "state": "output-available"},
        {"type": "text", "text": ("这是内置演示智能体的回复：已收到你的问题。\n\n"
                                  f"> {text}\n\n你可以继续使用会话、技能、主机和工作区功能。")},
    ]


@_cmd("sendMessage")
def c_send_message(self, db, data):
    cid = data.get("conversationId") or rid("c")
    t = now()
    conv = db.get(m.Conversation, cid)
    if conv is None:
        title = (data.get("title") or (data.get("text") or "")[:50] or "未命名任务")
        conv = m.Conversation(id=cid, teamId=self._ctx_team(db, data) or "",
                              userId=self.user["id"], projectId=data.get("projectId"),
                              title=title, hostId=data.get("hostId"),
                              workdir=data.get("workdir"), modelId=data.get("modelId", "clawsgo-1.0-lithium"),
                              context=data.get("context", "default"), effort=data.get("effort"),
                              mode=data.get("mode", "agent"), streamId=None,
                              pinnedAt=None, archivedAt=None, createdAt=t, updatedAt=t,
                              lastMessageAt=t, lastMessagePreview="", lastMessageAttachments=0)
        db.add(conv)
    text = str(data.get("text", ""))
    seq = db.query(m.Message).filter_by(conversationId=cid).count()
    um = m.Message(id=data.get("messageId") or rid("m"), conversationId=cid,
                   role="user", seq=seq + 1, modelId=None, context=None,
                   parts=[{"type": "text", "text": text}], streamId=None, meta=None,
                   createdAt=t)
    am = m.Message(id=data.get("assistantMessageId") or rid("m"), conversationId=cid,
                   role="assistant", seq=seq + 2, modelId=conv.modelId, context=conv.context,
                   parts=_demo_assistant_parts(text), streamId="stream_" + rid(20),
                   meta={"modelId": conv.modelId, "effort": conv.effort, "mode": conv.mode},
                   createdAt=t)
    db.add_all([um, am])
    conv.updatedAt = t
    conv.lastMessageAt = t
    conv.lastMessagePreview = text[:120]
    conv.lastMessageAttachments = len(data.get("files") or [])
    conv.streamId = am.streamId
    return {"userMessage": S.message_row(db, um),
            "assistantMessage": S.message_row(db, am),
            "conversation": S.conversation_row(db, conv)}


@_cmd("updateConversation")
def c_update_conversation(self, db, data):
    conv = db.get(m.Conversation, req(data, "conversationId"))
    if conv is None:
        raise notFound("会话")
    for k in ("title", "modelId", "effort", "mode", "context", "projectId", "hostId", "workdir"):
        if data.get(k) is not None:
            setattr(conv, k, data[k])
    if data.get("pinned") is True:
        conv.pinnedAt = now()
    elif data.get("pinned") is False:
        conv.pinnedAt = None
    conv.updatedAt = now()
    return {"conversation": S.conversation_row(db, conv)}


@_cmd("archiveConversation", "unarchiveConversation")
def c_archive_conversation(self, db, data):
    conv = db.get(m.Conversation, req(data, "conversationId"))
    if conv is None:
        raise notFound("会话")
    conv.archivedAt = None if data.get("archive") is False else now()
    return {"ok": True}


@_cmd("deleteConversation")
def c_delete_conversation(self, db, data):
    conv = db.get(m.Conversation, req(data, "conversationId"))
    if conv is None:
        raise notFound("会话")
    cid = conv.id
    for x in db.query(m.Message).filter_by(conversationId=cid).all():
        db.delete(x)
    db.delete(conv)
    return {"ok": True, "id": cid}


@_cmd("stopMessage")
def c_stop_message(self, db, data):
    return {"ok": True, "stopped": True}


@_cmd("searchAll")
def c_search_all(self, db, data):
    q = (data.get("query") or "").strip().lower()
    convs = [S.conversation_row(db, c) for c in db.query(m.Conversation).all()
             if q in (c.title or "").lower()]
    msgs = [S.message_row(db, x) for x in db.query(m.Message).all()
            if q in "".join(p.get("text", "") for p in (x.parts or []) if isinstance(p, dict)).lower()]
    return {"conversations": convs, "messages": msgs, "total": len(convs) + len(msgs)}


# ===========================================================================
# skills domain
# ===========================================================================
_BUILTIN_SKILLS = [
    {"slug": "literature-review", "title": "文献综述",
     "description": "检索、筛选、抽取、成文一条龙：给定研究问题，产出带证据表的综述初稿与 PRISMA 流程图。",
     "version": "1.4.0", "tags": ["research", "review", "prisma"],
     "files": ["SKILL.md", "prisma.py", "extract.py"]},
    {"slug": "prisma-flow", "title": "PRISMA 流程图",
     "description": "把筛选各层的计数渲染成 PRISMA 2020 流程图，输出 Mermaid / SVG。",
     "version": "1.1.2", "tags": ["research", "figure"],
     "files": ["SKILL.md", "render.mjs"]},
    {"slug": "latex-manuscript", "title": "LaTeX 手稿",
     "description": "按期刊模板搭手稿骨架，处理引用、图表编号与参考文献。",
     "version": "2.0.1", "tags": ["writing", "latex"],
     "files": ["SKILL.md", "main.tex", "Makefile"]},
    {"slug": "meta-analysis", "title": "Meta 分析",
     "description": "效应量合并、异质性检验、森林图与漏斗图。",
     "version": "0.9.4", "tags": ["statistics", "figure"],
     "files": ["SKILL.md", "pool.py"]},
    {"slug": "data-cleaning", "title": "数据清洗",
     "description": "缺失值、异常值、单位与编码统一，产出可追溯的清洗日志。",
     "version": "1.2.0", "tags": ["data", "pipeline"],
     "files": ["SKILL.md", "clean.py"]},
    {"slug": "figure-studio", "title": "图版工坊",
     "description": "按目标期刊的图注、字号、分辨率规范重排图表。",
     "version": "1.0.3", "tags": ["figure", "typesetting"],
     "files": ["SKILL.md"]},
]

_BUILTIN_README = {
    "literature-review": ("# 文献综述\n\n## 何时使用\n用户要求「调研 / 综述 / 检索文献 / 写 review / 找证据」时。\n\n"
                          "## 流程\n1. **拆问题** — 把研究问题拆成 PICO，明确纳入排除标准。\n"
                          "2. **定检索式** — 为每个数据库生成检索式，留档。\n"
                          "3. **去重筛选** — 按标题摘要初筛，再全文复筛。\n"
                          "4. **抽数据** — 用统一表格抽取研究类型/样本量/干预/结局/偏倚风险。\n"
                          "5. **成文** — 引言、方法（含 PRISMA 流程图）、结果、讨论、局限。\n"),
    "prisma-flow": ("# PRISMA 流程图\n\n渲染筛选各层计数为 PRISMA 2020 流程图（Mermaid / SVG）。\n\n"
                    "恒等式：`identified - duplicates == screened`\n`screened - excluded_title == fulltext`\n"
                    "`fulltext - excluded_full == included`\n"),
    "latex-manuscript": ("# LaTeX 手稿\n\n## 骨架\n- `main.tex` 主文件，`\\input` 各章节\n- `sections/` 章节\n- `figures/` 图\n- `refs.bib` 参考文献\n"),
    "meta-analysis": ("# Meta 分析\n\n## 流程\n1. 统一效应量（OR / RR / SMD / MD）录入。\n"
                      "2. 异质性检验（I² / Q）。\n3. 森林图与漏斗图输出。\n"),
    "data-cleaning": ("# 数据清洗\n\n## 流程\n1. 缺失值策略（删除/均值/插值）。\n2. 异常值检测。\n"
                      "3. 单位与编码统一，产出清洗日志。\n"),
    "figure-studio": ("# 图版工坊\n\n按目标期刊的图注、字号、分辨率规范重排图表，输出出版级图版。\n"),
}


def _team_skills(self, db, team_id):
    return db.query(m.Skill).filter_by(teamId=team_id).all()


def _seed_team_skills(self, db, team_id):
    existing = {s.slug for s in _team_skills(self, db, team_id)}
    for b in _BUILTIN_SKILLS:
        if b["slug"] in existing:
            continue
        installed = b["slug"] not in ("meta-analysis",)
        enabled = b["slug"] not in ("meta-analysis", "figure-studio")
        db.add(m.Skill(
            id=rid("s"), teamId=team_id, userId=self.user["id"], name=b["slug"],
            slug=b["slug"], title=b["title"], description=b["description"],
            version=b["version"], source="official", repo="https://github.com/clawsgo/skills",
            tags=b["tags"], installed=installed, enabled=enabled,
            installedAt=now() if installed else None, hostId=None,
            files=[{"path": f, "size": 1200 + (hash(f) % 3000)} for f in b["files"]],
            readme=_BUILTIN_README.get(b["slug"], f"# {b['slug']}\n\n{b['description']}\n"),
        ))


@_cmd("getSkills")
def c_get_skills(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    _seed_team_skills(self, db, team_id)
    skills = _team_skills(self, db, team_id)
    rows = [S.skill_row(db, s) for s in skills]
    return {"skills": rows, "items": rows, "total": len(rows)}


def _find_skill(self, db, team_id, key):
    for s in _team_skills(self, db, team_id):
        if s.name == key or s.slug == key or s.id == key:
            return s
    return None


@_cmd("getSkillDetail")
def c_get_skill_detail(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    _seed_team_skills(self, db, team_id)
    s = _find_skill(self, db, team_id, data.get("slug")) if data.get("slug") else None
    if s is None:
        raise notFound("技能")
    files = [{"path": f.get("path") if isinstance(f, dict) else f,
              "name": f.get("path").split("/")[-1] if isinstance(f, dict) and f.get("path") else f,
              "size": f.get("size") if isinstance(f, dict) else 0}
             for f in (s.files or [])]
    detail = S.skill_row(db, s)
    detail["dir"] = f"data/skills/{team_id}/{s.name}"
    detail["files"] = files
    detail["fileCount"] = len(files)
    detail["readme"] = s.readme or ""
    return {"detail": detail, "skill": detail}


@_cmd("getSkillFile")
def c_get_skill_file(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    _seed_team_skills(self, db, team_id)
    slug = data.get("slug")
    s = _find_skill(self, db, team_id, slug) if slug else None
    if s is None:
        raise notFound("技能")
    path = data.get("path") or "SKILL.md"
    if "/" in path or ".." in path:
        # treat as nested file inside skill dir
        pass
    if path.endswith("/") or path in ("", "."):
        files = [{"name": f["path"].split("/")[-1], "path": f["path"],
                  "type": "file", "size": f["size"]} for f in (s.files or [])]
        return {"exists": True, "path": path, "type": "dir", "entries": files,
                "content": None}
    content = s.readme or ""
    return {"exists": True, "path": path, "type": "file", "content": content,
            "text": content, "size": len(content), "language": "markdown"}


@_cmd("setSkillEnabled")
def c_set_skill_enabled(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    s = _find_skill(self, db, team_id, data.get("slug")) if data.get("slug") else None
    if s is None:
        raise notFound("技能")
    s.enabled = data.get("enabled") is not False
    if s.enabled:
        s.installed = True
    return {"ok": True, "skill": S.skill_row(db, s)}


@_cmd("installSkill")
def c_install_skill(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    slug = data.get("slug") or data.get("name") or req(data, "slug")
    s = _find_skill(self, db, team_id, slug)
    if s is None:
        b = next((x for x in _BUILTIN_SKILLS if x["slug"] == slug), None)
        if b is None:
            b = {"slug": slug, "title": slug, "description": "手动安装的技能",
                 "version": "1.0.0", "tags": []}
        s = m.Skill(id=rid("s"), teamId=team_id, userId=self.user["id"], name=slug, slug=slug,
                    title=b["title"], description=b["description"], version=b["version"],
                    source=data.get("source", "official"), repo=None, tags=b["tags"],
                    installed=True, enabled=True, installedAt=now(), hostId=None,
                    files=[{"path": "SKILL.md", "size": 120}],
                    readme=f"# {slug}\n\n{b['description']}\n")
        db.add(s)
    else:
        s.installed = True
        s.enabled = True
        if not s.installedAt:
            s.installedAt = now()
    return {"skill": S.skill_row(db, s), "ok": True}


@_cmd("uninstallSkill")
def c_uninstall_skill(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    s = _find_skill(self, db, team_id, data.get("slug")) if data.get("slug") else None
    if s is None:
        raise notFound("技能")
    s.installed = False
    s.enabled = False
    return {"ok": True, "skill": S.skill_row(db, s)}


@_cmd("searchSkillMarket")
def c_search_skill_market(self, db, data):
    q = (data.get("query") or "").strip().lower()
    team_id = self._ctx_team(db, data) or ""
    rows = []
    if len(q) >= 2:
        team_installed = {s.slug for s in _team_skills(self, db, team_id)}
        for b in _BUILTIN_SKILLS:
            hay = " ".join([b["slug"], b["title"], b["description"]] + b["tags"]).lower()
            if q in hay:
                rows.append({"id": b["slug"], "slug": b["slug"], "name": b["slug"],
                             "title": b["title"], "description": b["description"],
                             "version": b["version"], "source": "official",
                             "repo": "https://github.com/clawsgo/skills",
                             "tags": b["tags"], "fileCount": len(b["files"]),
                             "stars": 120 + len(b["slug"]) * 7,
                             "installs": 300 + len(b["slug"]) * 13,
                             "installed": b["slug"] in team_installed})
    return {"skills": rows, "items": rows, "total": len(rows), "query": data.get("query") or ""}


@_cmd("listGithubSkills")
def c_list_github_skills(self, db, data):
    repo = data.get("repo") or "clawsgo/skills"
    rows = [{"slug": b["slug"], "name": b["slug"], "title": b["title"],
             "description": b["description"], "version": b["version"],
             "path": f"{b['slug']}/SKILL.md", "repo": repo,
             "url": f"https://github.com/{repo}/tree/main/{b['slug']}",
             "fileCount": len(b["files"])} for b in _BUILTIN_SKILLS]
    return {"skills": rows, "items": rows, "total": len(rows), "repo": repo}


# ===========================================================================
# hosts domain
# ===========================================================================
@_cmd("getHosts")
def c_get_hosts(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    rows = db.query(m.Host).filter_by(teamId=team_id).order_by(m.Host.createdAt.desc()).all()
    hosts = [S.host_row(db, h) for h in rows]
    return {"hosts": hosts, "items": hosts, "total": len(hosts)}


@_cmd("createHost")
def c_create_host(self, db, data):
    kind = data.get("kind") or "cloud"
    name = data.get("name") or f"{kind}-{rid(4)}"
    spec = data.get("spec") or {}
    cpu = int(data.get("cpu") or spec.get("cpu") or 2)
    mem = int(data.get("memoryGb") or spec.get("memoryGb") or 4)
    disk = int(data.get("diskGb") or spec.get("diskGb") or 50)
    gpu = data.get("gpu") or spec.get("gpu")
    h = m.Host(id=rid("h"), teamId=self._ctx_team(db, data) or "", userId=self.user["id"],
               name=name, kind=kind,
               status="offline" if kind == "ssh" else "running",
               spec={"cpu": cpu, "memoryGb": mem, "diskGb": disk, "gpu": gpu},
               image=data.get("image", "clawsgo/science-runtime:2026.09" if kind == "cloud" else None),
               workdir=data.get("workdir", "/home/clawsgo/workspace" if kind == "cloud" else "/"),
               createdAt=now(), lastSeenAt=now() if kind != "ssh" else None, cacheClearedAt=None)
    db.add(h)
    if kind == "ssh":
        db.add(m.SshServer(
            id=rid("ssh"), teamId=h.teamId, userId=h.userId, name=name,
            hostname=data.get("hostname") or data.get("host") or "127.0.0.1",
            port=int(data.get("port") or 22), username=data.get("username") or "root",
            authType=data.get("authType") or "key", status="unknown",
            latencyMs=None, lastProbeAt=None, createdAt=now()))
    hosts = [S.host_row(db, x) for x in db.query(m.Host).filter_by(teamId=h.teamId).all()]
    return {"host": S.host_row(db, h), "hosts": hosts}


@_cmd("updateHost")
def c_update_host(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    for k in ("name", "workdir", "image"):
        if data.get(k) is not None:
            setattr(h, k, data[k])
    spec = dict(h.spec or {})
    if data.get("spec"):
        spec.update({k: v for k, v in data["spec"].items() if v is not None})
    for k in ("cpu", "memoryGb", "diskGb", "gpu"):
        if data.get(k) is not None:
            spec[k] = data[k]
    h.spec = spec
    return {"host": S.host_row(db, h)}


@_cmd("deleteHost")
def c_delete_host(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    hid = h.id
    db.delete(h)
    return {"ok": True, "id": hid}


@_cmd("rebuildHost")
def c_rebuild_host(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    h.status = "running"
    h.lastSeenAt = now()
    return {"ok": True, "host": S.host_row(db, h)}


@_cmd("cleanHostCache")
def c_clean_host_cache(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    h.cacheClearedAt = now()
    return {"ok": True, "storage": _host_storage(h)}


def _host_storage(h):
    spec = h.spec or {}
    total = spec.get("diskGb") or 200
    hsh = hash(h.id) % 9973
    used = round(hsh / 9973 * total * 0.35)
    cache = round(used * 0.18)
    return {"hostId": h.id, "usedGb": used, "totalGb": total, "freeGb": total - used,
            "usedBytes": used * 1024 ** 3, "totalBytes": total * 1024 ** 3,
            "cacheGb": cache, "workdirGb": used - cache, "cacheClearedAt": h.cacheClearedAt,
            "updatedAt": now()}


@_cmd("getHostStatus")
def c_get_host_status(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    running = []
    for c in db.query(m.Conversation).filter_by(hostId=h.id).all():
        if c.streamId:
            running.append({"conversationId": c.id, "title": c.title,
                            "userId": c.userId, "startedAt": c.lastMessageAt or c.updatedAt or c.createdAt})
    row = S.host_row(db, h)
    row["hostId"] = h.id
    row["online"] = h.status in ("running", "online")
    row["running"] = running
    row["runningConversations"] = len(running)
    row["activity"] = []
    row["uptimeSeconds"] = _uptime_seconds(h.createdAt)
    row["loadAvg"] = [0.42, 0.38, 0.31]
    return row


def _uptime_seconds(created_iso):
    try:
        c = datetime.fromisoformat(created_iso)
        return max(0, int((datetime.now(timezone.utc) - c).total_seconds()))
    except Exception:
        return 0


@_cmd("getHostEnvironment")
def c_get_host_environment(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    workdir = data.get("workdir") or h.workdir or "/"
    gpu = (h.spec or {}).get("gpu")
    packages = [{"name": n, "version": v} for n, v in [
        ("numpy", "2.3.1"), ("pandas", "2.3.0"), ("scipy", "1.15.2"),
        ("matplotlib", "3.10.3"), ("pytorch", "2.8.0"), ("biopython", "1.86")]]
    env = {"hostId": h.id, "workdir": workdir, "image": h.image,
           "os": "linux (remote)" if h.kind == "ssh" else "Ubuntu 24.04 LTS",
           "kernel": "6.8.0-clawsgo", "python": "3.13.12", "node": "22.22.2",
           "git": "2.53.0", "latex": "TeX Live 2026", "cuda": "12.8" if gpu else None,
           "gpu": [{"name": gpu, "driver": "580.65", "cuda": "12.8"}] if gpu else [],
           "packages": packages, "env": {"CLAWSGO_WORKSPACE": workdir, "LANG": "en_US.UTF-8"},
           "checkedAt": now()}
    return {"environment": env, **env}


@_cmd("getHostStorage")
def c_get_host_storage(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    storage = _host_storage(h)
    return {"storage": storage, **storage}


def _normalize_path(path):
    if not path:
        return "/"
    path = path.replace("\\", "/")
    if not path.startswith("/"):
        path = "/" + path
    parts = [p for p in path.split("/") if p]
    return "/" + "/".join(parts)


@_cmd("getHostDirectories")
def c_get_host_directories(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    path = _normalize_path(data.get("path") or h.workdir or "/")
    entries = _WORKSPACE_TREE.get(path)
    if entries is None:
        return {"exists": False, "path": data.get("path") or "/", "entries": [],
                "directories": [], "items": [], "total": 0,
                "workdir": h.workdir, "home": "/home/clawsgo"}
    rows = []
    for e in entries:
        if e[0] == "dir":
            rows.append({"name": e[1], "filename": e[1], "path": e[2], "type": "dir",
                         "kind": "dir", "size": 0, "mtime": now()})
        else:
            rows.append({"name": e[1], "filename": e[1], "path": e[3], "type": "file",
                         "kind": "file", "size": e[3], "mtime": now()})
    rows.sort(key=lambda r: (r["type"] != "dir", r["name"].lower()))
    parent = None if path == "/" else "/" + "/".join(path.split("/")[:-1])
    return {"exists": True, "path": path, "parent": parent, "entries": rows,
            "directories": [r for r in rows if r["type"] == "dir"],
            "items": rows, "total": len(rows), "workdir": h.workdir, "home": "/home/clawsgo"}


@_cmd("createHostDirectory")
def c_create_host_directory(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    path = _normalize_path(req(data, "path"))
    if _WORKSPACE_TREE.get(path):
        return {"ok": True, "created": False, "existed": True, "path": path}
    _WORKSPACE_TREE[path] = []
    return {"ok": True, "created": True, "existed": False, "path": path}


@_cmd("getHostSkills")
def c_get_host_skills(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    rows = [s for s in db.query(m.Skill).all()
            if s.hostId == h.id or s.teamId == h.teamId]
    skills = [S.skill_row(db, s) for s in rows]
    return {"skills": skills, "items": skills, "total": len(skills)}


@_cmd("getHostSkillDetail")
def c_get_host_skill_detail(self, db, data):
    self._own_host(db, req(data, "hostId"), data)
    key = data.get("slug")
    s = next((x for x in db.query(m.Skill).all() if x.name == key or x.slug == key or x.id == key), None)
    if s is None:
        raise notFound("技能")
    return {"skill": S.skill_row(db, s), "detail": S.skill_row(db, s)}


@_cmd("getSshServers")
def c_get_ssh_servers(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    rows = db.query(m.SshServer).filter_by(teamId=team_id).all()
    servers = [S.ssh_server_row(db, s) for s in rows]
    return {"sshServers": servers, "items": servers, "total": len(servers)}


@_cmd("createSshServer")
def c_create_ssh_server(self, db, data):
    s = m.SshServer(id=rid("ssh"), teamId=self._ctx_team(db, data) or "",
                    userId=self.user["id"], name=req(data, "name"),
                    hostname=req(data, "hostname"), port=int(data.get("port") or 22),
                    username=data.get("username") or "root", authType=data.get("authType") or "key",
                    status="unknown", latencyMs=None, lastProbeAt=None, createdAt=now())
    db.add(s)
    return {"sshServer": S.ssh_server_row(db, s), "id": s.id}


@_cmd("updateSshServer")
def c_update_ssh_server(self, db, data):
    s = db.get(m.SshServer, req(data, "sshServerId"))
    if s is None:
        raise notFound("SSH服务器")
    for k in ("name", "hostname", "port", "username", "authType"):
        if data.get(k) is not None:
            setattr(s, k, int(data[k]) if k == "port" else data[k])
    return {"sshServer": S.ssh_server_row(db, s)}


@_cmd("deleteSshServer")
def c_delete_ssh_server(self, db, data):
    s = db.get(m.SshServer, req(data, "sshServerId"))
    if s is None:
        raise notFound("SSH服务器")
    db.delete(s)
    for h in db.query(m.Host).filter_by(name=s.name, teamId=s.teamId).all():
        if not db.query(m.SshServer).filter_by(name=h.name, teamId=h.teamId).first():
            h.status = "offline"
    return {"ok": True, "id": s.id}


@_cmd("probeSshServers")
def c_probe_ssh_servers(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    if data.get("sshServerId"):
        rows = [s for s in db.query(m.SshServer).all() if s.id == data["sshServerId"]]
    else:
        rows = db.query(m.SshServer).filter_by(teamId=team_id).all()
    results = []
    for s in rows:
        ok = s.name != "lab-a100"  # deterministic: seeded ssh host stays offline
        s.status = "online" if ok else "unreachable"
        s.latencyMs = 42 if ok else None
        s.lastProbeAt = now()
        row = S.ssh_server_row(db, s)
        row["probe"] = {"status": s.status, "latencyMs": s.latencyMs}
        results.append(row)
        for h in db.query(m.Host).filter_by(name=s.name, teamId=s.teamId).all():
            h.status = "running" if ok else "offline"
            if ok:
                h.lastSeenAt = now()
    return {"sshServers": results, "results": results, "items": results, "total": len(results)}


@_cmd("openHostView")
def c_open_host_view(self, db, data):
    self._own_host(db, req(data, "hostId"), data)
    return {"ok": True, "hostId": data["hostId"], "available": False,
            "reason": "local-reproduction: no desktop host process",
            "url": "http://127.0.0.1:8080/"}


@_cmd("pickHostDirectory")
def c_pick_host_directory(self, db, data):
    h = self._own_host(db, req(data, "hostId"), data)
    return {"path": h.workdir or "/", "hostId": h.id, "root": h.workdir or "/"}


@_cmd("adminGetCloudHosts")
def c_admin_get_cloud_hosts(self, db, data):
    self._admin_only(db)
    rows = [h for h in db.query(m.Host).filter_by(teamId=self._ctx_team(db, data)).all()
            if h.kind == "cloud"]
    hosts = [S.host_row(db, h) for h in rows]
    return _listout("hosts", hosts, len(hosts), data)


@_cmd("adminRebuildHost")
def c_admin_rebuild_host(self, db, data):
    self._admin_only(db)
    return c_rebuild_host(self, db, data)


# ===========================================================================
# teams domain
# ===========================================================================
@_cmd("getTeams")
def c_get_teams(self, db, data):
    u = self._user(db)
    mems = db.query(m.TeamMember).filter_by(userId=u.id).all()
    team_ids = [] if u.role == "super_admin" else [mm.teamId for mm in mems]
    rows = db.query(m.Team).all()
    if u.role != "super_admin":
        rows = [t for t in rows if t.id in team_ids]
    teams = [S.team_row(db, t, u.id) for t in rows]
    return {"teams": teams, "items": teams, "total": len(teams)}


@_cmd("createTeam")
def c_create_team(self, db, data):
    name = (data.get("name") or "").strip()
    if not name:
        raise badRequest("团队名称不能为空", "INVALID_TEAM_NAME")
    t = m.Team(id=rid("t"), name=name, ownerId=self.user["id"], plan="free",
               memberLimit=int(data.get("memberLimit") or 3), creditBalance=0, createdAt=now())
    db.add(t)
    db.add(m.TeamMember(id=rid("tmem"), teamId=t.id, userId=self.user["id"],
                        role="owner", joinedAt=now()))
    return {"team": S.team_row(db, t, self.user["id"])}


@_cmd("updateTeam")
def c_update_team(self, db, data):
    for _ in ():  # keep linters quiet about unused vars
        break
    t = self._own_team(db, req(data, "teamId"), require_admin=True)
    if (data.get("name") or "").strip():
        t.name = data["name"].strip()
    return {"team": S.team_row(db, t, self.user["id"])}


@_cmd("deleteTeam")
def c_delete_team(self, db, data):
    t = self._own_team(db, req(data, "teamId"))
    if t.id == self.user["id"]:
        raise badRequest("个人空间不可删除", "PERSONAL_TEAM")
    if t.ownerId != self.user["id"] and self.user["role"] != "super_admin":
        raise forbidden("只有所有者可以解散团队")
    tid = t.id
    db.query(m.TeamMember).filter_by(teamId=tid).delete()
    db.query(m.TeamInvitation).filter_by(teamId=tid).delete()
    db.delete(t)
    return {"ok": True, "id": tid}


@_cmd("setMemberLimit")
def c_set_member_limit(self, db, data):
    t = self._own_team(db, req(data, "teamId"), require_admin=True)
    limit = data.get("memberLimit")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise badRequest("成员上限不合法")
    if limit < 1:
        raise badRequest("成员上限不合法")
    count = db.query(m.TeamMember).filter_by(teamId=t.id).count()
    if limit < count:
        raise conflict(f"当前已有{count}名成员，上限不能低于此数")
    t.memberLimit = limit
    return {"team": S.team_row(db, t, self.user["id"]), "ok": True}


@_cmd("getTeamMembers")
def c_get_team_members(self, db, data):
    team_id = data.get("teamId") or self._ctx_team(db, data)
    self._own_team(db, team_id)
    rows = db.query(m.TeamMember).filter_by(teamId=team_id).all()
    members = [S.team_member_row(db, r) for r in rows]
    return _listout("members", members, len(members), data)


@_cmd("removeTeamMember")
def c_remove_team_member(self, db, data):
    t = self._own_team(db, req(data, "teamId"), require_admin=True)
    uid = req(data, "userId")
    if uid == t.ownerId:
        raise badRequest("不能移除团队所有者", "CANNOT_REMOVE_OWNER")
    row = db.query(m.TeamMember).filter_by(teamId=t.id, userId=uid).first()
    if row is None:
        raise notFound("成员")
    db.delete(row)
    return {"ok": True}


@_cmd("updateTeamMemberRole")
def c_update_team_member_role(self, db, data):
    t = self._own_team(db, req(data, "teamId"), require_admin=True)
    role = req(data, "role")
    if role not in ("admin", "member"):
        raise badRequest("角色只能是 admin 或 member")
    uid = req(data, "userId")
    if uid == t.ownerId:
        raise badRequest("不能修改所有者的角色", "CANNOT_CHANGE_OWNER")
    mem = db.query(m.TeamMember).filter_by(teamId=t.id, userId=uid).first()
    if mem is None:
        raise notFound("成员")
    mem.role = role
    return {"ok": True, "member": S.team_member_row(db, mem)}


@_cmd("transferTeamOwnership")
def c_transfer_team_ownership(self, db, data):
    t = self._own_team(db, req(data, "teamId"))
    if t.ownerId != self.user["id"] and self.user["role"] != "super_admin":
        raise forbidden("只有所有者可以转让团队")
    uid = req(data, "userId")
    target = db.query(m.TeamMember).filter_by(teamId=t.id, userId=uid).first()
    if target is None:
        raise notFound("成员")
    cur = db.query(m.TeamMember).filter_by(teamId=t.id, userId=self.user["id"]).first()
    if cur:
        cur.role = "admin"
    target.role = "owner"
    t.ownerId = uid
    return {"ok": True, "team": S.team_row(db, t, self.user["id"])}


@_cmd("leaveTeam")
def c_leave_team(self, db, data):
    t = self._own_team(db, req(data, "teamId"))
    if t.ownerId == self.user["id"]:
        raise badRequest("所有者不能直接退出，请先转让团队", "OWNER_CANNOT_LEAVE")
    db.query(m.TeamMember).filter_by(teamId=t.id, userId=self.user["id"]).delete()
    return {"ok": True}


@_cmd("getTeamInvitations")
def c_get_team_invitations(self, db, data):
    t = self._own_team(db, req(data, "teamId"))
    rows = db.query(m.TeamInvitation).filter_by(teamId=t.id).all()
    invs = [S.team_invitation_row(db, inv) for inv in rows]
    return _listout("invitations", invs, len(invs), data)


@_cmd("createTeamInvitation")
def c_create_team_invitation(self, db, data):
    t = self._own_team(db, req(data, "teamId"), require_admin=True)
    phone = data.get("phone")
    email = data.get("email")
    if not phone and not email:
        raise badRequest("需要手机号或邮箱", "INVALID_INVITEE")
    target = None
    if phone:
        target = db.query(m.User).filter_by(phone=phone).first()
    if email and target is None:
        target = db.query(m.User).filter_by(email=email).first()
    if target and db.query(m.TeamMember).filter_by(teamId=t.id, userId=target.id).first():
        raise conflict("该用户已是团队成员")
    inv = m.TeamInvitation(id=rid("inv"), teamId=t.id, inviterId=self.user["id"],
                           inviteeId=target.id if target else None, phone=phone, email=email,
                           role=data.get("role") or "member", status="pending",
                           createdAt=now(), expiresAt=_shift_iso(now(), 7))
    db.add(inv)
    return {"invitation": S.team_invitation_row(db, inv), "ok": True}


@_cmd("cancelTeamInvitation")
def c_cancel_team_invitation(self, db, data):
    inv = db.get(m.TeamInvitation, req(data, "invitationId"))
    if inv is None:
        raise notFound("邀请")
    self._own_team(db, inv.teamId, require_admin=True)
    inv.status = "cancelled"
    return {"ok": True}


@_cmd("getMyInvitations")
def c_get_my_invitations(self, db, data):
    u = self._user(db)
    rows = db.query(m.TeamInvitation).filter_by(inviteeId=u.id).all()
    rows = [r for r in rows if r.status == "pending"]
    out = []
    for inv in rows:
        team = db.get(m.Team, inv.teamId)
        row = S.team_invitation_row(db, inv)
        row["teamName"] = team.name if team else ""
        row["team"] = S.team_row(db, team, u.id) if team else None
        out.append(row)
    return _listout("invitations", out, len(out), data)


@_cmd("acceptTeamInvitation")
def c_accept_team_invitation(self, db, data):
    u = self._user(db)
    inv = db.get(m.TeamInvitation, req(data, "invitationId"))
    if inv is None:
        raise notFound("邀请")
    if inv.status != "pending":
        raise badRequest("邀请已失效", "INVITATION_NOT_PENDING")
    if inv.expiresAt and inv.expiresAt < now():
        inv.status = "expired"
        raise badRequest("邀请已过期", "INVITATION_EXPIRED")
    team = db.get(m.Team, inv.teamId)
    if team is None:
        raise notFound("团队")
    count = db.query(m.TeamMember).filter_by(teamId=team.id).count()
    if team.memberLimit and count >= team.memberLimit:
        raise conflict("团队席位已满", "TEAM_FULL")
    if not db.query(m.TeamMember).filter_by(teamId=team.id, userId=u.id).first():
        db.add(m.TeamMember(id=rid("tmem"), teamId=team.id, userId=u.id,
                            role=inv.role or "member", joinedAt=now()))
    inv.status = "accepted"
    inv.inviteeId = u.id
    return {"ok": True, "team": S.team_row(db, team, u.id)}


@_cmd("rejectTeamInvitation")
def c_reject_team_invitation(self, db, data):
    inv = db.get(m.TeamInvitation, req(data, "invitationId"))
    if inv is None:
        raise notFound("邀请")
    inv.status = "rejected"
    return {"ok": True}


@_cmd("claimInvite")
def c_claim_invite(self, db, data):
    u = self._user(db)
    code = (data.get("code") or "").strip().upper()
    if not code:
        raise badRequest("缺少邀请码", "INVALID_INVITE_CODE")
    ic = next((c for c in db.query(m.InviteCode).all()
               if (c.code or "").upper() == code and c.active is not False), None)
    if ic is None:
        raise badRequest("邀请码无效", "INVALID_INVITE_CODE")
    if ic.maxUses and ic.usedCount >= ic.maxUses:
        raise badRequest("邀请码已用尽", "INVITE_CODE_EXHAUSTED")
    team = db.get(m.Team, ic.teamId)
    if team is None:
        raise notFound("团队")
    if not db.query(m.TeamMember).filter_by(teamId=team.id, userId=u.id).first():
        db.add(m.TeamMember(id=rid("tmem"), teamId=team.id, userId=u.id,
                            role="member", joinedAt=now(), invitedByCode=code))
        ic.usedCount = (ic.usedCount or 0) + 1
    credits = 0
    if ic.rewardCredits:
        team.creditBalance = (team.creditBalance or 0) + ic.rewardCredits
        credits = ic.rewardCredits
        db.add(m.CreditLedger(id=rid("cl"), teamId=team.id, userId=u.id,
                              delta=ic.rewardCredits, reason="invite_reward",
                              balanceAfter=team.creditBalance,
                              note=f"邀请码 {code}", createdAt=now()))
    return {"ok": True, "team": S.team_row(db, team, u.id), "credits": credits}


def _shift_iso(iso, days):
    from datetime import timedelta
    try:
        return (datetime.fromisoformat(iso) + timedelta(days=days)).isoformat().replace("+00:00", "Z")
    except Exception:
        return iso


# ===========================================================================
# billing domain
# ===========================================================================
def _subscription_for(self, db, team_id):
    sub = db.query(m.Subscription).filter_by(teamId=team_id).first()
    if sub is None:
        sub = m.Subscription(id=rid("sub"), teamId=team_id, plan="free", planId="free",
                             status="active", seats=1, priceMonthly=0, currency="CNY",
                             currentPeriodEnd=None, cycleStartAt=now(), planEndAt=None,
                             monthlyMilli=0, createdAt=now())
        db.add(sub)
    return sub


def _grant_plan(self, db, team_id, plan_id, months=1, note=None):
    months = months or 1
    sub = _subscription_for(self, db, team_id)
    sub.plan = plan_id
    sub.planId = plan_id
    sub.status = "active"
    sub.priceMonthly = P.PLANS[plan_id]["monthlyCents"]
    sub.cycleStartAt = now()
    sub.planEndAt = _shift_iso(now(), 30 * months)
    sub.currentPeriodEnd = sub.planEndAt
    sub.monthlyMilli = P.PLANS[plan_id]["monthlyCredits"] * 1000
    team = db.get(m.Team, team_id)
    if team:
        team.plan = plan_id
        monthly = P.PLANS[plan_id]["monthlyCredits"]
        if monthly > 0:
            team.creditBalance = (team.creditBalance or 0) + monthly
            db.add(m.CreditLedger(id=rid("cl"), teamId=team_id, userId=self.user.get("id"),
                                  delta=monthly, reason="topup", balanceAfter=team.creditBalance,
                                  note=note or f"{plan_id} · {months} 个月", createdAt=now()))
    return sub


@_cmd("getSubscription")
def c_get_subscription(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    self._own_team(db, team_id) if team_id else None
    sub = _subscription_for(self, db, team_id)
    team = db.get(m.Team, team_id)
    spec = P.plan_spec(sub.planId or sub.plan or "free")
    plan_id = sub.planId or sub.plan or "free"
    return {"subscription": {
        **S.subscription_row(db, sub),
        "planId": plan_id, "plan": plan_id,
        "planLabel": P.PLAN_TITLES.get(plan_id, plan_id),
        "seats": sub.seats or 1,
        "creditBalance": team.creditBalance if team else 0,
        "monthlyCredits": P.PLANS[plan_id]["monthlyCredits"],
        "spec": spec,
        "canUpgrade": plan_id == "free" or plan_id in P.SELF_SERVE,
        "canInvoice": plan_id in P.INVOICE_PLANS,
        "autoRenew": True}}


@_cmd("getPlans")
def c_get_plans(self, db, data):
    self._user(db)
    return {"plans": P.all_plan_specs(), "topupTiers": P.topup_tiers(),
            "gateways": P.GATEWAYS, "monthOptions": P.MONTH_OPTIONS, "selfServe": P.SELF_SERVE}


@_cmd("quoteUpgrade")
def c_quote_upgrade(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    plan_id = req(data, "planId")
    months = int(data.get("months") or 1)
    sub = _subscription_for(self, db, team_id)
    cur = sub.planId or sub.plan or "free"
    if P.plan_rank(plan_id) <= P.plan_rank(cur):
        raise badRequest("目标套餐不高于当前套餐", "PLAN_NOT_UPGRADE")
    if months not in P.MONTH_OPTIONS and months not in (1, 12):
        raise badRequest("不识别的付费周期", "INVALID_CYCLE")
    due = P.plan_cycle_cents(plan_id, months)
    return {"quote": {"listCents": due, "prorationCents": 0, "dueCents": max(1, due)}}


@_cmd("createPaymentOrder")
def c_create_payment_order(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    self._own_team(db, team_id)
    kind = data.get("kind") or "plan"
    provider = data.get("provider") or "wechat"
    if kind == "plan":
        plan_id = req(data, "planId")
        if plan_id not in P.PLANS:
            raise badRequest("未知套餐", "INVALID_PLAN")
        months = int(data.get("months") or 1)
        amount = data.get("priceCents") or P.plan_cycle_cents(plan_id, months)
        credit_milli = P.PLANS[plan_id]["monthlyCredits"] * 1000 * months
        bonus_milli = 0
    else:  # topup
        price_cents = int(data.get("priceCents") or 0)
        tier = next((t for t in P.topup_tiers() if t["priceCents"] == price_cents), None)
        if tier is None:
            raise badRequest("不支持的充值档位", "INVALID_TOPUP_AMOUNT")
        amount = price_cents
        credit_milli = tier["creditMilli"]
        bonus_milli = tier["bonusMilli"]
        plan_id = None
        months = 0
    o = m.PaymentOrder(id=rid("po"), orderNo="CG" + uuid.uuid4().hex[:8].upper(),
                       teamId=team_id, userId=self.user["id"], kind=kind, planId=plan_id,
                       months=months, amountCents=amount, currency="CNY", provider=provider,
                       gateway=provider, status="pending",
                       payUrl=f"mock://pay/{uuid.uuid4().hex[:12]}",
                       creditMilli=credit_milli, bonusMilli=bonus_milli,
                       providerTradeNo=None, refundedAt=None, paidAt=None,
                       createdAt=now(), expiresAt=_shift_iso(now(), 1))
    db.add(o)
    row = S.payment_order_row(db, o)
    row["amount"] = amount
    return {"order": row, "payUrl": o.payUrl}


def _settle_if_due(self, db, o):
    if o.status != "pending":
        return o
    try:
        created = datetime.fromisoformat(o.createdAt)
        elapsed = (datetime.now(timezone.utc) - created).total_seconds() * 1000
    except Exception:
        elapsed = 99999
    if elapsed >= 6000:
        o.status = "paid"
        o.paidAt = now()
        o.providerTradeNo = "TP" + uuid.uuid4().hex[:16]
        team = db.get(m.Team, o.teamId)
        grant = (o.creditMilli or 0) // 1000 if (o.creditMilli or 0) > 0 else 0
        if o.kind == "plan":
            _grant_plan(self, db, o.teamId, o.planId, o.months, note=f"套餐 {o.planId}")
        elif grant:
            team.creditBalance = (team.creditBalance or 0) + grant + (o.bonusMilli or 0) // 1000
            db.add(m.CreditLedger(id=rid("cl"), teamId=o.teamId, userId=self.user.get("id"),
                                  delta=grant + (o.bonusMilli or 0) // 1000, reason="topup",
                                  balanceAfter=team.creditBalance,
                                  note=f"充值 {o.orderNo}", createdAt=now()))
    return o


@_cmd("syncPaymentOrder")
def c_sync_payment_order(self, db, data):
    o = db.get(m.PaymentOrder, req(data, "orderId"))
    if o is None:
        raise notFound("订单")
    o = _settle_if_due(self, db, o)
    return {"order": S.payment_order_row(db, o)}


@_cmd("recheckPaymentOrders")
def c_recheck_payment_orders(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    pending = db.query(m.PaymentOrder).filter_by(teamId=team_id, status="pending").all()
    recovered = 0
    for o in pending:
        before = o.status
        _settle_if_due(self, db, o)
        if o.status != before:
            recovered += 1
    return {"checked": len(pending), "recovered": recovered, "ok": True}


@_cmd("getPaymentOrders")
def c_get_payment_orders(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    rows = [r for r in db.query(m.PaymentOrder).filter_by(teamId=team_id).all()
            if r.status != "pending" or (r.createdAt or "") >= datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")]
    # settle any due pending
    rows = [_settle_if_due(self, db, r) for r in rows]
    rows = [S.payment_order_row(db, r) for r in rows]
    rows.sort(key=lambda r: r["createdAt"] or "", reverse=True)
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    return _listout("orders", rows, total, data, 20, 200)


@_cmd("getInvoices")
def c_get_invoices(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    rows = [S.invoice_row(db, i) for i in db.query(m.Invoice).filter_by(teamId=team_id).all()]
    rows.sort(key=lambda r: r["createdAt"] or "", reverse=True)
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    paid = sum((o.amountCents or 0) for o in db.query(m.PaymentOrder).filter_by(
        teamId=team_id, status="paid").all())
    issued = sum(i.amount for i in db.query(m.Invoice).filter_by(
        teamId=team_id).all() if i.status in ("issued", "requested"))
    return {"invoices": rows, "items": rows, "total": total,
            "limit": _limit(data, 20, 200), "offset": _offset(data),
            "available": max(0, paid - issued)}


@_cmd("createInvoice")
def c_create_invoice(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    team = self._own_team(db, team_id)
    sub = _subscription_for(self, db, team_id)
    if (sub.planId or sub.plan) not in P.INVOICE_PLANS:
        raise badRequest("当前套餐不支持开票", "INVOICE_PLAN_NOT_ELIGIBLE")
    try:
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        raise badRequest("开票金额不合法", "INVALID_AMOUNT")
    if amount <= 0:
        raise badRequest("开票金额不合法", "INVALID_AMOUNT")
    if data.get("type") == "vat_special":
        tax_no = data.get("taxNo") or ""
        if not re.fullmatch(r"[0-9A-Za-z]{15,20}", tax_no):
            raise badRequest("纳税人识别号格式不正确（15–20 位字母数字）", "INVALID_TAX_NO")
    inv = m.Invoice(id=rid("inv"), teamId=team_id, userId=self.user["id"],
                    orderId=data.get("orderId"), amount=amount,
                    title=data.get("title") or team.name, taxNo=data.get("taxNo") or "",
                    type=data.get("type") or "normal", status="requested",
                    email=data.get("email"), invoiceNo=None, note=data.get("note"),
                    createdAt=now(), issuedAt=None)
    db.add(inv)
    return {"invoice": S.invoice_row(db, inv)}


@_cmd("deleteInvoice")
def c_delete_invoice(self, db, data):
    inv = db.get(m.Invoice, req(data, "invoiceId"))
    if inv is None:
        raise notFound("发票")
    self._own_team(db, inv.teamId)
    if inv.status == "issued":
        raise badRequest("已开具的发票不能删除", "INVOICE_ISSUED")
    db.delete(inv)
    return {"ok": True}


@_cmd("redeemCode")
def c_redeem_code(self, db, data):
    u = self._user(db)
    code = (data.get("code") or "").strip().upper()
    if not code:
        raise badRequest("请输入兑换码", "REDEEM_CODE_NOT_FOUND")
    row = next((r for r in db.query(m.RedeemCode).all()
                if (r.code or "").upper() == code), None)
    if row is None:
        raise badRequest("兑换码不存在", "REDEEM_CODE_NOT_FOUND")
    if row.disabled:
        raise badRequest("兑换码已作废", "REDEEM_CODE_INVALID")
    if row.usedBy:
        raise badRequest("兑换码已被使用", "REDEEM_CODE_EXHAUSTED")
    team = db.get(m.Team, self._ctx_team(db, data) or "")
    row.usedBy = u.id
    row.usedAt = now()
    if team:
        team.creditBalance = (team.creditBalance or 0) + row.credits
        db.add(m.CreditLedger(id=rid("cl"), teamId=team.id, userId=u.id,
                              delta=row.credits, reason="redeem_code",
                              balanceAfter=team.creditBalance, note=code, createdAt=now()))
        return {"ok": True, "credits": row.credits, "balance": team.creditBalance}
    return {"ok": True, "credits": row.credits, "balance": 0}


@_cmd("getMyInviteCodes", "getInviteCodes")
def c_get_my_invite_codes(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    rows = [S.invite_code_row(db, c) for c in db.query(m.InviteCode).filter_by(teamId=team_id).all()]
    members = db.query(m.TeamMember).filter_by(teamId=team_id).all()
    for row in rows:
        code = row["code"]
        row["invitees"] = [mm.userId for mm in members if (mm.invitedByCode or "").upper() == code.upper()]
        row["url"] = f"mock://claim?code={code}"
    return {"inviteCodes": rows, "items": rows, "total": len(rows),
            "codes": [r["code"] for r in rows]}


@_cmd("createInviteCode")
def c_create_invite_code(self, db, data):
    code = (data.get("code") or "CG" + uuid.uuid4().hex[:6].upper())
    c = m.InviteCode(id=rid("ic"), teamId=self._ctx_team(db, data) or "", userId=self.user["id"],
                     code=code, name=data.get("name") or "", usedCount=0,
                     maxUses=int(data.get("maxUses") or 0),
                     rewardCredits=int(data.get("rewardCredits") or 0), active=True, createdAt=now())
    db.add(c)
    return {"inviteCode": S.invite_code_row(db, c), "ok": True}


@_cmd("renameInviteCode")
def c_rename_invite_code(self, db, data):
    c = None
    if data.get("inviteCodeId"):
        c = db.get(m.InviteCode, data["inviteCodeId"])
    elif data.get("code"):
        c = next((x for x in db.query(m.InviteCode).all() if x.code == data["code"]), None)
    if c is None:
        raise notFound("邀请码")
    self._own_team(db, c.teamId)
    if data.get("name") is not None:
        c.name = data["name"]
    if data.get("maxUses") is not None:
        c.maxUses = int(data["maxUses"])
    if data.get("active") is not None:
        c.active = bool(data["active"])
    return {"inviteCode": S.invite_code_row(db, c), "ok": True}


@_cmd("getPaymentDocuments")
def c_get_payment_documents(self, db, data):
    o = db.get(m.PaymentOrder, req(data, "orderId"))
    if o is None:
        raise notFound("订单")
    if o.teamId != self._ctx_team(db, data):
        raise ApiError("FORBIDDEN", "无权访问该订单", 403)
    invs = [S.invoice_row(db, i) for i in db.query(m.Invoice).filter_by(orderId=o.id).all()]
    return {"documents": [], "order": S.payment_order_row(db, o), "invoices": invs, "total": len(invs)}


# ===========================================================================
# support domain
# ===========================================================================
@_cmd("getMyTickets", "getTickets")
def c_get_my_tickets(self, db, data):
    team_id = self._ctx_team(db, data) or ""
    u = self._user(db)
    if u.role in ("admin", "super_admin") and data.get("mine") is False:
        rows = [t for t in db.query(m.Ticket).filter_by(teamId=team_id).all()]
    else:
        rows = [t for t in db.query(m.Ticket).filter_by(teamId=team_id, userId=u.id).all()]
    rows.sort(key=lambda r: r.createdAt or "", reverse=True)
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 50, 200)]
    tickets = []
    for t in rows:
        row = S.ticket_row(db, t)
        msgs = [S.ticket_message_row(db, x) for x in db.query(m.TicketMessage).filter_by(
            ticketId=t.id).order_by(m.TicketMessage.createdAt.asc()).all()]
        row["messages"] = msgs
        tickets.append(row)
    return _listout("tickets", tickets, total, data, 50, 200)


@_cmd("getTicket")
def c_get_ticket(self, db, data):
    t = self._own_ticket(db, req(data, "id") or data.get("ticketId"))
    msgs = [S.ticket_message_row(db, x) for x in db.query(m.TicketMessage).filter_by(
        ticketId=t.id).order_by(m.TicketMessage.createdAt.asc()).all()]
    return {"ticket": S.ticket_row(db, t), "messages": msgs,
            "truncated": False, "unreadCount": t.unreadForUser or 0}


@_cmd("createTicket")
def c_create_ticket(self, db, data):
    subject = (data.get("subject") or "").strip()
    body = str(data.get("body") or data.get("content") or "").strip()
    if not subject:
        raise badRequest("请填写工单标题", "INVALID_SUBJECT")
    if not body:
        raise badRequest("请填写工单内容", "INVALID_BODY")
    seq = self._counter(db, "ticket").value + 1
    self._counter(db, "ticket").value = seq
    t = m.Ticket(id=rid("t"), seq=seq, teamId=self._ctx_team(db, data) or "",
                 userId=self.user["id"], type=data.get("type") or "general",
                 subject=subject, status="open", priority=data.get("priority") or "normal",
                 createdAt=now(), updatedAt=now(), lastMessagePreview=body[:120],
                 lastMessageAttachments=len(data.get("attachments") or []),
                 unreadForUser=0, unreadForAdmin=1)
    db.add(t)
    db.add(m.TicketMessage(id=rid("tm"), ticketId=t.id, authorId=self.user["id"],
                           authorRole="user", body=body,
                           attachments=data.get("attachments") or [], createdAt=now()))
    return {"ticket": S.ticket_row(db, t), "id": t.id}


@_cmd("replyTicket")
def c_reply_ticket(self, db, data):
    t = self._own_ticket(db, req(data, "id") or data.get("ticketId"))
    if t.status in ("closed", "resolved", "deleted"):
        raise badRequest("工单已关闭，无法回复", "TICKET_CLOSED")
    body = str(data.get("body") or data.get("content") or "").strip()
    if not body:
        raise badRequest("回复内容不能为空", "INVALID_BODY")
    author_role = "admin" if self.user["role"] in ("admin", "super_admin") else "user"
    db.add(m.TicketMessage(id=rid("tm"), ticketId=t.id, authorId=self.user["id"],
                           authorRole=author_role, body=body,
                           attachments=data.get("attachments") or [], createdAt=now()))
    t.status = "open"
    t.updatedAt = now()
    t.lastMessagePreview = body[:120]
    t.lastMessageAttachments = len(data.get("attachments") or [])
    if author_role == "admin":
        t.unreadForUser = (t.unreadForUser or 0) + 1
        t.unreadForAdmin = 0
    else:
        t.unreadForAdmin = (t.unreadForAdmin or 0) + 1
        t.unreadForUser = 0
    return {"ok": True, "ticket": S.ticket_row(db, t)}


@_cmd("markTicketSeen")
def c_mark_ticket_seen(self, db, data):
    t = self._own_ticket(db, req(data, "id") or data.get("ticketId"))
    t.unreadForUser = 0
    return {"ok": True}


@_cmd("getTicketUnreadCount")
def c_get_ticket_unread_count(self, db, data):
    u = self._user(db)
    total = sum(t.unreadForUser or 0 for t in db.query(m.Ticket).filter_by(userId=u.id).all())
    return {"count": total}


@_cmd("getActiveAnnouncements")
def c_get_active_announcements(self, db, data):
    self._user(db)
    rows = [a for a in db.query(m.Announcement).filter_by(active=True).all()]
    rows.sort(key=lambda r: r.publishedAt or "", reverse=True)
    anns = [S.announcement_row(db, a) for a in rows]
    return _listout("announcements", anns, len(anns), data)


@_cmd("getNotifications")
def c_get_notifications(self, db, data):
    u = self._user(db)
    rows = [a for a in db.query(m.AuditLog).filter_by(actorId=u.id).order_by(
        m.AuditLog.createdAt.desc()).all()]
    data["limit"] = data.get("limit", 20)
    notifs = [{"id": a.id, "type": "audit", "action": a.action, "detail": a.detail or "",
               "read": True, "createdAt": a.createdAt} for a in rows[:_limit(data, 20, 100)]]
    return {"notifications": notifs, "items": notifs, "total": len(notifs),
            "unread": 0, "limit": _limit(data, 20, 100), "offset": _offset(data)}


@_cmd("uploadTicketAttachment")
def c_upload_attachment(self, db, data):
    name = data.get("name") or "file.bin"
    aid = rid("att")
    return {"attachment": {"id": aid, "name": name, "size": 0,
                           "mimeType": "application/octet-stream",
                           "url": f"mock://attachment/{aid}"},
            "id": aid, "url": f"mock://attachment/{aid}"}


@_cmd("adminGetTickets", "adminGetTicketStats", "adminCloseTicket", "adminDeleteTicket")
def c_admin_tickets(self, db, data):
    self._admin_only(db)
    cmd = "adminGetTickets"
    # The registered key is not passed; infer from the payload shape.
    if data.get("id") or data.get("ticketId"):
        t = self._own_ticket(db, data.get("id") or data.get("ticketId"))
        msgs = [S.ticket_message_row(db, x) for x in db.query(m.TicketMessage).filter_by(
            ticketId=t.id).order_by(m.TicketMessage.createdAt.asc()).all()]
        return {"ticket": S.ticket_row(db, t), "messages": msgs, "truncated": False}
    rows = [S.ticket_row(db, t) for t in db.query(m.Ticket).all()]
    rows.sort(key=lambda r: r["createdAt"] or "", reverse=True)
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    return _listout("tickets", rows, total, data, 20, 200)


# ===========================================================================
# admin domain
# ===========================================================================
@_cmd("adminGetUsers", "adminGetUserDetail")
def c_admin_get_users(self, db, data):
    self._admin_only(db)
    query = (data.get("query") or "").strip().lower()
    rows = db.query(m.User).all()
    if query:
        rows = [u for u in rows if query in (u.name or "").lower() or query in (u.phone or "")
                or query in (u.email or "").lower() or query in (u.id or "").lower()]
    if data.get("role"):
        rows = [u for u in rows if u.role == data["role"]]
    if data.get("banned") is not None:
        rows = [u for u in rows if u.banned == bool(data["banned"])]
    rows.sort(key=lambda u: u.createdAt or "", reverse=True)
    total = len(rows)
    page = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    users = []
    for u in page:
        row = S.user_row(u)
        row["plan"] = u.plan or "free"
        row["teams"] = db.query(m.TeamMember).filter_by(userId=u.id).count()
        row["conversations"] = db.query(m.Conversation).filter_by(userId=u.id).count()
        last = db.query(m.Conversation).filter_by(userId=u.id).first()
        row["lastActiveAt"] = last.lastMessageAt if last else u.createdAt
        users.append(row)
    return _listout("users", users, total, data, 20, 200)


@_cmd("adminGetTeams", "adminGetTeamDetail", "adminGetTeamMembers", "adminGetTeamHosts")
def c_admin_get_teams(self, db, data):
    self._admin_only(db)
    if data.get("teamId"):
        team = db.get(m.Team, data["teamId"])
        if team is None:
            raise notFound("团队")
        owner = db.get(m.User, team.ownerId)
        members = [S.team_member_row(db, mm) for mm in db.query(m.TeamMember).filter_by(teamId=team.id).all()]
        hosts = [S.host_row(db, h) for h in db.query(m.Host).filter_by(teamId=team.id).all()]
        detail = {"ownerName": owner.name if owner else "", "memberCount": len(members),
                  "conversations": db.query(m.Conversation).filter_by(teamId=team.id).count(),
                  "projects": db.query(m.Project).filter_by(teamId=team.id).count(),
                  "hosts": len(hosts), "storageUsedGb": 0,
                  "creditsSpent": 100, "paidCents": 2990,
                  "tickets": db.query(m.Ticket).filter_by(teamId=team.id).count(),
                  "createdAt": team.createdAt}
        row = S.team_row(db, team, self.user["id"])
        return {"team": row, "detail": detail, "subscription": S.subscription_row(db, _subscription_for(self, db, team.id)),
                "balance": team.creditBalance or 0}
    query = (data.get("query") or "").strip().lower()
    rows = db.query(m.Team).all()
    if query:
        rows = [t for t in rows if query in (t.name or "").lower() or query in t.id.lower()]
    rows.sort(key=lambda t: t.createdAt or "", reverse=True)
    total = len(rows)
    page = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    teams = []
    for t in page:
        owner = db.get(m.User, t.ownerId)
        members = db.query(m.TeamMember).filter_by(teamId=t.id).count()
        sub = db.query(m.Subscription).filter_by(teamId=t.id).first()
        row = S.team_row(db, t, self.user["id"])
        row["ownerName"] = owner.name if owner else ""
        row["memberCount"] = members
        row["conversations"] = db.query(m.Conversation).filter_by(teamId=t.id).count()
        row["hosts"] = db.query(m.Host).filter_by(teamId=t.id).count()
        row["plan"] = (sub.planId or sub.plan) if sub else (t.plan or "free")
        teams.append(row)
    return _listout("teams", teams, total, data, 20, 200)


@_cmd("adminGetPaymentOrders")
def c_admin_get_payment_orders(self, db, data):
    self._admin_only(db)
    rows = [S.payment_order_row(db, o) for o in db.query(m.PaymentOrder).all()]
    rows.sort(key=lambda r: r["createdAt"] or "", reverse=True)
    for r in rows:
        team = db.get(m.Team, r["teamId"])
        user = db.get(m.User, r["userId"])
        r["teamName"] = team.name if team else ""
        r["userName"] = user.name if user else ""
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    return _listout("orders", rows, total, data, 20, 200)


@_cmd("adminGetInvoices", "adminGetInvoiceStats")
def c_admin_get_invoices(self, db, data):
    self._admin_only(db)
    all_rows = db.query(m.Invoice).all()
    stats = {"total": len(all_rows),
             "requested": sum(1 for i in all_rows if i.status == "requested"),
             "issued": sum(1 for i in all_rows if i.status == "issued"),
             "rejected": sum(1 for i in all_rows if i.status == "rejected"),
             "amountRequested": sum(i.amount for i in all_rows if i.status == "requested"),
             "amountIssued": sum(i.amount for i in all_rows if i.status == "issued"),
             "amountRejected": sum(i.amount for i in all_rows if i.status == "rejected"),
             "normal": sum(1 for i in all_rows if i.type == "normal"),
             "vatSpecial": sum(1 for i in all_rows if i.type == "vat_special")}
    if data.get("invoiceId"):
        inv = db.get(m.Invoice, data["invoiceId"])
        if inv is None:
            raise notFound("发票")
        return {"invoice": S.invoice_row(db, inv)}
    rows = [S.invoice_row(db, i) for i in all_rows]
    rows.sort(key=lambda r: r["createdAt"] or "", reverse=True)
    for r in rows:
        team = db.get(m.Team, r["teamId"])
        r["teamName"] = team.name if team else ""
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    return {"invoices": rows, "items": rows, "total": total, "stats": stats,
            "limit": _limit(data, 20, 200), "offset": _offset(data)}


@_cmd("adminGetRedeemCodes", "adminCreateRedeemCodes", "adminDisableRedeemCode")
def c_admin_redeem_codes(self, db, data):
    self._admin_only(db)
    if data.get("redeemCodeId") or data.get("id") or data.get("code"):
        key = data.get("redeemCodeId") or data.get("id") or data.get("code")
        rc = next((r for r in db.query(m.RedeemCode).all()
                   if r.id == key or r.code == key), None)
        if rc is None:
            raise notFound("兑换码")
        rc.disabled = True
        return {"ok": True, "code": rc.code}
    if data.get("credits") is not None or data.get("count") is not None:
        count = int(data.get("count") or 1)
        credits = int(data.get("credits") or 0)
        batch = data.get("batch") or "manual"
        codes = []
        for _ in range(count):
            code = "CG-" + uuid.uuid4().hex[:12].upper()
            code = "-".join(code[i:i + 4] for i in range(0, 12, 4))
            rc = m.RedeemCode(id=rid("rc"), code=f"CG-{code}", credits=credits,
                              batch=batch, usedBy=None, usedAt=None, disabled=False, createdAt=now())
            db.add(rc)
            codes.append(S.redeem_code_row(db, rc))
        return {"ok": True, "batch": batch, "count": len(codes), "codes": codes, "items": codes}
    rows = [S.redeem_code_row(db, r) for r in db.query(m.RedeemCode).all()]
    batches = sorted({r["batch"] for r in rows if r["batch"]})
    return {"codes": rows, "items": rows, "total": len(rows),
            "redeemCodes": rows, "batches": batches,
            "limit": _limit(data, 20, 200), "offset": _offset(data)}


@_cmd("adminTopupCredits", "adminGrantPlan", "setUserRole", "updateUserRoles", "banUser", "unbanUser")
def c_admin_user_actions(self, db, data):
    self._admin_only(db)
    # infer action from payload shape
    user_id = data.get("userId") or data.get("id")
    if user_id and (data.get("credits") is not None or data.get("amount") is not None
                    or data.get("role") is not None or data.get("banned") is not None
                    or data.get("ban") is not None or data.get("reason") is not None
                    or data.get("unban") is not None):
        u = db.get(m.User, user_id)
        if u is None:
            raise notFound("用户")
        roles = data.get("roles")
        if roles:
            u.roles = roles
            u.role = "super_admin" if "super_admin" in roles else roles[0]
        if data.get("role"):
            role = data["role"]
            if role not in ("user", "admin", "super_admin"):
                raise badRequest("非法角色")
            if u.role == "super_admin" and self.user["id"] != u.id:
                raise badRequest("不能修改超级管理员")
            u.role = role
        if data.get("banned") is True or data.get("ban") is True:
            u.banned = True
            u.banReason = data.get("reason")
        if data.get("banned") is False or data.get("unban") is True:
            u.banned = False
            u.banReason = None
        return {"ok": True, "user": S.user_row(u)}
    team_id = data.get("teamId") or data.get("userId") or user_id
    if data.get("planId") and team_id:
        sub = _grant_plan(self, db, team_id, data["planId"], int(data.get("months") or 1))
        return {"ok": True, "subscription": S.subscription_row(db, sub)}
    if data.get("credits") is not None and team_id:
        team = db.get(m.Team, team_id)
        if team is None:
            raise notFound("团队")
        amount = int(data.get("credits") or data.get("amount") or 0)
        team.creditBalance = (team.creditBalance or 0) + amount
        db.add(m.CreditLedger(id=rid("cl"), teamId=team_id, userId=self.user["id"],
                              delta=amount, reason="topup", balanceAfter=team.creditBalance,
                              note=data.get("note") or "后台充值", createdAt=now()))
        return {"ok": True, "balance": team.creditBalance}
    raise badRequest("参数不完整")


@_cmd("adminGetAnnouncements", "adminCreateAnnouncement", "adminUpdateAnnouncement", "adminDeleteAnnouncement")
def c_admin_announcements(self, db, data):
    self._admin_only(db)
    if data.get("titleZh") or data.get("contentZh") is not None:
        ann = m.Announcement(id=rid("ann"), titleZh=data.get("titleZh") or "公告",
                             titleEn=data.get("titleEn"), bodyZh=data.get("contentZh") or "",
                             bodyEn=data.get("contentEn") or "",
                             level=data.get("level") or "info", active=True,
                             publishedAt=data.get("publishedAt") or now(),
                             createdAt=now(), createdBy=self.user["id"])
        db.add(ann)
        return {"ok": True, "announcement": S.announcement_row(db, ann)}
    rows = [S.announcement_row(db, a) for a in db.query(m.Announcement).all()]
    rows.sort(key=lambda r: r["createdAt"] or "", reverse=True)
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    return _listout("announcements", rows, total, data, 20, 200)


@_cmd("adminGetAuditLogs")
def c_admin_get_audit_logs(self, db, data):
    self._admin_only(db)
    rows = db.query(m.AuditLog).order_by(m.AuditLog.createdAt.desc()).all()
    logs = [{"id": a.id, "actorId": a.actorId, "actorName": a.actorName or "",
             "action": a.action, "target": a.target, "detail": a.detail or "",
             "ip": a.ip or "", "createdAt": a.createdAt} for a in rows]
    total = len(logs)
    logs = logs[_offset(data): _offset(data) + _limit(data, 20, 200)]
    return _listout("logs", logs, total, data, 20, 200)


@_cmd("adminGetChatConversations", "adminGetConversion", "adminGetConversation", "adminGetConversationMessages")
def c_admin_get_conversations(self, db, data):
    self._admin_only(db)
    if data.get("conversationId"):
        c = db.get(m.Conversation, data["conversationId"])
        if c is None:
            raise notFound("会话")
        msgs = [S.message_row(db, x) for x in db.query(m.Message).filter_by(
            conversationId=c.id).order_by(m.Message.seq.asc()).all()]
        return {"conversation": S.conversation_row(db, c),
                "messages": msgs, "items": msgs, "total": len(msgs)}
    rows = [S.conversation_row(db, c) for c in db.query(m.Conversation).all()]
    rows.sort(key=lambda r: r["lastMessageAt"] or r["updatedAt"] or r["createdAt"] or "", reverse=True)
    for r in rows:
        user = db.get(m.User, r["userId"])
        r["userName"] = user.name if user else ""
        cid = r["id"]
        msgs = db.query(m.Message).filter_by(conversationId=cid).all()
        r["messageCount"] = len(msgs)
        r["credits"] = 0
    total = len(rows)
    rows = rows[_offset(data): _offset(data) + _limit(data, 20, 200)]
    return _listout("conversations", rows, total, data, 20, 200)


@_cmd("adminGetPlans")
def c_admin_get_plans(self, db, data):
    self._user(db)
    return {"plans": P.all_plan_specs(), "topupTiers": P.topup_tiers()}


@_cmd("adminGetExpiringSubscriptions", "adminGetPromoters", "adminGetEngagementReport",
      "adminGetRevenueReport", "adminGetMigrationStatus")
def c_admin_reports(self, db, data):
    self._admin_only(db)
    return {"ok": True, "items": [], "total": 0, "status": "idle", "history": []}


# ---------------------------------------------------------------------------
# Precise handlers for commands that share a payload shape with others.
# Registered directly to override the payload-sniffing multi-registrations.
# ---------------------------------------------------------------------------
def _admin_ticket_detail(self, db, data):
    self._admin_only(db)
    t = self._own_ticket(db, data.get("id") or data.get("ticketId"))
    msgs = [S.ticket_message_row(db, x) for x in db.query(m.TicketMessage).filter_by(
        ticketId=t.id).order_by(m.TicketMessage.createdAt.asc()).all()]
    return {"ticket": S.ticket_row(db, t), "messages": msgs,
            "truncated": False, "unreadCount": t.unreadForUser or 0}


def _admin_ticket_stats(self, db, data):
    self._admin_only(db)
    rows = db.query(m.Ticket).all()
    by_priority = {p: sum(1 for t in rows if (t.priority or "normal") == p)
                   for p in ("low", "normal", "high", "urgent")}
    return {"stats": {
        "total": len(rows),
        "open": sum(1 for t in rows if t.status == "open"),
        "answered": sum(1 for t in rows if t.status == "answered"),
        "resolved": sum(1 for t in rows if t.status == "resolved"),
        "closed": sum(1 for t in rows if t.status == "closed"),
        "unread": sum(1 for t in rows if (t.unreadForAdmin or 0) > 0),
        "byPriority": by_priority}}


def _admin_close_ticket(self, db, data):
    self._admin_only(db)
    t = db.get(m.Ticket, data.get("id") or data.get("ticketId"))
    if t is None:
        raise notFound("工单")
    t.status = "closed"
    t.closedAt = now()
    t.updatedAt = now()
    return {"ok": True, "id": t.id, "status": "closed"}


def _admin_delete_ticket(self, db, data):
    t = db.get(m.Ticket, data.get("id") or data.get("ticketId"))
    if t is None:
        raise notFound("工单")
    t.status = "deleted"
    t.deletedAt = now()
    t.updatedAt = now()
    return {"ok": True, "id": t.id, "status": "deleted"}


def _admin_reply_ticket(self, db, data):
    self._admin_only(db)
    t = db.get(m.Ticket, data.get("id") or data.get("ticketId"))
    if t is None:
        raise notFound("工单")
    body = str(data.get("body") or data.get("content") or "").strip()
    if not body:
        raise badRequest("回复内容不能为空", "INVALID_BODY")
    db.add(m.TicketMessage(id=rid("tm"), ticketId=t.id, authorId=self.user["id"],
                           authorRole="admin", body=body,
                           attachments=data.get("attachments") or [], createdAt=now()))
    t.status = data.get("status") or "answered"
    t.updatedAt = now()
    t.lastMessagePreview = body[:120]
    t.unreadForUser = (t.unreadForUser or 0) + 1
    t.unreadForAdmin = 0
    return {"ok": True, "ticket": S.ticket_row(db, t)}


def _admin_user_detail(self, db, data):
    self._admin_only(db)
    uid = data.get("userId") or data.get("id")
    u = db.get(m.User, uid) if uid else None
    if u is None:
        raise notFound("用户")
    mems = db.query(m.TeamMember).filter_by(userId=u.id).all()
    teams = []
    for mm in mems:
        t = db.get(m.Team, mm.teamId)
        if t:
            row = S.team_row(db, t, u.id)
            row["role"] = mm.role
            row["memberId"] = mm.id
            teams.append(row)
    hosts = [S.host_row(db, h) for h in db.query(m.Host).filter_by(userId=u.id).all()]
    convs = db.query(m.Conversation).filter_by(userId=u.id).all()
    msgs = sum(db.query(m.Message).filter_by(conversationId=c.id).count() for c in convs)
    orders = db.query(m.PaymentOrder).filter_by(userId=u.id).all()
    balance = (S.personal_team_for(db, u.id).creditBalance if S.personal_team_for(db, u.id) else 0)
    stats = {"teams": len(teams), "hosts": len(hosts), "conversations": len(convs),
             "messages": msgs, "creditsSpent": 0,
             "paidCents": sum(o.amountCents or 0 for o in orders if o.status == "paid"),
             "tickets": db.query(m.Ticket).filter_by(userId=u.id).count(),
             "devices": db.query(m.Device).filter_by(userId=u.id).count()}
    prof = S.profile_row(db, u)
    return {"user": S.user_row(u), "profile": prof, "teams": teams, "hosts": hosts,
            "subscription": S.subscription_row(db, _subscription_for(self, db, u.id)),
            "stats": stats, "balance": balance, "detail": {"teams": teams, "conversations": convs}}


def _admin_team_members(self, db, data):
    self._admin_only(db)
    tid = req(data, "teamId")
    rows = db.query(m.TeamMember).filter_by(teamId=tid).all()
    members = [S.team_member_row(db, mm) for mm in rows]
    return _listout("members", members, len(members), data)


def _admin_team_hosts(self, db, data):
    self._admin_only(db)
    tid = req(data, "teamId")
    rows = db.query(m.Host).filter_by(teamId=tid).all()
    hosts = [S.host_row(db, h) for h in rows]
    return _listout("hosts", hosts, len(hosts), data)


COMMANDS["adminGetTicket"] = _admin_ticket_detail
COMMANDS["adminGetTicketStats"] = _admin_ticket_stats
COMMANDS["adminCloseTicket"] = _admin_close_ticket
COMMANDS["adminDeleteTicket"] = _admin_delete_ticket
COMMANDS["adminReplyTicket"] = _admin_reply_ticket
COMMANDS["adminGetUserDetail"] = _admin_user_detail
COMMANDS["adminGetTeamMembers"] = _admin_team_members
COMMANDS["adminGetTeamHosts"] = _admin_team_hosts


def _admin_set_role(self, db, data):
    self._admin_only(db)
    u = db.get(m.User, req(data, "userId"))
    if u is None:
        raise notFound("用户")
    role = req(data, "role")
    if role not in ("user", "admin", "super_admin"):
        raise badRequest("非法角色")
    if u.role == "super_admin" and self.user["id"] != u.id:
        raise badRequest("不能修改超级管理员")
    u.role = role
    return {"ok": True, "user": S.user_row(u)}


def _admin_set_roles(self, db, data):
    self._admin_only(db)
    u = db.get(m.User, req(data, "userId"))
    if u is None:
        raise notFound("用户")
    roles = data.get("roles") or []
    if not isinstance(roles, list) or not roles:
        raise badRequest("角色列表不能为空")
    u.role = "super_admin" if "super_admin" in roles else roles[0]
    return {"ok": True, "userId": u.id, "roles": roles, "role": u.role}


def _admin_ban(self, db, data, banned=True):
    self._admin_only(db)
    u = db.get(m.User, data.get("userId") or data.get("id"))
    if u is None:
        raise notFound("用户")
    u.banned = banned
    u.banReason = (data.get("reason") if banned else None)
    return {"ok": True, "user": S.user_row(u)}


def _admin_topup(self, db, data):
    self._admin_only(db)
    team_id = data.get("teamId") or data.get("userId")
    team = db.get(m.Team, team_id)
    if team is None:
        raise notFound("团队")
    amount = int(data.get("credits") if data.get("credits") is not None else (data.get("amount") or 0))
    team.creditBalance = (team.creditBalance or 0) + amount
    db.add(m.CreditLedger(id=rid("cl"), teamId=team.id, userId=self.user["id"],
                          delta=amount, reason="topup", balanceAfter=team.creditBalance,
                          note=data.get("note") or "后台充值", createdAt=now()))
    return {"ok": True, "balance": team.creditBalance}


def _admin_grant_plan(self, db, data):
    self._admin_only(db)
    team_id = req(data, "teamId")
    plan_id = req(data, "planId")
    if plan_id not in P.PLANS:
        raise badRequest("未知套餐", "INVALID_PLAN")
    sub = _grant_plan(self, db, team_id, plan_id, int(data.get("months") or 1))
    return {"ok": True, "subscription": S.subscription_row(db, sub)}


COMMANDS["setUserRole"] = _admin_set_role
COMMANDS["updateUserRoles"] = _admin_set_roles
COMMANDS["banUser"] = lambda self, db, data: _admin_ban(self, db, data, True)
COMMANDS["unbanUser"] = lambda self, db, data: _admin_ban(self, db, data, False)
COMMANDS["adminTopupCredits"] = _admin_topup
COMMANDS["adminGrantPlan"] = _admin_grant_plan


def _admin_issue_invoice(self, db, data, rejected=False):
    self._admin_only(db)
    inv = db.get(m.Invoice, data.get("invoiceId"))
    if inv is None:
        raise notFound("发票")
    if rejected:
        inv.status = "rejected"
    else:
        inv.status = "issued"
        inv.invoiceNo = data.get("invoiceNo") or f"INV{datetime.now().year}{uuid.uuid4().hex[:6].upper()}"
        inv.issuedAt = now()
    return {"ok": True, "invoice": S.invoice_row(db, inv)}


COMMANDS["adminIssueInvoice"] = lambda self, db, data: _admin_issue_invoice(self, db, data, False)
COMMANDS["adminRejectInvoice"] = lambda self, db, data: _admin_issue_invoice(self, db, data, True)


# ===========================================================================
# module-level facade (mirrors the old `backend.core` surface)
# ===========================================================================
backend = Backend()


def dispatch(cmd, payload=None, **kwargs):
    try:
        return {"data": backend.call(cmd, payload)}
    except Exception as e:
        return {"error": {"code": getattr(e, "code", "INTERNAL"),
                          "message": getattr(e, "message", str(e))}}


def command_names():
    p = ROOT / "contracts" / "commands.json"
    try:
        return json.loads(p.read_text(encoding="utf8"))
    except Exception:
        return []


class BackendEphemeral:
    """A throw-away backend on its own temporary SQLite file (used by tests)."""

    def __init__(self):
        self.backend = Backend(url=f"sqlite:///{DATA / ('ephemeral_' + uuid.uuid4().hex + '.db')}")

    def call(self, c, d=None):
        return self.backend.call(c, d)
