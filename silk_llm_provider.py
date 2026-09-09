"""محوّل مزوّد كلود الرقيق — thin LLM provider seam (تدقيق المعمارية، دين ٣).

مشكلة قبل هذا الملف: `silk_ai_judge._call`/`_call_tools` كانا يعرفان تفاصيل
Anthropic HTTP مباشرة (المسار، رأس الإصدار، شكل الحمولة) — أي مزوّد بديل
مستقبلاً (OpenAI مثلاً) يعني جراحة في كل موضع نداء. هذا الملف يستخرج تلك
التفاصيل خلف واجهة `LLMProvider` بمنهجين فقط: `complete` (نداء نص مفرد) و
`complete_tools` (حلقة استخدام أدوات متعددة الأدوار) — تماماً كما كان
`_call`/`_call_tools` يفعلان، بلا أي تغيير سلوكي (نفس المسار، نفس الحمول،
نفس معالجة الفشل/الرفض).

لا مزوّد ثانٍ اليوم — Anthropic هو التنفيذ الوحيد؛ الاختيار عبر إعداد
(`SILK_LLM_PROVIDER`, افتراضي "anthropic") بدل استيراد مباشر، فإضافة مزوّد
لاحقاً = صفّ جديد + سطر تسجيل في `_PROVIDERS`، لا تغيير في مواضع النداء.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import time
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)

# آخر تفصيل فشل نداء كلود — بلاغ حي إنتاجي (ثالث تشغيلة، كاتب التقرير):
# None عائد من complete/complete_tools كان يعني "مفتاح غائب أو فشل" بلا
# أي وسيلة لمعرفة نوع الفشل الفعلي (Timeout؟ خطأ شبكة؟ رفض HTTP؟) سوى
# البحث يدوياً في سجلات الخادم. contextvar يُضبط عند كل نداء (نجاحاً كان
# أو فشلاً) فيُقرأ فوراً بعد النداء — آمن مع ThreadPoolExecutor (نفس نمط
# silk_context، عبر copy_context() لا حالة عالمية مشتركة بين الخيوط).
_last_error: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "silk_llm_last_error", default=None)


def last_error() -> dict | None:
    """آخر تفصيل فشل نداء كلود في هذا السياق — {"type","message"} أو None
    (لا نداء بعد، أو آخر نداء نجح). اقرأها فوراً بعد نداء أعاد None لمعرفة
    السبب الفعلي بدل التخمين."""
    return _last_error.get()


# سبب توقّف آخر نداء — بلاغ حي إنتاجي (كاتب التقرير، تمور/هولندا HS080410):
# رد ناجح بـstop_reason="max_tokens" (نص مقتطع أو بلا نص) كان يعيد None
# فيصير report=None (سلسلة PRs #69/#70/#71). المزوّد طبقة HTTP رقيقة لا تعرف
# التتبّع؛ فبدل حلقة تصعيد مخفية داخله، يعرض `stop_reason` لطبقة الكاتب
# (silk_ai_judge) التي تصعّد السقف وتعيد المحاولة — **كل محاولة نداءٌ مُتتبَّع
# مستقل** (report_call event + عدّ llm_calls + قياس رموز)، لا حلقة صامتة
# خارج طبقة التتبّع/العدّ. contextvar يُضبط عند كل نداء ويُقرأ فوراً بعده.
_last_stop_reason: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "silk_llm_last_stop_reason", default=None)


def last_stop_reason() -> str | None:
    """سبب توقّف آخر نداء `complete` في هذا السياق ("max_tokens"/"end_turn"/…)
    أو None (لا نداء نصّي بعد، أو فشل قبل الرد). تقرأه طبقة الكاتب لتقرّر
    تصعيد سقف الإخراج (نص مقتطع) بدل تخمين.
    الموجة p6 (T5): "aborted_timeout" = بثٌّ أُجهِض (خمول/سقف كلّي) وأُعيد
    **النصّ الجزئي** المجمَّع — تكمِله طبقة الكاتب بدل إعادة التوليد."""
    return _last_stop_reason.get()


# ── البثّ · streaming (الموجة p6، T5 — الجذر) ────────────────────────────────
# الفرع ب الحيّ: نداءٌ غير مبثوث ينتظر الجسد كاملاً تحت مهلة قراءة ٣٠٠ث؛
# توليدُ ١٢–١٦ ألف رمز يجلس على الحدّ نفسه فتُقتل مهلةُ القراءة توليداً
# سليماً بطيئاً — رموزه محسوبة ولا يُحفَظ منها شيء. مع البثّ: مهلة القراءة
# تصير **خمولاً بين الأحداث** (SILK_AI_STREAM_IDLE_S) لا جداراً كلّياً، ويبقى
# سقفٌ كلّي (SILK_AI_STREAM_TOTAL_S) شبكةَ أمان؛ والإجهاض يعيد الجزءَ المجمَّع
# لا None. المسار غير المبثوث لا يتغيّر حرفاً (stream=False افتراضياً).
_STREAM_IDLE_DEFAULT_S = 120.0
_STREAM_TOTAL_DEFAULT_S = 900.0
_STREAM_ABORTED = "aborted_timeout"


def _stream_idle_s() -> float:
    """أقصى صمت بين حدثَي SSE قبل الإجهاض (افتراضياً ١٢٠ث)."""
    try:
        return float(os.environ.get("SILK_AI_STREAM_IDLE_S",
                                    "").strip() or _STREAM_IDLE_DEFAULT_S)
    except ValueError:
        return _STREAM_IDLE_DEFAULT_S


def _stream_total_s(timeout: float) -> float:
    """السقف الكلّي لنداءٍ مبثوث — لا ينزل تحت مهلة المستدعي (`timeout` هي
    الحقل المقفول في أحداث التتبّع) وافتراضيه ٩٠٠ث."""
    try:
        total = float(os.environ.get("SILK_AI_STREAM_TOTAL_S",
                                     "").strip() or _STREAM_TOTAL_DEFAULT_S)
    except ValueError:
        total = _STREAM_TOTAL_DEFAULT_S
    return max(float(timeout or 0.0), total)


class StreamTotalTimeout(Exception):
    """تجاوز السقف الكلّي لبثٍّ — يُسمّى نفسه في last_error (لا ReadTimeout)."""


# ── معاملات المعاينة: قرار واعٍ بالنموذج · model-aware sampling params ───────
# الثلاثة (`temperature`/`top_p`/`top_k`) أُزيلت معاً من Claude 4.7 فصاعداً:
# إرسال أيٍّ منها يردّ **400 invalid_request_error**. والأثر ليس «حكماً غير
# حتمي» بل **فشل النداء كلّه** — `complete` تعيد None، فيسقط التوليف والكاتب
# والمراجع: تقرير بلا سرد. **حضور المفتاح وحده كافٍ للرفض**، فالقيمة المحايدة
# (1.0) ليست علاجاً: المفتاح يُحذف من الحمولة، لا يُضبَط.
#
# ما زال يقبلها: `claude-haiku-4-5-*`, `claude-sonnet-4-6` وما قبلها.
#
# تصحيح الصفّ ٤٧ (docs/LESSONS.md): `temperature=0` شُحنت لأن الافتراضي 1.0
# أنتج حكمين مختلفين لنفس المدخلات في يوم واحد (WATCH ثم GO) — لكنها **لم
# تضمن يوماً مخرجاً متطابقاً**، حتى على النماذج التي تقبلها؛ خفّضت التشتّت لا
# أكثر. على نماذج 4.7+ لا وجود لهذه الرافعة أصلاً: الحتمية تأتي من **التوجيه**
# (تثبيت الحقل الحتمي `silk_narrative.authoritative_verdict` مصدراً وحيداً
# للحكم المعروض، وتضييق المطالبة)، لا من معامل معاينة. القانون الحاكم للصفّ ٤٧
# يبقى «الحكم المعروض من الحقل الحتمي حصراً» — وهو قائم ولم يُمَسّ هنا.
#
# `SILK_LLM_NO_SAMPLING_PARAMS` مخرج تشغيلي بلا نشر: بادئات مفصولة بفواصل (أو
# مسافات) تحلّ محل الافتراضية بالكامل — تُضاف بادئة حين يُرقّى نموذج آخر،
# أو تُفرَّغ («») فلا يُستثنى نموذج.
_NO_SAMPLING_PARAMS_PREFIXES: tuple[str, ...] = (
    "claude-opus-4-7", "claude-opus-4-8", "claude-opus-5",
    "claude-sonnet-5", "claude-fable-5", "claude-mythos")

# المفاتيح الثلاثة أُزيلت معاً — تُنزَع معاً (`_scrub_sampling_params`).
_SAMPLING_PARAM_KEYS: tuple[str, ...] = ("temperature", "top_p", "top_k")


def _no_sampling_params_prefixes() -> tuple[str, ...]:
    """بادئات النماذج التي تُهمَل معها معاملات المعاينة — الافتراضية أو ما
    يضبطه `SILK_LLM_NO_SAMPLING_PARAMS`. المتغيّر **مضبوطاً** يحلّ محل
    الافتراضية كاملةً (فارغاً صراحةً = لا نموذج يُستثنى)؛ **غير مضبوط** =
    الافتراضية."""
    raw = os.environ.get("SILK_LLM_NO_SAMPLING_PARAMS")
    if raw is None:
        return _NO_SAMPLING_PARAMS_PREFIXES
    return tuple(p for p in raw.replace(",", " ").split() if p)


def _supports_sampling_params(model: str) -> bool:
    """هل يقبل هذا النموذج معاملات المعاينة (temperature/top_p/top_k)؟

    المطابقة ببادئة وبلا حساسية حالة الأحرف، فتغطي اللواحق المؤرَّخة
    (`claude-opus-4-8-20260115`) وعائلةً كاملة ببادئة واحدة (`claude-mythos`
    تغطي `claude-mythos-5` و`claude-mythos-preview` معاً)."""
    m = (model or "").strip().lower()
    return not any(m.startswith(p.lower().strip())
                   for p in _no_sampling_params_prefixes())


def _scrub_sampling_params(payload: dict, model: str) -> dict:
    """نقطة الاختناق الوحيدة: تُنقّي الحمولة من معاملات المعاينة قبل الإرسال.

    لماذا هنا لا عند كل موضع بناء: `_post` يمرّ به **كل** نداء (نصّي، أدوات،
    رؤية، وأي موضع يُضاف لاحقاً)، فالحماية بنيوية لا اتفاقية — موضعٌ جديد
    ينسى الفحص لا يستطيع إعادة إنتاج الـ400.

    قاعدتان:
    ١) نموذج لا يقبلها ⇒ تُنزَع الثلاثة كلّها (لا تُضبَط على قيمة محايدة —
       حضور المفتاح وحده يكفي للرفض).
    ٢) نموذج يقبلها ⇒ لا يُرسَل `temperature` و`top_p` معاً (توصية Anthropic،
       وإرسالهما معاً 400 مستقلّ على عائلة Claude 4+). `temperature` هو
       المثبَّت عمداً في هذه المدوّنة، فيُنزَع `top_p` عند التزاحم."""
    if not _supports_sampling_params(model):
        for key in _SAMPLING_PARAM_KEYS:
            if payload.pop(key, None) is not None:
                log.warning("dropped %s for model %r — sampling params are "
                            "rejected (HTTP 400) on this model family",
                            key, model)
    elif "temperature" in payload and "top_p" in payload:
        payload.pop("top_p")
        log.warning("dropped top_p for model %r — temperature and top_p must "
                    "not be sent together", model)
    return payload


class LLMProvider(ABC):
    """الواجهة الدنيا — نداء إكمال نصّي، ونداء حلقة استخدام أدوات."""

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int,
                model: str, timeout: float) -> str | None:
        """نص الرد أو None عند غياب مفتاح/فشل/رفض — لا استثناء يتسرّب للمستدعي."""

    @abstractmethod
    def complete_tools(self, system: str, messages: list, tools: list | None,
                       max_tokens: int, model: str, timeout: float) -> dict | None:
        """رد الـMessages API الخام (غير مُحلَّل) أو None — يقود `silk_llm_runtime`
        حلقة tool_use/tool_result فوقه."""

    def complete_vision(self, system: str, text: str, image_b64: str,
                        media_type: str, max_tokens: int, model: str,
                        timeout: float) -> str | None:
        """نداء رؤية واحد (صورة + نصّ) — نص الرد أو None عند غياب مفتاح/فشل/رفض.

        اختياري (تنفيذ افتراضي = None) كي لا يُلزَم كل مزوّد به؛ يُستعمله مسار
        استقبال المنتج المتعدد الوسائط (بطاقة مكوّنات/صورة منتج). لا استثناء
        يتسرّب للمستدعي — فشلٌ = None => «تعذّرت القراءة» لا اختلاق."""
        return None


class AnthropicProvider(LLMProvider):
    """التنفيذ الوحيد اليوم — يغلّف api.anthropic.com/v1/messages حرفياً
    كما كان `silk_ai_judge._call`/`_call_tools` يفعلان قبل هذا الاستخراج."""

    _ENDPOINT = "https://api.anthropic.com/v1/messages"
    _VERSION = "2023-06-01"

    def __init__(self, api_key_env: str = "ANTHROPIC_API_KEY") -> None:
        self._api_key_env = api_key_env

    def _key(self) -> str:
        return os.environ.get(self._api_key_env, "").strip()

    def _headers(self, key: str) -> dict:
        return {"x-api-key": key, "anthropic-version": self._VERSION,
                "content-type": "application/json"}

    @staticmethod
    def _record_usage(model: str, data: dict) -> None:
        """سجّل رموز الرد في عدّاد اقتصاد البيانات — قناة جانبية صامتة (دين ٤)،
        لا تغيّر عقد complete/complete_tools؛ no-op خارج تحليل نشط أو بلا usage.

        `cache_read_input_tokens`/`cache_creation_input_tokens` (Prompt
        Caching، المرحلة ٠): حقلا usage إضافيان من Anthropic حين يُخزَّن
        `system`/`tools` — غيابهما (نداء بلا كاش) يمرّر صفراً بلا أثر."""
        usage = data.get("usage") if isinstance(data, dict) else None
        if not usage:
            return
        import silk_context  # lazy: keep this module cycle-safe and offline
        silk_context.record_llm_usage(
            model, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0))

    @staticmethod
    def _timeout_pair(timeout: float) -> tuple[float, float]:
        """(مهلة اتصال، مهلة قراءة) — بلاغ حي (ثالث تشغيلة، كاتب التقرير):
        قيمة مفردة تُطبَّق كمهلتَي اتصال وقراءة معاً في requests؛ اتصال
        TCP بـapi.anthropic.com لا يجب أن يستغرق قرب المهلة الكاملة أبداً
        — فصلهما يُفشل مشاكل الاتصال (DNS/شبكة) خلال ثوانٍ بدل انتظار
        المهلة الكاملة، ولا يغيّر سلوك التوليد الطويل المشروع (مهلة
        القراءة تبقى كاملة). تمييز الاستثناء الناتج (ConnectTimeout مقابل
        ReadTimeout) يوضّح تلقائياً أيّ طَوري الفشل وقع — بلا تخمين."""
        return (min(10.0, timeout), timeout)

    # الحالات العابرة التي تُعاد محاولتها فقط — 429 (تجاوز حصّة/معدّل) و529
    # (ازدحام Anthropic). كلاهما يُرفض **قبل** التوليد فكلفة الرموز صفر، وإعادة
    # المحاولة بـbackoff هي النمط الموصى به. غير هذين (400 حمولة/401 مفتاح/رفض)
    # لا يُعاد — فشل فوري كما كان.
    _RETRYABLE_STATUS = (429, 529)

    # أخطاء الاتصال السريعة العابرة — بلاغ مالك حيّ بدليل مباشر (تقرير الكويت،
    # تشغيلتان): نداء الكاتب (أثقل حمولة، في الذيل) فشل بـ«تعذّر الاتصال بالمصدر»
    # بينما المحلّل نجح على نفس الخادم قبله بثوانٍ — فشلٌ متقطّع في طور الاتصال،
    # لا حصّة (لم يلتقطه retry الـ429/529) ولا مهلة قراءة بطيئة (المدّة 200ث <
    # 300ث). ConnectTimeout يفشل ≤10ث (راجع _timeout_pair) فكلفة الرموز صفر،
    # وإعادة محاولته آمنة. **ReadTimeout مستثنى عمداً**: يعني أن النموذج ولّد
    # فعلاً حتى مهلة القراءة الكاملة — إعادته تحرق رموزاً/وقتاً بلا طائل، وذاك
    # مسار إصلاح مختلف (تقليص الحمولة/streaming) يقرّره دليل writer-diagnostics.
    @classmethod
    def _is_retryable_exc(cls, exc: Exception) -> bool:
        """هل الاستثناء خطأ اتصال سريع عابر يُعاد؟ ConnectTimeout/ConnectionError
        نعم؛ ReadTimeout (مهلة قراءة بطيئة) وغيرها لا."""
        try:
            import requests
        except Exception:  # noqa: BLE001
            return False
        exc_type = type(exc)
        # ReadTimeout يرث Timeout؛ نستثنيه صراحةً قبل فحص العائلة العابرة.
        if isinstance(exc, requests.exceptions.ReadTimeout):
            return False
        return isinstance(exc, (requests.exceptions.ConnectTimeout,
                                requests.exceptions.ConnectionError))

    @classmethod
    def _is_connect_phase(cls, exc: Exception) -> bool:
        """هل العطلُ في طور **الاتصال** (لم يُرسَل شيء)؟ ConnectTimeout أو تعذّرُ إنشاء
        الاتصال — تُعاد حتى السقف؛ أمّا انقطاعٌ بعد الإرسال فقد يكون النموذجُ ولّد فعلاً
        (EXT-7) فيُعاد مرّةً واحدة فقط."""
        try:
            import requests
        except Exception:  # noqa: BLE001
            return False
        if isinstance(exc, requests.exceptions.ConnectTimeout):
            return True
        blob = repr(exc)
        return ("NewConnectionError" in blob or "Failed to establish" in blob
                or "Name or service not known" in blob or "getaddrinfo" in blob)

    @staticmethod
    def _note_retry(kind: str) -> None:
        """عدّ كلَّ إعادةٍ وأعلِنها للمشغّل (EXT-7) — قناةٌ جانبية لا ترفع أبداً."""
        try:
            import silk_context
            silk_context.count_data("llm_retried_attempts")
        except Exception:  # noqa: BLE001
            pass
        try:
            import silk_ops_log
            silk_ops_log.record_service_failure(
                "anthropic", f"نداءُ كلود أُعيد بعد {kind}", context={"kind": kind})
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _retry_after(resp, cap: float = 60.0) -> float | None:
        """ثوانٍ من ترويسة Retry-After إن وُجدت (Anthropic يرسلها على 429) —
        مقيّدة بـcap كي لا ننام دهراً. None حين غيابها/تعذّر تحليلها."""
        val = None
        try:
            val = (resp.headers or {}).get("retry-after")
        except Exception:  # noqa: BLE001 — ترويسة اختيارية
            return None
        if not val:
            return None
        try:
            return max(0.0, min(cap, float(val)))
        except (TypeError, ValueError):
            return None

    def _post(self, key: str, payload: dict, timeout: float,
              stream: bool = False):
        """POST واحد مع إعادة محاولة + backoff أسّي على الحالات العابرة فقط.

        يُرجع `resp` (بعد raise_for_status) أو يرمي آخر استثناء — فيلتقطه
        المستدعي و`_error_detail` كما اليوم (فبعد استنفاد المحاولات، السلوك
        مطابق للسابق تماماً: None + خطأ مُسجَّل). SILK_LLM_MAX_RETRIES=0 يعطّل
        الإعادة (سلوك اليوم بالضبط). العدّاد المالي يُحجَز مرّة قبل التشغيلة لا
        لكل محاولة HTTP، و429/529 صفر رموز — فالكلفة ~صفر."""
        import time
        import requests  # lazy: keep core import offline-safe
        try:
            max_retries = max(0, int(os.environ.get(
                "SILK_LLM_MAX_RETRIES", "2").strip() or "2"))
        except ValueError:
            max_retries = 2
        try:
            base = max(0.0, float(os.environ.get(
                "SILK_LLM_RETRY_BASE_S", "1.0").strip() or "1.0"))
        except ValueError:
            base = 1.0
        # نقطة الاختناق: كل نداء يمرّ من هنا، فالتنقية بنيوية لا اتفاقية.
        payload = _scrub_sampling_params(payload, payload.get("model", ""))
        # p6/T5: المسار المبثوث — "stream": true في الحمولة، requests يقرأ
        # الجسد تدريجياً، ومهلة القراءة = خمول بين الأحداث لا جدار كلّي.
        # المسار الافتراضي (stream=False) يمرّ بالأسطر نفسها حرفياً.
        extra_kw = {}
        if stream:
            payload["stream"] = True
            extra_kw = {"stream": True}
            timeout_pair = (min(10.0, timeout), _stream_idle_s())
        else:
            timeout_pair = self._timeout_pair(timeout)
        attempt = 0
        while True:
            import silk_context
            silk_context.check_cancelled("provider_attempt")
            if not silk_context.reserve_data("llm_attempts", int(os.environ.get("SILK_RESEARCH_MAX_LLM_CALLS", "40"))):
                raise RuntimeError("run_llm_attempt_budget_exhausted")
            try:
                resp = requests.post(
                    self._ENDPOINT, timeout=timeout_pair,
                    headers=self._headers(key), json=payload, **extra_kw)
            except Exception as exc:  # noqa: BLE001
                # خطأ اتصال سريع عابر (ConnectTimeout/ConnectionError) → أعِد
                # المحاولة؛ غيره (ReadTimeout/…) يُرمى فوراً للمستدعي كالسابق.
                # EXT-7: طورُ الاتصال يُعاد حتى السقف؛ غيرُه من ConnectionError مرّةً واحدة.
                _cap = max_retries if self._is_connect_phase(exc) else min(1, max_retries)
                if self._is_retryable_exc(exc) and attempt < _cap:
                    self._note_retry(type(exc).__name__)
                    wait = base * (2 ** attempt)
                    log.warning("AI call transient %s (attempt %d/%d) — retry "
                                "in %.1fs", type(exc).__name__, attempt + 1,
                                max_retries + 1, wait)
                    if wait > 0:
                        time.sleep(wait)
                    attempt += 1
                    continue
                raise
            # getattr دفاعي: كائن ردٍّ بلا status_code (نادر) يُعامَل كغير عابر
            # فيمرّ لـraise_for_status كالسابق — لا انهيار على شكل ردٍّ غريب.
            if (getattr(resp, "status_code", None) in self._RETRYABLE_STATUS
                    and attempt < max_retries):
                if stream:
                    # مراجعة §58 #10: ردٌّ مبثوث لم يُقرأ جسدُه يحجز اتصالاً من
                    # التجمّع؛ تركُه عند كل إعادة يستنزف التجمّع تحت البعثات
                    # المتوازية فتظهر أخطاءُ اتصالٍ زائفة.
                    try:
                        resp.close()
                    except Exception:  # noqa: BLE001
                        pass
                self._note_retry(f"HTTP {resp.status_code}")
                wait = self._retry_after(resp)
                if wait is None:
                    wait = base * (2 ** attempt)
                log.warning("AI call transient %s (attempt %d/%d) — retry in "
                            "%.1fs", resp.status_code, attempt + 1,
                            max_retries + 1, wait)
                if wait > 0:
                    time.sleep(wait)
                attempt += 1
                continue
            resp.raise_for_status()
            return resp

    def complete(self, system, user, max_tokens, model, timeout,
                 stream: bool = False,
                 cache_prefix_chars: "int | None" = None,
                 effort: "str | None" = None, thinking_disabled: bool = False):
        _last_error.set(None)       # نظافة الحالة من أول سطر — لا تسريب بين نداءات
        _last_stop_reason.set(None)
        key = self._key()
        if not key:
            return None
        try:
            # WP-1 §1: `temperature=0` على نداءات `complete` (التوليف/الكاتب/
            # المراجع/المحلل النصي) حيث يقبلها النموذج — تخفّض التشتّت، ولا
            # تضمن تطابقاً (انظر التصحيح في رأس الملف). على 4.7+ لا تُرسَل
            # إطلاقاً: حضور المفتاح يردّ 400 فيسقط النداء كلّه، والحتمية هناك
            # من الحقل الحتمي والتوجيه لا من معامل معاينة. لا `top_p` هنا
            # بحال. حلقة الأدوات (`complete_tools`) تبقى على افتراض المزوّد:
            # مخرجاتها لا تحدّد الحكم المعروض (الحكم من المحرّك الحتمي).
            # الموجة ٨ (كاش بادئة الكاتب): حدٌّ صالح داخل النص يقسم رسالة
            # المستخدم كتلتين وتُعلَّم الأولى `cache_control` — نداء المسوّدة
            # يكتب الكاش ونداءا التصعيد/التنقيح (بادئة مطابقة بايتاً) يقرآنه
            # بعُشر السعر (نفس عائلة كاش system/tools — PR #68). بلا حدّ (أو
            # حدّ غير صالح): الحمولة القديمة حرفياً.
            _n = cache_prefix_chars
            if _n and isinstance(user, str) and 0 < _n <= len(user):
                # حدّ يساوي الطول كله (نداء المسوّدة بلا ذيل ملاحظات) يعلّم
                # الرسالة كتلةً واحدة مكاشة — هي التي يقرؤها التنقيح لاحقاً.
                _content = [{"type": "text", "text": user[:_n],
                             "cache_control": {"type": "ephemeral"}}]
                if _n < len(user):
                    _content.append({"type": "text", "text": user[_n:]})
            else:
                _content = user
            payload = {"model": model, "max_tokens": max_tokens,
                       "system": [{"type": "text", "text": system,
                                   "cache_control": {"type": "ephemeral"}}],
                       "messages": [{"role": "user", "content": _content}]}
            # Sonnet 5 defaults to adaptive thinking at high effort. A report
            # retry may otherwise spend its entire output allowance before text.
            # Scope this override to the documented model family and caller.
            if str(model).lower().startswith("claude-sonnet-5"):
                if effort in {"low", "medium", "high"}:
                    payload["output_config"] = {"effort": effort}
                if thinking_disabled:
                    payload["thinking"] = {"type": "disabled"}
            if _supports_sampling_params(model):
                payload["temperature"] = 0
            abort_err = None
            if stream:
                resp = self._post(key, payload, timeout, stream=True)
                data, abort_err = self._consume_stream(
                    resp, _stream_total_s(timeout))
            else:
                resp = self._post(key, payload, timeout)
                data = resp.json()
            self._record_usage(model, data)
            stop_reason = data.get("stop_reason")
            _last_stop_reason.set(stop_reason)   # تقرؤه طبقة الكاتب للتصعيد
            if abort_err:
                # بثٌّ أُجهِض: الجزء المجمَّع يُعاد (إن وُجد) مع تفصيل الإجهاض —
                # لا None صامت، ولا إعادة توليد من الصفر.
                _last_error.set(abort_err)
                partial = "".join(b.get("text", "") for b in data.get("content", [])
                                  if b.get("type") == "text").strip()
                log.warning("AI call stream aborted (%s: %s) — partial text %d chars",
                            abort_err.get("type"), abort_err.get("message"),
                            len(partial))
                return partial or None
            if stop_reason == "refusal":  # safety decline -> no fabrication
                log.warning("AI judge: request refused by the model")
                _last_error.set({"type": "refusal",
                                 "message": "model refused the request"})
                return None
            text = "".join(b.get("text", "") for b in data.get("content", [])
                          if b.get("type") == "text").strip()
            if not text:
                # رد HTTP ناجح بلا كتل نصية (stop_reason=max_tokens نموذجياً) —
                # يُعلَن فجوة صريحة، لا اختلاق. `last_stop_reason` مضبوط أعلاه
                # فتعرف طبقة الكاتب أن السبب اقتطاعٌ وتصعّد (بلاغ هولندا).
                detail = {"type": "empty_response",
                          "message": f"HTTP 200 بلا كتل نصية — "
                                     f"stop_reason={stop_reason!r}"}
                log.warning("AI judge call returned no text: %s", detail["message"])
                _last_error.set(detail)
                return None
            _last_error.set(None)
            # نص مقتطع (stop_reason=max_tokens) يُعاد كما هو؛ طبقة الكاتب تقرّر
            # التصعيد عبر last_stop_reason() — نص جزئي مفيد لا None.
            return text
        except Exception as e:  # noqa: BLE001 — optional layer must never crash analysis
            # سجّل رمزَ الحالة وجسمَ الردّ الفعليَّين لا نوعَ الاستثناء وحده
            # (طلب المالك): «تعذّر الاتصال» وحدها لا تُميّز 429 من 401 من 529،
            # وهي أفعالٌ تشغيليةٌ مختلفة. `_error_detail` يلتقطهما أصلاً —
            # كان السجلّ يرميهما فيبقى التشخيص مستحيلاً من السجلّات.
            detail = self._error_detail(e)
            log.warning("AI judge call failed: %s: %s (status=%s body=%s)",
                        detail.get("type"), detail.get("message"),
                        detail.get("status_code"), detail.get("response_body"))
            _last_error.set(detail)
            return None

    def complete_tools(self, system, messages, tools, max_tokens, model, timeout,
                       stream: bool = False):
        _last_error.set(None)  # نظافة الحالة من أول سطر — لا تسريب بين نداءات
        key = self._key()
        if not key:
            return None
        try:
            payload = {"model": model, "max_tokens": max_tokens,
                      "system": [{"type": "text", "text": system,
                                 "cache_control": {"type": "ephemeral"}}],
                      "messages": messages}
            if tools:
                # علّم آخر أداة فقط — Anthropic يخزّن كل ما قبل نقطة التعليم
                # (system + tools معاً) ككتلة كاش واحدة مستقرة عبر جولات
                # الحلقة، إذ لا يتغيّر تعريف الأدوات بين الجولات.
                payload["tools"] = [*tools[:-1],
                                    {**tools[-1],
                                     "cache_control": {"type": "ephemeral"}}]
            if stream:
                resp = self._post(key, payload, timeout, stream=True)
                data, abort_err = self._consume_stream(
                    resp, _stream_total_s(timeout))
                self._record_usage(model, data)
                if abort_err:
                    _last_error.set(abort_err)
                    log.warning("AI tool call stream aborted (%s: %s) — "
                                "%d partial block(s)", abort_err.get("type"),
                                abort_err.get("message"),
                                len(data.get("content") or []))
                    # جزءٌ مجمَّع يُعاد بوسم stop_reason=aborted_timeout (تقرؤه
                    # حلقة التشغيل فتحلّل ما وصل)؛ لا شيء مجمَّع ⇒ None كما كان.
                    return data if data.get("content") else None
                _last_error.set(None)
                return data
            resp = self._post(key, payload, timeout)
            data = resp.json()
            self._record_usage(model, data)
            _last_error.set(None)
            return data
        except Exception as e:  # noqa: BLE001 — optional layer must never crash analysis
            log.warning("AI tool call failed: %s: %s", type(e).__name__, e)
            _last_error.set(self._error_detail(e))
            return None

    def complete_vision(self, system, text, image_b64, media_type,
                        max_tokens, model, timeout):
        """نداء رؤية واحد — صورة base64 + نصّ في رسالة مستخدم واحدة.

        يعكس `complete` حرفياً لكن المحتوى قائمةُ كتلٍ (صورة ثم نص). يسجّل
        الرموز في عدّاد اقتصاد البيانات (قناة جانبية) فتُحتسب كلفتُه كأيّ
        نداء. غياب المفتاح/الرفض/الفشل => None (فجوة معلنة، لا اختلاق)."""
        _last_error.set(None)
        _last_stop_reason.set(None)
        key = self._key()
        if not key:
            return None
        try:
            # WP-1 §1: استخلاص أقلّ تشتّتاً كالنصّي — ومُهمَلة كلّياً على
            # النماذج الرافضة (`_supports_sampling_params` هو الحكم الواحد).
            payload = {"model": model, "max_tokens": max_tokens,
                       "system": [{"type": "text", "text": system,
                                   "cache_control": {"type": "ephemeral"}}],
                       "messages": [{"role": "user", "content": [
                           {"type": "image",
                            "source": {"type": "base64",
                                       "media_type": media_type,
                                       "data": image_b64}},
                           {"type": "text", "text": text}]}]}
            if _supports_sampling_params(model):
                payload["temperature"] = 0
            resp = self._post(key, payload, timeout)
            data = resp.json()
            self._record_usage(model, data)
            stop_reason = data.get("stop_reason")
            _last_stop_reason.set(stop_reason)
            if stop_reason == "refusal":
                log.warning("vision call refused by the model")
                _last_error.set({"type": "refusal",
                                 "message": "model refused the request"})
                return None
            out = "".join(b.get("text", "") for b in data.get("content", [])
                          if b.get("type") == "text").strip()
            if not out:
                _last_error.set({"type": "empty_response",
                                 "message": f"HTTP 200 بلا نص — "
                                            f"stop_reason={stop_reason!r}"})
                return None
            _last_error.set(None)
            return out
        except Exception as e:  # noqa: BLE001 — optional layer must never crash
            log.warning("vision call failed: %s: %s", type(e).__name__, e)
            _last_error.set(self._error_detail(e))
            return None

    @classmethod
    def _consume_stream(cls, resp, total_s: float) -> tuple[dict, dict | None]:
        """اقرأ ردّ SSE وجمّعه إلى **نفس شكل** ردّ Messages API غير المبثوث:
        {"content": [كتل نصّ/tool_use], "stop_reason", "usage"} — فلا يتغيّر
        أيّ مستدعٍ. يعيد (data, abort_detail): `abort_detail=None` عند اكتمال
        البثّ؛ وعند الخمول (ReadTimeout من requests) أو تجاوز السقف الكلّي أو
        انقطاع الاتصال يُغلَق الردّ ويُعاد ما تجمّع مع تفصيل الإجهاض
        (`_error_detail`) و`stop_reason="aborted_timeout"`. لا استثناء يتسرّب."""
        blocks: dict[int, dict] = {}
        order: list[int] = []
        closed: set = set()
        partial_json: dict[int, str] = {}
        usage: dict = {}
        stop_reason = None
        abort = None
        t0 = time.monotonic()
        event_name = None
        events_seen = 0          # p6/T7: صفر أحداث ⇒ بوّابة تجاهلت البثّ
        message_stopped = False
        raw_lines: list[str] = []
        # ردٌّ بلا iter_lines لم يبدأ بثّاً أصلاً (وسيط يعيد جسداً عادياً):
        # صفر أحداث ⇒ مسار التراجع أدناه، لا إجهاض.
        _lines = (resp.iter_lines(decode_unicode=True)
                  if hasattr(resp, "iter_lines") else [])
        try:
            for raw in _lines:
                if time.monotonic() - t0 > total_s:
                    raise StreamTotalTimeout(
                        f"stream exceeded SILK_AI_STREAM_TOTAL_S={total_s:g}s")
                if raw is None:
                    continue
                line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
                line = line.strip()
                if events_seen == 0:      # مراجعة §58 #12: يُقرأ في مسار
                    raw_lines.append(line)   # التراجع وحده — لا نحتفظ بالبثّ كلّه
                if not line:
                    event_name = None
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except ValueError:
                    continue
                events_seen += 1
                kind = ev.get("type") or event_name
                if kind == "message_start":
                    u = (ev.get("message") or {}).get("usage") or {}
                    for k in ("input_tokens", "cache_read_input_tokens",
                              "cache_creation_input_tokens"):
                        if k in u:
                            usage[k] = u[k]
                elif kind == "content_block_start":
                    idx = int(ev.get("index", len(order)))
                    cb = dict(ev.get("content_block") or {})
                    if cb.get("type") == "text":
                        cb.setdefault("text", "")
                    elif cb.get("type") == "thinking":
                        # كتلةُ تفكيرٍ ممتدّ: نصُّها وتوقيعُها يصلان **دلتا**،
                        # فتُهيَّأ بحقلَيها كي يتراكما عليهما لا بجوارهما.
                        cb.setdefault("thinking", "")
                        cb.setdefault("signature", "")
                    elif cb.get("type") == "tool_use":
                        partial_json[idx] = ""
                    blocks[idx] = cb
                    order.append(idx)
                elif kind == "content_block_delta":
                    idx = int(ev.get("index", 0))
                    d = ev.get("delta") or {}
                    _dt = d.get("type")
                    # افتراضُ الكتلة يتبع نوعَ الدلتا: دلتا تفكيرٍ على فهرسٍ
                    # لم يصل افتتاحُه (وسيطٌ ابتلع حدثاً) كانت تُقلَب كتلةَ
                    # نصّ، فيعود التفكيرُ في `text` ويضيع التوقيعُ صامتاً.
                    _seed = ({"type": "thinking", "thinking": "", "signature": ""}
                             if _dt in ("thinking_delta", "signature_delta")
                             else {"type": "text", "text": ""})
                    blk = blocks.setdefault(idx, _seed)
                    if idx not in order:
                        order.append(idx)
                    if _dt == "text_delta":
                        blk["text"] = blk.get("text", "") + (d.get("text") or "")
                    elif _dt == "thinking_delta":
                        # الحادثة الحيّة 2026-08-23: كانت تُسقَط صامتةً، فتخرج
                        # كتلةُ التفكير بنصٍّ فارغ وتُرفَض عند إعادتها في الدور
                        # التالي بـ400 «each thinking block must contain
                        # thinking». التسلسلُ حرفيٌّ — لا تنقية ولا إعادة بناء.
                        blk["thinking"] = (blk.get("thinking", "")
                                           + (d.get("thinking") or ""))
                    elif _dt == "signature_delta":
                        # التوقيعُ يصل مقطَّعاً كالنصّ، وهو جزءٌ من الكتلة
                        # يجب أن يُعاد حرفياً وإلا رُفض الدور.
                        blk["signature"] = (blk.get("signature", "")
                                            + (d.get("signature") or ""))
                    elif _dt == "input_json_delta":
                        partial_json[idx] = (partial_json.get(idx, "")
                                             + (d.get("partial_json") or ""))
                elif kind == "content_block_stop":
                    idx = int(ev.get("index", 0))
                    closed.add(idx)       # مراجعة §58 #7: الإغلاق يُتتبَّع صراحةً
                    if idx in partial_json and \
                            blocks.get(idx, {}).get("type") == "tool_use":
                        try:
                            blocks[idx]["input"] = json.loads(partial_json[idx] or "{}")
                        except ValueError:
                            blocks[idx]["input"] = {}
                elif kind == "message_delta":
                    stop_reason = ((ev.get("delta") or {}).get("stop_reason")
                                   or stop_reason)
                    u = ev.get("usage") or {}
                    if "output_tokens" in u:
                        usage["output_tokens"] = u["output_tokens"]
                elif kind == "message_stop":
                    message_stopped = True
                    break
                elif kind == "error":
                    err = ev.get("error") or {}
                    raise RuntimeError("stream error event: %s: %s" % (
                        err.get("type"), err.get("message")))
        except Exception as e:  # noqa: BLE001 — الإجهاض يُعاد تفصيلاً لا استثناءً
            abort = cls._error_detail(e)
            stop_reason = _STREAM_ABORTED
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        # p6/T7: بوّابة/وسيط يتجاهل "stream": true ويعيد جسد JSON عادياً —
        # **صفر** أحداث SSE وبلا إجهاض ⇒ يُقرأ الجسد رسالةً عادية (المسار
        # مُسجَّل صراحةً كي لا يمرّ تجريدُ البثّ صامتاً في الإنتاج). بثٌّ بدأ
        # ثم مات لا يصل هنا (abort مضبوط) — يعود جزئياً بوسم aborted_timeout.
        if abort is None and events_seen == 0:
            body = None
            try:
                body = json.loads("".join(raw_lines))
            except ValueError:
                try:
                    body = resp.json()
                except Exception:  # noqa: BLE001 — لا جسد مقروء
                    body = None
            if isinstance(body, dict) and "content" in body:
                log.warning("AI call path=json_fallback — gateway returned a "
                            "JSON body for a stream request (0 SSE events)")
                return body, None
            abort = {"type": "empty_stream",
                     "message": "0 SSE events and no parseable JSON body"}
            stop_reason = _STREAM_ABORTED
        else:
            log.info("AI call path=streamed events=%d aborted=%s",
                     events_seen, bool(abort))
        if events_seen and abort is None and (not message_stopped or set(order) - closed):
            abort = {"type": "incomplete_stream", "message": "SSE ended before message/block completion"}
            stop_reason = _STREAM_ABORTED
        content = []
        for idx in order:
            blk = blocks[idx]
            if blk.get("type") == "tool_use" and idx not in closed:
                # مراجعة §58 #7: كتلة أداة لم تُغلَق (إجهاض) — وسائطُها JSON
                # جزئيّ لا يُخمَّن. كانت تمرّ بوسائطَ فارغة لأن
                # content_block_start يحمل input={} أصلاً، فبدت أداةً بلا
                # وسائط بدل أن تُسقَط. تُسقَط إلا إن اكتمل نصُّها فعلاً.
                log.warning("dropping an unclosed tool_use block %r — its "
                            "arguments are partial and are never guessed",
                            blk.get("name"))
                continue
            content.append(blk)
        if abort is not None and not usage.get("output_tokens"):
            # مراجعة §58 #3: `message_delta` (حاملُ رموز الإخراج) لا يصل عند
            # الإجهاض، فكان الإنفاق الأكبر يُسجَّل **صفراً**: حارسُ الميزانية
            # يعمى عنه والمصالحةُ تُعيد مالاً أُنفِق فعلاً. لا نختلق رقماً
            # دقيقاً — نُقدّر من النصّ المجمَّع ونُعلن أنه تقدير.
            _txt = "".join(b.get("text", "") for b in content
                           if b.get("type") == "text")
            _txt += "".join(partial_json.get(i, "") for i in partial_json)
            if _txt:
                usage["output_tokens"] = max(1, len(_txt) // 4)
                usage["output_tokens_estimated"] = True
                log.warning("aborted stream: output tokens ESTIMATED at ~%d "
                            "from %d chars (message_delta never arrived)",
                            usage["output_tokens"], len(_txt))
        data = {"content": content, "stop_reason": stop_reason}
        if usage:
            data["usage"] = usage
        return data, abort

    @staticmethod
    def _error_detail(e: Exception) -> dict:
        """فصّل الاستثناء — بلاغ حي: "مهلة أو خطأ شبكة" الغامضة كانت تخفي
        نوع الفشل الفعلي. لطلب HTTP فاشل (raise_for_status) نُظهر الرد
        (حالة + مقتطف نص) كما طلب المالك صراحة؛ لغيره نوع الاستثناء
        ورسالته (يميّز requests.ConnectTimeout عن requests.ReadTimeout
        تلقائياً — راجع _timeout_pair)."""
        detail = {"type": type(e).__name__, "message": str(e)[:300]}
        resp = getattr(e, "response", None)
        if resp is not None:
            try:
                detail["status_code"] = resp.status_code
                detail["response_body"] = (resp.text or "")[:300]
            except Exception:  # noqa: BLE001 — تفصيل إضافي، لا شرط
                pass
        return detail


class FakeProvider(LLMProvider):
    """مقعدٌ معلَّب على **مسار المزوّد الحقيقي** — R8 (TEST-1، تدقيق 2026-09-01).

    لماذا: كلُّ رُتب المتصفّح تمرّ بـ`SILK_PLATFORM_FAKE_ENGINE` الذي يقفز فوق الخطّ كلَّه
    (جسر ← بعثات ← توليف ← كاتب)، فبقي «الدراسةُ تكتمل فعلاً على الخطّ الحقيقي» غيرَ
    مُثبَتٍ خارج العيّنة. هذا المزوّد يردّ ردوداً معلَّبة **من داخل** الخطّ: كلُّ حلقةٍ
    ونقطةِ تفتيشٍ وحصّةٍ ومصالحةٍ تعمل كما في الإنتاج، بصفر نداءات شبكة وصفر دولار.

    لا يعيش في الإنتاج: `get_provider` يرفضه تحت أيّ إشارة إنتاج ويرتدّ إلى Anthropic
    بتحذير — لا مقعدَ صامتٌ يخدم عملاءَ حقيقيين."""

    _REPORT = ("## ملخّص تنفيذيّ\n\nهذه استجابةٌ معلَّبة من مزوّدٍ اختباريّ (FakeProvider) "
               "لإثبات الخطّ الحقيقي بلا نداء خارجيّ — ليست بحثاً ولا توصية.\n\n"
               "## المنهجية\n\nمصادرُ عامّة (Comtrade/البنك الدولي) عبر مسارها المعتاد.\n")

    def complete(self, system, user, max_tokens, model, timeout, **kw):
        return self._REPORT

    def complete_tools(self, system, messages, tools, max_tokens, model, timeout, **kw):
        return {"content": [{"type": "text", "text": self._REPORT}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0}}

    def complete_vision(self, system, text, image_b64, media_type,
                        max_tokens, model, timeout, **kw):
        return None          # الرؤيةُ خارج نطاق المقعد — «تعذّرت القراءة» صادقةً


_PROVIDERS = {"anthropic": AnthropicProvider, "fake": FakeProvider}


def _production_signal() -> bool:
    """إشارةُ إنتاج — R8/TEST-1: **نفسُ تعريف** `silk_platform.api.boot_config_guard`
    (سرُّ المنصّة مطلوب / كوكي آمنة) مضافاً إليه مصيدةُ القرص الدائم.

    `SILK_API_KEY` **ليس** منها عمداً: هو صمّامُ مصادقةٍ تضبطه كلُّ بيئةِ اختبارٍ تقريباً،
    ورُتبةُ ٤ **مضطرّةٌ** لضبطه (بدونه تحجب المنصّةُ طبقاتِ كلود كلَّها) — فجعلُه إشارةَ
    إنتاج كان يُبطِل المقعدَ في الموضع الوحيد الذي وُجد له."""
    return any(os.environ.get(k, "").strip().lower() in ("1", "true", "yes", "on")
               for k in ("SILK_REQUIRE_PERSISTENT_DATA_DIR",
                         "SILK_PLATFORM_REQUIRE_SECRET",
                         "SILK_PLATFORM_SECURE_COOKIES"))
_provider_instance: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """اختر المزوّد حسب `SILK_LLM_PROVIDER` (افتراضي anthropic) — مفرد
    مُخزَّن مؤقتاً (lazy singleton)؛ اسم غير معروف يتراجع بأمان لـAnthropic."""
    global _provider_instance
    if _provider_instance is None:
        name = os.environ.get("SILK_LLM_PROVIDER", "anthropic").strip().lower()
        if name == "fake" and _production_signal():
            log.warning("SILK_LLM_PROVIDER=fake ignored under a production signal — "
                        "falling back to Anthropic")
            name = "anthropic"
        cls = _PROVIDERS.get(name, AnthropicProvider)
        _provider_instance = cls()
    return _provider_instance


def reset_provider() -> None:
    """أعد ضبط المفرد المخزَّن — test-only reset (تبديل SILK_LLM_PROVIDER بين
    الاختبارات يتطلبه)."""
    global _provider_instance
    _provider_instance = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = get_provider()
    print(f"active provider: {type(p).__name__}")
