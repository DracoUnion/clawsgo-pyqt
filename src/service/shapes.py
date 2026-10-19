"""Response serializers — port of `clawsgo-opensource/server/lib/shapes.mjs`.

Pure functions mapping ORM rows to the exact JSON shape the frontend expects.
Functions that need to look up related rows take ``db`` (the active SQLAlchemy
Session) as their first argument. Derived/optional fields are computed here,
never stored.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

from . import models as m


def _shift_days(iso: str, days: int) -> str:
    try:
        d = _dt.datetime.fromisoformat(iso)
        return (d + _dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")
    except Exception:
        return iso


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# user / profile / team
# ---------------------------------------------------------------------------
def user_row(u):
    if u is None:
        return None
    return {
        "id": u.id,
        "userId": u.id,
        "name": u.name,
        "email": u.email,
        "phone": u.phone,
        "avatarUrl": u.avatarUrl,
        "locale": u.locale or "zh-CN",
        "theme": u.theme or "dark",
        "role": u.role or "user",
        "banned": bool(u.banned),
        "banReason": u.banReason,
        "createdAt": u.createdAt,
    }


def personal_team_for(db, user_id):
    """Personal team for a user; mirrors seed.mjs `id === userId` invariant."""
    mem = db.query(m.TeamMember).filter_by(userId=user_id, role="owner").first()
    if mem:
        team = db.get(m.Team, mem.teamId)
        if team:
            return team
    team = db.get(m.Team, user_id)
    if team:
        return team
    return db.query(m.Team).first()


def profile_row(db, u):
    if u is None:
        return None
    team = personal_team_for(db, u.id)
    return {
        "id": u.id,
        "userId": u.id,
        "teamId": team.id if team else None,
        "name": u.name,
        "displayName": u.name or u.email or u.phone or "",
        "email": u.email,
        "phone": u.phone,
        "avatarUrl": u.avatarUrl,
        "role": u.role,
        "roles": [u.role] if u.role else ["user"],
        "locale": u.locale or "zh-CN",
        "theme": u.theme or "dark",
        "plan": u.plan or "free",
        "onboardedAt": u.onboardedAt,
        "createdAt": u.createdAt,
        "banned": bool(u.banned),
        "banReason": u.banReason,
        "credits": team.creditBalance if team else 0,
    }


def team_row(db, t, requester_id):
    if t is None:
        return None
    mem = db.query(m.TeamMember).filter_by(teamId=t.id, userId=requester_id).first()
    member_count = db.query(m.TeamMember).filter_by(teamId=t.id).count()
    return {
        "id": t.id,
        "userId": requester_id,
        "name": t.name,
        "ownerId": t.ownerId,
        "role": mem.role if mem else "member",
        "plan": t.plan,
        "memberLimit": t.memberLimit or 10,
        "memberCount": member_count,
        "creditBalance": t.creditBalance or 0,
        "seatsUsed": member_count,
        "createdAt": t.createdAt,
    }


# ---------------------------------------------------------------------------
# team member / invitation
# ---------------------------------------------------------------------------
def team_member_row(db, mm):
    u = db.get(m.User, mm.userId) if mm.userId else None
    return {
        "id": mm.id,
        "userId": mm.userId,
        "teamId": mm.teamId,
        "role": mm.role,
        "joinedAt": mm.joinedAt,
        "name": u.name if u else "(已注销)",
        "email": u.email if u else None,
        "phone": u.phone if u else None,
        "avatarUrl": u.avatarUrl if u else None,
        "banned": bool(u.banned) if u else False,
    }


def team_invitation_row(db, inv):
    u = db.get(m.User, inv.inviteeId) if inv.inviteeId else None
    inviter = db.get(m.User, inv.inviterId) if inv.inviterId else None
    return {
        "id": inv.id,
        "teamId": inv.teamId,
        "inviterId": inv.inviterId,
        "inviterName": inviter.name if inviter else None,
        "inviteeId": inv.inviteeId,
        "email": inv.email or (u.email if u else None),
        "phone": inv.phone or (u.phone if u else None),
        "role": inv.role,
        "status": inv.status,
        "createdAt": inv.createdAt,
        "expiresAt": inv.expiresAt,
    }


# ---------------------------------------------------------------------------
# host / ssh server
# ---------------------------------------------------------------------------
def host_row(db, h):
    if h is None:
        return None
    spec = h.spec or {}
    ssh = db.query(m.SshServer).filter_by(name=h.name, teamId=h.teamId).first()
    online = h.status in ("running", "online")
    return {
        "id": h.id,
        "teamId": h.teamId,
        "userId": h.userId,
        "name": h.name,
        "kind": h.kind,
        "status": h.status,
        "canDispatchTask": h.status in ("running", "online"),
        "canOpenTerminal": h.kind == "local" or h.status == "running",
        "online": online,
        "image": h.image,
        "workdir": h.workdir,
        "createdAt": h.createdAt,
        "lastSeenAt": h.lastSeenAt,
        "spec": spec,
        "cpu": spec.get("cpu"),
        "memoryGb": spec.get("memoryGb"),
        "diskGb": spec.get("diskGb"),
        "gpu": spec.get("gpu"),
        "specLabel": " · ".join(x for x in [
            f"{spec['cpu']} vCPU" if spec.get("cpu") else None,
            f"{spec['memoryGb']} GB" if spec.get("memoryGb") else None,
            spec.get("gpu"),
        ] if x),
        "cacheClearedAt": h.cacheClearedAt,
        "sshServerId": ssh.id if ssh else None,
    }


def ssh_server_row(db, s):
    if s is None:
        return None
    return {
        "id": s.id,
        "teamId": s.teamId,
        "userId": s.userId,
        "name": s.name,
        "hostname": s.hostname,
        "port": s.port or 22,
        "username": s.username,
        "authType": s.authType or "key",
        "status": s.status or "unknown",
        "latencyMs": s.latencyMs,
        "lastProbeAt": s.lastProbeAt,
        "createdAt": s.createdAt,
    }


# ---------------------------------------------------------------------------
# skill
# ---------------------------------------------------------------------------
def skill_row(db, s):
    if s is None:
        return None
    return {
        "id": s.id,
        "name": s.name,
        "slug": s.slug or s.name,
        "title": s.title or s.name,
        "description": s.description or "",
        "version": s.version or "1.0.0",
        "source": s.source or "official",
        "repo": s.repo,
        "tags": s.tags or [],
        "installed": s.installed is not False,
        "enabled": bool(s.enabled),
        "installedAt": s.installedAt,
        "hostId": s.hostId,
        "fileCount": len(s.files or []),
        "files": s.files or [],
        "readme": s.readme or "",
    }


# ---------------------------------------------------------------------------
# ticket / ticket message
# ---------------------------------------------------------------------------
def ticket_row(db, t):
    if t is None:
        return None
    return {
        "id": t.id,
        "seq": t.seq,
        "teamId": t.teamId,
        "userId": t.userId,
        "type": t.type,
        "subject": t.subject,
        "status": t.status,
        "priority": t.priority or "normal",
        "createdAt": t.createdAt,
        "updatedAt": t.updatedAt,
        "lastMessageAt": t.updatedAt,
        "lastMessagePreview": t.lastMessagePreview or "",
        "lastMessageAttachments": t.lastMessageAttachments or 0,
        "unreadCount": t.unreadForUser or 0,
        "unreadForUser": t.unreadForUser or 0,
        "unreadForAdmin": t.unreadForAdmin or 0,
    }


def ticket_message_row(db, tm):
    return {
        "id": tm.id,
        "ticketId": tm.ticketId,
        "authorId": tm.authorId,
        "authorRole": tm.authorRole,
        "body": tm.body,
        "attachments": tm.attachments or [],
        "createdAt": tm.createdAt,
    }


# ---------------------------------------------------------------------------
# invoice / payment order / ledger / subscription
# ---------------------------------------------------------------------------
def invoice_row(db, i):
    return {
        "id": i.id,
        "teamId": i.teamId,
        "userId": i.userId,
        "orderId": i.orderId,
        "amount": i.amount,
        "currency": i.currency or "CNY",
        "title": i.title,
        "taxNo": i.taxNo or "",
        "type": i.type,
        "status": i.status,
        "email": i.email,
        "note": i.note,
        "createdAt": i.createdAt,
        "issuedAt": i.issuedAt,
    }


def payment_order_row(db, o):
    return {
        "id": o.id,
        "orderNo": o.orderNo,
        "teamId": o.teamId,
        "userId": o.userId,
        "kind": o.kind or "plan",
        "planId": o.planId,
        "months": o.months or 1,
        "amount": o.amountCents or 0,
        "amountCents": o.amountCents or o.amount or 0,
        "creditMilli": o.creditMilli or 0,
        "bonusMilli": o.bonusMilli or 0,
        "payUrl": o.payUrl,
        "currency": o.currency or "CNY",
        "gateway": o.gateway or o.provider,
        "provider": o.provider or o.gateway,
        "plan": o.plan,
        "status": o.status,
        "providerTradeNo": o.providerTradeNo,
        "refundedAt": o.refundedAt,
        "createdAt": o.createdAt,
        "paidAt": o.paidAt,
    }


def credit_ledger_row(db, r):
    return {
        "id": r.id,
        "teamId": r.teamId,
        "userId": r.userId,
        "delta": r.delta,
        "reason": r.reason,
        "balanceAfter": r.balanceAfter,
        "note": r.note,
        "createdAt": r.createdAt,
    }


def subscription_row(db, s):
    if s is None:
        return None
    start = s.cycleStartAt or s.createdAt or _now_iso()
    end = s.planEndAt or s.currentPeriodEnd or _shift_days(start, 30)
    return {
        "id": s.id,
        "teamId": s.teamId,
        "planId": s.planId or s.plan or "free",
        "plan": s.planId or s.plan or "free",
        "status": s.status,
        "seats": s.seats or 1,
        "priceMonthly": s.priceMonthly or 0,
        "currency": s.currency or "CNY",
        "cycleStartAt": start,
        "currentPeriodEnd": end,
        "planEndAt": end,
        "createdAt": s.createdAt,
    }


# ---------------------------------------------------------------------------
# announcement / device / invite code / redeem code
# ---------------------------------------------------------------------------
def announcement_row(db, a):
    return {
        "id": a.id,
        "titleZh": a.titleZh,
        "titleEn": a.titleEn or a.titleZh,
        "contentZh": a.bodyZh or "",
        "contentEn": a.bodyEn or a.bodyZh or "",
        "bodyZh": a.bodyZh or "",
        "bodyEn": a.bodyEn or "",
        "level": a.level or "info",
        "active": bool(a.active),
        "publishedAt": a.publishedAt,
        "createdAt": a.createdAt,
        "createdBy": a.createdBy,
    }


def invite_code_row(db, c):
    return {
        "id": c.id,
        "teamId": c.teamId,
        "userId": c.userId,
        "code": c.code,
        "name": c.name or "",
        "usedCount": c.usedCount or 0,
        "maxUses": c.maxUses or 0,
        "rewardCredits": c.rewardCredits or 0,
        "active": c.active is not False,
        "createdAt": c.createdAt,
    }


def redeem_code_row(db, c):
    status = "disabled" if c.disabled else ("used" if c.usedBy else "unused")
    return {
        "id": c.id,
        "code": c.code,
        "credits": c.credits,
        "batch": c.batch,
        "status": status,
        "usedBy": c.usedBy,
        "usedAt": c.usedAt,
        "createdAt": c.createdAt,
    }


# ---------------------------------------------------------------------------
# project / conversation / message / agent memory
# ---------------------------------------------------------------------------
def project_row(db, p, viewer_id=None):
    if p is None:
        return None
    convs = db.query(m.Conversation).filter_by(projectId=p.id).all()
    convs = [c for c in convs if not c.archivedAt]
    creator = db.get(m.User, p.userId)
    return {
        "id": p.id,
        "teamId": p.teamId,
        "userId": p.userId,
        "name": p.name,
        "kind": p.kind,
        "instruction": p.instruction,
        "conversationCount": len(convs),
        "taskCount": len(convs),
        "myTaskCount": len([c for c in convs if c.userId == viewer_id]) if viewer_id else len(convs),
        "creatorName": creator.name if creator else "",
        "createdAt": p.createdAt,
        "updatedAt": p.updatedAt,
        "archivedAt": p.archivedAt,
        "pinnedAt": p.pinnedAt,
    }


def conversation_row(db, c):
    if c is None:
        return None
    p = db.get(m.Project, c.projectId) if c.projectId else None
    creator = db.get(m.User, c.userId)
    return {
        "id": c.id,
        "teamId": c.teamId,
        "userId": c.userId,
        "projectId": c.projectId,
        "projectKind": p.kind if p else "implicit",
        "creatorName": creator.name if creator else "",
        "projectTitle": p.name if p else None,
        "title": c.title or "",
        "hostId": c.hostId,
        "workdir": c.workdir,
        "modelId": c.modelId,
        "context": c.context or "default",
        "effort": c.effort,
        "mode": c.mode or "agent",
        "streamId": c.streamId,
        "createdAt": c.createdAt,
        "updatedAt": c.updatedAt,
        "lastMessageAt": c.lastMessageAt,
        "lastMessagePreview": c.lastMessagePreview or "",
        "lastMessageAttachments": c.lastMessageAttachments or 0,
        "pinnedAt": c.pinnedAt,
        "archivedAt": c.archivedAt,
    }


def message_row(db, msg):
    return {
        "id": msg.id,
        "conversationId": msg.conversationId,
        "role": msg.role,
        "seq": msg.seq or 0,
        "modelId": msg.modelId,
        "context": msg.context,
        "parts": msg.parts or [],
        "streamId": msg.streamId,
        "metadata": msg.meta,
        "createdAt": msg.createdAt,
    }