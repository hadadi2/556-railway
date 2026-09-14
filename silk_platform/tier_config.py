"""إعدادات الباقات الفعّالة — the ONE effective-tier source (2026-08-20).

قرار المالك: جدول الباقات في لوحة الأدمِن يعدّل **السعر وحصّة الدراسات**.
هذه الوحدة هي الطبقة الوحيدة التي تدمج المصادر الثلاثة بترتيبٍ معلَن:

    models.TIER_LIMITS (ثوابت الكود)  ←  الحصص الافتراضية
    config/pricing.yaml               ←  الأسعار المُقرّة (بذرة/سقوط)
    جدول tier_settings في القاعدة     ←  تجاوز المالك الحيّ (يفوز)

لماذا القاعدة تفوز: هي وحدها على الوحدة المركَّبة (`db.db_path` يشتقّ من
`SILK_DATA_DIR`)؛ الملف داخل صورة النشر والثوابتُ كود، فالكتابة على أيٍّ منهما
تتبخّر عند إعادة النشر (الدرس ٤). The DB is the only durable writable source.

**بلا ذاكرة مخبّأة عامّة عمداً.** قيمةٌ قديمة في السعر إزعاج، وفي الحصّة
إطلاقٌ كان يجب منعه — والقراءة صفٌّ واحد بمفتاح أساسي من SQLite محلّي.
No process-level cache: a stale quota is an admission that should have failed.

كل قارئ للحصص يمرّ من `effective_limits` (`quota.py`، `entitlements.py`،
`api.py`)، وكل قارئ للأسعار من `effective_pricing` (`pricing.public_pricing`)
— فيبقى `GET /platform/pricing` المصدر الواحد الذي تقرؤه صفحتا الهبوط والدفع.
"""
from __future__ import annotations

import dataclasses
import logging
import sqlite3

from . import audit
from .db import now_iso
from .models import Tier, TierLimits, tier_limits

log = logging.getLogger(__name__)

_TIERS = ("basic", "silver", "gold")


def _rows(conn: sqlite3.Connection) -> dict:
    """كل صفوف التجاوز في استعلامٍ واحد — {tier: Row}. غيابُ الجدول = {}.

    قاعدةٌ لم تُرحَّل بعد (ملفٌ قديم) تُعامَل كقاعدةٍ بلا تجاوزات: السلوك يعود
    إلى ما قبل هذه الموجة بالضبط بدل أن يسقط الطلب. **وهذا الاستثناء الوحيد
    المبتلَع**: أيّ `OperationalError` آخر — «database is locked» أو عمودٌ
    مفقود بعد ترحيلٍ ناقص — يُرفَع كما هو، لأن ابتلاعه يعيد الحصّةَ صامتاً
    إلى الثابت فيُقبَل إطلاقٌ كان يجب منعه، وهو بعينه ما تمنعه هذه الوحدة.
    Only "no such table" is treated as "no overrides" — never a locked DB.
    """
    try:
        rows = conn.execute(
            "SELECT tier, price, price_annual, monthly_studies, updated_at "
            "FROM tier_settings").fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise
        log.info("tier_settings table absent; serving defaults")
        return {}
    return {r["tier"]: r for r in rows}


def _monthly_for(lim: TierLimits, row) -> int:
    """الحصّة الشهرية المعروضة/المنفَّذة لهذه الطبقة بعد صفّ التجاوز.

    R4.9 (تدقيق 2026-09-01، BIZ-2): طبقةُ مدى الحياة (`lifetime_studies > 0`)
    شهريُّها **صفرٌ دائماً** — ولو حمل الجدولُ صفّاً قديماً بغيره (تركةُ ما
    قبل الإكراه): العرضُ يتبع القاعدةَ التي يفرضها `quota` فعلاً، لا رقماً لا
    يقرؤه أحد.
    """
    if lim.lifetime_studies > 0:
        return 0
    return (int(row["monthly_studies"]) if row is not None
            else int(lim.monthly_studies))


def effective_limits(conn: sqlite3.Connection, tier: str | Tier) -> TierLimits:
    """حدود الطبقة بعد تجاوز المالك — the limits that are actually enforced.

    الحصّة الشهرية وحدها قابلة للتجاوز اليوم (قرار المالك: «السعر + حصّة
    الدراسات»)؛ باقي الحقول من الثوابت كما هي. `dataclasses.replace` يحفظ
    كونَ `TierLimits` مجمّدةً فلا يُعدَّل الثابتُ العام بالخطأ.
    """
    t = tier if isinstance(tier, Tier) else Tier(str(tier))
    base = tier_limits(t)
    row = _rows(conn).get(t.value)
    if row is None:
        return base
    return dataclasses.replace(base, monthly_studies=_monthly_for(base, row))


