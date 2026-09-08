"""استحقاقات الطبقة — the ONE tier-gate mechanism (PR-2).

كل بوّابة طبقة تمرّ من هنا: عدد المقاعد، القمع، مستوى اللوحة، وصول الـAPI،
العلامة البيضاء، التصدير. الحدود نفسها تعيش في `models.TIER_LIMITS` (مصدر واحد)
وهذه الوحدة تقرأها وتفرضها، فلا تتناثر مقارنات الطبقات في النقاط النهائية.

لماذا وحدة مستقلّة: موجتا اللوحات (PR-6) والقمع (PR-7) ستحتاجان نفس البوّابة؛
لو فرض كل مسارٍ طبقتَه بيده لظهر بابٌ ثانٍ يتخطّى الحدّ. Single gate, reused.

`TierGateError` تحمل دعوة الترقية التي تطلبها المواصفة (§2: «block, show upgrade
prompt, write audit log entry») فتترجمها النقطة النهائية إلى 403 مفهومة.

Every tier decision reads TIER_LIMITS through this module — PR-6 (dashboards)
call the same gate instead of comparing tiers inline. (The funnel
feature was deleted outright with prospecting — owner decision 2026-08-17.)
"""
from __future__ import annotations

import dataclasses
import sqlite3

from . import audit, quota, tier_config
from .db import now_iso
from .models import Tier, tier_limits

UNLIMITED = -1


class TierGateError(Exception):
    """ميزة/حدّ يتجاوز الطبقة — carries the machine-readable upgrade prompt.

    `feature` كود الميزة، `tier` الطبقة الحالية، `required_tiers` أدنى الطبقات
    التي تمنحها — كي تعرض الواجهة «ارقِ إلى Gold» لا رسالةً عامّة.
    """

    def __init__(self, feature: str, tier: str, required_tiers: list[str],
                 detail: str = "", limit: int | None = None,
                 used: int | None = None):
        self.feature = feature
        self.tier = tier
        self.required_tiers = required_tiers
        self.limit = limit
        self.used = used
        super().__init__(detail or f"{feature} is not available on the {tier} tier")

    def as_detail(self) -> dict:
        """حمولة 403 — the endpoint returns this verbatim as the 403 detail."""
        out = {"error": "tier_gate", "feature": self.feature, "tier": self.tier,
               "required_tiers": self.required_tiers, "upgrade": True,
               "message": str(self)}
        if self.limit is not None:
            out["limit"] = self.limit
        if self.used is not None:
            out["used"] = self.used
        return out


# ── الميزات المنطقية · boolean features ──────────────────────────────────────
# اسم الميزة → قارئٌ من TierLimits. القراءة من مصدر واحد تمنع انحراف الجداول.
_BOOL_FEATURES = {
    "api_access": lambda lim: lim.api_access,
    "white_label": lambda lim: lim.white_label,
    "export": lambda lim: lim.export,
}


def _tier_name(tier: str | Tier) -> str:
    return tier.value if isinstance(tier, Tier) else str(tier)


def _tiers_granting(feature: str) -> list[str]:
    """أدنى الطبقات التي تمنح الميزة — which tiers grant it (for the prompt)."""
    reader = _BOOL_FEATURES.get(feature)
    if reader is None:
        return []
    return [t.value for t in Tier if reader(tier_limits(t))]


def has_feature(tier: str | Tier, feature: str) -> bool:
    """هل تمنح الطبقة هذه الميزة؟ — pure check, no raise.

    ميزة مجهولة ترفع ValueError لا ترجع False: خطأٌ مطبعيّ في اسم ميزة
    (`"exports"`) كان سيفتح البوّابة صمتاً لكل الطبقات. An unknown feature is a
    bug, not a denial — fail loudly instead of silently allowing.
    """
    reader = _BOOL_FEATURES.get(feature)
    if reader is None:
        raise ValueError(f"unknown tier feature: {feature}")
    return bool(reader(tier_limits(tier)))


def require_feature(tier: str | Tier, feature: str) -> None:
    """افرض ميزة أو ارفع TierGateError — the gate PR-6/PR-7 call."""
    if not has_feature(tier, feature):
        raise TierGateError(feature, _tier_name(tier), _tiers_granting(feature))


def dashboard_level(tier: str | Tier) -> str:
    """مستوى اللوحة — 'none' | 'basic' | 'full' (PR-6 يقرأه)."""
    return tier_limits(tier).dashboard


