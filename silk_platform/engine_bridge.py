"""جسر المنصّة⇄المحرّك — the platform→engine study bridge (قرار مالك 2026-08-17).

قرار المالك الحرفي: «ربط آلي بالمحرك من واجهة العميل، وفيه عداد وقت يظهر له كم
متبقي على إعداد الدراسة، وكذلك له حد شهري من الدراسات، ومن واجهة الأدمن يكون
مطلعاً على الدراسات». هذه الوحدة هي ذلك الربط: إطلاق دراسةٍ مصنعٍ يشغّل
`silk_engine.analyze` في خيط daemon (نفس نمط `_research_background` في api.py
الجذري — «الخيوط تكفي، لا طوابير» قرارٌ مستقر)، والنتيجة تُخزَّن في قاعدة
المحرّك (`silk_storage`) ويُربَط معرّفها بالدراسة.

المبادئ غير القابلة للكسر هنا:
- **لا اختلاق**: ETA يُحسَب من مددٍ مقيسة فعلاً أو يُعلَن «تقديري»؛ فشل التنفيذ
  يعيد الدراسة مسودّةً بسببٍ معلن (`run_error`) — لا «مكتملة» كاذبة أبداً.
- **لا إنفاق ذكاء اصطناعي تلقائي**: التشغيل داخل `silk_context.block_ai_extras()`
  افتراضاً — إضافات كلود على مسار المصنع خلف صمّام `SILK_PLATFORM_STUDY_AI`
  (مطفأ — قاعدة الصمّامات الجديدة، الدرس ٧٠). المسار المجاني يتدهور بفجواتٍ
  معلنة لا بأرقامٍ مختلقة.
- **لا تكلفة داخلية لأي سطح مصنع**: `_COST_KEYS` هنا هي المصدر الواحد الذي
  يستورده حارس `tests/test_platform_cost_visibility.py` — كل حمولة تعبر للمصنع
  تمرّ من `strip_cost_keys`.
- **حصةٌ لا تُحرَق بلا ناتج**: دراسة فشل تشغيلها تُرجِع حجزها عبر
  `quota.release_launch` (سابقة التعويض القائمة في مسار الإطلاق نفسه).

The registry `_ACTIVE` distinguishes a restart orphan from a still-running
thread in THIS process — the orphan sweep at mount() relies on it.
"""
from __future__ import annotations

import base64
import contextvars
import datetime
import inspect
import json
import logging
import os
import re
import statistics
import threading
import time

from . import audit, notifications, quota
from .db import connect, now_iso

log = logging.getLogger(__name__)

# ── مفاتيح التكلفة الممنوعة على أي سطح مصنع · the ONE cost-key ban list ──────
# يستوردها `tests/test_platform_cost_visibility.py` (المصدر الواحد — لا نسخة
# ثانية تنحرف). أي حمولة محرّك تعبر لمصنع تُجرَّد من هذه المفاتيح تكراريّاً.
_COST_KEYS = frozenset({
    "cost_usd", "cost_usd_estimate", "cost_usd_by_model", "cost_usd_by_mission",
    "data_economics", "research_costs", "llm_usage", "mission_usage",
    "cost_unpriced_models",
    # عدّادات التشغيل (ترحيل 007) — سطح أدمِن حصراً؛ صفوف المصنع تُجرَّد منها.
    "run_stats",
})

# سباكة تدقيق داخلية لا تخص المصنع (G-04 — C4 موجة #14): سجل رقع العرض
# (`render_repairs` — قبل/بعد/موضع كل رقعة) قناةُ مشغّلٍ على العرض الجذري؛
# تسريبه في JSON تقرير المصنع يعرض لغة سباكة داخلية للعميل الدافع.
# R5 (تدقيق 2026-09-01، ENG-13): `run_token` سياجُ المحاولة الداخليّ — كان يصل
# حمولةَ المستأجر مع الصفّ كاملاً؛ لا قارئَ له خارج الخادم.
_INTERNAL_AUDIT_KEYS = frozenset({"render_repairs", "run_token"})


# رطانة داخلية لا تُعرَض لعميل مصنع (جولة المالك 2026-08-17: سطر الخلاصة كان
# يقول «أضف بطاقة منتجك (product_card)» — معرّف شيفرة لا يستطيع المصنع فعل شيء
# به). القائمة ضيّقة عمداً: معرّفات داخلية مرصودة فقط، لا مساس بأي رقم أو حكم.
_CLIENT_BRIEF_JARGON = re.compile(r"\s*\((?:product_card|deep_research)\)")


def sanitize_client_brief(view: dict) -> dict:
    """نقِّ نصوص العميل من معرّفات الشيفرة الداخلية — presentation only.

    تُطبَّق بعد `strip_cost_keys` في نقاط تقرير المنصّة الثلاث (عرض/docx/PDF).
    الجملة العربية تبقى كما هي؛ يُحذف المعرّف ASCII بين قوسين فقط.
    §58 M1: التغطية تشمل — إضافةً إلى `brief` — ملاحظةَ الموقع التنافسي
    (`competitive_position.note`): منبعها silk_render يقول «أضف بطاقة منتجك
    (product_card)…» وكل دراسة منصّة بلا بطاقة، فكانت الرطانة تُطبع حرفياً
    في قسم «موقعك التنافسي» من كل Word/PDF ينزّله المصنع.
    """
    def _clean(text):
        return _CLIENT_BRIEF_JARGON.sub("", str(text))

    brief = view.get("brief")
    if isinstance(brief, list):
        view["brief"] = [_clean(line) for line in brief]
    elif isinstance(brief, str):
        view["brief"] = _clean(brief)
    cp = view.get("competitive_position")
    if isinstance(cp, dict) and isinstance(cp.get("note"), str):
        cp["note"] = _clean(cp["note"])
    return view


def strip_cost_keys(obj):
    """جرّد مفاتيح التكلفة تكراريّاً — recursive cost-key removal (new copy).

    قرار المالك: «إخفاء التكلفة من داشبورد العميل» — القفل بنيوي: كل ما يعبر
    من قاعدة المحرّك إلى ردّ مصنعٍ يمرّ من هنا، فمفتاح تكلفة جديد في نتيجة
    المحرّك مستقبلاً يُجرَّد تلقائياً دون تذكُّر أحد.
    """
    if isinstance(obj, dict):
        return {k: strip_cost_keys(v) for k, v in obj.items()
                if k not in _COST_KEYS and k not in _INTERNAL_AUDIT_KEYS}
    if isinstance(obj, list):
        return [strip_cost_keys(x) for x in obj]
    return obj


# ── سجلّ التشغيل داخل-العملية · in-process run registry ─────────────────────
# القيمة = (رمز المحاولة، لحظة بدئها monotonic): «حيّ» ليست حالةً أبدية —
# تشغيلةٌ تجاوزت مهلتها تُعامَل يتيمةً ولو بقي خيطها معلَّقاً (بلا مهلةٍ عليا
# كانت دراسةٌ عالقة «قيد الإعداد» بلا سببٍ ولا نهاية — بلاغ 2026-08-19).
# والرمزُ يمنع خيطَ التشغيلة المكنوسة («الزومبي») من شطب سجلّ خلفه.
_ACTIVE: dict[int, tuple[str, float]] = {}
_LOCK = threading.Lock()
_THREADS: list[threading.Thread] = []

# ETA الافتراضي المعلَن حين لا تاريخ مُقاس — declared, never presented as measured.
# لكل وضعٍ افتراضُه: التحليل السريع دقائق معدودة؛ البحث العميق (١٢ بعثة كلود +
# محلل + كاتب/مراجع) ربع ساعة تقريباً — رقمٌ معلَن «تقديري» حتى تتراكم مددٌ مقيسة.
_DEFAULT_ETA_S = 240
_DEFAULT_DEEP_ETA_S = 900

# R2 (2026-09-02): نصوص النهايات غير الناجحة التي يكتبها مُشرِف التشغيلات
# (`study_runtime`) — تُعرَّف هنا كي لا يستورد الجسرُ المشرفَ (المشرف يستورد
# الجسر؛ اتجاهٌ واحد يمنع الدورة). سطحٌ يقرؤه المصنع: عربيّ، بلا رطانة.
INTERRUPTED_REASON = "انقطع التنفيذ بإعادة نشر — أعد الإطلاق"
TIMEOUT_REASON = "تجاوز التنفيذ المهلة القصوى فأُوقف — أعد الإطلاق"
CANCELLED_REASON = "أُلغيت الدراسة بطلبك — أُرجعت حصّتها"
CANCELLED_QUEUED_REASON = "أُلغيت الدراسة قبل بدء التنفيذ بطلبك — أُرجعت حصّتها"
CANCELLED_TITLE_FMT = "أُلغيت دراسة «{p}» وأُرجعت حصّتها"

# مقبضُ التشغيلة الحالية داخل خيطها (contextvar) — يقرؤه `_run_engine_deep`
# ليمرّر نداءَ تخصيص معرّف المحرّك (`on_allocated`) بلا تغيير توقيع
# `_run_engine` الذي تطعّمه عشراتُ الاختبارات.
_current_run: contextvars.ContextVar = contextvars.ContextVar(
    "silk_platform_current_run", default=None)


def wait_idle(timeout: float = 30.0) -> bool:
    """انتظر خمود كل خيوط الجسر — test seam (سابقة `quota._user_quota_check_delay`).

    يعيد True إن خمدت كلها قبل المهلة. لا يُستدعى من مسار إنتاجي.
    R2: يفوّض إلى `study_runtime.wait_idle` — الخيوط صار يملكها المشرف، وصفٌّ
    منتظرٌ قابلٌ للبدء ليس «خموداً».
    """
    from . import study_runtime
    return study_runtime.wait_idle(timeout)


def fake_engine_enabled() -> bool:
    """مقعد اختبار رُتبة ٢-٣ — `SILK_PLATFORM_FAKE_ENGINE=1` (لا أثر بلا الضبط).

    سابقتا `SILK_PLATFORM_EXPOSE_RESET_TOKEN` و`_user_quota_check_delay`: مقعدٌ
    بيئي صريح لا يُضبَط في إنتاجٍ أبداً؛ العيّنة موسومة وتعبر مسار الحفظ الحقيقي.
    """
    return os.environ.get("SILK_PLATFORM_FAKE_ENGINE", "").strip() in ("1", "deep")


def _study_ai_allowed() -> bool:
    """صمّام إضافات كلود على مسار دراسات المصانع — مطفأ افتراضاً (الدرس ٧٠).

    التشغيلة الآلية بنقرة مصنعٍ يجب ألا تصرف رصيد كلود/السقف اليومي تلقائياً؛
    المسار المجاني يتدهور بفجوة معلنة (`ai_extras_note`) لا يختلق شيئاً.
    (يخصّ الوضع السريع `quick` وحده — الوضع العميق يدير بواباته بنفسه.)
    """
    return os.environ.get("SILK_PLATFORM_STUDY_AI", "").strip() == "1"


def study_mode() -> str:
    """وضع تشغيل دراسات المنصّة — `deep` (الافتراضي) أو `quick`.

    قرار المالك 2026-08-18 («المنصّة لا تعمل»): دراسة المصنع كانت تشغّل
    `silk_engine.analyze` السريع فتكتمل في ثوانٍ بلا بحث حقيقي — «المحرك
    الأساسي يحتاج ١٥ دقيقة عشان يعطيني دراسة». الافتراضي الآن هو مسار
    `/research` العميق نفسه عبر `silk_research_gateway` (نقضٌ مقصود ومؤرَّخ
    لافتراض الدرس ٧٠ على مسار المنصّة وحده: الدراسة المدفوعة بالباقة هي
    المنتج، والحماية بوابةُ جهوزية + حصّة الباقة + السقف اليومي — لا حجب).
    `SILK_PLATFORM_STUDY_MODE=quick` يعيد السلوك السابق (تطوير/طوارئ).
    """
    raw = os.environ.get("SILK_PLATFORM_STUDY_MODE", "").strip().lower()
    return "quick" if raw == "quick" else "deep"


def launch_mode() -> str:
    """الوضع الذي ستُنفَّذ به التشغيلة فعلاً — `fake` | `deep` | `quick`.

    (§58 موجة A): وسمُ `run_stats.mode` كان يقرأ البيئة وقت الإنهاء لا الفرعَ
    المنفَّذ — فتشغيلات المقعد الوهمي (٠٫٥ث) كانت ستُوسَم `deep` وتلوّث وسيط
    ETA «المقاس» برقمٍ لا يقيس شيئاً. `fake` وسمٌ ثالث صريح لا يطابق أي وضعٍ
    حقيقي فلا يدخل وسيطَه أبداً.
    """
    return "fake" if fake_engine_enabled() else study_mode()


def launch_stamp_json() -> str:
    """ختم الوضع يُكتب على الصف **وقت المطالبة** (§58 موجة A) — كنسُ الأيتام
    يقرأ نافذته من وضع الصف نفسه لا من بيئةِ لحظة الكنس، فتبديلُ الصمّام أثناء
    تشغيلةٍ حيّة (أو خدمة ثانية على نفس القاعدة) لا يحكم عليها بنافذة الوضع
    الآخر."""
    return json.dumps({"mode": launch_mode()}, ensure_ascii=False)


class DeepRunRefused(RuntimeError):
    """رفضٌ معلَن من بوابات البحث العميق (جهوزية/رمز HS/ميزانية) — الرسالة
    عربية جاهزة للعرض في `run_error` كما هي، بلا اسم صنف الاستثناء.

    ويحمل — حين توفّرها البوّابة — الحمولةَ **القابلة للتنفيذ**: `candidates`
    (مرشّحو البند الجمركي كما ولّدها المحرّك) و`code` (رمز الخطأ). بلا هذا
    الحمل كان نصّ «اختر البند المطابق أدناه» يصل المصنعَ بلا أيّ «أدناه»:
    طريق مسدود أُعيد إنتاجه محلياً (بلاغ المالك 2026-08-19، منتج «حليب» ⇒
    040110/040120/040140/040150 تتمايز بنسبة الدهن). Actionable, not just prose.
    """

    def __init__(self, message: str, *, candidates: list | None = None,
                 code: str | None = None,
                 advisories: list | None = None) -> None:
        super().__init__(message)
        self.candidates = list(candidates or [])
        self.code = (code or "").strip()
        # مراجعة §58 على R4 (2026-09-05): تنبيهاتُ ما قبل التشغيل كما أعلنتها
        # بوّابةُ الجسم — تُحمَل كي تُسمّى نهايةُ التشغيلة باسمها ويصير الرفضُ
        # قابلاً للإقرار من صفّ الدراسة لا طريقاً مسدوداً.
        self.advisories = list(advisories or [])


