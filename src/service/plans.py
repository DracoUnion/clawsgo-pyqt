"""Plan tables — port of `clawsgo-opensource/server/lib/plans.mjs`.

Prices are in cents (分). Monthly credits per plan.
"""
from __future__ import annotations

# planId: (rank, label, monthlyCents, monthlyCredits, diskGb)
PLANS = {
    "free": {"rank": 0, "label": "免费版", "labelEn": "Free", "monthlyCents": 0, "monthlyCredits": 0, "diskGb": 10},
    "plus": {"rank": 1, "label": "Plus", "labelEn": "Plus", "monthlyCents": 990, "monthlyCredits": 30000, "diskGb": 20},
    "pro": {"rank": 2, "label": "Pro", "labelEn": "Pro", "monthlyCents": 2990, "monthlyCredits": 120000, "diskGb": 50},
    "ultra": {"rank": 3, "label": "Ultra", "labelEn": "Ultra", "monthlyCents": 9990, "monthlyCredits": 500000, "diskGb": 100},
    "team": {"rank": 4, "label": "团队版", "labelEn": "Team", "monthlyCents": 29990, "monthlyCredits": 1500000, "diskGb": 200},
    "enterprise": {"rank": 5, "label": "企业版", "labelEn": "Enterprise", "monthlyCents": 99900, "monthlyCredits": 5000000, "diskGb": 500},
}

# planId -> display title used on cards
PLAN_TITLES = {
    "free": "Free",
    "plus": "Plus",
    "pro": "Pro",
    "ultra": "Ultra",
    "team": "团队版",
    "enterprise": "企业版",
}

SELF_SERVE = ["plus", "pro", "ultra"]
MONTH_OPTIONS = [1, 12]
ANNUAL_DISCOUNT_BP = 6000  # yearly = 60% of monthly*12
GATEWAYS = ["stripe", "wechat", "alipay"]
INVOICE_PLANS = ["pro", "ultra", "team", "enterprise"]

# [[yuan, bonusBp], ...]
TOPUP_TIERS = [[10, 500], [50, 1000], [100, 1500], [500, 2000], [1000, 3000]]

_MODELS = {
    "free": ["lithium"],
    "plus": ["lithium", "silicon", "claude-sonnet-5", "gpt-5.6-terra"],
    "pro": ["lithium", "silicon", "titanium", "claude-opus-5", "gpt-5.6-sol", "gpt-6-astra",
            "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "gpt-5.5"],
    "ultra": ["lithium", "silicon", "titanium", "claude-opus-5", "gpt-5.6-sol", "gpt-6-astra",
              "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "gpt-5.5"],
    "team": ["lithium", "silicon", "titanium", "claude-opus-5", "gpt-5.6-sol", "gpt-6-astra",
             "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "gpt-5.5",
             "claude-fable-5-1", "claude-fable-5"],
    "enterprise": ["lithium", "silicon", "titanium", "claude-opus-5", "gpt-5.6-sol",
                   "gpt-6-astra", "gpt-5.5", "claude-fable-5-1", "claude-fable-5"],
}

_CPU = {"free": 2, "plus": 3, "pro": 10, "ultra": 20, "team": 50, "enterprise": 100}
_MEM = {"free": 4, "plus": 8, "pro": 16, "ultra": 32, "team": 64, "enterprise": 128}
_AGENT_MEMORY = {"free": "50 MB", "plus": "200 MB", "pro": "1 GB", "ultra": "1 GB",
                 "team": "1 GB", "enterprise": "1 GB"}
_HIGHLIGHT = {"plus": "日常使用", "pro": "重度用户", "ultra": "专业团队"}


def plan_cycle_cents(plan_id: str, months: int) -> int:
    spec = PLANS[plan_id]
    if months == 12:
        return round(spec["monthlyCents"] * 12 * 0.6)
    return spec["monthlyCents"] * months


def plan_spec(plan_id: str) -> dict:
    p = PLANS[plan_id]
    yearly = plan_cycle_cents(plan_id, 12)
    return {
        "planId": plan_id,
        "label": PLAN_TITLES[plan_id],
        "monthlyCents": p["monthlyCents"],
        "yearlyCents": yearly,
        "monthlyCredits": p["monthlyCredits"],
        "cpus": _CPU[plan_id],
        "memoryGb": _MEM[plan_id],
        "diskGb": p["diskGb"],
        "concurrency": None if _CPU[plan_id] >= 20 else _CPU[plan_id],
        "hostCpu": _CPU[plan_id],
        "agentMemory": _AGENT_MEMORY[plan_id],
        "models": _MODELS[plan_id],
        "highlight": _HIGHLIGHT.get(plan_id),
        "invoice": plan_id in INVOICE_PLANS,
        "selfServe": plan_id in SELF_SERVE,
    }


def all_plan_specs() -> list:
    return [plan_spec(p) for p in ["free", "plus", "pro", "ultra", "team", "enterprise"]]


def plan_rank(plan_id: str) -> int:
    return PLANS.get(plan_id, {}).get("rank", 0)


def topup_tiers() -> list:
    out = []
    for yuan, bonus_bp in TOPUP_TIERS:
        price_cents = yuan * 100
        credit_milli = price_cents * 1000
        bonus_milli = round(credit_milli * bonus_bp / 10000)
        out.append({
            "priceCents": price_cents,
            "bonusBp": bonus_bp,
            "creditMilli": credit_milli,
            "bonusMilli": bonus_milli,
            "yuan": yuan,
        })
    return out