# ── ملخّص الاستحقاقات + الاستخدام · entitlements + usage snapshot ────────────
@dataclasses.dataclass(frozen=True)
class Entitlements:
    """ما تمنحه الطبقة + ما استُهلِك — consumed by PR-6 dashboards verbatim."""
    tier: str
    studies_limit: int          # الشهري، أو سقف مدى الحياة لـBasic
    studies_used: int
    studies_period: str         # 'month' | 'lifetime'
    dashboard: str
    api_access: bool
    white_label: bool
    export: bool
    # حصّة المستخدم (قرار مالك 2026-08-17) — 0 في الحدّ = بلا سقفٍ لكل مستخدم.
    per_user_studies_limit: int = 0
    per_user_studies_used: int = 0   # للمستخدم المنادي فقط (0 إن لم يُمرَّر)

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def studies_used_effective(tier: Tier, stored_count: int,
                           stored_period: str | None) -> int:
    """العدّاد الشهري كما يراه الإطلاق فعلاً — the count a launch would see.

    `quota.reserve_launch` يصفّر العدّاد **كسولاً** عند دخول شهر جديد، فالقراءة
    الخام قد تعرض عدّاد شهرٍ مضى: حساب Silver أطلق دراستين في يونيو يظهر
    «2/2 — ممنوع» في يوليو قبل أوّل إطلاق، بينما الإطلاق **سينجح** لأن الحجز
    يصفّر أولاً. رقمان متعارضان للعميل نفسه.

    التصحيح هنا **قراءةٌ خالصة**: لا تكتب في قاعدة على مسار GET؛ فقط طبّق نفس
    قاعدة الفترة التي يطبّقها الحجز. Basic لا فترة لها (مدى الحياة).
    Read-only mirror of the lazy roll — never writes on a GET path.
    """
    if tier == Tier.BASIC:
        return int(stored_count)
    if stored_period != quota.current_period():
        return 0        # شهر جديد لم يُطلَق فيه بعد · new month, counter is stale
    return int(stored_count)


class TierChangeError(ValueError):
    """تغيير طبقة مرفوض — a refused tier change (carries a machine-readable code)."""

    def __init__(self, code: str, message: str, **extra):
        self.code = code
        self.extra = extra
        super().__init__(message)

    def as_detail(self) -> dict:
        return {"error": self.code, "message": str(self), **self.extra}


def set_account_tier(conn: sqlite3.Connection, account_id: int,
                     new_tier: str | Tier, *, admin_user_id: int | None) -> dict:
    """غيّر طبقة حساب (أدمِن سِلك) — audited; counters are untouched.

    (كان التخفيضُ يُرفَض إن ترك «مقاعد زائدة»؛ سقط الفحص مع حذف المقاعد
    نهائياً — قرار المالك 2026-08-19: حسابٌ واحد لكل مصنع، فلا سقفَ مستخدمين
    يمكن خرقُه. The seat-cap downgrade refusal died with the seats themselves.)

    الحصص الشهرية **لا** تُصفَّر عند التغيير: العدّاد يقيس ما استُهلِك فعلاً هذا
    الشهر، وترقيةٌ وسط الشهر ترفع السقف لا الاستهلاك. Counters are untouched.
    """
    row = conn.execute("SELECT id, kind, tier FROM accounts WHERE id = ?",
                       (account_id,)).fetchone()
    if row is None:
        raise TierChangeError("account_not_found", f"no account {account_id}")
    if row["kind"] != "factory":
        # حساب سِلك/الخزنة ليس مشتركاً؛ طبقته بلا معنى وتغييرها يفتح باباً
        # لتعديل حساب المنصّة نفسه. Only factory accounts are subscribers.
        raise TierChangeError("not_a_factory_account",
                              "only factory accounts have a subscription tier")
    try:
        target = new_tier if isinstance(new_tier, Tier) else Tier(str(new_tier))
    except ValueError as exc:
        raise TierChangeError(
            "unknown_tier", f"unknown tier: {new_tier}",
            valid_tiers=[t.value for t in Tier]) from exc
    old = Tier(row["tier"])
    if target == old:
        return {"account_id": account_id, "tier": old.value, "changed": False}

    # (حُذف فحصُ «تخفيضٌ يترك مقاعد زائدة» مع حذف المقاعد نهائياً — قرار
    # المالك 2026-08-19: حسابٌ واحد لكل مصنع، فلا سقف مستخدمين يُخرَق.)
    conn.execute("UPDATE accounts SET tier = ?, updated_at = ? WHERE id = ?",
                 (target.value, now_iso(), account_id))
    audit.record(conn, action="account_tier_changed", user_id=admin_user_id,
                 account_id=account_id, resource_type="account",
                 resource_id=account_id,
                 changes={"from": old.value, "to": target.value})
    conn.commit()
    return {"account_id": account_id, "tier": target.value, "changed": True,
            "previous_tier": old.value}


