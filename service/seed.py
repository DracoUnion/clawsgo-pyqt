"""Seed data — port of `clawsgo-opensource/server/lib/seed.mjs`.

Inserted once when the users table is empty. IDs are fixed/readable strings
(not uuids) so tests and the demo UI stay deterministic; the personal-team
invariant `team.id === owner userId` is preserved.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import models as m


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ago(ms: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(milliseconds=ms)).isoformat().replace("+00:00", "Z")


def seed(db) -> None:
    now = _now()
    # ---------------- users / team ----------------
    owner = m.User(
        id="u_demo", phone="13800000000", email="demo@clawsgo.local", name="演示用户",
        avatarUrl=None, role="user", locale="zh-CN", theme="dark",
        onboardedAt=_ago(9 * 864e5), createdAt=_ago(30 * 864e5),
        banned=False, banReason=None, password="clawsgo2026", plan="pro",
    )
    admin = m.User(
        id="u_admin", phone="13900000000", email="admin@clawsgo.local", name="平台管理员",
        avatarUrl=None, role="super_admin", locale="zh-CN", theme="dark",
        onboardedAt=_ago(40 * 864e5), createdAt=_ago(60 * 864e5),
        banned=False, banReason=None, password="clawsgo2026", plan="ultimate",
    )
    db.add_all([owner, admin])

    team = m.Team(
        id="u_demo", name="演示实验室", ownerId="u_demo", plan="pro",
        memberLimit=10, creditBalance=4820, createdAt=_ago(30 * 864e5),
    )
    db.add(team)
    db.add_all([
        m.TeamMember(id="u_demo_owner", teamId="u_demo", userId="u_demo", role="owner", joinedAt=_ago(30 * 864e5)),
        m.TeamMember(id="u_admin_member", teamId="u_demo", userId="u_admin", role="admin", joinedAt=_ago(25 * 864e5)),
    ])
    db.add(m.Subscription(
        id="sub_pro", teamId="u_demo", plan="pro", planId="pro", status="active",
        seats=5, priceMonthly=299, currency="CNY",
        currentPeriodEnd=_now(), createdAt=_ago(30 * 864e5), cycleStartAt=_ago(30 * 864e5),
    ))
    db.add_all([
        m.CreditLedger(id="cl_1", teamId="u_demo", userId="u_demo", delta=5000, reason="topup", balanceAfter=5000, createdAt=_ago(30 * 864e5), note="首次充值"),
        m.CreditLedger(id="cl_2", teamId="u_demo", userId="u_demo", delta=-180, reason="usage", balanceAfter=4820, createdAt=_ago(2 * 864e5), note="对话用量结算"),
    ])

    # ---------------- hosts / ssh ----------------
    h_cloud = m.Host(
        id="h_cloud_default", teamId="u_demo", userId="u_demo", name="cloud-default",
        kind="cloud", status="running",
        spec={"cpu": 8, "memoryGb": 32, "diskGb": 200, "gpu": "RTX 4090 24GB"},
        image="clawsgo/science-runtime:2026.09", workdir="/home/clawsgo/workspace",
        createdAt=_ago(30 * 864e5), lastSeenAt=_ago(3 * 60e3), cacheClearedAt=None,
    )
    h_ssh = m.Host(
        id="h_lab_a100", teamId="u_demo", userId="u_demo", name="lab-a100",
        kind="ssh", status="offline",
        spec={"cpu": 64, "memoryGb": 256, "diskGb": 4000, "gpu": "A100 80GB x4"},
        image=None, workdir="/data/lab",
        createdAt=_ago(12 * 864e5), lastSeenAt=_ago(2 * 864e5), cacheClearedAt=None,
    )
    db.add_all([h_cloud, h_ssh])
    db.add(m.SshServer(
        id="ssh_lab_a100", teamId="u_demo", userId="u_demo", name="lab-a100",
        hostname="10.0.12.31", port=22, username="researcher", authType="key",
        status="unreachable", lastProbeAt=_ago(2 * 864e5), latencyMs=None, createdAt=_ago(12 * 864e5),
    ))
    db.add_all([
        m.Folder(id="f_1", hostId="h_cloud_default", path="/home/clawsgo/workspace", createdAt=_ago(28 * 864e5)),
        m.Folder(id="f_2", hostId="h_cloud_default", path="/home/clawsgo/data", createdAt=_ago(20 * 864e5)),
    ])

    # ---------------- skills ----------------
    _seed_skills(db, h_cloud.id)

    # ---------------- projects / conversations ----------------
    p1 = m.Project(
        id="p_perovskite", teamId="u_demo", userId="u_demo", name="钙钛矿太阳能电池稳定性",
        kind="explicit", instruction="长期跟踪 MAPbI3 薄膜在湿热条件下的降解路径，产出可复现的实验与仿真对照报告。",
        createdAt=_ago(20 * 864e5), updatedAt=_ago(2 * 864e5), archivedAt=None, pinnedAt=_ago(19 * 864e5),
    )
    p2 = m.Project(
        id="p_uncategorized", teamId="u_demo", userId="u_demo", name="未归类",
        kind="implicit", instruction=None,
        createdAt=_ago(30 * 864e5), updatedAt=_ago(1 * 3600e3), archivedAt=None, pinnedAt=None,
    )
    db.add_all([p1, p2])

    conv_defs = [
        ("c_pv_degrad", p1.id, 2 * 3600e3, "钙钛矿薄膜湿度降解机制梳理",
         "帮我梳理 MAPbI3 薄膜在 85%RH / 85℃ 条件下的主要降解路径，并给出可验证的实验判据。"),
        ("c_xrd_shift", p1.id, 26 * 3600e3, "XRD 峰位随退火温度漂移分析",
         "我有一组 XRD 数据，退火温度从 80℃ 到 180℃。峰位出现系统性漂移，帮我分析可能原因。"),
        ("c_rename_script", p2.id, 3 * 864e5, "写一个批量重命名脚本",
         "把 data/raw 下所有 *.csv 按 日期_样品编号.csv 重命名，日期取文件 mtime。"),
    ]
    for cid, project_id, age, title, q in conv_defs:
        _seed_conversation(db, cid, project_id, title, q, age, h_cloud.id)

    # ---------------- tickets ----------------
    db.add_all([
        m.Ticket(
            id="t_ssh_offline", seq=1001, teamId="u_demo", userId="u_demo", type="technical",
            subject="SSH 主机 lab-a100 一直显示离线", status="open", priority="normal",
            createdAt=_ago(26 * 3600e3), updatedAt=_ago(20 * 3600e3),
            lastMessagePreview="已收到，我们在排查出口网络策略。", lastMessageAttachments=0,
            unreadForUser=1, unreadForAdmin=0,
        ),
        m.Ticket(
            id="t_billing_pro", seq=1002, teamId="u_demo", userId="u_demo", type="billing",
            subject="咨询：Pro 套餐额度如何计费", status="closed", priority="low",
            createdAt=_ago(9 * 864e5), updatedAt=_ago(8 * 864e5),
            lastMessagePreview="按输出 token 折算点数，明细可在「用量」页查看。", lastMessageAttachments=0,
            unreadForUser=0, unreadForAdmin=0,
        ),
    ])
    db.add_all([
        m.TicketMessage(id="tm_1", ticketId="t_ssh_offline", authorId="u_demo", authorRole="user",
                        body="lab-a100 从昨天开始一直离线，probeSshServers 也失败。同网段其他机器正常。",
                        attachments=[], createdAt=_ago(26 * 3600e3)),
        m.TicketMessage(id="tm_2", ticketId="t_ssh_offline", authorId="u_admin", authorRole="admin",
                        body="已收到，我们在排查出口网络策略。请提供 `ssh -vvv` 的前 30 行输出。",
                        attachments=[], createdAt=_ago(20 * 3600e3)),
        m.TicketMessage(id="tm_3", ticketId="t_billing_pro", authorId="u_demo", authorRole="user",
                        body="Pro 套餐的额度是按什么口径扣的？", attachments=[], createdAt=_ago(9 * 864e5)),
        m.TicketMessage(id="tm_4", ticketId="t_billing_pro", authorId="u_admin", authorRole="admin",
                        body="按输出 token 折算点数，明细可在「用量」页查看。", attachments=[], createdAt=_ago(8 * 864e5)),
    ])

    # ---------------- announcements / codes / orders / invoices ----------------
    db.add(m.Announcement(
        id="ann_1", titleZh="ClawsGO 1.0 Titanium 已上线", titleEn="ClawsGO 1.0 Titanium is live",
        bodyZh="新模型在长时程任务上的稳定性提升明显，欢迎在模型选择器中切换体验。",
        bodyEn="The new model is noticeably more stable on long-horizon tasks.",
        level="info", active=True, publishedAt=_ago(3 * 864e5), createdAt=_ago(3 * 864e5), createdBy="u_admin",
    ))
    db.add(m.InviteCode(
        id="ic_1", teamId="u_demo", userId="u_demo", code="CG-DEMO-2026", name="默认邀请码",
        usedCount=3, maxUses=20, rewardCredits=200, active=True, createdAt=_ago(30 * 864e5),
    ))
    db.add_all([
        m.RedeemCode(id="rc_1", code="CLAWSGO-DEMO-1000", credits=1000, batch="demo", usedBy=None, usedAt=None, disabled=False, createdAt=_ago(30 * 864e5)),
        m.RedeemCode(id="rc_2", code="CLAWSGO-DEMO-2500", credits=2500, batch="demo", usedBy=None, usedAt=None, disabled=False, createdAt=_ago(30 * 864e5)),
    ])
    db.add(m.PaymentOrder(
        id="po_1", orderNo="CGDEMO20260001", teamId="u_demo", userId="u_demo", kind="plan",
        planId="pro", months=1, amountCents=2990, currency="CNY", provider="wechat", gateway="wechat",
        status="paid", payUrl=None, creditMilli=120000000, bonusMilli=0,
        providerTradeNo="wx-demo-001", refundedAt=None, paidAt=_ago(30 * 864e5), createdAt=_ago(30 * 864e5),
    ))
    db.add(m.Invoice(
        id="inv_1", teamId="u_demo", userId="u_demo", orderId="po_1", amount=2990,
        title="演示实验室", taxNo="", type="normal", status="issued", email="demo@clawsgo.local",
        invoiceNo="INV2026DEMO001", createdAt=_ago(29 * 864e5), issuedAt=_ago(28 * 864e5),
    ))
    db.add(m.Device(
        id="dev_1", userId="u_demo", name="Windows 11 Desktop", platform="win32",
        appVersion="1.0.0", status="active", lastSeenAt=_ago(4 * 60e3), createdAt=_ago(20 * 864e5), revokedAt=None,
    ))
    db.add_all([
        m.AuditLog(id="al_1", actorId="u_admin", actorName="平台管理员", action="admin.grantPlan", target="u_demo",
                   detail="授予 pro 套餐", ip="127.0.0.1", createdAt=_ago(29 * 864e5)),
        m.AuditLog(id="al_2", actorId="u_demo", actorName="演示用户", action="auth.signIn", target="u_demo",
                   detail="手机号密码登录", ip="127.0.0.1", createdAt=_ago(2 * 3600e3)),
    ])
    db.add(m.AgentMemory(
        id="am_1", teamId="u_demo", userId="u_demo", scope="global", key="report-format",
        content="产出实验报告时优先给出「结论 → 证据 → 复现步骤」三段式，图表统一 300dpi。",
        createdAt=_ago(18 * 864e5), updatedAt=_ago(18 * 864e5),
    ))
    db.add(m.Counter(key="ticket", value=1002))


# ---------------------------------------------------------------------------
def _seed_skills(db, host_id) -> None:
    now = _now()
    defs = [
        ("s_arxiv", "arxiv-search", "检索 arXiv 预印本，支持按作者、分类、时间窗过滤，返回 BibTeX。", "official", None, ["research", "literature"]),
        ("s_pdf", "pdf-extract", "从 PDF 中抽取正文、表格与公式，输出结构化 Markdown。", "official", None, ["document", "parsing"]),
        ("s_bio", "bio-seq-align", "序列比对与系统发生树构建（ClustalW/MAFFT 后端）。", "official", None, ["biology"]),
        ("s_figure", "figure-studio", "把数据表一键绘制成出版级图表，自动匹配期刊配色与字体。", "official", None, ["visualization"]),
        ("s_matlab", "matlab-bridge", "通过 MATLAB Engine 调用本地 MATLAB 脚本并回收工作区变量。", "github", "clawsgo/skill-matlab-bridge", ["matlab"]),
        ("s_rdkit", "rdkit-chem", "分子式解析、相似性计算与 2D 结构渲染。", "github", "clawsgo/skill-rdkit", ["chemistry"]),
        ("s_wandb", "wandb-track", "把训练指标同步到 Weights & Biases 并生成对比报告。", "github", "clawsgo/skill-wandb", ["ml", "tracking"]),
        ("s_lab", "lab-notebook", "按实验记录规范生成电子实验记录本条目，支持签名留痕。", "official", None, ["workflow"]),
    ]
    for sid, name, desc, source, repo, tags in defs:
        installed = source == "official"
        db.add(m.Skill(
            id=sid, teamId="u_demo", userId="u_demo", name=name, slug=name, title=name,
            description=desc, version="1.0.5", source=source, repo=repo, tags=tags,
            installed=installed, enabled=installed,
            installedAt=_ago(30 * 864e5) if installed else None,
            hostId=host_id if installed else None,
            files=[{"path": "SKILL.md", "size": 2200}, {"path": "scripts/run.py", "size": 3200}],
            readme=f"# {name}\n\n{desc}\n\n## 用法\n\n在被调用的工作区内直接触发该技能，智能体会自动读取 SKILL.md 并按其流程执行。\n",
        ))


def _seed_conversation(db, cid, project_id, title, q, age_ms, host_id) -> None:
    now = _now()
    conv = m.Conversation(
        id=cid, teamId="u_demo", userId="u_demo", projectId=project_id, title=title,
        hostId=host_id, workdir="/home/clawsgo/workspace", modelId="clawsgo-1.0-lithium",
        context="default", effort="high", mode="agent", pinnedAt=None, archivedAt=None,
        streamId=None, createdAt=_ago(age_ms + 12 * 60e3), updatedAt=_ago(age_ms),
        lastMessageAt=_ago(age_ms), lastMessagePreview="已完成降解路径梳理，给出 4 条可验证判据与实验设计。",
        lastMessageAttachments=1,
    )
    db.add(conv)
    db.add_all([
        m.Message(
            id=cid + "_m1", conversationId=cid, role="user", seq=1, modelId=None, context=None,
            parts=[{"type": "text", "text": q}], streamId=None, meta=None, createdAt=_ago(age_ms + 11 * 60e3),
        ),
        m.Message(
            id=cid + "_m2", conversationId=cid, role="assistant", seq=2, modelId="clawsgo-1.0-lithium",
            context="default", parts=_demo_parts(), streamId=None,
            meta={"usage": {"inputTokens": 1840, "outputTokens": 962, "contextTokens": 2802}, "durationMs": 18400},
            createdAt=_ago(age_ms + 10 * 60e3),
        ),
    ])


def _demo_parts():
    return [
        {"type": "reasoning", "text": "先界定问题边界，再按「机制 → 判据 → 实验」三层组织回答。"},
        {"type": "tool", "toolUseId": "call_demo1", "toolName": "Glob",
         "input": {"pattern": "data/**/*.csv", "description": "扫描工作区数据文件"},
         "output": "data/raw/20260301_S1.csv\ndata/raw/20260302_S2.csv\ndata/processed/xrd_summary.csv",
         "state": "output-available", "durationMs": 420},
        {"type": "text", "text": (
            "## 结论\n\n已完成分析，给出 4 条可验证判据：\n\n"
            "1. 水合 → 相变：生成一水合物 MAPbI3·H2O，晶格膨胀后不可逆分解。\n"
            "2. 碘空位迁移：水分降低离子迁移活化能，碘空位向界面富集。\n"
            "3. 界面化学反应：与电极或掺杂剂发生氧化还原。\n"
            "4. 温度耦合：85℃ 加速路径 1–3 的动力学常数。\n\n"
            "### 可验证判据\n\n| 判据 | 观测手段 | 预期信号 |\n"
            "| --- | --- | --- |\n"
            "| 一水合物生成 | XRD | 2θ ≈ 8.7° 出现新峰 |\n"
            "| 碘空位富集 | XPS | I 3d 结合能负移 0.2–0.4 eV |\n\n"
            "### 复现步骤\n\n```bash\npython scripts/humidity_expose.py --rh 85 --temp 85 --hours 0,24,96,240\n```\n\n"
            "需要我把峰位漂移也做定量拟合吗？"
        )},
    ]
