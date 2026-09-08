"""محوّل الدفع العام — the provider-agnostic payments adapter (2026-08-17).

قرار المالك الحرفي: «لم أقرر — جهّزها عامة»: صفحة دفع جاهزة للربط بأي مزوّد
(مُيسر/Tap/Stripe) بمتغير بيئة واحد `SILK_PAY_PROVIDER` وملف محوّل واحد هو
هذا الملف — لا شيفرة دفع منثورة في النقاط.

قواعد غير قابلة للكسر:
- **لا دفع وهمي أبداً**: تكامل المزوّدات لم يُبنَ بعد، فكل مزوّد هنا يرفع
  `ProviderNotConfigured` **حتى مع مفتاحه مضبوطاً** — «مفتاح موجود» لا يساوي
  «تكامل مبني»، وتحويلٌ شكلي إلى صفحة دفع لا تعمل اختلاقٌ صريح. حين يقرّر
  المالك مزوّده يُبنى `create_checkout` الحقيقي لذلك الصنف وحده (+ ترحيل
  Operation.SUBSCRIPTION المؤجَّل عمداً حتى ذلك اليوم).
- **صفر استيراد شبكي على مستوى الوحدة** (نمط `correlation.py` المحروس):
  الوحدة تُستورد في كل إقلاع منصّة؛ النداء الشبكي — يوم يُبنى — يكون كسولاً
  داخل الدالة.
- الرفض المهيّأ يتدهور برسالة معلنة ثنائية اللغة يعيدها المسار للعميل —
  الاهتمام يُسجَّل في التدقيق فلا يضيع طلبُ مشترِك.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


class ProviderNotConfigured(Exception):
    """الدفع الإلكتروني غير مفعَّل — رسالة معلنة ثنائية اللغة للعميل."""

    message_ar = ("الدفع الإلكتروني لم يُفعَّل بعد — سجّلنا طلبك وسيتواصل "
                  "معك فريق سِلك لإتمام الاشتراك.")
    message_en = ("Online payment is not enabled yet — we recorded your "
                  "request and the Silk team will contact you to complete "
                  "the subscription.")


class _BaseProvider:
    """العقد الواحد لكل مزوّد: `create_checkout(plan, cycle, customer)`.

    يعيد — يوم يُبنى التكامل — `{"url": <redirect>, "reference": <id>}`.
    """

    NAME = "base"
    ENV_KEYS: tuple[str, ...] = ()

    def create_checkout(self, plan: str, billing_cycle: str,
                        customer: dict) -> dict:
        raise ProviderNotConfigured()


class MoyasarProvider(_BaseProvider):
    """مُيسر (moyasar.com) — سيقرأ `MOYASAR_SECRET_KEY` حين يُبنى التكامل."""

    NAME = "moyasar"
    ENV_KEYS = ("MOYASAR_SECRET_KEY",)


class TapProvider(_BaseProvider):
    """Tap (tap.company) — سيقرأ `TAP_SECRET_KEY` حين يُبنى التكامل."""

    NAME = "tap"
    ENV_KEYS = ("TAP_SECRET_KEY",)


class StripeProvider(_BaseProvider):
    """Stripe — سيقرأ `STRIPE_SECRET_KEY` حين يُبنى التكامل."""

    NAME = "stripe"
    ENV_KEYS = ("STRIPE_SECRET_KEY",)


PROVIDERS: dict[str, type[_BaseProvider]] = {
    "moyasar": MoyasarProvider,
    "tap": TapProvider,
    "stripe": StripeProvider,
}


def provider_from_env() -> _BaseProvider | None:
    """المزوّد المختار من `SILK_PAY_PROVIDER` — None لغير المضبوط/المجهول.

    قيمة مجهولة = تحذير سجلّ + None معلَنة (الصفحة تعرض «غير مفعَّل») —
    لا انهيار إقلاع بسبب حرف خاطئ في متغير بيئة.
    """
    raw = os.environ.get("SILK_PAY_PROVIDER", "").strip().lower()
    if not raw:
        return None
    cls = PROVIDERS.get(raw)
    if cls is None:
        log.warning("SILK_PAY_PROVIDER=%r غير معروف — المعروف: %s",
                    raw, sorted(PROVIDERS))
        return None
    return cls()