def _detail_advisories(detail) -> list:
    """تنبيهاتُ `prerun_advisory` من detail الرفض — نصوصٌ فقط، لا مفاتيح داخلية."""
    if not isinstance(detail, dict):
        return []
    out = []
    for a in (detail.get("advisories") or []):
        if isinstance(a, dict):
            out.append({k: str(a.get(k) or "")[:300]
                        for k in ("kind", "message", "detail")})
    return out


def _refusal_code(exc) -> str:
    """رمزُ إغلاق صفّ التشغيلة لرفضٍ معلَن — `prerun_advisory` يُسمّى باسمه."""
    return ("prerun_advisory"
            if getattr(exc, "code", "") == "prerun_advisory" else "refused")


class EngineInternalError(RuntimeError):
    """عطلٌ داخليّ في جسم المحرّك (5xx / `research_run_failed`) — R1 (ENG-4).

    رسالته **رمزٌ قصير** لا نصّ الاستثناء: `reason` الخام (تتبّع، مفاتيح) كان
    يصل المصنع حرفياً عبر `DeepRunRefused`/`_http_detail_text`. النصّ الكامل
    يبقى في سجلّ الخادم (منقَّحاً)، والمسار العامّ في `_thread_body` يكتب
    سبباً عربياً بالرمز.
    """


def _http_detail_text(detail) -> str:
    """نصّ عربي مفهوم من detail استثناء HTTP — الأولوية للسبب ثم الرسالة."""
    if isinstance(detail, dict):
        for key in ("reason", "message", "error"):
            val = detail.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return str(detail)


# رموزُ رفضِ بوّابات البند الجمركي وحدها — الرفضُ الذي يكون «اختر البند» جواباً
# له فعلاً (`silk_hs_confirm` + بوّابتا `api`). أيُّ رفضٍ آخر (جهوزية، سقف
# ميزانية، سوق) لا يُملأ له حقلُ المرشّحين.
_HS_GATE_CODES = frozenset({
    "hs_confidence_too_low", "hs_confirmation_needed",
    "hs_axis_disambiguation_needed", "hs_ambiguous", "unresolved_hs",
    # رفضُ خطّ التصنيف الواحد (`silk_hs_pipeline`) — نفسُ العائلة: «اختر
    # البند» جوابٌ صالحٌ لها، فتُملأ لها قائمةُ المرشّحين.
    "hs_requires_confirmation", "hs_catalog_conflict",
    "hs_catalog_rejected",
})

# قرار المالك 2026-08-31 (يعيد تأكيد قرار 2026-08-29): شاشةُ المصنع لا تعرض
# قائمةَ مرشّحين ولا تسأل المصنعَ أن يختار بنداً — فجملةُ «اختر …» على سطحها
# طريقٌ مسدود. رفضُ بوّابة البند يصل المصنعَ برسالةٍ إرشادية: حسِّن اسمَ/وصفَ
# المنتج (نوعُه ومادّتُه لا الاسمُ التجاري وحده) أو أدخل الرمز يدوياً.
# التبديل عند حدّ الجسر وحده — حمولةُ `hs_candidates` وعقدُ الاختيار عبر
# الـAPI (`PATCH /platform/studies/{id}`) يبقيان كما هما لعملاء الـAPI،
# وحوارُ لوحة المشغّل (`web/index.html`) خارجُ نطاق القرار.
FACTORY_EDIT_TAIL = ("عدِّل اسمَ المنتج أو وصفَه في «تعديل» فاذكر نوعَ "
                     "المنتج ومادّته (لا الاسمَ التجاري وحده) ثم أعد "
                     "الإطلاق — أو أدخل الرمز الجمركي يدوياً.")
# الجملُ الآمرةُ بالاختيار كما تصدرها البوّابات حرفياً (`silk_hs_confirm`
# و`silk_hs_pipeline`) — كلُّ واحدةٍ تُستبدَل بالإرشاد أعلاه. `PICK_TAIL`
# تُستورَد من مصدرها وقت الاستعمال (استيرادٌ كسول كباقي الوحدة).
_PICK_SENTENCES = (
    "اختر البند المطابق أدناه (يظهر حدُّ كلٍّ بلغةٍ مفهومة) أو أدخل "
    "رمزاً يدوياً قبل بدء التحليل.",
    "اختر من المرشّحين أدناه أو أدخل رمزاً يدوياً قبل بدء التحليل.",
    "اختر البند المطابق من البنود المعروضة، أو أدخل رمزَك الجمركي.",
    "اختر البند المطابق.",
    "اختر البند الصحيح.",
    "أدخل رمزاً صحيحاً أو اختر بنداً.",
)


def _factory_gate_reason(reason: str) -> str:
    """رسالةُ رفضِ بوّابة البند كما يقرؤها المصنع — إرشادٌ لا سؤالُ اختيار.

    الرأسُ التفسيريّ (لماذا رُفض) يبقى كما أصدرته البوّابة؛ جملةُ «اختر»
    وحدها تُستبدَل بإرشاد تحسين الاسم/الوصف. وإن حملت الرسالةُ صياغةً لا
    نعرفها بلا أيّ إرشاد تحرير، يُلحَق الإرشادُ بذيلها — لا رفضَ بلا مخرج
    (LESSONS ٧٩). `NO_CANDIDATES_TAIL` يُرشِد للتحرير أصلاً فلا يُمَسّ.
    """
    from silk_hs_confirm import NO_CANDIDATES_TAIL, PICK_TAIL
    for sentence in (PICK_TAIL,) + _PICK_SENTENCES:
        reason = reason.replace(sentence, FACTORY_EDIT_TAIL)
    if FACTORY_EDIT_TAIL not in reason and NO_CANDIDATES_TAIL not in reason:
        reason = reason.rstrip() + " " + FACTORY_EDIT_TAIL
    return reason


def _catalog_candidates(study_id: int, account_id: int, product: str) -> list:
    """مرشّحو بندٍ من **وصف** منتج الكتالوج حين عجز الاسمُ وحده عن الترشيح.

    بلاغ «الطاحونة» (2026-08-29): اسمُ المنتج في الكتالوج قد يكون اسمَ علامةٍ
    تجارية («الطاحونة») لا يطابق أيّ صفٍّ في مرجع HS، فيرتدّ الإطلاق برفضٍ
    **بلا مرشّحين**: لا زرَّ «اختر البند الجمركي» في شاشة المصنع ولا مخرج إلا
    أن يكتب المالكُ رمزاً جمركياً بيده — طريقٌ مسدود. والوصفُ المكتوب في
    الكتالوج («حلاوة طحينية سادة») يحمل المنتجَ الحقيقي، فيُقرأ هنا
    **للترشيح وحده**: لا يغيّر المنتجَ المُحلَّل ولا أيّ رقمٍ في الدراسة.

    قراءةٌ حتميّة صرفة (CSV محليّ) — صفر شبكة، صفر كلود، صفر تكلفة. أيّ تعذّرٍ
    يعيد `[]`: هذا تحسينُ مخرجٍ لا شرطُ إطلاق.
    """
    desc = ""
    try:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT p.description AS d FROM studies s "
                "JOIN products p ON p.id = s.product_id "
                "WHERE s.id = ? AND s.owner_id = ? AND p.account_id = ?",
                (study_id, account_id, account_id)).fetchone()
            desc = str((row["d"] if row else "") or "").strip()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — تحسينٌ لا شرطُ إطلاق
        log.warning("study %s catalog description read failed: %s",
                    study_id, exc)
        return []
    if not desc:
        return []
    try:
        from silk_hs_confirm import deterministic_candidates
        return _detail_candidates(
            {"candidates": deterministic_candidates(
                f"{product or ''} {desc}".strip())})
    except Exception as exc:  # noqa: BLE001
        log.warning("study %s catalog candidates failed: %s", study_id, exc)
        return []


def _detail_candidates(detail) -> list:
    """مرشّحو البند الجمركي من detail الرفض — [] حين لا تعرضهم البوّابة.

    الشكل كما يولّده `silk_hs_confirm.preflight_block` / `silk_hs_classifier`:
    قائمة قواميس (`hs6`, `band_ar`, `description_ar`, `reason_ar`, …). تُصفَّى
    إلى الحقول المعروضة وحدها — لا مفتاح داخلي يعبر إلى سطح المصنع، ولا
    اختلاق: صفٌّ بلا `hs6` يُسقَط بدل تلفيق رمز.
    """
    if not isinstance(detail, dict):
        return []
    out = []
    for cand in (detail.get("candidates") or []):
        if not isinstance(cand, dict):
            continue
        code = str(cand.get("hs6") or "").strip()
        if not code:
            continue
        row = {"hs6": code}
        for key in ("band_ar", "description_ar", "reason_ar",
                    "official_description"):
            val = cand.get(key)
            if isinstance(val, str) and val.strip():
                row[key] = val.strip()[:300]
        # البند ١٧: المصنعُ يحتاج **لماذا** لا الرمزَ وحده — الدليلُ المقيس
        # وما يناقض البديل. أرقامٌ وقوائمُ نصّيةٌ فقط، بلا أيّ مفتاحٍ داخليّ.
        conf = cand.get("confidence")
        if isinstance(conf, (int, float)) and not isinstance(conf, bool):
            row["confidence"] = round(float(conf), 3)
        for key in ("matched_attributes", "contradictions"):
            vals = cand.get(key)
            if isinstance(vals, list) and vals:
                row[key] = [str(v)[:160] for v in vals[:6]]
        out.append(row)
    # لا اقتطاع: `silk_hs_dialog.build_candidates` يضمن اكتمال مجموعة المحور
    # الرقمي (البند ٧٣) — قصُّها هنا قد يُخفي الحدّ الصحيح بينما أيُّ اختيارٍ
    # معروض يُرفَع تأكيداً. (ملاحظة مراجعة ذاتية §58، 2026-08-19.)
    return out


def _close_brackets(text: str) -> str:
    """أعِد النصَّ متوازنَ الأقواس — قصٌّ داخل قوسٍ مفتوح يترك «(الناقص: أ، ب».

    ملاحظةُ مراجعةٍ ذاتية §58: `_trim_sentence` يقصّ عند الفاصلة العربية —
    وهذه الموجةُ نفسُها وضعت فواصلَ عربية **داخل** قوسٍ («(الناقص: أ، ب، ج)»)،
    فصار المقصُّ ينتجُ ما يقول تعليقُه إنه يمنعه. التراجعُ إلى آخر نقطةِ
    توازنٍ أصدقُ من إغلاقِ قوسٍ على نصٍّ مبتور.
    """
    depth = 0
    last_balanced = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0:
            last_balanced = i + 1
    return text if depth == 0 else text[:last_balanced].rstrip(" ،؛-—")


