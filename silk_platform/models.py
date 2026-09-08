"""الثوابت والأنواع — roles, tiers, pricing, and the auth request context.

مصدر واحد للحقيقة لحدود الأدوار والحصص والتسعير كي لا تتكرّر الأرقام في
النقاط النهائية. المال بالسنتات الصحيحة (لا عائم). Single source of truth.
"""
from __future__ import annotations

import dataclasses
import enum


class Role(str, enum.Enum):
    """أدوار النظام الثلاثة · the three system roles."""
    SILK_ADMIN = "silk_admin"      # داخلي: مقاييس مجمّعة، تمويل، مفتاح القتل
    SILK_ANALYST = "silk_analyst"  # داخلي: مجمّعات مجهّلة للقراءة فقط
    FACTORY = "factory"            # عميل: CRUD كامل على بيانات حسابه فقط


class Tier(str, enum.Enum):
    """طبقات الاشتراك · subscription tiers."""
    BASIC = "basic"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class Operation(str, enum.Enum):
    """أنواع عمليات الدفتر · ledger operation types (mirror the CHECK constraint)."""
    EMAIL_SENT = "email_sent"
    REPORT_GENERATED = "report_generated"
    WALLET_FUNDED = "wallet_funded"
    API_CALL = "api_call"
    STORAGE_CHARGE = "storage_charge"
    COMPARISON_REPORT = "comparison_report"
    DRAFT_EMAIL = "draft_email"


# ── حدود الطبقات · tier limits ───────────────────────────────────────────────
# monthly_studies: العدد المسموح شهرياً. Basic خاصّة: 1 مدى الحياة (لا تُصفَّر).
# per_user_monthly_studies: سقفُ إطلاقات **كل مستخدم** شهرياً (قرار مالك
#   2026-08-17). 0 = بلا حدٍّ لكل مستخدم (سقف الحساب وحده يحكم) — وهو افتراض
#   كل الطبقات كي لا يتغيّر سلوك حسابٍ قائم؛ الأدمِن يضبط تجاوزاً لكل حساب
#   عبر accounts.per_user_monthly_studies (راجع entitlements.per_user_limit).
@dataclasses.dataclass(frozen=True)
class TierLimits:
    monthly_studies: int
    lifetime_studies: int          # >0 فقط لـ Basic؛ 0 يعني «لا سقف مدى حياة»
    dashboard: str                 # 'none' | 'basic' | 'full'
    api_access: bool
    white_label: bool
    export: bool
    price_cents_per_year: int
    per_user_monthly_studies: int = 0   # 0 = بلا حدّ لكل مستخدم
    # R4.2 (تدقيق 2026-09-01، API-2؛ قرار المالك 2026-09-02): السقفُ
    # **التجميعيّ** لبايتات الصور المرفوعة لهذا الحساب. السقفُ الوحيد قبله
    # كان ١٠ ميغابايت **لكل ملف** — فحسابٌ واحد يملأ الوحدة المركَّبة بألف
    # ملفٍّ تحت السقف، وفوترةُ التخزين تُحرِّر الفاتورة بعد الحدوث لا قبله.
    # يُتجاوَز بالبيئة لكل طبقة: `SILK_PLATFORM_STORAGE_CAP_MB_{TIER}`.
    storage_bytes: int = 100 * 1024 * 1024


TIER_LIMITS: dict[Tier, TierLimits] = {
    Tier.BASIC: TierLimits(
        monthly_studies=0, lifetime_studies=1,
        dashboard="none", api_access=False,
        white_label=False, export=False, price_cents_per_year=0,
        storage_bytes=100 * 1024 * 1024),                                # 100 MB
    Tier.SILVER: TierLimits(
        monthly_studies=2, lifetime_studies=0,
        dashboard="basic", api_access=False,
        white_label=False, export=False, price_cents_per_year=100_000,   # $1,000
        storage_bytes=1024 * 1024 * 1024),                               #   1 GB
    Tier.GOLD: TierLimits(
        monthly_studies=6, lifetime_studies=0,
        dashboard="full", api_access=False,
        white_label=False, export=False, price_cents_per_year=500_000,   # $5,000
        storage_bytes=5 * 1024 * 1024 * 1024),                           #   5 GB
    Tier.PLATINUM: TierLimits(
        monthly_studies=15, lifetime_studies=0,
        dashboard="full", api_access=True,
        white_label=True, export=True, price_cents_per_year=1_500_000,   # $15,000
        storage_bytes=20 * 1024 * 1024 * 1024),                          #  20 GB
}


def tier_limits(tier: str | Tier) -> TierLimits:
    """حدود طبقة — resolve a tier's limits (accepts str or Tier)."""
    t = tier if isinstance(tier, Tier) else Tier(str(tier))
    return TIER_LIMITS[t]


# ── التسعير (سنتات) · pricing in cents ───────────────────────────────────────
# أسعار البريد/التقرير المدفوع حُذفت مع التنقيب (قرار مالك 2026-08-17: «الباقة
# فقط» تحكم الدراسات — لا خصم لكل دراسة). سعر التخزين باقٍ لفوترة الصور
# (jobs.run_storage_billing)، وأسعار الاشتراك السنوية أعلاه في TIER_LIMITS.
PRICE_STORAGE_CENTS_PER_GB_MONTH = 10  # $0.10 / GB-month


# ── سياق المصادقة للطلب · per-request auth context ───────────────────────────
@dataclasses.dataclass(frozen=True)
class AuthContext:
    """الهويّة المحمَّلة في كل طلب — current_user / current_account / current_role.

    الوسيط (middleware) يبنيها من الجلسة ويضعها في `request.state.auth`؛ كل
    فحص صلاحية وكل استعلام مُستأجَر يشتقّ منها account_id — لا مصدر آخر.
    """
    user_id: int
    account_id: int
    role: Role
    email: str
    language_preference: str = "en"
    session_id: int | None = None

    @property
    def is_silk_admin(self) -> bool:
        return self.role == Role.SILK_ADMIN

    @property
    def is_silk_analyst(self) -> bool:
        return self.role == Role.SILK_ANALYST

    @property
    def is_factory(self) -> bool:
        return self.role == Role.FACTORY

    @property
    def is_internal(self) -> bool:
        """مستخدم سِلك داخلي (admin أو analyst) · a Silk-internal operator."""
        return self.role in (Role.SILK_ADMIN, Role.SILK_ANALYST)