def effective_pricing(conn: sqlite3.Connection) -> dict:
    """أسعار الباقات الفعّالة + تصريحُ مصدر كلٍّ — prices with their source.

    يرجّع `{tier: {"price", "price_annual", "monthly_studies", "overridden"}}`.
    `overridden` ليس زينة: قيمةٌ من القاعدة تُعرَض بلا وسمٍ توهم القارئَ أنها
    السعر المُقرّ في `config/pricing.yaml` — وهو اختلاقُ مصدرٍ لا رقم.
    """
    from . import pricing
    cfg = pricing.load_pricing()
    rows = _rows(conn)
    out = {}
    for key in _TIERS:
        row = rows.get(key)
        lim = tier_limits(key)
        out[key] = {
            "price": int(row["price"]) if row else int(cfg.get(f"{key}_price", 0)),
            "price_annual": (int(row["price_annual"]) if row
                             else int(cfg.get(f"{key}_price_annual", 0))),
            "monthly_studies": _monthly_for(lim, row),
            "overridden": row is not None,
            "updated_at": row["updated_at"] if row else None,
        }
    return out


class TierSettingsError(ValueError):
    """إدخالٌ مرفوض — carries a machine-readable reason for the 422 detail."""

    def __init__(self, field: str, detail: str):
        self.field = field
        super().__init__(detail)


def _as_nonneg_int(value, field: str) -> int:
    """عددٌ صحيح ≥ 0 حصراً — بلا كسورٍ ولا نصٍّ ولا منطقيّ.

    `bool` نوعٌ فرعيّ من `int` في بايثون، و`True` كان سيمرّ سعراً = ١.
    و`1.5` عددُ دراساتٍ لا معنى له — الرفض المعلَن أصدق من التقريب الصامت.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TierSettingsError(field, f"{field} must be a non-negative integer")
    if value < 0:
        raise TierSettingsError(field, f"{field} must be >= 0")
    return int(value)


def set_tier(conn: sqlite3.Connection, tier: str, *, price, price_annual,
             monthly_studies, actor_user_id: int | None) -> dict:
    """اكتب تجاوز الباقة + قيد تدقيق بالقيمتين قبل/بعد. يرجّع القيم الفعّالة.

    نفس نمط `entitlements.set_per_user_quota`: تحقّق ← كتابة ← تدقيق ← commit
    واحد. القيمُ الثلاث تُكتَب معاً فلا يبقى صفٌّ نصفَ محدَّث.
    """
    key = str(tier or "").strip().lower()
    if key not in _TIERS:
        raise TierSettingsError("tier", f"unknown tier: {tier}")
    p = _as_nonneg_int(price, "price")
    pa = _as_nonneg_int(price_annual, "price_annual")
    ms = _as_nonneg_int(monthly_studies, "monthly_studies")
    # R4.9 (تدقيق 2026-09-01، BIZ-2): طبقةٌ محكومة بسقف مدى الحياة
    # (`lifetime_studies > 0`) لا يقرأ `quota` شهريَّها أبداً — قبولُ رقمٍ لها
    # ونشرُه في `/pricing` وعدٌ لا يفي به أحد (اختلاقٌ بالعرض). يُكرَه إلى صفر
    # ويُسجَّل الإكراهُ في قيد التدقيق؛ لا رفضٌ: السعران يُكتبان والقفلُ
    # القائم يتوقّع 200.
    requested_ms = ms
    coerced = tier_limits(key).lifetime_studies > 0 and ms != 0
    if coerced:
        ms = 0

    before = effective_pricing(conn)[key]
    conn.execute(
        "INSERT INTO tier_settings (tier, price, price_annual, monthly_studies, "
        "updated_at, updated_by) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(tier) DO UPDATE SET price = excluded.price, "
        "price_annual = excluded.price_annual, "
        "monthly_studies = excluded.monthly_studies, "
        "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
        (key, p, pa, ms, now_iso(), actor_user_id))
    changes = {"from": {k: before[k] for k in
                        ("price", "price_annual", "monthly_studies")},
               "to": {"price": p, "price_annual": pa, "monthly_studies": ms}}
    if coerced:
        changes["coerced"] = {"monthly_studies": {
            "requested": requested_ms, "to": 0, "reason": "lifetime_tier"}}
    audit.record(conn, action="tier_settings_changed", user_id=actor_user_id,
                 resource_type="tier", resource_id=key, changes=changes)
    conn.commit()
    return effective_pricing(conn)[key]