def _empty_reason(result: dict | None) -> str:
    """سبب «اكتمل بلا محتوى» مقروءاً من النتيجة نفسها — لا اتهام ثابت للشبكة،
    ولا ادّعاء بإرجاع مال.

    الموجة p6 (T10، الفرع ب الحيّ): الصياغة القديمة «أُرجعت الحصة» أوهمت بأن
    المال عاد — المُرجَع **مقعد الإطلاق** في الباقة؛ الدولارات الفعلية (بعثات +
    محلل) مسجَّلة في دفتر الاستخدام ولا تُستردّ. و«آخر خطأ في طبقة التحليل» كان
    يُقرأ من contextvar آخر نداء في الخيط (الكاتب/المراجع غالباً) لا من طبقة
    التحليل. الآن يُقرأ كلّ شيء من النتيجة: الطبقة الفاشلة وسببها وقابلية
    إعادة المحاولة (report.failure_reason/skip_reason/error_type/retryable)
    والتكلفة الفعلية (data_economics.cost_usd_estimate) ومعرّف التحليل
    المحفوظ — وتقول الرسالة إن إعادة الإطلاق تستأنف منه بلا إعادة بعثات.
    """
    res = result or {}
    deep = res.get("deep_research")
    seat = "أُرجع مقعد الإطلاق إلى باقتك"
    cost = (res.get("data_economics") or {}).get("cost_usd_estimate")
    cost_txt = (f"؛ التكلفة الفعلية المسجَّلة {float(cost):.2f}$ لا تُستردّ"
                if isinstance(cost, (int, float)) else "")
    if isinstance(deep, dict):
        rep = deep.get("report") if isinstance(deep.get("report"), dict) else {}
        aid = res.get("analysis_id")
        # بلاغ التحليل ٢٧ (2026-08-29): الفروع كانت ثلاثة وكلُّ ما عداها
        # يسقط على «كاتب التقرير»، فقال النصُّ للمالك «الطبقة الفاشلة: كاتب
        # التقرير» ثم أردف بسببٍ يقول «أوقفنا الدراسة **قبل** مرحلتي التحليل
        # والكتابة» — تشخيصان متناقضان في جملةٍ واحدة. والإيقاف المبكر ليس
        # عطلَ طبقةٍ أصلاً: هو رفضُ كفايةٍ مقصود قبل أيّ نداءٍ مدفوع (عقد عدم
        # الاختلاق). النصُّ يُشتقّ من الحالة التي وقعت فعلاً لا من فرعٍ يتيم.
        early = rep.get("skip_reason") == "early_halt"
        layer = ("طبقة التحليل الشامل" if rep.get("skip_reason") == "analyst_call_failed"
                 else "سقف الإنفاق" if rep.get("skip_reason") == "budget"
                 else "" if early
                 else "كاتب التقرير")
        detail = str(rep.get("failure_reason") or "").strip()
        # تصنيفُ العطل يعيش في **رأس** الرسالة لا في ذيل التفصيل: كان
        # يُلحَق آخرَ السبب فيكون أوّلَ ما يبتلعه القصّ — وهو أوّلُ ما يحتاجه
        # مَن يشخّص (مراجعةٌ ذاتية §58).
        _class = ""
        if rep.get("error_type") and rep["error_type"] not in detail:
            _class += f" ({rep['error_type']})"
        if rep.get("status_code") and str(rep["status_code"]) not in detail:
            _class += f" [HTTP {rep['status_code']}]"
        # عند الإيقاف المبكر لم يجرِ التحليل الشامل إطلاقاً
        # (`silk_research_pipeline`: `analyst_skipped_early`) — ادّعاءُ
        # اكتماله كان يناقض السببَ المطبوع بعده بسطر.
        saved = (("اكتملت البعثات وحُفظت" if early
                  else "اكتملت البعثات والتحليل وحُفظا")
                 + (f" (رقم التحليل {aid})" if aid else ""))
        if rep.get("retryable") is False:
            advice = ("الخلل دائم لا عابر — أبلغ الإدارة بإصلاحه قبل إعادة "
                      "الإطلاق؛ إعادةُ الإطلاق تستأنف من المحفوظ (لا إعادة "
                      "للبعثات) لكنها لن تنجح قبل الإصلاح")
        else:
            advice = ("إعادةُ الإطلاق تستأنف من المحفوظ — لا إعادة للبعثات ولا "
                      "دفع مضاعف")
        head = (f"{saved}؛ لم يُنتَج نصّ التقرير — "
                + (f"الطبقة الفاشلة: {layer}" if layer
                   else "لا لعطلٍ تقني: الجوانب المحسوبة دون الحدّ الأدنى "
                        "للحكم")
                + _class)
        tail = f". {seat}{cost_txt}. {advice}."
        # القصُّ يأكل التفصيلَ لا الذيل (موجة «الشامل بدل الترقيع»): رفعُ
        # السقف كلّما طال السببُ مطاردةٌ لا حلّ — كلُّ إثراءٍ لاحقٍ للسبب كان
        # سيبتلع من جديد ما يحتاجه المصنعُ فعلاً (مقعدُه المُرجَع، وكم دُفع،
        # وأنّ إعادة الإطلاق تستأنف). الذيلُ يُحجَز أوّلاً والباقي للتفصيل،
        # **والقصُّ عند حدّ جملة** بالمقصّ القائم (`silk_reports._trim_sentence`)
        # لا وسطَ كلمة: نصٌّ يقرؤه مصنعٌ لا يُبتَر على «التعريفة الجمر…»
        # بقوسٍ مفتوح (مراجعةٌ ذاتية §58 على هذه الموجة نفسها — نصفاها كانا
        # يتعارضان: أحدهما يُطيل السببَ والآخر يقصّه دون طوله).
        if detail:
            # نقطةٌ مزدوجة («… توقف.. أُرجع») حين ينتهي السببُ بنقطته.
            body = detail.rstrip(".")
            room = _REASON_MAX - len(head) - len(tail) - len(" — السبب: ")
            if len(body) > room:
                try:
                    from silk_reports import _trim_sentence
                    body = _trim_sentence(body, max(40, room)).rstrip(".")
                except Exception:  # noqa: BLE001 — المقصّ تحسينٌ لا شرط
                    body = body[:max(0, room)].rsplit(" ", 1)[0]
            # التوازنُ يُفرَض دوماً لا عند القصّ وحده: سببٌ يصل مبتوراً من
            # طبقةٍ أعلى (قصُّ تخزينٍ سابق) يُنتِج نفسَ القوس المفتوح.
            # قوسٌ غيرُ متوازنٍ من أوّل محرف يُفرغ النصّ — فيبقى وسمُ
            # «— السبب:» معلّقاً على فراغ ويسقط التفصيلُ كلّه (ملاحظة
            # مراجعةٍ ذاتية §58). الوسمُ يسقط مع تفصيله لا يتيماً.
            body = _close_brackets(body)
            if body.strip():
                head += f" — السبب: {body}"
        return head + tail
    return ("اكتمل التشغيل دون أي بيانات من المصادر (شبكة/حد معدل). "
            f"{seat}{cost_txt}؛ اطلب من الإدارة فحص المصادر ثم أعد الإطلاق.")


def resolve_market(market_pref: str | None):
    """حُلّ تفضيل السوق إلى {iso3, m49} — None لغير المضبوط أو المجهول.

    ملاحظة §58: التصفية على قائمة الأسواق-١ وحدها كانت تُسقِط بصمتٍ أي سوقٍ
    خارجها (رمز عالمي كـJPN) فيتلقى المصنع تقرير «كل الأسواق» موسوماً بسوقه
    المختار — كذبة استهداف. الحلّ: قائمة الأسواق-١ أولاً ثم مرجع الدول الكامل
    (`silk_market_resolver` — iso3+m49 لكل دولة)، والمجهول فعلاً يُرفَض عند
    الإدخال (`api._study_research_fields`) عبر `market_known` أدناه.
    """
    pref = (market_pref or "").strip().upper()
    if not pref:
        return None
    try:
        from silk_market_ranker import COUNTRIES
        for c in COUNTRIES:
            if c.get("iso3") == pref:
                return {"iso3": pref, "m49": c.get("m49", "")}
        from silk_market_resolver import _load
        for row in _load():
            if (row.get("iso3") or "").upper() == pref and row.get("m49"):
                return {"iso3": pref, "m49": str(row["m49"])}
    except Exception:  # noqa: BLE001 — بلا محرّك (اختبار منصّة معزولة)
        return None
    return None


def market_reference_available() -> bool:
    """هل مرجعُ الأسواق قابلٌ للتحميل أصلاً؟ — P3 (§58 على BIZ-14): الفشلُ المغلق
    صحيح، لكنّ نسبتَه إلى المستخدم («سوقُك مجهولة») كذبٌ حين يكون العطلُ عندنا."""
    try:
        from silk_market_ranker import COUNTRIES  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def market_known(market_pref: str) -> bool:
    """هل الرمز سوق معروف في مراجعنا؟ — بوّابة إدخال `market_pref`.

    تعذُّر المرجع (منصّة بلا محرّك) = قبول متسامح: التحقق الشكلي (٣ أحرف
    ASCII) قائم في النقطة، والاستهداف الفعلي يتحقّق وقت التشغيل.
    """
    try:
        from silk_market_ranker import COUNTRIES  # noqa: F401 — فحص توفر المحرّك
    except Exception as exc:  # noqa: BLE001
        # P3 (BIZ-14، تدقيق 2026-09-01): كان القبولَ المتسامح — سوقٌ مجهولة تعبر البوّابة
        # وتُنفَق عليها تشغيلةٌ كاملة تنتهي بلا بيانات. الفشلُ مغلقٌ الآن: بلا مرجعٍ لا
        # نُصادِق على سوق (رسالةُ الرفض تقول «تعذّر التحقّق» لا «سوق غير معروفة»).
        log.warning("market gate: reference unavailable (%s) — failing closed", exc)
        return False
    return resolve_market(market_pref) is not None


def _target_countries(market_pref: str | None):
    """قائمة الأسواق المستهدفة — [{iso3, m49}] أو None (ترتيب المحرّك الكامل)."""
    hit = resolve_market(market_pref)
    return [hit] if hit else None


def _fake_result(product: str, hs_code: str | None) -> dict:
    """عيّنة بشكل نتيجة `analyze` — موسومة صراحةً، للمقعد الاختباري فقط.

    تعبر مسار `silk_storage.save_analysis` **الحقيقي** (لا قاعدة موازية) كي
    يختبر التدفق نفس ما يجري إنتاجياً؛ الوسم في `note` يمنع تقديمها كحيّة.
    """
    return {
        "product": product,
        "hs_code": hs_code or "080410",
        "hs_confidence": 1.0,
        "hs_note": "عيّنة اختبار محاكاة الشكل — fake-engine test seam",
        "year": 2024,
        "preliminary": True,
        "classified": True,
        "markets": [{
            "country": "المملكة العربية السعودية → الإمارات",
            "iso3": "ARE", "m49": "784",
            "total_score": 0.62, "confidence": 0.5,
            "components": {},
            "recommendation": "عيّنة اختبار — ليست توصية حقيقية.",
        }],
        "note": "عيّنة اختبار محاكاة الشكل (SILK_PLATFORM_FAKE_ENGINE=1) — "
                "ليست تحليلاً حياً.",
    }


# نصوصُ العيّنة بلغتَي التقرير — الوسمُ أوّلاً في الحالتين فلا تُقدَّم حيّةً.
# **الموجة B.** اسمُ متغيّر البيئة أُخرِج من نصّ الوسم: معرّفٌ داخليّ في نصٍّ
# يواجه العميل هو سباكةٌ مسرَّبة، وبوّابةُ اتساق اللغة ترصده (بحقّ) نثراً
# إنجليزياً في تقريرٍ عربيّ. الوسمُ نفسُه يبقى — عيّنةٌ لا تُقدَّم حيّةً أبداً.
_FAKE_TAG = {
    "ar": "عيّنة اختبار لمحاكاة الشكل — ليست بحثاً حياً.",
    "en": "Shape-simulation test sample — not live research.",
}
_FAKE_BODY = {
    "ar": ("هذا **نصٌّ تجريبي** بشكل تقرير البحث العميق كي تختبر رُتب "
           "المتصفح عرضَ التنسيق (عناوين وقوائم وجداول وغامق) بلا أي نداء "
           "كلود.\n\n- بند عيّنة أول\n- بند عيّنة ثانٍ\n\n"
           "| المستوى | القيمة |\n|---|---|\n| عيّنة أ | 1 |\n"
           "| عيّنة ب | 2 |\n"),
    "en": ("This is **sample prose** shaped like a deep-research report so "
           "the browser lanes can exercise formatting (headings, lists, "
           "tables, bold) without any model call.\n\n- First sample item\n"
           "- Second sample item\n\n| Level | Value |\n|---|---|\n"
           "| Sample A | 1 |\n| Sample B | 2 |\n"),
}


def _fake_missions() -> dict:
    """بعثاتُ عيّنةٍ **بشكل الإنتاج**: مؤشّراتٌ مرصودةٌ بمصادرَ عمومية حقيقية.

    الأرقامُ موسومةٌ عيّنةً في ملاحظاتها ولا تتقاطع مع أيّ رقمٍ في متن العيّنة
    (المتنُ بلا مبالغ)، فلا يُطلِق حارسُ تناقضِ الأدلة والمتن بحقٍّ ولا بغيره.
    """
    def _f(value, source, note, conf=0.8):
        return {"value": value, "source": source, "confidence": conf,
                "note": note, "retrieved_at": "2026-08-20",
                "source_ids": (source,)}

    return {
        "trade_flow": {"failed": False, "summary": "عيّنة", "findings": [
            _f(8400000, "UN Comtrade", "عيّنة: واردات السوق المرصودة 2023"),
            _f(4.4, "UN Comtrade", "عيّنة: نمو سنوي مركّب %")]},
        "demographics_economy": {"failed": False, "summary": "عيّنة",
                                 "findings": [
            _f(52000, "World Bank", "عيّنة: نصيب الفرد من الناتج")]},
        "demand_trends": {"failed": False, "summary": "عيّنة", "findings": [
            _f(63, "Google Trends", "عيّنة: متوسط اهتمام البحث")]},
        # البند 2 (أمر إصلاح المحرّك): محرّكُ القرار لم يعد يُصدر درجةً بأقل
        # من ٣ أعمدة — مقعدٌ ببعثاتٍ تحسب عموداً واحداً ما عاد يمرّن مسارَ
        # الترقية الذي تختبره رُتبتا ٢–٣ (الدرس ٩٦: المقعد يطابق ما يستبدله).
        # ملخّصُ المنافسين **مُهيكل** كما تُنتِجه الأداة الحقيقية (الدرس ١٢١).
        "competitors": {"failed": False, "summary": "عيّنة", "findings": [
            {"value": {"year": 2023, "hhi": 2400, "supplier_count": 9,
                       "top_suppliers": [{"partner": "Saudi Arabia",
                                          "share": 41.0}]},
             "source": "UN Comtrade", "confidence": 0.9, "data_year": 2023,
             "note": "عيّنة: مورّدو السوق 2023، مؤشر تركّز HHI=2400",
             "retrieved_at": "2026-08-20", "source_ids": ("UN Comtrade",)}]},
        "risk_news": {"failed": False, "summary": "عيّنة", "findings": [
            _f(-0.4, "World Bank", "عيّنة: الاستقرار السياسي (WGI) PV.EST"),
            _f(0.2, "World Bank", "عيّنة: جودة التنظيم (WGI) RQ.EST"),
            _f(2.9, "World Bank", "عيّنة: LPI الأداء اللوجستي")]},
    }


def _fake_report_text(lang: str = "ar") -> str:
    """نصُّ عيّنةٍ **بالبنية القانونية** (`## N. <عنوان>`) وبلغة الدراسة.

    كان هذا النصّ يستعمل عناوين `#`/`##` حرّة بلا ترقيم، فيُفكِّكه المُصدِّر
    إلى **صفر أقسام** — فيسقط كلُّ قسمٍ في تقرير العميل إلى سطر «السرد غير
    متاح»، وتمرّ رُتبتا ٢–٣ على تقريرٍ بلا متنٍ أصلاً. مقعدٌ لا يُنتِج شكلَ ما
    يُحاكيه لا يختبر شيئاً — والآن يعكس البنية الحقيقية (أحد عشر قسماً
    مرقّماً) وبلغة الدراسة، فيقيس المصنوعَ النهائي فعلاً في اللغتين.
    """
    from silk_ai_judge import report_sections
    lang = "en" if str(lang or "ar").lower() == "en" else "ar"
    tag, body = _FAKE_TAG[lang], _FAKE_BODY[lang]
    out = [tag, ""]
    for i, title in enumerate(report_sections(lang), 1):
        out.append(f"## {i}. {title}")
        out.append("")
        out.append(body)
        out.append("")
    return "\n".join(out)


