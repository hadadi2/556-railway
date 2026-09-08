"""أسعار الباقات — the ONE pricing source (قرار مالك 2026-08-17).

قرار المالك الحرفي: «اضف الباقات من اقتراحك واسعار» ثم إقرار الأرقام بالريال
السعودي شهرياً، ثم إعادة التسعير السوقية 2026-08-18 («اعد تصميم الباقات بناء
على تسعيرة السوق وخلي فيه خصم عن الاشتراك السنوي»): أساسية مجاناً بدراسة
تجريبية · فضية 699 · ذهبية 1,799 · بلاتينية 4,499 ر.س/شهر، والسنوي = 10
أشهر (شهران مجاناً ≈ خصم 17%). المصدر ملف `config/pricing.yaml` المسطّح —
المالك يعدّل الأرقام بلا كود — ويُدمَج مع حصص `models.TIER_LIMITS` الحقيقية
في `public_pricing()` الذي تخدمه نقطة `GET /platform/pricing` العامة.

قواعد الصدق:
- تعذُّر قراءة الملف = السقوط إلى `_DEFAULTS` المعلَنة (الأرقام المُقرّة
  نفسها) مع وسم `source="defaults"` — لا سعر مخفي ولا انهيار.
- لا استيراد شبكي هنا إطلاقاً (قراءة ملف محلي فقط).
- `price_cents_per_year` القديمة في TIER_LIMITS بلا قارئ — تبقى كما هي حتى
  قرار حذف صريح؛ هذا الملف هو مصدر العرض المعتمد.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_PRICING_PATH = os.path.join(os.path.dirname(__file__), "..", "config",
                             "pricing.yaml")

# الافتراضات = الأرقام المُقرّة حرفياً (إعادة التسعير السوقية 2026-08-18) —
# تُستعمل فقط إن تعذّر الملف، ويُعلَن ذلك في الرد.
_DEFAULTS = {
    "currency": "SAR",
    "billing_cycle": "monthly",
    "basic_price": 0,
    "silver_price": 699,
    "gold_price": 1799,
    "platinum_price": 4499,
    "basic_price_annual": 0,
    "silver_price_annual": 6990,
    "gold_price_annual": 17990,
    "platinum_price_annual": 44990,
}

_TIER_ORDER = ("basic", "silver", "gold", "platinum")


def load_pricing(path: str | None = None) -> dict:
    """اقرأ ملف الأسعار المسطّح — نفس نمط `silk_reports._load_branding`.

    يعيد dict كاملاً دائماً: قيم الملف حيث صحّت، والافتراض المعلَن حيث غابت،
    مع `source` = "file" أو "defaults".
    """
    p = path or _PRICING_PATH
    out = dict(_DEFAULTS)
    source = "defaults"
    try:
        raw: dict[str, str] = {}
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                raw[k.strip()] = v.strip()
        for key in _DEFAULTS:
            if key not in raw or raw[key] == "":
                continue
            # كل مفتاح افتراضه عدد صحيح (أسعار شهرية/سنوية + نسبة الخصم)
            # يُقرأ عدداً — التالف يُبقي الافتراض المعلَن.
            if isinstance(_DEFAULTS[key], int):
                try:
                    out[key] = max(0, int(raw[key]))
                except ValueError:
                    log.warning("pricing.yaml: %s ليست رقماً (%r) — الافتراض "
                                "المعلَن يبقى", key, raw[key])
                    continue
            else:
                out[key] = raw[key]
        source = "file"
    except OSError as exc:
        log.warning("pricing.yaml غير مقروء (%s) — الأسعار الافتراضية المعلنة",
                    exc)
    out["source"] = source
    return out


def _payment_config() -> dict:
    """حالة مزوّد الدفع — من `payments.provider_from_env` (استيراد كسول).

    غياب الوحدة/المزوّد = «غير مهيأ» معلَنة — صفحة الدفع تقول الحقيقة قبل
    أي إرسال.
    """
    try:
        from . import payments
        provider = payments.provider_from_env()
        return {"configured": provider is not None,
                "provider": getattr(provider, "NAME", None)}
    except Exception:  # noqa: BLE001 — قبل وجود وحدة الدفع (ترتيب الموجات)
        return {"configured": False, "provider": None}


def public_pricing() -> dict:
    """الرد العام للباقات — القيم **الفعّالة** + حصص TIER_LIMITS الحقيقية.

    كل رقم حصّة يأتي من `tier_config.effective_limits` (المصدر الواحد الذي
    تفرضه البوّابة فعلاً) — لا نسخة ثانية هنا قد تنحرف عن البوابات الحقيقية.

    والسعر كذلك: تجاوز المالك من لوحة الأدمِن (جدول `tier_settings`، قرار
    2026-08-20) يفوز على `config/pricing.yaml`، ويحمل كل صفٍّ `overridden`
    فيُعرَف مصدره — قيمةٌ من القاعدة تُعرَض بلا وسمٍ توهم أنها السعر المُقرّ
    في الملف. تعذُّر فتح القاعدة (قراءةٌ عامّة قبل أي ترحيل) = السقوط إلى
    الملف والثوابت كما كان تماماً، بلا انهيار ولا رقم مخفيّ.
    """
    from .models import tier_limits
    cfg = load_pricing()
    eff = {}
    try:
        from . import db as pdb, tier_config
        conn = pdb.connect()
        try:
            eff = tier_config.effective_pricing(conn)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — قاعدة غائبة/غير مرحَّلة = لا تجاوزات
        log.warning("pricing: tier overrides unreadable; serving file values")
        eff = {}
    tiers = []
    for key in _TIER_ORDER:
        lim = tier_limits(key)
        ov = eff.get(key) or {}
        tiers.append({
            "key": key,
            "price": int(ov.get("price", cfg.get(f"{key}_price", 0))),
            "price_annual": int(ov.get("price_annual",
                                       cfg.get(f"{key}_price_annual", 0))),
            # R4.9: طبقةُ مدى الحياة لا تنشر رقماً شهرياً لا يقرؤه `quota` —
            # صفرٌ صريح ولو حمل التجاوزُ غيرَه.
            "monthly_studies": (0 if lim.lifetime_studies > 0 else
                                int(ov.get("monthly_studies",
                                           lim.monthly_studies))),
            "overridden": bool(ov.get("overridden", False)),
            "lifetime_studies": lim.lifetime_studies,                      # ‎-1 = بلا حدّ
            "dashboard": lim.dashboard,
            "api_access": bool(lim.api_access),
            "white_label": bool(lim.white_label),
            "export": bool(lim.export),
        })
    # نسبة الخصم السنوي تُشتق من الأسعار نفسها (أدنى نسبة بين الباقات
    # المدفوعة التي لها سعر سنوي) — لا حقل يدوي ثانٍ قد ينحرف عن الحقيقة.
    discounts = [round((1 - t["price_annual"] / (12 * t["price"])) * 100)
                 for t in tiers if t["price"] > 0 and t["price_annual"] > 0]
    has_annual = bool(discounts)
    return {"currency": cfg["currency"],
            "cycle": cfg["billing_cycle"],          # وحدة حقل price الأساسي
            "cycles": (["monthly", "annual"] if has_annual else ["monthly"]),
            "annual_discount_pct": min(discounts) if discounts else 0,
            "source": cfg["source"], "payment": _payment_config(),
            "tiers": tiers}