def set_per_user_quota(conn: sqlite3.Connection, account_id: int,
                       value: int | None, *, admin_user_id: int | None) -> dict:
    """اضبط حصّة الدراسات لكل مستخدم في حساب مصنع (أدمِن) — audited.

    قرار مالك 2026-08-17: «الأدمِن يحدد عدد الدراسات لكل مستخدم بناءً على
    الباقة». `None` يمسح التجاوز (يعود افتراض الطبقة)، و`0` يعني صراحةً «بلا
    حدٍّ لكل مستخدم»، و`>=1` هو السقف الشهري لكل مستخدم. لا يمسّ أي عدّاد —
    العدّ مشتقّ من الدراسات نفسها (`quota.user_launches_this_period`).
    None clears the override (tier default applies); 0 = explicitly uncapped;
    >=1 caps each user's monthly launches. Counters are untouched.
    """
    row = conn.execute("SELECT id, kind, tier, per_user_monthly_studies "
                       "FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise TierChangeError("account_not_found", f"no account {account_id}")
    if row["kind"] != "factory":
        raise TierChangeError("not_a_factory_account",
                              "only factory accounts have study quotas")
    if value is not None:
        value = int(value)
        if value < 0:
            raise TierChangeError("invalid_quota",
                                  "per_user_monthly_studies must be >= 0 or null")
    conn.execute("UPDATE accounts SET per_user_monthly_studies = ?, "
                 "updated_at = ? WHERE id = ?",
                 (value, now_iso(), account_id))
    audit.record(conn, action="per_user_quota_changed", user_id=admin_user_id,
                 account_id=account_id, resource_type="account",
                 resource_id=account_id,
                 changes={"from": row["per_user_monthly_studies"], "to": value})
    conn.commit()
    return {"account_id": account_id, "per_user_monthly_studies": value,
            "effective_limit": quota.per_user_limit(conn, account_id)}


def snapshot(conn: sqlite3.Connection, account_id: int,
             user_id: int | None = None) -> Entitlements:
    """لقطة استحقاقات حساب — limits + current usage in one read.

    Basic تُقاس على عدّاد مدى الحياة (لا يُصفَّر)، والبقية على العدّاد الشهري بعد
    تطبيق قاعدة الفترة — نفس تمييز `quota.py` كي لا يظهر رقمان متعارضان للعميل.
    `user_id` (اختياري) يُرفِق استهلاك **هذا المستخدم** من حصّة المستخدم.
    """
    row = conn.execute(
        "SELECT tier, current_month_study_count, lifetime_study_count, quota_period "
        "FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise ValueError(f"no account {account_id}")
    tier = Tier(row["tier"])
    # نفس مصدر البوّابة بالضبط — لو قرأ الملخّص الثابتَ والبوّابةُ
    # التجاوزَ لعرضت اللوحة حدّاً غير الذي يُرفَض عنده الإطلاق.
    lim = tier_config.effective_limits(conn, tier)
    if tier == Tier.BASIC:
        studies_limit, studies_used, period = (lim.lifetime_studies,
                                               int(row["lifetime_study_count"]),
                                               "lifetime")
    else:
        studies_limit, period = lim.monthly_studies, "month"
        studies_used = studies_used_effective(
            tier, row["current_month_study_count"], row["quota_period"])
    per_user_lim = quota.per_user_limit(conn, account_id)
    per_user_used = (quota.user_launches_this_period(conn, account_id, user_id)
                     if user_id is not None else 0)
    return Entitlements(
        tier=tier.value, studies_limit=studies_limit, studies_used=studies_used,
        studies_period=period, dashboard=lim.dashboard,
        api_access=lim.api_access, white_label=lim.white_label, export=lim.export,
        per_user_studies_limit=per_user_lim, per_user_studies_used=per_user_used)