def _fake_result_deep(product: str, hs_code: str | None,
                      lang: str = "ar") -> dict:
    """عيّنة بشكل نتيجة `/research` — موسومة صراحةً، لمقعد `deep` الاختباري.

    نفس عقد `_fake_result`: تعبر مسار `silk_storage.save_analysis` الحقيقي،
    والوسم في `note`/نص التقرير يمنع تقديمها كحيّة. الشكل مرآة مصغّرة لِما
    يبنيه `api._run_research_pipeline` (مفاتيح `deep_research` الجوهرية) كي
    تختبر رُتبتا ٢–٣ عرض التقرير العميق وتنزيله بلا أي نداء كلود.

    `lang`: لغةُ تقرير الدراسة. المقعدُ يستبدل الكاتبَ الحقيقيَّ، فلو بقي
    نصُّه عربياً دائماً لَما استطاعت رُتبتا ٢–٣ التحقّق من تقريرٍ إنجليزيّ
    إطلاقاً — يبقى الحكمُ والأرقام واحدةً، واللغةُ وحدها تتبع الدراسة.
    """
    tag = _FAKE_TAG["en" if str(lang or "ar").lower() == "en" else "ar"]
    sample_report = _fake_report_text(lang)
    out = {
        "product": product,
        "hs_code": hs_code or "080410",
        "hs_confidence": 1.0,
        "year": None,
        "preliminary": True,
        "market": {"iso3": "ARE", "m49": "784", "iso2": "AE",
                   "name_en": "United Arab Emirates", "name_ar": "الإمارات"},
        "markets": [],
        "deep_research": {
            # **الموجة B.** المقعدُ كان يُعيد `missions: {}` — تقريرٌ بسردٍ
            # كاملٍ و**صفرِ أدلة**. هذا بالضبط ما صارت بوّابةُ التسليم تمنعه
            # (البند T-01: صفرُ مؤشّراتٍ ليس تغطيةً كاملة)، فكانت الرُتبتان
            # ٢ و٣ ترسبان بحقّ. وامتداداً للدرس ٩٦: مقعدٌ لا يلتزم عقدَ ما
            # يستبدله لا يختبر شيئاً — والبعثاتُ الحقيقية تُنتِج مؤشّراتٍ
            # بمصادرَ عمومية دائماً، فكذلك المقعد.
            "missions": _fake_missions(),
            "analyst": {},
            # رمز الحكم الإنجليزي الخام — منه تشتق طبقة العرض الشارة
            # (`_verdict_tone`)؛ العيّنة موسومة في note فلا تُقدَّم كحكم حي.
            "verdict": {"verdict": "PRELIMINARY GO", "confidence": 0.5,
                        "note": tag},
            "report": {"report": sample_report,
                       "review_cycles": 0, "unresolved_notes": []},
            "report_style": "commercial",
            "importer_leads": [],
            "trace_id": None,
            "budget_status": {"within_budget": True, "note": tag},
        },
        "note": tag,
    }
    # ── الموجة Z (الدرس ٩٦ ثانيةً) — المقعدُ يطابق **الشكل الجديد** ────────
    # صار مسارُ الإنتاج يبني صفَّ السوق ويُشغّل محرّكَ القرار **قبل** الكاتب
    # ثمّ يُقدّم حكمَه في حقل الحكم (`Z-01`). والمقعدُ بقي على الشكل القديم
    # (`markets: []` وحكمُ جوريةٍ خام)، فرُتبةُ الخادم الحقيقيّ كانت تُعيد
    # «توصية أولية بالدخول» **بلا أيّ قرارِ محرّك** — أي أنّ أدلّةَ الرُتبة ٢
    # على هذين البندين كانت **جوفاء**، ومقعدٌ لا يلتزم عقدَ ما يستبدله لا
    # يختبر شيئاً. يُعاد استعمالُ شيفرة الإنتاج نفسِها هنا، لا نسخةٌ منها.
    try:
        import silk_deep_pillars as _dp
        from silk_requirements_agent import regulatory_state as _reg_state
        _dr = out["deep_research"]
        _reg = _reg_state(out["market"]["iso3"], out.get("hs_code"))
        _dec = _dp.decide_for_deep(_dr, regulatory=_reg)
        _dr["verdict"] = _dp.promote_engine_verdict(_dr["verdict"], _dec)
        _row = {"iso3": out["market"]["iso3"],
                "name_ar": out["market"]["name_ar"],
                "name_en": out["market"]["name_en"], "rank": 1, "deep": True,
                "regulatory": _reg, "components": _dp.build_components(_dr)}
        if _dec:
            _row["decision"] = _dec
        out["markets"] = [_row]
    except Exception as exc:  # noqa: BLE001 — مقعدٌ لا يُسقِط تشغيلة
        log.warning("fake deep decision shape failed: %s", exc)
    return out


def product_card_from_row(row: dict | None) -> dict | None:
    """ابنِ بطاقةَ المنتج من صفّ الكتالوج — أو **لا تبنِها** (البند E-04).

    `ProductCard` يشترط `cost_per_unit`؛ وهو رقمُ المصنع نفسه لا رقمٌ منشورٌ
    يمكن البحثُ عنه. فغيابُه **فجوةُ إدخالٍ** لا فجوةُ بحث: تُعاد `None`
    فيبقى محرّكُ التقاطع معطَّلاً **بإعلان**، بدل أن يُشغَّل على تكلفةٍ مُقدَّرة
    تُنتِج هامشاً وهمياً يبني عليه المصنعُ قراراً.

    وما عدا التكلفة اختياريٌّ: الحقلُ الغائب يُترَك `None` فتُعلِن طبقاتُ
    الاقتصاد فجوتَه باسمه (SAM يحتاج الشريحة، SOM يحتاج الطاقة الشهرية).
    """
    if not isinstance(row, dict):
        return None
    cost = row.get("cost_per_unit")
    if cost in (None, ""):
        return None
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return None
    if cost <= 0:
        return None
    certs = [c.strip() for c in str(row.get("certifications") or "").split(",")
             if c.strip()]
    card = {"cost_per_unit": cost}
    for key, col in (("unit", "cost_unit"), ("tier", "tier"),
                     ("monthly_capacity", "monthly_capacity"),
                     ("shipping_per_unit", "shipping_per_unit"),
                     ("fixed_costs", "fixed_costs"),
                     ("cost_currency", "cost_currency")):
        val = row.get(col)
        if val not in (None, ""):
            card[key] = val
    if certs:
        card["certifications"] = certs
    return card


def apply_study_cost(card: dict | None, study: dict | None,
                     product: str = "") -> dict | None:
    """تكلفة إنتاج **الدراسة** تغلب تكلفة الكتالوج — أو تبني بطاقة وحدها.

    هدف الدراسة الاحترافية (البند ٢): حقل التكلفة صار على نموذج طلب
    الدراسة نفسه (بوحدة سوق المنتج — لتر للسوائل، كجم لغيرها)، والقيمة
    الأحدث إدخالاً (الدراسة) تفوز على الكتالوج. قيمة غير رقمية أو ≤0
    تُتجاهَل فيبقى ما كان — لا اختلاق ولا إسقاط بطاقة قائمة. وحدة البطاقة
    تُختم بوحدة السوق حين لا يحملها الكتالوج (مصدر الوحدة الواحد:
    `silk_economics.market_unit`)."""
    raw = (study or {}).get("production_cost")
    try:
        cost = float(raw)
    except (TypeError, ValueError):
        return card
    if cost <= 0:
        return card
    out = dict(card or {})
    out["cost_per_unit"] = cost
    if not out.get("unit"):
        try:
            from silk_economics import market_unit
            out["unit"] = market_unit(product)[1]
        except Exception:  # noqa: BLE001 — الوحدة إثراء لا شرط
            pass
    return out


# R4.7 (تدقيق 2026-09-01، API-11؛ الترحيل ٠١٧): مصادرُ الرمز المسجَّلة على
# المنتج التي تُمرَّر إلى المحرّك كما هي — `manual` (كتبه المصنعُ بيده) و
# `image` (حسمته الرؤيةُ من العبوة). كلُّ ما سواها («unknown»، صفوفٌ قديمة،
# رمزُ دراسةٍ يخالف رمزَ منتجها) يبقى «catalog» فيواجه البوّاباتِ كاملةً.
_SETTLED_HS_SOURCES = ("manual", "image")


def _runner_takes(runner, name: str) -> bool:
    """هل تقبل المغلقةُ المسجَّلة هذا الوسيط؟ — signature probe, never guesses."""
    import inspect
    try:
        params = inspect.signature(runner).parameters
    except (TypeError, ValueError):  # مغلقة غير قابلة للفحص — لا تخمين
        return False
    if name in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def _run_engine(product: str, hs_code: str | None,
                market_pref: str | None,
                hs_confirmed: bool = False,
                lang: str = "ar",
                product_card: dict | None = None,
                resume_analysis_id: int | None = None,
                hs_source: str | None = None,
                advisories_ack: bool = False) -> dict | None:
    """شغّل المحرّك (أو مقعده الاختباري) وأعد النتيجة — None عند استثناء داخلي.

    الوضعان (قرار المالك 2026-08-18):
    - `deep` (الافتراضي): جسم تشغيلة `/research` نفسه عبر
      `silk_research_gateway` — ١٢ بعثة + محلل + كاتب/مراجع، بكل بواباته.
    - `quick`: السلوك السابق — `silk_engine.analyze(..., persist=True)` داخل
      `block_ai_extras()` ما لم يفعّل المالك `SILK_PLATFORM_STUDY_AI=1`.
    """
    # §58 موجة A: البوّابة هي `fake_engine_enabled()` نفسها (القيمتان المعلومتان
    # حصراً) — فحصُ «أي قيمة غير فارغة» كان يجعل `0`/`false` تقدّم عيّنةً مزيفة.
    if fake_engine_enabled():
        seam = os.environ.get("SILK_PLATFORM_FAKE_ENGINE", "").strip()
        import time as _t
        import silk_context as _sctx
        # يمهل رُتبة المتصفح لالتقاط حالة «قيد الإعداد» فعلاً (٠٫٥ ث افتراضاً).
        # R2: `SILK_PLATFORM_FAKE_ENGINE_DELAY_S` يطيلها لتمرين إعادة التشغيل
        # والإلغاء على خادمٍ حقيقي — ينام بشرائح ويتوقّف عند طلب الإلغاء كما
        # يفعل الخطُّ العميق عند نقاط تفتيشه.
        try:
            _delay = max(0.0, float(os.environ.get(
                "SILK_PLATFORM_FAKE_ENGINE_DELAY_S", "").strip() or "0.5"))
        except ValueError:
            _delay = 0.5
        _until = _t.monotonic() + _delay
        while _t.monotonic() < _until:
            _sctx.check_cancelled("fake-engine")
            _t.sleep(min(0.25, max(0.0, _until - _t.monotonic())))
        result = (_fake_result_deep(product, hs_code, lang) if seam == "deep"
                  else _fake_result(product, hs_code))
        from silk_storage import init_db, save_analysis
        init_db(None)
        result["analysis_id"] = save_analysis(result, None)
        return result

    if study_mode() == "deep":
        return _run_engine_deep(product, hs_code, market_pref, hs_confirmed,
                                lang, product_card,
                                resume_analysis_id=resume_analysis_id,
                                hs_source=hs_source,
                                advisories_ack=advisories_ack)

    import contextlib

    from silk_context import block_ai_extras
    import silk_engine

    # مراجعة §58 (موجة الدرس ١٢٠ — «إصلاحٌ على مسارٍ واحد نصفُ إصلاح»):
    # الوضع السريع كان يمرّر رمزَ الكتالوج إلى `silk_engine.analyze` مباشرةً
    # بلا أيّ بوّابة HS إطلاقاً (البوّابات تعيش في معالجات api لا في
    # المكتبة) — نفسُ ثغرة الدراسة #10 على المسار الشقيق. نقطةُ الاختناق
    # الواحدة نفسُها (`preflight_block`)، والرفض يصعد `DeepRunRefused`
    # بمرشّحيه فيصير `run_error` قابلاً للتنفيذ. `hs_confirmed` يبقى المخرج.
    if hs_code and not hs_confirmed:
        from silk_hs_confirm import preflight_block
        # R4.7: مصدرٌ مسجَّل على المنتج (`manual`/`image`) = اختيارُ إنسانٍ
        # حاضر — نفسُ قاعدة `api._hs_user_supplied` على المسار العميق
        # (إصلاحٌ على مسارٍ واحد نصفُ إصلاح).
        _blk = preflight_block(product, hs_code, hs_confirmed,
                               user_supplied=(hs_source in _SETTLED_HS_SOURCES))
        if _blk is not None:
            raise DeepRunRefused(
                str(_blk.get("message") or "رمز HS المخزَّن يحتاج تأكيداً "
                    "قبل بدء الدراسة"),
                candidates=_blk.get("candidates"),
                code=_blk.get("error"))

    guard = contextlib.nullcontext() if _study_ai_allowed() else block_ai_extras()
    with guard:
        # **الموجة B (البند R-06).** كلُّ أعلام الإثراء كانت تبقى على
        # افتراضها `False`، ومنها `with_requirements` — فوضعُ الطوارئ `quick`
        # كان يُسقِط الطبقةَ التنظيمية بأكملها عن دراسة المصنع: لا قائمةَ
        # اشتراطاتِ دخولٍ من المرجع المُقنَّن، ولا بندَ أهلية EU 2017/625،
        # بلا أيّ إعلانٍ للمصنع. العلَمان أدناه **بلا شبكةٍ ولا كلود ولا
        # إنفاق**: `with_requirements` قراءةُ CSV محلّي، و`with_research`
        # يشغّل حزمةَ الوكلاء الحتمية التي تُنتِج `pillar_inputs` ومنها
        # قرارُ `silk_decision` (وإلا فوضعُ quick بلا محرّك قرارٍ أيضاً).
        return silk_engine.analyze(
            product,
            countries=_target_countries(market_pref),
            hs_code=(hs_code or None),
            with_requirements=True,
            with_research=True,
            persist=True,
        )


