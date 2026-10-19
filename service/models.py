"""SQLAlchemy ORM models for the embedded ClawsGO backend.

Table set mirrors `clawsgo-opensource/server/data/db.json` collections. All
datetime values are stored as ISO-8601 strings (matching the Node `now()`),
and nested structures (parts/spec/files/...) use JSON columns.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Column, Integer, String, Text, Boolean
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("CLAWSGO_DATA_DIR", ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)
DB_URL = f"sqlite:///{DATA / 'backend.db'}"  # for create_engine

Base = declarative_base()


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_default() -> Any:
    return {}


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    phone = Column(String(32), index=True)
    email = Column(String(128), nullable=True)
    name = Column(String(128))
    avatarUrl = Column(String(256), nullable=True)
    role = Column(String(16), default="user")
    locale = Column(String(16), default="zh-CN")
    theme = Column(String(16), default="dark")
    onboardedAt = Column(String(40), nullable=True)
    createdAt = Column(String(40))
    banned = Column(Boolean, default=False)
    banReason = Column(String(256), nullable=True)
    password = Column(String(64))
    plan = Column(String(16), default="free")


class Team(Base):
    __tablename__ = "teams"

    id = Column(String(64), primary_key=True)
    name = Column(String(128))
    ownerId = Column(String(64))
    plan = Column(String(16), default="free")
    memberLimit = Column(Integer, default=10)
    creditBalance = Column(Integer, default=0)
    createdAt = Column(String(40))


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    role = Column(String(16), default="member")
    joinedAt = Column(String(40))
    invitedByCode = Column(String(64), nullable=True)
    invitedBy = Column(String(64), nullable=True)


class TeamInvitation(Base):
    __tablename__ = "team_invitations"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    inviterId = Column(String(64))
    inviteeId = Column(String(64), nullable=True)
    phone = Column(String(32), nullable=True)
    email = Column(String(128), nullable=True)
    role = Column(String(16), default="member")
    status = Column(String(16), default="pending")
    createdAt = Column(String(40))
    expiresAt = Column(String(40), nullable=True)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    plan = Column(String(16), default="free")
    planId = Column(String(16), nullable=True)
    status = Column(String(16), default="active")
    seats = Column(Integer, default=1)
    priceMonthly = Column(Integer, default=0)
    currency = Column(String(8), default="CNY")
    currentPeriodEnd = Column(String(40), nullable=True)
    cycleStartAt = Column(String(40), nullable=True)
    planEndAt = Column(String(40), nullable=True)
    monthlyMilli = Column(Integer, default=0)
    createdAt = Column(String(40))


class Host(Base):
    __tablename__ = "hosts"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    name = Column(String(128))
    kind = Column(String(16), default="cloud")
    status = Column(String(16), default="provisioning")
    spec = Column(JSON, default=dict)
    image = Column(String(256), nullable=True)
    workdir = Column(String(256), nullable=True)
    createdAt = Column(String(40))
    lastSeenAt = Column(String(40), nullable=True)
    cacheClearedAt = Column(String(40), nullable=True)


class SshServer(Base):
    __tablename__ = "ssh_servers"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    name = Column(String(128))
    hostname = Column(String(128))
    port = Column(Integer, default=22)
    username = Column(String(64), default="root")
    authType = Column(String(16), default="key")
    status = Column(String(16), default="unknown")
    latencyMs = Column(Integer, nullable=True)
    lastProbeAt = Column(String(40), nullable=True)
    createdAt = Column(String(40))


class Skill(Base):
    __tablename__ = "skills"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), nullable=True, index=True)
    userId = Column(String(64), nullable=True)
    name = Column(String(128))
    slug = Column(String(128), nullable=True)
    title = Column(String(128), nullable=True)
    description = Column(Text, default="")
    version = Column(String(16), default="1.0.0")
    source = Column(String(16), default="official")
    repo = Column(String(256), nullable=True)
    tags = Column(JSON, default=list)
    installed = Column(Boolean, default=True)
    enabled = Column(Boolean, default=True)
    installedAt = Column(String(40), nullable=True)
    hostId = Column(String(64), nullable=True)
    files = Column(JSON, default=list)
    readme = Column(Text, default="")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    projectId = Column(String(64), nullable=True)
    title = Column(String(256), default="")
    hostId = Column(String(64), nullable=True)
    workdir = Column(String(256), nullable=True)
    modelId = Column(String(64), nullable=True)
    context = Column(String(32), default="default")
    effort = Column(String(16), nullable=True)
    mode = Column(String(16), default="agent")
    streamId = Column(String(64), nullable=True)
    pinnedAt = Column(String(40), nullable=True)
    archivedAt = Column(String(40), nullable=True)
    createdAt = Column(String(40))
    updatedAt = Column(String(40))
    lastMessageAt = Column(String(40), nullable=True)
    lastMessagePreview = Column(Text, default="")
    lastMessageAttachments = Column(Integer, default=0)


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(64), primary_key=True)
    conversationId = Column(String(64), index=True)
    role = Column(String(16))
    seq = Column(Integer, default=0)
    modelId = Column(String(64), nullable=True)
    context = Column(String(32), nullable=True)
    parts = Column(JSON, default=list)
    streamId = Column(String(64), nullable=True)
    meta = Column("metadata", JSON, default=dict)
    createdAt = Column(String(40))


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String(64), primary_key=True)
    seq = Column(Integer, default=1001)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    type = Column(String(32), default="general")
    subject = Column(String(256))
    status = Column(String(16), default="open")
    priority = Column(String(16), default="normal")
    createdAt = Column(String(40))
    updatedAt = Column(String(40))
    lastMessagePreview = Column(Text, default="")
    lastMessageAttachments = Column(Integer, default=0)
    unreadForUser = Column(Integer, default=0)
    unreadForAdmin = Column(Integer, default=0)
    closedAt = Column(String(40), nullable=True)
    deletedAt = Column(String(40), nullable=True)


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(String(64), primary_key=True)
    ticketId = Column(String(64), index=True)
    authorId = Column(String(64))
    authorRole = Column(String(16))
    body = Column(Text)
    attachments = Column(JSON, default=list)
    createdAt = Column(String(40))
    recalledAt = Column(String(40), nullable=True)
    recalledBy = Column(String(64), nullable=True)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(String(64), primary_key=True)
    orderNo = Column(String(64))
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    kind = Column(String(16), default="plan")
    planId = Column(String(16), nullable=True)
    months = Column(Integer, default=1)
    amountCents = Column(Integer, default=0)
    currency = Column(String(8), default="CNY")
    provider = Column(String(16), default="wechat")
    gateway = Column(String(16), default="wechat")
    status = Column(String(16), default="pending")
    payUrl = Column(String(512), nullable=True)
    plan = Column(JSON, nullable=True)
    creditMilli = Column(Integer, default=0)
    bonusMilli = Column(Integer, default=0)
    providerTradeNo = Column(String(64), nullable=True)
    refundedAt = Column(String(40), nullable=True)
    paidAt = Column(String(40), nullable=True)
    createdAt = Column(String(40))
    expiresAt = Column(String(40), nullable=True)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    orderId = Column(String(64), nullable=True)
    amount = Column(Integer, default=0)
    currency = Column(String(8), default="CNY")
    title = Column(String(256), default="")
    taxNo = Column(String(32), default="")
    type = Column(String(16), default="normal")
    status = Column(String(16), default="requested")
    email = Column(String(128), nullable=True)
    invoiceNo = Column(String(64), nullable=True)
    note = Column(Text, nullable=True)
    redInvoiceNo = Column(String(64), nullable=True)
    createdAt = Column(String(40))
    issuedAt = Column(String(40), nullable=True)


class CreditLedger(Base):
    __tablename__ = "credit_ledger"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), nullable=True)
    delta = Column(Integer, default=0)
    reason = Column(String(32))
    balanceAfter = Column(Integer, default=0)
    note = Column(Text, nullable=True)
    createdAt = Column(String(40))


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    name = Column(String(256))
    kind = Column(String(16), default="explicit")
    instruction = Column(Text, nullable=True)
    createdAt = Column(String(40))
    updatedAt = Column(String(40))
    archivedAt = Column(String(40), nullable=True)
    pinnedAt = Column(String(40), nullable=True)


class Device(Base):
    __tablename__ = "devices"

    id = Column(String(64), primary_key=True)
    userId = Column(String(64), index=True)
    name = Column(String(128))
    platform = Column(String(16), default="web")
    appVersion = Column(String(16), nullable=True)
    status = Column(String(16), default="active")
    workspaceRoot = Column(String(256), nullable=True)
    lastSeenAt = Column(String(40))
    createdAt = Column(String(40))
    revokedAt = Column(String(40), nullable=True)


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(String(64), primary_key=True)
    titleZh = Column(String(256))
    titleEn = Column(String(256), nullable=True)
    bodyZh = Column(Text, default="")
    bodyEn = Column(Text, default="")
    level = Column(String(16), default="info")
    active = Column(Boolean, default=True)
    publishedAt = Column(String(40))
    createdAt = Column(String(40))
    createdBy = Column(String(64), nullable=True)


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    code = Column(String(64))
    name = Column(String(128), default="")
    usedCount = Column(Integer, default=0)
    maxUses = Column(Integer, default=0)
    rewardCredits = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    createdAt = Column(String(40))


class RedeemCode(Base):
    __tablename__ = "redeem_codes"

    id = Column(String(64), primary_key=True)
    code = Column(String(64))
    credits = Column(Integer, default=0)
    batch = Column(String(64), nullable=True)
    usedBy = Column(String(64), nullable=True)
    usedAt = Column(String(40), nullable=True)
    disabled = Column(Boolean, default=False)
    createdAt = Column(String(40))


class AgentMemory(Base):
    __tablename__ = "agent_memory"

    id = Column(String(64), primary_key=True)
    teamId = Column(String(64), index=True)
    userId = Column(String(64), index=True)
    scope = Column(String(32), default="global")
    key = Column(String(128))
    content = Column(Text)
    createdAt = Column(String(40))
    updatedAt = Column(String(40))


class Folder(Base):
    __tablename__ = "folders"

    id = Column(String(64), primary_key=True)
    hostId = Column(String(64), index=True)
    path = Column(String(512))
    createdAt = Column(String(40))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True)
    actorId = Column(String(64))
    actorName = Column(String(128), nullable=True)
    action = Column(String(64))
    target = Column(String(64), nullable=True)
    detail = Column(Text, nullable=True)
    ip = Column(String(64), nullable=True)
    createdAt = Column(String(40))


class Counter(Base):
    __tablename__ = "counters"

    key = Column(String(32), primary_key=True)
    value = Column(Integer, default=0)


class StoredFile(Base):
    """Audit row for uploaded/linked virtual files (workspace / attachments)."""

    __tablename__ = "stored_files"

    id = Column(String(64), primary_key=True)
    kind = Column(String(16), default="upload")
    conversationId = Column(String(64), nullable=True)
    ticketId = Column(String(64), nullable=True)
    path = Column(String(512), nullable=True)
    name = Column(String(256), nullable=True)
    size = Column(Integer, default=0)
    mimeType = Column(String(128), nullable=True)
    url = Column(String(512), nullable=True)
    createdAt = Column(String(40))


def create_all(engine) -> None:
    Base.metadata.create_all(engine)