def _resume_matches(analysis_id: int, product: str, market: str) -> bool:
    """هل تشغيلة `analysis_id` المحفوظة لنفس المنتج والسوق؟ (p6/T10) — يُقرأ
    من لقطة الطلب المخزَّنة وقت الإنشاء؛ أيّ اختلاف ⇒ لا استئناف (تشغيلة
    جديدة) بدل رفض 409 لاحق. تعذّر القراءة ⇒ False (لا تخمين)."""
    try:
        from silk_storage import get_research_run
        row = get_research_run(int(analysis_id))
    except Exception:  # noqa: BLE001 — قاعدة المحرّك غير متاحة = لا استئناف
        return False
    if not row or row.get("kind") != "research":
        return False
    req = row.get("request") or {}
    same_product = (str(req.get("product") or row.get("product") or "").strip()
                    == str(product or "").strip())
    # مراجعة §58 #8: المقارنة **بالرمز القياسي** لا بالتهجئة. لقطةُ الطلب تخزّن
    # `market` باسم العرض (مثلاً "Netherlands") بينما `market_pref` للدراسة قد
    # يكون "NLD" أو "هولندا" — فكانت المطابقةُ النصّية تُعطّل الاستئناف صامتاً
    # فتُدفَع البعثاتُ والمحلل مرّتين، عينُ ما وُضِع T10 لمنعه.
    stored_iso3 = str(req.get("market_iso3") or "").strip().upper()
    want = str(market or "").strip()
    want_iso3 = want.upper()
    if len(want_iso3) != 3 or not want_iso3.isalpha():
        try:
            from silk_market_resolver import resolve_market
            ref, _ = resolve_market(want)
            want_iso3 = str(getattr(ref, "iso3", "") or "").upper()
        except Exception:  # noqa: BLE001 — تعذّر الحسم = لا استئناف، لا تخمين
            want_iso3 = ""
    if not stored_iso3:
        # صفٌّ قديم بلا ختمِ رمز — قارِن بالتهجئة كما كان (لا انحدار).
        same_market = str(req.get("market") or "").strip().upper() == want_iso3 \
            or str(req.get("market") or "").strip() == want
    else:
        same_market = bool(want_iso3) and stored_iso3 == want_iso3
    return bool(same_product and same_market)


def _runner_declares(runner, name: str) -> bool:
    """هل يعلن توقيعُ المغلقة الوسيطَ باسمه **صراحةً** (لا عبر **kwargs)؟

    R2: `on_allocated` يُمرَّر لمن يعلنه فقط — مغلقاتُ الاختبار `def run(**kw)`
    تقيس مفاتيحها حرفياً، و`_runner_takes` يقبل كل شيء لها.
    """
    try:
        return name in inspect.signature(runner).parameters
    except (TypeError, ValueError):
        return False


def _allocation_callback(run):
    """نداءٌ يكتب معرّف تشغيلة المحرّك على صفّ `study_runs` لحظة تخصيصه (R2).

    بلا هذا كان الجسر يعرف المعرّف في نهاية التشغيلة فقط — فموتُ العملية بعد
    الحفظ وقبل الربط يُيتّم تحليلاً مدفوعاً. الكتابة تحسينٌ لا شرطُ تشغيل:
    فشلُها تحذيرٌ في السجلّ لا كسرٌ للتشغيلة.
    """
    def _on_allocated(analysis_id) -> None:
        try:
            run.analysis_id = int(analysis_id)
            conn = connect()
            try:
                conn.execute(
                    "UPDATE study_runs SET analysis_id = ? "
                    "WHERE id = ? AND state = 'running'",
                    (int(analysis_id), int(run.run_id)))
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 — ربطٌ تحسيني لا شرطُ تشغيل
            log.warning("study_run analysis link skipped run_id=%s: %s",
                        getattr(run, "run_id", "-"), exc)
    return _on_allocated


def _run_engine_deep(product: str, hs_code: str | None,
                     market_pref: str | None,
                     hs_confirmed: bool = False,
                     lang: str = "ar",
                     product_card: dict | None = None,
                     resume_analysis_id: int | None = None,
                     hs_source: str | None = None,
                     advisories_ack: bool = False) -> dict | None:
    """تشغيلة البحث العميق لدراسة منصّة — نفس جسم `/research` حرفياً.

    عبر المغلقة المسجَّلة في `silk_research_gateway` (يسجّلها `api.create_app`
    وقت الإقلاع) — مسارٌ واحد لا خط أنابيب موازٍ: كل بوابات الجسم تسري (حسم
    وتأكيد رمز HS، التغطية، الجهوزية، حجز الميزانية الدولارية، النقاط
    المرجعية). رفضُ بوابةٍ يصعد `DeepRunRefused` برسالة عربية معلَنة تصير
    `run_error` كما هي. غياب التسجيل (عمليةٌ بلا محرّك) = رفضٌ معلَن أيضاً —
    **لا تدهور صامت إلى الوضع السريع** (عقد عدم الاختلاق).
    """
    import silk_research_gateway as gateway

    runner = gateway.runner()
    if runner is None:
        raise DeepRunRefused(
            "محرّك البحث العميق غير مسجَّل في هذه العملية — أقلِع الخادم عبر "
            "uvicorn api:app ثم أعد الإطلاق")
    market = (market_pref or "").strip()
    if not market:
        # دراسة عميقة بلا سوق مستهدفة لا معنى لها (المسار العميق سوقٌ واحدة
        # بعمق) — بوابة الإطلاق ترفض قبل الوصول هنا؛ هذا حزام أمانٍ معلَن.
        raise DeepRunRefused(
            "الدراسة العميقة تتطلب سوقاً مستهدفة — عدِّل الدراسة واختر السوق "
            "ثم أعد الإطلاق")
    kwargs = {"product": product, "market": market, "hs_code": hs_code}
    # حادثة الدراسة #10 (حليب/الأردن): رمزُ الكتالوج المخزَّن كان يصل الجسمَ
    # كأنه إدخالُ مستخدمٍ حاضر فيمرّ اختصارُ محور `preflight_block` ويُبنى
    # تحليلٌ كامل (1.80$) على بندٍ قديمٍ لا يطابق المنتج. يُوسَم مصدرُه
    # صراحةً فيواجه البوّاباتِ كاملةً؛ تأكيدُ المصنع (`hs_confirmed`) يبقى
    # المَخرجَ الشرعيّ. نفسُ نمط التمرير المتسامح: مغلقةٌ قديمة بلا الوسيط
    # تبقى صالحة.
    if hs_code and _runner_takes(runner, "hs_source"):
        kwargs["hs_source"] = "catalog"
        # R4.7 (تدقيق 2026-09-01، API-11؛ الترحيل ٠١٧): مصدرٌ **مسجَّل** على
        # منتج الكتالوج (`manual` كتبه المصنع بيده | `image` حسمته الرؤية من
        # العبوة) يمرّ كما سُجِّل — الافتراضُ «catalog» يبقى لكلّ ما سواه
        # (`unknown`، صفوفُ ما قبل الترحيل، رمزُ دراسةٍ يخالف رمزَ منتجها).
        if hs_source in _SETTLED_HS_SOURCES:
            kwargs["hs_source"] = hs_source
    # R4.8: إقرارُ المصنع الصريح بتنبيه ما قبل التشغيل يصل جسمَ `/research`
    # كما لو أرسله عميلٌ حاضر (`ResearchRequest.advisories_ack`) — لا يُمرَّر
    # إلا `True` صريحاً ولمن يقبله (مغلقةٌ قديمة بلا الوسيط تبقى صالحة).
    if advisories_ack and _runner_takes(runner, "advisories_ack"):
        kwargs["advisories_ack"] = True
    # الموجة ٠: لغة تقرير الدراسة (لقطتها) تصل الكاتب — نفس نمط التمرير
    # المتسامح أعلاه: مغلقةٌ قديمة مسجَّلة بلا الوسيط تبقى صالحة.
    if _runner_takes(runner, "lang"):
        kwargs["lang"] = lang
    # الموجة C (E-04): بطاقةُ المنتج — تُمرَّر **فقط** إن بُنيت فعلاً. `None`
    # لا تُمرَّر إطلاقاً: تمريرُها يجعل «بلا بطاقة» و«ببطاقةٍ فارغة» حالةً
    # واحدةً عند المستهلِك، والفرقُ بينهما فجوةُ إدخالٍ معلنة مقابل خطأ.
    if product_card and _runner_takes(runner, "product_card"):
        kwargs["product_card"] = product_card
    if hs_confirmed and _runner_takes(runner, "hs_confirmed"):
        # مغلقةٌ قديمة مسجَّلة بلا الوسيط (اختبارات) تبقى صالحة — الراية
        # تُمرَّر فقط لمن يقبلها، فلا TypeError مُقنَّعة كفشل محرّك.
        kwargs["hs_confirmed"] = True
    # p6/T10: دراسةٌ لها تشغيلة محفوظة (فشل ذيل سابق) لنفس المنتج والسوق تستأنف
    # منها — البعثات والمحلل المحفوظة تُعاد بالقروش لا بالدولارات.
    if (resume_analysis_id and _runner_takes(runner, "resume")
            and _resume_matches(resume_analysis_id, product, market)):
        kwargs["resume"] = int(resume_analysis_id)
        log.info("study relaunch resumes saved research run %s",
                 resume_analysis_id)
    # R2: معرّف تشغيلة المحرّك يُربَط بصفّ التشغيلة لحظة تخصيصه لا عند النهاية —
    # يُمرَّر لمن يعلن الوسيط صراحةً في توقيعه فقط (لا عبر **kwargs).
    _run = _current_run.get()
    if _run is not None and _runner_declares(runner, "on_allocated"):
        kwargs["on_allocated"] = _allocation_callback(_run)
    try:
        return runner(**kwargs)
    except Exception as exc:  # noqa: BLE001 — يُفكَّك أدناه: HTTP معلَن أم عطل
        detail = getattr(exc, "detail", None)
        if detail is not None:  # HTTPException من بوابات الجسم — سبب معلَن
            status = int(getattr(exc, "status_code", 0) or 0)
            code = detail.get("error") if isinstance(detail, dict) else None
            # R1 (تدقيق 2026-09-01، ENG-4): 5xx/`research_run_failed` عطلٌ داخليّ
            # لا رفضُ بوّابة — نصّه الخام للسجلّ (منقَّحاً)، والمصنع يقرأ الرمز
            # وحده عبر المسار العامّ. كان `reason` (تتبّع + مفاتيح) يصل حرفياً.
            if status >= 500 or code == "research_run_failed":
                try:
                    import silk_diagnostics as _dg
                    _raw = _dg._redact(str(detail))[:300]
                except Exception:  # noqa: BLE001 — التنقيح تحسين لا شرط
                    _raw = "<detail withheld: redactor unavailable>"
                log.warning("deep run internal failure (%s): %s",
                            code or status, _raw)
                raise EngineInternalError(
                    str(code or f"engine_http_{status}")) from exc
            raise DeepRunRefused(
                _http_detail_text(detail),
                candidates=_detail_candidates(detail),
                code=(detail.get("error")
                      if isinstance(detail, dict) else None),
                advisories=_detail_advisories(detail)) from exc
        raise


def _dp_value(v):
    """قيمة نقطة بيانات بشكلَيها — DataPoint dataclass أو dict مُسلسَل."""
    if v is None:
        return None
    if isinstance(v, dict):
        return v.get("value")
    return getattr(v, "value", None)


def result_is_substantive(result: dict | None) -> bool:
    """هل حملت النتيجة بياناتٍ حقيقية واحدة على الأقل؟ — حارس «المكتملة الفارغة».

    شكوى المالك المعاد إنتاجها (2026-08-17): مصادر فاشلة كلها ⇒ `classified=True`
    وسوقٌ بدرجة 0.0 وثقة 0.0 وكل المكوّنات None — والجسر كان يسمها «مكتملة».
    الجوهر = سوقٌ واحد فيه ثقة صف > 0 **أو** مكوّنٌ بقيمة غير None. عقد عدم
    الاختلاق نفسه بالمقلوب: كما لا نختلق رقماً، لا نختلق «اكتمالاً» بلا أرقام.
    """
    deep = (result or {}).get("deep_research")
    if isinstance(deep, dict):
        # نتيجة بحث عميق: `markets` فارغة بنيوياً (سوق واحدة بعمق) — الجوهر
        # هو التقرير المكتوب نفسه. تشغيلة بلا نص تقرير = هيكل فارغ، لا تُوسَم
        # «مكتملة» (نفس عقد بوابة الجهوزية 409 في /research بالمقلوب).
        report = deep.get("report")
        text = (report or {}).get("report") if isinstance(report, dict) else None
        return bool(str(text or "").strip())
    markets = (result or {}).get("markets")
    for m in (markets if isinstance(markets, list) else []):
        try:
            if float(m.get("confidence") or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
        comps = m.get("components") or {}
        for v in (comps.values() if isinstance(comps, dict) else []):
            if _dp_value(v) is not None:
                return True
    return False


def _run_stats_json(result: dict | None, duration_s: float, mode: str) -> str:
    """لخّص عدّادات التشغيلة JSON — أداة قياس الأدمِن (ترحيل 007).

    من `data_economics` الذي يرفقه `analyze` (عدّاد `silk_context`)؛ غيابه
    (استثناء قبل الاكتمال) = None معلَنة لا أصفاراً مختلَقة. `mode` هو الفرع
    المنفَّذ فعلاً (يلتقطه الخيط عند بدئه — §58 موجة A: لا قراءة بيئةٍ وقت
    الإنهاء قد تكون تبدّلت، ولا وسم `deep` لعيّنة مقعدٍ في نصف ثانية).
    """
    de = (result or {}).get("data_economics") or {}
    return json.dumps({
        "duration_s": round(float(duration_s), 1),
        # وضع التشغيلة — يقود وسيط ETA لكل وضع (لا خلط مدد ثوانٍ بدقائق).
        "mode": mode,
        "live": de.get("live_fetches"),
        "store": de.get("store_hits"),
        "cache": de.get("cache_hits"),
    }, ensure_ascii=False)


def _notify_finish(conn, study_id: int, account_id: int, *, kind: str,
                   title_fmt: str, body: str) -> None:
    """إشعار إنهاء تشغيلةٍ في **نفس المعاملة** — مساعد مشترك للنجاح والفشل.

    R3: الجسمُ انتقل إلى `notifications.notify_study_finish` (مصدرٌ واحد يقرؤه
    مسارُ الإغلاق اليدوي في `lifecycle` أيضاً)؛ هذا الاسم يبقى مدخلَ الجسر.
    """
    notifications.notify_study_finish(conn, study_id, account_id, kind=kind,
                                      title_fmt=title_fmt, body=body)


def _notify_safely(conn, study_id: int, account_id: int, *, kind: str,
                   title_fmt: str, body: str) -> bool:
    """`_notify_finish` بلا صعود — R1 (تدقيق 2026-09-01، RC-5/ENG-6).

    كان الإشعار داخل معاملة النجاح بلا حماية، فيصعد فشلُ `notifications.record`
    إلى `bridge_crash` ويقلب نجاحاً محفوظاً إلى فشلٍ مُسترَدّ الحصّة. الآن فشلُ
    الإشعار يُسجَّل (سجلّ الخادم + قيد تدقيق `notification_failed`) ولا يمسّ
    الحسم. R3: الجسمُ في `notifications` (مصدرٌ واحد)؛ هذا مدخلُ الجسر.
    """
    return notifications.notify_study_finish_safely(
        conn, study_id, account_id, kind=kind, title_fmt=title_fmt, body=body)


def _notify_after_commit(study_id: int, account_id: int, *, kind: str,
                         title_fmt: str, body: str) -> None:
    """إشعارٌ في معاملةٍ ثانية **بعد** التزام الحسم — لا يرفع أبداً (R1/ENG-6)."""
    try:
        conn = connect()
    except Exception:  # noqa: BLE001
        log.exception("study %s notification connection failed", study_id)
        return
    try:
        _notify_safely(conn, study_id, account_id, kind=kind,
                       title_fmt=title_fmt, body=body)
        conn.commit()
    except Exception:  # noqa: BLE001
        log.exception("study %s notification commit failed", study_id)
    finally:
        conn.close()


def _close_run_row(conn, run_token: str | None, state: str, now: str, *,
                   error_code: str | None = None, error_text: str | None = None,
                   analysis_id: int | None = None) -> int:
    """أغلق صفّ `study_runs` لهذه المحاولة على **سياجه الخاصّ** (الرمز + نشط).

    R2: غيرُ مشروطٍ بنجاح سياج الدراسة — صفٌّ جارٍ عالق (دراسةٌ عادت مسودّةً
    بطريقٍ آخر) كان سيحجب كل إطلاقٍ لاحق بفهرس الفرادة. `run_token=None`
    (نداءات قديمة/اختبارات) = لا صفّ يُغلَق. نفس المعاملة التي يلتزمها المُنادي.
    """
    if not run_token:
        return 0
    try:
        cur = conn.execute(
            "UPDATE study_runs SET state = ?, finished_at = ?, error_code = ?, "
            "error_text = ?, analysis_id = COALESCE(analysis_id, ?) "
            "WHERE run_token = ? AND state IN ('queued','running')",
            (state, now, error_code, (error_text or None),
             (int(analysis_id) if analysis_id else None), run_token))
        if cur.rowcount:
            log.info("study_run_%s run_token=%s", state, run_token[:8])
        return cur.rowcount
    except Exception as exc:  # noqa: BLE001 — قاعدةٌ قبل الترحيل 018: لا كسر
        log.warning("study_run row close skipped (%s): %s", state, exc)
        return 0


def _finish_if_cancelled(run, study_id: int, account_id: int,
                         run_token: str | None,
                         run_stats: str | None = None,
                         analysis_id: int | None = None) -> bool:
    """إن طُلب إلغاءُ هذه التشغيلة فأنهِها **باسم سببه** لا بنصّ الاستثناء (R2).

    `RunCancelled` يصل الجسرَ استثناءً عادياً؛ ما يقرؤه المصنع هو سبب الإلغاء
    (طلبه/المهلة/الإغلاق) بالعربية. المهلةُ والإغلاقُ حسما الصفَّ سلفاً في
    المشرف، فالكتابة هنا مسيَّجة بالرمز وتمرّ بلا أثر — لا سباق.
    """
    if run is None or getattr(run, "cancel", None) is None or not run.cancel.is_set():
        return False
    reason = getattr(run, "cancel_reason", None)
    # §58 A6: على المسار السريع/المحاكى لا معرّفَ مخصَّصاً على المقبض — مؤشّرُ
    # الاستئناف الذي حسبه الفرعُ غيرُ المُلغى (`_resumable`) يبقى هو الاحتياط.
    aid = getattr(run, "analysis_id", None) or analysis_id
    if reason == "timeout":
        _finish_failure(study_id, account_id, TIMEOUT_REASON, run_stats=run_stats,
                        run_token=run_token, analysis_id=aid,
                        run_state="failed", error_code="timeout")
    elif reason == "shutdown":
        _finish_failure(study_id, account_id, INTERRUPTED_REASON,
                        run_stats=run_stats, run_token=run_token, analysis_id=aid,
                        run_state="interrupted", error_code="interrupted")
    else:
        _finish_failure(study_id, account_id, CANCELLED_REASON, run_stats=run_stats,
                        run_token=run_token, analysis_id=aid,
                        run_state="cancelled", error_code="cancelled",
                        notify_kind="study_cancelled",
                        notify_title_fmt=CANCELLED_TITLE_FMT)
    log.info("study_run_cancel_applied study_id=%s reason=%s", study_id,
             reason or "requested")
    return True


def _classification_method(result: dict | None) -> str | None:
    """«كيف حُسِم البند» من عقد التصنيف الواحد في النتيجة — أو None.

    R4.7 (الترحيل ٠١٧): يُقرأ من `result["hs_classification"]
    ["classification_method"]` (ما يحمله `silk_research_pipeline` من
    `silk_hs_pipeline`) حرفياً — لا استنتاجَ من شكل الطلب.
    """
    hc = (result or {}).get("hs_classification")
    if not isinstance(hc, dict):
        return None
    method = str(hc.get("classification_method") or "").strip()
    return method[:64] or None


def _finish_success(study_id: int, account_id: int, analysis_id: int,
                    run_stats: str | None = None,
                    run_token: str | None = None,
                    hs_method: str | None = None) -> None:
    """وسمُ الاكتمال — **مقيَّدٌ برمز المحاولة** (`run_token`).

    بلا القيد: تشغيلةٌ كُنست لتجاوزها المهلة يستيقظ خيطُها بعد إعادة الإطلاق
    فيجد الصفَّ `in_progress` ثانيةً ويكتب عليه معرّفَ تحليله القديم — تقريرٌ
    خاطئ لدراسةٍ جارية (ملاحظة مراجعة ذاتية §58، 2026-08-19).
    """
    conn = connect()
    marked = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        cancelled = conn.execute(
            "SELECT r.cancel_requested_at FROM study_runs r JOIN studies s ON s.id=r.study_id "
            "WHERE r.run_token=? AND r.state='running' AND s.owner_id=? AND s.id=?",
            (run_token, account_id, study_id)).fetchone() if run_token else None
        if cancelled and cancelled["cancel_requested_at"]:
            conn.rollback()
            conn.close()
            _finish_failure(study_id, account_id, "أُلغيت الدراسة بطلبك؛ النتيجة المحفوظة باقية للاستئناف.",
                            run_stats=run_stats, run_token=run_token, analysis_id=analysis_id,
                            run_state="cancelled", error_code="cancelled")
            return
        now = now_iso()
        # R4.7 (الترحيل ٠١٧): «كيف حُسِم البند» يُكتَب من عقد التصنيف الواحد
        # في النتيجة — `COALESCE` يُبقي ما سُجِّل حين لا تحمل النتيجةُ طريقةً.
        cur = conn.execute(
            "UPDATE studies SET analysis_id = ?, run_finished_at = ?, "
            "completed_at = ?, state = 'completed', run_stats = ?, "
            "hs_classification_method = COALESCE(?, hs_classification_method), "
            "updated_at = ? "
            "WHERE id = ? AND owner_id = ? AND state = 'in_progress' "
            "AND (? IS NULL OR run_token = ?)",
            (int(analysis_id), now, now, run_stats, hs_method, now, study_id,
             account_id, run_token, run_token))
        # R2: صفّ التشغيلة يُغلَق على سياجه هو — نفس المعاملة، نفس الالتزام.
        _close_run_row(conn, run_token, "completed", now,
                       analysis_id=int(analysis_id))
        if cur.rowcount:
            audit.record(conn, action="study_run_completed",
                         account_id=account_id, resource_type="study",
                         resource_id=study_id,
                         changes={"analysis_id": int(analysis_id)})
            marked = True
        conn.commit()
    finally:
        conn.close()
    # إشعار الاكتمال (قرار 2026-08-18) — R1 (RC-5/ENG-6): **بعد** الالتزام وفي
    # معاملته الخاصّة: لا إشعار لدراسة لم تُوسَم فعلاً، وفشلُ الإشعار لا يقلب
    # نجاحاً محفوظاً (كان في نفس المعاملة بلا حماية فيصعد إلى bridge_crash
    # ويُرجِع الحصّة على تقريرٍ مدفوع). «مكتملة بلا إشعار» تترك قيدَ تدقيق
    # `notification_failed` لا صمتاً.
    if marked:
        _notify_after_commit(study_id, account_id, kind="study_completed",
                             title_fmt="اكتملت دراسة «{p}»",
                             body="التقرير جاهز للعرض والتنزيل من قسم الدراسات.")


# سقفُ نصّ `run_error`: القصُّ عند ٤٠٠ كان يبتلع ذيلَ الرسالة (المقعدُ
# المُرجَع + التكلفة المسجَّلة + وعدُ الاستئناف) حالما طالت التفاصيل — وهي
# أهمُّ ما يقرؤه المصنع. حارسُ الطول يبقى، لكن **فوق أطول رسالةٍ عاديّة**
# يولّدها `_empty_reason` فعلاً لا تحتها: تسميةُ القياسات الناقصة لكلّ عمودٍ
# غائب (الدرس ٢٠٧) ترفع الحالةَ العاديّة إلى ~٩١٠ حرفاً، فسقفُ ٧٠٠ كان
# يقصّها هي نفسها — والقصُّ يبقى للحالة الشاذّة وحدها.
_REASON_MAX = 1000


def _finish_failure(study_id: int, account_id: int, reason: str,
                    run_stats: str | None = None,
                    hs_candidates: list | None = None,
                    run_token: str | None = None,
                    analysis_id: int | None = None,
                    run_state: str = "failed",
                    error_code: str | None = None,
                    notify_kind: str = "study_failed",
                    notify_title_fmt: str | None = None) -> None:
    """فشلُ تشغيلٍ يعيد الدراسة مسودّةً بسببٍ معلن ويُرجِع الحصّة.

    R2: `run_state`/`error_code` يُغلقان صفّ `study_runs` لهذه المحاولة في
    المعاملة نفسها (failed | interrupted | cancelled)، و`notify_kind`/
    `notify_title_fmt` يسمّيان الإشعارَ باسم النهاية (الإلغاء ليس تعثّراً).

    نفس شكل تعويض رفض الحصّة في مسار الإطلاق (silk_platform/api.py): مسح ختم
    الإطلاق يجعل حصّة المستخدم تُحرَّر تلقائياً (العدّ مشتق من الختم)، و
    `quota.release_launch` يُرجِع عدّاد الحساب — **فقط** إن نجح الإرجاع إلى
    draft (rowcount=1) فلا إرجاع مزدوج تحت أي تزامن.
    """
    conn = connect()
    reverted = False
    try:
        # درس 193: التقط launched_at قبل أن يُصفّره الـUPDATE — release_launch
        # يحتاجه ليتجنّب إرجاع إطلاقٍ سبق إعادةَ تعيينٍ (تحت-إنفاذ الحصّة).
        _lr = conn.execute("SELECT launched_at FROM studies WHERE id = ? "
                           "AND owner_id = ?", (study_id, account_id)).fetchone()
        _launched_at = _lr["launched_at"] if _lr else None
        cur = conn.execute(
            "UPDATE studies SET state = 'draft', launched_at = NULL, "
            "launched_by_user_id = NULL, run_finished_at = ?, run_error = ?, "
            "run_stats = COALESCE(?, run_stats), hs_candidates = ?, "
            # p6/T10: تشغيلةٌ حُفظت نتيجتها (الفرع ب) تُشار إليها كي تستأنف
            # إعادةُ الإطلاق منها بدل تشغيلة كاملة — لا تُمسَح إشارة سابقة.
            "analysis_id = COALESCE(?, analysis_id), "
            "updated_at = ? WHERE id = ? AND owner_id = ? "
            "AND state = 'in_progress' AND (? IS NULL OR run_token = ?)",
            (now_iso(), (reason or "")[:_REASON_MAX], run_stats,
             (json.dumps(hs_candidates, ensure_ascii=False)
              if hs_candidates else None),
             (int(analysis_id) if analysis_id else None),
             now_iso(), study_id, account_id, run_token, run_token))
        # R2: صفّ التشغيلة يُغلَق على سياجه هو — **قبل** `release_launch` الذي
        # يلتزم داخلياً، فيهبط الاثنان في التزامٍ واحد.
        _close_run_row(conn, run_token, run_state, now_iso(),
                       error_code=error_code,
                       error_text=(reason or "")[:_REASON_MAX],
                       analysis_id=(int(analysis_id) if analysis_id else None))
        if cur.rowcount:
            quota.release_launch(conn, account_id, launched_at=_launched_at)
            audit.record(conn, action="study_run_failed",
                         account_id=account_id, resource_type="study",
                         resource_id=study_id,
                         changes={"reason": (reason or "")[:200],
                                  "run_state": run_state,
                                  "error_code": error_code})
            reverted = True
        conn.commit()
    finally:
        conn.close()
    # إشعار التعثّر (قرار 2026-08-18) بالسبب المعلَن نفسه — R1 (ENG-6، نفس
    # عائلة النجاح): بعد الالتزام وفي معاملته الخاصّة، فلا يعلّق فشلُ الإشعار
    # دراسةً «قيد الإعداد» بصفّ تشغيلةٍ مفتوح إلى الأبد.
    if reverted:
        _notify_after_commit(study_id, account_id, kind=notify_kind,
                             title_fmt=(notify_title_fmt
                                        or "تعثّرت دراسة «{p}» وأُرجعت حصّتها"),
                             body=(reason or "")[:_REASON_MAX])


def _thread_body(study_id: int, account_id: int, product: str,
                 hs_code: str | None, market_pref: str | None,
                 hs_confirmed: bool = False,
                 run_token: str | None = None,
                 lang: str = "ar",
                 product_card: dict | None = None,
                 resume_analysis_id: int | None = None,
                 run=None,
                 hs_source: str | None = None,
                 advisories_ack: bool = False) -> None:
    # R2: `run` مقبضُ التشغيلة الدائمة (`study_runtime.RunHandle`) — يحمل حدث
    # الإلغاء وسببه ومعرّف المحرّك المخصَّص. يُنشَر في contextvar كي يقرأه
    # `_run_engine_deep` بلا تغيير توقيع `_run_engine`. غيابه = السلوك القائم.
    _run_ctx = _current_run.set(run)
    try:
        t0 = time.monotonic()
        # الفرع المنفَّذ يُلتقط **عند البدء** (§58 موجة A) — لا قراءة بيئةٍ وقت
        # الإنهاء قد يكون الصمّام تبدّل خلالها.
        mode = launch_mode()
        # البند ٢٢ (الرصد): سطرُ إقلاعٍ بنيويّ لكل تشغيلة — بلا هذا كان
        # «الدراسة عالقة» تشخيصاً يدوياً في كلّ حادثة.
        log.info("study_launch study_id=%s mode=%s hs_code=%s "
                 "hs_confirmed=%s market=%s engine_started=1",
                 study_id, mode, hs_code or "-", bool(hs_confirmed),
                 market_pref or "-")
        try:
            result = _run_engine(product, hs_code, market_pref, hs_confirmed,
                                 lang, product_card,
                                 resume_analysis_id=resume_analysis_id,
                                 hs_source=hs_source,
                                 advisories_ack=advisories_ack)
        except DeepRunRefused as exc:
            # رفضٌ معلَن من بوابات البحث العميق — الرسالة عربية جاهزة كما هي،
            # لا اسم صنف استثناء (رطانة) في سطحٍ يقرؤه مصنع.
            log.warning("study %s deep run refused: %s", study_id, exc)
            # R2: إلغاءٌ تعاونيّ يصل هنا كرفضٍ (RunCancelled ⇒ 500 ⇒ DeepRunRefused)
            # — النهاية تُسمّى بسبب الإلغاء لا بنصّ الرفض.
            if _finish_if_cancelled(run, study_id, account_id, run_token,
                                    _run_stats_json(None, time.monotonic() - t0,
                                                    mode)):
                return
            # بلاغ «الطاحونة»: رفضٌ بلا مرشّحين = شاشةٌ بلا زرِّ اختيار. وصفُ
            # الكتالوج آخرُ مصدرٍ حتميّ يعرف المنتجَ حين يعجز اسمُه عن ذلك.
            # **مشروطٌ برمز الرفض** (مراجعة ذاتية §58): الواجهة تقرأ
            # `hs_candidates` غيرَ الفارغة كإشارةٍ إلى أن الرفض الأخير كان
            # بوّابةَ البند، فتعرض زرَّ الاختيار — ولو مُلئت لرفضِ جهوزيةٍ أو
            # سقفِ ميزانية لأنبتت زرّاً يعيد الإطلاق إلى الرفض نفسه.
            _reason = str(exc)
            _cands = getattr(exc, "candidates", None)
            if getattr(exc, "code", None) in _HS_GATE_CODES:
                if not _cands:
                    _cands = _catalog_candidates(study_id, account_id, product)
                # قرار المالك 2026-08-31: ما يقرؤه المصنعُ إرشادٌ لا سؤالُ
                # اختيار — جملُ «اختر …» تُستبدَل عند هذا الحدّ وحده،
                # والمرشّحون يبقون على الصفّ لعقد الـAPI.
                _reason = _factory_gate_reason(_reason)
            _finish_failure(study_id, account_id, _reason[:380],
                            run_stats=_run_stats_json(
                                None, time.monotonic() - t0, mode),
                            hs_candidates=_cands,
                            run_token=run_token, error_code=_refusal_code(exc))
            return
        except Exception as exc:  # noqa: BLE001 — فشل المحرّك = سبب معلن، لا انهيار
            log.warning("study %s engine run failed: %s", study_id, exc)
            # R2: `RunCancelled` (أو أيّ استثناءٍ بعد طلب الإلغاء) = نهاية باسم سببه.
            if _finish_if_cancelled(run, study_id, account_id, run_token,
                                    _run_stats_json(None, time.monotonic() - t0,
                                                    mode)):
                return
            # صيد الفجوات ٣: `run_error` سطحٌ يقرؤه المصنع (صف الدراسة +
            # حمولة 409) — كان يحمل اسم صنف الاستثناء (رطانة، خلاف قاعدة
            # `DeepRunRefused` أعلاه نفسها) ونصَّه الخام بلا تنقيح أسرار.
            # الصنفُ والنصُّ الكاملان يبقيان في سجل التشغيل (log.warning).
            try:
                import silk_diagnostics as _dg
                _detail = _dg._redact(str(exc))[:220]
            except Exception:  # noqa: BLE001 — التنقيح تحسين لا شرط
                _detail = str(exc)[:220]
            _finish_failure(study_id, account_id,
                            "تعذّر إكمال الدراسة لعطل تقني أثناء التشغيل — "
                            f"أعد المحاولة أو راجع الدعم. (التفصيل: {_detail})",
                            run_stats=_run_stats_json(
                                None, time.monotonic() - t0, mode),
                            run_token=run_token, error_code="engine_failed")
            return
        stats = _run_stats_json(result, time.monotonic() - t0, mode)
        analysis_id = (result or {}).get("analysis_id")
        log.info("study_engine_done study_id=%s analysis_id=%s hs_code=%s "
                 "elapsed_s=%.1f", study_id, analysis_id or "-",
                 (result or {}).get("hs_code") or "-", time.monotonic() - t0)
        # نتيجة بحث عميق: رمز HS مرّ ببوابات حسم/تأكيد جسم /research نفسها
        # (وإلا لرفضت التشغيلةَ قبل أي إنفاق) — لا مفتاح `classified` فيها.
        is_deep = isinstance((result or {}).get("deep_research"), dict)
        classified = is_deep or bool((result or {}).get("classified", False))
        if not analysis_id:
            # `_persist` يبتلع أخطاء الحفظ (silk_engine.py) — نتيجة بلا معرّف
            # لا يمكن ربطها ولا عرض تقريرها: فشلٌ معلن لا «مكتملة» كاذبة.
            _finish_failure(study_id, account_id,
                            "تعذّر حفظ نتيجة التحليل في قاعدة المحرّك — أعد الإطلاق",
                            run_stats=stats, run_token=run_token,
                            error_code="save_failed")
            return
        if not classified:
            # تصنيف HS فشل/التبس ⇒ التقرير فارغ الأسواق. حرقُ حصّة المصنع على
            # تقريرٍ بلا محتوى ظلمٌ؛ نعيدها مسودّةً بسببٍ يوجّهه للحلّ (رمز HS
            # يدوي أو قراءة الصورة). الفجوة معلنة — لا رمز مُخمَّن أبداً.
            note = (result or {}).get("hs_note") or (result or {}).get("note") \
                or "تعذّر تصنيف المنتج إلى رمز HS"
            _finish_failure(
                study_id, account_id,
                f"تعذّر تصنيف المنتج: {str(note)[:220]} — "
                "أدخل رمز HS يدوياً أو استخدم قراءة الصورة ثم أعد الإطلاق",
                run_stats=stats, run_token=run_token, error_code="unclassified")
            return
        if not result_is_substantive(result):
            # حارس «المكتملة الفارغة» (شكوى المالك 2026-08-17): مصنَّفة لكن كل
            # المصادر فشلت ⇒ تقرير بلا أرقام. نُعيدها مسودّةً بسبب موجِّه ونُرجع
            # الحصّة — نتيجة المحرّك المحفوظة تبقى دليلاً في قاعدته (لا حذف)،
            # لكنها لا تُربَط ولا تُقدَّم «مكتملةً». أثر جانبي صحيح: بلا
            # analysis_id لا تدخل التشغيلة الفارغة وسيطَ ETA.
            # p6/T10 (تصحيح): يُشار إلى التحليل المحفوظ **فقط** إن كان فيه
            # عملٌ يُستأنَف — تشغيلةٌ عميقة بعثاتُها/مراحلُها محفوظة (الفرع ب).
            # تشغيلةٌ خرجت بلا أيّ بيانات من المصادر لا تُستأنَف: ربطُها
            # بالدراسة يُعلن معرّفاً بلا محتوى ويُغري إعادةَ إطلاقٍ تستأنف
            # فراغاً (قفل test_platform_engine_honesty القائم).
            _deep = (result or {}).get("deep_research")
            # مراجعة §58 #15: `stages` لا يوجد في نتيجة التشغيلة الحيّة (يُلحَق
            # في قراءة GET وحدها)، فكان نصفُ الشرط ميتاً. تُقرأ نقاطُ المراحل
            # من المخزن مباشرةً كي يُحتسَب عملٌ محفوظٌ حتى بلا قاموس بعثات.
            _saved_stages = {}
            if isinstance(_deep, dict) and analysis_id:
                try:
                    from silk_storage import load_stage_checkpoints
                    _saved_stages = load_stage_checkpoints(int(analysis_id))
                except Exception:  # noqa: BLE001 — قراءةٌ تحسينية
                    _saved_stages = {}
            _resumable = (int(analysis_id)
                          if isinstance(_deep, dict)
                          and (_deep.get("missions") or _saved_stages)
                          else None)
            # R2: نتيجةٌ خاوية بعد طلب إلغاء = أُلغيت (البعثات توقّفت بطلبه) —
            # بمؤشّر الاستئناف نفسه الذي كان الفرعُ غيرُ المُلغى سيحفظه (§58 A6).
            if _finish_if_cancelled(run, study_id, account_id, run_token, stats,
                                    analysis_id=_resumable):
                return
            _finish_failure(study_id, account_id, _empty_reason(result),
                            run_stats=stats, run_token=run_token,
                            analysis_id=_resumable, error_code="empty")
            return
        # نجاحٌ حُفظ دائماً يبقى نجاحاً ولو وصل الإلغاء متأخّراً (عقد الصدق).
        _finish_success(study_id, account_id, int(analysis_id),
                        run_stats=stats, run_token=run_token,
                        hs_method=_classification_method(result))
    except Exception:  # noqa: BLE001 — خيط daemon لا يرفع أبداً
        log.exception("study %s bridge thread crashed", study_id)
        try:
            if not _finish_if_cancelled(run, study_id, account_id, run_token):
                _finish_failure(study_id, account_id,
                                "عطل داخلي في جسر التشغيل — أعد الإطلاق",
                                run_token=run_token, error_code="bridge_crash")
        except Exception:  # noqa: BLE001
            log.exception("study %s failure handling also failed", study_id)
    finally:
        _current_run.reset(_run_ctx)
        with _LOCK:
            # لا تشطب قيدَ محاولةٍ أحدث: الزومبي يصحو بعد كنسٍ وإعادة إطلاق.
            if _ACTIVE.get(study_id, ("", 0.0))[0] == (run_token or ""):
                _ACTIVE.pop(study_id, None)


# R2 (2026-09-02): `run_study_async` (خيطٌ يُطلَق مباشرةً من مسار الإطلاق بلا
# سجلٍّ دائم) حُذف — الإطلاق يُدرج صفّ `study_runs` في معاملة المطالبة، ثم
# `study_runtime.dispatch()` يطالب به ويبدأ خيطه بسقفٍ (أو يتركه منتظراً).
# `_thread_body` بقي كما هو جسمَ الخيط؛ `_ACTIVE` يبقى مرآةً في الذاكرة يقودها
# المشرف (test seams + كنسُ الصفوف القديمة بلا سجلّ).


# ── ETA صادق · honest ETA ────────────────────────────────────────────────────
def _parse_iso(ts: str | None) -> datetime.datetime | None:
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _run_mode(run_stats_raw) -> str:
    """وضع تشغيلةٍ مخزَّن في `run_stats` — صفوف ما قبل الميزة تُعدّ `quick`.

    (كل تشغيلة سبقت وضع `deep` كانت تحليلاً سريعاً فعلاً — ليس افتراضاً
    مختلَقاً بل توصيفاً تاريخياً دقيقاً لتلك الصفوف.)
    """
    try:
        return (json.loads(run_stats_raw or "{}") or {}).get("mode") or "quick"
    except (TypeError, ValueError):
        return "quick"


def eta_seconds(conn) -> tuple[int, str]:
    """المدة المتوقعة للتشغيلة — (ثوانٍ، أساس)، لوضع التشغيل الحالي.

    الأساس `measured_median` = وسيط آخر ٧ تشغيلات مكتملة **مقيسة فعلاً**
    (كلا الختمين موجودان) **من نفس الوضع** — بعد توصيل الوضع العميق (قرار
    2026-08-18) خلطُ مدد ثوانٍ (سريع) بدقائق (عميق) يُنتج وسيطاً لا يصف
    أياً منهما. وإلا `declared_default` وتعرضه الواجهة «تقديري» — لا رقم
    يُقدَّم كمقاسٍ وهو ليس كذلك (عقد عدم الاختلاق).
    """
    mode = launch_mode()
    # R1 (تدقيق 2026-09-01، ENG-5): المكتملة وحدها — التشغيلة الفاشلة تعود مسودّةً
    # **بمعرّف استئناف وختم انتهاء** (`_finish_failure`)، فكانت مددُها (ثوانٍ)
    # تلوّث وسيط المكتملة (دقائق).
    rows = conn.execute(
        "SELECT run_started_at, run_finished_at, run_stats FROM studies "
        "WHERE state = 'completed' AND analysis_id IS NOT NULL "
        "AND run_started_at IS NOT NULL "
        "AND run_finished_at IS NOT NULL ORDER BY id DESC LIMIT 60").fetchall()
    durations = []
    for r in rows:
        if _run_mode(r["run_stats"]) != mode:
            continue
        a, b = _parse_iso(r["run_started_at"]), _parse_iso(r["run_finished_at"])
        if a and b and b > a:
            durations.append((b - a).total_seconds())
        if len(durations) >= 7:
            break
    if durations:
        return max(5, int(statistics.median(durations))), "measured_median"
    return (_DEFAULT_DEEP_ETA_S if mode == "deep" else _DEFAULT_ETA_S), \
        "declared_default"


# ── كنس الأيتام · restart-orphan sweep ───────────────────────────────────────
def _orphan_grace_s(row_mode: str = "quick") -> int:
    """نافذة سماح الكنس (ثوانٍ) — لا حكم على تشغيلة أحدث من هذا العمر.

    ملاحظة §58 (النشر المتداخل): سجل `_ACTIVE` محلّي للعملية؛ أثناء تبديل
    حاويات Railway قد يكنس الجديدُ تشغيلةً حيّةً في القديمة. النافذة تُبقي
    التشغيلات الأحدث من السقف خارج الحكم — والكنس يعاد دورياً من مجدول
    المنصّة فيلتقط اليتيم الحقيقي بعد انقضائها. تشغيلةٌ تتجاوز النافذة أثناء
    تداخلٍ فعلي خطرٌ متبقٍ مصرَّح به (نادر: تحليل أطول من النافذة + تداخل).
    """
    # الافتراض واعٍ بوضع **الصف نفسه** (§58 موجة A): يُقرأ من ختم المطالبة
    # (`launch_stamp_json`) لا من بيئة لحظة الكنس — تبديلُ الصمّام أثناء
    # تشغيلة عميقة حيّة (أو خدمة ثانية على نفس القاعدة) كان سيحكم عليها
    # بنافذة الوضع السريع (٩٠٠ث) وهي في دقيقتها الثانية عشرة.
    default = 3600 if row_mode == "deep" else 900
    try:
        return max(60, int(os.environ.get(
            "SILK_PLATFORM_ORPHAN_GRACE_S", "").strip() or str(default)))
    except ValueError:
        return default


def _as_utc(dt: datetime.datetime | None) -> datetime.datetime | None:
    """ختمٌ بلا منطقة (قاعدة المحرّك تختم بالتوقيت المحلّي = UTC على النشر) يُقرأ UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def _orphan_analysis_verdict(analysis_id: int, started) -> str:
    """حكم الكنس على تشغيلة محرّك مشارٍ إليها — "completed" | "not_completed" | "unknown".

    R1 (تدقيق 2026-09-01، RC-2/ENG-1): كان الحكم «الصفّ مقروء ⇒ مكتمل» فتُوسَم
    الدراسة مكتملةً على صفّ `running` (خيطٌ آخر ما زال يُنفق) أو `failed` أو
    مكتملٍ **أقدم** من محاولتها (بقايا استئناف). الشرط الآن: الحالة `completed`
    (أو تحليلٌ سريع جوهريّ — `result_is_substantive`) **و**ختمُ تحديثه عند/بعد بدء
    هذه المحاولة. تعذُّر القراءة = «unknown»: لا حكم بلا دليل — الكنسة التالية
    تحسم.
    """
    try:
        from silk_storage import get_analysis, get_research_run
        run = get_research_run(int(analysis_id))
        if run is None:
            return "not_completed"
        if run.get("status") == "completed":
            done = True
        elif run.get("kind") != "research":
            done = result_is_substantive(get_analysis(int(analysis_id)))
        else:
            done = False
        if not done:
            return "not_completed"
        updated = _as_utc(_parse_iso(run.get("updated_at")))
        base = _as_utc(started)
        if updated is None or (base is not None and updated < base):
            return "not_completed"
        return "completed"
    except Exception as exc:  # noqa: BLE001 — لا حكم بلا دليل
        log.warning("orphan sweep: engine store unreachable for analysis %s: %s",
                    analysis_id, exc)
        return "unknown"


def sweep_orphans(conn) -> dict:
    """اكنس دراسات `in_progress` اليتيمة عند التركيب — never raises.

    يتيمة = ليست في `_ACTIVE` (خيطها مات بإعادة نشر — `docs/LESSONS` عائلة
    «الخيوط تموت بإعادة النشر، التعافي صريح لا ذاتي»). فرعان:
    - `analysis_id` موجود وقابل للقراءة ⇒ التشغيل أنجز قبل الموت: `completed`
      (بلا اختلاق وقت انتهاء — `run_finished_at` يبقى فارغاً والمدة تُعرض «—»).
    - غير ذلك ⇒ عودة إلى draft بسببٍ معلن + إرجاع الحصّة.
    تعذُّر قراءة قاعدة المحرّك مع `analysis_id` موجود = لا حكم: يُترك الصف
    بسجلّ تحذير (الحسم بلا دليل اختلاق) — الكنسة التالية تحسمه.
    """
    out = {"completed": 0, "reverted": 0, "skipped": 0}
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    try:
        rows = conn.execute(
            "SELECT id, owner_id, analysis_id, run_started_at, run_stats, "
            "launched_at FROM studies WHERE state = 'in_progress'").fetchall()
        # R2: دراسةٌ لها سجلّ تشغيلة نشط يملك حكمَها مُشرِفُ التشغيلات (نبضة +
        # هويّة إقلاع، لا عُمرٌ وحده) — هذا الكنس للصفوف القديمة بلا سجلّ فقط.
        try:
            owned = {int(x[0]) for x in conn.execute(
                "SELECT study_id FROM study_runs "
                "WHERE state IN ('queued','running')")}
        except Exception:  # noqa: BLE001 — قاعدةٌ قبل الترحيل 018: لا سجلّ
            owned = set()
        for r in rows:
            sid = int(r["id"])
            if sid in owned:
                continue
            grace = _orphan_grace_s(_run_mode(r["run_stats"]))
            with _LOCK:
                entry = _ACTIVE.get(sid)
            live_since = entry[1] if entry else None
            overdue = (live_since is not None
                       and (time.monotonic() - live_since) >= grace)
            if live_since is not None and not overdue:
                continue          # يعمل في هذه العملية — ليس يتيماً
            started = _parse_iso(r["run_started_at"])
            if (not overdue and started is not None
                    and (now_dt - started).total_seconds() < grace):
                out["skipped"] += 1   # داخل نافذة السماح — قد تعمل في عملية أخرى
                continue
            aid = r["analysis_id"]
            if aid:
                # R1 (تدقيق 2026-09-01، RC-2/ENG-1): «مقروء» ≠ «مكتمل» — الحكم
                # بحالة صفّ المحرّك وطزاجته بعد بدء هذه المحاولة، لا بوجوده.
                verdict = _orphan_analysis_verdict(int(aid), started)
                if verdict == "unknown":
                    log.warning("orphan sweep: no verdict for study %s "
                                "(analysis %s) — engine store unreadable", sid, aid)
                    out["skipped"] += 1
                    continue
                if verdict == "completed":
                    now = now_iso()
                    conn.execute(
                        "UPDATE studies SET state = 'completed', "
                        "completed_at = ?, updated_at = ? "
                        "WHERE id = ? AND state = 'in_progress'",
                        (now, now, sid))
                    audit.record(conn, action="study_run_orphan_completed",
                                 account_id=int(r["owner_id"]),
                                 resource_type="study", resource_id=sid,
                                 changes={"analysis_id": int(aid)})
                    # R1 (ENG-10): كل انتقالٍ نهائي يُشعِر — الكنس كان صامتاً.
                    _notify_safely(conn, sid, int(r["owner_id"]),
                                   kind="study_completed",
                                   title_fmt="اكتملت دراسة «{p}»",
                                   body="التقرير جاهز للعرض والتنزيل من قسم "
                                        "الدراسات.")
                    out["completed"] += 1
                    continue
            # سببان مختلفان لا يجوز خلطهما: خيطٌ مات بإعادة نشر، أو تشغيلةٌ
            # ما زالت معلّقة وتجاوزت مهلتها. الثانية يبقى خيطها حيّاً وقد
            # ينتهي لاحقاً — و`_finish_success` مشروط بـ`in_progress` فلا
            # يكتب فوق الحسم هنا (لا سباق).
            reason = ("تجاوز التنفيذ المهلة القصوى دون نتيجة — أعد الإطلاق"
                      if overdue else
                      "انقطع التنفيذ بإعادة نشر — أعد الإطلاق")
            cur = conn.execute(
                "UPDATE studies SET state = 'draft', launched_at = NULL, "
                "launched_by_user_id = NULL, run_error = ?, "
                "updated_at = ? WHERE id = ? AND state = 'in_progress'",
                (reason, now_iso(), sid))
            if cur.rowcount:
                quota.release_launch(conn, int(r["owner_id"]),
                                     launched_at=r["launched_at"])   # درس 193
                audit.record(conn, action="study_run_orphaned",
                             account_id=int(r["owner_id"]),
                             resource_type="study", resource_id=sid)
                # R1 (ENG-10): الإرجاع بإشعارٍ بالسبب نفسه — لا مسودّة صامتة.
                _notify_safely(conn, sid, int(r["owner_id"]), kind="study_failed",
                               title_fmt="تعثّرت دراسة «{p}» وأُرجعت حصّتها",
                               body=reason)
                out["reverted"] += 1
        conn.commit()
    except Exception:  # noqa: BLE001 — الكنس تحسين إقلاع، لا يُسقِط التركيب أبداً
        log.exception("orphan sweep failed")
    return out


# ── صورة → منتج → رمز HS · image → product → HS code ────────────────────────
def _vision_allowed() -> tuple[bool, str]:
    """هل نداء الرؤية الواحد مسموح؟ — مرآة `_intake_vision_allowed` الجذرية
    (api.py، closure لا يُستورد): مفتاح كلود موجود، غير مكشوف بلا SILK_API_KEY،
    وتفعيلة واحدة محجوزة ذرّياً من السقف اليومي. الرفض يتدهور بصدقٍ إلى
    «تعذّرت القراءة» — لا اختلاق ولا إنفاق خارج المحاسبة."""
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return False, ("طبقة الرؤية تتطلّب ANTHROPIC_API_KEY على الخادم — "
                       "اكتب اسم المنتج يدوياً.")
    if not os.environ.get("SILK_API_KEY", "").strip():
        return False, ("مفتاح كلود مضبوط بلا SILK_API_KEY — طبقة الرؤية محجوبة "
                       "حتى تُضبط المصادقة (نفس حارس 503 في المحرّك).")
    try:
        import silk_usage
        if not silk_usage.try_reserve_paid_calls(1):
            return False, ("سقف الاستهلاك اليومي (SILK_PAID_DAILY_CAP) مستنفد — "
                           "تعذّرت قراءة الصورة لهذا الطلب.")
    except Exception as exc:  # noqa: BLE001 — تعذُّر الحجز = رفض آمن لا إنفاق أعمى
        return False, f"تعذّر حجز تفعيلة الرؤية ({type(exc).__name__})"
    return True, ""


def classify_image_flow(image_bytes: bytes, media_type: str) -> dict:
    """صورة منتج ⇒ اسم مقروء ⇒ رمز HS واحد أو إدخال يدوي.

    يعيد استخدام السلسلة القائمة حرفياً (لا مسار جديد):
    `silk_product_intake.intake_image` (رؤية واحدة مقيسة، عقد «تعذّرت القراءة»
    الصادق) ثم `silk_hs_from_image.classify_extraction`؛ لا تُعرض قائمة
    مرشحين أو نسبة ثقة للمصنع. كل الردّ يمرّ من
    `strip_cost_keys` قبل بلوغ المصنع.
    """
    try:
        import silk_product_intake as intake
    except Exception:  # noqa: BLE001 — منصّة بلا محرّك: فجوة معلنة
        return {"ok": False, "status": "engine_unavailable",
                "message": "وحدات المحرّك غير متاحة من هذه الخدمة"}
    if not intake.enabled():
        return {"ok": False, "status": "intake_disabled",
                "message": "قراءة صور المنتجات معطّلة على الخادم — "
                           "يفعّلها الأدمِن بضبط SILK_IMAGE_INTAKE=1"}
    if media_type not in intake.ALLOWED_MEDIA_TYPES:
        return {"ok": False, "status": "invalid_image",
                "message": f"نوع الصورة غير مدعوم للقراءة: {media_type} — "
                           "المدعوم jpeg/png/webp"}
    b64 = base64.b64encode(image_bytes or b"").decode()
    # التحقق (حجم/سحر الملف) **قبل** حجز التفعيلة — ملاحظة §58: سقف رفع
    # المنصّة (10م.ب) أكبر من سقف الرؤية (5م.ب)، فكل نقرة على صورة كبيرة كانت
    # تحرق تفعيلة من السقف اليومي بلا أي نداء (الجذر يتحقق أولاً عمداً:
    # «لا حجز على إدخالٍ باطل»).
    raw_check, why = intake._decode_and_check(b64, media_type)
    if raw_check is None:
        return {"ok": False, "status": "invalid_image", "message": why,
                "reason": why, "needs_confirmation": True, "product_name": ""}
    allow, reason = _vision_allowed()

    # قياس الكلفة الفعلية بالدولار (مرآة `/products/intake` الجذرية): عدّاد حول
    # النداء ثم تسجيل الكلفة في دفتر اليوم — يُحتسَب في السقف المشترك، لا إنفاق
    # غير مرئي. القياس قناة جانبية لا تُسقط الرد.
    import silk_context
    if allow:
        silk_context.begin_data_counter()
    out = intake.intake_image(b64, media_type, "product",
                              allow_vision=allow, blocked_reason=reason)
    if allow:
        try:
            import silk_usage
            from silk_pricing import estimate_cost_usd
            _c = silk_context.data_counter() or {}
            _cost = estimate_cost_usd(_c.get("llm_usage"))
            if _cost.get("total_usd"):
                silk_usage.record_usd(_cost["total_usd"])
        except Exception as exc:  # noqa: BLE001
            log.warning("platform vision cost metering failed: %s", exc)

    if out.get("ok") and out.get("product_name"):
        try:
            from silk_hs_from_image import classify_extraction
            allow_claude = bool(
                os.environ.get("ANTHROPIC_API_KEY", "").strip()
                and os.environ.get("SILK_API_KEY", "").strip())
            # نفس حكم الكتالوج: رمز محسوم أو إدخال يدوي؛ لا قائمة أو نسبة ثقة.
            # Shared image decision; vision was metered above, classifier meters itself.
            out = classify_extraction(out, allow_claude=allow_claude)
            out.pop("reason", None)  # تفاصيل التصنيف الداخلية لا تخص المصنع.
        except Exception as exc:  # noqa: BLE001 — لا تخمين عند عطب التصنيف
            log.warning("HS classification after intake failed: %s", exc)
            from silk_hs_from_image import MANUAL_FALLBACK_MSG
            out = {"ok": False, "hs6": None, "message": MANUAL_FALLBACK_MSG}
    return strip_cost_keys(out)
