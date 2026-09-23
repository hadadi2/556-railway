"""بوابة الجودة قبل التسليم لسِلك — Silk pre-delivery quality gate (الموجة ١٠).

تشغَّل تلقائياً في نهاية كل `/research`، **قبل** أن يُعرَض DOCX — فحوصات
حتمية (لا كلود) على `view["deep_research"]` النهائي: لا رموز شركاء خامة،
لا تقطيع منتصف كلمة، لا تسريب Markdown/JSON خام، لا أرقام ثقة خامة في
المتن، لا تسريب سباكة داخلية (LLMAgent:*/وسوم dp)، تغطية الملحق التقني،
عدم إعلان "دليل غير كافٍ" حين توجد أدلة كافية، ترتيب/اكتمال الأقسام
الأحد عشر (§10.3)، وصحة البعثات (بعثة بلا نتائج مستشهَد بها). حكم PASS /
PASS-WITH-WARNINGS / FAIL؛ النتائج القابلة للإصلاح (Markdown/ثقة خام/
تقطيع/سباكة داخلية) تُصلَح آلياً بالفعل في طبقة العرض
(`silk_reports._strip_inline_markdown`/`_evidence_badge`/`_truncate_at_word`،
`silk_render._strip_internal_plumbing`) — هذه البوابة حارس انحدار يتأكد
أنها فعلاً أُصلحت، لا مصلح مستقل. النتائج غير القابلة للإصلاح (بنيوية/
بيانات) تُبنى كملاحظات تُعرَض داخل قسم "منهجية البحث ونطاقه" (٢) — لا
لافتة تحذير على الغلاف، ولا صمت.

منطق فحص صرف: صفر شبكة، صفر تعديل على الأرقام — قراءة وتشكيل فقط، مثل
`silk_render.py` تماماً.
"""
from __future__ import annotations

import logging
import os
import re

log = logging.getLogger(__name__)

PASS, WARN, FAIL = "PASS", "PASS-WITH-WARNINGS", "FAIL"

_MARKDOWN_RE = re.compile(r"(^#{1,6}\s)|(```)|(\*\*)", re.M)
# مفتاح JSON بأي حروف (لا اللاتينية فقط) — بلاغ حي: حكم مسرَّب عُرِّبت
# مفاتيحه ("{\"الحكم\":...}") فأفلت من [a-zA-Z_]+؛ [^"\s]+ يلتقط الصيغتين.
_RAW_JSON_RE = re.compile(r'[{]\s*"[^"\s]+"\s*:', re.M)
# §8 (قرار المُشرِف): نمطُ ثقةٍ **سياقيّ** — كلمةٌ مفتاحية (ثقة/confidence) +
# كسرٌ عشريّ. لا صيدَ كسورٍ مجرّدة: «0.6 مليون» ومقاديرُ البيانات مشروعة.
_RAW_CONFIDENCE_RE = re.compile(r"(?:ثقة|confidence)\s*[:=]?\s*0\.\d", re.I)
_TERMINAL_PUNCT = ".!?:؛،؟…\"'”)"
# بلاغ منتج من المالك: التقرير المعروض للعميل كشف السباكة الداخلية
# ("LLMAgent:tariffs_agreements"، وسوم استشهاد خام "dp7") — كلود يستشهد
# أحياناً حرفياً بوسوم رآها في مدخلاته. طبقة العرض تُصلح هذا فعلاً
# (silk_render._strip_internal_plumbing)؛ هذا الفحص حارس انحدار.
_INTERNAL_PLUMBING_RE = re.compile(r"LLM(?:Mission)?Agent:[A-Za-z_]+|\[?dp\d+\]?")
# بلاغ مالك (تسريب سباكة ٢): أسماء حقول داخلية إنجليزية ("verdict"،
# "confidence 0.64") ومفاتيح بعثات snake_case خام ("pricing_scout") ظهرت في
# نص معروض للعميل. طبقة العرض تُصلح فعلاً (_strip_internal_plumbing يعرّب
# الحقول، وlabel العربي يحل محل المفتاح) — هذان حارسا انحدار حتميان.
_EN_FIELD_LEAK_RE = re.compile(r"\b(?:verdict|confidence)\b")


def _check_markdown_and_raw_json(text: str) -> list[dict]:
    findings = []
    if not text:
        return findings
    if _MARKDOWN_RE.search(text):
        findings.append({"check": "markdown_artifacts", "repairable": True,
                         "note": "تسريب رموز Markdown (#/```/**) في النص المصدَر"})
    if _RAW_JSON_RE.search(text):
        findings.append({"check": "raw_json", "repairable": True,
                         "note": "كتلة JSON خام مسرَّبة في النص المصدَر"})
    return findings


def _check_raw_confidence(text: str) -> list[dict]:
    if text and _RAW_CONFIDENCE_RE.search(text):
        return [{"check": "raw_confidence", "repairable": True,
                 "note": "رقم ثقة خام '(ثقة 0.x)' مسرَّب في النص المصدَر"}]
    return []


# PR A §A1 (بلاغ تحليل ٧): تعارض قيمة الثقة — الملخّص «ثقة منخفضة (50%)»
# والقسم ٤ «الثقة متوسطة (73%)». رقمٌ واحد (`verdict["confidence"]`) سُقِّف في
# طبقة العرض (سقف رمز HS المُعلَّم) **بعد** أن جمّد الكاتب النسخة غير المسقوفة
# في المتن. الفكس الجذري تمريرُ القيمة المسقوفة نفسها للكاتب؛ هذه بوابة حتمية
# تُفشِل حين تفلت نسبتا ثقة مختلفتان إلى المتن — تلتقط نسب الثقة حصراً (شكل
# «عالية/متوسطة/منخفضة (NN%)» أو نسبة تجاور لفظَ ثقة)، لا نسب الحصص/النمو.
# الشكل ١: تسمية نطاقٍ + نسبة («منخفضة (50%)») — مخرَج `confidence_phrase`
# القياسيّ، يغطّي كلّ عرضٍ مشروع للثقة. الشكل ٢: لفظُ ثقةٍ **ملاصقٌ** للنسبة
# («درجة الثقة 73%») — نافذةٌ ضيّقة (فاصل/قوس فقط) كي لا تُلتقَط نسبةُ حصّة/
# نموٍّ تصادف قربَ كلمة «ثقة» في جملةٍ أخرى (إيجابٌ كاذب).
_CONF_PCT_RES = [
    re.compile(r"(?:عالية|متوسطة|منخفضة)\s*\(\s*(\d{1,3})\s*%\s*\)"),
    re.compile(r"(?:درجة\s+الثقة|الثقة|بثقة|ثقة)\s*[:(]?\s*(\d{1,3})\s*%"),
    # صيد الفجوات ٣: المرآة الإنجليزية — الفحص حاجب وكان خامداً كلياً على
    # lang=en. دورة C4: النمطُ العاري (high/low (N%)) أشعل على نثرٍ بريء
    # («Import duty is high (21%)») — التسميةُ تُقاس فقط بقرينة confidence
    # في نافذةٍ قصيرة قبلها (العربية تلزمها بنيةُ confidence_phrase نفسها).
    re.compile(r"confidence[^.\n]{0,30}?\b(?:high|medium|low)\b\s*"
               r"\(\s*(\d{1,3})\s*%\s*\)", re.I),
    re.compile(r"confidence(?:\s+(?:level|score))?\s*[:(]?\s*(?:is\s+)?"
               r"(\d{1,3})\s*%", re.I),
]


def _check_confidence_value_conflict(text: str) -> list[dict]:
    """PR A §A1 — نسبتا ثقة مختلفتان في التقرير نفسه = تعارض حاجب. الثقة
    قيمةٌ واحدة تُشتقّ من مصدر واحد (`silk_narrative.confidence_phrase` فوق
    `verdict["confidence"]` المسقوفة)؛ ظهور رقمين مختلفين يعني أن الكاتب حمل
    نسخةً غير مسقوفة بينما سقّفت طبقة العرض الغلاف — يجب توحيدهما قبل التسليم."""
    if not text:
        return []
    pcts: set[int] = set()
    for rex in _CONF_PCT_RES:
        for m in rex.finditer(text):
            try:
                pcts.add(int(m.group(1)))
            except ValueError:
                continue
    if len(pcts) >= 2:
        shown = "، ".join(f"{p}%" for p in sorted(pcts))
        return [{"check": "confidence_value_conflict", "repairable": False,
                 "note": (f"نسبتا ثقة مختلفتان في التقرير ({shown}) — درجة "
                          "الثقة قيمةٌ واحدة من مصدر واحد؛ التعارض يعني أن "
                          "الكاتب حمل نسخة غير مسقوفة بينما سُقِّف الغلاف. "
                          "وحِّد الثقة من مصدرها الواحد قبل التسليم")}]
    return []


def _check_mid_word_truncation(text: str) -> list[dict]:
    """تقطيع منتصف كلمة — آخر سطر في كل **فقرة** (كتلة أسطر متتالية بين
    سطرين فارغين) ينتهي بحرف/رقم بلا علامة ترقيم ختامية، مع طول كافٍ
    يستبعد عناوين/فواصل قصيرة عادية (بلاغ حي: "لا تتوفر من أد"). يفحص
    آخر سطر في الفقرة فقط لا كل سطر — نثر مُلفوف يدوياً عبر أسطر متعددة
    (تنسيق شائع للمصدر) لا يجب أن يُبلَّغ سطراً سطراً كتقطيع مزيَّف؛
    التقطيع الحقيقي يظهر في نهاية الوحدة المولَّدة لا وسطها."""
    if not text:
        return []
    findings = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        s = lines[-1]
        if s.startswith(("#", "|", "-", "*")):
            continue
        if len(s) < 25:
            continue
        if s[-1] not in _TERMINAL_PUNCT and not s.endswith("**"):
            findings.append({"check": "mid_word_truncation", "repairable": True,
                             "note": f"فقرة تنتهي بلا علامة ترقيم ختامية: "
                                     f"'...{s[-40:]}'"})
    return findings


def _check_trailing_ellipsis(text: str) -> list[dict]:
    """§5/§6 (أمر العمل الرئيس) — لا فقرة/حقيقة تنتهي بنقاط حذف «…»/«...»
    (بتر غير نظيف). حارس انحدار: القصّ النظيف (silk_reports._trim_sentence)
    يقطع عند حدّ جملة بلا نقاط حذف؛ ظهورها يعني بتراً وصل المُسلَّم."""
    if not text:
        return []
    findings = []
    for block in re.split(r"\n\s*\n", text):
        s = block.strip()
        # WP-2 §6(ب): الاقتباس الحرفي (كتلة > أو نصّ داخل «») يُستثنى — فقرة
        # غير اقتباسية تنتهي بنقاط حذف = بتر يصل العميل => FAIL لا تحذير.
        if s.startswith(">"):
            continue
        if s.endswith("…") or s.endswith("..."):
            findings.append({"check": "trailing_ellipsis", "repairable": False,
                             "note": "نصّ ينتهي بنقاط حذف «…» — بتر غير نظيف "
                                     "(§5): يجب القصّ عند حدّ جملة أو العرض كاملاً"})
        # موجة سدّ الفجوات (F3 — البند 12): «…» في منتصف كتلةٍ (بندُ قائمة
        # فجواتٍ مثلاً) كان غير مرئي هنا — الفرعُ أعلاه يرى نهايةَ الكتلة
        # فقط، والفحصُ السطري docx فقط (run_client_artifact_text_gate).
        # نفسُ عقد docx: تخطّي الاقتباس وحارسُ طول >25؛ السطرُ الأخير
        # يُستثنى حين تنتهي الكتلةُ نفسها بالحذف كي لا تزدوج الإصابة.
        lines = [ln.strip() for ln in s.splitlines()]
        last = len(lines) - 1
        for i, ln in enumerate(lines):
            if i == last and (s.endswith("…") or s.endswith("...")):
                continue
            if ln.startswith(">"):
                continue
            if len(ln) > 25 and (ln.endswith("…") or ln.endswith("...")):
                findings.append({
                    "check": "trailing_ellipsis", "repairable": False,
                    "note": "سطرٌ داخل كتلةٍ ينتهي بنقاط حذف «…» — بتر غير "
                            f"نظيف (البند 12): '...{ln[-40:]}'"})
    return findings


# §B-3 (حزمة الفكس v2.1) — شظية حرف/حرفين عربية يتيمة في آخر سطر فقرة، بلا
# علامة ترقيم ختامية بعدها: أثر بتر منتصف كلمة نجا من فحص علامة الترقيم
# (بلاغ حي: «تحققا ت» — «تحققات» انقطعت فبقيت شظيتان). لا يلتقط أدوات الربط
# أحادية الحرف المشروعة («و»/«ف»/«ب») حين تكون الفقرة كلها قصيرة أصلاً —
# نشترط طولاً كافياً قبل الشظية كي لا يكون التنبيه كاذباً على فقرة قصيرة عادية.
_ORPHAN_TOKEN_RE = re.compile(r"(?:^|\s)[ء-ي]{1,2}\s*$")
# مرآةٌ لاتينية (البند G-06): شظيةُ حرفٍ/حرفين تختم فقرةً بلا ترقيم. تُستثنى
# الكلماتُ الإنجليزية القصيرة المشروعة كي لا يُفشِل الحارسُ نثراً سليماً.
_ORPHAN_TOKEN_EN_RE = re.compile(r"(?:^|\s)([A-Za-z]{1,2})\s*$")
_ORPHAN_EN_ALLOW = frozenset({
    "a", "i", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in",
    "is", "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us",
    "we", "eu", "uk", "us", "ai", "hs", "kg", "m2", "m3"})


def _check_orphan_short_token(text: str, lang: str = "ar") -> list[dict]:
    """§B-3 — شظية 1-2 حرف عربية يتيمة تختم فقرة بلا علامة ترقيم: أثر بترٍ
    غير نظيف نجا من `_check_mid_word_truncation` (ذاك يفحص غياب الترقيم
    فقط، لا شكل الشظية نفسها)."""
    if not text:
        return []
    findings = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        s = lines[-1].strip()
        if not s or s[-1] in _TERMINAL_PUNCT:
            continue
        if lang == "en":
            m = _ORPHAN_TOKEN_EN_RE.search(s)
            if m and m.group(1).lower() not in _ORPHAN_EN_ALLOW \
                    and len(s) > len(m.group(0)) + 3:
                findings.append({
                    "check": "orphan_short_token", "repairable": False,
                    "note": ("A one/two-letter orphan fragment ends a "
                             f"paragraph — mid-word truncation: '...{s[-25:]}'")})
            continue
        m = _ORPHAN_TOKEN_RE.search(s)
        if m and len(s) > len(m.group(0)) + 3:
            findings.append({
                "check": "orphan_short_token", "repairable": False,
                "note": f"شظية حرف/حرفين عربية يتيمة تختم فقرة — أثر بتر "
                       f"منتصف كلمة: '...{s[-25:]}'"})
    return findings


# §B-4 — إحالة معلَّقة: النص يعد بملاحظة/قسم («انظر الملاحظة المنهجية»، أو
# «انظر «عنوان بين قوسين»») لا وجود له فعلياً في التقرير.
_METHOD_NOTE_REF_RE = re.compile(r"انظر\s+الملاحظة\s+المنهجية")
_QUOTED_SECTION_REF_RE = re.compile(r"(?:انظر|راجع)\s+[^.\n]{0,20}«([^»]+)»")
# مرآةٌ إنجليزية (البند G-06): «see/refer to "…"» بعلاماتٍ مزدوجةٍ أو مُزخرَفة.
_QUOTED_SECTION_REF_EN_RE = re.compile(
    r"(?:see|refer to)\s+[^.\n]{0,20}[\"\u201c«]([^\"\u201d»]+)[\"\u201d»]", re.I)
_METHOD_NOTE_REF_EN_RE = re.compile(r"see\s+the\s+methodology\s+note", re.I)
_HEADING_RE = re.compile(r"^#{2,3}\s+(?:\d+\.\s*)?(.+?)\s*$", re.M)


def _check_dangling_cross_reference(text: str,
                                    lang: str = "ar") -> list[dict]:
    """§B-4 — كل عبارة إحالة («انظر»/«راجع») يجب أن تُشير إلى قسم/ملاحظة
    موجودة فعلياً في نفس التقرير، لا وعداً معلَّقاً."""
    if not text:
        return []
    findings = []
    if lang == "en":
        return _dangling_cross_reference_en(text)
    if _METHOD_NOTE_REF_RE.search(text) and "ملاحظة منهجية" not in text \
            and "قسم المنهجية" not in text:
        findings.append({
            "check": "dangling_cross_reference", "repairable": False,
            "note": "النص يحيل إلى «الملاحظة المنهجية» لكن لا ملاحظة/قسم "
                   "بهذا المضمون موجود فعلياً في التقرير"})
    headings = _HEADING_RE.findall(text)
    for m in _QUOTED_SECTION_REF_RE.finditer(text):
        ref = m.group(1).strip()
        if not any(ref == h or ref in h or h in ref for h in headings):
            findings.append({
                "check": "dangling_cross_reference", "repairable": False,
                "note": f"إحالة معلَّقة إلى «{ref}» — لا عنوان قسم بهذا "
                       "الاسم موجود في التقرير"})
    return findings


# WP-2 §6 — سقالة «إذن ماذا؟»/"So what" الحرفية والنصوص النائبة التقنية:
# كلتاهما وصلت تقارير عملاء مُسلَّمة فعلاً (تدقيق 2026-07-22). FAIL لا تحذير.
_SO_WHAT_LEAK_RE = re.compile(r"إذن\s*،?\s*ماذا|So\s+what", re.I)
# مراجعة شيفرة PR #147: الإبرة العارية «أثر التتبع» كانت (أ) تُطابِق نثراً
# مشروعاً («أثر التتبع الرقمي…») و(ب) **تفوّت هدفها الفعلي** — النص النائب
# الحقيقي مُشكَّل («أثر التتبّع» بالشدّة) فلا يطابق الإبرة غير المشكَّلة.
# الفكس: عبارات مميِّزة كاملة + مقارنة بعد تجريد التشكيل من الطرفين.
_AR_DIACRITICS_STRIP_RE = re.compile("[ً-ْٰ]")


def _strip_ar_diacritics(s: str) -> str:
    """جرّد التشكيل العربي للمقارنة النصية فقط — لا يغيّر نصاً معروضاً."""
    return _AR_DIACRITICS_STRIP_RE.sub("", s or "")


# المُطبِّع العربي **الواحد** لفحوص أمر إصلاح المحرّك (أمر المُشرِف قبل
# إغلاق P2): الإبرة والنص كلاهما عبره — حادثتا «أساساً/أساسا» (البند 6)
# و«لم يُحدَّد/يتعذّر الحساب» (البند 5) نفسُ العائلة مرتين، وكل مطابقةٍ
# ذاتيةِ المنطق بذرةُ ثالثة. يجرّد التشكيل والتطويل، يوحّد أ/إ/آ→ا وة→ه
# وى→ي، يطوي المسافات (لا الأسطر — تقطيعُ الجمل يسبقه أو يتلوه سواء)،
# ويخفض اللاتينية. للمقارنة فقط — لا يمسّ نصاً معروضاً.
_AR_TATWEEL_RE = re.compile("ـ")
_AR_ALEF_RE = re.compile("[أإآ]")


def _norm_ar(s: object) -> str:
    t = _strip_ar_diacritics(str(s or ""))
    t = _AR_TATWEEL_RE.sub("", t)
    t = _AR_ALEF_RE.sub("ا", t)
    t = t.replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"[ \t]+", " ", t).lower()


# ── الصنف ١٦: عبارةٌ إلزاميةٌ يكسرها سطرٌ جديد · wrapped mandatory literal ──
# **العيبُ المرصود:** تقريرٌ يحمل التحذيرَ الإلزاميّ «…ولا يصلح هذا الرقم
# أساساً\nللتفاوض» — والفحصُ يُبلِّغ غيابَه، لأنّ `_norm_ar` يطوي المسافاتَ
# والجدولةَ فقط لا **الأسطرَ** (وهو تصميمٌ مقصود: فحوصٌ كثيرةٌ تقطع على
# الأسطر). فعبارةٌ إلزاميةٌ متعدّدةُ الكلمات لا تُطابَق أبداً إذا لفَّها
# الكاتبُ على سطرين — ومعاقبةُ الإفصاح عيبٌ أخطرُ من غيابه (الدرس 239).
#
# `_flat_ar` للحضورِ الحرفيّ وحدَه: طيُّ كلِّ فراغٍ بما فيه السطرُ الجديد.
# لا يُستعمَل حيث يكون السطرُ حدّاً دلالياً (قطعُ الفقرات، رؤوسُ الجداول).
def _flat_ar(s: object) -> str:
    """نصٌّ مطبَّعٌ **بطيّ كلّ فراغ** — لمطابقةِ حضورِ عبارةٍ إلزامية."""
    return re.sub(r"\s+", " ", _norm_ar(s)).strip()


def _dangling_cross_reference_en(text: str) -> list[dict]:
    """مرآةُ الإحالة المعلَّقة على الإنجليزية (البند G-06) — نفسُ المعيار."""
    findings = []
    # صيد الفجوات ٣: كان الشرط `"methodology" not in text` — وعبارةُ الإحالة
    # نفسُها («see the methodology note») تحملها، فالمرآةُ لا يمكن أن تُطلِق
    # أبداً (شرطٌ ينفي نفسه). تُستبعَد الإحالاتُ ثم يُبحَث عن القسم الفعلي —
    # كما تعمل النسخة العربية (أل التعريف تكسر الاحتواء هناك مصادفةً).
    remainder = _METHOD_NOTE_REF_EN_RE.sub("", text)
    if _METHOD_NOTE_REF_EN_RE.search(text) and \
            "methodolog" not in remainder.lower():
        findings.append({
            "check": "dangling_cross_reference", "repairable": False,
            "note": ("The report refers to a methodology note that does not "
                     "exist anywhere in it")})
    headings = _HEADING_RE.findall(text)
    for m in _QUOTED_SECTION_REF_EN_RE.finditer(text):
        ref = m.group(1).strip()
        if not any(ref == h or ref in h or h in ref for h in headings):
            findings.append({
                "check": "dangling_cross_reference", "repairable": False,
                "note": (f"Dangling cross-reference to \u00ab{ref}\u00bb — no "
                         "section with that name exists in the report")})
    return findings


_PLACEHOLDER_STRINGS = (
    "بند تقني غير قابل للعرض المباشر",
    "التفاصيل في أثر التتبع",
    "التفاصيل الكاملة في أثر التتبع",
    "التحليل السردي التفصيلي لهذا القسم غير متاح",
)

# **الموجة B (البند G-06).** بعد الموجة ٠ صارت الإنجليزية إعداداً حيّاً
# للمصانع، وكانت هذه الفحوصُ **الحاجزة** تخمُد عليها لأنّ أنماطها عربيةٌ
# حرفياً — فتسريبُ نصٍّ نائبٍ أو إحالةٍ معلَّقة في تقريرٍ إنجليزيّ يمرّ.
# المرايا مشتقّةٌ من نصوص `silk_i18n` نفسِها لا مكتوبةٌ يدوياً، فلا تتباعد
# عمّا يطبعه المُصدِّر فعلاً.
_PLACEHOLDER_STRINGS_EN = (
    "detailed narrative for this section is not available",
    "details are in the trace",
    "technical item not directly presentable",
)


def _placeholder_strings(lang: str) -> tuple:
    out = list(_PLACEHOLDER_STRINGS if lang != "en"
               else _PLACEHOLDER_STRINGS_EN)
    try:            # النصُّ النائبُ الفعليّ الذي يطبعه المُصدِّر لهذه اللغة
        import silk_i18n
        v = str(silk_i18n.t("section_narrative_absent", lang) or "").strip()
        if v:
            out.append(v)
    except Exception:  # noqa: BLE001 — القائمةُ الثابتة تكفي
        pass
    return tuple(out)


_GAPS_TRIGGER_RE = re.compile(r"فجوة بيانات|(?<![ء-ي])فجوات\s*:")
_GAPS_TRIGGER_EN_RE = re.compile(r"\bdata gaps?\b|(?<![A-Za-z])gaps\s*:",
                                 re.I)


def _check_gaps_closing_contradiction(dr: dict) -> list[dict]:
    """WP-4 §3 — تناقض الختام مع المتن: القسم الختامي سيطبع «لا فجوة
    جوهرية…» (كل مدخلات الفجوات الأربعة خالية — نفس المصدر الواحد
    `silk_reports._client_gap_inputs`) بينما نص التقرير يعلن «فجوة بيانات»
    صراحةً. الحالة المُسلَّمة فعلاً (2026-07-22): الختام نفى الفجوات بينما
    قسم المخاطر عدّد ثلاثاً (حوكمة البنك الدولي/الموسمية/سعر الصرف)."""
    text = ((dr.get("report") or {}).get("text") or "")
    summaries = " ".join(str((m or {}).get("summary") or "")
                         for m in (dr.get("missions") or {}).values())
    combined = text + "\n" + summaries
    # مراجعة شيفرة PR #147: «فجوات:» العارية كانت تطابق «الفجوات:» داخل
    # سردٍ سليم («الفجوات: لا توجد فجوات جوهرية») فتُفشِل تقريراً صحيحاً —
    # المُشغِّل الآن كلمة مستقلة (لا يسبقها حرف عربي) أو «فجوة بيانات».
    # البند G-06: المُشغِّلُ يقبل اللغتين — بقيّةُ الفحص بنيويّةٌ أصلاً
    # (يقرأ `_client_gap_inputs`، لا نصّاً)، فالمرآةُ نمطٌ واحدٌ لا أكثر.
    if not (_GAPS_TRIGGER_RE.search(combined)
            or _GAPS_TRIGGER_EN_RE.search(combined)):
        return []
    try:
        from silk_reports import _client_gap_inputs
        critical, informational = _client_gap_inputs(dr)
    except Exception:  # noqa: BLE001 — فحص إضافي لا يكسر البوابة
        return []
    if critical or informational:
        return []   # الختام لن يطبع النفي — لا تناقض
    return [{"check": "gaps_closing_contradiction", "repairable": False,
             "note": "التقرير يعلن «فجوة بيانات» في متنه بينما القسم "
                    "الختامي سيطبع «لا فجوة جوهرية تمنع اتخاذ القرار» — "
                    "تناقض فجوات حاجب للتسليم"}]


def _check_client_scaffold_leak(text: str) -> list[dict]:
    """WP-2 §6(أ) — العبارة السقالية الحرفية «إذن ماذا»/"So what" في نص
    يواجه العميل: أثر تعليمة المحلل القديمة، نُزِعت في المصدر والمُنظِّف —
    ظهورها هنا انحدار حاجب."""
    if text and _SO_WHAT_LEAK_RE.search(text):
        return [{"check": "client_scaffold_leak", "repairable": False,
                 "note": "العبارة السقالية الحرفية «إذن ماذا»/So what "
                        "ظهرت في نص التقرير — تُصاغ الآثار نثراً مدمجاً، "
                        "لا سقالة تعليمات تصل العميل"}]
    return []


def _check_placeholder_leak(text: str, lang: str = "ar") -> list[dict]:
    """WP-2 §6(ج) — نصّ نائب تقني («بند تقني غير قابل للعرض المباشر»/«أثر
    التتبع»/سطر عدم التوفّر العام) في نص يواجه العميل = فشل توليد سُلِّم
    بدل أن يُعاد أو يُحجَب — FAIL."""
    findings = []
    plain = _strip_ar_diacritics(text or "")
    for ph in _placeholder_strings(lang):
        if plain and _strip_ar_diacritics(ph).lower() in plain.lower():
            findings.append({
                "check": "placeholder_leak", "repairable": False,
                "note": f"نصّ نائب تقني وصل نص التقرير: «{ph}» — فشل "
                       "التوليد يُعاد أو يُحجَب التسليم، لا يُسلَّم نائب"})
    return findings


# §B-2 — بدل نصّ عام ثابت («التحليل السردي التفصيلي لهذا القسم غير متاح…»)
# حين يخلو قسم عميل من سرد الكاتب: FAIL يمنع التسليم (§0) بدل نصّ عام دائم
# يوهم بتحليل لم يحدث فعلياً. WP-2 §3: حقائق التقاطع الخام لم تعد تكفي
# وحدها (كانت تُسرَد نقاطاً حرفية بسقالة «إذن ماذا» وبتر) — القسم بلا سرد
# كاتب يمرّ فقط إن حمل نثر الصياغة التجارية المُحضَّر
# (`dr["client_fallback_prose"]`، نداء كاتب مصغّر قبل البوابة).


def _check_client_section_would_be_placeholder(dr: dict) -> list[dict]:
    """يُعيد استعمال منطق تجميع أقسام العميل الفعلي (`silk_reports`) للتحقّق
    مسبقاً: هل سيُصادف أيّ قسم من الأقسام الخمسة النهائية غياب سرد الكاتب
    **و** غياب حقائق تقاطع مهيكلة معاً؟ تلك هي بالضبط الحالة التي كانت
    تُغطّى بنصّ عام ثابت بدل تحليل حقيقي (البند §B-2).

    **الموجة ٠ (مراجعة ذاتية).** كانت هذه الدالّة تُعيد بناء منطق التجميع
    نسخةً ثالثة (مُمفصَلةً على العنوان العربي حرفياً) رغم أنّ تعليقَها يقول
    إنها «تُعيد استعمال» منطقَ `silk_reports` — فانكسرت على الإنجليزية بينما
    بقي الأصلُ سليماً، وكان كلُّ قسمٍ إنجليزيّ يُبلَّغ «نصّاً عاماً ثابتاً»
    ويُفشِل التقرير. الآن تُفوِّض فعلاً إلى `_client_missing_narrative_heads`
    (المُمفصَلة على الرقم الترتيبي) — مسارٌ واحدٌ لا ثلاثة، فيستحيل تباعدُهما.
    """
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []  # فشل الكاتب كاملاً محكوم عبر analyst_layer_failed/agent_failed
    try:
        from silk_reports import _client_missing_narrative_heads
    except Exception:  # noqa: BLE001 — فحص إضافي، لا يكسر البوابة
        return []
    prose_map = dr.get("client_fallback_prose") or {}
    findings = []
    for head in _client_missing_narrative_heads(dr):
        # WP-2 §3: القسم بلا سرد كاتب يمرّ فقط بنثر الصياغة التجارية
        # المُحضَّر — لا تكفي حقائق التقاطع الخام (كانت تُسرَد نقاطاً حرفية).
        if str(prose_map.get(head) or "").strip():
            continue
        findings.append({
            "check": "client_section_placeholder", "repairable": False,
            "note": f"قسم «{head}» سيُعرَض للعميل بنصٍّ عام ثابت بدل "
                   "تحليل حقيقي — لا سرد كاتب ولا نثر صياغة تجارية "
                   "مُحضَّر له في هذه التشغيلة"})
    return findings

# §D-5 (حزمة الفكس v2.1) — بلاغ حي: «بنسبة .%68» (نقطة قبل علامة النسبة
# قبل الرقم). حارس انحدار: `silk_render._fix_stray_percent_punctuation`
# تُصلح هذا فعلاً؛ ظهوره هنا يعني ثغرة في التطبيع لا حالة طبيعية.
_STRAY_PERCENT_DOT_BEFORE_RE = re.compile(r"\.\s*%")
_STRAY_PERCENT_DOT_AFTER_DIGIT_RE = re.compile(r"%\s*\.\d")


def _check_stray_percent_punctuation(text: str) -> list[dict]:
    """§D-5 — ترقيمٌ ملتصقٌ خاطئ حول علامة النسبة (بلاغ حي: «بنسبة .%68»)."""
    if not text:
        return []
    if _STRAY_PERCENT_DOT_BEFORE_RE.search(text) or \
            _STRAY_PERCENT_DOT_AFTER_DIGIT_RE.search(text):
        return [{"check": "stray_percent_punctuation", "repairable": True,
                 "note": "ترقيمٌ ملتصقٌ خاطئ حول علامة النسبة «%» "
                        "(نقطة في موضع الرقم) — أثر تنسيقٍ غير مُصلَح"}]
    return []


# §F-1 (حزمة الفكس v2.1) — سجلّ كيانات لكل تقرير: اسمان لاتينيان متعدّدا
# الكلمات بنفس مجموعة الكلمات بترتيب مختلف ("Taste of Nature" مقابل "Nature
# of Taste") على الأرجح نفس الكيان مكتوباً بصيغتين — WARN لا FAIL (خطر
# إيجابٍ كاذبٍ حقيقي على شركات مختلفة تتشارك كلمات شائعة).
_LATIN_ENTITY_RE = re.compile(
    r"\b[A-Z][a-zA-Z]+(?:\s+(?:of|de|&|and|the)?\s*[A-Z][a-zA-Z]+){1,3}\b")
_ENTITY_STOPWORDS = {"of", "de", "and", "the", "for"}


def _check_entity_near_duplicates(text: str) -> list[dict]:
    """§F-1 — اسمان يتشاركان نفس مجموعة الكلمات بترتيبٍ مختلف: على الأرجح
    نفس الكيان مكتوباً بصيغتين لم تُوحَّدا (سجلّ كيانات واحد لكل تقرير)."""
    if not text:
        return []
    seen: dict = {}
    findings = []
    for m in _LATIN_ENTITY_RE.finditer(text):
        name = m.group(0).strip()
        words = frozenset(w.lower() for w in re.findall(r"[A-Za-z]+", name)
                          if w.lower() not in _ENTITY_STOPWORDS)
        if len(words) < 2:
            continue
        prior = seen.get(words)
        if prior and prior != name:
            findings.append({
                "check": "entity_near_duplicate", "repairable": False,
                "note": f"اسمان متقاربان على الأرجح لنفس الكيان بترتيب "
                       f"كلمات مختلف: «{prior}» و«{name}» — وحِّدهما في "
                       "سجلّ كيانات واحد لكل تقرير"})
        else:
            seen.setdefault(words, name)
    return findings


# §F-3 (حزمة الفكس v2.1) — بلاغ حي: «ثقة عالية (68%)» بجانب 90%/75% بلا
# مقياس متّسق. النطاقات المعتمدة (silk_narrative.confidence_phrase): عالية
# ≥80% / متوسطة 60-79% / منخفضة <60%. حارس انحدار مستقلّ لا يعتمد على أن
# كل مكان في الكود يستدعي confidence_phrase فعلياً.
_CONFIDENCE_BAND_RE = re.compile(r"(عالية|متوسطة|منخفضة)\s*\((\d{1,3})%\)")
# المرآة الإنجليزية (صيد الفجوات ٣ — الفحص حاجب وكان خامداً على lang=en؛
# الاسم المتقادم «confidence_band_label» في قائمة الإعلان كان يخفيه عن قفل
# G-06 نفسه). التسمية الإنجليزية تُترجَم لمقابلها قبل مقارنة السلّم الواحد.
# دورة C4: قرينة confidence شرطٌ — النمط العاري أفشل «high (21%)» الجمركية.
_CONFIDENCE_BAND_EN_RE = re.compile(
    r"confidence[^.\n]{0,30}?\b(high|medium|low)\b\s*\((\d{1,3})%\)",
    re.IGNORECASE)
_BAND_EN_TO_AR = {"high": "عالية", "medium": "متوسطة", "low": "منخفضة"}


def _check_confidence_band_label(text: str) -> list[dict]:
    """§F-3 — كل تسمية «عالية/متوسطة/منخفضة» (أو مرآتها high/medium/low)
    تُطابِق نطاقها الرقمي المعتمد."""
    if not text:
        return []
    findings = []
    pairs = [(m.group(1), m.group(2))
             for m in _CONFIDENCE_BAND_RE.finditer(text)]
    pairs += [(_BAND_EN_TO_AR[m.group(1).lower()], m.group(2))
              for m in _CONFIDENCE_BAND_EN_RE.finditer(text)]
    for label, pct_s in pairs:
        try:
            pct = int(pct_s)
        except ValueError:
            continue
        # WP-1 §4: العتبات من سُلَّم المعايرة الواحد — لا نسخة محلية.
        from silk_style_contract import confidence_band_label
        expected = confidence_band_label(pct)
        if label != expected:
            findings.append({
                "check": "confidence_band_mismatch", "repairable": False,
                "note": f"تسمية ثقة «{label} ({pct}%)» لا تطابق النطاق "
                       f"المعتمد (عالية ≥80% / متوسطة 60-79% / منخفضة "
                       f"<60%) — المتوقَّع «{expected}»"})
    return findings


# §G-1 (حزمة الفكس v2.1) — بلاغ حي: «LPI 3.2 لعام 2022» — لا نسخة LPI لعام
# 2022 فعلياً (نسخ مؤشر أداء اللوجستيات للبنك الدولي: 2007/2010/2012/2014/
# 2016/2018/2023 فقط؛ الأعوام بين نسخة وأخرى لا نسخة منشورة لها). حارس
# حتمي: سنة مذكورة مباشرة مع «LPI» ضمن إحدى الفجوات المعروفة بين نسخ حقيقية.
_LPI_INVALID_EDITION_YEARS = {"2019", "2020", "2021", "2022", "2024"}
# نافذة قصيرة لا تعبر سطراً؛ تسمح بالنقاط العشرية («3.2») بين «LPI» والسنة
# لكنها قصيرة (≤25 محرفاً) فلا تقفز جملةً كاملة.
_LPI_YEAR_NEAR_RE = re.compile(
    r"LPI[^\n]{0,25}?(19\d\d|20\d\d)|(19\d\d|20\d\d)[^\n]{0,25}?LPI")


def _check_lpi_edition_year(text: str) -> list[dict]:
    """§G-1 — سنةٌ مذكورة مع LPI ضمن فجوة معروفة بين نسخ حقيقية منشورة."""
    if not text:
        return []
    findings = []
    for m in _LPI_YEAR_NEAR_RE.finditer(text):
        yr = m.group(1) or m.group(2)
        if yr in _LPI_INVALID_EDITION_YEARS:
            findings.append({
                "check": "lpi_invalid_edition_year", "repairable": False,
                "note": f"سنة {yr} مذكورة مع LPI لكن لا نسخة LPI منشورة "
                       "لهذا العام فعلياً (نسخ البنك الدولي المنشورة: "
                       "2007/2010/2012/2014/2016/2018/2023) — تحقّق من "
                       "السنة الصحيحة قبل الاستشهاد"})
    return findings


# ══════════════════════════════════════════════════════════════════════════
# معجمُ المِجَسّات ثنائيُّ اللغة · the bilingual probe lexicon
# ══════════════════════════════════════════════════════════════════════════
#
# **موجة الخياطة (البنود S-01…S-06).** الموجة ٠ جعلت لغةَ المصنع تحكم لغةَ
# التقرير، وبقيت مِجَسّاتُ بوّابة الجودة عربيةً حرفية — فصار سبعةُ فحوصٍ على
# تقريرٍ إنجليزيّ إمّا **صامتاً** (اثنان منها **حاجزان**) أو **كاذبَ
# الاشتعال** يحقن ملاحظةً عربية في تقريرٍ إنجليزيّ. إعادةُ إنتاجٍ مباشرة
# لكلٍّ منها في `tests/test_gate_language_parity.py`.
#
# القاعدةُ الدائمة: **مِجَسٌّ يُقرأ من معجمٍ واحدٍ ثنائيِّ اللغة، لا من سلسلةٍ
# حرفية داخل الفحص.** وفحصٌ بلا مرآةٍ إنجليزية يُعلَن في `_AR_ONLY_CHECKS` —
# لا يُترَك صامتاً. وقفلُ AST في اختبار التكافؤ يمنع عودةَ الحالتين معاً.
#
# الإنجليزيةُ مكتوبةٌ **أصالةً** (§34): «per kg» لا ترجمةً حرفية لـ«لكل كجم».
from silk_style_contract import PARAMETER_VERBS as _STYLE_PARAMETER_VERBS

_GATE_PROBES: dict[str, dict[str, tuple[str, ...]]] = {
    # قياسٌ على أساس الكيلوجرام مُدَّعى في المتن (§4.4).
    "per_kg_claim": {
        "ar": ("/كجم", "لكل كجم", "للكيلو", "للكيلوجرام"),
        "en": ("/kg", "per kg", "per kilo", "per kilogram")},
    # رفضُ تحويلٍ عامّ بلا تسمية الخاصية الفيزيائية المفقودة (§7).
    "generic_conversion_refusal": {
        "ar": ("يتعذر التحويل", "يتعذّر التحويل", "لا يمكن التحويل"),
        "en": ("conversion is not possible", "cannot be converted",
               "unable to convert", "conversion is not feasible",
               "no conversion is possible")},
    # المدةُ الكلية للنفاذ — من قرار الدخول حتى أول شحنة نظامية (§5.5).
    "access_timeline": {
        "ar": ("المدة الكلية", "المدّة الكلية", "إجمالي المدة"),
        # «total time» وحدَها فضفاضة («the total time in transit») فتُطفئ
        # الفحصَ على تقريرٍ لا يذكر مدةَ النفاذ (مراجعة ذاتية §58، الجولة ٢).
        "en": ("total lead time", "overall lead time", "end-to-end time",
               "total elapsed time")},
    # إعلانُ «دليل غير كافٍ» على تقاطعٍ يحمل بنوداً فعلية (حاجز).
    "insufficient_evidence": {
        "ar": ("دليل غير كافٍ", "دليل غير كاف", "لا تتوفر بيانات كافية"),
        "en": ("insufficient evidence", "not enough evidence",
               "no sufficient data", "insufficient data")},
    # صياغةٌ شرطية قرب رقمٍ مبنيٍّ على معلمةٍ معلنة (§7.2). العربيةُ تُقرأ
    # من عقد الأسلوب نفسِه (`silk_style_contract.PARAMETER_VERBS`، الدرس ٨٧)
    # لا نسخةً ثانية تتباعد عنه — والإنجليزيةُ مرآتُها المكتوبةُ أصالةً.
    "parameter_conditional": {
        "ar": ("سيناريو",) + _STYLE_PARAMETER_VERBS,
        # **مراجعة ذاتية §58.** «under the» و«if » كانتا هنا فأطفأتا الفحصَ
        # على أيّ متنٍ إنجليزيّ عاديّ تقريباً — مرآةٌ **أضعفُ** من أصلها
        # أسوأُ من غيابها: تُعلَن تغطيةً وهي ليست تغطية. المِجَسّاتُ الباقية
        # صياغاتُ افتراضٍ صريحة لا كلماتٌ شائعة.
        "en": ("scenario", "assuming", "assumes", "on the assumption")},
    # صدرُ مقطعٍ يتحدّث عن واردات السوق (حارسُ تناقض المقام).
    "market_imports": {
        "ar": ("الواردات", "واردات"),
        "en": ("imports", "import value")},
    # قرينةُ ادّعاءِ الحكم — تسميةُ الدرجة وحدَها ليست ادّعاءً (§H-2).
    "verdict_claim_cue": {
        "ar": ("التوصية", "الحكم", "نوصي", "نُوصي"),
        "en": ("recommendation", "we recommend", "verdict",
               "the recommended")},
}


def _probe(key: str, lang: str) -> tuple[str, ...]:
    """مِجَسّاتُ هذا المفهوم بلغةِ التقرير — مصدرٌ واحد لا سلسلةٌ حرفية.

    مفتاحٌ غير مسجَّل يرفع `KeyError` عمداً (نفس عقد `silk_i18n.t`): مِجَسٌّ
    ناقصٌ يجب أن ينكشف في الاختبار لا أن يصير فحصاً صامتاً في الإنتاج."""
    import silk_i18n
    return _GATE_PROBES[key][silk_i18n.normalize(lang)]


def _segment_re(key: str, lang: str) -> "re.Pattern[str]":
    """تعبيرٌ نمطيّ يلتقط مقطعاً يبدأ بأحد مِجَسّات هذا المفهوم بلغته.

    الفاصلُ يشمل الفاصلةَ العربية والإنجليزية معاً كي لا يعتمد الالتقاطُ على
    ترقيمِ لغةٍ بعينها."""
    alts = "|".join(re.escape(pr) for pr in _probe(key, lang))
    # **مراجعة ذاتية §58 (الجولة ٢).** الفاصلةُ اللاتينية `,` كانت في صنف
    # الإنهاء، فقُطِع «7,670,000» عند أوّل فاصلةٍ عشرية وسقط الالتقاط في
    # اللغتين معاً — أي أنّ «توسيعَ» الحارس كان تضييقاً له. الفاصلةُ العربية
    # وحدَها فاصلُ جُمَلٍ لا فاصلُ آحاد.
    return re.compile(rf"(?:{alts})[^،\n]{{0,60}}", re.I)


def _hits(text: object, key: str, lang: str) -> bool:
    """هل يذكر النصُّ هذا المفهوم بلغته؟ — مقارنةٌ غيرُ حسّاسةٍ للحالة على
    الإنجليزية (المتن يكتب «Per kg» و«per kg» سواءً)."""
    low = str(text or "").lower()
    return any(pr.lower() in low for pr in _probe(key, lang))


# §H-2 (حزمة الفكس v2.1) — بلاغ حي: شُحن «التوصية بالدخول» (تسمية درجة
# «دخول قوي») بجانب «يتحول إلى دخول قوي إذا تحقق شرطان» بينما الحكم
# القانوني الفعلي «دخول مشروط» — سلّم الدرجات مُعرَّف مرّة واحدة
# (`silk_render._VERDICT_LABELS_AR`)؛ هذا حارس انحدار: أيّ ذكرٍ لتسمية درجة
# **أعلى** من الدرجة الفعلية في متن التقرير يجب أن يُصاغ شرطاً مستقبلياً،
# لا حكماً حالياً.
# صدرُ **الجملة الفرعية** لا الجملة كاملةً: «We recommend a
# conditional entry now, and the exporter may enter the market later»
# كانت تُقرأ ادّعاءً لأنّ القرينةَ في أوّل الجملة (مراجعة ذاتية §58،
# الجولة ٢). الفاصلةُ فاصلُ دعوى.
_CLAUSE_HEAD_RE = re.compile(r"[.!?؟,،;؛\n]")


def _label_claimed_as_verdict(text: object, label: str, lang: str) -> bool:
    """هل يذكر المتنُ هذه التسميةَ **ادّعاءَ حكمٍ** لا مجردَ عبارةٍ عابرة؟

    **مراجعة ذاتية §58.** التسميةُ الإنجليزية «Enter the market» عبارةُ فعلٍ
    شائعة: «the cost to enter the market is USD 40,000» كان يُطلِق حاجزاً
    غيرَ قابلٍ للإصلاح على تقريرٍ سليم. فالمِجَسّ الآن التسميةُ **مع قرينةِ
    ادّعاءٍ** في نافذةٍ قصيرة حولها («Recommendation: Enter the market»)،
    وهو ما تعنيه العربيةُ «التوصية بالدخول» أصلاً بلفظها. اتّجاهٌ واحدٌ في
    اللغتين: تسميةٌ بلا قرينةِ ادّعاء ليست حكماً."""
    body = str(text or "")
    low, needle = body.lower(), str(label or "").lower()
    if not needle:
        return False
    # التسميةُ العربية «التوصية بالدخول» تحمل قرينتَها بلفظها — فأيُّ ذكرٍ
    # لها ادّعاءٌ، تماماً كما كان السلوكُ قبل هذه الموجة (لا إضعافَ للعربية
    # ثمناً لإصلاح الإنجليزية). والإنجليزيةُ «Enter the market» لا تحملها،
    # فتُطلَب القرينةُ في صدر جملتها.
    if _hits(label, "verdict_claim_cue", lang):
        return needle in low
    start = 0
    while True:
        i = low.find(needle, start)
        if i < 0:
            return False
        # القرينةُ تُطلَب في **صدر الجملة نفسِها** قبل التسمية، لا في جوارٍ
        # عامّ: جملةٌ سابقة تذكر الحكمَ ثمّ جملةٌ تذكر تكلفةَ الدخول كانت
        # تُقرأ ادّعاءً وهي ليست كذلك.
        head = _CLAUSE_HEAD_RE.split(body[:i])[-1]
        if _hits(head, "verdict_claim_cue", lang):
            return True
        start = i + len(needle)


def _check_recommendation_tier_label_consistency(
        dr: dict, lang: str = "ar") -> list[dict]:
    """§H-2 — الحكم الفعلي «دخول مشروط» لكن المتن يذكر تسمية «دخول قوي»
    («التوصية بالدخول» / «Enter the market») بلا تأطيرها كشرطٍ مستقبلي.

    **البند S-01 (حاجز كان صامتاً).** المِجَسّ كان السلسلةَ العربية حرفياً،
    فعلى تقريرٍ إنجليزيّ لا يشتعل الحاجزُ أبداً — يُشحَن للمصنع متنٌ يقول
    «Enter the market» فوق حكمٍ «Conditional entry». التسميةُ تُقرأ الآن من
    **مصدرِ التسمية نفسِه** (`silk_i18n.t("verdict_go", lang)`) لا من نسخةٍ
    حرفية تتباعد عنه."""
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    try:
        from silk_render import _verdict_tone
    except Exception:  # noqa: BLE001 — فحص إضافي، لا يكسر البوابة
        return []
    verdict = dr.get("verdict") or {}
    # مراجعة شيفرة PR #147: الحكم من المصدر الواحد (الحتمي أولاً) — القراءة
    # القديمة (ai أولاً) كانت تُفشِل تقريراً صحيحاً أو تتخطّى خطأً حقيقياً
    # كلما اختلفت قراءة كلود عن الحكم الحتمي المعروض.
    from silk_narrative import authoritative_verdict
    v_raw, _ = authoritative_verdict(verdict)
    if _verdict_tone(v_raw or "") != "conditional":
        return []
    import silk_i18n
    go_label = silk_i18n.t("verdict_go", lang)
    if _label_claimed_as_verdict(text, go_label, lang):
        return [{
            "check": "recommendation_tier_mislabel", "repairable": False,
            "note": ("الحكم القانوني الحالي «دخول مشروط» لكن المتن يذكر "
                     f"تسمية درجة أعلى «{go_label}» — صف الترقية كشرطٍ "
                     "مستقبلي («يتحول إلى X إذا تحقق كذا») لا حكماً حالياً")}]
    return []


# PR A §A2 (بلاغ تحليل ٧): تعارض تسمية الحكم — الغلاف/§5 «التوصية بالدخول»
# بينما §4 «توصية أولية بالدخول» تُعامَل حالةً مستقبلية. سلّم التسميات مُوحَّد
# الآن (`silk_render._VERDICT_LABELS_AR`، نغمة `preliminary` مستقلة يتّفق
# عليها الكاتب والغلاف)؛ هذه بوابة انحدار: تسميتا حكمٍ حاسمتان مختلفتان
# مذكورتان **إثباتاً** (لا كشرط قلبٍ مستقبليّ) في نفس المتن = تعارض حاجب.
# جذرُ «تحوّل» يلتقط كل تصريفاته (يتحوّل/تتحوّل/التحوّل) — البلاغ الحيّ في
# نموذج إسبانيا كان «تتحوّل … إلى التوصية بالدخول» (مؤنّث) فأفلت من «يتحول».
_VERDICT_FLIP_MARKER_RE = re.compile(
    r"تحوّل|تحول|إذا|إن\s|لو\s|بشرط|شرط|حين|متى|سيناريو|في\s+حال|احتمال|"
    # المرآة الإنجليزية (صيد الفجوات ٣ — الفحص حاجب وكان خامداً على lang=en)
    # دورة C4: `would` و`condition` (بادئةً — تطابق تسمية Conditional entry
    # نفسها!) وسّعا الإعفاء حتى كاد يحيّد المرآة — أضيق مجموعة أفعال قلب.
    r"\bif\b|\bwhen\b|\bunless\b|\bscenario\b|\bbecomes?\b|\bflip",
    re.IGNORECASE)


def _check_verdict_label_conflict(dr: dict) -> list[dict]:
    """PR A §A2 — تسميتا حكمٍ حاسمتان مختلفتان مذكورتان إثباتاً في المتن.
    كلّ تسمية يسبقها ضمن نافذة قصيرة مؤشّرُ شرطٍ مستقبليّ («يتحوّل إلى…
    إذا…») تُستثنى (شرط قلبٍ مشروع لا تعارض). ≥٢ تسمية حاسمة مؤكَّدة معاً =
    التقرير يعرض حكمين — يجب حكمٌ واحد من مصدر واحد."""
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    from silk_render import _VERDICT_LABELS_AR
    # التسميات الحاسمة فقط (لا «تعذّر إصدار توصية»/«غير محسومة» — قد تتعايش
    # مع تسميةٍ حاسمة كإعلان تغطيةٍ ناقصة لا كحكمٍ ثانٍ متعارض).
    decisive = {_VERDICT_LABELS_AR[k] for k in
                ("go", "preliminary", "conditional", "watch", "nogo")
                if k in _VERDICT_LABELS_AR}
    # المرآة الإنجليزية (صيد الفجوات ٣): معجم التسميات الإنجليزي القانوني من
    # silk_i18n — نفس المفاتيح الحاسمة؛ تقرير lang=en بحكمين كان يمرّ صامتاً.
    import silk_i18n
    for k in ("go", "preliminary", "conditional", "watch", "nogo"):
        en = (silk_i18n.TERMS.get(f"verdict_{k}") or {}).get("en")
        if en:
            decisive.add(en)
    asserted: set[str] = set()
    for label in decisive:
        start = 0
        while True:
            idx = text.find(label, start)
            if idx < 0:
                break
            start = idx + len(label)
            pre = text[max(0, idx - 45):idx]
            if _VERDICT_FLIP_MARKER_RE.search(pre):
                continue   # شرط قلبٍ مستقبليّ صريح — لا إثبات
            asserted.add(label)
    if len(asserted) >= 2:
        shown = "» و«".join(sorted(asserted))
        return [{"check": "verdict_label_conflict", "repairable": False,
                 "note": (f"تسميتا حكمٍ حاسمتان متعارضتان مذكورتان إثباتاً: "
                          f"«{shown}» — التقرير يعرض حكمين بينما الحكم قيمةٌ "
                          "واحدة من مصدر واحد؛ أيّ ترقية/بديل يُصاغ شرطاً "
                          "مستقبلياً صريحاً، لا حكماً حالياً موازياً")}]
    return []


# §C (حزمة الفكس v2.1) — مدقّق الاتساق الرقمي: أرقامٌ يُفترَض أنها **نفس
# المؤشر** لكنها اختُلفت بمقدار ضئيل يستحيل تفسيره إحصائياً (بلاغ حي: واردات
# 2023 شُحنت 6,733,369 في موضع و6,733,376 في آخر — فارق تحريف/خطأ حساب لا
# مصدرين مختلفين شرعاً). لا يلتقط أرقاماً متقاربة صدفةً بمصادر مختلفة
# (فارقٌ نسبي ≤0.5% فقط، وأكبر من صفر — التطابق التامّ ليس تناقضاً).
_LARGE_NUMBER_RE = re.compile(r"\b\d{1,3}(?:,\d{3}){2,}(?:\.\d+)?\b")


def _check_near_duplicate_figures(text: str) -> list[dict]:
    """§C-3 — رقمان كبيران متقاربان جداً (≤0.5% فارقاً نسبياً) في نفس
    التقرير على الأرجح نفس المؤشر بقيمتين متضاربتين، لا مصدرين مختلفين."""
    if not text:
        return []
    nums = []
    for m in _LARGE_NUMBER_RE.finditer(text):
        try:
            v = float(m.group(0).replace(",", ""))
        except ValueError:
            continue
        nums.append(v)
    findings = []
    seen_pairs = set()
    for i, a in enumerate(nums):
        for b in nums[i + 1:]:
            if a == b or a <= 0 or b <= 0:
                continue
            rel = abs(a - b) / max(a, b)
            if 0 < rel <= 0.005:
                key = (round(min(a, b)), round(max(a, b)))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                findings.append({
                    "check": "near_duplicate_figure", "repairable": False,
                    "note": f"رقمان كبيران متقاربان جداً ({a:,.0f} و{b:,.0f}، "
                           f"فارق {rel*100:.3f}%) على الأرجح نفس المؤشر بقيمة "
                           "واحدة قانونية لا قيمتين متضاربتين — وحِّدهما"})
    return findings


# §C-1 (حزمة الفكس v2.1) — بلاغ حي: HHI شُحن بدقّة عشرية مختلَقة («2184.7»)
# رغم أن المقياس معياريّاً رقمٌ صحيح بعد الضرب ×10000 (0-10000). دقّةٌ عشرية
# على HHI = وهم دقّة لم يُحسَب فعلياً بهذا التفصيل.
_HHI_DECIMAL_RE = re.compile(r"HHI[^0-9]{0,10}(\d{3,5}\.\d+)")


def _check_hhi_false_precision(text: str) -> list[dict]:
    """§C-1 — قيمة HHI (مقياس 0-10000 بعد الضرب) بدقّة عشرية مختلَقة.

    PR B §B9: صار **قابلاً للإصلاح** — `silk_render._fix_hhi_false_precision`
    يقرّبها إلى صحيحٍ قبل وصول النص (نفس نطاق regex هذا الفحص)؛ فظهورها هنا
    يعني فشلَ الإصلاح تحديداً في هذه التشغيلة (وصلت الدقّة الوهميّة المُسلَّم)
    — لذا هي ضمن `_REGRESSION_GUARD_FIRED` تُفشِل الحكم لا مجرّد تحذير."""
    if not text:
        return []
    findings = []
    for m in _HHI_DECIMAL_RE.finditer(text):
        findings.append({
            "check": "hhi_false_precision", "repairable": True,
            "note": f"قيمة HHI «{m.group(1)}» بدقّة عشرية على مقياس 0-10000 "
                   "— يجب أن تكون رقماً صحيحاً مقرَّباً (وهم دقّة غير محسوب "
                   "فعلياً بهذا التفصيل)"})
    return findings


# §C-2 (حزمة الفكس v2.1) — بلاغ حي: شُحنت مراتب موردين #1،#2،#5،#6 متخطّية
# #3،#4 — جدول موردين يجب أن يكون متصلاً (top-N كاملاً) لا صفوفاً منتقاة.
_SUPPLIER_RANK_RE = re.compile(r"#(\d{1,2})\b")


def _check_supplier_rank_contiguity(text: str) -> list[dict]:
    """§C-2 — مراتب موردين مذكورة بترقيم «#N» يجب أن تكون متصلة من ١."""
    if not text:
        return []
    ranks = sorted({int(m.group(1)) for m in _SUPPLIER_RANK_RE.finditer(text)})
    if len(ranks) < 2:
        return []
    expected = list(range(ranks[0], ranks[-1] + 1))
    if ranks != expected:
        missing = sorted(set(expected) - set(ranks))
        return [{
            "check": "supplier_rank_gap", "repairable": False,
            "note": f"مراتب موردين مذكورة بترقيم غير متصل ({ranks}) — "
                   f"مراتب مفقودة {missing}؛ جدول أعلى الموردين يجب أن يكون "
                   "متصلاً (top-N كاملاً) لا صفوفاً منتقاة"}]
    return []


def _check_internal_plumbing_leak(text: str) -> list[dict]:
    """تسريب سباكة داخلية (اسم وكيل خام/وسم استشهاد dp) في نص التقرير
    المصدَر — بلاغ منتج من المالك. حارس انحدار: طبقة العرض
    (`silk_render._strip_internal_plumbing`) تُصلح هذا فعلاً قبل وصول
    النص هنا؛ ظهوره يعني ثغرة في التطبيع لا حالة طبيعية."""
    if not text:
        return []
    if _INTERNAL_PLUMBING_RE.search(text):
        return [{"check": "internal_plumbing_leak", "repairable": True,
                 "note": "تسريب سباكة داخلية (اسم وكيل/وسم استشهاد خام) "
                        "في نص التقرير المصدَر"}]
    return []


def _check_english_field_and_mission_key_leak(text: str) -> list[dict]:
    """حقول داخلية إنجليزية (verdict/confidence) أو مفاتيح بعثات snake_case
    خام (pricing_scout وأخواتها) في نص معروض للعميل — حارس انحدار: طبقة
    العرض تعرّب الحقول (`_strip_internal_plumbing`) وتستبدل المفتاح بالاسم
    العربي (`label` في النموذج القانوني)؛ ظهور أيٍّ منها يعني ثغرة تطبيع.
    مفاتيح البعثات تُستورد كسولاً من السجل الواحد (silk_missions.MISSIONS)
    — لا قائمة يدوية تتقادم؛ فشل الاستيراد يمرّر فحص الحقول وحده."""
    findings = []
    if not text:
        return findings
    if _EN_FIELD_LEAK_RE.search(text):
        findings.append({"check": "english_field_leak", "repairable": True,
                         "note": "اسم حقل داخلي إنجليزي (verdict/confidence) "
                                "مسرَّب في النص المصدَر"})
    try:
        from silk_missions import MISSIONS
        keys_re = re.compile(
            r"\b(?:" + "|".join(re.escape(k) for k in MISSIONS) + r")\b")
        if keys_re.search(text):
            findings.append({"check": "mission_key_leak", "repairable": True,
                             "note": "مفتاح بعثة داخلي خام (snake_case) "
                                    "مسرَّب في النص المصدَر"})
    except Exception:  # noqa: BLE001 — حارس ثانوي، لا يعطّل البوابة
        pass
    return findings


# §2 (أمر العمل الرئيس — سرّية: صفر سباكة داخلية في المُسلَّم): محفّزات
# تُفشِل البوابة حتمياً إن ظهرت في نصّ التقرير أو ملخّصات المصادر. طبقة
# العرض (silk_render._strip_internal_plumbing) تُحيّدها فعلاً قبل وصول النص
# هنا — ظهور أيٍّ منها = ثغرة تطبيع، لا حالة طبيعية (حارس انحدار حتمي).
#   لا تُطبَع القيمة المطابَقة في الملاحظة كي لا تُعيد البوابة تسريبها بنفسها.
_CONFIDENTIALITY_LEAK_PATTERNS = [
    ("tool_use_leak", re.compile(r"tool[-\s]?use", re.I), "وسم استخدام أداة"),
    ("claude_mention", re.compile(r"\bClaude\b|كلود"), "ذكر صريح للأداة (كلود)"),
    ("env_var_leak", re.compile(r"SILK_[A-Z_]+"), "اسم متغيّر بيئة داخلي"),
    ("research_track_leak", re.compile(r"مسار(?:ات)?\s+(?:ال)?بحث"),
     "نسبة الحقائق لمسار بحث داخلي"),
    ("facts_list_leak", re.compile(r"بين\s+الحقائق"),
     "تلميح لقائمة حقائق داخلية"),
    ("ops_warning_leak", re.compile(r"⚠"), "رمز تحذير تشغيلي"),
]


# §8 (أمر العمل الرئيس — بوابة الأسلوب الحتمية): جودة العربية التجارية.
#   FAIL: «م$» (اختزال عملة)، «(1)» ترقيم إنجليزي داخل فقرة، «بين الحقائق».
#   WARN: «من ناحية» > مرّتين (سقف رابط)، رقم مفتاحي مميَّز مكرَّر > مرّتين.
# المرآة الإنجليزية «4.2m$» محظورة في العقد الإنجليزي نصاً وكانت بلا
# إنفاذ (موجة سدّ الفجوات الثانية).
_MSHORT_STYLE_RE = re.compile(r"\d\s*م\$|\d\s*[mM]\$")
# «(1)» وسط سطر لا بدايته — `\s` كانت تبتلع `\n` نفسَه فيُفشَل الترقيمُ
# المفتتِح لسطر قائمةٍ (البديل الذي يقترحه الموجّه!) — بياضُ داخل السطر فقط.
_INLINE_ENUM_RE = re.compile(r"(?<![\n(])[ \t]\(\d\)")
# §8 (قرار المُشرِف): قائمةُ أدوات الربط الموسَّعة — عباراتٌ متعدّدةُ الكلمات
# (خطرُ إيجابٍ كاذبٍ ضئيل). تدرّجٌ لكلّ أداة: ≤٢ تمرّ، ٣–٤ WARN، ≥٥ FAIL.
_CONNECTORS = ("من ناحية", "علاوة على ذلك", "بالإضافة إلى",
               "من جهة أخرى", "إضافة إلى ذلك")
# رقم مفتاحي مميَّز: نسبة بكسر عشري («55.28%») أو رقم بفواصل آلاف («61,000,000»)
# أو قيمة HHI مجاورة للفظها — عادةً لا يتكرّر طبيعياً، فتكراره >مرّتين حشو.
_KEYFIG_RES = [
    re.compile(r"\d{1,3}\.\d+\s*%"),
    re.compile(r"\d{1,3}(?:,\d{3}){2,}"),
    re.compile(r"HHI[^0-9]{0,8}\d{3,5}"),
]


def style_digest(text: str) -> dict:
    """عدّادُ أدوات الربط والأرقام المفتاحية (§8) — عدٌّ فقط، لا حكم. يُطبَع
    **دائمًا** في CI (كمبدأ §4: الأخضر/التحذير مفحوصٌ لا مُستنتَج)."""
    text = text or ""
    connectors = {c: len(re.findall(re.escape(c), text)) for c in _CONNECTORS}
    connectors = {c: n for c, n in connectors.items() if n}
    figures: dict = {}
    for rex in _KEYFIG_RES:
        for m in rex.finditer(text):
            tok = re.sub(r"\s+", "", m.group(0))
            figures[tok] = figures.get(tok, 0) + 1
    figures = {t: n for t, n in figures.items() if n}
    return {"connectors": connectors, "key_figures": figures}


def _style_tier(n: int) -> str:
    """تدرّجُ الأسلوب: ≥٥ FAIL، ٣–٤ WARN، وإلا ok."""
    return "FAIL" if n >= 5 else "WARN" if n >= 3 else "ok"


def format_style_digest(text: str) -> str:
    """خُلاصةُ الأسلوب القابلة للفحص — تُطبَع دائمًا في CI (قرار المُشرِف §8)."""
    d = style_digest(text)
    out = ["----- §8 style digest (connectors / key-figures) -----"]
    if not d["connectors"] and not d["key_figures"]:
        out.append("  (none over threshold-tracked patterns)")
    for c, n in sorted(d["connectors"].items(), key=lambda kv: -kv[1]):
        out.append(f"  connector «{c}» ×{n}  [{_style_tier(n)}]")
    for t, n in sorted(d["key_figures"].items(), key=lambda kv: -kv[1]):
        out.append(f"  key-figure «{t}» ×{n}  [{_style_tier(n)}]")
    return "\n".join(out)


def _check_style(text: str) -> list[dict]:
    """§8 — جودة الأسلوب الحتمية (بلا كلود). FAIL على اختزال العملة/الترقيم
    الإنجليزي داخل الفقرة؛ وتدرّجٌ لأدوات الربط والأرقام المفتاحية (٣–٤ WARN،
    ≥٥ FAIL) — قرار المُشرِف §8: أسلوبٌ لا تسريب، فالتصعيد عند الإفراط فقط."""
    findings = []
    if not text:
        return findings
    if _MSHORT_STYLE_RE.search(text):
        findings.append({"check": "style_currency_shorthand", "repairable": True,
                         "note": "اختزال العملة «م$» — اكتب «مليون دولار» كاملةً"})
    if _INLINE_ENUM_RE.search(text):
        findings.append({"check": "style_inline_enumeration", "repairable": False,
                         "note": "ترقيم إنجليزي «(1)…(2)» داخل فقرة — استعمل "
                                 "أولاً/ثانياً أو قائمة مرقّمة"})
    dg = style_digest(text)
    for c, n in dg["connectors"].items():
        if n >= 5:
            findings.append({"check": "style_connector_excess", "repairable": False,
                             "note": f"أداة الربط «{c}» تكرّرت {n} مرّات "
                                     "(≥٥ = حشوٌ أسلوبيّ يُفشِل) — نوّع أدوات الربط"})
        elif n >= 3:
            findings.append({"check": "style_connector_overuse", "repairable": False,
                             "note": f"أداة الربط «{c}» تكرّرت {n} مرّات "
                                     "(الحدّ المريح مرّتان) — نوّع أدوات الربط"})
    for tok, n in dg["key_figures"].items():
        if n >= 5:
            findings.append({
                "check": "style_repeated_key_figure_excess", "repairable": False,
                "note": f"رقم مفتاحي «{tok}» تكرّر {n} مرّات في المتن "
                        "(≥٥ = حشوٌ يُفشِل) — اذكره كاملاً مرّة ثم أحِل إليه"})
        elif n >= 3:
            findings.append({
                "check": "style_repeated_key_figure", "repairable": False,
                "note": f"رقم مفتاحي «{tok}» تكرّر {n} مرّات في المتن "
                        "(الحدّ مرّتان) — اذكره كاملاً مرّة ثم أحِل إليه"})
    return findings


def _check_confidentiality_leaks(text: str) -> list[dict]:
    """§2 — تسريب سرّية في المُسلَّم (اسم أداة/متغيّر بيئة/مسار بحث/…). حارس
    انحدار: يُفشِل البوابة إن أفلت أيّ محفّز من طبقة التطهير."""
    findings = []
    for check, pat, human in _CONFIDENTIALITY_LEAK_PATTERNS:
        if pat.search(text or ""):
            findings.append({
                "check": check, "repairable": True,
                "note": f"تسريب سرّية داخلي في نصّ التقرير ({human}) — "
                        "يجب تحييده قبل التسليم"})
    return findings


def _check_bare_partner_codes(dr: dict) -> list[dict]:
    """رمز شريك خام بدل اسم — حارس انحدار دائم لإصلاح ١٠.٢أ
    (`silk_data_layer.partner_name`) لا فحصاً أولياً؛ يُتوقَّع نظافته دوماً
    الآن لكنه يبقى يرصد أي تسرّب مستقبلي (مصدر بيانات جديد لا يمرّ عبر
    partner_name).

    سدّ تسريب (الطبقة ٧ — مفارقة البوابة): كانت ملاحظة هذا الفحص نفسها
    تحمل مفتاح البعثة الخام (snake_case) وتنسيق repr بايثون الخام
    (`{p!r}` → `'042'` بعلامات اقتباس بايثونية) — وهذه الملاحظة
    (`repairable: False`) تُحقَن مباشرة في قسم "منهجية البحث ونطاقه"
    المعروض للعميل عبر `methodology_notes`؛ أي بوابة الجودة كانت تكتشف
    تسريباً ثم تُصدر تسريباً موازياً بنفسها. الاسم التجاري + بلا تنسيق
    بايثون الآن، بنفس `_mission_label` المستعمَل في بقية هذا الملف."""
    findings = []
    for key, m in (dr.get("missions") or {}).items():
        label = _mission_label(key)
        for f in (m.get("findings") or []):
            v = f.get("value")
            if isinstance(v, dict) and "partner" in v:
                p = str(v.get("partner") or "")
                if p.isdigit():
                    findings.append({
                        "check": "bare_partner_code", "repairable": False,
                        "note": f"[{label}] رمز شريك خام بلا اسم: «{p}»"})
    return findings


def _check_intersection_insufficiency(dr: dict, lang: str = "ar") -> list[dict]:
    """"دليل غير كافٍ" رغم وجود ≥٢ بند ذي صلة — بلاغ حي (الموجة ٩-١٠).

    **البند S-02 (حاجز كان صامتاً).** كلا مِجَسّيه — اسمُ التقاطع وعبارةُ
    «الدليل غير الكافي» — كانا عربيَّين حرفياً، فتقريرٌ إنجليزيّ يعلن
    «insufficient evidence» فوق تقاطعٍ يحمل بنوداً فعلية يمرّ الحاجزَ صامتاً.
    الاسمُ يُقرأ الآن من معجم `silk_i18n` (نفسُه الذي يطبعه العارض) والعبارةُ
    من معجم المِجَسّات."""
    from silk_render import _category_label
    from silk_market_analyst import _CATEGORY_LABELS
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    by_cat = (dr.get("analyst") or {}).get("by_category") or {}
    findings = []
    for cat in _CATEGORY_LABELS:
        items = by_cat.get(cat) or []
        if len(items) < 2:
            continue
        label = _category_label(cat, lang)
        idx = text.lower().find(label.lower())
        # **مراجعة ذاتية §58.** كان المتنُ كلُّه يصير النافذةَ حين لا يُعثَر
        # على اسم التقاطع — فجملةٌ واحدة تقول «دليل غير كافٍ» تُنسَب إلى
        # **كلّ** تقاطعٍ ذي بنود، وعلى الإنجليزية يقع ذلك دائماً (اسمُ
        # التقاطع مصطلحُ عرضٍ لا يكتبه الكاتبُ في متنه) ⇒ خمسةُ حواجزَ
        # كاذبة على تقريرٍ سليم. لا إسنادَ بلا موضع: تقاطعٌ لا يُعثَر عليه
        # لا يُلام — وهو نفسُ عقدِ عدم الاختلاق مطبَّقاً على الإسناد.
        if idx < 0:
            continue
        window = text[idx:idx + 400]
        if _hits(window, "insufficient_evidence", lang):
            findings.append({
                "check": "intersection_insufficiency", "repairable": False,
                "note": f"تقاطع '{label}' يحوي {len(items)} بند(اً) ذا صلة "
                       "لكن النص يعلن 'دليل غير كافٍ' بدل الحساب الحسابي"})
    return findings


def _check_section_structure(dr: dict, lang: str = "ar") -> list[dict]:
    """ترتيب/اكتمال الأقسام الأحد عشر (§10.3) — يعيد استعمال الفحص الحتمي
    الموجود أصلاً في silk_ai_judge (مصدر حقيقة واحد لا تكرار منطق).

    **الموجة ٠ (مراجعة ذاتية).** بلا تمرير اللغة كان الفحصُ يقارن عناوينَ
    تقريرٍ إنجليزيّ بقائمةٍ عربية، فيُبلِغ أنّ **الأحد عشر كلَّها مفقودة**
    ويُفشِل كلَّ تقريرٍ إنجليزيّ سليم — و`section_structure` في
    `FAIL_TRIGGER_CHECKS`. المعيارُ البنيويّ واحدٌ، وقائمةُ التسميات تتبع
    اللغة."""
    from silk_ai_judge import _section_order_issues
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    return [{"check": "section_structure", "repairable": False, "note": issue}
           for issue in _section_order_issues(text, lang)]


def _mission_label(key: str) -> str:
    """اسم البعثة التجاري بالعربية — بلاغ منتج من المالك: ملاحظات هذه
    البوابة تصل قسم "حدود المنهجية وجودة البيانات" في التقرير المعروض
    للعميل مباشرة؛ المفتاح snake_case الخام (مثل "tariffs_agreements")
    سباكة داخلية لا لغة تجارية."""
    try:
        from silk_missions import MISSIONS
        row = MISSIONS.get(key)
        if row and row.get("name"):
            return row["name"]
    except Exception:  # noqa: BLE001 — تسمية تجميلية لا شرط فحص
        pass
    return key.replace("_", " ")


#: البعثاتُ التي **تقرؤها طبقةُ الأعمدة فعلاً** — فشلُ إحداها يحجب التسليم.
#:
#: **مقيسةٌ من `silk_deep_pillars` لا مُقدَّرة** (تصحيحُ مراجعةٍ ذاتية §58):
#: أوّلُ تعدادٍ كُتب «من أعمدة القرار الخمسة» بالحدس فأخطأ في الاتجاهين —
#: أدرج `pricing_scout` وهي لا تُقرأ في `build_pillar_inputs` إطلاقاً، وأسقط
#: `tariffs_agreements`/`demographics_economy`/`logistics` وهي تُقرأ. القائمةُ
#: أدناه هي **بالضبط** ما يناديه `_metric_findings`/`_findings` هناك
#: (`build_pillar_inputs` و`_COMPONENT_SOURCES`)، ويقفلها اختبارٌ يقارنها
#: بالمصدر فلا تتباعد صامتةً.
#: ما عداها **إثرائيٌّ**: يُثري التقريرَ ولا يُقيم عموداً، ففشلُه يُعلَن
#: ولا يمنع القرار.
_CORE_EVIDENCE_MISSIONS = frozenset({
    "trade_flow", "competitors", "demographics_economy",
    "tariffs_agreements", "risk_news", "logistics", "customs_requirements"})

#: مجموعةُ الإثرائيات المعرَّفة — مقامُ عتبة النصف. **ثابتةٌ لا محسوبةٌ من
#: الحمولة**: حمولةٌ جزئية (بعثاتٌ قليلة في اختبارٍ أو جسرٍ محاكى) كانت
#: تُصغِّر المقامَ فيعود الحجبُ على فشلٍ إثرائيٍّ واحد (§58).
def _optional_missions() -> frozenset:
    from silk_missions import MISSION_ORDER
    return frozenset(MISSION_ORDER) - _CORE_EVIDENCE_MISSIONS


def _check_agent_health(dr: dict) -> list[dict]:
    """بعثات بلا أي نتيجة مستشهَد بها — تُسرَد صراحة، لا تُخفى داخل ملخّص.

    بعثة **فشلت فعلياً** (`failed=True`) أشد من بعثة نجحت لكن لم تجد
    جديداً (مثل `opportunity_gaps` حين تكون كل الفرص مغطّاة أصلاً في
    البعثات الأخرى) — الأولى بند `agent_failed`، الثانية `agent_empty`
    (ملاحظة منهجية فقط، لا تُفشِل الحكم وحدها).

    **والتناسبُ بين الفشلين (بلاغ المالك، حادثةٌ مقيسة):** كان أيُّ فشلٍ
    يُصدِر `agent_failed` الحاجب، فبعثةٌ إثرائيةٌ صفريةٌ واحدة من اثنتي
    عشرة تُعامَل كتقريرٍ بلا أدلةٍ أصلاً. دراسةٌ حقيقية (عشرُ بعثاتٍ
    بأدلةٍ مستشهَدة، جدولُ قرارٍ كامل، أسعارٌ بعلامةٍ ومتجر) رُفض تسليمُها
    لأنّ «اتجاهات الطلب» و«الفرص» لم تُنتجا استشهاداً — وكلتاهما لا تقيم
    عموداً. فصار الحجبُ **للجوهريّ** (`_CORE_EVIDENCE_MISSIONS`)، والإثرائيُّ
    `agent_failed_optional`: ملاحظةٌ شديدةٌ تصل «حدود المنهجية» ولا تحجب.

    **وحدُّ الكمّ يبقى**: فشلُ نصف الإثرائيات فأكثر يعود `agent_failed` —
    تقريرٌ نصفُ إثرائه فارغٌ ليس تقريرَ قرارٍ ولو نجا جوهرُه. (وهذا نفسُ
    مبدأ العتبة في `_style_grade` أعلاه؛ كان هذا الفحصُ وحدَه بلا واحدة.)
    """
    findings = []
    missions = dr.get("missions") or {}

    def _void(m: dict) -> bool:
        """بعثةٌ **بلا أدلةٍ فعلاً** — لا رايةٌ مجمّدةٌ وحدَها.

        `failed = not findings` تُجمَّد في `run_llm_agent` **قبل** أن تُلحِق
        خطواتُ D3 (`_augment_risk_news_wgi`/`_fx`, `_augment_competitors_
        structured`) أدلّتَها الحتمية. فبعثةٌ رُفعت رايتُها ثمّ امتلأت
        بأدلةٍ مُهيكَلة كانت تُحجَب وتُوصَف «بلا نتائج مستشهَد بها» بينما
        طبقةُ الأعمدة تحسب منها درجةً (§58). القياسُ على ما وصل فعلاً.
        """
        return bool(m.get("failed")) and not (m.get("findings") or [])

    opt_defined = _optional_missions()
    optional_failed = [k for k, m in missions.items()
                       if _void(m) and k in opt_defined]
    # المقامُ من المجموعة المعرَّفة لا من الحاضرة (انظر `_optional_missions`).
    optional_blocks = len(optional_failed) * 2 >= len(opt_defined)
    for key, m in missions.items():
        label = _mission_label(key)
        if _void(m):
            if key in _CORE_EVIDENCE_MISSIONS:
                check = "agent_failed"
            elif optional_blocks:
                # سببُ الحجب هنا **عتبةُ العدد** لا عمودٌ بلا سند — فاسمٌ
                # ونصٌّ يقولان ذلك، وإلا أُرسِل القارئُ خلف سببٍ لم يقع
                # (نفسُ عائلة الدرسين ٢٥٥ و٢٦٩).
                check = "agent_failed_many_optional"
            else:
                check = "agent_failed_optional"
            findings.append({
                "check": check, "repairable": False,
                "note": f"بعثة '{label}' فشلت بلا نتائج مستشهَد بها — "
                       f"{m.get('summary') or 'بلا ملخّص'}"})
        elif not (m.get("findings") or []):
            findings.append({
                "check": "agent_empty", "repairable": False,
                "note": f"بعثة '{label}' نجحت لكن بلا نتائج مستشهَد بها — "
                       f"{m.get('summary') or 'بلا ملخّص'}"})
    return findings


def _check_analyst_layer_failure(dr: dict) -> list[dict]:
    """فشل طبقة المحلل الشامل كاملة — بلاغ حي إنتاجي (تمور/هولندا): نداءا
    المحلل الشامل وكاتب التقرير تجاوزا مهلة ثابتة فأعادا None، فظهرت
    التقاطعات الخمسة كلها "دليل غير كافٍ" مع غياب التقرير الكامل — ومرّت
    البوابة رغم ذلك لأن كل الفحوصات أعلاه تشترط نص تقرير غير فارغ.

    هذا فحص مستقل لا يشترط وجود نص: تشغيلة بلا تقرير كامل **و** بخمس
    تقاطعات معلنة كلها ناقصة الأدلة معاً = فشل الطبقة كلها، لا نتيجة
    تحليل حقيقية — لا يجوز أن تمر بحكم PASS/PASS-WITH-WARNINGS."""
    from silk_market_analyst import REQUIRED_CATEGORIES

    text = ((dr.get("report") or {}).get("text") or "")
    if text:
        return []
    missing = set((dr.get("analyst") or {}).get("missing_categories") or [])
    if missing >= set(REQUIRED_CATEGORIES):
        return [{"check": "analyst_layer_failed", "repairable": False,
                 "note": "طبقة المحلل الشامل فشلت كاملة: التقاطعات الخمسة "
                        "كلها بلا أدلة كافية والتقرير الكامل غائب — نداء "
                        "المحلل الشامل و/أو كاتب التقرير فشل (مهلة أو خطأ "
                        "شبكة)، لا نتيجة تحليل حقيقية لهذه التشغيلة"}]
    return []


# سقف صفوف الملحق التقني — ثابت واحد مشترك مع المصدِّر
# (`silk_reports._docx_technical_appendix`) كي لا ينحرف حجم الجدول المُسلَّم
# عن رسالة البوابة. رُفع 80 ← 150 (بلاغ حي Nadec/اليمن: 102 استشهاداً
# قُصّت إلى 80 فظهر بلاغ `audit_coverage` على كل تصدير).
AUDIT_APPENDIX_CAP = 150
_AUDIT_APPENDIX_CAP = AUDIT_APPENDIX_CAP   # الاسم القديم — توافق داخلي


def _check_audit_coverage(dr: dict) -> list[dict]:
    """سقف ملحق `AUDIT_APPENDIX_CAP` صفاً (150 حالياً) — إن تجاوزه إجمالي
    الاستشهادات، أعلن القطع صراحة بدل حذف صامت ("لا سقف صامت")."""
    total = sum(len(m.get("findings") or [])
               for m in (dr.get("missions") or {}).values())
    if total > _AUDIT_APPENDIX_CAP:
        return [{"check": "audit_coverage", "repairable": False,
                 "note": f"{total} استشهاداً إجمالياً يتجاوز سقف الملحق "
                        f"التقني ({_AUDIT_APPENDIX_CAP}) — يُعرَض أول "
                        f"{_AUDIT_APPENDIX_CAP} فقط، معلَناً هنا لا صامتاً"}]
    return []


# Q2 (تدقيق CAGR غير متسق، تمور/هولندا): معدّل نمو سنوي مركّب واحد قد يظهر
# برقمين مختلفين على نافذتَي سنوات مختلفتين (الملخّص «13.3% (2020-2024)»
# مقابل الحكم «16.3% (2019-2023)») بلا مصالحة. نلتقط «معدّل نمو مؤطَّر بنافذة»
# = نسبة مئوية تجاور لفظَ نموٍّ ونافذةَ سنوات ضمن الجملة نفسها.
_GROWTH_KW_RE = re.compile(r"نمو|مركّب|مركب|سنوي|CAGR|معدّل النمو|compound", re.I)
_PCT_RE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%")
_YEAR_WINDOW_RE = re.compile(r"(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}")


def _check_cagr_consistency(dr: dict) -> list[dict]:
    """اكشف أكثر من معدّل نمو سنوي مركّب بنوافذ سنوات مختلفة بلا مصالحة —
    نفس المقياس، سنوات أساس مختلفة، رقمان متعارضان. يمسح سرد الكاتب + تعليل
    الحكم + ملخّص المحلل (المصادر التي أظهرت التعارض فعلاً في البلاغ الحيّ)."""
    report_text = (dr.get("report") or {}).get("text") or ""
    verdict = dr.get("verdict") or {}
    # درس 186: العرض يسطّح ملخّص المحلل إلى `analyst.summary` — قراءة
    # `analyst.report.summary` وحدها كانت تعمي هذه القناة (إحدى ثلاث سمّتها
    # الوثيقة مصدرَ التعارض في البلاغ الحيّ). كلا الشكلين يُقرآن.
    analyst = dr.get("analyst") or {}
    analyst_summary = (analyst.get("summary")
                       or (analyst.get("report") or {}).get("summary"))
    reasoning = " ".join(str(x) for x in [
        (verdict.get("ai") or {}).get("reasoning"), verdict.get("note"),
        analyst_summary] if x)
    blob = report_text + "\n" + reasoning
    all_windows = [(m.start(), re.sub(r"\s+", "", m.group(0)))
                   for m in _YEAR_WINDOW_RE.finditer(blob)]
    # قُرب (لا تقسيم جُمَل — «.» يكسر العشري «13.3%»): لكل نسبة يجاورها لفظُ
    # نموٍّ ضمن ±45 محرفاً، نربطها بأقربِ نافذةِ سنوات إليها (أقلّ مسافة، ≤45)
    # — فلا تختطف نسبةٌ نافذةَ جملةٍ أخرى في نصٍّ قصير.
    windowed: list[tuple[str, str]] = []
    for pm in _PCT_RE.finditer(blob):
        ctx = blob[max(0, pm.start() - 45):pm.end() + 45]
        if not _GROWTH_KW_RE.search(ctx):
            continue
        near = [(abs(wp - pm.start()), w) for wp, w in all_windows
                if abs(wp - pm.start()) <= 45]
        if not near:
            continue
        windowed.append((pm.group(1), min(near)[1]))
    distinct_vals = {v for v, _ in windowed}
    distinct_wins = {w for _, w in windowed}
    if len(distinct_vals) >= 2 and len(distinct_wins) >= 2:
        pairs = "، ".join(f"{v}% ({w})" for v, w in dict.fromkeys(windowed))
        return [{
            "check": "cagr_inconsistency", "repairable": False,
            "note": ("معدّلات نمو سنوي مركّب متعارضة على نوافذ سنوات مختلفة "
                     f"بلا مصالحة: {pairs} — يجب اعتماد معدّل واحد قانوني مع "
                     "ذكر نافذته، وأيّ بديل يُذكر بنافذته صراحة")}]
    return []


# Q3 (تدقيق عملة العمود المضلِّل، تمور/هولندا): عمود «السعر/كجم بالدولار»
# يحمل قيماً باليورو مع اعتذار داخل الخليّة — وعدٌ بتحويلٍ لم يُجرَ. نكشف عمود
# عملةٍ يَعِد بعملةٍ بينما النصّ يحمل رموز عملةٍ أخرى.
_CURRENCY_LABELS = {
    "USD": re.compile(r"بالدولار|\bUSD\b|دولار"),
    "EUR": re.compile(r"باليورو|\bEUR\b|€|يورو"),
    "GBP": re.compile(r"بالجنيه|\bGBP\b|£|جنيه إسترليني"),
}


_PRICE_HEADER_CUR_RE = re.compile(
    r"السعر[^|\n]{0,20}?(بالدولار|باليورو|بالجنيه)")
_HEADER_PHRASE_TO_CUR = {"بالدولار": "USD", "باليورو": "EUR", "بالجنيه": "GBP"}


def _check_currency_label_mismatch(dr: dict) -> list[dict]:
    """اكشف عمودَ سعرٍ يَعِد بعملةٍ بينما القيم بعملةٍ أخرى (تحويل غير مُنجَز).

    البلاغ الحيّ: عنوان العمود «السعر/كجم بالدولار» بينما الخلايا يورو. البحث
    عن العملة الأخرى **يقتصر على نافذة الجدول نفسه** (من الترويسة حتى أول
    سطرٍ فارغ) — لا كامل نص التقرير: تقارير حقيقية تخلط عملات مشروعة بأقسام
    مختلفة (استيراد بالدولار دوماً §1، تجزئة بعملة الرصد §6) بلا أيّ خطأ؛
    فحصٌ على كامل النص كان يُبلِّغ تعارضاً زائفاً بين قسمين مستقلّين تماماً.
    **قابل للإصلاح** فعلياً — راجع silk_render._fix_price_column_currency_label
    (يُعنوِن العمود بالعملة المرصودة فعلاً قبل وصول النص هنا)؛ هذا الفحص
    حارس انحدار يتأكّد أنّ الإصلاح نجح فعلاً لهذه التشغيلة."""
    text = (dr.get("report") or {}).get("text") or ""
    m = _PRICE_HEADER_CUR_RE.search(text)
    if not m:
        return []
    cur = _HEADER_PHRASE_TO_CUR[m.group(1)]
    block_end = text.find("\n\n", m.end())
    block = text[m.start():block_end if block_end != -1 else len(text)]
    others = [c for c, pat in _CURRENCY_LABELS.items()
             if c != cur and pat.search(block)]
    if others:
        return [{
            "check": "currency_label_mismatch", "repairable": True,
            "note": (f"عمود السعر مُعنوَن بـ{cur} بينما جدول الأسعار نفسه يحمل "
                     f"قيماً بعملة أخرى ({'، '.join(others)}) — عنوِن العمود "
                     "بالعملة المرصودة فعلاً، ولا تَعِد بتحويلٍ لم يُجرَ")}]
    return []


# Master Prompt Part 2 §A3/§C — تناقضٌ رقميٌّ داخليّ: حقيقة في سجل الأدلة
# (findings البعثات، قيمة DataPoint خام) تخالف رقماً في متن التقرير لنفس
# المؤشر بأكثر من ٣× (المثال المكتشف: واردات 17K$ في المتن مقابل 11.88
# مليون$ في سجل الأدلة). سجل الأدلة مصدرٌ **بنيويّ** (قيمة DataPoint رقمية
# حقيقية) لا نصٌّ حرّ — فالمقارنة أضيق خطراً من CAGR/العملة (نصّ مقابل نصّ):
# طرفٌ واحد بياناتٌ مؤكَّدة. نافذة تفسيرٍ محلية (٦٠ محرفاً حول الرقم في
# المتن) تمنع علماً زائفاً حين يُفسَّر التناقض صراحةً (نفس مبدأ فئة كومتريد
# مجاورة في مدوّنة الكويت القانونية) — مطابقٌ لعقد عدم الاختلاق: كلا الرقمين
# يُحفَظان، لا يُصحَّح أحدهما صامتاً.
_RECONCILED_PHRASES = ("مؤشر سياقي", "فئة مجاورة", "فئة كومتريد مجاورة",
                       "ليس خطأً", "لا يُصلَح برقمٍ مختلَق", "تفسير التناقض",
                       "التناقض متوقَّع", "مصالحة",
                       # الصنف ١١ (المراجعة الذاتية بعد الجولة الأولى):
                       # **تمييزُ المباشر عن المرآة عقدٌ محفوظ** — تقريرٌ
                       # يُفصِح عن الفجوة صريحاً («بيانات المرآة … فجوة …
                       # لم تُحسم») يفعل بالضبط ما يُطلَب منه، فلا يُحجَب.
                       "بيانات المرآة", "المرآة", "التصريح المباشر",
                       "mirror data", "directly reported")

# الصنف ١١: **عوالمُ مختلفة لا تُقارَن** — «نصيب الفرد من الواردات 0.005
# دولار» يحمل كلمة «الواردات» فيدخل مِجَسَّ الفحص، فتُقارَن نسبةٌ للفرد
# بإجماليِّ واردات ⇒ 240,000,000× ⇒ **حجبٌ** على جملةٍ سليمة.
# و`_check_cross_universe_ratio` يعرف أصلاً أنّ «نصيب الفرد» عالمٌ آخر —
# فالمعرفةُ كانت موجودةً في البوابة ولم تبلغ هذا الفحص.
_OTHER_UNIVERSE_CTX_RE = re.compile(
    r"نصيب\s+الفرد|للفرد|لكلّ?\s+فرد|حصة\s+الفرد|متوسط\s+السعر"
    r"|سعر\s+(?:ال)?(?:وحدة|كجم|كيلو|لتر|طن|عبوة|رف|حدود)"
    r"|per\s+capita|unit\s+price|price\s+per", re.IGNORECASE)
# المرايا الإنجليزية مضمومة (صيد الفجوات ٣) — فحص تناقض الأدلة حاجب وكان
# خامداً كلياً على lang=en (شرطا «واردات» و«دولار» عربيان).
_IMPORTS_KW_RE = re.compile(r"الواردات|واردات|\bimports?\b", re.IGNORECASE)
_USD_AMOUNT_RE = re.compile(
    r"(\d[\d,.]*)\s*(مليار|مليون|ألف|الف|billion|million|thousand)?\s*"
    r"(?:دولار|(?:US\s?)?dollars?|USD)", re.IGNORECASE)
_USD_MAGNITUDE = {"مليار": 1_000_000_000, "مليون": 1_000_000,
                  "ألف": 1_000, "الف": 1_000,
                  "billion": 1_000_000_000, "million": 1_000_000,
                  "thousand": 1_000}
# مراجعة الشيفرة: مذكِّرٌ نموّ/نسبة («نمو الواردات 9% سنوياً») ليس قيمة
# استيرادٍ مطلقة بالدولار حتى لو ذُكرت كلمة «واردات» في نفس الملاحظة — قيمته
# الخام (مثال: 9) تعني نسبة مئوية لا مبلغاً، فمقارنتها برقمٍ دولاريّ في المتن
# تُنتِج نسبة تناقضٍ زائفة (false positive). يُستبعَد من سجل الأدلة هنا.
_GROWTH_RATE_NOTE_RE = re.compile(r"نمو|معدّل|معدل|CAGR|%|٪", re.I)


def _usd_amount_to_float(num_str: str, mag: str) -> "float | None":
    try:
        v = float(num_str.replace(",", ""))
    except ValueError:
        return None
    return v * _USD_MAGNITUDE.get((mag or "").lower(), 1)


# بلاغ A3 (تحليل ٧): `_USD_AMOUNT_RE` أعلاه يشترط لفظ «دولار»، بينما الكاتب
# يكتب TAM فعلاً بصيغة رمز `$` — «TAM = 61,000,000$» (عيّنة
# `samples/research_report_latest.md` سطر ٥١) و«2,090,000$» في تحليل ٧ — فأفلتت
# تلك الصيغة وبقيت بوابة A3 **صامتة** على الحالة التي بُنيت لها. المستخلِص أدناه
# يلتقط كلّ صيغةٍ يُخرِجها الكاتب: `N,NNN,NNN$` (لاحق)، `$N` (سابق)، و«N مليون
# دولار» (لفظ). لا يمسّ `_USD_AMOUNT_RE`/`_check_evidence_body_numeric_consistency`
# (نطاقٌ أضيق مقصود) — استخلاصٌ مستقلّ لبوّابتَي TAM وتباين المرآة.
_USD_TRAIL_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(مليار|مليون|ألف|الف|billion|million|thousand)?"
    r"\s*(?:دولار|\$|(?:US\s?)?dollars?|USD)", re.IGNORECASE)
_USD_LEAD_RE = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*"
    r"(مليار|مليون|ألف|الف|billion|million|thousand)?", re.IGNORECASE)


# حدُّ «تطابقٍ شبهِ تامّ» — تحته يغلب التقريبُ وبترُ الوحدات، فلا يُبلَّغ.
# قابلٌ للضبط بيئياً كبقية عتبات البوابة (`SILK_NEAR_MATCH_RATIO`).
_NUMERIC_NEAR_MATCH = float(
    os.environ.get("SILK_NEAR_MATCH_RATIO", "").strip() or 1.10)


def _iter_usd_amounts(text: str) -> list[tuple[int, int, float]]:
    """كلّ مبلغٍ دولاريّ في المتن بأيّ صيغة — قائمة (بداية، نهاية، قيمة).
    يشمل `$`-اللاحقة (`61,000,000$`)، و`$`-السابقة (`$61`)، واللفظية (`61 مليون
    دولار`/`17000 دولار`) — لا صيغةً واحدة كما كان الاشتراط القديم."""
    spans: list[tuple[int, int, float]] = []
    for m in _USD_TRAIL_RE.finditer(text or ""):
        v = _usd_amount_to_float(m.group(1), m.group(2) or "")
        if v is not None and v > 0:
            spans.append((m.start(), m.end(), v))
    for m in _USD_LEAD_RE.finditer(text or ""):
        v = _usd_amount_to_float(m.group(1), m.group(2) or "")
        if v is None or v <= 0:
            continue
        if any(a <= m.start() < b for a, b, _ in spans):
            continue   # لا تُكرِّر مبلغاً التقطته الصيغة اللاحقة
        spans.append((m.start(), m.end(), v))
    spans.sort()
    return spans


def _fmt_gate_num(v: object) -> str:
    """رقمٌ في بلاغِ البوابة عبر المُنسِّق الواحد (الصنف ٣).

    الصنف ١١ (ج): `{v:,.0f}` كان يطبع «0$» لمبلغٍ دون الوحدة (0.005) —
    فيقرأ المشغّلُ بلاغاً بلا معنى عن رقمٍ موجود. البلاغُ سطحُ قراءةٍ أيضاً.
    """
    from silk_narrative import fmt_number
    return fmt_number(v)


def _check_evidence_body_numeric_consistency(dr: dict) -> list[dict]:
    """قارن قيمة الواردات المسجَّلة في سجل الأدلة (DataPoint خام في findings
    البعثات) برقم الواردات المذكور في متن التقرير — تعارضٌ حقيقي (>٣×) بلا
    تفسيرٍ في نافذة محلية حول الرقم (لا كامل النص) => FAIL."""
    text = (dr.get("report") or {}).get("text") or ""
    if not text:
        return []
    evidence_values = []
    for m in (dr.get("missions") or {}).values():
        for f in (m.get("findings") or []):
            v = f.get("value")
            note = str(f.get("note") or "")
            if isinstance(v, (int, float)) and not isinstance(v, bool) \
                    and _IMPORTS_KW_RE.search(note) \
                    and not _GROWTH_RATE_NOTE_RE.search(note):
                evidence_values.append(float(v))
    if not evidence_values:
        return []
    findings = []
    seen_pairs = set()
    for pm in _USD_AMOUNT_RE.finditer(text):
        ctx = text[max(0, pm.start() - 60):pm.end() + 60]
        if not _IMPORTS_KW_RE.search(ctx):
            continue
        amt = _usd_amount_to_float(pm.group(1), pm.group(2) or "")
        if amt is None or amt <= 0:
            continue
        if any(p in ctx for p in _RECONCILED_PHRASES):
            continue
        # الصنف ١١ (أ): عالمٌ آخر لا يُقارَن بإجماليٍّ.
        if _OTHER_UNIVERSE_CTX_RE.search(ctx):
            continue
        # الصنف ١١ (ب): **رقمٌ مسنودٌ في الأدلة ليس تناقضاً** — حين يحمل
        # السجلُّ قراءتين مشروعتين لمؤشرٍ واحد (تصريحٌ مباشر + مرآة)، كانت
        # الحلقةُ تقارن قراءةَ المتن بالقراءةِ **الأخرى** فتُفشِل تقريراً
        # صحيحاً. وذكرُ قراءتين بلا تمييزٍ عيبٌ حقيقيّ لكنه من عائلةِ
        # **الصنف ٦** (قيمتان لمؤشرٍ واحد) لا من عائلةِ الرقمِ غيرِ المسنود
        # التي يحرسها هذا الفحص — فحصان لعيبٍ واحدٍ يُضاعِفان الحجبَ ولا
        # يزيدان تغطية.
        if any(abs(amt - ev) <= abs(ev) * (_NUMERIC_NEAR_MATCH - 1.0)
               for ev in evidence_values if ev):
            continue
        for ev in evidence_values:
            if ev <= 0:
                continue
            ratio = max(ev, amt) / min(ev, amt)
            # **الموجة C (البند X-02).** كان الكشفُ شريحتين منفصلتين: تطابقٌ
            # شبهُ تامّ يمرّ، وتناقضٌ فاحش (>٣×) يحجب. وبينهما — حيث يعيش
            # **أخطرُ تعارضٍ حقيقيّ** — لا كشفَ إطلاقاً: رقمان يختلفان ٢٫٥×
            # لنفس المؤشر يصلان العميلَ في وثيقةٍ واحدة بلا كلمة.
            #
            # الشريحةُ الوسطى **تحذيريّة لا حاجبة** عمداً: لها أسبابٌ مشروعة
            # (سنةٌ مختلفة، تجميعٌ مختلف)، وحجبُ تقريرٍ صحيحٍ لأجلها ضررٌ لا
            # نفع. والحاجزُ عند ٣× يبقى كما هو حرفياً — تكافؤٌ رجعيّ.
            if ratio <= _NUMERIC_NEAR_MATCH:
                continue
            key = (round(ev), round(amt))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if ratio > 3:
                findings.append({
                    "check": "evidence_body_numeric_contradiction",
                    "repairable": False,
                    "note": (f"تناقضٌ رقميٌّ داخليّ: سجل الأدلة يسجّل قيمة "
                             f"واردات {_fmt_gate_num(ev)}$ بينما متن التقرير "
                             f"يذكر {_fmt_gate_num(amt)}$ لنفس المؤشر "
                             f"(نسبة {ratio:.1f}× "
                             "> 3×) بلا تفسيرٍ مجاور — يجب التصالح أو "
                             "التفسير الصريح قبل التسليم")})
            else:
                findings.append({
                    "check": "evidence_body_numeric_divergence",
                    "repairable": True,
                    "note": (f"رقمان مختلفان لنفس المؤشر: سجل الأدلة "
                             f"{_fmt_gate_num(ev)}$ والمتن "
                             f"{_fmt_gate_num(amt)}$ (فرق "
                             f"{ratio:.2f}×). قد يكون الفرق مشروعاً (سنة "
                             "أخرى أو تجميع مختلف) — اذكر أيّهما تقصد "
                             "وسببَ الفرق، أو وحّدهما")})
            break
    return findings


# PR A §A3 (بلاغ تحليل ٧): TAM أصغر من تدفّق دولة واحدة — §3.1 يضع TAM =
# 2.09M بينما يذكر تدفّق السعودية وحدها 22.14M لنفس السوق/السنة. TAM (إجمالي
# واردات السوق) يجب أن يكون ≥ تدفّق أيّ دولةٍ واحدة إليه تعريفاً؛ تدفّقٌ مفردٌ
# يتجاوز TAM المذكورة = تعارضٌ منطقيّ (تباين منظور استيراد↔تصدير المرآة، أو
# رمز HS ضيّق) — تعارضٌ حاجب يجب تفسيره/تصحيحه قبل التسليم. فحصٌ نصّيّ (يعمل
# على تقريرٍ مخزَّن/مُعاد التوليد) لا يعتمد على شكل حقلٍ بعينه.
_TAM_MARKER_RE = re.compile(
    r"TAM|إجمالي\s+(?:ال)?واردات|حجم\s+السوق|السوق\s+الكلّ?ي|الطلب\s+الكلّ?ي")
# المرايا الإنجليزية مضمومة (صيد الفجوات ٣) — بوابتا TAM/تباين المرآة
# حاجبتان وكانتا خامدتين كلياً على lang=en (مستخلص `$` محايد لغوياً أصلاً؛
# الخمود كان في فعل التدفق والدولة المفردة حصراً).
_FLOW_VERB_RE = re.compile(
    r"صادرات|تصدير|يصدّر|تصدّر|تدفّق|واردات\s+من|"
    r"exports?|exported|imports\s+from|shipments?\s+from", re.IGNORECASE)
_SINGLE_COUNTRY_RE = re.compile(
    r"وحده|وحدها|دولة\s+واحدة|مورّد\s+واحد|شريك\s+واحد|السعودية|سعودي|"
    r"\balone\b|single\s+(?:country|supplier|partner)|one\s+country|"
    r"Saudi", re.IGNORECASE)


def _marker_min_dist(text: str, start: int, end: int, rex, lo: int,
                     hi: int) -> "int | None":
    """أقصرُ مسافةٍ من مدى الرقم [start,end] إلى أيّ تطابقٍ لـrex ضمن [lo,hi]؛
    None إن لا تطابق (يُستعمَل لنسبِ رقمٍ للمؤشّر الأقرب حين يتجاور رقمان)."""
    best: "int | None" = None
    for m in rex.finditer(text[lo:hi]):
        ms, me = m.start() + lo, m.end() + lo
        d = 0 if (ms <= end and me >= start) else min(abs(ms - end),
                                                      abs(start - me))
        best = d if best is None else min(best, d)
    return best


def _classify_market_amounts(text: str) -> tuple[list[float], list[float]]:
    """صنّف كلّ مبلغٍ دولاريّ في المتن (بأيّ صيغة، عبر `_iter_usd_amounts`) إلى:
       - tam_amounts: مبلغٌ مجاورٌ لمؤشّر إجماليِّ سوقٍ (TAM/إجمالي واردات/حجم
         السوق) ضمن نافذة ±٧٠ محرفاً.
       - flow_amounts: مبلغٌ مجاورٌ لفعل تدفّق **و**دولةٍ واحدة (صادرات … السعودية
         وحدها) — تدفّق دولةٍ مفردةٍ/مرآةٍ.
    حين يجتمع مؤشّرا TAM والتدفّق في نافذة رقمٍ واحد (رقمان متجاوران في نفس
    الجملة)، يُنسَب الرقم للمؤشّر **الأقرب** إليه لا بأولويّةٍ ثابتة — كي لا
    تُختطَف قيمةُ تدفّقٍ مفردٍ إلى دلوِ TAM لمجرّد أنّ لفظ TAM في المدى.
    مستخلَصٌ واحد يُغذّي بوابة A3 (تعارضٌ منطقيّ: TAM < تدفّق مفرد) وبوابة تباين
    المرآة (سرد الانكماش) — مصدر تصنيفٍ واحد لا نسختان."""
    tam_amounts: list[float] = []
    flow_amounts: list[float] = []
    for start, end, amt in _iter_usd_amounts(text):
        lo, hi = max(0, start - 70), end + 70
        ctx = text[lo:hi]
        tam_hit = bool(_TAM_MARKER_RE.search(ctx))
        flow_hit = bool(_FLOW_VERB_RE.search(ctx)) and \
            bool(_SINGLE_COUNTRY_RE.search(ctx))
        if tam_hit and not flow_hit:
            tam_amounts.append(amt)
        elif flow_hit and not tam_hit:
            flow_amounts.append(amt)
        elif tam_hit and flow_hit:
            td = _marker_min_dist(text, start, end, _TAM_MARKER_RE, lo, hi)
            fds = [d for d in (
                _marker_min_dist(text, start, end, _FLOW_VERB_RE, lo, hi),
                _marker_min_dist(text, start, end, _SINGLE_COUNTRY_RE, lo, hi))
                if d is not None]
            fd = min(fds) if fds else None
            if td is not None and (fd is None or td <= fd):
                tam_amounts.append(amt)
            else:
                flow_amounts.append(amt)
    return tam_amounts, flow_amounts


def _check_tam_below_single_country_flow(dr: dict) -> list[dict]:
    """PR A §A3 — TAM مذكورة أصغر من تدفّق دولةٍ واحدة مذكور لنفس السوق."""
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    tam_amounts, flow_amounts = _classify_market_amounts(text)
    if not tam_amounts or not flow_amounts:
        return []
    tam = min(tam_amounts)                 # أصغر إجماليٍّ مذكور (الأكثر تحفّظاً)
    worst = max((f for f in flow_amounts if f > tam), default=None)
    if worst is None:
        return []
    return [{"check": "tam_below_single_country_flow", "repairable": False,
             "note": (f"إجمالي واردات السوق المذكور (TAM ≈ {tam:,.0f}$) أصغر "
                      f"من تدفّق دولةٍ واحدة مذكور لنفس السوق ({worst:,.0f}$) "
                      "— مستحيلٌ منطقياً (تدفّق دولةٍ واحدة ≤ إجمالي الواردات "
                      "دائماً). راجع منظور المصدر (استيراد↔مرآة تصدير) وصحّة "
                      "رمز HS، وفسّر التباين صراحةً أو صحّحه قبل التسليم")}]


# P0 (بلاغ تحليل ٧ — سردُ تباين المرآة): «انكماش ‑22.08% CAGR» محسوبٌ من سلسلة
# تصريح اليمن الجمركية التي انهار تسجيلها، ويقود السرد (تهديد رئيسي/ضعف SWOT/
# «الحفاظ على حصة في مواجهة انكماش الحجم») بينما تدفّق المرآة (تصدير السعودية
# 22.14M) يفوق التصريح المُعلَن (2.09M) ×١٠. القاعدة الكتابية: حين يفوق تدفّق
# المرآة التصريحَ مادّياً، تُعرَض القيمتان معاً، وتُسمّى المفارقة صراحةً، ولا
# يُقاد السرد بانكماشٍ مبنيٍّ على الرقم الأدنى. بوابةٌ حاجبة تُفشِل حين يجتمع
# (أ) تدفّق مرآةٍ مفردٍ يفوق إجمالي السوق المُعلَن، (ب) سردُ انكماشٍ **مؤطَّرٌ
# تهديداً/ضعفاً** (قيادةً به لا تذييلاً)، دون (ج) مصالحةٍ صريحة تسمّي أنّ
# المرآة تفوق التصريح وتعتمدها بديلاً (لا تلميح «ضعف التسجيل» عابراً وحده).
_CONTRACTION_RE = re.compile(
    r"انكماش|تقلّص|تقلص|تراجع\s+الحجم|[‑–—−-]\s*\d{1,2}(?:[.,]\d+)?\s*%|"
    r"contraction|shrink|declin", re.IGNORECASE)
_THREAT_FRAME_RE = re.compile(
    r"تهديد|التهديد|نقطة\s+الضعف|نقطة\s+ضعف|الضعف\b|التحدّي|التحدي|مواجهة|"
    r"\bthreat|\bweakness|\bchallenge", re.IGNORECASE)
# مصالحةٌ صريحة: سطرٌ يجمع منظور المرآة/التصدير بفعل اعتمادٍ/تفوّقٍ صريح — لا
# مجرّد ذكرٍ عابرٍ لـ«المرآة» ولا تلميح «ضعف التسجيل» وحده (القاعدة: قِد بالمصالحة
# لا بالانكماش). نافذةٌ قصيرة (≤٨٠ محرفاً) كي لا تقفز جملةً كاملة.
_MIRROR_RECONCILED_RE = re.compile(
    r"(?:المرآة|تصدير\s+المُصدِّر|تصدير\s+الشريك|منظور\s+التصدير)"
    r"[^\n]{0,80}?(?:يفوق|تفوق|أعلى|أكبر|نعتمد|البديل|الأقرب|الأدقّ|الأدق)|"
    r"mirror[^\n]{0,80}?(?:exceeds?|higher|larger|adopted|preferred|"
    r"more\s+reliable)", re.IGNORECASE)


def _check_mirror_divergence_contraction_narrative(dr: dict) -> list[dict]:
    """P0 (تحليل ٧) — سردُ انكماشٍ مؤطَّرٌ تهديداً بينما تدفّق المرآة يفوق
    التصريح المُعلَن، دون تسمية المفارقة/مصالحتها = عيبٌ حاجب. السوق قد لا
    ينكمش؛ التسجيل قد يكون هو الذي انهار — فلا يُقاد السرد بالسلسلة الأدنى."""
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    tam_amounts, flow_amounts = _classify_market_amounts(text)
    if not tam_amounts or not flow_amounts:
        return []
    total = min(tam_amounts)
    mirror = max((f for f in flow_amounts if f > total), default=None)
    if mirror is None:
        return []
    # (ب) قيادةٌ بالانكماش: انكماش/‑CAGR متجاورٌ لتأطير تهديدٍ/ضعفٍ (±١٢٠ محرفاً).
    led_by_contraction = any(
        _THREAT_FRAME_RE.search(text[max(0, cm.start() - 120):cm.end() + 120])
        for cm in _CONTRACTION_RE.finditer(text))
    if not led_by_contraction:
        return []
    # (ج) مصالحةٌ صريحة للمفارقة تُلغي القيادةَ بالأدنى — لا تُفشِل حينها.
    if _MIRROR_RECONCILED_RE.search(text):
        return []
    ratio = mirror / total if total else 0
    return [{"check": "mirror_divergence_contraction_narrative",
             "repairable": False,
             "note": (f"سردُ انكماشٍ (‑CAGR/«انكماش») مؤطَّرٌ تهديداً/ضعفاً بينما "
                      f"تدفّق المرآة (تصدير الشريك ≈ {mirror:,.0f}$) يفوق إجمالي "
                      f"السوق المُعلَن ({total:,.0f}$) بنحو {ratio:.0f}× — الانكماش "
                      "محسوبٌ من سلسلة تصريحٍ ضعيفةِ التسجيل. اعرض القيمتين معاً "
                      "وسمِّ مفارقة المرآة صراحةً، ولا تَقُد السرد بانكماشٍ مبنيٍّ "
                      "على الرقم الأدنى قبل مصالحة المنظورَين")}]


# تصعيدُ التقادُم (بلاغ تحليل ٧ — قاعدةٌ إضافية): آلية `silk_staleness` **تُوسِم**
# السنوات المتقادِمة (>٥ سنوات) لكنها لا تُفشِل. حين تقود سنةٌ متقادِمة استنتاجاً
# **مذكوراً** — دخل الفرد 2018 وPPP 2013 مدخلَين لاستنتاج «القدرة الشرائية تقيّد
# التسعير» — يجب أن تُفشِل لا أن تُوسَم فقط. نربط سنةً متقادِمةً (من الحقائق ذات
# القيم عبر `data_year` البنيويّ، لا نثراً) بلغةِ استنتاجٍ قوّةٍ شرائية↔تسعير في
# نافذةٍ محلية — فلا يُعلَم على ذكرٍ عابرٍ لسنةٍ قديمة بلا استنتاجٍ مبنيٍّ عليها.
_PURCHASING_POWER_RE = re.compile(
    r"القدرة\s+الشرائية|القوّة\s+الشرائية|القوة\s+الشرائية|تعادل\s+القوة|\bPPP\b")
_PRICING_CONCLUSION_RE = re.compile(
    r"تسعير|التسعير|السعر|الأسعار|تقيّد|تقيد|تحدّ|يحدّ|يقيّد")


def _stale_years_in_view(dr: dict) -> set:
    """سنوات الحقائق المتقادِمة (ذات القيم) عبر بعثات + تقاطعات المحلل — من
    الحقل البنيويّ `data_year` لا من نثر التقرير (`silk_staleness`)."""
    from silk_staleness import stale_fact_years
    findings: list = []
    for m in (dr.get("missions") or {}).values():
        findings.extend((m or {}).get("findings") or [])
    for dps in ((dr.get("analyst") or {}).get("by_category") or {}).values():
        findings.extend(dps or [])
    return stale_fact_years(findings)


def _check_stale_year_driving_conclusion(dr: dict) -> list[dict]:
    """تصعيدُ التقادُم — سنةُ حقيقةٍ أقدم من ٥ سنوات تقود استنتاجاً تسعيرياً
    مذكوراً (قوّة شرائية↔تسعير) = فشلٌ حاجب، لا مجرّد وسمٍ «الأحدث المتاح»."""
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    stale = _stale_years_in_view(dr)
    if not stale:
        return []
    findings: list[dict] = []
    for yr in sorted(stale):
        for m in re.finditer(rf"(?<!\d){yr}(?!\d)", text):
            win = text[max(0, m.start() - 160):m.end() + 160]
            if _PURCHASING_POWER_RE.search(win) and _PRICING_CONCLUSION_RE.search(win):
                findings.append({
                    "check": "stale_year_driving_conclusion", "repairable": False,
                    "note": (f"سنةُ بياناتٍ متقادِمة ({yr}، أقدم من ٥ سنوات) تقود "
                             "استنتاجاً مذكوراً (القدرة الشرائية تقيّد التسعير) — "
                             "بياناتٌ بهذا القِدَم لا تصلح مدخلاً حاضراً لاستنتاجٍ "
                             "تسعيريّ؛ حدِّثها أو أعلن الفجوة صراحةً، لا تُوسَم فقط")})
                break   # بندٌ واحد لكلّ سنة متقادِمة قائدة
    return findings


# بلاغ المالك (تحليل ٧ — مِجَسّ /trend الحيّ): سلسلةُ واردات اليمن السنوية
# 2018=$0.88M، 2019=$5.59M (ذروة)، 2023=$2.09M (2020–2022 بلا بيانات — انهيارُ
# التسجيل). التقريرُ ثبّت الأساسَ على ذروة 2019 فأنتج «‑22.08% انكماش»، بينما
# التثبيت على 2018 (أوّل سنةٍ مرصودة) يعطي +18.9% **نموّاً**. اختيارُ سنة الأساس
# **قلب الإشارة** فانهار سردُ «السوق المنكمش» كلّه (تهديد الغلاف/ضعف SWOT).
# القاعدة (أمر المالك): ادّعاءُ نموّ/انكماشٍ تنقلب إشارتُه بتغيير سنة الأساس
# المرصودة ضمن السلسلة نفسها = عيبٌ حاجب. حتميّ: نقرأ السلسلة من نقاط البعثات
# (كلّ سنة DataPoint من comtrade_imports بـdata_year) لا من نثر التقرير.
_DIRECTIONAL_CLAIM_RE = re.compile(
    r"انكماش|تقلّص|تقلص|نموّ|نمو|CAGR|معدّل\s+النمو|معدل\s+النمو|تراجع|توسّع|توسع")
# إفصاحٌ صحيح (§3.6): تقريرٌ يذكر «سنة الأساس» صراحةً أو يصرّح أنّ الاتجاه غير
# محسومٍ لحساسيته لسنة الأساس لم يُخفِ شيئاً — القاعدة تُفشِل التثبيتَ المُختار
# الصامت لا الإفصاحَ عن الحساسية. لا يُسكِت تحليل ٧ (لا يذكر «سنة الأساس»).
_BASE_YEAR_DISCLOSED_RE = re.compile(
    r"سنة\s+الأساس|سنةِ\s+الأساس|سنتَي\s+الأساس|حساسية[^.\n]{0,30}الأساس|"
    r"اعتماداً\s+على\s+سنة\s+الأساس|غير\s+محسوم[^.\n]{0,40}الأساس|"
    # صيد الفجوات ٣: الموجّه 3.8 يأمر بالإفصاح بلغة التقرير — إعفاءٌ عربيّ
    # المِجَسّ وحدَه كان يعاقِب الإفصاحَ الإنجليزيَّ الصحيح FAIL.
    r"base[- ]?year", re.IGNORECASE)
_IMPORT_TOTAL_NOTE_RE = re.compile(r"استيراد|واردات")
_NON_TOTAL_NOTE_RE = re.compile(r"سعر|الوزن|كميات|وحدة|price", re.I)


def _annual_import_series(dr: dict) -> dict:
    """سلسلةُ واردات السوق السنوية {سنة: قيمة} من نقاط البعثات — إجماليّاتُ
    الاستيراد فقط (لا أسعار/كميات)، بـ`data_year` بنيويّ. تشمل تقديرات المرآة
    (status=mirrored) فهي واردات أيضاً. لا تحليلَ نثر — قراءةٌ بنيوية."""
    series: dict = {}
    for m in (dr.get("missions") or {}).values():
        for f in ((m or {}).get("findings") or []):
            v = f.get("value")
            y = f.get("data_year")
            note = str(f.get("note") or "")
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            if v <= 0 or not isinstance(y, int) or isinstance(y, bool):
                continue
            if not _IMPORT_TOTAL_NOTE_RE.search(note) \
                    or _NON_TOTAL_NOTE_RE.search(note):
                continue
            series[y] = float(v)   # آخر قيمةٍ لكلّ سنة إن تكرّرت
    return series


def _check_cagr_sign_flips_under_base_year(dr: dict) -> list[dict]:
    """بلاغ المالك — إشارةُ معدّل النمو المركّب تنقلب بتغيير سنة الأساس المرصودة
    في السلسلة نفسها (2018→نموّ مقابل 2019→انكماش، نفس النهاية 2023). ادّعاءُ
    اتجاهٍ واحد على سلسلةٍ كهذه يُشكِّك السردَ كلّه — عيبٌ حاجب."""
    text = ((dr.get("report") or {}).get("text") or "")
    if not text or not _DIRECTIONAL_CLAIM_RE.search(text):
        return []                       # لا ادّعاءَ اتجاهٍ في المتن — لا قلب
    if _BASE_YEAR_DISCLOSED_RE.search(text):
        return []                       # أفصح عن حساسية سنة الأساس (§3.6) — لا عقاب
    series = _annual_import_series(dr)
    if len(series) < 3:
        return []                       # نحتاج ≥٣ سنوات مرصودة لتظهر الحساسية
    years = sorted(series)
    last_y, last_v = years[-1], series[years[-1]]
    pos: list = []
    neg: list = []
    for b in years[:-1]:
        span = last_y - b
        if span <= 0:
            continue
        cagr = (last_v / series[b]) ** (1.0 / span) - 1.0
        (pos if cagr > 0 else neg if cagr < 0 else []).append((b, cagr))
    if not pos or not neg:
        return []                       # الإشارة ثابتة عبر كلّ الأسس — لا قلب
    bp, cp = max(pos, key=lambda t: t[1])   # أقوى نموّ
    bn, cn = min(neg, key=lambda t: t[1])   # أقوى انكماش
    return [{"check": "cagr_sign_flips_under_base_year", "repairable": False,
             "note": (f"إشارةُ معدّل النمو المركّب تنقلب بتغيير سنة الأساس "
                      f"المرصودة في السلسلة نفسها: أساس {bp} = {cp*100:+.1f}% "
                      f"(نموّ) مقابل أساس {bn} = {cn*100:+.1f}% (انكماش)، "
                      f"والنهايةُ {last_y}. لا يجوز بناءُ حكم/تهديدٍ على اتجاهٍ "
                      "واحدٍ مختار — ثبِّت الأساسَ على أوّل سنةٍ مرصودة، أو "
                      "اعرض كلا القراءتين صراحةً")}]


# PR B §B3 (بلاغ تحليل ٧): تلوّثُ العملة — §3.9 اقتبس سعراً بالريال العُماني
# داخل دراسةِ اليمن. الأسعار تُعرَض بالدولار (عملة الإبلاغ) أو بعملة السوق
# المرصودة؛ عملةُ دولةٍ **أخرى** (خليجية/إقليمية) في متن التقرير = تلوّثٌ
# مضلِّل. خريطةٌ محدودةٌ لأسماء العملات العربية المميِّزة → الدولة (لا «ريال»
# وحدها — مشتركةٌ بين SAR/QAR/YER/OMR؛ ولا «دينار» وحدها). USD/EUR/GBP عملاتُ
# إبلاغٍ عالمية لا تُبلَّغ. يُفحَص فقط حين تكون دولةُ السوق معروفة (لا إيجاب كاذب).
_CURRENCY_COUNTRY_PHRASES = {
    "ريال عماني": "OMN", "ريال قطري": "QAT", "ريال سعودي": "SAU",
    "ريال يمني": "YEM", "دينار كويتي": "KWT", "دينار بحريني": "BHR",
    "درهم إماراتي": "ARE", "درهم مغربي": "MAR", "دينار أردني": "JOR",
    "جنيه مصري": "EGY", "دينار عراقي": "IRQ", "ليرة تركية": "TUR",
    "دينار جزائري": "DZA", "دينار تونسي": "TUN", "دينار ليبي": "LBY",
    "ريال إيراني": "IRN", "ليرة لبنانية": "LBN",
}
# المرآة الإنجليزية (صيد الفجوات ٣) — نفس الخريطة المحدودة، مطابقة lowercase
# مع جمع اختياري («Omani rials»). USD/EUR/GBP عملات إبلاغ عالمية لا تُبلَّغ.
_CURRENCY_COUNTRY_PHRASES_EN = {
    "omani rial": "OMN", "qatari riyal": "QAT", "saudi riyal": "SAU",
    "yemeni rial": "YEM", "kuwaiti dinar": "KWT", "bahraini dinar": "BHR",
    "emirati dirham": "ARE", "uae dirham": "ARE", "moroccan dirham": "MAR",
    "jordanian dinar": "JOR", "egyptian pound": "EGY", "iraqi dinar": "IRQ",
    "turkish lira": "TUR", "algerian dinar": "DZA", "tunisian dinar": "TUN",
    "libyan dinar": "LBY", "iranian rial": "IRN", "lebanese pound": "LBN",
}
# مزيل التشكيل — `_norm_ar` لا يمسّ الحركات، والعبارة المشكولة كانت تفلت.
_AR_DIACRITICS_RE = re.compile("[ً-ْٰ]")


# PR B §B5 (بلاغ تحليل ٧): بعثة «demand_trends» تُبلَّغ «مكتملة» (`failed=not
# findings` تَعُدّ أيّ نتيجة من أدواتها الأربع نجاحاً — faostat/openalex يُغطّيان
# غياب Trends)، بينما §3.3/§6 يعلنان بيانات Trends/الموسمية مفقودةً فتبقى ذروة
# رمضان مجهولة. «بعثةٌ بلا بيانات صالحة لغرضها لا تُعَدّ مكتملة»: نُبرِز التناقض
# ملاحظةً منهجية (لا حكماً حاجباً — كـagent_empty) حين تُعلن البعثةُ نفسها في
# ملخّصها فجوةَ الاتجاهات/الموسمية رغم عدم فشلها.
_TRENDS_GAP_RE = re.compile(
    r"(?:اتجاهات|Trends|تريندز|موسمي|رمضان|seasonal)", re.I)


def _check_trends_hollow_completion(dr: dict) -> list[dict]:
    """PR B §B5 — بعثةُ الاتجاهات/الطلب «مكتملة» لكنها تُعلن فجوةَ الاتجاهات/
    الموسمية في ملخّصها نفسه (بياناتها الأساسية غائبة) — تُبرَز لا تُخفى."""
    findings = []
    for key, m in (dr.get("missions") or {}).items():
        if not isinstance(m, dict):
            continue
        if "trend" not in key and "demand" not in key:
            continue
        if m.get("failed"):
            continue   # فشلٌ صريح محكومٌ أصلاً (agent_failed)
        summary = str(m.get("summary") or "")
        gm = _GAPS_TRIGGER_RE.search(summary) or ("فجوات" in summary)
        if gm and _TRENDS_GAP_RE.search(summary):
            findings.append({
                "check": "trends_hollow_completion", "repairable": False,
                "note": (f"بعثةُ «{_mission_label(key)}» مُبلَّغةٌ غيرَ فاشلة "
                         "لكنها تُعلن فجوةَ بيانات الاتجاهات/الموسمية في "
                         "ملخّصها — لم تُنتِج بياناتٍ صالحةً لغرضها الأساسي "
                         "(موسمية/ذروة الطلب)؛ تُقرأ كتغطيةٍ ناقصة لا اكتمالاً")})
    return findings


def _check_off_market_currency(dr: dict) -> list[dict]:
    """PR B §B3 — عملةُ دولةٍ غير سوق الدراسة (وليست عملةَ إبلاغٍ عالمية)
    مذكورةٌ في متن التقرير = تلوّثُ عملةٍ مضلِّل يجب تصحيحه قبل التسليم."""
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    market = dr.get("market") or {}
    market_iso3 = str(market.get("iso3") or "").upper()
    if not market_iso3:
        return []   # سوق مجهول — لا فحص (تفادي إيجاب كاذب)
    findings = []
    seen: set[str] = set()
    # صيد الفجوات ٣: المطابقة الخام (`phrase in text`) كانت تُهزَم بأل
    # التعريف والتشكيل — نصُّ حادثة §B3 الأصلية نفسُه («بالريال العُماني»)
    # كان يفلت. تُطبَّع الكومةُ والإبرةُ معاً (قاعدة المُطبِّع الواحد) مع
    # قبول «ال» على كلمات العبارة، وتُضاف مرآةٌ إنجليزية (الفحص حاجب).
    norm_text = _AR_DIACRITICS_RE.sub("", _norm_ar(text))
    low_text = text.lower()
    for phrase, iso3 in _CURRENCY_COUNTRY_PHRASES.items():
        if iso3 == market_iso3:
            continue   # عملةُ السوق نفسها مشروعة (رصدٌ محليّ)
        words = _norm_ar(phrase).split()
        pat = r"\s+".join(r"(?:ال)?" + re.escape(w) for w in words)
        if re.search(pat, norm_text) and phrase not in seen:
            seen.add(phrase)
            findings.append({
                "check": "off_market_currency", "repairable": False,
                "note": (f"عملةٌ خارج السوق «{phrase}» ({iso3}) مذكورةٌ في "
                         f"دراسةِ سوقٍ مختلف ({market_iso3}) — الأسعار تُعرَض "
                         "بالدولار أو بعملة السوق المرصودة؛ صحّح العملة "
                         "المتسرّبة قبل التسليم")})
    for phrase, iso3 in _CURRENCY_COUNTRY_PHRASES_EN.items():
        if iso3 == market_iso3:
            continue
        if re.search(re.escape(phrase) + r"s?\b", low_text) \
                and phrase not in seen:
            seen.add(phrase)
            findings.append({
                "check": "off_market_currency", "repairable": False,
                "note": (f"عملةٌ خارج السوق «{phrase}» ({iso3}) مذكورةٌ في "
                         f"دراسةِ سوقٍ مختلف ({market_iso3}) — الأسعار تُعرَض "
                         "بالدولار أو بعملة السوق المرصودة؛ صحّح العملة "
                         "المتسرّبة قبل التسليم")})
    return findings


# Master Prompt Part 2 §D — تغطية المصادر: كل مؤشرٍ يحمل مصدراً مسمّى
# حقيقياً أو وسم «تقدير استرشادي» صريح؛ عتبة القبول ≥٨٥٪. دون العتبة =
# ضيّق نطاق التقرير وأعلن الفجوة، لا تشحن مؤشرات بلا مصدر (البند ٩).
def _check_source_coverage(dr: dict) -> list[dict]:
    from silk_source_coverage import compute_source_coverage, SOURCE_COVERAGE_MIN_PCT
    cov = compute_source_coverage(dr)
    if cov["total"] == 0:
        # **الموجة B (البند T-01).** كان صفرُ المؤشّرات يعيد `[]` — أي أنّ
        # تقريراً بلا **أيّ** دليلٍ مرصود يمرّ من أقوى حارسِ إسنادٍ معلَن،
        # وهي بالضبط الحالةُ المتدهورة التي يحتاجه فيها العميل. صفرُ أدلةٍ
        # ليس تغطيةً كاملة؛ إنه غيابُ أساسِ التقرير نفسِه.
        return [{
            "check": "source_coverage_below_threshold", "repairable": False,
            "note": ("لا مؤشّر واحد بقيمةٍ مرصودة في سجلّ الأدلة — لا أساس "
                     "مُسنَد لهذا التقرير. تُعلَن الفجوة ولا يُسلَّم سردٌ "
                     "رقميٌّ بلا دليل")}]
    if cov["pct"] >= SOURCE_COVERAGE_MIN_PCT:
        return []
    return [{
        "check": "source_coverage_below_threshold", "repairable": False,
        "note": (f"تغطية المصادر {cov['pct']:.0f}% ({cov['backed']}/"
                 f"{cov['total']} مؤشراً بمصدرٍ مسمّى) دون عتبة القبول "
                 f"{SOURCE_COVERAGE_MIN_PCT:.0f}% — ضيّق نطاق التقرير أو "
                 "أعلن الفجوة صراحةً بدل شحن مؤشرات بلا مصدرٍ مسمّى")}]


# سدّ تسريب (الطبقة ٧ — مفارقة البوابة): هذه الفحوصات مُعلَّمة repairable=True
# لأن *صنف* النتيجة يُصلَح عادة في طبقة العرض قبل أن يصل النص هنا (راجع تعليق
# الوحدة) — لكن حين تُطلِق أحدها فعلياً، فهذا يعني أن الإصلاح **فشل تحديداً في
# هذه التشغيلة**، والنص الخام وصل بالفعل إلى DOCX المُسلَّم قبل تشغيل البوابة
# (api.py._attach_quality_gate تُشغَّل بعد بناء العرض لا قبله). تخفيضها بصمت
# إلى WARN يعني أن البوابة تكتشف تسريباً فعلياً ثم تكتمه — لا يجوز أن يمرّ بحكم
# أهدأ من فشل بنيوي حقيقي (section_structure/agent_failed). ثابتٌ على مستوى
# الوحدة كي تُثبِّته الاختبارات (عقد تصعيد §8: …_excess داخله، WARN خارجه).
_REGRESSION_GUARD_FIRED = {"min_pillars_scored", "competition_unit_valid",
                           "retail_unit_mismatch", "retail_price_presence_conflict",
                           "pillar_narrative_sync",
                           "hs_recommendation_match",
                           "derived_number_has_inputs",
                           "pricing_contradiction_flagged",
                           "verdict_evidence_direction",
                           "verdict_label_matches_content",
                           "repeated_span", "table_row_stutter",
                           # انحدار D1 (#13): الازدواج القصير الملاصق نفس
                           # العائلة — يصل العميل إن مرّ، فيقود FAIL.
                           "adjacent_short_stutter",
                           "empty_citation", "dead_table",
                           "system_language_leak",
                           "internal_plumbing_leak", "english_field_leak",
                           "mission_key_leak", "raw_confidence",
                           "trailing_ellipsis", "tool_use_leak",
                           "claude_mention", "env_var_leak",
                           "research_track_leak", "facts_list_leak",
                           "ops_warning_leak",
                           # §8: اختزال العملة والترقيم الإنجليزي داخل الفقرة
                           # يُفشِلان (FAIL). أدوات الربط/الأرقام المفتاحية
                           # مُدرَّجة (قرار المُشرِف): ٣–٤ WARN (خارج المجموعة)،
                           # ≥٥ FAIL (…_excess داخلها).
                           "style_currency_shorthand",
                           "style_inline_enumeration",
                           "style_connector_excess",
                           "style_repeated_key_figure_excess",
                           # البند ٥ (تدقيق «تحليل #1» DZA): وعدُ عملةٍ لم
                           # يُنجَز تحويلها بلاغٌ مضلِّل حقيقي (لا مجرّد أسلوب)
                           # — الإصلاح الفعلي في silk_render._fix_price_
                           # column_currency_label؛ ظهوره يعني فشل الإصلاح.
                           "currency_label_mismatch",
                           # PR B §B9: HHI بدقّة عشرية — يُصلَح في العرض
                           # (_fix_hhi_false_precision)؛ ظهوره = فشل الإصلاح.
                           "hhi_false_precision"}


# WP-7 §3 — النصوص النائبة الصلبة التي لا يجوز أن تبلغ **المستند النهائي
# المبني** أبداً (سطر عدم التوفّر العام مستثنى هنا: مسار التدهور المتعمَّد
# للاستدعاء المباشر؛ تسليمه عبر API محكوم بفحص القالب client_section_placeholder).
_ARTIFACT_HARD_PLACEHOLDERS = (
    "بند تقني غير قابل للعرض المباشر",
    "التفاصيل في أثر التتبع",
    "التفاصيل الكاملة في أثر التتبع",
)


# ══════════════════════════════════════════════════════════════════════════
# الموجة ٠ — فحصان منفصلان لا فحصٌ واحد: **الاتساق ≠ الجودة**
# ══════════════════════════════════════════════════════════════════════════
#
# خلطُهما عيبٌ تصميميّ حقيقي لا تفصيلُ تنظيم:
#   • **الاتساق** سؤالٌ ثنائيّ: هل تسرّبت لغةٌ خطأ إلى سطح العميل؟ جوابُه
#     نعم/لا، وأثرُه فادح (تقريرٌ مختلط يصل مصنعاً)، فحكمُه **حاجز**.
#   • **الجودة** حكمٌ متدرّج: نحوٌ، وضوحٌ، تكرارٌ، نبرةُ ترجمةٍ آلية. لا عتبةَ
#     ثنائيةً صادقة له، وحجبُ تقريرٍ صحيحٍ لعيبٍ أسلوبيّ ضررٌ لا نفع، فحكمُه
#     **تحذيريّ**.
# ولو دُمِجا لَحجب الأول تقريراً سليماً بسبب الثاني، أو مرّر الثاني تسرّباً
# لأن الأسلوب حسن — وكلاهما فشلٌ صامت.

def _check_language_consistency(text: str, lang: str = "ar",
                                view: dict | None = None) -> list[dict]:
    """**اتساق اللغة — حاجز.** هل يحوي المستند النهائي نثراً بلغةٍ خطأ؟

    مسؤوليةٌ واحدة لا غير: كشف تسرّب اللغة. لا يفحص نحواً ولا أسلوباً.

    الاستثناء **بنيويّ صريح** لا قائمةَ كلماتٍ مخمَّنة: الروابط، رموز HS،
    المعرّفات التقنية، الاختصارات المعيارية، وأسماء الكيانات المرصودة فعلاً
    في هذه الدراسة (علامات/شركات/منتجات/مصادر رسمية) — تُستخرَج من العرض
    نفسه عبر `silk_i18n.entity_allowlist`، فما يمرّ هو ما رُصد لا ما خُمِّن.
    """
    import silk_i18n
    allow = silk_i18n.entity_allowlist(view or {})
    spans = silk_i18n.foreign_prose_spans(text, lang, allow)
    if not spans:
        return []
    other = "الإنجليزية" if silk_i18n.normalize(lang) == "ar" else "العربية"
    sample = "؛ ".join(sp[:90] for sp in spans[:3])
    return [{
        "check": "language_consistency", "repairable": False,
        "note": (f"المستند النهائي بلغة «{silk_i18n.normalize(lang)}» يحوي "
                 f"{len(spans)} مقطعاً بـ{other} — تسرّبُ لغةٍ إلى سطح "
                 f"العميل: {sample}")}]


# أنماطُ الترجمة الآلية والصياغة المتعثّرة — إنجليزيةٌ تُقرأ كأنها مترجمةٌ عن
# العربية حرفياً (§34: «no literal translation from Arabic»)، وعربيةٌ تُقرأ
# كأنها مترجمةٌ عن الإنجليزية (§33). تحذيريّ: مؤشّرُ أسلوبٍ لا برهانُ عطل.
_MT_PATTERNS_EN = (
    re.compile(r"\bit is worth (?:noting|mentioning) that\b", re.I),
    re.compile(r"\bin the framework of\b|\bwithin the framework of\b", re.I),
    re.compile(r"\bthe aforementioned\b", re.I),
    re.compile(r"\bas for\b\s+the\b", re.I),
    re.compile(r"\bit can be said that\b", re.I),
    re.compile(r"\band that is\b\s+(?:what|due to)\b", re.I),
)
_MT_PATTERNS_AR = (
    re.compile(r"في حين أنّ?ه من المهم"),
    re.compile(r"يُعتبَر\s+\w+\s+كـ"),
    re.compile(r"بشكل\s+(?:رئيسي|أساسي)\s+جداً"),
    re.compile(r"واحد من الأكثر"),
)
# طولُ الجملة التنفيذيّ — نفس حدّ عقد الأسلوب (لا عتبةً ثانية قد تتباعد).
_QUALITY_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n")


def _check_language_quality(text: str, lang: str = "ar") -> list[dict]:
    """**جودة اللغة — تحذيريّ.** هل يُقرأ النصّ كتقريرٍ تنفيذيٍّ محترم؟

    يفحص — في اللغتين — النبرة المبالِغة، وأنماط الترجمة الآلية، وطول الجملة
    التنفيذيّ، وتكرارَ الجملة نفسها. **لا يفحص لغةً خطأ** (ذاك الفحص أعلاه).

    يُبنى فوق ما هو قائم فعلاً (`silk_style_contract.ALARMIST_PHRASES`،
    `SENTENCE_MAX_WORDS`) — لا عتبةً جديدة قد تتباعد عن عقد الكاتب.
    """
    import silk_i18n
    from silk_style_contract import ALARMIST_PHRASES, SENTENCE_MAX_WORDS
    lang = silk_i18n.normalize(lang)
    out: list[dict] = []
    if not (text or "").strip():
        return out

    if lang == "ar":
        for ph in ALARMIST_PHRASES:
            if ph in text:
                out.append({"check": "language_quality_tone", "repairable": True,
                            "note": f"نبرة مبالِغة على سطح العميل: «{ph}»"})
                break
        # هدف الدراسة الاحترافية (البند ٥): مقاييس عدّاد النثر — قياس
        # تحذيري في هذه القناة (الدرس 135)، والعتبات معلنة هنا؛ مناطق
        # العمى في silk_prose_meter نفسه. الملاحظات عدٌّ بلا صدى نص.
        try:
            from silk_prose_meter import analyze as _prose
            pm = _prose(text)
            if pm["sentences"] >= 5:
                if (pm["nominal_ratio"] or 0) > 0.35:
                    out.append({"check": "language_quality_prose_openers",
                                "repairable": True,
                                "note": (f"{len(pm['nominal_openers'])} من "
                                         f"{pm['sentences']} جملة تفتتح "
                                         "بالاسم/فعل الحشو — ابدأ بالفعل "
                                         "(قاعدة النثر ١)")})
                if len(pm["passives"]) >= 3:
                    out.append({"check": "language_quality_prose_passive",
                                "repairable": True,
                                "note": (f"{len(pm['passives'])} جملة بصيغة "
                                         "مجهول/«يتم» — سمِّ الفاعل "
                                         "(قاعدة النثر ٣)")})
                if sum(pm["heavy_connectors"].values()) >= 3:
                    out.append({"check": "language_quality_prose_connectors",
                                "repairable": True,
                                "note": ("روابط ثقيلة "
                                         f"×{sum(pm['heavy_connectors'].values())}"
                                         " — الخفيفة تكفي (قاعدة النثر ٥)")})
                if pm["literal_terms"]:
                    out.append({"check": "language_quality_prose_literal",
                                "repairable": True,
                                "note": ("مصطلح مترجم حرفياً "
                                         f"×{sum(pm['literal_terms'].values())}"
                                         " (قاعدة النثر ٤)")})
        except Exception:  # noqa: BLE001 — قياسٌ تحسيني لا يُسقط البوابة
            pass
    mt = _MT_PATTERNS_EN if lang == "en" else _MT_PATTERNS_AR
    for pat in mt:
        m = pat.search(text)
        if m:
            out.append({"check": "language_quality_machine_translation",
                        "repairable": True,
                        "note": ("صياغةٌ تُقرأ كترجمةٍ آلية لا كنصٍّ مكتوبٍ "
                                 f"بلغته: «{m.group(0)}»")})
            break

    sentences = [x.strip() for x in _QUALITY_SENTENCE_SPLIT.split(text)
                 if x.strip()]
    long_ones = [x for x in sentences
                 if len(x.split()) > SENTENCE_MAX_WORDS * 2]
    if len(long_ones) >= 3:
        out.append({"check": "language_quality_readability", "repairable": True,
                    "note": (f"{len(long_ones)} جملةً تتجاوز ضِعف الحدّ "
                             f"التنفيذيّ ({SENTENCE_MAX_WORDS} كلمة) — "
                             "قابلية القراءة التنفيذية تنخفض")})
    # تكرارُ الجملة نفسها حرفياً — حشوٌ يُضعِف التقرير (نفس منطق تكرار الرقم).
    seen: dict[str, int] = {}
    for x in sentences:
        if len(x.split()) >= 6:
            seen[x] = seen.get(x, 0) + 1
    dupes = [x for x, n in seen.items() if n >= 3]
    if dupes:
        out.append({"check": "language_quality_repetition", "repairable": True,
                    "note": (f"جملةٌ مكرَّرة حرفياً ≥٣ مرّات: "
                             f"«{dupes[0][:80]}»")})
    return out


def run_client_artifact_text_gate(text: str, lang: str = "ar",
                                  view: dict | None = None) -> list[dict]:
    """WP-7 §3 — بوابة نصّ المُنتَج النهائي: تُشغَّل على النص الكامل
    المستخرَج من مستند العميل **بعد** بنائه (docx — ومنه يُشتق الـPDF)، لا
    على القالب فقط: طبقة العرض نفسها قد تُدخِل نصاً لم يمرّ على فحوصات
    القالب. تعيد قائمة بنود؛ أي بند = رفض التسليم (RuntimeError في
    `render_client_docx`)."""
    findings: list[dict] = []
    if not text:
        return findings
    findings += _check_client_scaffold_leak(text)
    _plain = _strip_ar_diacritics(text)
    for ph in _ARTIFACT_HARD_PLACEHOLDERS:
        if _strip_ar_diacritics(ph) in _plain:
            findings.append({
                "check": "placeholder_leak", "repairable": False,
                "note": f"نصّ نائب تقني في المستند النهائي: «{ph}»"})
    # بتر «…» على مستوى السطر (نص docx المستخرَج سطرٌ لكل فقرة، لا كتل
    # منفصلة بأسطر فارغة) — الاقتباسات (»/") الخاتمة مستثناة بنيوياً لأن
    # السطر حينها لا ينتهي بالنقاط نفسها.
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(">"):
            continue
        if len(s) > 25 and (s.endswith("…") or s.endswith("...")):
            findings.append({
                "check": "trailing_ellipsis", "repairable": False,
                "note": f"سطر في المستند النهائي ينتهي بنقاط حذف: "
                       f"'...{s[-40:]}'"})
    if "لا فجوة جوهرية" in text and "فجوة بيانات" in text:
        findings.append({
            "check": "gaps_closing_contradiction", "repairable": False,
            "note": "المستند النهائي يعلن «فجوة بيانات» ويطبع «لا فجوة "
                   "جوهرية» معاً — تناقض فجوات في المُنتَج المبني"})
    # الموجة ٠: اتساق اللغة **حاجز** على سطح المُنتَج النهائي — أقرب نقطةٍ
    # ممكنة للعميل، بعد بناء المستند فعلياً وقبل حفظه.
    findings += _check_language_consistency(text, lang, view)
    return findings


# البنود غير القابلة للإصلاح التي تُفشِل الحكم (FAIL لا WARN) — ثابتٌ واحد
# على مستوى الوحدة كي تُثبِّته الاختبارات وتُضاف إليه البوابات الجديدة بلا
# نسخٍ للمنطق داخل `run_quality_gate`. (البنود القابلة للإصلاح التي أفلتت
# فعلاً تُفشِل عبر `_REGRESSION_GUARD_FIRED` — مسارٌ منفصل.)

# ── الموجة C · C1-٤ — الحاجزُ التنظيميّ يمنع الإيجاب ──────────────────────

# الأحكامُ الإيجابية بالرمز الإنجليزيّ الخام (المصدرُ الوحيد للنبرة) — ما
# يُقرَأ «ادخل السوق». `CONDITIONAL-GO` **ليست** منها: مشروطةٌ بحكم تعريفها،
# وحاجزٌ مفتوحٌ هو بالضبط أحدُ شروطها.
_POSITIVE_VERDICT_CODES = ("GO", "PRELIMINARY GO", "STRONG GO")


def _open_hard_regulatory(view: dict) -> list[dict]:
    """الحواجزُ الصلبةُ المفتوحة كما بثّها وكيلُ الاشتراطات — بنيويّاً.

    لا مطابقةَ عبارات: يُقرأ الحقلُ المُهيكل الذي يضعه
    `silk_requirements_agent` في نقطةٍ موسومة، عبر أيّ من السطحين.
    """
    reg = (view or {}).get("regulatory") or {}
    if isinstance(reg, dict) and reg.get("open_hard"):
        return list(reg["open_hard"])
    return []


def _check_regulatory_blocker(view: dict) -> list[dict]:
    """توصيةٌ إيجابيةٌ بينما حاجزٌ صلبٌ مفتوح = **رفضُ تسليم**.

    الفجوة (§٥ من الجرد): بوّابةُ الأهلية كانت تُعلَّق ملاحظةً على البنود
    التالية ولا تمنع شيئاً — فتقريرٌ يقول «ادخل» بينما المنشأةُ غيرُ مُدرَجة
    في قوائم الاتحاد كان يُسلَّم كاملاً. الآن حاجزٌ في `FAIL_TRIGGER_CHECKS`.

    **ولا يُفشِل الحاجزُ المفتوحُ وحدَه تقريراً**: تقريرٌ يقول «لا تدخل قبل
    حسم الإدراج» صحيحٌ ونافع. المرفوضُ هو **الجمعُ** بين إيجابٍ وحاجز.
    """
    hard = _open_hard_regulatory(view)
    if not hard:
        return []
    dr = (view or {}).get("deep_research") or {}
    verdict_raw = str(((dr.get("verdict") or {}).get("verdict")
                       or (view or {}).get("verdict") or "")).upper()
    positive = any(code in verdict_raw for code in _POSITIVE_VERDICT_CODES) \
        and "NO-GO" not in verdict_raw and "CONDITIONAL" not in verdict_raw
    if not positive:
        return []
    items = "؛ ".join(str(b.get("item") or "")[:70] for b in hard[:2])
    return [{
        "check": "regulatory_hard_blocker_open", "repairable": False,
        "note": ("التقرير يوصي بالدخول بينما شرطُ دخولٍ إلزاميٌّ لم يُحسَم "
                 f"بعد: {items}. شرطٌ كهذا يعني رفضَ الشحنة عند الحدود لا "
                 "تأخّرَها، فلا تُسلَّم توصيةٌ إيجابيةٌ فوقه.")}]


# ── الموجة C · Z-03 وZ-05 — تحجيمُ السوق يُفحَص اشتقاقاً لا مقداراً فقط ────

_SIZING_ROW_RE = re.compile(
    r"\|\s*(TAM|SAM|SOM)\s*\|([^|\n]*)\|([^|\n]*)\|", re.I)


def _sizing_rows(text: str) -> list[dict]:
    """صفوفُ جدول التحجيم كما كتبها الكاتب — المستوى والقيمة وطريقة الحساب."""
    out: list[dict] = []
    for m in _SIZING_ROW_RE.finditer(text or ""):
        out.append({"level": m.group(1).upper(),
                    "value": (m.group(2) or "").strip(),
                    "method": (m.group(3) or "").strip()})
    return out


def _check_market_sizing_derivation(dr: dict) -> list[dict]:
    """كلُّ رقمِ تحجيمٍ يحمل معادلتَه، والمعادلةُ مؤرَّضةٌ فعلاً (Z-03 + Z-05).

    **الفجوة:** الفحصُ الوحيد المتعلّق بـTAM كان `_check_tam_below_single_
    country_flow` — فحصُ **مقدار** لا فحصُ **اشتقاق**. فرقمٌ سليمُ المقدار
    ومُختلَقُ الاشتقاق يمرّ بلا كلمة، وهو الحالةُ الأخطر: يبدو معقولاً.

    و**حارسُ التأريض** (`silk_evals.formula_grounded_numbers`) — الوحيدُ
    القادرُ على كشف رقمٍ مشتقٍّ بلا تأريض — كان يعيش في حزمة **التقييم** لا
    في مسار التشغيل، فلا يُشغَّل على تقريرٍ يُسلَّم. يُعاد استعمالُه هنا بدل
    بناء حارسٍ ثانٍ.

    تحذيريٌّ لا حاجب: الكاتبُ قد يعرض التحجيم نثراً مشروعاً بلا جدول، وحجبُ
    تقريرٍ صحيحٍ لأجل شكلٍ ضررٌ لا نفع.
    """
    text = (dr.get("report") or {}).get("text") or ""
    if not text:
        return []
    rows = _sizing_rows(text)
    if not rows:
        return []
    out: list[dict] = []
    # (١) كلُّ صفٍّ يحمل طريقةَ حسابه — عمودٌ فارغ يعني رقماً بلا اشتقاق.
    naked = [r["level"] for r in rows
             if not r["method"] or r["method"] in ("-", "—", "غير متاح")]
    if naked:
        out.append({
            "check": "sizing_row_without_method", "repairable": True,
            "note": (f"صفوفُ تحجيمٍ بلا طريقة حساب: {'، '.join(naked)}. الرقمُ "
                     "بلا معادلته لا يمكن للمصنع أن يتحقّق منه ولا أن يعيد "
                     "حسابه بمدخلاته هو")})
    # (٢) الترتيب المنطقيّ: TAM ≥ SAM ≥ SOM. انقلابُه خطأٌ اشتقاقيّ لا أسلوبيّ.
    vals: dict = {}
    for r in rows:
        nums = re.findall(r"\d[\d,.]*", r["value"])
        if nums:
            try:
                vals[r["level"]] = float(nums[0].replace(",", ""))
            except ValueError:
                pass
    order = [lv for lv in ("TAM", "SAM", "SOM") if lv in vals]
    for a, b in zip(order, order[1:]):
        if vals[a] < vals[b]:
            out.append({
                "check": "sizing_order_inverted", "repairable": True,
                "note": (f"{b} أكبر من {a} ({vals[b]:,.0f} مقابل "
                         f"{vals[a]:,.0f}) — والجزءُ لا يكون أكبر من الكلّ. "
                         "راجع المعادلة أو الوحدات")})
    # (٣) التأريض: معادلاتُ التحجيم تمرّ بحارس `silk_evals` نفسه.
    try:
        from silk_evals import formula_grounded_numbers
        known = set()
        for m in (dr.get("missions") or {}).values():
            for f in (m.get("findings") or []):
                v = f.get("value") if isinstance(f, dict) else None
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    known.add(str(int(v)) if float(v).is_integer() else str(v))
        grounded = formula_grounded_numbers(text, known)
        ungrounded = [r["level"] for r in rows
                      if r["level"] in vals
                      and str(int(vals[r["level"]])) not in grounded
                      and str(int(vals[r["level"]])) not in known]
        if ungrounded and grounded is not None and len(rows) > 1:
            out.append({
                "check": "sizing_not_grounded", "repairable": True,
                "note": (f"أرقامُ تحجيمٍ لم نتمكّن من ردّها إلى رقمٍ مرصود عبر "
                         f"معادلةٍ صحيحة: {'، '.join(ungrounded)}. اذكر مصدر "
                         "المدخل أو صرّح بأنه افتراض")})
    except Exception as exc:  # noqa: BLE001 — الحارسُ تحسينيّ لا شرطُ تسليم
        log.warning("sizing grounding check skipped: %s", exc)
    return out


# ── الموجة C · C-07 وC-08 — الرقمُ يُربَط بالحكم لا بنفسه ─────────────────


def _asserted_in(text: str, label: str) -> bool:
    """هل تُذكَر هذه التسميةُ **إثباتاً** لا شرطَ قلبٍ مستقبليّاً؟"""
    start = 0
    while True:
        idx = text.find(label, start)
        if idx < 0:
            return False
        start = idx + len(label)
        if not _VERDICT_FLIP_MARKER_RE.search(text[max(0, idx - 45):idx]):
            return True


def _check_narrative_matches_the_verdict(view: dict) -> list[dict]:
    """نثرُ الكاتب يطابق **الحكمَ والثقةَ الحتميَّين**، لا نفسَه فقط.

    **الفجوتان:** `_check_confidence_value_conflict` يرصد رقمَي ثقةٍ مختلفَين
    **داخل النصّ**، و`_check_verdict_label_conflict` يرصد تسميتَي حكمٍ **داخل
    النصّ** — كلاهما حارسُ اتساقٍ **داخليّ** للنثر. فنصٌّ متّسقٌ مع نفسه
    تماماً بينما يخالف الحكمَ المخزَّن والثقةَ المسقوفة يمرّ من الاثنين معاً:
    الكاتبُ يقول «٧٢٪» والغلافُ يقول «٥٥٪»، ولا فحصَ يقارنهما لأنّ كلاً منهما
    متّسقٌ في موضعه.

    وهذان يقرآن `dr["report"]["text"]` وحدَه فيعميان عن الشارة والخلاصة —
    وهما أوّلُ ما يقرؤه صاحبُ المصنع.

    الفحصُ هنا **حاجزٌ للحكم وتحذيريٌّ للثقة**: تسميةُ حكمٍ مخالفةٌ للحكم
    المخزَّن خطأٌ قاطع، وفرقُ نقطةٍ مئويةٍ في الثقة قد يكون تقريباً.
    """
    dr = (view or {}).get("deep_research") or {}
    text = str((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    out: list[dict] = []
    verdict = dr.get("verdict") or {}
    # (١) التسمية: الحكمُ الحتميّ مقابل ما يؤكّده المتن.
    try:
        from silk_render import _VERDICT_LABELS_AR, _verdict_tone
        tone = _verdict_tone(verdict.get("verdict"))
        expected = _VERDICT_LABELS_AR.get(tone)
    except Exception:  # noqa: BLE001
        expected = None
    # **يُقارَن الحاسمُ بالحاسم وحدَه.** حكمٌ مُسجَّلٌ «غير محسوم» أو غائب
    # (`tone="unknown"`) لا يناقض تسميةً حاسمةً في المتن — تلك مشكلةٌ أخرى
    # (V-01، الموجة D). والمرورُ الأول لم يميّز، فحجب تقريراً سليماً فوراً:
    # حارسٌ يمنع الصحيحَ أسوأُ من غيابه.
    decisive_tones = ("go", "preliminary", "conditional", "watch", "nogo")
    if expected and tone in decisive_tones:
        decisive = {v for k, v in _VERDICT_LABELS_AR.items()
                    if k in decisive_tones}
        # **الاستثناءُ نفسه الذي يستعمله `_check_verdict_label_conflict`** —
        # لا آليةٌ ثانية: تسميةٌ يسبقها شرطُ قلبٍ مستقبليٌّ صريح («يتحوّل إلى…
        # إذا…») ليست إثباتاً لحكمٍ ثانٍ بل صياغةٌ مشروعة. المرورُ الأول أغفلها
        # فحجب مدوّنةَ اختبارٍ سليمةَ النيّة — وكان سيحجب تقارير حقيقية.
        others = [lbl for lbl in decisive
                  if lbl != expected and _asserted_in(text, lbl)]
        if others and not _asserted_in(text, expected):
            out.append({
                # **تحذيريٌّ في هذه الموجة، وسببُ ذلك مُسجَّل.** الفحصُ صحيحٌ
                # ويكشف تناقضاً حقيقياً، لكنّ جعلَه حاجزاً فوراً أسقط ١٢
                # اختباراً قائماً: مدوّناتُ الاختبار تخالف نيّتَها المكتوبة
                # («الكاتب مقيَّد بالحكم الحتمي فيطابقه السرد») لأنّ حقلَ
                # الحكم يُضبَط `CONDITIONAL-GO` بينما السردُ القانونيّ يقول
                # `WATCH`. وهذا التناقضُ نفسُه هو البند V-01 المؤجَّل إلى
                # الموجة D — حيث يُصلَح **مصدرُ** الحكم فتُحدَّث المدوّناتُ
                # معه اتساقاً واحداً. الترقيةُ إلى حاجزٍ تتبع ذلك الإصلاح، لا
                # تسبقه: حجبُ التسليم بناءً على مدوّناتٍ متناقضةٍ سلفاً يمنع
                # الصحيحَ قبل أن يمنع الخطأ.
                "check": "narrative_verdict_mismatch", "repairable": True,
                "note": (f"الحكمُ المُسجَّل «{expected}» بينما متنُ التقرير "
                         f"يؤكّد «{others[0]}» ولا يذكر الحكمَ المُسجَّل — "
                         "حكمان في وثيقةٍ واحدة")})
    # (٢) الثقة: الرقمُ المسقوف مقابل ما يطبعه المتن.
    try:
        conf = float(verdict.get("confidence"))
    except (TypeError, ValueError):
        conf = None
    if conf is not None:
        pct = round(conf * 100) if conf <= 1.0 else round(conf)
        shown: set = set()
        for rex in _CONF_PCT_RES:
            for m in rex.finditer(text):
                try:
                    shown.add(int(m.group(1)))
                except ValueError:
                    continue
        far = [p for p in shown if abs(p - pct) > 2]
        if far:
            out.append({
                "check": "narrative_confidence_mismatch", "repairable": True,
                "note": (f"الثقةُ المُسجَّلة {pct}% بينما المتن يذكر "
                         f"{'، '.join(f'{p}%' for p in sorted(far))} — "
                         "وحّدهما أو اشرح الفرق")})
    return out


def _check_narrative_money_grounded(dr: dict) -> list[dict]:
    """كلُّ **مبلغٍ ماليّ** في نثر الكاتب يُردّ إلى دليلٍ أو معادلةٍ مؤرَّضة.

    **الفجوة Z-02:** عقدُ الاستشهاد (`dpN`) يحرس **البعثات** وحدَها؛ ونثرُ
    الكاتب لا يمرّ به إطلاقاً. فرقمٌ لم يرد في أيّ دليل يمكن أن يظهر في
    التقرير بثقةٍ تامّة، ولا شيء يقف في وجهه.

    **النطاق مقصودٌ ضيّق:** المبالغُ المالية وحدَها — وهي الأرقامُ التي يُبنى
    عليها قرارُ الدخول. توسيعُه إلى كلّ رقمٍ (سنوات، نسب، عدد متاجر) كان
    سيُنتِج ضجيجاً يُخفي الإشارة، وحارسٌ يصرخ دائماً لا يُسمَع.

    وتحذيريٌّ لا حاجب: الرقمُ قد يكون مذكوراً بصيغةٍ مختلفة عن الدليل (تقريب،
    وحدةٌ أخرى)، وحجبُ تقريرٍ صحيحٍ لأجل صياغةٍ ضررٌ لا نفع. الإصلاحُ الكامل —
    إخضاعُ نثر الكاتب لعقد `dpN` نفسه — يتطلّب تغييرَ بروتوكول الكاتب،
    وهو خارج نطاق هذه الموجة عمداً.
    """
    text = (dr.get("report") or {}).get("text") or ""
    if not text:
        return []
    known: set = set()
    for m in (dr.get("missions") or {}).values():
        for f in (m.get("findings") or []):
            v = f.get("value") if isinstance(f, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                known.add(round(float(v)))
    if not known:
        return []          # لا أدلةَ رقمية ⇒ لا مرجعَ للمقارنة، لا لومَ
    try:
        from silk_evals import formula_grounded_numbers
        grounded_lits = formula_grounded_numbers(text, {str(k) for k in known})
    except Exception:  # noqa: BLE001 — الحارسُ تحسينيّ
        grounded_lits = set()
    grounded: set = set()
    for lit in grounded_lits:
        try:
            grounded.add(round(float(str(lit).replace(",", ""))))
        except (TypeError, ValueError):
            continue
    loose: list = []
    for _a, _b, amt in _iter_usd_amounts(text):
        r = round(amt)
        if r in known or r in grounded:
            continue
        # تسامحٌ للتقريب: مبلغٌ يقارب دليلاً ضمن ٢٪ هو نفسُه بصياغةٍ أخرى.
        if any(abs(r - k) <= max(1.0, 0.02 * max(r, k)) for k in known):
            continue
        # ومبلغٌ **ناتجُ معادلةٍ مكتوبة** لا يُطالَب بمصدرٍ مستقلّ: معادلتُه
        # ظاهرةٌ للقارئ ومدخلاتُها تُفحَص في مكانها (`_check_market_sizing_
        # derivation`). اشتراطُ مصدرٍ له كان يُنتِج تحذيراً على رقمٍ **أفضل**
        # توثيقاً من غيره — وحارسٌ يعاقب الشفافيةَ يُدرَّب الناسُ على تفاديه.
        if "=" in text[max(0, _a - 40):_a]:
            continue
        loose.append(r)
    if not loose:
        return []
    shown = "، ".join(f"{v:,.0f}$" for v in sorted(set(loose))[:3])
    return [{
        "check": "narrative_money_not_grounded", "repairable": True,
        "note": (f"مبالغُ في نصّ التقرير لم نستطع ردَّها إلى رقمٍ مرصودٍ ولا "
                 f"إلى معادلةٍ صحيحةٍ من أرقامٍ مرصودة: {shown}. اذكر مصدرَ "
                 "كلٍّ منها أو معادلتَه، أو احذفه")}]


FAIL_TRIGGER_CHECKS = frozenset({
    "section_structure", "agent_failed", "agent_failed_many_optional",
    "analyst_layer_failed",
    "evidence_body_numeric_contradiction", "source_coverage_below_threshold",
    # §B (حزمة الفكس v2.1): بتر/إحالة معلَّقة/قسم عميل بلا محتوى فعلي.
    "orphan_short_token", "dangling_cross_reference",
    "client_section_placeholder",
    # WP-1 §4: تسمية نطاق ثقة لا تطابق رقمها = خطأ يصل وجه التقرير.
    "confidence_band_mismatch",
    # WP-2 §6: سقالة «إذن ماذا»/نصّ نائب تقني/بتر «…» غير اقتباسي.
    "client_scaffold_leak", "placeholder_leak", "trailing_ellipsis",
    # WP-4 §3: ختامٌ ينفي الفجوات بينما المتن يعلنها.
    "gaps_closing_contradiction",
    # PR A (بلاغ تحليل ٧): تعارض ثقة/تسمية حكم، وTAM أصغر من تدفّق دولة واحدة.
    "confidence_value_conflict", "verdict_label_conflict",
    "tam_below_single_country_flow",
    # P0 (تحليل ٧): سردُ انكماشٍ مبنيٍّ على سلسلةٍ ضعيفةِ التسجيل بينما المرآة
    # تفوقها، وتصعيدُ التقادُم (سنةٌ >٥ سنوات تقود استنتاجاً مذكوراً).
    "mirror_divergence_contraction_narrative",
    "stale_year_driving_conclusion",
    # بلاغ المالك (تحليل ٧): إشارةُ CAGR تنقلب بتغيير سنة الأساس المرصودة.
    "cagr_sign_flips_under_base_year",
    # PR B (بلاغ تحليل ٧): تلوّثُ عملةٍ خارج السوق يصل العميل مضلِّلاً.
    "off_market_currency",
    # الموجة ٠ (تصحيح المالك ١): تسرّبُ لغةٍ خطأ إلى تقرير العميل **حاجز** —
    # تقريرٌ مختلط اللغة يصل مصنعاً خرقٌ لعقد المنتج لا عيبٌ أسلوبيّ.
    # (فحوص `language_quality_*` تحذيريّةٌ عمداً وليست هنا — الجودة حكمٌ
    # متدرّج، وحجبُ تقريرٍ صحيحٍ لعيبٍ أسلوبيّ ضررٌ لا نفع.)
    "language_consistency",
    # الموجة C (§٥-٤): توصيةٌ إيجابيةٌ فوق شرطِ دخولٍ إلزاميٍّ غيرِ محسوم.
    "regulatory_hard_blocker_open",
    # صيد الفجوات ٣: S-01/S-02 موثَّقان «حاجزين» منذ موجة التكافؤ لكنهما لم
    # يُوصَلا بأيٍّ من مجموعتَي الحجب — توصيةُ «ادخل» فوق حكمٍ مشروط كانت
    # تُسلَّم 200 (الدرس 98: الحارس الذي لا يمكن أن يُطلِق).
    "recommendation_tier_mislabel", "intersection_insufficiency",
    # هدف الدراسة الاحترافية (البند ١): «غير محسوب» يسمّي تحويل وحدةٍ ثابتُها
    # مسجّل مدخلاً ناقصاً — حجبُ رقمٍ محسوبٍ حتمياً لا يُسلَّم (عائلة الدرس 84).
    "unit_conversion_refusal",
    # الدرس ٢٦٢: رمزُ سجلٍّ داخليٌّ غيرُ مملوء وصل نصاً مُصيَّراً — بنيةٌ
    # داخلية لا تصل عميلاً بأيّ حال، فحاجبٌ بلا راية.
    "ledger_token_unbound",
})


# ── الجولة الثانية: مجموعةُ الحجبِ الفعّالة · flag-gated fail triggers ──────
# قرار المالك 2026-08-19 «لا حجب جديداً» يبقى سارياً على الإنتاج: الفحوصُ
# الجديدة تحجب **فقط** حين تُفعَّل رايتُها صريحاً. و`FAIL_TRIGGER_CHECKS`
# نفسُها **لا تُمَسّ** — عشراتُ الاختبارات تقرؤها عقداً ثابتاً — فتُحسَب
# المجموعةُ الفعّالة عند الحكم: مطفأةً = المجموعةُ الأصلية حرفياً.
_FLAGGED_FAIL_TRIGGERS: tuple = (
    # الدرس ٢٦٢: فحوصُ سجلّ الحقائق — تحذيريةٌ في وضع القياس (الافتراضي)،
    # وحاجبةٌ حين يفعّل المالكُ `SILK_LEDGER_ENFORCE` بعد أسبوع القياس.
    ("ledger_value_mismatch", "silk_fact_ledger", "enforce"),
    ("ledger_status_mismatch", "silk_fact_ledger", "enforce"),
    ("ledger_count_mismatch", "silk_fact_ledger", "enforce"),
    ("ledger_series_year_mismatch", "silk_fact_ledger", "enforce"),
    ("chart_year_mismatch", "silk_fact_ledger", "enforce"),
    ("blocking_condition_drift", "silk_fact_ledger", "enforce"),
    ("ledger_stale", "silk_fact_ledger", "enforce"),
    # (اسمُ الفحص، الوحدةُ التي تحمل رايتَه، اسمُ دالّة الراية)
    ("metric_value_divergence", "silk_figure_store", "enabled"),
    ("open_conditions_count_mismatch", "silk_render",
     "open_conditions_single"),
    ("high_confidence_with_missing_pillar", "silk_render",
     "confidence_discipline"),
    ("reference_to_nonexistent_figure", "silk_narrative",
     "derived_provenance_enabled"),
)


# ── الدرس ٢٥٤ (القفلُ العام): الموجّهُ لا يُخالِف البوّابةَ التي تحكمه ──────
# حادثةُ ماليزيا: `high_confidence_with_missing_pillar` حاجبٌ يفحص **نثرَ**
# الكاتب، وعلاجُه (سقفُ التسمية) طُبِّق في العرض وفي البوّابة **ولم يصل
# موجّهَ الكاتب** — فسلّمه الموجّهُ «عالية (80%)» وأمره بألّا يذكر تسميةً
# غيرها، ثم حجبت البوّابةُ التقريرَ كلَّه على طاعته. وإعادةُ التوليد لا
# تُصلِح حتمياً. العيبُ ليس في الفحص بل في غيابِ ما يمنع تكرارَه.
#
# السجلُّ أدناه يصنّف **كلَّ** فحصٍ حاجبٍ مُفعَّلٍ براية (`_FLAGGED_FAIL_
# TRIGGERS`): إمّا «قارئُ نثرٍ بعبارةٍ ممنوعة» فيلزمه نمطٌ مُعلَنٌ + مصدرُ
# تعليمةٍ في موجّه الكاتب، أو «غيرُ نصّيّ» بسببٍ مكتوب. القفلُ في
# `tests/test_prose_blocker_prompt_parity.py`: النمطُ الممنوع **لا يجوز أن
# يُطابِق موجّهَ الكاتب المبنيَّ فعلاً** (لا موجّهاً مُعاد تركيبه — الدرس
# ١٨٦)، والمصدرُ المُسمّى يجب أن يكون رمزاً موجوداً يصل الموجّه.
# سجلٌّ تعريفيّ (توثيق-كشيفرة) — لا يقرؤه `run_quality_gate`.
PROSE_LITERAL_BLOCKERS: dict = {
    # (اسمُ الفحص): (اسمُ النمط **الثابت** الممنوع في هذه الوحدة،
    #                (وحدةُ التعليمة المقابلة، رمزُها في موجّه الكاتب))
    "high_confidence_with_missing_pillar": (
        "_HIGH_CONF_RE", ("silk_ai_judge", "_summarize_verdict")),
}

# بقيّةُ الفحوص الحاجبةِ المُفعَّلةِ براية: تقرأ النثرَ أو لا تقرؤه، لكنّ
# الممنوعَ فيها **ليس نمطاً ثابتاً** يمكن للموجّه أن يُسلِّمه حرفياً — فلا
# قفلَ «الموجّه لا يحمل الممنوع» عليها. كلٌّ بسببه المقيس، والتصنيفُ
# إلزاميٌّ لا اختياريّ (الاختبار يرفض فحصاً غيرَ مصنَّف).
NON_LITERAL_FLAGGED_BLOCKERS: dict = {
    # الدرس ٢٦٢: فحوصُ السجلّ **غيرُ نصّية** — تقابل رقماً أو حالةً أو عدداً
    # في النصّ بقيمةٍ مخزَّنة، لا عبارةً ممنوعةً يمكن للموجّه أن يُملِيها.
    # وتعليمةُ الموجّه المقابلة (`silk_fact_ledger.LEDGER_TOKEN_RULE`) تُلحَق
    # أصلاً حين يوجد سجلّ، وبوّابةُ المسوّدة (`draft_issues`) تردّ المخالفةَ
    # للكاتب **قبل التخزين** فلا يبلغ الحجبَ إلا ما تعذّر إصلاحُه.
    "ledger_value_mismatch":
        "مقابلةُ رقمٍ في النصّ بقيمةٍ مخزَّنة بتسامح تقريبٍ مقيس — أيُّ رقمٍ "
        "صحيحٍ مسموح، والخطأُ في مخالفته السجلَّ لا في لفظه.",
    "ledger_status_mismatch":
        "مقابلةُ إعلانِ غيابٍ بحالةٍ محسوبةٍ في السجلّ — الممنوعُ أن يخالف "
        "الحالةَ المخزَّنة، لا عبارةُ الغياب نفسُها (وهي مسموحةٌ حين تصدق).",
    "ledger_count_mismatch":
        "مطابقةُ عددٍ مذكورٍ بعددٍ محسوب (`silk_fact_ledger` عن قائمة محرّك "
        "القرار) — أيُّ عددٍ صحيحٍ مسموح.",
    "ledger_series_year_mismatch":
        "مقارنةُ سنةٍ في النصّ بأحدث سنةٍ مرصودةٍ في السلسلة — رقمٌ لا عبارة.",
    "chart_year_mismatch":
        "مقارنةُ سنةِ رسمٍ ببيانات السلسلة — بنيويٌّ لا نصّيّ (لا يقرأ متناً).",
    "blocking_condition_drift":
        "مطابقةُ تعريفِ الشرط الحاجب بنصّ السجلّ — النصُّ متغيّرٌ لكلّ دراسة "
        "لا ثابتٌ يمكن حظرُه.",
    "ledger_stale":
        "مقارنةُ لقطةِ الكاتب بالسجلّ الحاليّ — حالةُ بياناتٍ لا عبارةٌ في "
        "المتن؛ لا موجّهَ يمكنه تفاديها بالصياغة.",
    "metric_value_divergence":
        "تباعدُ قيمتين لنفس المقياس — مقارنةُ أرقامٍ مخزَّنة لا عبارةٌ "
        "ممنوعة؛ وتعليمةُ الموجّه المقابلة "
        "(`silk_figure_store.FIGURE_IDENTITY_RULE`) تُلحَق أصلاً خلف رايتها.",
    "open_conditions_count_mismatch":
        "مطابقةُ عددٍ مذكورٍ بعددٍ محسوب (`silk_render.open_conditions`) — "
        "أيُّ عددٍ صحيحٍ مسموح، والخطأُ في مخالفته الحسابَ لا في لفظه.",
    "reference_to_nonexistent_figure":
        "الإبرةُ مُشتقّةٌ من أسماء بنود القرار في التشغيلة نفسها "
        "(`_dn_needle`) + وجودِ رقم — نمطٌ متغيّرٌ لكلّ دراسة لا ثابت؛ "
        "وتعليمةُ الموجّه المقابلة (`silk_narrative.DERIVED_PROVENANCE_RULE` "
        "وسطرُ «قياسات لم يعتمدها محرك القرار») تُلحَقان خلف رايتهما.",
}


def effective_fail_triggers() -> frozenset:
    """مجموعةُ الفحوص الحاجبة الآن — الثابتة زائداً ما تُفعِّله الرايات."""
    extra = set()
    for check, module, fname in _FLAGGED_FAIL_TRIGGERS:
        try:
            if getattr(__import__(module), fname)():
                extra.add(check)
        except Exception:  # noqa: BLE001 — رايةٌ غيرُ قابلةٍ للقراءة = مطفأة
            continue
    return FAIL_TRIGGER_CHECKS | extra


_HHI_VALUE_RE = re.compile(r"HHI[^\d\n]{0,25}(\d+(?:[.,]\d+)?)")


def _check_hhi_scale(dr: dict) -> list[dict]:
    """الموجة 2أ (Gate C تحذيري): مقياس HHI الواحد 0–10000. قيمة HHI معروضة
    < 1 = كسر 0–1 تسرّب للنص بينما العتبات المعلنة (2500) على 0–10000 —
    مقارنة صامتة خاطئة. تحذيري فقط (قرار مالك: لا حجب جديداً)."""
    text = ((dr.get("report") or {}).get("text") or "")
    bad = []
    for m in _HHI_VALUE_RE.finditer(text):
        try:
            v = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        if 0 < v < 1:
            bad.append(m.group(1))
    if not bad:
        return []
    return [{
        "check": "hhi_wrong_scale", "repairable": True,
        "note": (f"قيمة HHI بمقياس كسري ({'، '.join(bad)}) بينما العتبات "
                 "المعلنة على مقياس 0–10000 — وحّد عبر silk_economics.hhi")}]


# القاعدة الدائمة (#13 — تصحيح المُشرِف، البند 6): النمو المركّب يُحسب إلى
# أحدث سنة مرصودة أو يعلن طرفيه — وهذا الفحص المرافق يرصد نافذةً تقف خلف
# أحدث رصد (CAGR ‏2019–2023 بينما TAM ‏2024 مرصود في الدراسة نفسها).
# دورة C4: الفجوة تسمح بأرقام بينية («CAGR ‏41.2% للفترة 2019-2023») —
# حصر الفجوة بغير الأرقام كان يعمي الفحص متى سبقت القيمةُ المدى؛ تاريخ
# ISO لا يطابق أصلاً (شرط سنةٍ كاملة على طرفي الفاصلة).
_CAGR_RANGE_NOTE_RE = re.compile(
    r"(?:CAGR|نمو[^0-9\n]{0,15}مرك)[^\n]{0,60}?"
    r"(19\d\d|20\d\d)\s*[–—-]\s*(19\d\d|20\d\d)")
_TAM_YEAR_NOTE_RE = re.compile(r"سنة\s+(19\d\d|20\d\d)")


def _check_cagr_endpoint_lag(dr: dict) -> list[dict]:
    """`cagr_endpoint_lag` — ملاحظة منهجية (لا تقود FAIL): نافذة النمو
    المركّب المعلنة تنتهي قبل أحدث سنة TAM مرصودة في التشغيلة نفسها.

    **منطقة العمى المعلنة**: المقارنة على سنة TAM المعلنة («سنة {y}») في
    ملاحظات الحقائق حصراً — سلسلة أحدث في مصدر آخر بلا ملاحظة TAM لا
    تُرى؛ وملاحظة CAGR بلا مدى سنوات صريح خارج النطاق."""
    cagr_end = None
    tam_year = None
    for m in (dr.get("missions") or {}).values():
        findings = (m.get("findings") if isinstance(m, dict)
                    else getattr(m, "findings", None)) or []
        for f in findings:
            note = str((f.get("note") if isinstance(f, dict)
                        else getattr(f, "note", None)) or "")
            rng = _CAGR_RANGE_NOTE_RE.search(note)
            if rng:
                cagr_end = max(cagr_end or 0, int(rng.group(2)))
            if "TAM" in note or "إجمالي واردات" in note:
                ty = _TAM_YEAR_NOTE_RE.search(note)
                if ty:
                    tam_year = max(tam_year or 0, int(ty.group(1)))
    if cagr_end and tam_year and cagr_end < tam_year:
        return [{
            "check": "cagr_endpoint_lag", "repairable": False,
            "note": (f"نافذة النمو المركّب تنتهي عند {cagr_end} بينما أحدث "
                     f"سنة مرصودة في الدراسة {tam_year} — يُحدَّث طرف "
                     "النافذة لأحدث سنة مرصودة أو يُعلَن سبب الاستثناء "
                     "بجانب الرقم")}]
    return []


def _check_cagr_recompute(dr: dict) -> list[dict]:
    """الموجة 2أ (Gate C تحذيري): إعادة حساب CAGR حيث توجد سلسلة بنيوية —
    n = آخر سنة مرصودة − أولها (silk_trend.cagr_pct)، بتسامح 0.2 نقطة.
    يطلق فقط عند وجود بنية {series, cagr_pct} — لا تحليل نثر ولا ضجيج."""
    import silk_trend
    findings_out = []
    for m in (dr.get("missions") or {}).values():
        for f in (m or {}).get("findings") or []:
            if not isinstance(f, dict):
                continue
            series = f.get("series")
            stated = f.get("cagr_pct")
            if not isinstance(series, list) or stated is None:
                continue
            pairs = [(r.get("year"), r.get("value")) for r in series
                     if isinstance(r, dict) and r.get("value") is not None]
            if len(pairs) < 2:
                continue
            recomputed = silk_trend.cagr_pct(sorted(
                (y, v) for y, v in pairs if isinstance(y, int)))
            if recomputed is None:
                continue
            try:
                if abs(float(stated) - recomputed) > 0.2:
                    findings_out.append({
                        "check": "cagr_recompute_mismatch", "repairable": True,
                        "note": (f"CAGR المعلن {stated}% ≠ المعاد حسابه "
                                 f"{recomputed}% من نفس السلسلة "
                                 "(n = آخر سنة مرصودة − أولها) — صحّح المعلن")})
            except (TypeError, ValueError):
                continue
    return findings_out


def _check_source_contract_completeness(dr: dict) -> list[dict]:
    """الموجة ١ (Gate A تحذيري): اكتمال بطاقة النسب لكل بند — الرابط (بعد ملء
    السجلّ العمومي) والوحدة. لا يمسّ عرض الرقم إطلاقاً (تعديل مالك ٤) — يقيس
    ويحذّر فقط، ويطلق فقط حين ينخفض الاكتمال عن النصف (لا ضجيج على القديم)."""
    from silk_data_layer import datapoint_provenance
    total = with_url = 0
    for m in (dr.get("missions") or {}).values():
        for f in (m or {}).get("findings") or []:
            prov = datapoint_provenance(f)
            if prov.get("value") is None:
                continue
            total += 1
            if prov.get("url"):
                with_url += 1
    # عتبة حجم: تقارير حقيقية فقط (≥10 بنود) — لا ضجيج على مثبتات/تشغيلات
    # صغيرة قديمة الشكل (حارسا «الحالة النظيفة» القائمان يبقيان PASS).
    if total < 10 or with_url / total >= 0.5:
        return []
    return [{
        "check": "source_contract_incomplete", "repairable": True,
        "note": (f"بطاقة النسب مكتملة الرابط في {with_url}/{total} بنداً فقط "
                 "— أكمل روابط المصادر في السجلّ العمومي (لا يمسّ عرض الأرقام)")}]


def _check_vintage_expired_facts(dr: dict) -> list[dict]:
    """الموجة ١ (§2.4 تحذيري): بيانات أقدم من الطبقة الصلبة (7 سنوات
    افتراضياً) موجودة بين البنود — سياقٌ فقط، لا تُبنى عليها خلاصة. تحذير
    للمشغّل؛ لا حجب ولا إخفاء قيمة (قرار مالك 2026-08-19)."""
    import silk_staleness as S
    expired_years: set = set()
    for m in (dr.get("missions") or {}).values():
        for f in (m or {}).get("findings") or []:
            val = f.get("value") if isinstance(f, dict) else getattr(f, "value", None)
            if val is None:
                continue  # فجوة معلنة لا «بند» — لا إنذار كاذب (مراجعة §58)
            y = S.fact_year(f)
            if y and S.vintage_tier(y) == S.VINTAGE_EXPIRED:
                expired_years.add(y)
    if not expired_years:
        return []
    ys = "، ".join(str(y) for y in sorted(expired_years))
    return [{
        "check": "vintage_expired_facts_present", "repairable": True,
        "note": (f"بنود بسنوات بيانات أقدم من {S.vintage_hard_years()} سنوات "
                 f"({ys}) — تصلح سياقاً فقط ولا تُبنى عليها خلاصة (§2.4)")}]


def _check_economics_present(dr: dict) -> list[dict]:
    """الموجة ٣ (تحذيري): توفّرت مرساة سعر مرصودة لكن قسم الاقتصاد غاب من
    العرض — «إعلان استحالة التسعير ليس مخرجاً مقبولاً» (§5.4)."""
    # **الموجة C (البند E-08).** الشرطُ كان `isinstance(value, (int, float))`
    # وحدَه — وبعثةُ الأسعار على المسار العميق تُعيد **جملاً**، فكان الفحصُ
    # **خامداً بنيوياً**: لا يُطلِق أبداً مهما غاب قسمُ الاقتصاد. فحصٌ لا
    # يُطلِق ليس فحصاً، وحضورُه في القائمة يوهم بتغطيةٍ غيرِ موجودة.
    from silk_economics import _findings_of, _fv, price_numbers_in_text
    def _is_price(f) -> bool:
        val = _fv(f)
        if isinstance(val, bool):
            return False
        if isinstance(val, (int, float)):
            return True
        return bool(price_numbers_in_text(val))
    has_price = any(
        _is_price(f)
        for f in _findings_of((dr.get("missions") or {}).get("pricing_scout")))
    eco = dr.get("economics") or {}
    if not has_price or (eco.get("reverse_solve") or {}).get("max_exw"):
        return []
    # البند 5 (أمر إصلاح المحرّك): حلٌّ معلَّق **بفجوةٍ تسمّي الناقص**
    # («غير محسوب — يلزم: حجم العبوة/العملة») ليس «غائباً رغم المدخلات» —
    # المدخلات نفسها هي الناقصة، والغياب معلَنٌ لا صامت. الفحص يبقى لحالة
    # الغياب الصامت (سعرٌ صالح ولا نموذج ولا فجوة).
    # الصدرُ صار «يلزم:» بلغة القارئ (الموجة د-٤) و«الناقص:» مفردةٌ داخلية؛
    # الحارسُ يعرف الصيغتين كي لا يُطلِق على فجوةٍ معلَنةٍ بالصياغة الجديدة
    # ولا على تقريرٍ مخزَّنٍ بالقديمة.
    if any(("الناقص" in str(g) or "يلزم:" in str(g))
           for g in (eco.get("gaps") or [])):
        return []
    return [{
        "check": "economics_missing_despite_inputs", "repairable": True,
        "note": ("سعر رف منافس مرصود لكن النموذج الاقتصادي (الحل العكسي "
                 "لأقصى سعر مصنع) غائب من العرض — راجع silk_economics")}]


def _check_price_comparability(dr: dict, lang: str = "ar") -> list[dict]:
    """الموجة ٣ (تحذيري): مرساة السعر تحمل فجوات قابلية مقارنة (وحدة/صرف/
    أساس تقييم) — تُعلن للمشغّل كي لا تُقارن أسعار على أسس مختلفة (§4.4).

    **البند S-03.** ادّعاءُ الكيلوجرام كان يُلتقَط بالعربية وحدَها (`/كجم`)،
    فتقريرٌ إنجليزيّ يقارن «per kg» فوق مرساةٍ غير مطبَّعة يمرّ بلا إعلان."""
    anchor = (dr.get("economics") or {}).get("anchor_price") or {}
    gaps = anchor.get("gaps") or []
    # يطلق فقط حين يقارن التقرير فعلاً على أساس الكيلوجرام بلا تطبيع —
    # تحذير دائم-الاشتعال لا يقرؤه أحد (مراجعة §58: لا ضجيج بنيوي).
    text = ((dr.get("report") or {}).get("text") or "")
    per_kg_claimed = _hits(text, "per_kg_claim", lang)
    if not gaps or not per_kg_claimed or anchor.get("per_kg") is not None:
        return []
    return [{
        "check": "price_comparability_gaps", "repairable": True,
        "note": ("مرساة السعر غير مكتملة التطبيع: " + "؛ ".join(gaps)
                 + " — لا مقارنة سعرية على أسس مختلفة قبل سدّها")}]


def _check_generic_conversion_refusal(dr: dict,
                                      lang: str = "ar") -> list[dict]:
    """الموجة ٣ (تحذيري، تعديل مالك ٢): عبارة «يتعذر التحويل» العامة ممنوعة
    — التعذر يُعلن فقط مع تسمية الخاصية الفيزيائية المفقودة تحديداً.

    **البند S-04.** المِجَسّ العربيّ وحدَه كان يترك «conversion is not
    possible» الإنجليزية تمرّ — وهي بعينها العبارةُ العامة الممنوعة."""
    text = ((dr.get("report") or {}).get("text") or "")
    if _hits(text, "generic_conversion_refusal", lang):
        return [{
            "check": "generic_conversion_refusal", "repairable": True,
            "note": ("عبارة «يتعذر التحويل» العامة وردت في التقرير — سمِّ "
                     "الخاصية الفيزيائية المفقودة تحديداً (الكثافة/حجم "
                     "العبوة) أو طبّق ثابت سجل التحويل بمصدره")}]
    return []


_HS_TOKEN_RE = re.compile(r"\b(\d{6})\b")
_HS_CONTEXT_RE = re.compile(r"(?:HS|رمز|البند|بند)")


def _check_hs_consistency_lock(view_or_dr: dict, dr: dict) -> list[dict]:
    """الموجة ٤ (Gate B تحذيري — §3.3): رمز واحد محسوم في التقرير كله.
    أي رمز سداسي في سياق HS يخالف الرمز المحسوم — ولم يُفصَح عنه (مرشّح/
    مجاور/شقيق ضمن نفس البند) — يقوّض كل كمية لاحقة بصمت."""
    resolved = str(view_or_dr.get("hs_code")
                   or (view_or_dr.get("header") or {}).get("hs_code") or "")
    if not re.fullmatch(r"\d{6}", resolved):
        return []
    text = ((dr.get("report") or {}).get("text") or "")
    allowed = {resolved}
    deriv = dr.get("hs_derivation") or {}
    prov = dr.get("hs_provenance") or {}
    for extra in (deriv.get("hs6"), prov.get("hs6")):
        if extra:
            allowed.add(str(extra))
    strays = set()
    for m in _HS_TOKEN_RE.finditer(text):
        tok = m.group(1)
        if tok in allowed:
            continue
        # أشقّاء نفس البند الرباعي مشروعون (عرض التفكيك — §3.2 البديل المفضّل).
        if tok[:4] == resolved[:4]:
            continue
        # سياق HS **قبل** الرمز فقط («رمز HS 190531») — النافذة الثنائية
        # كانت تلتقط رقماً بريئاً تليه كلمة «رمز» في جملة أخرى.
        ctx = text[max(0, m.start() - 20):m.start()]
        if _HS_CONTEXT_RE.search(ctx):
            strays.add(tok)
    if not strays:
        return []
    return [{
        "check": "hs_consistency_lock", "repairable": True,
        "note": ("رموز HS مخالفة للرمز المحسوم "
                 f"{resolved} وردت في التقرير بلا إفصاح: "
                 f"{'، '.join(sorted(strays))} — رمز واحد محسوم في كل "
                 "الأقسام، وأي رمز آخر يُذكر بإفصاح صريح (§3.3)")}]


def _check_spec_evidence_coherence(dr: dict) -> list[dict]:
    """الموجة ٤ (تحذيري — §3.4): رمز غير مؤكَّد يستلزم أثر إعادة التأطير
    (وسم الفئة المجاورة) في الحدود أو النص — غيابه = أرقام فئة مجاورة
    تُقرأ كمقاييس فعلية."""
    conf = dr.get("hs_confirmation") or {}
    if conf.get("confirmed") is not False:
        return []
    try:
        from silk_hs_confirm import CONTEXTUAL_TAG
    except Exception:
        return []
    text = ((dr.get("report") or {}).get("text") or "")
    limits = " ".join(str(l) for l in (dr.get("limits") or []))
    deriv_note = (dr.get("hs_derivation") or {}).get("substitution_note") or ""
    if CONTEXTUAL_TAG in text or CONTEXTUAL_TAG in limits or deriv_note:
        return []
    return [{
        "check": "spec_evidence_coherence", "repairable": True,
        "note": ("الرمز غير مؤكَّد لمواصفة المنتج ولا أثر لإعادة تأطير "
                 "«فئة مجاورة — مؤشر سياقي» في الحدود أو النص — أرقام "
                 "الفئة المجاورة ستُقرأ كمقاييس فعلية (§3.4)")}]


def _check_curated_reference_consulted(dr: dict) -> list[dict]:
    """هل استندت بعثةُ الاشتراطات إلى **المرجع المُقنَّن** فعلاً؟ (البند R-02)

    الوضعُ بعد الدحض العدائيّ في تدقيق الموجة A: الطبقةُ التنظيمية **ليست**
    غائبةً عن المسار العميق — تصلها عبر أداة `lookup_reference` التي تنادي
    `RequirementsAgent`، وبعثةٌ لا تُنتِج بنداً واحداً تُصنَّف `failed` فيُطلِق
    `agent_failed` وهو حاجزٌ أصلاً. فالخطرُ المتبقّي أضيقُ ممّا قُدِّر أوّلاً،
    وهو حقيقيّ مع ذلك: **قد يُرضي النموذجُ البعثةَ ببحث ويبٍ وحدَه**، فتصل
    اشتراطاتُ الدخول من صفحةٍ عامّة بدل لائحةٍ مستشهَدةٍ برقمها — وهذا أخطرُ
    صنفٍ من المحتوى يُخطئ فيه تقرير (نصيحةٌ تنظيمية).

    الفحصُ **تحذيريّ** لا حاجز: المرجعُ مُقنَّنٌ لثلاثةٍ وثلاثين سوقاً من ٣٨،
    فسوقٌ خارج تغطيته يُعلِن «تحقّق محلياً» بصدق — وحجبُ التقرير عندها عقابٌ
    على صدقٍ لا على عيب. الترقيةُ إلى حاجزٍ بعد توسيع المدوّنة (الموجة C).
    """
    m = (dr.get("missions") or {}).get("customs_requirements")
    if not m:
        return []
    failed = (m.get("failed") if isinstance(m, dict)
              else getattr(m, "failed", True))
    if failed is not False:
        return []          # فشلُ البعثة يلتقطه `agent_failed` الحاجز
    findings = (m.get("findings") if isinstance(m, dict)
                else getattr(m, "findings", None)) or []
    marker = "requirements reference"
    hit = False
    for f in findings:
        get = (f.get if isinstance(f, dict)
               else (lambda k, d=None, _o=f: getattr(_o, k, d)))
        blob = f"{get('source', '')} {get('note', '')}".lower()
        if marker in blob or "eur-lex" in blob or "official portal" in blob:
            hit = True
            break
    if hit:
        return []
    return [{
        "check": "curated_reference_not_consulted", "repairable": True,
        "note": ("قسم الاشتراطات لم يستند إلى المرجع التنظيميّ المُقنَّن "
                 "(جدول requirements) — اشتراطاتُ الدخول هنا من بحثٍ عامّ لا "
                 "من لائحةٍ مستشهَدةٍ برقمها؛ تحقّق محلياً قبل الاعتماد")}]


def _check_access_timeline_presence(dr: dict, lang: str = "ar",
                                    regulatory: dict | None = None) -> list[dict]:
    """الموجة ٥ (تحذيري — §5.5): بعثة الاشتراطات نجحت لكن التقرير لا يذكر
    «المدة الكلية» للنفاذ لا كمدى ولا كفجوة معلنة — القيد الفعلي على
    الدخول غالباً، وأكثر ما يُسقَط."""
    m = (dr.get("missions") or {}).get("customs_requirements") or {}
    failed = m.get("failed") if isinstance(m, dict) else getattr(m, "failed", True)
    if failed is not False:
        return []
    text = ((dr.get("report") or {}).get("text") or "")
    # **البند S-05 (كاذبُ الاشتعال).** المِجَسّ العربيّ وحدَه كان يجعل تقريراً
    # إنجليزياً **صحيحاً** («Total lead time: 45–60 days») يُلام على نقصٍ
    # ليس فيه — وبملاحظةٍ عربية تُحقَن في مسارٍ إنجليزيّ.
    if _hits(text, "access_timeline", lang):
        return []
    # **الموجة C (R-04).** مطابقةُ العبارة وحدَها كانت المعيار: تقريرٌ يكتب
    # «المدة الكلية» بلا حساب يمرّ، وتقريرٌ يحسب المدّةَ بصياغةٍ أخرى يُلام.
    # الآن الحسابُ البنيويّ يسبق النثر — وإن حُسِبت المدّةُ فعلاً فالملاحظةُ
    # تصير «اذكرها» لا «احسبها»، وإن كانت فجوةً مقنَّنةً فالسببُ يُسمّى.
    # درس 186: الحالة التنظيمية في `view["regulatory"]` (المستوى الأعلى) لا
    # داخل deep_research — كان `dr.get("regulatory")` يعطّل فرعَي «المدة محسوبة»
    # و«فجوة معلنة» صامتاً فينحطّ الفحص للرسالة العامة. تُمرَّر الآن من العرض.
    tl = ((regulatory or dr.get("regulatory") or {}).get("access_timeline")
          or {})
    if tl.get("total_days"):
        return [{
            "check": "access_timeline_missing", "repairable": True,
            "note": ("المدةُ الكلية للنفاذ محسوبةٌ من المرجع المقنَّن "
                     f"({tl['total_days'].get('min')}–"
                     f"{tl['total_days'].get('max')} يوماً) ولم يذكرها "
                     "التقرير — أضِفها إلى قسم الاشتراطات")}]
    if tl.get("gap"):
        return [{
            "check": "access_timeline_missing", "repairable": True,
            "note": f"المدةُ الكلية للنفاذ فجوةٌ معلنة: {tl['gap']}"}]
    return [{
        "check": "access_timeline_missing", "repairable": True,
        "note": ("قسم الاشتراطات لا يذكر «المدة الكلية من قرار الدخول حتى "
                 "أول شحنة نظامية» — تُذكر كمدى أو كفجوة معلنة (§5.5)")}]


# أزواج أشكال المنتج المتعارضة (Gate D بند 5): مرساة سعر بشكل مخالف للشكل
# الموصى به تُفسد كل تسعير لاحق. أزواج معروفة لا لغويات عامة.
_FORM_CONFLICTS = {
    "UHT": ("طازج",), "طويل الأجل": ("طازج",),
    "طازج": ("UHT", "مجفف", "مجمد", "طويل الأجل"),
    "مجفف": ("طازج",), "مجمد": ("طازج",),
}


def _check_anchor_matches_recommended_form(dr: dict) -> list[dict]:
    """الموجة ٣/سدّ الخياطة (تحذيري — Gate D بند 5): مرساة السعر تطابق شكل
    المنتج الموصى به — توصية UHT لا تُبنى على سعر طازج. يستيقظ فقط حين
    تحمل بطاقة المنتج حقل الشكل (لا لغويات تخمينية)."""
    eco = dr.get("economics") or {}
    form = str(eco.get("product_form") or "").strip()
    anchor = eco.get("anchor_price") or {}
    if not form or not anchor:
        return []
    blob = f"{anchor.get('source') or ''} {anchor.get('note') or ''}"
    for key, conflicts in _FORM_CONFLICTS.items():
        if key in form:
            hit = next((c for c in conflicts if c in blob), None)
            if hit:
                return [{
                    "check": "anchor_form_mismatch", "repairable": True,
                    "note": (f"شكل المنتج الموصى به «{form}» لكن مرساة "
                             f"السعر مرصودة لمنتج «{hit}» — كل تسعير لاحق "
                             "يجب أن يُبنى على الشكل الموصى به (§5.3)")}]
    return []


def _report_text(dr: dict) -> str:
    """نصّ التقرير المكتوب — نقطة قراءة واحدة لحرّاس العائلة الجدد."""
    return ((dr or {}).get("report") or {}).get("text") or ""


def _check_plain_language(view: dict, dr: dict) -> list[dict]:
    """لغة التاجر (قرار المالك 2026-08-19، تحذيري): اختصارٌ إنجليزيّ عارٍ
    **نجا** من التبسيط داخل نثرٍ عربيّ يصل العميل.

    يستعمل **نفس قواعد سياق المُبسِّط** لا مجرّد وجود الحروف: «SAM Food
    Trading BV» اسمُ شركةٍ و«World Bank LPI» اسمُ مصدر — كلاهما يبقى عمداً،
    فوسمُه تحذيراً إنذارٌ كاذبٌ يتكرّر في كلّ تقرير (مراجعة ذاتية §58).

    (فحصُ «الشرح المقحوم» أُسقِط عمداً: التبسيطُ يحذف الصيغة `(gloss)` حتمياً
    قبل الوصول، فكان الشرطُ لا يتحقّق أبداً — فحصٌ ميّت. الإصلاحُ الحتميّ
    مقفولٌ باختباره في tests/test_plain_language_reports.py.)
    """
    from silk_style_contract import PLAIN_TERMS
    raw = _report_text(dr)
    if not raw:
        return []
    try:
        from silk_reports import _is_arabic_prose_context, _plain_language
        text = _plain_language(raw)
    except Exception:  # noqa: BLE001 — الفحص لا يُسقط البوابة
        return []
    survivors = []
    for term in PLAIN_TERMS:
        for m in re.finditer(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", text):
            before = text[max(0, m.start() - 60):m.start()]
            after = text[m.end():m.end() + 30]
            if _is_arabic_prose_context(before, after):
                survivors.append(term)
                break
    if not survivors:
        return []
    return [{"check": "plain_language_jargon", "repairable": True,
             "note": (f"اختصارات إنجليزية عارية نجت إلى نصّ العميل: "
                      f"{'، '.join(sorted(set(survivors)))} — تُستبدَل بمعناها")}]


def _check_sufficiency_contradiction(view: dict, dr: dict) -> list[dict]:
    """LESSONS 88 (حارس عائلة، تحذيري) — سطر كفاية يقول «لا شيء» بينما سجلّ
    الفجوات غير فارغ = قناتا فجوات لا واحدة. يسري على كل دراسة وكل منتج."""
    suff = str(((view or {}).get("decision") or {}).get("sufficiency") or "")
    if not suff:
        return []
    n_gaps = len((dr or {}).get("gap_register")
                 or (dr or {}).get("limits")
                 or (view or {}).get("limits") or [])
    if n_gaps > 0 and "لا شيء" in suff:
        return [{"check": "sufficiency_contradiction", "repairable": True,
                 "note": (f"سطر كفاية البيانات يقول «لا شيء» بينما التقرير "
                          f"يسرد {n_gaps} بنداً يحتاج تحققاً — سجلّ فجوات "
                          "واحد لا اثنان (LESSONS 88)")}]
    return []


def _check_metric_value_conflict(view: dict, dr: dict,
                                 lang: str = "ar") -> list[dict]:
    """حارس عائلة (تحذيري): قيمة مورّد واحد تُنسب في النص إجماليَّ واردات
    السوق — قيمتان مختلفتان لنفس المؤشر في وثيقة واحدة. الكشف بنيوي من
    الحقيقتين المهيكلتين (إجمالي الواردات vs قيمة المورّد)، لا لغويات."""
    text = _report_text(dr)
    if not text:
        return []
    top = ((view or {}).get("markets") or [{}])[0] or {}
    tam = None
    for c in top.get("components_detail") or []:
        if isinstance(c, dict) and c.get("name") == "market_size":
            tam = c.get("value")
            break
    if not isinstance(tam, (int, float)) or tam <= 0:
        return []
    for sc in (top.get("supplier_countries") or [])[:6]:
        v = sc.get("value_usd") if isinstance(sc, dict) else None
        if not isinstance(v, (int, float)) or v <= 0 or abs(v - tam) < 1:
            continue
        # صنف الأرقام العشرية يحمل نقطة، فلا تُستعمل النقطة فاصلَ مقطع هنا
        # (كانت تقطع «7.67» عند النقطة فيفلت التناقض).
        partner = str(sc.get("partner") or "").strip()
        # **مراجعة ذاتية §58.** المِجَسّ كان «واردات» حرفياً، فالحارسُ صامتٌ
        # على تقريرٍ إنجليزيّ — ورموزُ التهريب `\n` فيه أخفَته عن كاشف
        # الأحادية اللغوية نفسِه.
        for m in _segment_re("market_imports", lang).finditer(text):
            seg = m.group(0)
            # «واردات الأردن **من السعودية** 7.67 مليون» جملةٌ صحيحةُ المقام —
            # تسميةُ المورّد داخل المقطع تنفي التناقض (مراجعة ذاتية §58).
            if partner and partner in seg:
                continue
            if _same_magnitude_token(seg, v) and not _same_magnitude_token(seg, tam):
                return [{"check": "metric_value_conflict", "repairable": True,
                         "note": (f"قيمة المورّد «{sc.get('partner')}» "
                                  f"({v}) تظهر منسوبةً إلى واردات السوق "
                                  f"بينما الإجمالي المرصود ({tam}) — "
                                  "المقام يجب أن يُعلَن مع كل نسبة")}]
    return []


def _same_magnitude_token(segment: str, value: float) -> bool:
    """هل يحمل المقطع رقماً يطابق القيمة بمقياسها (خام أو بالمليون)؟"""
    for tok in re.findall(r"\d+(?:[.,]\d+)?", segment):
        try:
            n = float(tok.replace(",", ""))
        except ValueError:
            continue
        for scaled in (n, n * 1_000_000, n * 1_000):
            if value and abs(scaled - value) / max(abs(value), 1.0) < 0.01:
                return True
    return False


def _check_lpi_year_mismatch(dr: dict) -> list[dict]:
    """حارس عائلة (تحذيري): سنة LPI في النص = سنة القيمة المجلوبة. البرومبت
    كان يتطوّع بـ«2023 هي الأحدث» فيعيد الكاتب ختم قيمة 2018 بها."""
    text = _report_text(dr)
    if not text:
        return []
    src_year = None
    for rep in (dr.get("missions") or {}).values():
        if src_year:
            break
        for f in ((rep or {}).get("findings") or []):
            if not isinstance(f, dict):
                continue
            # درس 186: اكتشافاتُ /research لا تحمل حقل `metric` (بعثاتُ العمق
            # تطابق LPI بعبارةِ الملاحظة لا بحقل)؛ القراءة على `metric` وحدها
            # عمّت الحارسَ على المسار الوحيد الذي تعمل عليه البوابة. نطابق
            # الحقلَ **أو** عبارةَ LPI في ملاحظةٍ تحمل سنةً.
            note = str(f.get("note") or "")
            is_lpi = (f.get("metric") == "logistics_lpi"
                      or "LPI" in note or "الأداء اللوجستي" in note)
            if not is_lpi:
                continue
            # أوّلُ بندٍ **يحمل سنةً فعلاً** يحكم — بندٌ لاحقٌ بلا سنة كان
            # يُصفّر المرجع فيُعطّل الحارس صامتاً (مراجعة ذاتية §58).
            got = f.get("data_year") or _year_in(note)
            if got:
                src_year = got
                break
    if not src_year:
        return []
    cited = {y for y in re.findall(r"LPI[^\n]{0,80}?(20\d{2})", text)}
    cited |= {y for y in re.findall(r"(20\d{2})[^\n]{0,40}?LPI", text)}
    bad = sorted(y for y in cited if str(y) != str(src_year))
    if bad:
        return [{"check": "lpi_year_mismatch", "repairable": True,
                 "note": (f"سنة LPI في النص {bad} تخالف سنة القيمة المجلوبة "
                          f"{src_year} — السنة من المصدر حرفياً لا من "
                          "افتراض «الأحدث»")}]
    return []


def _year_in(text: str) -> str | None:
    m = re.search(r"(19|20)\d{2}", text or "")
    return m.group(0) if m else None


def _check_epistemic_verb_discipline(dr: dict, lang: str = "ar") -> list[dict]:
    """الموجة ٦ (تحذيري — §7.2): رقم مبني على معلمة معلنة (الحل العكسي
    بسيناريوهات) صيغ بفعل تقريري بلا صياغة شرطية قربه — طبقة «مُقدَّر»
    قُدِّمت بنحو «مرصود». حتمي: يفحص فقط أرقام المحرك المُعلمَنة المعروفة
    بنيوياً — لا تحليل نثر عام (سابقة D-25: انضباط أسلوبي غير حاجب)."""
    eco = dr.get("economics") or {}
    rs = eco.get("reverse_solve") or {}
    if not rs.get("scenarios"):
        return []          # لا معالم = لا شيء يُفحص
    text = ((dr.get("report") or {}).get("text") or "")
    token = str(rs.get("max_exw"))
    idx = text.find(token)
    if idx < 0:
        return []          # الرقم غير مذكور — فحص الحضور شأن فحص آخر
    ctx = text[max(0, idx - 120):idx + 120]
    # **البند S-06 (كاذبُ الاشتعال).** أفعالُ المعلمة (`PARAMETER_VERBS`)
    # عربيةٌ حرفية، فمتنٌ إنجليزيّ سليمُ الصياغة («Assuming the medium
    # scenario…») كان يُلام دائماً. المِجَسّ ثنائيُّ اللغة الآن.
    if _hits(ctx, "parameter_conditional", lang):
        return []
    return [{
        "check": "epistemic_verb_discipline", "repairable": True,
        "note": (f"أقصى سعر المصنع {token} مبني على معالم معلنة لكنه صيغ "
                 "بلا صياغة شرطية («بافتراض…»/«سيناريو…») قربه — طبقة "
                 "مُقدَّرة قُدِّمت بنحو مرصود (§7.2)")}]


def failure_record(gate: str, check: str, severity: str, detail: str,
                   action: str = "") -> dict:
    """سجل فشل موحّد (توجيه الجزء ٩): البوابة والبند، المدخل الناقص/غير
    الصالح، والفعل الذي يُصلحه — غلاف إضافي فوق الأشكال القائمة (409/
    AgentReport) لا بديل عنها."""
    return {"gate": gate, "check": check, "severity": severity,
            "detail": detail, "action": action}


# فحوصٌ تُمفصِل على عباراتٍ عربية حرفية — لا مرآةَ لها بعد على الإنجليزية.
# قائمةٌ **صريحة** كي يقرأ المشغّل ما لم يُفحَص؛ وتقصيرُها هدفُ موجةٍ لاحقة.
# **الموجة B (البندان G-06/G-08).** القائمةُ تقلّصت بثلاثة:
# `placeholder_leak` و`dangling_cross_reference` شُحنت لهما مرايا إنجليزية
# (كلاهما **حاجز**)، و`client_scaffold_leak` كان مُعلَناً «مُتخطّى» وهو يعمل
# على الإنجليزية أصلاً — نمطُه يطابق "So what" حرفياً. إعلانُ تخطٍّ كاذبٍ
# يُضعِف الثقةَ بالقائمة كلِّها، وهي مصدرُ صدقِ البوّابة أمام المشغّل.
#
# **موجةُ الخياطة.** والمرآةُ أصدق: قائمةٌ **ناقصة** أسوأُ من قائمةٍ كاذبة —
# المشغّلُ يقرأ ثلاثةَ بنودٍ فيظنّ الباقيةَ كلَّها قد جرت. وكانت ناقصةً فعلاً
# بسبعة فحوصٍ (`S-01`…`S-07`) خمدت صامتةً على تقريرٍ إنجليزيّ منذ الموجة ٠،
# اثنان منها **حاجزان**. السبعةُ صارت ثنائيةَ المِجَسّ (`_GATE_PROBES`)،
# والقائمةُ لم تعد تُصان بالذاكرة: قفلُ AST في
# `tests/test_gate_language_parity.py` يشتقّ الفحوصَ عربيةَ المِجَسّ من
# الشيفرة نفسِها ويُحمِّر CI على أيِّ بندٍ غيرِ مُعلَنٍ هنا.
# صيد الفجوات ٣: كانت القائمة تسمّي فحصين لا وجود لهما (confidence_band_label
# وstyle_alarmist — الاسمان المُصدَران confidence_band_mismatch
# وlanguage_quality_tone)، والاسمُ الخاطئ كان يخفي عن قفل G-06 نفسِه أنّ
# confidence_band_mismatch فحصٌ **حاجب** خامد على الإنجليزية. القاعدة (قفل
# G-06): فحصٌ حاجب لا يُعلَن خامداً — يُرآى. لذلك مُرئي في هذه الموجة ستةُ
# فحوصٍ حاجبة (confidence_value_conflict، off_market_currency،
# confidence_band_mismatch، verdict_label_conflict،
# tam_below_single_country_flow + تباين المرآة، evidence_body_numeric_*)،
# ولا يبقى معلَناً إلا التحذيريُّ الذي لا معنى لمرآته أو مرآتُه في قناة أخرى.
_AR_ONLY_CHECKS = (
    ("robotic_stock_phrase",
     "قائمةُ الحشو عربيةٌ — النصَّ الإنجليزيَّ يقيسه `HUMAN_VOICE_RULE_EN` "
     "في الموجّه، ولا مرآةَ بوابةٍ له بعد"),
    ("language_quality_tone",
     "قائمةُ العبارات المبالِغة عربية — المرآةُ الإنجليزية تحذيريّةٌ في "
     "قناة `language_quality`"),
    ("plain_language_jargon",
     "قاعدةُ «استبدل المصطلح بمعناه» عربيةٌ بطبعها؛ الإنجليزية تشرحه عند "
     "أوّل ورودٍ بدل استبداله (§34)"),
    ("currency_label_mismatch",
     "مِجَسّ تسمية العملة عربي — فحص تحذيري (قابل للإصلاح) خامد على "
     "الإنجليزية — فجوة معلنة"),
    ("unclassified_product_attribute",
     "نمط «الأساس + صفة» عربي التركيب (الصفة تلي الاسم)؛ الإنجليزية "
     "معكوسة الترتيب وخارج نطاقه — فجوة معلنة، وجدول ATTR_PHRASES "
     "الإنجليزي يبقى تحت الفحص الحاجب"),
)


def _view_lang(view: object) -> str:
    """لغة تقرير هذا العرض — يرفعها `silk_render.build_view` (الموجة ٠)."""
    import silk_i18n
    if isinstance(view, dict):
        return silk_i18n.normalize(view.get("report_language"))
    return silk_i18n.DEFAULT_LANG


# البند 3 (أمر إصلاح المحرّك) — مكوّنٌ تعلن اللوحةُ غيابَه بينما متنُ التقرير
# يسرده رقمياً (تقرير #11: «استقرار العملة لم يُرصَد» مقابل «الدينار ثابت عند
# 0.71 عبر 2021–2023»). الإبرُ **قويةُ الدلالة عمداً** (صيغُ السرد الفعلية لا
# كلماتٍ عامة) كي لا يُحجَب تقريرٌ بريء ذكر الكلمة في سطر فجوةٍ مشروع.
_PILLAR_BODY_NEEDLES = {
    "fx_stability": ("سعر الصرف", "الدينار", "سعر صرف"),
    "saudi_momentum": ("تستحوذ السعودية", "حصة السعودية", "الحصة السعودية"),
    "tam_log": ("إجمالي واردات", "حجم الواردات", "إجمالي الواردات"),
    "legibility": ("شهادة المنشأ",),
}
_PILLAR_COMPONENT_AR = {
    "fx_stability": "استقرار العملة", "saudi_momentum": "الحصة السعودية",
    "tam_log": "حجم واردات السوق", "legibility": "وضوح قائمة الاشتراطات",
}
# جملةُ فجوةٍ معلنة («لم يُرصَد إجمالي واردات السوق» في ملحق الحدود) ذكرٌ
# مشروع لا سرد — احتسابُها كان سيحجب تقريراً أميناً أعلن فجوته بنفسه
# (مراجعة §58 على البند 3: فحصٌ مُفشِل عتبتُه أعلى من إبرة الكلمة وحدها).
_GAP_SENTENCE_TOKENS = ("غير مرصود", "غير مرصودة", "لم يُرصَد", "لم يرصد",
                        "لم تُرصَد", "لم ترصد", "غير متاح", "غير محسوب",
                        "غير محسوبة", "لم يُحدَّد", "لم يحدد", "لم يحدَّد",
                        "يتعذر الحساب", "يتعذّر الحساب",
                        "لا يمكن حساب", "لعدم رصد", "قبل رصد",
                        "المعطى الناقص:",
                        # موجة سدّ الفجوات الثانية: مرايا إنجليزية — جملة
                        # فجوةٍ إنجليزية صادقة كانت تُفشِل الفحص زوراً.
                        "not available", "not calculated", "not computed",
                        "not observed", "cannot be computed",
                        # دورة C4: «missing» العارية تحت-سلسلة شائعة
                        # (dismissing) وتعفي جملاً ليست فجوات — الصيغ
                        # المقيدة فقط.
                        "missing:", "is missing", "are missing")


def _norm_gap_tokens() -> tuple:
    return tuple(_norm_ar(g) for g in _GAP_SENTENCE_TOKENS)


def _narrated_outside_gap_sentences(text: str, needles: tuple) -> bool:
    """هل يسرد المتنُ المكوّنَ خارج جملِ الفجوة المعلنة؟ التقطيع على فواصل
    الجمل فقط (لا النقطتين) كي يبقى صفُّ الجدول «إجمالي الواردات: غير
    مرصود» جملةً واحدة. المطابقة عبر المُطبِّع الواحد `_norm_ar`."""
    n_needles = tuple(_norm_ar(n) for n in needles)
    gaps = _norm_gap_tokens()
    # A decimal point is not a sentence boundary; headings name an indicator
    # without asserting that it was measured. Keep observed prose checked.
    for seg in re.split(r"(?<!\d)\.|\.(?!\d)|[\n؟!؛]", _norm_ar(text)):
        heading = seg.strip().strip("#* :|").strip()
        if heading in n_needles:
            continue
        if (any(n in seg for n in n_needles)
                and not any(g in seg for g in gaps)):
            return True
    return False


def _check_pillar_narrative_sync(view: dict) -> list[dict]:
    """`pillar_narrative_sync`: عمودٌ يقول «X غير مرصود» والمتنُ يذكر X —
    مصدران متنافران في مصنوعٍ واحد؛ فشلُ بناءٍ لا ملاحظةَ أسلوب."""
    row = ((view.get("markets") or [None])[0]
           if isinstance(view, dict) else None) or {}
    # مفتاح العرض الحقيقي `entry_decision` (silk_render.py:3170) أولاً —
    # القراءة على «decision» وحده جعلت الحارس ميّتاً على كل عرض فعلي
    # (درس 186)؛ الاحتياط يبقي صفوفاً خاماً من مستهلك قديم مغطاة.
    dec = row.get("entry_decision") or row.get("decision") or {}
    pillars = dec.get("pillars") if isinstance(dec, dict) else None
    text = (((view.get("deep_research") or {}).get("report") or {})
            .get("text") or "")
    if not pillars or not text:
        return []
    findings = []
    for p in pillars.values():
        if not isinstance(p, dict):
            continue
        for comp in (p.get("missing") or []):
            needles = _PILLAR_BODY_NEEDLES.get(comp)
            if needles and _narrated_outside_gap_sentences(text, needles):
                findings.append({
                    "check": "pillar_narrative_sync", "repairable": False,
                    "note": (f"اللوحة تعلن «{_PILLAR_COMPONENT_AR.get(comp, comp)}"
                             "» غير مرصود بينما متن التقرير يسرده — العمود "
                             "والسرد يقرآن من مصدرين مختلفين")})
    return findings


# البند 4 (أمر إصلاح المحرّك) — بيانات التجارة كلُّها تحت بندٍ (heading،
# أول ٤ أرقام) بينما التوصياتُ تسمّي منتجاً من بندٍ آخر (تقرير #11: البيانات
# تحت 0401 «حليب غير مركّز» والتوصية تستهدف المجفف/المكثف = 0402) — فالحجم
# والحصة وHHI والسعر لا تنطبق على المنتج الموصى به. مرجعٌ داخليّ: إبرة سمةِ
# منتجٍ ← بندُها الحقيقي. الصفوف **بصيغ الكتابة الفعلية** من التقريرين
# (منتجٌ+سمة معاً — «المجفف» وحدها كانت ستلتقط «التين المجفف» في بندٍ آخر)،
# وتُقارَن بعد تجريد التشكيل. عائلة الألبان هي الحادثة المثبتة؛ عائلاتٌ
# جديدة تُضاف صفوفَ بياناتٍ لا منطقاً.
# انحدار البند 4 الثاني (#13 «حليب الأطفال» بند 1901 والفحص أعمى): القائمة
# المجمّدة هنا كانت «تتأخر منتجاً واحداً دائماً» — صارت صفوف بيانات في
# المرجع الواحد `silk_hs_reference.ATTR_PHRASES` (يستهلكه الفحص أدناه)،
# والاسم المحلي يبقى مرساةً للأقفال القائمة (الدرس 124).
from silk_hs_reference import ATTR_PHRASES as _HS_ATTR_HEADINGS
# نطاق المسح: نافذتا التوصية (الخلاصة التنفيذية + التوصيات الاستراتيجية)
# حصراً — الدرس ٤٢: فحص النافذة لا كامل المستند؛ ذكرُ 0402 في شرح تعريف
# البند (§2) أو في جدول أسعار التجزئة (§6) مشروعٌ لا توصية.
_RECOMMENDATION_WINDOW_TITLES = ("الخلاصة التنفيذية", "التوصيات الاستراتيجية",
                                 "Executive Summary",
                                 "Strategic Recommendations")


def _check_hs_recommendation_match(view: dict) -> list[dict]:
    """`hs_recommendation_match`: التوصياتُ تسمّي سمةَ منتجٍ خارج البند الذي
    جُمعت بياناتُ التجارة تحته — تسليمُ التقرير يتوقف برسالة صريحة (البند 4:
    «قِيسَت الفئة الصحيحة ووُصي بفئةٍ أخرى» هو خطأ #10 منقولاً لا مُصلَحاً)."""
    hs = str(view.get("hs_code")
             or (view.get("header") or {}).get("hs_code") or "").strip()
    text = (((view.get("deep_research") or {}).get("report") or {})
            .get("text") or "")
    if len(hs) < 4 or not hs[:4].isdigit() or not text:
        return []
    heading = hs[:4]
    from silk_ai_judge import _section_window
    windows = [w for t in _RECOMMENDATION_WINDOW_TITLES
               if (w := _section_window(text, t))]
    if not windows:
        return []
    scope = _norm_ar("\n".join(windows))
    findings, seen = [], set()
    for needle, (attr_heading, label) in _HS_ATTR_HEADINGS.items():
        if attr_heading != heading and label not in seen \
                and _norm_ar(needle) in scope:
            seen.add(label)
            findings.append({
                "check": "hs_recommendation_match", "repairable": False,
                "note": (f"التوصيات تسمّي «{label}» وهو بند HS {attr_heading} "
                         f"بينما بيانات التجارة جُمعت تحت البند {heading} — "
                         "الأرقام المعروضة لا تنطبق على المنتج الموصى به")})
    return findings


# صفات عمومية/حالية لا سمات فئة منتج — لا تستدعي حسم بند (قائمة قصيرة
# مغلقة الطبيعة، عكس فضاء المنتجات المفتوح).
_ATTR_GENERIC_QUALIFIERS = frozenset({
    "عام", "حالي", "متخصص", "اساسي", "جديد", "مستورد", "محلي",
    "فاخر", "تقليدي", "حديث", "مشبع", "موصى", "مقترح", "مهيمن",
    "منافس", "مماثل", "بديل"})


def _check_unclassified_product_attribute(view: dict) -> list[dict]:
    """كاشف «سمة منتج غير مصنّفة» (تصحيح المُشرِف على #13): توصيةٌ تسمّي
    «{المنتج الأساس} + صفة معرَّفة» وصفتُها ليست في تعريف بند الدراسة ولا
    في مرجع `ATTR_PHRASES` — تُعلَن ملاحظةً **تحذيرية للمشغّل** يجب حسمها،
    لا صمت: الجدول تعدادٌ يتأخر منتجاً، وهذا الكاشف يلتقط ما لم يُعدَّد بعد
    (سابقتا #11 و#13 شُحنتا صامتتين). دورة C4: الصفة تُشترط معرَّفةً بـ«ال»
    (الصيغة الوصفية/الإضافية الفعلية — «حليب الأطفال»/«الحليب المجفف»)
    كي لا يلتقط الأفعال والجارّ والمجرور بعد الأساس؛ والعرضُ بالنص الخام
    لا المطبَّع؛ والملاحظة قابلة للإصلاح (تحذير مشغّل لا ملاحظة منهجية
    تُطبع للعميل).

    **منطقة العمى المعلنة** (قاعدة المُشرِف — كل فحص يصرّح بما لا يلتقطه):
    (أ) صفة **بلا أداة تعريف** («حليب بروتين» العارية) لا تُرى — ثمن إسكات
    الأفعال؛ (ب) صفة بعيدة عن كلمة الأساس (جملة منفصلة) لا تُرى؛
    (ج) التقارير الإنجليزية خارج نطاقه (مُعلَن في `_AR_ONLY_CHECKS`)؛
    (د) الصفات متعددة الكلمات تُلتقط بكلمتها الأولى فقط؛ (هـ) صفات
    الحال المشروعة داخل البند («الطازج») تُذكَر حين لا ترد في تعريفه —
    إعلانٌ زائد مقبول للمشغّل لا إيجابية حاجبة."""
    hs = str(view.get("hs_code")
             or (view.get("header") or {}).get("hs_code") or "").strip()
    product = str(view.get("product")
                  or (view.get("header") or {}).get("product") or "").strip()
    text = (((view.get("deep_research") or {}).get("report") or {})
            .get("text") or "")
    base_raw = product.split(" ")[0] if product else ""
    if len(hs) < 4 or not text or len(base_raw) < 3:
        return []
    from silk_ai_judge import _section_window
    windows = [w for t in _RECOMMENDATION_WINDOW_TITLES
               if (w := _section_window(text, t))]
    if not windows:
        return []
    raw_scope = "\n".join(windows)
    try:
        from silk_hs_reference import definition
        # التعريفان معاً (السداسي + الرباعي): «السائل» ترد في تعريف البند
        # 0401 الرباعي لا في سطر 040120 السداسي.
        defn = " ".join(filter(None, (definition(hs), definition(hs[:4]))))
    except Exception:  # noqa: BLE001 — مرجع غائب = لا استثناء تعريفي
        defn = ""
    # مطابقة التعريف على حدود كلمات مجرّدة من «ال» — دورة C4: «لوز» كانت
    # تسقط في substring داخل «وزنا» فيصمت الكاشف عن «حليب اللوز».
    def_tokens = {t[2:] if t.startswith("ال") else t
                  for t in re.findall(r"[ء-ي]+", _norm_ar(defn))}
    table = {_norm_ar(k) for k in _HS_ATTR_HEADINGS}
    base_n = _norm_ar(base_raw)
    # «كحليب البروتين»/«لحليب الأطفال»: أداة جر/عطف اختيارية قبل الأساس.
    # الدراسة الحية الرابعة (دورة العرض): التشكيل داخل الكلمة («المدعّم»)
    # كان يقطع الالتقاط عند الشدّة فتُعرض «المدع» مبتورة — الحركات ضمن الصنف.
    pat = re.compile(r"(?<![ء-ي])[كلبوف]?(?:ال)?" + re.escape(base_raw)
                     + r"\s+(ال[ء-يً-ْ]{3,})")
    unknown: list[str] = []
    for m in pat.finditer(raw_scope):
        q_raw = m.group(1)                       # «الأطفال» — بأداة التعريف
        q_bare = _norm_ar(q_raw)[2:]
        if (not q_bare or q_bare in _ATTR_GENERIC_QUALIFIERS
                or q_bare == base_n):
            continue
        if q_bare in def_tokens:
            continue      # صفة واردة في تعريف بند الدراسة نفسه — مشروعة
        phrase_n = f"{base_n} {_norm_ar(q_raw)}"
        if any(phrase_n in t or t in phrase_n for t in table):
            continue      # محسومة في المرجع — شأن الفحص الحاجب أعلاه
        if q_raw not in unknown:
            unknown.append(q_raw)
    if not unknown:
        return []
    return [{
        "check": "unclassified_product_attribute", "repairable": True,
        "note": ("التوصيات تسمّي سمات منتج لم يُحسم بندها الجمركي: «"
                 + "، ".join(unknown[:5])
                 + "» — تحقق من بند كل سمة قبل الاعتماد؛ أرقام التجارة "
                 f"المعروضة مجموعة تحت البند {hs[:4]} وحده")}]


# البند 5 (أمر إصلاح المحرّك) — رقم مشتق من مدخلات غير مرصودة (تقرير #11:
# «أقصى سعر مصنع = $0.3274/كجم» بأربع منازل فوق جدول أسعارٍ كلّه «يتعذّر
# الحساب») . المرجع الحتمي: الحل العكسي في `economics_view` — حين يكون
# معلَّقاً (مدخلُ حقيقةٍ غائب: أساس الكتلة/العملة/مرساة الرف) لا يجوز أن
# يظهر في المتن رقمٌ لأقصى سعر مصنع؛ البديل «غير محسوب — الناقص: [المدخل]».
_DERIVED_EXW_NEEDLES = ("أقصى سعر مصنع", "أقصى سعر للمصنع",
                        "أقصى سعر تسليم المصنع", "أقصى تكلفة خارج المصنع",
                        "max ex-factory", "maximum ex-factory",
                        "max ex-works", "maximum ex-works")
_ANY_DIGIT_RE = re.compile(r"[0-9٠-٩]")


def _check_derived_number_has_inputs(view: dict) -> list[dict]:
    """`derived_number_has_inputs`: رقمُ أقصى سعر مصنع في المتن بينما الحلّ
    العكسيّ المحسوب معلَّق (مدخلاته غير مرصودة) — الرقم غير قابل للتدقيق.
    جملةُ «غير محسوب — الناقص: …» هي البديل المشروع ولا تُحتسَب (نفس حارس
    سياق النفي في `pillar_narrative_sync`)."""
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    rs = ((dr.get("economics") or {}).get("reverse_solve") or {})
    if rs.get("max_exw") is not None:
        return []
    n_needles = tuple(_norm_ar(n) for n in _DERIVED_EXW_NEEDLES)
    gaps = _norm_gap_tokens()
    for seg in re.split(r"[.\n؟!؛]", _norm_ar(text)):
        if (any(n in seg for n in n_needles)
                and _ANY_DIGIT_RE.search(seg)
                and not any(g in seg for g in gaps)):
            return [{
                "check": "derived_number_has_inputs", "repairable": False,
                "note": ("المتن يعرض رقماً لأقصى سعر مصنع بينما الحل العكسي "
                         "المحسوب معلَّق لغياب مدخلاته المرصودة — رقم مشتق "
                         "بلا مدخلات لا يُسلَّم؛ البديل: «غير محسوب — "
                         "الناقص: [اسم المدخل]»")}]
    return []


# ── الصنف ٩: رقمٌ مشتقٌّ بلا إسناد · derived figure without provenance ─────
# **العيبُ المرصود:** خارطةُ الطريق تُسمّي «الشريحةَ القابلة للخدمة» و«نقطةَ
# التعادل» بأرقامٍ في إطارٍ محسوب، بينما المحرّكُ يُعلن البندَين نفسَهما
# **فجوةً** (`tier == "gap"`) في «أرقام القرار» — فيقرأ صاحبُ القرار رقماً
# لم يُحسَب أصلاً. و«أقصى خسارة» تصل رقماً واحداً شاملَ المظهر بينما أساسُها
# (كلفةُ الدخول) استُبعد منه الشحنُ غيرُ المتحقّق ورسومُ التسجيل.
#
# **الجذر:** لا قاعدةَ تقابل بين ما أعلنه المحرّك مجهولاً وما كتبه الكاتبُ
# محسوباً؛ فالكاتبُ يُعيد الاشتقاق بحرّية والبوابةُ لا تقيس التقابل.
#
# الأوّلُ حاجبٌ **خلف رايةِ الصنف ٩ فقط** (`_FLAGGED_FAIL_TRIGGERS`)؛ والثاني
# تحذيريّ. والمرجعُ في الحالتين حتميّ: بنودُ `decision_numbers` نفسُها.
_DN_STOPWORDS = ("من", "الى", "في", "حتى", "اول", "ان", "على", "عن",
                 "مع", "او", "و", "الي", "بعد", "قبل", "لكل")
_MAX_LOSS_NEEDLES = ("أقصى خسارة", "أقصى الخسارة", "سقف الخسارة",
                     "maximum loss", "max loss")
# إفصاحُ الاستبعاد المقبول قرب سقفِ المخاطرة — أيٌّ منها يُعفي (والمدى
# نفسُه إفصاحٌ: رقمان بينهما شَرطة يقولان إنّ الرقم غيرُ قاطع).
_EXCLUSION_DISCLOSURE = ("خارج", "غير محسوب", "غير محسوبة", "غير متحقق",
                         "غير متحققة", "مستبعد", "مستبعدة", "لا يشمل",
                         "لا تشمل", "يُستبعد", "يستبعد", "بلا سعر",
                         "excluded", "not included", "does not include")
_ENGINE_EXCLUSION_MARKS = ("خارج المجموع", "يُستبعد من المجموع",
                           "فيُستبعد من المجموع")
# المدى: رقمان بفاصلٍ صريح («7,100–10,700»، «بين 7,100 و 10,700»،
# «7,100 to 10,700»). العطفُ بين رقمين يُقبَل فاصلَ مدىً — ثمنُه المُعلَن
# أنّ رقمين غيرَ مرتبطين في جملةِ السقف نفسِها يُعفيانها، وهو ثمنٌ أهونُ
# من معاقبةِ الصيغةِ العربيّةِ الأشهرِ للمدى.
_RANGE_MARK_RE = re.compile(
    r"\d[\s,.\d]*\s*(?:[-–—]|و|الى|إلى|to)\s*\d")


def _dn_needle(name: object) -> str:
    """إبرةُ بندٍ من «أرقام القرار»: أقصرُ مقطعٍ **متّصلٍ** من اسمه يبدأ من
    أوّله ويضمّ كلمةً دالّةً واحدةً على الأقلّ بعد الأولى.

    «نقطة التعادل» ⇒ «نقطة التعادل»؛ «أقصى خسارة إن فشل الدخول» ⇒ «أقصى
    خسارة»؛ «الزمن من القرار إلى أول فاتورة» ⇒ «الزمن من القرار» (الكلمةُ
    الثانيةُ حرفُ جرٍّ فتُضَمّ الثالثة) — كي لا تبتلعَ الإبرةُ نثراً عاماً.
    """
    words = [w for w in _norm_ar(str(name or "")).split() if w]
    if len(words) < 2:
        return " ".join(words)
    for i in range(1, len(words)):
        if words[i] not in _DN_STOPWORDS and len(words[i]) >= 3:
            return " ".join(words[:i + 1])
    return " ".join(words[:2])


# بنودٌ **زمنية** بطبعها: رقمُ الزمن فيها قيمةٌ لا جدولٌ زمنيّ.
_TIME_ITEM_RE = re.compile(r"زمن|مدة|مدّة|توقيت")
# رقمٌ ملتصقٌ بوحدةِ زمنٍ — جدولٌ زمنيٌّ لا قيمةُ بند. الإبرةُ تُقرَأ على
# النصِّ **المطبَّع** (`_norm_ar` يطوي الهمزة)، فكلُّ وحدةٍ بصيغتيها.
_TIME_QTY_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:يوم|أيام|ايام|يوما|أسبوع|اسبوع|أسابيع|اسابيع|"
    r"أسبوعا|اسبوعا|شهر|شهور|أشهر|اشهر|شهرا|سنة|سنه|سنوات|سنين|عام|أعوام|"
    r"اعوام|ربع|أرباع|ارباع)")


def _shows_a_value(seg: str, time_item: bool) -> bool:
    """هل تعرض الجملةُ **قيمةً** للبند، أم جدولاً زمنياً فحسب؟"""
    if not _ANY_DIGIT_RE.search(seg):
        return False
    if time_item:
        return True
    return bool(_ANY_DIGIT_RE.search(_TIME_QTY_RE.sub(" ", seg)))


def _check_reference_to_nonexistent_figure(view: dict) -> list[dict]:
    """`reference_to_nonexistent_figure` (الصنف ٩ — حاجبٌ خلف رايته): المتنُ
    يُسمّي بندَ قرارٍ برقمٍ في إطارٍ محسوب بينما المحرّكُ يُعلنه فجوة.

    **مأخذُ المراجعة الذاتية:** «أيُّ رقمٍ» كان يُحتسَب عرضاً لقيمةٍ، فجملةٌ
    مشروعةٌ تُعلِن **جدولاً زمنياً** («نقطةُ التعادل ستتضح بعد أول 3 أشهر من
    التشغيل») تُفشِل التقريرَ بفحصٍ غيرِ قابلٍ للإصلاح. فالرقمُ الملتصقُ
    بوحدةِ **زمن** ليس قيمةً للبند — إلّا حين يكون البندُ نفسُه زمنياً
    («الزمن من القرار إلى أول فاتورة»)، فيُقرأ من اسمِه لا بتفريع.

    **منطقةُ العمى المعلنة:** (أ) صياغةٌ لا تحمل إبرةَ اسمِ البند («العتبةُ
    التي تتساوى عندها») لا تُرى؛ (ب) رقمٌ بلا رقمٍ عربيٍّ أو لاتينيّ في
    الجملة نفسها لا يُرى؛ (ج) جملةٌ تحمل رمزَ فجوةٍ معلَنة تُعفى بالتصميم —
    «نقطةُ التعادل غير محسوبة: الناقصُ تكلفتُك» هي الصيغةُ المشروعة؛
    (د) رقمٌ زمنيٌّ في بندٍ غيرِ زمنيٍّ لا يُعَدّ قيمةً.
    """
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    text = ((dr.get("report") or {}).get("text") or "")
    dn = ((dr.get("economics") or {}).get("decision_numbers") or [])
    if not text or not dn:
        return []
    gaps = _norm_gap_tokens()
    named: list[str] = []
    plain_segs = [seg for seg in re.split(r"[.\n؟!؛]", _norm_ar(text))]
    for e in dn:
        if not isinstance(e, dict) or e.get("tier") != "gap":
            continue
        needle = _dn_needle(e.get("name"))
        if len(needle) < 6:
            continue
        time_item = bool(_TIME_ITEM_RE.search(str(e.get("name") or "")))
        for seg in plain_segs:
            if (needle in seg and _shows_a_value(seg, time_item)
                    and not any(g in seg for g in gaps)):
                nm = str(e.get("name") or "").strip()
                if nm and nm not in named:
                    named.append(nm)
                break
    if not named:
        return []
    return [{
        "check": "reference_to_nonexistent_figure", "repairable": False,
        "note": ("المتن يعرض رقماً لبنودٍ يُعلنها المحرك غير محسوبة: «"
                 + "، ".join(named[:4]) + "» — رقمٌ لبندٍ مجهولٍ لا يُسلَّم؛ "
                 "البديل: «غير محسوب — الناقص: [اسم المدخل]»")}]


def _check_max_loss_without_components(view: dict) -> list[dict]:
    """`max_loss_without_components` (الصنف ٩، تحذيريّ): سقفُ المخاطرة يصل
    رقماً مفرداً بينما أساسُه المحسوب **استُبعد منه** مكوّنٌ سمّاه المحرّك.

    المرجعُ حتميّ: بندُ كلفةِ الدخول يُصرِّح بالاستبعاد نصّاً («خارج
    المجموع»/«يُستبعد من المجموع»). فإن صرّح ولم يحمل نثرُ سقفِ المخاطرة
    مدىً ولا إفصاحَ استبعاد ⇒ سقفٌ يُقرأ شاملاً وهو ناقص.

    **منطقةُ العمى المعلنة:** غيابُ ذكرِ السقف من المتن أصلاً لا يُلتقَط هنا
    (شأنُ `decision_numbers_present`)؛ ومدىً مكتوبٌ بالكلمات بلا رقمين
    («بين أدنى وأقصى») لا يُرى.
    """
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    text = ((dr.get("report") or {}).get("text") or "")
    dn = ((dr.get("economics") or {}).get("decision_numbers") or [])
    if not text or not dn:
        return []
    excluded: list[str] = []
    ml_named = False
    for e in dn:
        if not isinstance(e, dict):
            continue
        method = str(e.get("method") or "")
        if any(m in method for m in _ENGINE_EXCLUSION_MARKS):
            excluded.append(str(e.get("name") or ""))
        if (any(n in str(e.get("name") or "") for n in _MAX_LOSS_NEEDLES)
                and e.get("tier") == "estimated"):
            ml_named = True
            excluded += [str(u) for u in (e.get("unknown") or [])]
    if not ml_named or not excluded:
        return []
    n_needles = tuple(_norm_ar(n) for n in _MAX_LOSS_NEEDLES)
    n_disclose = tuple(_norm_ar(d) for d in _EXCLUSION_DISCLOSURE)
    gaps = _norm_gap_tokens()
    for raw_seg in re.split(r"[.\n؟!؛]", text):
        seg = _norm_ar(raw_seg)
        if not (any(n in seg for n in n_needles)
                and _ANY_DIGIT_RE.search(seg)):
            continue
        if (any(d in seg for d in n_disclose) or any(g in seg for g in gaps)
                or _RANGE_MARK_RE.search(raw_seg)):
            continue
        return [{
            "check": "max_loss_without_components", "repairable": True,
            "note": ("سقف المخاطرة يُعرض رقماً مفرداً بينما أساسه المحسوب "
                     "استُبعد منه مكوّن سمّاه المحرك — اعرضه مدىً وسمِّ ما "
                     "هو خارجه: «" + "؛ ".join(
                         x for x in excluded[:2] if x) + "»")}]
    return []


# ── الصنف ١٢: «غير متاح» وهو مرصود · declared unavailable yet observed ────
# **العيبُ المرصود:** «التعرفة غير متاحة — اعتُمدت 0%» وبعثةُ التعريفات
# تحمل «التعريفة المطبَّقة 60%»؛ و«الناقص: عملة السعر المرصود» وملاحظةُ
# السعر تقول «روبية» صريحةً. الفجوةُ مُعلَنةٌ صادقةً في ظاهرها وكاذبةٌ في
# مضمونها: المعطى **مرصودٌ** ولم يُعرَف، لا مفقود.
#
# هذا الفحصُ يقابل **إعلانَ النقص** بما تحمله البعثةُ المسؤولةُ عنه فعلاً.
# تحذيريّ دائماً (لا حجبَ جديد)، ويعمل بالراية وبدونها — فهو الشاهدُ على
# أنّ الفكسَ أصلحَ شيئاً: مطفأةً يُطلِق على المدوّنتين، ومفعّلةً يصمت.
# الصياغةُ الدقيقة (بعد قياسٍ): الفحصُ لا يسأل «هل تَرِد الكلمةُ في بعثةٍ ما؟»
# — سؤالٌ أطلقَ على تسعِ مدوّناتٍ منها ستٌّ **فجوتُها صادقة** (كلمةُ «جمرك»
# ترد بلا رقمٍ قابلٍ للقراءة، والعملةُ ترد في صفِّ سعرٍ **آخرَ** غيرِ المرساة).
# يسأل السؤالَ الحتميّ الوحيد: **هل كان مستخلِصُ المحرّك نفسُه سيجدها لو
# وُسِّعت المفردات؟** فيصمت بالبناء حين تُفعَّل الراية، ويُطلِق حين — وفقط
# حين — كان المعطى قابلاً للقراءة ولم يُقرَأ.
_UNAVAILABLE_INPUTS = (
    ("التعرفة غير متاحة", "tariff", "التعرفة", "tariffs_agreements"),
    ("عملة السعر المرصود", "currency", "عملة السعر المرصود",
     "pricing_scout"),
)


def _check_observed_value_declared_unavailable(view: dict) -> list[dict]:
    """`observed_value_declared_unavailable` (الصنف ١٢، تحذيريّ): قسمُ
    الاقتصاد يُعلن معطىً ناقصاً بينما مستخلِصُ المحرّك **كان سيجده** بمفرداتٍ
    أوسع — معطىً مرصوداً لم يُقرأ، لا معطىً مفقوداً.

    **منطقةُ العمى المعلنة:** (أ) المعطيانِ المقابَلان اثنان (التعريفةُ
    وعملةُ سعرِ المرساة) — وهما المقيسان، ويُزاد الجدولُ بمعطىً حين يُرصَد
    مثلُه؛ (ب) عملةٌ ترد في صفِّ سعرٍ لم يُصبح مرساةً لا تُحتسَب (المرساةُ
    وحدها تُغذّي الحلَّ العكسيّ)؛ (ج) اسمُ عملةٍ أقصرُ من ثلاثة أحرف
    مستبعَدٌ في المصدر الواحد (`silk_narrative._currency_token_re`).
    """
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    eco = (dr.get("economics") or {})
    gaps = [str(g) for g in (eco.get("gaps") or []) if str(g).strip()]
    if not gaps or not (dr.get("missions") or {}):
        return []
    import silk_economics as _E
    import silk_narrative as _N
    wide = _E._TARIFF_WORDS + _E._TARIFF_WORDS_EXTRA
    findings = []
    for needle, kind, label, mkey in _UNAVAILABLE_INPUTS:
        if not any(needle in g for g in gaps):
            continue
        hit = ""
        if kind == "tariff":
            val, note = _E._mission_numeric(dr, mkey, wide, 0.0, 100.0)
            if val is not None:
                hit = f"{val}% — «{str(note)[:40]}»"
        else:
            hit = _N.currency_in((eco.get("anchor_price") or {}).get("source"))
        if not hit:
            continue
        findings.append({
            "check": "observed_value_declared_unavailable",
            "repairable": True,
            "note": (f"قسم الاقتصاد يُعلن «{label}» معطىً ناقصاً بينما "
                     f"بعثة «{mkey}» تحمله قابلاً للقراءة ({hit}) — معطىً "
                     "مرصوداً لم يُقرأ، لا معطىً مفقوداً؛ مفرداتُ التعرّف "
                     "أضيقُ من مفرداتِ البيانات")})
    return findings


# ── الصنف ١٣: خانةُ قيمةٍ خارج المنسِّق الواحد ──────────────────────────────
# **العيبُ المرصود:** «2539350 INR (المدى 2539350–2539350، ±0%)» — سبعُ
# خاناتٍ بلا فاصلِ آلاف، ومدىً منحلٌّ يُقدَّم مجالَ قياسٍ ±0% حيث لا مجال.
# الصنفُ ٣ وحّد المنسِّقات وهذان السطحان بُنِيا بـf-string خاصّةٍ بهما.
#
# الفحصُ يقابل **الصيغةَ القائمة** بالصيغةِ القانونية للمنسِّق الواحد،
# ويسمّي الخانةَ بعينها. تحذيريّ دائماً، ويصمت بالبناء حين تُفعَّل الراية —
# فموضوعُه مسارُ العرض الساري لا بياناتُ المدوّنة.
def _check_decision_number_format_drift(view: dict) -> list[dict]:
    """`decision_number_format_drift` (الصنف ١٣، تحذيريّ): خانةُ قيمةٍ في
    «أرقام القرار» تُعرَض بصيغةٍ غير صيغةِ المنسِّق الواحد.

    **منطقةُ العمى المعلنة:** (أ) بنودُ الفجوة (`tier != "estimated"`) نصٌّ
    لا رقمٌ فلا تُقابَل؛ (ب) بندٌ مُعلَنٌ «أوسعَ من أن يُتصرف به»
    (`too_wide`) يُعرَض بملاحظته لا بقيمته فيُستثنى؛ (ج) سطوحٌ أخرى تعرض
    مقادير (جدولُ السيناريوهات والشلال) خارج نطاق هذا الفحص — تُضاف حين
    تُقاس، ولا يُدّعى شمولٌ غيرُ محقَّق.
    """
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    dn = ((dr.get("economics") or {}).get("decision_numbers") or [])
    if not dn:
        return []
    import silk_narrative as _N
    drifted = []
    for e in dn:
        if not isinstance(e, dict) or e.get("tier") != "estimated" \
                or e.get("too_wide"):
            continue
        canonical = _N.canonical_decision_value(e)
        if canonical != _N.fmt_decision_value(e):
            drifted.append(f"{e.get('name')}: «{canonical}»")
    if not drifted:
        return []
    return [{
        "check": "decision_number_format_drift", "repairable": True,
        "note": ("خانةُ قيمةٍ في «أرقام القرار» تُعرَض خارج المنسِّق الواحد "
                 "(فاصلُ آلافٍ غائب أو مدىً منحلٌّ طرفاه متساويان يُقدَّم "
                 "مجالَ قياس) — الصيغةُ القانونية: "
                 + "؛ ".join(drifted[:3]))}]


# ══════ الصنف ١٠: افتراضاتُ بنية السوق · market-structure assumptions ══════
# **العيوبُ المرصودة** في تقريرٍ حيٍّ واحد: «تقلّب 0.00%» لدولةٍ بسعرين
# متباعدين؛ وسلطةٌ هنا ومرفأٌ هناك بلا إقليمِ هدف؛ وبندٌ جمركيٌّ يغطّي فئةً
# كاملةً مقروءاً سوقَ منتج؛ ونشاطٌ لا صلةَ له في قائمة الروابط؛ ونظامُ مطابقةٍ
# يخصّ دولةً أخرى في قسم الحدود.
#
# الحرّاسُ الستّة **تحذيريةٌ كلُّها** (قرارُ المالك: لا حجب جديداً) وتقرأ
# **نصَّ التقرير أوّلاً**: سجلُّ التهيئة يغطّي أربعةَ أسواقٍ من ٣٨، فحارسٌ
# يشترط التهيئة ينام في الباقي — وهو بعينه الدرس ٩٨ (حارسٌ لا يُطلِق).
# التهيئةُ **تُثري البلاغَ** ولا تشترطه، كما في `authority_naming_drift`.
_FX_VOL_NEEDLES = ("تقلب سعر الصرف", "تقلّب سعر الصرف", "fx volatility")
_FX_PEG_DISCLOSURE = ("مربوط", "ربط رسمي", "ربطٌ رسميّ", "سعر ثابت رسمي",
                      "pegged", "official peg")


def _check_zero_fx_volatility(view: dict) -> list[dict]:
    """`zero_fx_volatility` (الصنف ١٠، تحذيريّ): المحرّك أصدر تقلّبَ صرفٍ
    **صفراً** فصار عمودُ أمانِ العملة كاملاً، بلا إعلانِ ربطٍ رسميّ.

    الصفرُ قيمةٌ مشروعةٌ لعملةٍ مربوطة، وهو أيضاً ما تُنتِجه سلسلةٌ ثابتةٌ
    أو سعرٌ رسميٌّ واحدٌ في سوقٍ له سعران — والفرقُ بينهما قرارُ مخاطرة.
    فالمطلوبُ إعلانُ أيِّهما، لا حَجبُ الرقم.

    **منطقةُ العمى المعلنة:** (أ) الفحصُ لا يميّز الربطَ الحقيقيَّ من السلسلة
    الثابتة — ولذلك هو تحذيرٌ يطلب الإعلان لا حكمٌ؛ (ب) تقلّبٌ **غيرُ**
    صفريٍّ لكنه محسوبٌ من سعرٍ رسميٍّ واحدٍ في سوقٍ بسعرين لا يُرى (لا معطى
    يُقابِل السعرَ الموازي)؛ (ج) صياغةُ الربط بالإنجليزية مشمولةٌ بإبرتين.
    """
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    missions = dr.get("missions") or {}
    risk = missions.get("risk_news") if isinstance(missions, dict) else None
    findings = ((risk.get("findings") if isinstance(risk, dict)
                 else getattr(risk, "findings", None)) or [])
    zero = False
    for f in findings:
        note = str((f.get("note") if isinstance(f, dict)
                    else getattr(f, "note", "")) or "")
        val = (f.get("value") if isinstance(f, dict)
               else getattr(f, "value", None))
        if not any(n in note for n in _FX_VOL_NEEDLES):
            continue
        try:
            if val is not None and float(val) == 0.0:
                zero = True
        except (TypeError, ValueError):
            continue
    if not zero:
        return []
    text = ((dr.get("report") or {}).get("text") or "")
    if any(d in text for d in _FX_PEG_DISCLOSURE):
        return []
    return [{
        "check": "zero_fx_volatility", "repairable": True,
        "note": ("تقلّبُ سعر الصرف مرصودٌ صفراً فصار عمودُ أمان العملة "
                 "كاملاً (١.٠٠) في الدرجة — والصفرُ إمّا ربطٌ رسميٌّ وإمّا "
                 "سلسلةٌ ثابتةٌ أو سعرٌ رسميٌّ واحدٌ في سوقٍ له سعران. "
                 "أعلِن أيَّهما: «العملة مربوطة رسمياً» أو «لم يُرصَد إلا "
                 "السعر الرسمي»")}]


# الصنف ١٠ — سلطتان ومرفأٌ بلا إقليمِ هدف. الإبرُ قويةُ الدلالة: منفذُ دخولٍ
# فعليّ لا كلمةٌ عامة، وإفصاحُ الإقليم بصيغِه المتوقّعة.
# بوّابةٌ **مسمّاة**: إبرةُ منفذٍ يتبعها اسمٌ علَم — «ميناء عدن» لا «ميناء».
# القيدُ مقيسٌ: الإبرةُ وحدَها أطلقت على تقريرٍ سليمٍ ذكر جهتين مشروعتين
# ومنفذاً واحداً، والشرطُ الحقيقيُّ للعيب المرصود **بوّابتان** (قيودُ سلطةٍ
# ومرفأُ أخرى). بالبوّابتين: صفرُ إطلاقةٍ على المدوّنات الأربعَ عشرة.
_NAMED_GATEWAY_RE = re.compile(
    r"(?:ميناء|مرفأ|منفذ|معبر|مطار)\s+([^\s،.؛()]{3,})")
# الصنف ١٤ (مراجعةُ الجولة الثالثة): الإبرةُ كانت تبتلع الكلمةَ العامّة —
# «منفذ الدخول» تُقرَأ بوّابةً اسمُها «الدخول»، فيصير لتقريرٍ ذي مرفأٍ واحدٍ
# بوّابتان ويُطلِق الحارسُ على الصحيح. الكلماتُ العامّة **مُستبعَدةٌ
# بالاسم**، والاسمُ العلَمُ وحدَه يُعَدّ بوّابة.
_GENERIC_GATEWAY_WORDS = frozenset({
    "الدخول", "دخول", "الرئيس", "الرئيسي", "الرئيسية", "الوحيد", "الوحيدة",
    "البري", "البرّي", "البحري", "البحرية", "الجوي", "الجويّ", "الحدودي",
    "الحدودية", "المستهدف", "المستهدفة", "المحدد", "المحددة", "النظامي",
    "النظامية", "المعتمد", "المعتمدة", "الجمركي", "الجمركية",
})


def _named_gateways(text: str) -> list:
    """بوّاباتُ الدخول **المسمّاةُ باسمٍ علَم** في المتن — مرتَّبةً بلا تكرار.

    الكلمةُ العامّةُ بعد الإبرة ليست اسماً: «منفذ الدخول»/«الميناء الرئيس»
    وصفٌ لا تسمية. قِياسُ المراجعة الثالثة: بلا هذا الاستبعاد صار لتقرير
    ليبيا ثلاثُ «بوّابات» إحداها «الدخول».
    """
    out = []
    for g in _NAMED_GATEWAY_RE.findall(text or ""):
        name = g.strip()
        if not name or _norm_ar(name) in {_norm_ar(w)
                                          for w in _GENERIC_GATEWAY_WORDS}:
            continue
        if name not in out:
            out.append(name)
    return sorted(out)
_TARGET_REGION_DISCLOSURE = ("الإقليم المستهدف", "المنطقة المستهدفة",
                             "منفذ الدخول المستهدف", "الإقليم الخاضع",
                             "تحت سلطة", "target region")


def _check_target_region_missing(view: dict, dr: dict,
                                 lang: str = "ar") -> list[dict]:
    """`target_region_missing_in_multi_authority` (الصنف ١٠، تحذيريّ): المتنُ
    يذكر جهتين مُنسَبتين **ومنفذَ دخولٍ** بلا إقليمِ هدفٍ مُعلَن.

    كلُّ سلطةٍ منفذٌ وقيودٌ ورسومٌ مختلفة، فقائمةُ اشتراطاتٍ من سلطةٍ فوق
    مرفأٍ تحت أخرى قائمةٌ لا تصلح للتنفيذ. آلةُ رصدِ الجهات هي
    `_authority_mentions` نفسُها (الصنف ٤) — لا كاشفَ ثانٍ.

    **منطقةُ العمى المعلنة:** (أ) جهتان بلا نسبةٍ («الحكومة» عارية) شأنُ
    `authority_naming_drift` لا هذا الفحص؛ (ب) بوّابةٌ بلا اسمٍ علَمٍ
    («الميناء الرئيس») لا تُعَدّ — القيدُ مقيسٌ لا مُقدَّر: بالإبرة وحدَها
    أطلق الفحصُ على تقريرٍ سليم، وبالبوّابتين المسمّيتين صفرُ إطلاقةٍ على
    المدوّنات الأربعَ عشرة؛ (ج) الفحصُ عربيُّ المجسّ (`_AR_ONLY_CHECKS`)؛
    (د) التهيئةُ (`multi_authority`) تُثري البلاغَ ولا تشترطه.
    """
    text = ((dr.get("report") or {}).get("text") or "")
    if not text or lang != "ar":
        return []
    mentions = _authority_mentions(text)
    quals = {row["qual"] for row in mentions.values()} if mentions else set()
    if len(quals) < 2:
        return []
    gates = _named_gateways(text)
    if len(gates) < 2:
        return []
    if any(d in text for d in _TARGET_REGION_DISCLOSURE):
        return []
    tail = ""
    try:
        import silk_market_structure as _MS
        iso3 = str((view.get("market") or {}).get("iso3")
                   or ((dr.get("market") or {}).get("iso3")) or "")
        if _MS.multi_authority(iso3):
            region = _MS.target_region(iso3)
            tail = (f" والإقليمُ المُهيَّأ لهذا السوق: «{region}»." if region
                    else " والسوقُ مُهيَّأٌ متعدّدَ السلطات بلا إقليمِ هدف.")
    except Exception:  # noqa: BLE001 — التهيئةُ تُثري البلاغ لا تشترطه
        tail = ""
    return [{
        "check": "target_region_missing_in_multi_authority",
        "repairable": True,
        "note": ("المتنُ يذكر جهتين مُنسَبتين (" + "، ".join(
            f"«{q}»" for q in sorted(quals)[:3]) + ") وبوّابتَي دخولٍ ("
            + "، ".join(f"«{g}»" for g in gates[:3]) + ") بلا إقليمِ هدفٍ "
            "مُعلَن — وكلُّ سلطةٍ بوّابةٌ وقيودٌ ورسومٌ مختلفة، فالقائمةُ "
            "لا تصلح للتنفيذ حتى يُسمَّى الإقليم." + tail)}]


# الصنف ١٠ — بندٌ جمركيٌّ واسعٌ غيرُ مُعلَن. الاتّساعُ يُثبَت بأحد سبيلين
# حتميّين: تهيئةُ المنتج (`hs_scope: broad`)، أو **وصفُ البند الرسميّ نفسُه**
# حين يحمل علامةَ سلّةٍ («ومنه»/«أخرى»/"other") — أي أنّ البندَ يضمّ المنتجَ
# بين غيره. وما لا يُثبَت لا يُحكَم عليه.
_HS_BREADTH_MARKS = ("ومنه", "ومنها", "أخرى", "غير ذلك", "غير مذكورة",
                     "other", "n.e.s")
_HS_BREADTH_DISCLOSURE = ("أوسع من", "فئة أوسع", "فئةً أوسع", "سياقاً للفئة",
                          "سياقاً عاماً للفئة", "فئة مجاورة", "فئةٍ مجاورة",
                          "مُعلَّم", "معلَّم", "broader category",
                          "category context")


def _hs6_registered(hs: str) -> bool:
    """هل البندُ السداسيُّ مسجَّلٌ بوصفه الخاصّ في المرجع؟ — وإلّا فالوصفُ
    المُعاد هو وصفُ بنده الرباعيّ (تدرّجُ `definition` الداخليّ)."""
    try:
        import silk_hs_reference
        return str(hs) in getattr(silk_hs_reference, "_HS6", {})
    except Exception:  # noqa: BLE001
        return False


def _check_broad_hs_scope_undisclosed(view: dict) -> list[dict]:
    """`broad_hs_scope_undisclosed` (الصنف ١٠، تحذيريّ): البندُ الجمركيُّ
    يغطّي فئةً أوسع من المنتج، والمتنُ لا يُفصِح.

    **منطقةُ العمى المعلنة:** (أ) بندٌ خارج المرجع المسجّل وبلا تهيئةٍ لا
    يُرى — الاتّساعُ لا يُخمَّن (وهو حالُ أغلب البنود اليوم: المرجعُ ثمانيةُ
    بنودٍ سداسية)؛ (ب) الإفصاحُ يُقاس بإبَرٍ نصّية، فصياغةٌ غيرُ متوقّعةٍ
    تُحتسَب غياباً — ثمنٌ مقبولٌ لتحذير؛ (ج) `hs_flagged` عائلةٌ **أخرى**
    (وصفُ البند لا يشمل صفةَ المنتج) ولها آلتُها القائمة.
    """
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    hs = str(view.get("hs_code")
             or (view.get("header") or {}).get("hs_code") or "").strip()
    text = ((dr.get("report") or {}).get("text") or "")
    if len(hs) < 6 or not text:
        return []
    broad, why = False, ""
    try:
        import silk_market_structure as _MS
        if _MS.hs_scope(hs) == "broad":
            broad, why = True, "التهيئةُ تُعلنه بنداً واسعاً"
    except Exception:  # noqa: BLE001
        pass
    if not broad:
        try:
            from silk_hs_reference import definition
            defn = str(definition(hs) or "")
            if defn and any(m in defn for m in _HS_BREADTH_MARKS):
                broad = True
                # مرجعُ الوصف يتدرّج ٦→٤ داخلياً، فيُقال **من أيّ مستوىً**
                # جاء الدليل: بندٌ غيرُ مسجَّلٍ سداسياً يُحكَم بوصف بنده
                # الرباعيّ — تقريبٌ مُعلَنٌ لا استنتاجٌ صامت.
                lvl = ("وصفُ البند الرسميّ" if str(definition(hs)) == defn
                       and _hs6_registered(hs) else "وصفُ البند الرباعيّ")
                why = f"{lvl} «{defn[:60]}» علامةُ سلّة"
        except Exception:  # noqa: BLE001
            pass
    if not broad:
        return []
    if any(d in text for d in _HS_BREADTH_DISCLOSURE):
        return []
    return [{
        "check": "broad_hs_scope_undisclosed", "repairable": True,
        "note": (f"أرقامُ التجارة مجموعةٌ تحت البند {hs} وهو أوسعُ من المنتج "
                 f"المدروس ({why}) — والمتنُ لا يُفصِح، فتُقرأ أرقامُ فئةٍ "
                 "كأنها أرقامُ المنتج. أضف سطرَ إفصاحٍ واحداً")}]


# الصنف ١٧: عتبةُ انقلابِ سلسلةِ القيمة — سعرُ حدودٍ يفوق سعرَ الرفّ
# المرصود بهذه النسبة أو أكثر. مقيسةٌ على المدوّنات الستّ عشرة (أعلى
# نسبةٍ مشروعةٍ ١.٠٤٧) لا مُقدَّرة — فصلٌ عشرون نقطة.
_BORDER_ABOVE_SHELF_RATIO = 1.25


def _check_border_price_out_of_range(view: dict) -> list[dict]:
    """`border_price_out_of_range` (الصنف ١٠، تحذيريّ): سعرُ الحدود المرصود
    غيرُ معقولٍ — خارجَ المدى المُهيَّأ للمنتج، أو **فوق سعرِ الرفّ المرصود
    في التقرير نفسِه** بفارقٍ لا يفسّره اختلافُ عبوةٍ أو رتبة.

    فرعان، والثاني هو ما يجعل الفحصَ حيّاً (الدرس ٩٨): الأوّلُ يحتاج
    `price_range` مُهيَّأً وهو غيرُ مُدخَلٍ لأيّ منتجٍ اليوم (قرارُ مالكٍ
    مسجَّل: العقدُ يُشحَن والصفوفُ إدخالٌ لاحقٌ بمصدر) — فحارسٌ بهذا الفرع
    وحدَه **لا يُطلِق في أيّ سوق**. والثاني لا يحتاج تهيئةً قطّ: يقابل ثلاثةَ
    أرقامٍ **مرصودةٍ في التقرير** (سعرُ الحدود دولاراً/كجم، سعرُ الرفّ بعملةٍ
    محلّية/كجم، سعرُ الصرف الرسميّ) — وسعرُ حدودٍ يفوق سعرَ الرفّ تناقضٌ في
    سلسلةِ القيمة لا واقعة.

    **العتبةُ مقيسة** لا مُقدَّرة: أعلى نسبةٍ مشروعةٍ على المدوّنات الستّ
    عشرة ١.٠٤٧ (ليبيا: ٢.٠٥ مقابل ١.٩٥٩ دولار/كجم — فارقُ عبوةٍ ورتبةٍ
    محتمَل)، فالعتبةُ ١.٢٥ تُبقي صفرَ إطلاقةٍ على المدوّنات كلِّها بفصلٍ
    مقيسٍ عشرين نقطة (سابقةُ الصنف ١١: قاعدةٌ تُطلِق على الصحيح لا تُشحَن).

    **مناطقُ العمى المعلنة:** (أ) الفرعُ الأوّل صامتٌ حتى تُدخَل الصفوف؛
    (ب) الفرعُ الثاني يحتاج الأرقامَ الثلاثة معاً — وهي مجتمعةٌ في ثلاثٍ من
    ستّ عشرةَ مدوّنة، فسوقٌ بلا سعرِ رفٍّ أو بلا سعرِ صرفٍ مرصودٍ لا يُرى؛
    (ج) سوقٌ بسعرَي صرفٍ متباعدين (رسميٌّ وموازٍ) قد يُظهِر انقلاباً ظاهرياً
    — ولذلك العتبةُ واسعةٌ والبلاغُ **طلبُ مراجعةٍ** لا حكمٌ بخطأ؛
    (د) سعرُ رفٍّ بعبوةٍ غيرِ الكيلوغرام يُطبَّع في مسار الأسعار لا هنا.
    """
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    hs = str(view.get("hs_code")
             or (view.get("header") or {}).get("hs_code") or "").strip()
    if not dr:
        return []
    try:
        import silk_economics as _E
        import silk_market_structure as _MS
        band = _MS.price_range(hs) if hs else None
        val, note = _E._mission_numeric(
            dr, "trade_flow", ("متوسط سعر استيراد", "قيمة الوحدة الحدودية",
                              "unit value"), 0.0, 100_000.0)
    except Exception:  # noqa: BLE001
        return []
    if val is None:
        return []
    if band and not (band["min"] <= val <= band["max"]):
        return [{
            "check": "border_price_out_of_range", "repairable": True,
            "note": (f"سعرُ الحدود المرصود {_fmt_gate_num(val)} دولار/كجم خارج "
                     f"المدى المعقول المُهيَّأ للمنتج "
                     f"({_fmt_gate_num(band['min'])}–"
                     f"{_fmt_gate_num(band['max'])})"
                     f" — «{str(note)[:40]}»؛ راجع البند أو المصدر قبل بناء "
                     "هامشٍ عليه")}]
    try:
        shelf, s_note, s_f = _E._mission_numeric_finding(
            dr, "pricing_scout", ("سعر رف", "سعر تجزئة", "shelf"),
            0.0, 10 ** 9)
        if shelf is None:
            return []
        # المراجعةُ الذاتية (البند ٢): إبرةٌ فضفاضة «سعر الصرف» تُطابِق
        # «تقلب سعر الصرف 12.4%» فتُقرَأ **نسبةٌ** سعرَ صرف — والملاحظتان
        # متعاقبتان في بعثة المخاطر نفسِها. الإبرةُ هي إبرةُ السابقة القائمة
        # في `silk_economics` حرفياً («سعر الصرف الرسمي») بحدودِها نفسِها.
        # المراجعةُ الذاتية (البند ٣): قسمةٌ بلا فحصِ عملة — سعرُ رفٍّ
        # مرصودٌ **بالدولار** كان يُقسَم على سعر الصرف فيصير خمسَ قيمته،
        # فيُطلِق الحارسُ على تقريرٍ سعرُ رفِّه ضِعفُ سعرِ الحدود. نفسُ
        # استثناء `silk_economics` القائم (`_cur in ("$","USD","دولار")`).
        _s_val = (s_f.get("value") if isinstance(s_f, dict)
                  else getattr(s_f, "value", ""))
        # العملةُ قد تعيش في نصّ القيمة لا في الملاحظة (الدرس ٢٧١).
        cur = _E.currency_in_note(
            f"{s_note} {_s_val if isinstance(_s_val, str) else ''}")
        # الدرس ٢٧٢: الحسمُ بعملة السوق من المصدر الواحد نفسِه الذي يقرؤه
        # `silk_economics` — «$» في سنغافورة ليس دولاراً أمريكياً، وصرفُ
        # الرينجيت لا يُقسَم عليه سعرٌ باليورو (كان هنا بلا فحص).
        import silk_narrative as _N
        _iso3 = str((view.get("market") or {}).get("iso3")
                    or (dr.get("market") or {}).get("iso3") or "")
        _loc = _E.market_currency(_iso3)
        if _E._iso(cur, _loc) == "USD":
            shelf_usd, rate = shelf, None
        elif _N.currency_is_local(cur, _loc) is False:
            return []           # عملةٌ أخرى يقيناً — لا تحويلَ بصرف السوق
        else:
            rate, _fx_note = _E._mission_numeric(
                dr, "risk_news", ("سعر الصرف الرسمي",), 1e-4, 100_000.0)
            if not rate:
                return []
            shelf_usd = shelf / rate
    except Exception:  # noqa: BLE001
        return []
    if shelf_usd <= 0 or val < _BORDER_ABOVE_SHELF_RATIO * shelf_usd:
        return []
    basis = (f" بسعر الصرف الرسمي {_fmt_gate_num(rate)}" if rate
             else " والسعرُ مرصودٌ بالدولار")
    return [{
        "check": "border_price_out_of_range", "repairable": True,
        "note": (f"سعرُ الحدود المرصود {_fmt_gate_num(val)} دولار/كجم يفوق "
                 f"سعرَ الرفّ المرصود في التقرير نفسِه "
                 f"({_fmt_gate_num(shelf_usd)} دولار/كجم{basis}) — "
                 f"«{str(s_note)[:40]}»؛ سلسلةُ القيمة "
                 "لا تحتمل هذا الاتجاه، فراجع وحدةَ أحدِ الرقمين أو مستوى "
                 "السعر قبل بناء هامشٍ عليه")}]


def _check_lead_outside_activity_allowlist(view: dict) -> list[dict]:
    """`lead_outside_activity_allowlist` (الصنف ١٠، تحذيريّ): رابطٌ في قائمة
    الجهات نشاطُه مُدرَجٌ ومستبعَدٌ من قائمة السماح.

    **منطقةُ العمى المعلنة:** (أ) نشاطٌ **مجهولٌ** يمرّ بالتصميم — الجهلُ
    بالتسمية ليس دليلَ عدمِ الصلة (سياسةُ `activity_label_ar`)؛ (ب) روابطُ
    مسارِ Places وبحثِ الويب لا تحمل نشاطاً أصلاً فلا تُرى (مسارُ الخرائط
    وحدَه يحمله)؛ (ج) الفحصُ لا يحكم على غيابِ موزّعٍ مسمّىً في النثر —
    ذلك شأنُ الإدراجِ التلقائيّ في `_clean_leads`.
    """
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    leads = ((dr.get("importer_leads") or {}).get("leads") or [])
    if not leads:
        return []
    try:
        from silk_style_contract import lead_activity_allowed
    except Exception:  # noqa: BLE001
        return []
    bad = []
    for lead in leads:
        if not isinstance(lead, dict):
            continue
        cat = str(lead.get("category") or "").strip()
        if cat and not lead_activity_allowed(cat):
            name = str(lead.get("name") or "").strip() or "جهةٌ بلا اسم"
            row = f"{name} ({cat})"
            if row not in bad:
                bad.append(row)
    if not bad:
        return []
    return [{
        "check": "lead_outside_activity_allowlist", "repairable": True,
        "note": ("قائمةُ الجهات تحمل نشاطاً لا صلةَ له بالمنتج: "
                 + "؛ ".join(bad[:3]) + " — الجهةُ تُدرَج لنشاطها لا لقربها "
                 "الجغرافيّ، وإدراجُها يُضعِف ثقةَ القائمة كلِّها")}]


def _check_regime_not_belonging_to_country(view: dict) -> list[dict]:
    """`regime_not_belonging_to_country` (الصنف ١٠، تحذيريّ): المتنُ يستشهد
    بنظامِ مطابقةٍ مالكُه دولةٌ أخرى ولا كتلةٌ يخصّها سوقُ الهدف.

    المرجعُ حتميّ: `data/regulatory_schemes_l1.csv` — مفتاحُه **النظام** لا
    السوق، فيعمل الفحصُ على الأسواق كلِّها بلا انتظار تهيئةِ سوق (الدرس ٩٨).
    ودولةُ المنشأ مشروعةٌ دائماً: اشتراطاتُ الخروج جزءٌ من كلّ تقرير.

    **منطقةُ العمى المعلنة:** (أ) نظامٌ غيرُ مُسجَّلٍ في الجدول لا يُحكَم
    عليه — لا نحكم على ما لا نعرف، والسجلُّ يُوسَّع بصفٍّ مُستشهَد؛
    (ب) المعاييرُ الدولية والأسماءُ التي تتقاسمها برامجُ عدّة دول موسومةٌ
    `INTL`/`MULTI` فلا تُحتسَب أبداً؛ (ج) ذكرُ النظام **نفياً** («لا ينطبق
    SONCAP هنا») يُحتسَب — ثمنٌ مُعلَنٌ لتحذير، والصياغةُ المشروعة أن يُذكَر
    نظامُ السوق لا نظامُ غيره.
    """
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    # مأخذُ المراجعة الذاتية: الملحقُ يُقرَأ متناً، فرابطُ مصدرٍ
    # (`fda.gov`, `ce-marking`) يُحتسَب نظاماً أجنبياً في قائمة الاشتراطات.
    # قصُّ الملحق هو اصطلاحُ كلّ فحصٍ نصّيٍّ في هذا الملف.
    text = _split_off_appendix(((dr.get("report") or {}).get("text") or ""))
    if not text:
        return []
    iso3 = str((view.get("market") or {}).get("iso3")
               or ((dr.get("market") or {}).get("iso3")) or "").strip()
    if not iso3:
        return []
    origin = str((view.get("header") or {}).get("origin") or "").strip()
    try:
        import silk_market_structure as _MS
        rows = _MS.schemes()
    except Exception:  # noqa: BLE001
        return []
    alien = []
    for row in rows:
        name = row["scheme"]
        if not re.search(r"(?<![A-Za-z0-9])" + re.escape(name)
                         + r"(?![A-Za-z0-9])", text, re.I):
            continue
        if _MS.scheme_belongs_to(name, iso3, origin):
            continue
        owner = row.get("owner_iso3") or row.get("owner_bloc") or "—"
        entry = f"{name} ({owner})"
        if entry not in alien:
            alien.append(entry)
    if not alien:
        return []
    return [{
        "check": "regime_not_belonging_to_country", "repairable": True,
        "note": ("المتنُ يستشهد بأنظمةِ مطابقةٍ لا تخصّ سوقَ الهدف "
                 f"({iso3}): " + "، ".join(alien[:3]) + " — نظامُ دولةٍ أخرى "
                 "في قائمةِ اشتراطاتٍ يُوهِم بقيدٍ غيرِ قائمٍ ويُخفي القيدَ "
                 "القائم")}]


# البند 6 (أمر إصلاح المحرّك) — تناقضُ تسعيرٍ محسوب مرّ بلا تعليق (تقرير
# #11: أقصى EXW ‏$0.3274 مقابل متوسط استيراد $0.81 — أدنى بـ60%، ومع ذلك
# قُدِّم الرقم «أساساً للتفاوض»). حين يحسب المحرك `pricing_contradiction`:
# التحذير الحرفي إلزاميّ في المتن (إبرته «لا يصلح هذا الرقم أساساً
# للتفاوض»)، وأي جملة تقترح اعتماده تفاوضياً بلا نفي = فشل بناء.
_NEGOTIATION_BASELINE_TOKENS = ("أساساً للتفاوض", "أساسا للتفاوض",
                                "أساس التفاوض", "خط الأساس التفاوضي",
                                "خطاً مرجعياً تفاوضياً",
                                "negotiating baseline", "negotiation baseline")
_PRICING_WARNING_NEEDLE = "لا يصلح هذا الرقم أساساً للتفاوض"
_PRICING_WARNING_NEEDLE_EN = "must not be used as a negotiating baseline"


def _check_pricing_contradiction_flagged(view: dict) -> list[dict]:
    """`pricing_contradiction_flagged`: المحرك رصد تناقضاً سعرياً — المتن
    يجب أن يحمل التحذير الإلزامي، ويُحظَر اقتراح الرقم أساساً تفاوضياً."""
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    pc = ((dr.get("economics") or {}).get("pricing_contradiction"))
    text = ((dr.get("report") or {}).get("text") or "")
    if not pc or not text:
        return []
    findings = []
    # المطابقة عبر المُطبِّع الواحد (`_norm_ar`) على الطرفين — «أساساً»
    # المنوَّنة على نصٍّ مجرَّد كانت لا تلتقي أبداً (حادثة هذا الفحص نفسه).
    # الصنف ١٦: الحضورُ الحرفيُّ يُقاس على نصٍّ مطويِّ الأسطر — التحذيرُ
    # الملفوفُ على سطرين كان يُبلَّغ غائباً وهو حاضر.
    plain = _flat_ar(text)
    if (_flat_ar(_PRICING_WARNING_NEEDLE) not in plain
            and _flat_ar(_PRICING_WARNING_NEEDLE_EN) not in plain):
        findings.append({
            "check": "pricing_contradiction_flagged", "repairable": False,
            "note": ("المحرك رصد أن أقصى سعر المصنع أدنى بنسبة "
                     f"{pc.get('shortfall_pct')}% من متوسط سعر الاستيراد "
                     "المرصود، والمتن لا يحمل التحذير الإلزامي — تناقض "
                     "تسعيري لا يمرّ بلا تعليق")})
    _base_tokens = tuple(_norm_ar(t) for t in _NEGOTIATION_BASELINE_TOKENS)
    _ok_tokens = (_norm_ar("لا يصلح"), "must not")
    gaps = _norm_gap_tokens()
    for seg in re.split(r"[.\n؟!؛]", plain):
        if (any(t in seg for t in _base_tokens)
                and not any(t in seg for t in _ok_tokens)
                and not any(g in seg for g in gaps)):
            findings.append({
                "check": "pricing_contradiction_flagged", "repairable": False,
                "note": ("المتن يقترح اعتماد أقصى سعر المصنع أساساً "
                         "تفاوضياً رغم تناقضه المحسوب مع متوسط سعر "
                         "الاستيراد — اقتراح محظور مع هذا التناقض")})
            break
    return findings


def _check_verdict_evidence_direction(view: dict) -> list[dict]:
    """`verdict_evidence_direction` (البند 7 من أمر إصلاح المحرّك): الحكم
    ترقّى عن التشغيلة السابقة لنفس (المنتج × السوق) بينما هبطت الثقةُ
    وهبط عددُ المؤشرات وارتفعت الفجوات — الحكم لا يتحرك مع الدليل؛ يتوقف
    التسليم ويُبلَّغ. الحسابُ نفسه في `silk_consistency` (قبل بناء العرض)؛
    هذا قارئ نتيجته الحتمية على القالب — لا نداء مخزنٍ من البوابة."""
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    vc = dr.get("verdict_consistency") or {}
    if not vc.get("inconsistent"):
        return []
    prev_id = vc.get("previous_analysis_id")
    return [{
        "check": "verdict_evidence_direction", "repairable": False,
        "note": ((vc.get("note") or "ترقية حكم مع تدهور كل مؤشرات الدليل")
                 + (f" (مقارنةً بالتشغيلة #{prev_id})" if prev_id else ""))}]


# البند 10 (أمر إصلاح المحرّك) — تسمية الحكم تطابق محتواه (تقرير #10:
# العنوان «لا تدخل» ونفس الصفحة تقول «أفضل باب دخول: SADAFCO» والقسم 10
# يقول العائق فجوات بيانات لا ضعف طلب). أُصلح في #11 — هذا قفله الدائم.
_ENTRY_ROUTE_NEEDLES = ("أفضل باب دخول", "أفضل مسار دخول",
                        "باب الدخول الموصى", "مسار الدخول الموصى",
                        "best entry route", "recommended entry route")
# جملةُ شرطٍ افتراضي («لو اكتملت البيانات لكان أفضل باب دخول…») توصيفٌ
# مشروع لشرط قلبٍ لا توصية حاضرة — تُستثنى.
_HYPOTHETICAL_TOKENS = ("لو ", "إذا ", "في حال", "عند توفر", "عند اكتمال",
                        "شرط قلب", "يتحوّل", "يتحول",
                        # مرايا إنجليزية (موجة سدّ الفجوات الثانية): شرطية
                        # إنجليزية مشروعة كانت تُفشِل تقريراً صحيحاً. دورة
                        # C4: «were/would/once» العارية أشيع من أن تُعفي —
                        # كانت تحيّد الحارس؛ الإبر فواتح شرطٍ محددة كالعربية.
                        "if ", "should the ", "in case ", "upon completion",
                        "flip condition", "would become")


def _check_verdict_label_matches_content(view: dict) -> list[dict]:
    """`verdict_label_matches_content`: حكمُ الدراسة «عدم دخول» بينما المتن
    يوصي إثباتاً بباب دخولٍ مسمّى — التسمية لا تطابق المحتوى."""
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    if str(dr.get("verdict_tone") or "") != "nogo":
        return []
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    n_needles = tuple(_norm_ar(n) for n in _ENTRY_ROUTE_NEEDLES)
    n_hypo = tuple(_norm_ar(h) for h in _HYPOTHETICAL_TOKENS)
    for seg in re.split(r"[.\n؟!؛]", _norm_ar(text)):
        if (any(n in seg for n in n_needles)
                and not any(h in seg for h in n_hypo)):
            return [{
                "check": "verdict_label_matches_content",
                "repairable": False,
                "note": ("تسمية الحكم «عدم دخول» بينما المتن يوصي إثباتاً "
                         "بباب دخول مسمّى — تسمية الحكم لا تطابق محتواه؛ "
                         "إمّا الحكم خاطئ وإمّا التوصية تُصاغ شرطَ قلبٍ "
                         "افتراضياً لا توصية حاضرة")}]
    return []


# ── P2 (أمر إصلاح المحرّك، البنود 11–23) — فحوص نصية حتمية ────────────────
# المُفشِلة (عيوب توليد/بناء يزيلها المسار السليم فلا تفشل تقريراً بريئاً):
# repeated_span، empty_citation، dead_table، system_language_leak،
# table_row_stutter.
# التحذيرية (تُصعَّد بمعيار الدرس 135 الرقمي: ثلاث دراسات حية متتالية بلا
# إصابة — العدّ عبر consecutive_clean_runs أدناه): absence_vocabulary،
# decimal_precision، sentence_length، caveat_repetition،
# decision_numbers_present.

_WORD_STRIP_RE = re.compile(r"[^\w؀-ۿ%$€.]+")


def _prose_lines(text: str) -> list[str]:
    """أسطر النثر فقط — لا جداول (|) ولا عناوين (#): صفوف الجداول المتشابهة
    وعناوين الأقسام تكراراتٌ بنيوية مشروعة لا عيوب توليد."""
    return [ln for ln in (text or "").split("\n")
            if not ln.lstrip().startswith(("|", "#"))]


def _check_repeated_span(text: str) -> list[dict]:
    """`repeated_span` (البند 11): امتداد ٨ كلمات يتكرر حرفياً **داخل
    الفقرة الواحدة** — عيبُ توليد (#10: «…فئة جملة ضيقة م وهذا التناقض
    متوقَّع…»؛ #11: «…هامش الرب …الربح…»). النطاق فقرةٌ عمداً: ذيلُ
    استشهادٍ متكرر عبر أقسامٍ («وفق UN Comtrade عام 2023…») نثرٌ مشروع لا
    تلعثم (§58: مدوّنات الأقسام النظيفة كانت تُفشَل زوراً)؛ نافذة ٤٠
    كلمة؛ حتمي O(n)؛ الرموز عبر المُطبِّع الواحد."""
    for line in _prose_lines(text):
        words = [w for w in _WORD_STRIP_RE.split(_norm_ar(line)) if w]
        if len(words) < 16:
            continue
        seen: dict = {}
        for i in range(len(words) - 7):
            key = tuple(words[i:i + 8])
            j = seen.get(key)
            if j is not None and 1 <= i - j <= 40:
                return [{
                    "check": "repeated_span", "repairable": False,
                    "note": ("امتداد ثماني كلمات مكرر حرفياً داخل الفقرة "
                             "— عيب توليد (لصق/تلعثم): «"
                             + " ".join(words[i:i + 8]) + "»")}]
            seen[key] = i
    return []


def _check_cross_universe_ratio(text: str) -> list[dict]:
    """`cross_universe_ratio` (E1 — الدراسة الحية الرابعة، تحذيري): «نصيب
    الفرد» مشتقٌ من **الواردات** — مقامٌ من عالمٍ مختلف عن بسطه (الواردات
    ليست استهلاكاً)، والرقم الذي يحتاج فقرة تنصّلٍ لا يُطبع (قاعدة المُشرِف؛
    الموجّه يحظره الآن نصاً — هذا حارس انحدارها).

    الإبرتان كلتاهما على السطر **المطبَّع** (C4 موجة #14 — الملاحظة 5:
    تطبيعُ نصف الشرط كان يُفقِد السطرَ المشكول)، وذراع «(مشتق)» وحدها
    أُسقطت — كانت تتهم نسبةً سليمة المقام («نصيب الفرد من الناتج (مشتق)»)
    باشتقاقٍ من الواردات زوراً.

    **منطقة العمى المعلنة**: نسبٌ مقلوبة المقام بصيغ أخرى («لكل نسمة من
    الصادرات»، اشتقاقٌ لا يسمّي الواردات في سطره) لا تُرى؛ والفحص سطري —
    بسطٌ ومقام في سطرين منفصلين خارجه."""
    findings = []
    for line in (text or "").split("\n"):
        nl = _norm_ar(line)
        if "نصيب الفرد" in nl and "واردات" in nl:
            findings.append({
                "check": "cross_universe_ratio", "repairable": True,
                "note": ("«نصيب الفرد» مشتق من الواردات — الواردات ليست "
                         "استهلاكاً فردياً؛ اذكر البسط والمقام كلاً على "
                         "حدة بدل نسبةٍ تحتاج فقرة تنصّل")})
            break
    return findings


def _check_adjacent_short_stutter(text: str) -> list[dict]:
    """`adjacent_short_stutter` (انحدار D1 — #13): امتدادُ ٢–٧ كلمات يعيد
    نفسه **ملاصقاً** داخل السطر، بسماح بصمة البتر (آخر كلمة في الظهور
    الأول بادئةٌ صارمة لنظيرتها في الثاني): «تحتاج تحققا تحتاج تحققا
    إضافيا» و«لا يتوفر س لا يتوفر سعر تجزئة» بلغتا PDF العميل تحت عتبات
    الفحوص الثلاثة (`repeated_span` ٨ كلمات؛ قاصّا الدمج بعتبتيهما).

    **منطقة العمى المعلنة** (قاعدة المُشرِف): (أ) التكرار القصير **غير
    الملاصق** (بينه كلمات) نثرٌ مشروع فلا يُمَسّ — تلعثمُه لا يُلتقَط؛
    (ب) امتداد ≥٨ كلمات شأن `repeated_span` (نافذة ٤٠ كلمة)؛ (ج) ازدواجُ
    كلمةٍ واحدة («جداً جداً») مشروعٌ لغوياً فلا يدخل."""
    findings = []
    for line in _prose_lines(text):
        words = [w for w in _WORD_STRIP_RE.split(_norm_ar(line)) if w]
        n = len(words)
        hit = None
        for s in range(2, 8):
            for i in range(n - 2 * s + 1):
                a, b = words[i:i + s], words[i + s:i + 2 * s]
                if sum(len(w) for w in a) < 6:
                    continue
                if a[:-1] != b[:-1]:
                    continue
                if a[-1] == b[-1] or (b[-1].startswith(a[-1])
                                      and len(b[-1]) > len(a[-1])):
                    hit = " ".join(a + b)
                    break
            if hit:
                break
        if hit:
            findings.append({
                "check": "adjacent_short_stutter", "repairable": False,
                "note": ("ازدواج قصير ملاصق — عيب توليد (تلعثم/بتر ثم "
                         f"استئناف): «{hit}»")})
            break
    return findings


_TABLE_CELL_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def _check_table_row_stutter(text: str) -> list[dict]:
    """`table_row_stutter` (دراسة #12 الحيّة، توقيع أمر المُشرِف C1): خليةٌ
    قصيرة بادئةٌ **صارمة** لخليةٍ لاحقة في نفس الصفّ على أي مسافة
    («يُق» → «يُقدَّر بنحو…») — أثرُ التحام صفٍّ مبتورٍ منتصفَ خليةٍ
    بإعادته الكاملة في سطرٍ واحد. التطابقُ التام **وحدَه** لا يُعلَّم أبداً
    (خليتا «غير متاح» في صفٍّ واحد مشروعتان — فلا حاجةَ لاستثناء رموز
    الفجوة ولا لعتبة طول). حارسا السلامة: الخليةُ القصيرة تحوي حرفاً (لا
    بادئات أرقام: «5» بادئة «5.84») وحرفُ الاستمرار في الأطول **حرفٌ** —
    بترُ منتصفِ الكلمة فيزياءُ الحادثة («حليب» قبل «حليب كامل» يستمرّ
    بمسافة فيمرّ). ودورة §58 الثانية: الصرفُ العربي يجعل البادئةَ وحدَها
    كاذبةً («غير متاح»/«غير متاحة»، «حليب»/«حليبنا») — فالإطلاق يشترط
    معها **دليلَ إعادة الصف**: خليةٌ أخرى في نفس الصفّ مكررةٌ حرفياً
    (عمود التسمية المُعاد — موجودٌ في الحادثة بالبناء). بترُ الخلية
    الأولى بلا تسمية مكررة قيدٌ معلَن مقبول (السجل). المنبعُ مُصلَح
    (قاصُّ التلعثم يقبل `\\n` حدَّ كلمة) — هذا حارسُ انحداره؛
    و`repeated_span` يبقى مستثنياً أسطر `|`."""
    for ln in (text or "").split("\n"):
        s = ln.strip()
        if not s.startswith("|") or set(s) <= {"|", "-", ":", " "}:
            continue
        cells = [_norm_ar(c).strip() for c in s.strip("|").split("|")]
        dup_evidence = len([c for c in cells if len(c) >= 2]) != \
            len({c for c in cells if len(c) >= 2})
        if not dup_evidence:
            continue
        for i, a in enumerate(cells):
            if len(a) < 2 or not _TABLE_CELL_LETTER_RE.search(a):
                continue
            for b in cells[i + 1:]:
                if (len(b) > len(a) and b.startswith(a)
                        and _TABLE_CELL_LETTER_RE.match(b[len(a)])):
                    return [{
                        "check": "table_row_stutter", "repairable": False,
                        "note": (f"خلية «{a[:30]}» بادئة مبتورة لخلية لاحقة "
                                 f"«{b[:40]}» في نفس صف الجدول — أثر التحام "
                                 "صف مبتور بإعادته الكاملة (عيب توليد، "
                                 "دراسة #12)")}]
    return []


# البند 13: فاصلة يتيمة من حقل مصدر فارغ — «(،» و«، /)» (تقرير #10 حرفياً).
# طبقة العرض تطويها (`_ORPHAN_LEAD/TAIL_COMMA_RE`) — هذا حارس انحدارها.
_EMPTY_CITATION_NEEDLES = ("(،", "( ،", "، /)", "،/)", "(/", "()", "（）",
                           # المرايا اللاتينية — «(, World Bank...)» بفاصلة
                           # لاتينية كان غير مرئي (موجة سدّ الفجوات الثانية).
                           "(,", "( ,", ", /)", ",/)")


def _check_empty_citation(text: str) -> list[dict]:
    plain = _norm_ar(text)
    hits = sorted({n for n in _EMPTY_CITATION_NEEDLES if n in plain})
    if not hits:
        return []
    return [{
        "check": "empty_citation", "repairable": True,
        "note": ("فاصلة/قوس استشهاد يتيم من حقل مصدر فارغ: "
                 + " ".join(f"«{h}»" for h in hits)
                 + " — حقل المصدر الفارغ يُسقِط القوس كاملاً، لا فاصلة يتيمة")}]


# البند 15: جدول ميت — أقل من نصف خاناته مملوءة. طبقة العرض تطويه لسطرٍ
# يسمّي الناقص (`silk_render._collapse_dead_tables`) — هذا حارس انحدارها.
_TABLE_GAP_TOKENS = ("غير متاح", "غير محسوب", "غير مرصود", "لم يُرصَد",
                     "لم يرصد", "يتعذر الحساب", "يتعذّر الحساب", "غير محدد",
                     "غير مذكور", "غير قابل للحساب", "لا يوجد", "فجوة معلنة",
                     "غير موثق", "غير موثقة", "n/a", "not available",
                     "cannot compute", "not observed",
                     # مرايا إنجليزية إضافية (موجة سدّ الفجوات الثانية):
                     # جدول إنجليزي ميت كله «not calculated/unknown/TBD»
                     # كان يمرّ. («-»/«—» الخالصة يلتقطها فحص المجموعة
                     # أعلاه، و«none» تُترك عمداً — تحت-سلسلة nonetheless.)
                     "not calculated", "not computed", "unknown", "tbd",
                     "not stated")


def _table_cell_populated(cell: str) -> bool:
    c = _norm_ar(cell).strip()
    if not c or set(c) <= set("—–- *"):
        return False
    if (any(_norm_ar(t) in c for t in _TABLE_GAP_TOKENS)
            and not re.search(r"[0-9٠-٩]", c)):
        return False
    return True


def _iter_md_tables(text: str):
    """كتل جداول Markdown: (سطر الترويسة، صفوف البيانات) لكل جدول."""
    lines = (text or "").split("\n")
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            block = lines[i:j]
            if len(block) >= 3:
                yield block[0], block[2:]
            i = j
        else:
            i += 1


def _check_dead_table(text: str) -> list[dict]:
    findings = []
    for header, data_rows in _iter_md_tables(text):
        cells = [c for r in data_rows
                 for c in r.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        populated = sum(1 for c in cells if _table_cell_populated(c))
        if populated / len(cells) < 0.5:
            head_txt = " / ".join(
                h.strip() for h in header.strip().strip("|").split("|")
                if h.strip())[:90]
            findings.append({
                "check": "dead_table", "repairable": True,
                "note": (f"جدول «{head_txt}» أكثر من نصف خاناته بلا قيمة "
                         f"({len(cells) - populated}/{len(cells)}) — يُستبدل "
                         "بسطر واحد يسمّي الناقص، لا هيكل فارغ")})
    return findings


# البند 23: لغة النظام عن آلية البناء لا تصل القارئ — طبقة العرض تسقط
# «آلياً» من عبارات الإحالة؛ هذا حارس انحدارها.
_SYSTEM_LANGUAGE_NEEDLES = ("يرد أسفل هذا القسم آلياً", "تلي هذا القسم آلياً",
                            "يلي هذا القسم آلياً", "يليان آلياً",
                            "تليان آلياً", "طبقة العرض تبني",
                            # مرايا إنجليزية (البند 23 كان بلا حارس إنجليزي)
                            "follows automatically below",
                            "automatically below this section",
                            "the rendering layer builds",
                            "is appended automatically",
                            # دورة C4: الموجّه نفسه يذكر «طبقة العرض تعرض»
                            # — صدى الكاتب لها يُلتقط.
                            "طبقة العرض تعرض",
                            "the rendering layer displays")


def _check_system_language_leak(text: str) -> list[dict]:
    plain = _norm_ar(text)
    hits = [n for n in _SYSTEM_LANGUAGE_NEEDLES if _norm_ar(n) in plain]
    if not hits:
        return []
    return [{
        "check": "system_language_leak", "repairable": True,
        "note": ("جملة لغة نظام عن آلية بناء التقرير وصلت القارئ: «"
                 + hits[0] + "» — تعليمات النظام لا تُطبع")}]


# البند 16 (تحذيري حتى معايرة Part B): مفردات الغياب تُوحَّد في اثنتين —
# «غير متاح» (الرقم لا وجود له) و«غير محسوب» (يوجد ولم يُحسب).
# موجة سدّ الفجوات (F4): «غير مرصود» و«غير مذكور» كانتا ناقصتين من القائمة
# بلا توثيق رغم ورودهما في نص البند 16 حرفياً — أُكملتا بعد تهجير مواضع
# انبعاثهما في طبقة العرض نفسها (silk_render/silk_reports/silk_economics)
# إلى الثنائية القانونية، وبعد حلّ تناقض الموجّه الذاتي (كان يفرض «وزن غير
# مذكور» في خلايا الأسعار ويحظر «غير مذكور» بعدها بأسطر).
# ══════════ الصنف ١ (موجة عيوب التقرير) — لغةُ النظام تصل القارئ ══════════
# بلاغُ المالك: عباراتٌ كُتبت لمطوّرٍ وصلت صاحبَ القرار. الفحصُ الحتميّ هو
# الحارسُ **الوحيد الممكن** لسبعٍ من العشر المرصودة: لا قالبَ في هذا
# المستودع يُنتجها، فهي من نثر الكاتب (النموذج) — وما لا قالبَ له لا يُصلَح
# إلّا بقاعدةٍ تُفحَص على كلّ تقرير. القوائمُ مصدرُها الواحد
# `silk_style_contract` (يستهلكها الموجّهُ والمراجعُ أيضاً) فلا تتباعد نسختان.
#
# **المنطقةُ العمياء المُعلَنة (نمط الدرس 172):** قائمةٌ محدودة — لغةُ نظامٍ
# جديدةٌ غيرُ مُدرَجة لا تُلتقَط. وقاعدةُ الإدراج سؤالُ الدرس 176 عند كلّ
# إضافة: **من يؤلّف هذه العبارة؟** إن كان قالباً فالقالبُ يُصلَح أوّلاً
# والقاعدةُ حارسُ انحدارٍ له؛ وإن كان النموذجَ فالقاعدةُ هي الإنفاذ.
#
# تحذيريّ لا حاجب (قرار المالك 2026-08-19: لا حجب جديداً بلا راية)، ويعيد
# القسمَ والنصَّ لكلّ إطلاقة كما طلب البلاغ.
_READER_LEAK_WINDOW = 40        # نصفُ نافذة قرينة المعنى التقنيّ (محارف)


def _reader_section_of(text: str, pos: int) -> str:
    """عنوانُ أقرب قسمٍ فوق الموضع — «القسم» في بلاغ الإطلاقة."""
    head = ""
    for m in _HEADING_RE.finditer(text, 0, max(pos, 0)):
        head = m.group(1).strip()
    return head or "قبل أول عنوان"


def _reader_snippet(text: str, start: int, end: int) -> str:
    """مقتطفٌ يقرؤه المشغّل — النصُّ حول الإطلاقة بلا أسطر."""
    lo = max(0, start - 45)
    return " ".join(text[lo:end + 45].split())


# **تصادمٌ رصده حارسٌ قائم** (`test_quality_gate_stays_warn…`): «إلى»
# تُطبَّع إلى «الي» بتوحيد الهمزات، وكذلك «آلي» — فكان حرفُ الجرّ الأكثرُ
# شيوعاً في العربية يُبلَّغ «لغةَ نظام». المفرداتُ ذاتُ المعنيين تُطابَق
# بتطبيعٍ **يحفظ الهمزة** (حركاتٌ وتطويلٌ فقط)، فلا يقع التصادم.
_TOKEN_SOFT_NORM_RE = re.compile("[\u064b-\u0652\u0670\u0640]")


def _norm_token(s: object) -> str:
    """تطبيعٌ للمطابقةِ **يحفظ صيغةَ الألف**: الحركاتُ والتطويلُ فقط."""
    return _TOKEN_SOFT_NORM_RE.sub("", str(s or ""))


# **المراجعةُ الذاتية للفرق (البند ٥٨)**: التطبيعُ يحذف حروفاً (تشكيلاً
# وتطويلاً) ويطوي المسافات، فمواضعُ المطابقة في النصّ المطبَّع **لا تطابق**
# مواضعَ النصّ الأصليّ — فكان بلاغُ `reader_language_leak` يسمّي قسماً غيرَ
# الذي فيه العيب ويقتطع مقطعاً من موضعٍ آخر. وبلاغٌ يشير إلى موضعٍ خطأ
# يُرسِل المشغّلَ إلى قسمٍ سليم.
#
# `_norm_map` يبني النصَّ المطبَّع **ومعه فهرسَ موضعِ كلّ حرفٍ في الأصل**،
# فيعود كلُّ موضعٍ إلى نظامه الإحداثيّ الصحيح.
def _norm_map(s: object, soft: bool = False) -> tuple:
    """(النصُّ المطبَّع، فهرسُ موضعِ كلّ حرفٍ في الأصل).

    `soft=True` يحفظ صيغةَ الألفِ ويطبّق تطبيعَ `_norm_token`؛ وإلّا يطبّق
    تطبيعَ `_norm_ar` حرفاً بحرف — والنتيجةُ **مطابقةٌ نصّياً** لِما تعيده
    الدالّتان، ومقفولٌ باختبار.
    """
    src = str(s or "")
    out: list = []
    idx: list = []
    for i, ch in enumerate(src):
        if _AR_DIACRITICS_STRIP_RE.fullmatch(ch) or ch == "ـ":
            continue
        if soft:
            out.append(ch)
            idx.append(i)
            continue
        if ch in "أإآ":
            ch = "ا"
        elif ch == "ة":
            ch = "ه"
        elif ch == "ى":
            ch = "ي"
        if ch in " \t":
            if out and out[-1] == " ":
                continue
            ch = " "
        out.append(ch.lower())
        idx.append(i)
    return "".join(out), idx


# الصوتُ البشريّ (طلب المالك «Humanized») — **حشوٌ كثيف** لا مجرّد حضور.
# تصحيحُ المراجعة الذاتية على أربعة مآخذ:
#  (أ) العدُّ بالمختلف كان **يعاقب التنويع**: ثلاثُ صيغٍ مرّةً واحدةً تُطلِق،
#      وتكرارُ صيغةٍ واحدةٍ ثلاثاً يصمت. فصار العدُّ بالظهور على طول المتن.
#  (ب) العتبةُ كانت مُعايَرةً على متونِ المدوّنات (٠.٩–٢.٤ كيلوبايت) بينما
#      المتنُ الحقيقيُّ ٥.٩–١١.٨ — والكثافةُ (لكلّ ألف كلمة) لا تتعلّق بالطول.
#  (ج) القائمةُ كانت تضمّ ما **تأمر به العقود** فيُلام كاتبٌ أطاع عقدَه —
#      فصارت `FILLER_PHRASES`: حشوٌ لا يأمر به عقدٌ ولا يفرضه مراجع.
#  (د) بلا تطبيعٍ كانت «والأثر العملي» **لا تُطابِق أبداً** صيغةَ العقد
#      المشكولة «والأثرُ العمليّ» — إبرةٌ ميتة (الدرس ٩٨).
# ويعمل **فقط حين الرايةُ مفعّلة**: مطفأةً لا إرشادَ في الموجّه يُتَّبع،
# فالبلاغُ يصير لوماً بلا علاج — إعلانٌ صريحٌ لا صمتٌ خفيّ.
# **مُعايَرةٌ بالقياس لا بالحدس:** أعلى كثافةٍ **مشروعة** مقيسة 7.09 لكلّ
# ألف كلمة (مدوّنةُ مصر: «وهذا يعني» مرّتين في متنٍ من ٢٨٢ كلمة)، وكلُّ
# العيّنات الملتزَمة — وهي متونٌ حقيقيةُ الطول (٤٥٧–١٩٨٠ كلمة) — تقيس صفراً.
# فالعتبةُ 12.0 تفصل بنحو ٧٠٪ فوق أعلى مشروع، والتثبيتةُ الموجَبة تقيس 122
# (فصلٌ عشرةُ أضعاف). ومحاولةٌ أولى بـ6.0 كانت **تُطلِق على مصر** — قاعدةٌ
# تُطلِق على الصحيح لا تُشحَن (سابقةُ الصنف ١١).
_FILLER_PER_1K_MAX = 12.0


def _check_robotic_stock_phrase(text: str) -> list[dict]:
    """`robotic_stock_phrase` (تحذيريّ): نثرٌ يعتمد الحشوَ الجاهز بكثافة.

    القائمةُ من `silk_style_contract.FILLER_PHRASES` — **المصدرُ الواحد** الذي
    يقرؤه الموجّهُ أيضاً، فلا تفترق قائمةُ البوابة عن قائمة الكاتب. والبلاغُ
    يحمل البديلَ الطبيعيَّ لكلّ عبارة فيكون **قابلاً للتصرّف** لا لوماً.

    **مناطقُ العمى المعلنة:** (أ) صامتٌ بلا `SILK_HUMAN_VOICE` — لا عيبَ في
    نثرٍ أطاع عقدَه؛ (ب) العتبةُ مُعايَرةٌ على عيّناتٍ لا على خرجِ كلود حيّ
    (لا وجود له في الريبو) فهي حدٌّ محافظٌ يُعاد ضبطُه عند أوّل قياسِ إنتاج؛
    (ج) الملحقُ مقصوص؛ (د) متنٌ أقصرُ من مئتَي كلمة لا يُقاس (الكثافةُ على
    عيّنةٍ صغيرةٍ ضجيج)؛ (هـ) عربيُّ المجسّ — مُعلَنٌ في `_AR_ONLY_CHECKS`.
    """
    import silk_style_contract as _SC
    if not _SC.human_voice():
        return []
    body = _split_off_appendix(text or "")
    words = len(body.split())
    if words < 200:
        return []
    flat = _flat_ar(body)
    found, hits = {}, 0
    alt = {p: a for p, a in _SC.STOCK_PHRASES}
    for phrase in _SC.filler_phrases():
        n = flat.count(_flat_ar(phrase))
        if n:
            found[phrase] = n
            hits += n
    density = hits * 1000.0 / words
    if density <= _FILLER_PER_1K_MAX:
        return []
    named = "، ".join(
        f"«{p}»×{n} ⇒ «{alt.get(p, '')}»"
        for p, n in sorted(found.items(), key=lambda t: -t[1])[:4])
    return [{
        "check": "robotic_stock_phrase", "repairable": True,
        "note": (f"كثافةُ الحشو الجاهز {density:.1f} لكلّ ألف كلمة "
                 f"(الحدّ {_FILLER_PER_1K_MAX:.0f}) فيُقرَأ النثرُ آلياً: "
                 + named + " — والبديلُ يقول المعنى نفسَه بصوتٍ طبيعيّ")}]


def _check_reader_language_leak(text: str, lang: str = "ar") -> list[dict]:
    """`reader_language_leak` (الصنف ١، تحذيريّ): لغةُ نظامٍ داخلية في نصٍّ
    يقرؤه صاحبُ القرار.

    ثلاثُ قنواتٍ بشدّةِ يقينٍ متفاوتة، ولذلك لا تُخلَط:

    1. **عباراتٌ حرفية** (`FORBIDDEN_READER_PHRASES`) — لا سياقَ يشفع لها.
    2. **رموزٌ خام** (`HARD_READER_TOKENS`) — بحدِّ كلمةٍ للّاتينيّ كي لا
       يُلتقَط `null` من داخل كلمة.
    3. **مفرداتٌ ذاتُ معنيين** (`CONTEXTUAL_READER_TOKENS`) — تُطلِق **فقط**
       بقرينةِ معنى تقنيّ قريبة. هذا شرطُ صدقٍ لا تسامح: «معادلة» وردت ١١
       مرّة في خطّ الأساس كلُّها **مأمورٌ بها** في معيار الكتابة («معادلة
       التعادل = كلفة الدخول ÷ هامش الوحدة»)، فحظرُها عارياً يُطلِق على كلّ
       تقريرٍ صحيح؛ و«واجهة» كانت تُلتقَط من داخل «مواجهة» بلا حدِّ كلمة.

    الملاحقُ مستثناةٌ (`_split_off_appendix`): الملحقُ التقنيّ سطحُ مدقّقٍ
    لا سطحُ قارئ — نفسُ استثناءِ `_check_decimal_precision`. وبلاغُ كلّ
    إطلاقةٍ يحمل **القسمَ والنصَّ** كما طلب البلاغ، وإطلاقةٌ واحدة لكلّ
    مفردةٍ (لا ضجيجَ تكرارٍ لنفس العبارة).
    """
    if not text:
        return []
    from silk_style_contract import (CONTEXTUAL_READER_TOKENS,
                                     FORBIDDEN_READER_PHRASES,
                                     HARD_READER_TOKENS, READER_TOKEN_ALLOW,
                                     SYSTEM_SENSE_CUES)
    body = _split_off_appendix(text)
    # المواضعُ تُترجَم إلى إحداثيّات النصّ الأصليّ قبل أيّ بلاغ (انظر
    # `_norm_map`): بلاغٌ يشير إلى قسمٍ غيرِ الذي فيه العيب يُرسِل المشغّلَ
    # إلى قسمٍ سليم — وهو عيبُ بلاغٍ لا عيبُ كشف.
    plain, _plain_idx = _norm_map(body)
    findings: list[dict] = []
    covered: list[tuple] = []          # مدياتُ العبارات المُبلَّغة (بالأصل)

    def _orig(pos: int, idx: list, fallback: int = 0) -> int:
        """موضعٌ في النصّ المطبَّع ⇒ موضعُه في الأصل."""
        if 0 <= pos < len(idx):
            return idx[pos]
        return idx[-1] if idx else fallback

    def _add(hit: str, start: int, end: int, why: str) -> None:
        covered.append((start, end))
        findings.append({
            "check": "reader_language_leak", "repairable": True,
            "note": (f"لغةُ نظامٍ داخلية في نصٍّ يقرؤه صاحبُ القرار: «{hit}» "
                     f"— القسم «{_reader_section_of(body, start)}»: "
                     f"…{_reader_snippet(body, start, end)}… ({why})")})

    def _inside_reported(pos: int) -> bool:
        return any(lo <= pos < hi for lo, hi in covered)

    # (١) العباراتُ الحرفية أوّلاً — فتغطّي رموزَها فلا يُبلَّغ الرمزُ مرّتين.
    for phrase in FORBIDDEN_READER_PHRASES:
        n_phrase = _norm_ar(phrase)
        i = plain.find(n_phrase)
        if i >= 0:
            lo = _orig(i, _plain_idx)
            hi = _orig(i + len(n_phrase) - 1, _plain_idx, lo) + 1
            _add(phrase, lo, hi, "عبارةٌ محظورة حرفياً")

    # (٢) الرموزُ الخام — حدُّ كلمةٍ للّاتينيّ الأبجديّ، ومطابقةٌ نصّيةٌ لغيره
    # (`{`/`}`/`N/A` رموزٌ لا كلمات، والعربيُّ يُطبَّع أوّلاً).
    for tok in HARD_READER_TOKENS:
        if tok.isascii() and tok.isalpha():
            m = re.search(rf"(?<![A-Za-z]){re.escape(tok)}(?![A-Za-z])",
                          body, re.I)
            span = (m.start(), m.end()) if m else None
        else:
            hay, needle = ((plain, _norm_ar(tok)) if not tok.isascii()
                           else (body, tok))
            i = hay.find(needle)
            if i < 0:
                span = None
            elif hay is body:
                span = (i, i + len(needle))
            else:
                lo = _orig(i, _plain_idx)
                span = (lo, _orig(i + len(needle) - 1, _plain_idx, lo) + 1)
        if span and not _inside_reported(span[0]):
            _add(tok, span[0], span[1],
                 "رمزٌ خام لا معنى له عند القارئ")

    # (٣) المفرداتُ ذاتُ المعنيين — بقرينةٍ فقط، وإطلاقةٌ واحدة لكلّ مفردة.
    soft, _soft_idx = _norm_map(body, soft=True)
    for tok in CONTEXTUAL_READER_TOKENS:
        ntok = _norm_token(tok)
        for m in re.finditer(rf"(?<![^\W\d_]){re.escape(ntok)}(?![^\W\d_])",
                             soft):
            o_lo = _orig(m.start(), _soft_idx)
            o_hi = _orig(m.end() - 1, _soft_idx, o_lo) + 1
            if _inside_reported(o_lo):
                continue
            lo = max(0, m.start() - _READER_LEAK_WINDOW)
            hi = min(len(soft), m.end() + _READER_LEAK_WINDOW)
            window = _norm_ar(soft[lo:hi])
            if any(_norm_ar(a) in window for a in READER_TOKEN_ALLOW):
                continue
            cue = next((c for c in SYSTEM_SENSE_CUES
                        if _norm_ar(c) in window), None)
            if cue:
                _add(tok, o_lo, o_hi,
                     f"بمعناها التقنيّ — قرينةُ «{cue}» بجوارها")
                break
    return findings


# ══════════ الصنف ٢ (موجة عيوب التقرير) — خانةٌ فارغة تكسر جملة ══════════
# بلاغُ المالك: «ثم السعودية بالحصة السعودية البالغة 10.44%»، و«الشريحة
# المحسوبة أعلاه رغم غياب رقم لحجمها»، و«استند هذا الحكم إلى شرطين مفتوحين»
# بلا شرطين.
#
# العلاجُ الحتميّ في القوالب نفسها (`silk_i18n.t` + `repair_interpolation` +
# صيغُ الفراغ `<key>_empty` — من ٦٣ زوجاً مكسوراً إلى صفر). وهذا الفحصُ
# حارسُ انحدارٍ له **وحارسٌ أصليّ لنثر الكاتب**: النموذجُ يركّب جملاً كهذه
# بنفسه، ولا قالبَ يُصلَح فيها.
#
# تحذيريّ. القاعدةُ الواحدة: `silk_i18n.repair_interpolation` هي مِعيارُ
# «سليم» — فلا قاعدةُ فحصٍ تخالف قاعدةَ إصلاح.
_UNRENDERED_SLOT_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z_0-9]{0,30}\}")
# إحالةٌ مكانيّة («أعلاه»/«أدناه») بجوار إعلانِ غياب: الإحالةُ تَعِد بشيءٍ
# أُعلِن أنه غيرُ موجود — «الشريحة المحسوبة أعلاه رغم غياب رقم لحجمها».
_SPATIAL_REF_RE = re.compile(r"أعلاه|أدناه|above|below", re.I)
_GAP_WORDS_NEAR = ("غير محسوب", "غير متاح", "لا نعرفه بعد", "not computed",
                   "not available", "not known yet")
_SPATIAL_GAP_WINDOW = 60
# صدى الكيان: الاسمُ نفسُه مكرّراً داخل وصفِه («السعودية بالحصة السعودية»).
# ≥٤ محارف كي لا تُلتقَط أدواتٌ وحروفُ جرّ، والنافذةُ ثلاثُ كلماتٍ بينهما.
_ECHO_WORD_RE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
# **المسافةُ هي التمييز** (مُعايَرةٌ في المراجعة الذاتية بعد الجولة الأولى):
# العيبُ المرصود «السعودية بالحصة **السعودية**» مسافتُه كلمةٌ واحدةٌ فاصلة
# (j = i+2) — الكلمةُ تعيد نفسَها داخل وصفِها. والتباينُ المشروع «العبوات
# الصغيرة … حصة العبوات الكبيرة» مسافتُه كلمتان (j = i+3) لأنّ بينهما
# فعلاً ومضافاً. فالسقفُ ٢: يحفظ العيبَ ويُخرِج المقارنة.
# (الاستدلالُ بالمُحدِّد التالي جُرِّب وأُسقِط: «بالحصة» و«البالغة» مختلفان
# فكان يُسكِت العيبَ المرصود نفسَه — معاملٌ واحدٌ مُعايَرٌ أصدقُ من حدسٍ.)
_ECHO_MAX_GAP = 2
# **ثلاثةُ استثناءاتٍ قِياسية، لا تخميناً** (مُعايَرةٌ على خطّ الأساس):
# (١) وحداتُ القياس والعملات: «0.85 دينار/لتر مقابل 0.55 دينار/لتر» مقارنةٌ
#     سليمة يجب أن تتكرّر فيها الوحدة — إنذارٌ كاذبٌ في كلّ سلّم أسعار.
_ECHO_UNIT_WORDS = frozenset({
    "دينار", "ريال", "دولار", "يورو", "درهم", "جنيه", "دينارا", "ريالا",
    "كجم", "كيلوغرام", "كيلو", "غرام", "لتر", "طن", "عبوة", "وحدة", "قطعة",
    "شهر", "سنة", "سنوياً", "سنويا", "يوم", "أسبوع", "مليون", "مليار", "ألف",
    # الصنف ١٥ (مراجعةُ الجولة الثالثة): **رأسٌ عامٌّ قبل اسمٍ علَم** يتكرّر
    # بالضرورة حين يُعَدّ كيانان — «ميناء طرابلس أو ميناء بنغازي» عربيةٌ
    # سليمة، و«الهيئة الغربية… الهيئة الشرقية» كذلك. الفحصُ أطلق عليها
    # صدىً. والاستبعادُ بالرأسِ العامِّ لا بقاعدةِ «تابعٌ مختلف»: تلك
    # جُرِّبت في الصنف ٢ فأسكتت العيبَ المرصود نفسَه («السعودية بالحصة
    # السعودية») — فالمعالجةُ بقائمةٍ مقيسةٍ لا بحدسٍ عامّ.
    "ميناء", "مرفأ", "منفذ", "معبر", "مطار", "هيئة", "الهيئة", "وزارة",
    "الوزارة", "شركة", "مؤسسة", "جمعية", "بنك", "سوق", "مدينة", "محافظة",
    "إقليم", "منطقة", "ولاية",
})
# **المراجعةُ الذاتية للفرق (البند ٥٨)**: المقارنةُ تجري على الكلمةِ
# **المطبَّعة** (`_norm_ar`) والقائمةُ مكتوبةٌ غيرَ مطبَّعة — فعشرون مدخلاً
# منها كانت **ميتةً** (كلُّ ما فيه ة/أ/إ/ى: «عبوة»، «أسبوع»، «وحدة»،
# «سنوياً»، «الهيئة»، «شركة»…)، ومنها استثناءاتٌ قائمةٌ قبل هذه الموجة. تُطبَّع
# القائمةُ مرّةً واحدة عند البناء فلا يتكرّر العيبُ بإضافةِ مدخلٍ جديد.
_ECHO_UNIT_NORM: frozenset = frozenset(_norm_ar(w) for w in _ECHO_UNIT_WORDS)
# (٢) رابطُ مقارنةٍ بين الورودين ⇒ تكرارٌ مقصودٌ لطرفَي المقارنة.
_ECHO_COMPARISON_RE = re.compile(
    r"مقابل|مقارنةً|مقارنة|بينما|في حين|أمام|versus|vs\.?|compared", re.I)
# (٣) الورودُ الثاني داخل قوسٍ ⇒ شرحٌ مقحوم: عيبٌ حقيقيّ لكنه من عائلةِ
#     المسرد (الصنف ٤ — «مصطلحٌ يُستعمل بلا تعريف»، ويحظره أصلاً
#     `PLAIN_LANGUAGE_RULE`: «ولا شرحَ بين قوسين وسط الجملة»). يُترك لقناته
#     كي لا يُبلِّغ فحصان عيباً واحداً بتسميتين.
_ECHO_PAREN_RE = re.compile(r"[\(（][^\)）]*$")


def _check_template_interpolation(text: str, lang: str = "ar") -> list[dict]:
    """`template_interpolation` (الصنف ٢، تحذيريّ): جملةٌ كسرتها خانةٌ فارغة
    أو إحالةٌ إلى ما أُعلِن غائباً أو صدى كيانٍ في وصفِه.

    أربعُ قنوات:

    1. **خانةٌ لم تُحشَ** — `{label}` حرفياً في نصٍّ معروض.
    2. **أثرٌ مكانيكيّ** — قوسٌ فارغ/نقطتان متدلّيتان/فراغٌ مزدوج، مُقاساً
       بأن `silk_i18n.repair_interpolation` تُغيّر السطر. مِعيارٌ واحد
       للإصلاح والفحص، فلا تتباعد قاعدتان.
    3. **إحالةٌ إلى غائب** — «أعلاه/أدناه» على مسافةٍ قريبة من إعلانِ غياب.
    4. **صدى كيان** — الاسمُ نفسُه داخل وصفِه («بالحصة السعودية» بعد
       «السعودية»)، بحدِّ كلمةٍ ونافذةٍ ثلاثِ كلمات.
    """
    if not text:
        return []
    from silk_i18n import repair_interpolation, tidy_punctuation
    body = _split_off_appendix(text)
    findings: list[dict] = []
    seen: set = set()

    def _add(kind: str, detail: str, pos: int) -> None:
        sig = (kind, detail)
        if sig in seen:
            return
        seen.add(sig)
        findings.append({
            "check": "template_interpolation", "repairable": True,
            "note": (f"{kind} — القسم «{_reader_section_of(body, pos)}»: "
                     f"…{_reader_snippet(body, pos, pos + len(detail))}…")})

    m = _UNRENDERED_SLOT_RE.search(body)
    if m:
        _add(f"خانةُ قالبٍ لم تُحشَ «{m.group(0)}»", m.group(0), m.start())
    # مِعيارُ القالب (`repair_interpolation`) يُقاس على **سطرٍ كاملٍ بذاته**:
    # نقطتان متدلّيتان آخرَ سطرٍ لا يتلوه متنٌ = خانةٌ فُرِّغت فعلاً.
    lines = body.splitlines()
    for n, raw in enumerate(lines):
        s = raw.strip()
        if not s or s.startswith(("#", "|", ">")):
            continue
        if repair_interpolation(s) == tidy_punctuation(s):
            continue
        if not s.rstrip().endswith((":", "：")):
            continue
        # **نقطتان يتلوهما متنٌ عنوانٌ مشروع** (رُصد في المراجعة الذاتية):
        # «الشرط الحاجب:» آخرَ سطرٍ يكمله السطرُ التالي نثرٌ سليم، وإسقاطُ
        # نقطتيه إفسادٌ لا إصلاح. الخانةُ المُفرَّغة تُخلِّف نقطتين **لا
        # يتلوهما شيء**.
        nxt = next((x.strip() for x in lines[n + 1:] if x.strip()), "")
        if nxt and not nxt.startswith(("#", "|", ">")):
            continue
        _add("نقطتان متدلّيتان — خانةٌ فُرِّغت بلا صيغةِ فراغٍ نحوية",
             s[:40], body.find(raw))

    for line in body.splitlines():
        stripped = line.strip()
        # الجداول والعناوين تُستثنى: فراغُ المحاذاة فيها مقصودٌ لا عطب.
        if not stripped or stripped.startswith(("#", "|", ">")):
            continue
        # **المِعيارُ الآمنُ على النثر** لا معيارُ القالب: شرطةٌ آخرَ سطرٍ
        # في نثرٍ مطويّ وسطُ جملةٍ لا أثرُ خانةٍ فارغة (قياسٌ على مدوّنة
        # Nadec). والقناتان بمِعيارَيهما أصدقُ من قناةٍ بمعيارٍ واحد خاطئ.
        if tidy_punctuation(stripped) != stripped:
            _add("أثرُ خانةٍ فارغة (قوسٌ فارغ/نقطتان متدلّيتان/فراغٌ مزدوج)",
                 stripped[:40], body.find(line))

    for m in _SPATIAL_REF_RE.finditer(body):
        lo = max(0, m.start() - _SPATIAL_GAP_WINDOW)
        hi = min(len(body), m.end() + _SPATIAL_GAP_WINDOW)
        window = _norm_ar(body[lo:hi])
        gap = next((g for g in _GAP_WORDS_NEAR if _norm_ar(g) in window), None)
        if gap:
            _add(f"إحالةٌ «{m.group(0)}» إلى ما أُعلِن «{gap}»",
                 m.group(0), m.start())

    for line in body.splitlines():
        if line.strip().startswith(("#", "|", ">")):
            continue
        words = [(w.group(0), w.start()) for w in _ECHO_WORD_RE.finditer(line)]
        norm = [_norm_ar(w) for w, _ in words]
        for i, w in enumerate(norm):
            if w in _ECHO_UNIT_NORM:
                continue
            for j in range(i + 1, min(i + 1 + _ECHO_MAX_GAP, len(norm))):
                if norm[j] != w or j == i + 1:
                    continue
                between = line[words[i][1] + len(words[i][0]):words[j][1]]
                if _ECHO_COMPARISON_RE.search(between):
                    break
                # الورودُ الثاني داخل قوسٍ ⇒ شرحٌ مقحوم (قناةُ الصنف ٤).
                if _ECHO_PAREN_RE.search(line[:words[j][1]]):
                    break
                _add(f"صدى كيانٍ داخل وصفِه «{words[i][0]}»",
                     words[i][0], body.find(line) + words[i][1])
                break
    return findings


# ══════ الصنف ٣ (موجة عيوب التقرير) — عرضُ الأرقام والوحدات والتواريخ ══════
# بلاغُ المالك: «36,234,200.146 مقابل 26730»؛ والدرجةُ 65 و0.65 و65% في
# تقريرٍ واحد؛ وأرقامٌ بلا وحدةٍ ولا سنة؛ وبياناتُ 2018 بلا سنةٍ مطبوعة؛
# وتوقّعُ 2024 بصيغةِ المستقبل في 2026؛ وتاريخُ التشغيل مكانَ تاريخِ الرصد.
#
# الجذرُ (خمسُ عائلاتِ تنسيقٍ متوازية) مُصلَحٌ بمُنسِّقٍ واحد في
# `silk_narrative`. وهذه أربعُ قواعدَ تحذيرية — حرّاسُ انحدارٍ له، وحرّاسٌ
# أصليّون لنثر الكاتب الذي لا يمرّ على مُنسِّق.

# (١) تعدّدُ صيغِ الدرجة: نفسُ القيمة بصيغتين.
_SCORE_OF_100_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:من|/|out of)\s*100")
_SCORE_WORD_RE = re.compile(
    r"(?:قوة (?:هذه )?الفرصة|الدرجة الموزونة|الدرجة|opportunity strength"
    r"|weighted score)[^\d\n]{0,25}(\d{1,3}(?:\.\d+)?)\s*(%|٪)?")
_SCORE_FRACTION_RE = re.compile(
    r"(?:قوة (?:هذه )?الفرصة|الدرجة)[^\d\n]{0,25}(0\.\d+)")

# (٢) مقدارٌ كبير بلا عملة: «مليون/مليار» أو رقمٌ ≥ أربع خانات في جملةِ مالٍ
# بلا رمزِ عملةٍ أو اسمِها قريباً.
_MAGNITUDE_WORD_RE = re.compile(r"\b(?:مليون|مليار|ألف)\b|\b(?:million|billion)\b")
_CURRENCY_NEAR_RE = re.compile(
    r"دولار|يورو|ريال|درهم|دينار|جنيه|نايرا|روبية|ين\b"
    r"|\b(?:USD|EUR|SAR|AED|QAR|KWD|JOD|DZD|YER|JPY|NGN|INR|EGP|GBP)\b"
    r"|[$€£¥]", re.I)
# كلماتُ سياقٍ غير ماليّ: مقدارٌ عن سكّانٍ أو أطنانٍ أو وحداتٍ لا يحتاج عملة.
_NON_MONEY_CTX_RE = re.compile(
    r"نسمة|سكان|السكان|طن|أطنان|كجم|كيلوغرام|لتر|عبوة|قطعة|وحدة|زيارة"
    r"|استعلام|بحث|مصنع|منشأة|شركة|نقطة|درجة|tonne|kg|litre|liter|units?"
    r"|population|searches", re.I)
_MONEY_WINDOW = 55

# (٣) بياناتٌ أقدمُ من ثلاثِ سنواتٍ تقود جملةً بلا سنةٍ مطبوعة.
_STALE_YEARS_DEFAULT = 3
_ANY_YEAR_RE = re.compile(r"\b(19\d\d|20\d\d)\b")

# (٤) تاريخُ رصدٍ يساوي تاريخَ التشغيل — ساعةُ خطِّ التجميع ليست معطىً.
_OBSERVED_LABEL_RE = re.compile(
    r"(?:تاريخ (?:ال)?رصد|رُصد (?:في|بتاريخ)|observ(?:ed|ation) date)"
    r"[^\d\n]{0,20}(\d{4}-\d{2}-\d{2})")


_STALE_YEAR_WINDOW = 90


def _as_number(v: object) -> "float | None":
    """رقمٌ من قيمةِ دليلٍ — أو `None` (بلا استثناءٍ يُسقِط الفحص)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _significant_number_mentions(body: str, num: float) -> list:
    """مواضعُ ذكرِ الرقم في النثر بصيغتَي العرض المعتادتين.

    الرقمُ يُعرَض إمّا كاملاً بفاصلِ آلاف («7,120,000») أو مختزلاً بمقداره
    («7.12 مليون»). لا تُلتقَط الأرقامُ الصغيرة (< 1000) كي لا يُطابَق
    «2» من نصٍّ آخر — الرقمُ الصغير يُميَّز بقيمته لا بذاته.
    """
    if abs(num) < 1000:
        return []
    out: list = []
    cands = {f"{num:,.0f}", f"{num:.0f}"}
    if abs(num) >= 1e6:
        cands.add(f"{num / 1e6:,.2f}".rstrip("0").rstrip("."))
        cands.add(f"{num / 1e6:,.1f}".rstrip("0").rstrip("."))
    if abs(num) >= 1e9:
        cands.add(f"{num / 1e9:,.2f}".rstrip("0").rstrip("."))
    for c in cands:
        if len(c) < 3:
            continue
        i = body.find(c)
        if i >= 0:
            out.append((i, i + len(c)))
    return out


def _check_score_format_drift(text: str) -> list[dict]:
    """`score_format_drift` (الصنف ٣، تحذيريّ): الدرجةُ بأكثر من صيغة.

    الصيغةُ المعتمدة واحدة: «N من 100» (`silk_narrative.fmt_score`). ظهورُ
    كسرٍ 0–1 أو نسبةٍ مئوية للدرجة نفسِها في التقرير خلطُ مقاييس — البلاغ
    المرصود: 65 و0.65 و65% لنفس الدرجة.
    """
    if not text:
        return []
    body = _split_off_appendix(text)
    forms: dict = {}
    for m in _SCORE_OF_100_RE.finditer(body):
        forms.setdefault("من 100", m.group(0).strip())
    for m in _SCORE_FRACTION_RE.finditer(body):
        forms.setdefault("كسر 0–1", m.group(0).strip())
    for m in _SCORE_WORD_RE.finditer(body):
        if m.group(2):                       # نسبةٌ مئوية للدرجة
            forms.setdefault("نسبة مئوية", m.group(0).strip())
    if len(forms) < 2:
        return []
    shown = "، ".join(f"«{v}» ({k})" for k, v in forms.items())
    return [{"check": "score_format_drift", "repairable": True,
             "note": ("الدرجةُ معروضةٌ بأكثر من صيغة في تقريرٍ واحد: " + shown
                      + " — الصيغةُ المعتمدة واحدة: «N من 100» "
                        "(silk_narrative.fmt_score)")}]


def _check_amount_without_currency(text: str) -> list[dict]:
    """`amount_without_currency` (الصنف ٣، تحذيريّ): مقدارٌ ماليٌّ بلا عملته.

    يُفحَص بالسياق لا عارياً: «38 مليون نسمة» و«2,500 طن» مقاديرُ مشروعةٌ
    بلا عملة، و«2500» قيمةُ مؤشرِ تركّزٍ لا مال. القاعدةُ تُطلِق حين يكون
    المقدارُ في سياقٍ ماليٍّ صريح بلا رمزِ عملةٍ قريب.
    """
    if not text:
        return []
    body = _split_off_appendix(text)
    findings: list[dict] = []
    seen: set = set()
    for m in _MAGNITUDE_WORD_RE.finditer(body):
        lo = max(0, m.start() - _MONEY_WINDOW)
        hi = min(len(body), m.end() + _MONEY_WINDOW)
        window = body[lo:hi]
        if _CURRENCY_NEAR_RE.search(window) or _NON_MONEY_CTX_RE.search(window):
            continue
        frag = " ".join(window.split())[:70]
        if frag in seen:
            continue
        seen.add(frag)
        findings.append({
            "check": "amount_without_currency", "repairable": True,
            "note": (f"مقدارٌ بلا عملةٍ ولا وحدةٍ معلَنة: «{m.group(0)}» — "
                     f"القسم «{_reader_section_of(body, m.start())}»: "
                     f"…{frag}…")})
    return findings[:5]


def _check_stale_data_without_year(dr: dict, text: str = "") -> list[dict]:
    """`stale_data_without_year` (الصنف ٣، تحذيريّ): **قيمةٌ** من بياناتٍ
    أقدمَ من ثلاثِ سنواتٍ مذكورةٌ في النثر بلا سنتها المطبوعة قريباً.

    القارئُ لا يستطيع تقديرَ صلاحيةِ رقمٍ لا يعرف سنته؛ و«بيانات 2018 بلا
    سنةٍ مطبوعة» هي العلّةُ المرصودة حرفياً.

    **الشرطُ قيمةٌ مذكورةٌ لا سنةٌ موجودةٌ في الأدلة** (تضييقٌ جاء من
    القياس): مدوّنةُ الكويت تحمل دليلاً من 2021 لا يذكره المتنُ أصلاً —
    ومطالبةُ تقريرٍ بطبعِ سنةِ رقمٍ لم يستعمله لومٌ على ما لم يفعل. فتُقرَأ
    قيمةُ كلّ حقيقةٍ متقادِمة، ويُطلَق الفحصُ حين تظهر القيمةُ في النثر
    ولا تظهر سنةٌ في نافذتها.

    **وهذه القاعدةُ إنفاذُ ما كان الموجّهُ يأمر به بلا حارس:** البند 2.1 من
    «إفصاح جودة البيانات» (`silk_ai_judge.deep_report`) يُلزِم الكاتبَ بحملِ
    وسمِ السنة «حيثما ذكرت تلك الحقيقة في السرد… كي لا تُقرأ كأنها راهنة»
    — ولم يكن شيءٌ يتحقّق منه. قاعدةٌ في موجّهٍ بلا فحصٍ أمنيةٌ لا قاعدة.
    """
    body = _split_off_appendix(text or _report_text(dr))
    if not body:
        return []
    try:
        cutoff = int(os.environ.get("SILK_STALE_DATA_YEARS",
                                    _STALE_YEARS_DEFAULT))
    except ValueError:
        cutoff = _STALE_YEARS_DEFAULT
    import datetime
    now = datetime.date.today().year
    # حقائقُ الأدلة بقِيَمها وسنواتها — نفسُ منبعِ `_stale_years_in_view`.
    facts: list = []
    for m in (dr.get("missions") or {}).values():
        facts.extend((m or {}).get("findings") or [])
    for dps in ((dr.get("analyst") or {}).get("by_category") or {}).values():
        facts.extend(dps or [])
    findings: list[dict] = []
    seen: set = set()
    for f in facts:
        if not isinstance(f, dict):
            continue
        yr = f.get("data_year")
        val = f.get("value")
        if not (isinstance(yr, (int, float)) and not isinstance(yr, bool)):
            continue
        yr = int(yr)
        if now - yr <= cutoff:
            continue
        num = _as_number(val)
        if num is None:
            continue
        for m in _significant_number_mentions(body, num):
            win = body[max(0, m[0] - _STALE_YEAR_WINDOW):
                       m[1] + _STALE_YEAR_WINDOW]
            if _ANY_YEAR_RE.search(win):
                continue
            key = (yr, m[0])
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                "check": "stale_data_without_year", "repairable": True,
                "note": (f"رقمٌ من بيانات {yr} (أقدمُ من {cutoff} سنوات) "
                         f"مذكورٌ بلا سنته — القسم "
                         f"«{_reader_section_of(body, m[0])}»: "
                         f"…{_reader_snippet(body, m[0], m[1])}…")})
            break
    return findings[:5]


def _check_observation_date_equals_run_date(view: dict) -> list[dict]:
    """`observation_date_equals_run_date` (الصنف ٣، تحذيريّ): تاريخُ الرصد
    المطبوع يساوي تاريخَ تشغيل التقرير.

    ساعةُ خطِّ التجميع ليست معطىً: تاريخٌ يساوي تاريخَ التشغيل يعني — على
    الأرجح — أنه **استُعير** من الساعة لا من المصدر، فيقرأ القارئُ بياناتٍ
    قديمةً كأنها رُصدت اليوم. يُقارَن بـ`view["date"]` لا بساعةِ الفحص، كي
    لا يطلق الفحصُ على تقريرٍ قديمٍ يُعاد قراءته.
    """
    if not isinstance(view, dict):
        return []
    run = str(view.get("date") or "").strip()
    if not run:
        return []
    dr = view.get("deep_research") or {}
    body = _report_text(dr)
    surfaces = [body] + [str(x) for x in (dr.get("limits") or [])]
    for blob in surfaces:
        for m in _OBSERVED_LABEL_RE.finditer(blob or ""):
            if m.group(1) == run:
                return [{
                    "check": "observation_date_equals_run_date",
                    "repairable": True,
                    "note": (f"تاريخُ الرصد المطبوع ({m.group(1)}) يساوي "
                             "تاريخَ تشغيل التقرير — ساعةُ التشغيل ليست "
                             "معطىً؛ يُطبَع تاريخُ الرصد إن وُجد في "
                             "البيانات، وإلّا يُقال «تاريخ الرصد غير "
                             "معروف» (silk_narrative.fmt_observed_at)")}]
    return []


# ══════ الصنف ٤ (موجة عيوب التقرير) — انزياحُ التسمية والمصطلح ══════
# بلاغُ المالك: «الحكومة الحوثية» و«السلطات الحوثية» و«الحكومة» لجهةٍ واحدة
# في تقريرٍ واحد؛ وتسمياتُ نشاطٍ إنجليزية في جدولٍ عربيّ؛ ومصطلحاتٌ بلا تعريف.
#
# **التسمياتُ الإنجليزية مغطّاةٌ أصلاً بحاجز** (`language_consistency`) —
# مقيسٌ على «| Import export company |». فلا قاعدةَ ثانيةً لها هنا: عيبٌ
# واحدٌ بتسميتين يُضاعِف الضجيجَ ولا يزيد تغطية. الفكسُ (جدولُ الترجمة عند
# حدِّ العرض) في `silk_style_contract.activity_label_ar`.
#
# والقاعدتان أدناه تحذيريّتان، وتعملان **بلا انتظارِ تهيئة**: تسمياتُ السلطة
# المحيَّدة تُهيَّأ في `data/market_profiles.json` وتصير التسميةَ المفضَّلة
# متى حضرت، لكنّ كشفَ الانزياح مبنيٌّ على نصّ التقرير نفسِه — فلا يكون
# الحارسُ نائماً بانتظار بياناتٍ لم تُهيَّأ بعد (سابقةُ الدرس 98).

# جهةٌ مُنسَبة: رأسٌ رسميّ + نسبةٌ تُعرِّفه («الحكومة الحوثية»، «سلطات عدن»).
_AUTHORITY_QUALIFIED_RE = re.compile(
    r"(الحكومة|حكومة|السلطات|السلطة|سلطات|الإدارة|إدارة|الهيئة|هيئة)"
    r"\s+((?:ال)?[^\W\d_]{3,}[\u064b-\u0652]?)")
# رأسٌ عارٍ بلا نسبة: «وتفرض الحكومة رسماً» — مبهمٌ حين تُذكر جهتان.
_AUTHORITY_BARE_RE = re.compile(
    r"(?<![^\W\d_])(الحكومة|السلطات|السلطة)(?![^\W\d_])")
# نِسَبٌ لا تُعرِّف جهةً: صفةٌ عامّة أو كلمةُ ربطٍ تلي الرأسَ مصادفةً.
_AUTHORITY_GENERIC_QUAL = frozenset({
    "المحلية", "المحلي", "الرسمية", "الرسمي", "المعنية", "المختصة",
    "المركزية", "الوطنية", "الاتحادية", "الجديدة", "نفسها", "هناك",
    "التي", "الذي", "قد", "لم", "لا", "أن", "إن", "على", "في", "من",
    "بأن", "بأنه", "ذاتها", "المضيفة", "المستوردة", "المصدرة",
})


# اسمٌ منصوبٌ منوَّن («قيداً»، «رسماً»، «تصريحاً») مفعولُ الفعل لا نسبةُ
# الجهة — إشارةٌ صرفيةٌ عربيةٌ حقيقية، وهي بعينها ما أخطأت به الصيغةُ الأولى
# («وتفرض الحكومة قيداً ثالثاً» عُدَّت جهةً ثالثة).
_ACCUSATIVE_TANWEEN_RE = re.compile("(?:\u064b|\u0627\u064b|\u064b\u0627)$")


def _authority_mentions(body: str) -> dict:
    """{النسبة المُطبَّعة → {الرؤوسُ المستعملة معها}} — حتميّ، بلا معجم.

    الرؤوسُ تُحفَظ **بهجائها الأصليّ** للعرض (التطبيعُ للمطابقة لا للبلاغ:
    «الحكمه» في رسالةٍ يقرؤها مشغّلٌ خطأٌ في ذاته).
    """
    generic = {_norm_ar(g).replace("ال", "", 1)
               for g in _AUTHORITY_GENERIC_QUAL}
    out: dict = {}
    for m in _AUTHORITY_QUALIFIED_RE.finditer(body):
        head, qual = m.group(1), m.group(2)
        if qual in _AUTHORITY_GENERIC_QUAL:
            continue
        if _norm_ar(qual).replace("ال", "", 1) in generic:
            continue
        if _ACCUSATIVE_TANWEEN_RE.search(qual):
            continue
        key = _norm_ar(qual)
        out.setdefault(key, {"qual": qual, "heads": {}})
        out[key]["heads"].setdefault(_norm_ar(head), head)
    return out


# المرآةُ الإنجليزية — قفلُ التكافؤ (`test_no_undeclared_arabic_only_check`)
# التقطَ أن الصيغةَ الأولى عربيةُ المِجَسّ وحدها، فتخمُد صامتةً على تقريرٍ
# إنجليزيّ والمشغّلُ يقرأ PASS ويظنّه قياساً. والعيبُ نفسُه قائمٌ بالإنجليزية
# («the Houthi government» / «the Houthi authorities»)، فالمرآةُ أصدقُ من
# إعلانِ خمود.
_AUTHORITY_QUALIFIED_EN_RE = re.compile(
    r"\b(government|authorities|authority|administration)\s+"
    r"(?:of\s+)?([A-Z][A-Za-z'-]{2,})"
    r"|\b([A-Z][A-Za-z'-]{2,})\s+"
    r"(government|authorities|authority|administration)\b")
_AUTHORITY_BARE_EN_RE = re.compile(
    r"\bthe\s+(government|authorities)\b(?!\s+of\b)", re.I)
_AUTHORITY_GENERIC_QUAL_EN = frozenset({
    "Local", "Official", "Central", "National", "Federal", "Competent",
    "Relevant", "Host", "Importing", "Exporting", "The",
})


def _authority_mentions_en(body: str) -> dict:
    """نظيرُ `_authority_mentions` للإنجليزية — {النسبة → {الرؤوس}}."""
    out: dict = {}
    for m in _AUTHORITY_QUALIFIED_EN_RE.finditer(body):
        head = (m.group(1) or m.group(4) or "").lower()
        qual = m.group(2) or m.group(3) or ""
        if not head or not qual or qual in _AUTHORITY_GENERIC_QUAL_EN:
            continue
        out.setdefault(qual, {"qual": qual, "heads": {}})
        # الترتيبُ الطبيعيّ إنجليزياً «Houthi government» لا «government
        # Houthi» — البلاغُ يقرؤه مشغّلٌ، فلا يُقلَب.
        out[qual]["heads"].setdefault(head, f"{qual} {head}")
    return out


def _check_authority_naming_drift(view: dict, dr: dict,
                                  lang: str = "ar") -> list[dict]:
    """`authority_naming_drift` (الصنف ٤، تحذيريّ): جهةٌ واحدة بتسميتين، أو
    رأسٌ عارٍ («الحكومة») حيث يذكر التقريرُ جهتين مُنسَبتين.

    القارئُ لا يعرف أيَّ جهةٍ تعني عند تعدّد السلطات، وهو فرقٌ عمليّ: كلُّ
    جهةٍ تتحكّم بمنفذٍ وقيودٍ ورسومٍ مختلفة. التسمياتُ المفضَّلة تُهيَّأ في
    `data/market_profiles.json` (`authorities`) وتُذكَر في البلاغ حين تحضر.
    """
    body = _split_off_appendix(_report_text(dr))
    if not body:
        return []
    findings: list[dict] = []
    en = str(lang).lower().startswith("en")
    mentions = (_authority_mentions_en(body) if en
                else _authority_mentions(body))
    for row in mentions.values():
        if len(row["heads"]) > 1:
            findings.append({
                "check": "authority_naming_drift", "repairable": True,
                "note": (f"جهةٌ واحدة («{row['qual']}») مُسمَّاةٌ بأكثر من "
                         f"رأسٍ في التقرير: "
                         # القيمةُ المحفوظة جاهزةٌ للعرض بلغتها: العربيةُ
                         # تحفظ الرأسَ وحده والإنجليزيةُ تحفظ الترتيبَ كاملاً.
                         + "، ".join(
                             f"«{h}»" if " " in h else f"«{h} {row['qual']}»"
                             for h in sorted(row["heads"].values()))
                         + " — تسميةٌ واحدةٌ محيَّدةٌ للتقرير كلّه")})
            break
    if len(mentions) >= 2:
        bare = (_AUTHORITY_BARE_EN_RE if en
                else _AUTHORITY_BARE_RE).search(body)
        if bare:
            names = "، ".join(f"«{r['qual']}»" for r in
                              list(mentions.values())[:3])
            preferred = _configured_authorities(view)
            tail = (f" التسمياتُ المُهيَّأة لهذا السوق: {preferred}."
                    if preferred else
                    " ولا تسمياتَ مُهيَّأة لهذا السوق في "
                    "data/market_profiles.json — تُهيَّأ موثَّقةً.")
            findings.append({
                "check": "authority_naming_drift", "repairable": True,
                "note": (f"«{bare.group(1)}» بلا نسبةٍ تُعرِّفها بينما يذكر "
                         f"التقريرُ جهتين أو أكثر ({names}) — القارئُ لا "
                         "يعرف أيَّ جهةٍ تعني، وكلُّ جهةٍ منفذٌ وقيودٌ "
                         "ورسومٌ مختلفة." + tail)})
    return findings


def _configured_authorities(view: dict) -> str:
    """تسمياتُ السلطة المُهيَّأة لسوق التقرير — نصٌّ للعرض أو فراغ.

    مأخذُ المراجعة الذاتية: كان يقرأ `view["market"]["iso3"]` وحدَه، وهو
    **غيرُ موجودٍ** في العرض الذي يبنيه `build_view` (الرمزُ في
    `deep_research.market.iso3`، كما تقرؤه الفحوصُ الشقيقة) — فالبلاغُ كان
    سيبقى يقول «لا تسمياتَ مُهيَّأة» بعد تهيئتِها (الدرس ١٨٦: اختبِر المفتاحَ
    الذي يبنيه `build_view` فعلاً).
    """
    try:
        import silk_profiles
        _v = view or {}
        _dr = (_v.get("deep_research") or {}) if isinstance(_v, dict) else {}
        iso3 = str((_v.get("market") or {}).get("iso3")
                   or (_dr.get("market") or {}).get("iso3") or "").upper()
        prof = silk_profiles.market_profile(iso3) if iso3 else None
        rows = (prof or {}).get("authorities") or []
        names = [str(silk_profiles.cited_value(r) or "").strip()
                 for r in rows if r]
        return "، ".join(f"«{n}»" for n in names if n)
    except Exception:  # noqa: BLE001 — التهيئةُ تحسينُ بلاغٍ لا شرطُ فحص
        return ""


def _check_defined_term_without_definition(view: dict, dr: dict) -> list[dict]:
    """`defined_term_without_definition` (الصنف ٤، تحذيريّ): مصطلحٌ مُعرَّفٌ
    في المسرد يُستعمَل في المتن بلا أن يصل تعريفُه أيَّ سطحٍ يقرؤه القارئ.

    التعريفاتُ الثابتة (المرآة/عتباتُ التركّز/سعرُ الحدود/نسبةُ التحقّق)
    تُبنى حتمياً في `silk_render._apply_merchant_language` وتُعرَض في
    «مسرد المصطلحات». هذا حارسُ انحدارٍ لذلك المسار: مصطلحٌ في المتن بلا
    مدخلٍ في `view["deep_research"]["glossary"]` يعني أنّ بانيَ المسرد لم
    يمرّ على هذا النصّ (سطحُ عرضٍ ثانٍ يتباعد — العطبُ الذي تسدّه الموجة).
    """
    from silk_style_contract import METHODOLOGY_DEFINITIONS_ORDER
    body = _split_off_appendix(_report_text(dr))
    if not body:
        return []
    plain = _norm_ar(body)
    defined = {_norm_ar(str((g or {}).get("term") or ""))
               for g in (dr.get("glossary") or [])}
    seen_gloss: set = set()
    missing: list = []
    for term, definition in METHODOLOGY_DEFINITIONS_ORDER:
        if definition in seen_gloss:
            continue
        if _norm_ar(term) not in plain:
            continue
        seen_gloss.add(definition)
        if not any(_norm_ar(term) in d or d in _norm_ar(term)
                   for d in defined if d):
            missing.append(term)
    if not missing:
        return []
    return [{"check": "defined_term_without_definition", "repairable": True,
             "note": ("مصطلحٌ مُستعمَلٌ في المتن بلا تعريفه في المسرد: "
                      + "، ".join(f"«{t}»" for t in missing[:4])
                      + " — التعريفُ سطرٌ واحدٌ ثابتٌ يُعرَض حين يَرِد "
                        "المصطلح (silk_style_contract."
                        "METHODOLOGY_DEFINITIONS)")}]


# ══════════ الصنف ٥ (موجة عيوب التقرير) — التكرار ══════════
# بلاغُ المالك: القرارُ التنظيميّ نفسُه مشروحٌ في خمسة أقسام، و«وهذا يعني»
# في كلّ فقرةٍ تقريباً. الجذرُ: كلُّ قسمٍ يُولَّد باستقلالٍ فلا يعرف ما شُرِح
# قبله — فالقاعدةُ في الموجّه (`SINGLE_EXPLANATION_RULE`) والإنفاذُ هنا.
#
# **ما هو مغطّىً أصلاً ولا يُكرَّر:** `_check_repeated_span` يلتقط تكراراً
# **حرفياً** لثماني كلماتٍ **داخل الفقرة الواحدة** — ونطاقُه الفقرةُ عمداً
# (§58: ذيلُ استشهادٍ متكرر عبر الأقسام نثرٌ مشروع). و`_check_style` يعدّ
# خمسةَ روابطَ ثقيلة **على مستوى المستند** (WARN عند ٣، FAIL عند ٥).
# فالناقصُ قناتان: **إعادةُ الصياغة** عبر الأقسام (لا تكرارٌ حرفيّ فلا
# يبلغها الأول)، و**تكرارُ الرابط داخل الفقرة** (العدّ المستنديّ لا يراه:
# «وهذا يعني» مرّتين في فقرةٍ ومرّةً في فقرتين = ٤ فقط).
_XSEC_MIN_WORDS = 8          # جملةٌ أقصرُ لا تحمل معنىً يُقارَن
# **مُعايَرٌ بالفصل المقيس** (تصحيحُ المراجعة الذاتية): أعلى تشابهٍ في إحدى
# عشرةَ مدوّنةٍ **سالبة** = 0.333 (قطر)، والعيبُ الحقيقيّ في التثبيتة
# الموجَبة = 0.538 (مصر: شرطُ التسجيل مشروحٌ في الخلاصة والتنظيم معاً).
# فالعتبةُ 0.45 بينهما: هامشٌ 35% فوق السالب و20% تحت الموجَب. القيمةُ
# الأولى (0.55) قِيست بسؤالٍ أضعف («هل يبلغ زوجٌ 0.45؟») فكانت **تفوّت
# العيبَ** — القياسُ الناقص أخطرُ من غيابه لأنه يُطمئن.
_XSEC_SIM_DEFAULT = 0.45
_XSEC_SENT_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n")
_XSEC_WORD_SPLIT = re.compile(r"[^\w؀-ۿ]+")


def _report_sections(text: str) -> list:
    """[(عنوانُ القسم، متنُه)] — تقسيمٌ على العناوين نفسِها التي يعرفها
    `_HEADING_RE`، فلا تعريفَ ثانياً للقسم يتباعد."""
    out: list = []
    cur, buf = "قبل أول عنوان", []
    for line in (text or "").splitlines():
        m = _HEADING_RE.match(line)
        if m:
            out.append((cur, "\n".join(buf)))
            cur, buf = m.group(1).strip(), []
        else:
            buf.append(line)
    out.append((cur, "\n".join(buf)))
    return out


def _xsec_sentences(text: str) -> list:
    """[(القسم، الجملة، مجموعةُ كلماتها المُطبَّعة)] — نثرٌ فقط."""
    out: list = []
    for name, body in _report_sections(text):
        for raw in _XSEC_SENT_SPLIT.split(body or ""):
            sent = " ".join(raw.split())
            if not sent or sent.startswith(("|", "#", ">", "-", "*")):
                continue
            words = [w for w in _XSEC_WORD_SPLIT.split(_norm_ar(sent))
                     if len(w) > 2]
            if len(words) >= _XSEC_MIN_WORDS:
                out.append((name, sent, frozenset(words)))
    return out


def _check_cross_section_near_duplicate(text: str) -> list[dict]:
    """`cross_section_near_duplicate` (الصنف ٥، تحذيريّ): الحقيقةُ نفسُها
    مشروحةٌ في قسمين — **إعادةُ صياغةٍ** لا تكرارٌ حرفيّ.

    القياسُ تشابهُ مجموعتَي الكلمات (Dice/Jaccard على الكلمات المُطبَّعة
    الأطولَ من حرفين) — نفسُ أسلوبِ مطابقةِ الأسماء المحافظ في
    `correlation.py`. العتبةُ **0.45 مُعايَرةٌ بالفصل المقيس** كما يشرح
    تعليقُ `_XSEC_SIM_DEFAULT`: أعلى تشابهٍ سالبٍ 0.333 والعيبُ الموجَب
    0.538. (كان هذا السطرُ يقول 0.55 — قيمةً سابقةً قِيست بسؤالٍ أضعف
    فكانت تفوّت العيب؛ ومأخذُ المراجعة الذاتية أنّ التوثيقَ بقي عليها.)
    تُضبَط بـ`SILK_XSEC_SIM`.

    الجملُ داخل القسم الواحد **مستثناة**: تفصيلٌ متدرّجٌ داخل قسمه مشروع،
    والعيبُ المرصود عبورُ الأقسام.
    """
    if not text:
        return []
    try:
        thresh = float(os.environ.get("SILK_XSEC_SIM", _XSEC_SIM_DEFAULT))
    except ValueError:
        thresh = _XSEC_SIM_DEFAULT
    sents = _xsec_sentences(_split_off_appendix(text))
    best = None
    for i in range(len(sents)):
        for j in range(i + 1, len(sents)):
            if sents[i][0] == sents[j][0]:
                continue
            a, b = sents[i][2], sents[j][2]
            union = len(a | b)
            if not union:
                continue
            sim = len(a & b) / union
            if sim >= thresh and (best is None or sim > best[0]):
                best = (sim, sents[i], sents[j])
    if not best:
        return []
    sim, first, second = best
    return [{"check": "cross_section_near_duplicate", "repairable": True,
             "note": (f"الحقيقةُ نفسُها مشروحةٌ في قسمين (تشابه "
                      f"{round(sim * 100)}%): «{first[0]}» و«{second[0]}» — "
                      f"«{first[1][:80]}» مقابل «{second[1][:80]}». قسمٌ "
                      "واحدٌ يشرحها كاملةً، والآخرُ يُحيل إليها بجملةٍ واحدة")}]


def _check_connector_repeated_in_paragraph(text: str,
                                           lang: str = "ar") -> list[dict]:
    """`connector_repeated_in_paragraph` (الصنف ٥، تحذيريّ): الرابطُ نفسُه
    أكثرَ من مرّةٍ في الفقرة الواحدة.

    العدّ المستنديّ في `_check_style` لا يرى هذا: «وهذا يعني» مرّتين في
    فقرةٍ ومرّةً في فقرتين = أربعٌ، دون عتبةِ الخمس. والعيبُ المرصود
    («وهذا يعني» في كلّ فقرةٍ تقريباً) يظهر في **توزيعه** لا في مجموعه.
    """
    if not text:
        return []
    from silk_style_contract import (REPEATED_CONNECTORS,
                                     REPEATED_CONNECTORS_EN)
    en = str(lang).lower().startswith("en")
    conns = REPEATED_CONNECTORS_EN if en else REPEATED_CONNECTORS
    body = _split_off_appendix(text)
    findings: list[dict] = []
    # **المراجعةُ الذاتية للفرق (البند ٥٨)**: موضعُ القسم كان يُؤخَذ بـ
    # `body.find(أوّلُ كلمةٍ في الفقرة)` — وهي تُطابِق **أوّلَ ورودٍ في
    # المستند كلِّه**، فكلمةٌ شائعةٌ («في»، «السوق») تُرجِع موضعاً في قسمٍ
    # آخر ويُسمّى قسمٌ سليمٌ في البلاغ. الموضعُ الآن **موضعُ الفقرة نفسِها**
    # مُتعقَّباً بالتقطيع لا بالبحث.
    _pos = 0
    for para in re.split(r"(\n\s*\n)", body):
        if not para.strip() or para.startswith("\n"):
            _pos += len(para)
            continue
        _para_at = _pos
        _pos += len(para)
        # عنوانٌ يلاصق متنَه بلا سطرٍ فارغ يجعل الفقرةَ تبدأ بـ«##»، وإسقاطُ
        # الفقرة كلّها حينها يُخمِد الفحصَ على نصفِ التقارير — تُسقَط
        # **الأسطرُ** غيرُ النثرية وحدها (قياسٌ: القاعدةُ لم تُطلِق أصلاً).
        prose = [ln for ln in para.splitlines()
                 if not ln.strip().startswith(("|", "#", ">"))]
        flat = " ".join(" ".join(prose).split())
        if not flat:
            continue
        # موضعُ أوّلِ سطرٍ **نثريّ** داخل الفقرة لا موضعُ الفقرة: الفقرةُ قد
        # تبدأ بعنوانها بلا سطرٍ فاصل، فيقع الموضعُ على العنوان نفسِه
        # فيُبلَّغ «قبل أول عنوان» خطأً.
        _first = next((ln for ln in prose if ln.strip()), "")
        _at = _para_at + (para.find(_first) if _first else 0)
        hay = flat.lower() if en else _norm_ar(flat)
        for c in conns:
            needle = c.lower() if en else _norm_ar(c)
            n = hay.count(needle)
            if n > 1:
                findings.append({
                    "check": "connector_repeated_in_paragraph",
                    "repairable": True,
                    "note": (f"الرابط «{c}» تكرّر {n} مرّات في فقرةٍ واحدة "
                             # موضعُ أوّلِ سطرٍ نثريّ لا موضعُ الفقرة: الفقرةُ
                             # قد تبدأ بعنوانها، فيقع الموضعُ **قبله**
                             # فيُبلَّغ «قبل أول عنوان» خطأً.
                             f"— القسم «{_reader_section_of(body, _at)}»: "
                             f"…{flat[:70]}… للمعنى الواحد صيغٌ عدّة، أو "
                             "اذكر النتيجة بلا رابط")})
                break
    return findings[:3]


# ══════ الصنف ٦ (موجة عيوب التقرير) — قيمتان لمؤشرٍ واحد ══════
# بلاغُ المالك: «الحصة السعودية 10.44% في الملخّص و12.42% في الجدول»،
# و«10.44% هي أيضاً حصةُ الصين لعام 2023». رقمٌ واحدٌ بقراءتين، وقراءةٌ
# واحدة لكيانين.
#
# الجذرُ (`silk_ai_judge._facts`): الأرقامُ تصل الكاتبَ **نصّاً بلا هوية**،
# فلا شيء يربط رقماً في §1 برقمٍ في §6. العلاجُ `silk_figure_store`:
# معرّفٌ ثابتٌ لكلّ قراءة، وقاعدةٌ واحدةٌ موثَّقة تختار قراءةَ القرار.
#
# **خلف رايةٍ مطفأةٍ افتراضياً** (`SILK_FIGURE_STORE`): الفحصُ لا يدخل
# مجموعةَ الحجب إلّا بها (قرار المالك: لا حجب جديداً بلا راية). وحين تُطفأ
# يبقى تحذيرياً — يُقاس ولا يحجب.

# إفصاحٌ يسمّي الفرقَ بين قراءتين ⇒ ذكرُهما معاً صحيحٌ لا تعارض.
_DIVERGENCE_DISCLOSED_RE = re.compile(
    r"مرآة|المرآة|تصريح\s+مباشر|مباشرة|فجوة|فارق|الفارق|مقابل|بينما"
    r"|لنفس\s+السنة|سنة\s+أخرى|mirror|directly\s+reported|gap\b",
    re.IGNORECASE)
_DIVERGENCE_WINDOW = 220


def _rendered_figure_positions(body: str, value: float) -> list:
    """مواضعُ ظهورِ قيمةٍ في النثر.

    `_significant_number_mentions` يشترط ≥1000 كي لا يُطابِق رقماً صغيراً
    مصادفةً — والحصصُ والنِّسَب (10.44) دونه. فالقيمُ الصغيرة تُطابَق
    **بحرفها متبوعةً بعلامة نسبة** حصراً: قيدٌ يمنع مطابقةَ «10» من «2010».
    """
    if abs(value) >= 1000:
        return _significant_number_mentions(body, value) or []
    out: list = []
    for form in {f"{value:g}", f"{value:.2f}".rstrip("0").rstrip(".")}:
        if len(form) < 2:
            continue
        # **المراجعةُ الذاتية للفرق (البند ٥٨)**: الصيغةُ المشتقّة من `:g`
        # تُسقِط الصفرَ العشريّ («30.0» ⇒ «30»)، والريبو يطبع الحصصَ
        # الصحيحةَ بصفرٍ عشريّ («30.0%») — فكان المُطابِقُ يفوّتها ويصمت
        # الفحصُ الحاجبُ (عائلةُ الدرس 98: حارسٌ لا يمكن أن يُطلِق).
        # الأصفارُ العشريةُ اللاحقةُ مقبولةٌ بعد الرقم صراحةً.
        for m in re.finditer(
                rf"(?<![\d.]){re.escape(form)}(?:\.0+)?\s*[%٪]", body):
            out.append((m.start(), m.end()))
            break
    return out


def _check_metric_value_divergence(view: dict, dr: dict) -> list[dict]:
    """`metric_value_divergence` (الصنف ٦): قراءتان لمؤشرٍ واحد تُعرَضان في
    التقرير **بلا تسميةِ الفرق**.

    حاجبٌ حين رايةُ `SILK_FIGURE_STORE` مفعّلة، وتحذيريٌّ بدونها.

    وذكرُ قراءتين **مع تسميةِ الفرق** صحيحٌ ومطلوب — تمييزُ المباشر عن
    المرآة عقدٌ محفوظ، وقد أثبت الصنف ١١ أنّ معاقبتَه كانت تحجب تقارير
    سليمة. فالشرطُ غيابُ الإفصاح لا وجودُ قراءتين.
    """
    import silk_figure_store as FS
    body = _split_off_appendix(_report_text(dr))
    if not body:
        return []
    store = FS.build(dr.get("missions"), dr.get("analyst"))
    blocking = FS.enabled()
    findings: list[dict] = []
    for metric, ids in (store.get("by_metric") or {}).items():
        if len(ids) < 2:
            continue
        figs = {f["id"]: f for f in store["figures"]}
        shown: list = []
        for fid in ids:
            fig = figs[fid]
            for lo, hi in _rendered_figure_positions(body, fig["value"]):
                shown.append((lo, hi, fig))
                break
        # قيمٌ **متمايزة** معروضة — تكرارُ القيمة نفسِها ليس تعارضاً.
        distinct = {round(f["value"], 6) for _, _, f in shown}
        if len(shown) < 2 or len(distinct) < 2:
            continue
        shown.sort(key=lambda t: (t[0], t[1]))   # بالموضع لا بالقاموس
        lo = max(0, shown[0][0] - 40)
        hi = min(len(body), shown[-1][1] + 40)
        span = body[lo:hi]
        if len(span) <= _DIVERGENCE_WINDOW * 2 \
                and _DIVERGENCE_DISCLOSED_RE.search(span):
            continue
        near = body[max(0, shown[0][0] - _DIVERGENCE_WINDOW):
                    shown[0][1] + _DIVERGENCE_WINDOW]
        if _DIVERGENCE_DISCLOSED_RE.search(near):
            continue
        vals = "، ".join(f"{f['id']}={_fmt_gate_num(f['value'])}"
                         for _, _, f in shown[:3])
        findings.append({
            "check": "metric_value_divergence",
            "repairable": not blocking,
            "note": (f"قراءتان أو أكثر للمؤشّر «{metric}» معروضتان في "
                     f"التقرير بلا تسميةِ الفرق: {vals} — سمِّ الفرق "
                     "(سنةٌ أخرى، تصريحٌ مباشر مقابل مرآة) أو اعرض قراءةً "
                     "واحدةً هي قراءةُ القرار "
                     f"({store['decision_reading'].get(metric)})")})
    return findings[:3]


# ── تحذيرٌ مرافق: قيمةٌ واحدة لكيانين في قسمٍ واحد ──────────────────────────
# «10.44% هي أيضاً حصةُ الصين لعام 2023» — تطابقٌ يكاد يكون نسخاً، ويستحقّ
# سؤالاً لا حجباً (قد يتطابق رقمان صدقاً).
_ENTITY_SHARE_RE = re.compile(
    r"([^\W\d_]{3,})\s*[:،]?\s*"
    r"(?:بحصة|حصة|بنسبة|عند|تبلغ|البالغة)?\s*"
    r"(\d{1,3}(?:\.\d+)?)\s*[%٪]")
# روابطُ بدايةِ الكلمة تُسقَط من الاسم المُبلَّغ («والصين» → «الصين»).
_ENTITY_LEAD_CONJ_RE = re.compile(r"^[وف]")


def _check_shared_value_across_entities(dr: dict) -> list[dict]:
    """`shared_value_across_entities` (الصنف ٦، تحذيريّ دائماً): نسبةٌ واحدة
    منسوبةٌ لكيانين مختلفين في القسم نفسِه."""
    body = _split_off_appendix(_report_text(dr))
    if not body:
        return []
    findings: list[dict] = []
    for name, sect in _report_sections(body):
        seen: dict = {}
        for m in _ENTITY_SHARE_RE.finditer(sect or ""):
            ent = _ENTITY_LEAD_CONJ_RE.sub("", " ".join(m.group(1).split()))
            pct = m.group(2)
            prior = seen.get(pct)
            if prior and _norm_ar(prior) != _norm_ar(ent):
                findings.append({
                    "check": "shared_value_across_entities",
                    "repairable": True,
                    "note": (f"النسبةُ {pct}% منسوبةٌ لكيانين في القسم "
                             f"«{name}»: «{prior}» و«{ent}» — تطابقٌ يستحقّ "
                             "مراجعةً (قد يكون نسخاً لا صدفة)")})
                break
            seen.setdefault(pct, ent)
        if findings:
            break
    return findings


# ══════ الصنف ٧ (موجة عيوب التقرير) — عددُ الشروط المفتوحة ══════
# بلاغُ المالك: «ثلاثةٌ في الملخّص، واثنان في التوصيات، وثلاثةٌ في إعادة
# التقييم». الجذرُ في `silk_render.open_conditions` (قائمةٌ واحدة، خمسةُ
# سطوحٍ بأربعِ سلوكيّات) — وهذا الفحصُ يقيس **ما يقوله النثرُ** مقابل
# القائمة الواحدة: عددٌ مذكورٌ في جملةٍ يخالف عددَ الشروط الفعليّ.
#
# حاجبٌ خلف رايةِ `SILK_OPEN_CONDITIONS_SINGLE`، وتحذيريٌّ بدونها.

# عددٌ عربيّ لفظاً — العيبُ المرصود كُتب لفظاً («شرطين») لا رقماً.
_AR_COUNT_WORDS = {
    "شرط واحد": 1, "شرطاً واحداً": 1, "شرطٌ واحد": 1,
    "شرطين": 2, "شرطان": 2, "شرطَين": 2,
    "ثلاثة شروط": 3, "ثلاث شروط": 3, "ثلاثةُ شروط": 3,
    "أربعة شروط": 4, "أربع شروط": 4, "أربعةُ شروط": 4,
    "خمسة شروط": 5, "خمس شروط": 5, "خمسةُ شروط": 5,
    "ستة شروط": 6, "ست شروط": 6, "ستةُ شروط": 6,
    "سبعة شروط": 7, "سبع شروط": 7,
    "ثمانية شروط": 8, "ثماني شروط": 8,
}
# صيغةٌ رقمية: «٣ شروط مفتوحة» / «شرطان (2)» / «2 شروط».
_DIGIT_COUNT_RE = re.compile(
    r"(\d{1,2})\s*(?:شرط|شروط|شرطاً|شروطاً)"
    r"|(?:شرط|شروط|شرطاً|شروطاً)\s*[\(（]\s*(\d{1,2})\s*[\)）]")
# سياقُ «مفتوح» شرطٌ لازم: «ثلاثة شروط صحّية» ليست عدَّ شروطِ القرار.
_OPEN_COND_CTX_RE = re.compile(r"مفتوح|مفتوحة|مفتوحين|مفتوحان|غير محسوم"
                               r"|لم تُغلَق|لم تغلق|قائمة")
_OPEN_COND_WINDOW = 60


def _stated_condition_counts(body: str) -> list:
    """[(العدد المذكور، الموضع، المقتطف)] — لفظاً ورقماً، بسياق «مفتوح»."""
    out: list = []
    plain = _norm_ar(body)
    for phrase, n in _AR_COUNT_WORDS.items():
        i = plain.find(_norm_ar(phrase))
        if i < 0:
            continue
        win = plain[max(0, i - _OPEN_COND_WINDOW):i + _OPEN_COND_WINDOW]
        if _OPEN_COND_CTX_RE.search(win):
            out.append((n, i, phrase))
    for m in _DIGIT_COUNT_RE.finditer(body):
        n = int(m.group(1) or m.group(2))
        win = body[max(0, m.start() - _OPEN_COND_WINDOW):
                   m.end() + _OPEN_COND_WINDOW]
        if _OPEN_COND_CTX_RE.search(_norm_ar(win)):
            out.append((n, m.start(), m.group(0).strip()))
    return out


def _check_open_conditions_count_mismatch(view: dict, dr: dict) -> list[dict]:
    """`open_conditions_count_mismatch` (الصنف ٧): عددٌ مذكورٌ في النثر
    يخالف عددَ الشروط المفتوحة الفعليّ، أو عددان مختلفان في تقريرٍ واحد.

    حاجبٌ خلف الراية، تحذيريٌّ بدونها. والعددُ المرجعيّ من **القائمة
    الواحدة** (`silk_render.open_conditions`) لا من عدِّ أسطرٍ في سطح.
    """
    import silk_render as R
    body = _split_off_appendix(_report_text(dr))
    if not body:
        return []
    top = ((view.get("markets") or [None])[0]
           if isinstance(view, dict) else None) or {}
    ed = top.get("entry_decision") or top.get("decision") or {}
    actual = R.open_conditions(ed)["count"]
    stated = _stated_condition_counts(body)
    if not stated:
        return []
    blocking = R.open_conditions_single()
    distinct = sorted({n for n, _, _ in stated})
    findings: list[dict] = []
    if len(distinct) > 1:
        shown = "، ".join(
            f"«{frag}» ({n}) في القسم «{_reader_section_of(body, pos)}»"
            for n, pos, frag in stated[:3])
        findings.append({
            "check": "open_conditions_count_mismatch",
            "repairable": not blocking,
            "note": (f"عددُ الشروط المفتوحة مذكورٌ بأكثر من قيمة في تقريرٍ "
                     f"واحد: {shown} — قائمةٌ واحدة وعددٌ واحد")})
    elif actual and distinct and distinct[0] != actual:
        n, pos, frag = stated[0]
        findings.append({
            "check": "open_conditions_count_mismatch",
            "repairable": not blocking,
            "note": (f"النثرُ يذكر «{frag}» ({n}) بينما الشروطُ المفتوحة "
                     f"الفعلية {actual} — القسم "
                     f"«{_reader_section_of(body, pos)}». العددُ يُقرأ من "
                     "القائمة الواحدة لا يُكتَب يدوياً")})
    return findings


# ══════ الصنف ٨ (موجة عيوب التقرير) — ثقةٌ عالية بمدخلاتٍ ناقصة ══════
# بلاغُ المالك: «ثقة عالية بينما عمودٌ أساسيٌّ غائب»، و«درجة 65 — عند
# العتبة بالضبط — وعمودُ الربحية مجهول»، و«نسبةُ التحقّق معروضةٌ كثقةِ حكم».
#
# القاعدةُ تُقال للقارئ لا تُخفى: لا «ثقةً عالية» مع جانبٍ أساسيٍّ مجهول أو
# شرطين مفتوحين. حاجبٌ خلف رايةِ `SILK_CONFIDENCE_DISCIPLINE`، تحذيريٌّ
# بدونها.
_HIGH_CONF_RE = re.compile(r"ثقة\s*عالية|ثقةٌ\s*عالية|عالية\s*\(\d{1,3}\s*%\)"
                           r"|high\s+confidence", re.IGNORECASE)


def _check_high_confidence_with_missing_pillar(view: dict,
                                               dr: dict) -> list[dict]:
    """`high_confidence_with_missing_pillar` (الصنف ٨): تسميةُ «ثقة عالية»
    على سطحٍ يقرؤه القارئ بينما جانبٌ أساسيٌّ مجهولٌ أو الشروطُ ≥٢.

    تُفحَص سطوحُ العرض **والنثر** معاً: العيبُ ظهر في الاثنين (لوحةُ الأساس
    تحمل التسمية، والكاتبُ يكتبها نثراً).
    """
    import silk_decision as D
    import silk_render as R
    if not isinstance(view, dict):
        return []
    top = ((view.get("markets") or [None])[0]) or {}
    ed = top.get("entry_decision") or top.get("decision") or {}
    pillars = ed.get("pillars") or {}
    if not pillars:
        return []
    cap = D.confidence_band_cap(pillars, ed.get("conditions"))
    if not cap:
        return []
    basis = ((view.get("decision") or {}).get("basis") or {})
    surfaces = [str(basis.get("confidence_band") or ""),
                str(basis.get("score_line") or ""),
                _split_off_appendix(_report_text(dr))]
    hit = next((s for s in surfaces if s and _HIGH_CONF_RE.search(s)), None)
    if not hit:
        return []
    missing = D.missing_core_pillars(pillars)
    why = (f"الجانبُ الأساسيّ «{D.pillar_label(missing[0])}» مجهول"
           if missing else
           f"{len(ed.get('conditions') or [])} شروطٌ مفتوحة")
    return [{
        "check": "high_confidence_with_missing_pillar",
        "repairable": not R.confidence_discipline(),
        "note": (f"تسميةُ «ثقة عالية» على سطحٍ يقرؤه القارئ بينما {why} — "
                 "السقفُ «متوسطة» حتى يُكمَل الجانبُ أو تُغلَق الشروط "
                 "(silk_decision.confidence_band_cap). الرقمُ لا يُمَسّ، "
                 "التسميةُ وحدها تُسقَّف")}]


_ABSENCE_FORBIDDEN = ("لم يُرصَد بعد", "لم يرصد بعد", "فجوة معلنة",
                      "يتعذّر الحساب", "يتعذر الحساب",
                      "غير محدد ضمن الحقائق", "غير قابل للحساب",
                      "غير مرصود", "غير مذكور",
                      # الثنائية الإنجليزية القانونية "not available"/
                      # "not computed" — وهذه محظوراتها (موجة سدّ الفجوات
                      # الثانية؛ العقد الإنجليزي يعلنها الآن نصاً).
                      "not observed", "declared gap", "cannot be computed",
                      # دورة C4: العقد يحظر «unspecified» العارية والإبرة
                      # كانت أضيق من قاعدتها.
                      "unobserved", "unspecified")


def _check_absence_vocabulary(text: str) -> list[dict]:
    plain = _norm_ar(text)
    hits = sorted({n for n in _ABSENCE_FORBIDDEN if _norm_ar(n) in plain})
    if not hits:
        return []
    return [{
        "check": "absence_vocabulary", "repairable": True,
        "note": ("مفردات غياب خارج المعجم الموحَّد: "
                 + "، ".join(f"«{h}»" for h in hits)
                 + " — المعتمد اثنتان فقط: «غير متاح» (لا وجود للرقم) "
                   "و«غير محسوب» (يوجد ولم يُحسب)")}]


# البند 18 (موجة سدّ الفجوات F5 — تحذيري كثلاثي P2 حتى معايرة Part B):
# جملة التحذير السياقي تكررت أربع مرات في تقرير #10؛ البديل صندوقٌ واحد
# أعلى التقرير (view["caveat_box"] الحتمي) + نجمة (*) عند كل رقم متأثر
# (تعليمة الكاتب). >1 ظهور لعائلة «مؤشر سياقي» في المتن = عودة الحادثة.
# «مؤشرا سياقيا» صيغة النصب بعد التطبيع (المنوَّنة تفقد ألفها التنوينية
# نصاً لا بنيةً) — كانت تفلت من العدّ (دورة تدقيق العقد المركب).
_CAVEAT_NEEDLES = ("مؤشر سياقي", "مؤشرا سياقيا", "contextual indicator")


def _check_caveat_repetition(text: str) -> list[dict]:
    plain = _norm_ar(text)
    n = sum(plain.count(_norm_ar(nd)) for nd in _CAVEAT_NEEDLES)
    if n <= 1:
        return []
    return [{
        "check": "caveat_repetition", "repairable": True,
        "note": (f"جملة التحذير السياقي («مؤشر سياقي») وردت {n} مرات في "
                 "المتن — تُذكر مرة واحدة (صندوق التحذير أعلى التقرير) "
                 "وتُوسَم الأرقام المتأثرة بنجمة (*) بدل تكرارها")}]


# البند 19 (تحذيري): دقة عشرية زائدة في النثر — ≤ منزلتين خارج الملاحق؛
# الدقة الكاملة مكانها الملحق. أرقام الجداول مستثناة (نثر فقط).
_EXCESS_DECIMALS_RE = re.compile(r"\b\d+\.\d{3,}\b")


def _split_off_appendix(text: str) -> str:
    """النص قبل قسم الملاحق — الدقة الكاملة هناك مشروعة."""
    m = re.search(r"^##\s+\d+\.\s*(?:الملاحق|Appendices)\s*$", text or "",
                  re.M)
    return (text or "")[:m.start()] if m else (text or "")


def _check_decimal_precision(text: str) -> list[dict]:
    body = "\n".join(_prose_lines(_split_off_appendix(text)))
    hits = _EXCESS_DECIMALS_RE.findall(body)
    if not hits:
        return []
    sample = "، ".join(sorted(set(hits))[:3])
    return [{
        "check": "decimal_precision", "repairable": True,
        "note": (f"أرقام بثلاث منازل عشرية فأكثر في النثر ({sample}"
                 + ("…" if len(set(hits)) > 3 else "")
                 + ") — ثلاثة أرقام معنوية في المتن والدقة الكاملة "
                   "في الملحق؛ منازل على رقم غير موثوق دقةٌ زائفة")}]


# البند 20 (تحذيري): متوسط طول الجملة ≤ 25 كلمة — جملة واحدة = فكرة واحدة
# + رقم واحد (#10: جملة 68 كلمة بأربعة أرقام في الخلاصة التنفيذية).
def _check_sentence_length(text: str) -> list[dict]:
    body = "\n".join(_prose_lines(_split_off_appendix(text)))
    # موجة سدّ الفجوات الثانية: النقطة العشرية («41.25») لا تقسم الجملة —
    # كانت تحيّد الفحص في نثرٍ رقمي كثيف؛ و«؛» و«\n» حدّا جملة أيضاً
    # (قائمة نقطية بلا نقاط كانت تلتحم جملةً واحدة عملاقة).
    lengths = [len(s.split())
               for s in re.split(r"[؟!؛\n]|(?<!\d)\.|\.(?!\d)", body)
               if len(s.split()) >= 3]
    if len(lengths) < 5:
        return []
    avg = sum(lengths) / len(lengths)
    if avg <= 25.0:
        return []
    return [{
        "check": "sentence_length", "repairable": True,
        "note": (f"متوسط طول الجملة {avg:.0f} كلمة (الحد 25) — جملة واحدة "
                 f"= فكرة واحدة ورقم واحد؛ أطول جملة {max(lengths)} كلمة")}]


def _check_decision_numbers_present(text: str) -> list[dict]:
    """`decision_numbers_present` (Part B، معيار الكتابة §9 — تحذيري على
    معيار التصعيد الرقمي نفسه، الدرس 135): قسم «أرقام القرار» يجمع أرقام
    المصدّر الفعلية (كلفة الدخول حتى أول شحنة، الشحنة التجريبية، التعادل،
    الزمن للفاتورة الأولى، أقصى الخسارة) — غيابه يبقي التقرير على أرقام
    المؤشرات وحدها (HHI/CAGR/حصص) بلا رقمٍ يتصرف به المصدّر."""
    if not (text or "").strip():
        return []
    from silk_style_contract import (DECISION_NUMBERS_HEADING,
                                     DECISION_NUMBERS_HEADING_EN)
    ar = _norm_ar(DECISION_NUMBERS_HEADING)
    en = DECISION_NUMBERS_HEADING_EN.lower()
    # دورة §58 الثانية: الإبرة **سطرُ عنوانٍ** (#/**/سطرٌ هو العنوان ذاته)
    # لا تحت-سلسلة في أي نثر — «قسم أرقام القرار غير متاح» كان يُسكِت
    # الفحص وهو بعينه ما وُجد الفحص ليكشفه.
    for ln in text.split("\n"):
        p = _norm_ar(ln).strip()
        if not p:
            continue
        is_heading = p.startswith(("#", "**")) or p in (ar, en)
        if is_heading and (ar in p or en in p):
            return []
    return [{"check": "decision_numbers_present", "repairable": True,
             "note": ("قسم «أرقام القرار» غائب — معيار الكتابة Part B يوجبه "
                      "داخل التوصيات الاستراتيجية (كلفة الدخول، الشحنة "
                      "التجريبية، نقطة التعادل، الزمن للفاتورة الأولى، "
                      "أقصى الخسارة؛ والمتعذر يُطبع بمعادلته وناقصه)")}]


def _check_unit_conversion_refusal(text: str, product: object) -> list[dict]:
    """`unit_conversion_refusal` (هدف الدراسة الاحترافية البند ١ — حاجز):
    «غير محسوب/غير متاح» يسمّي تحويلَ لتر↔كجم أو «الكثافة» مدخلاً ناقصاً
    لمنتجٍ كثافتُه ثابتٌ مسجّل في `CONVERSION_REGISTRY` — اختلاقُ عجزٍ عن
    ثابتٍ فيزيائيّ معروف (عائلة الدرس 84، دراسة #14: «العبوة باللتر وتحويل
    الكثافة إلى كجم غير متاح» فوق سعرٍ معروضٍ في الصف نفسه).

    **المنطقة العمياء المعلنة (الدرس 172):** يلتقط الجملةَ التي تجمع مفردةَ
    غيابٍ قانونية (غير محسوب/غير متاح/not computed/unavailable) مع ذكرِ
    التحويل صراحةً (كثافة/density أو لتر+كجم معاً) — إعادةُ صياغةٍ لا تسمّي
    التحويل («لا نعرف وزن العبوة») لا تُلتقط، وتلك فجوةُ حجمِ عبوةٍ مشروعة
    أصلاً. **جواب سؤال التأليف (الدرس 176):** سطرُ الفجوة القسري في برومبت
    الكاتب كان يفرض طباعة «غير محسوب — الناقص: …» بلا قيدٍ على تسمية
    التحويل — قُيِّد في نفس الموجة (silk_ai_judge، منع تسمية التحويل
    والكثافة) فلا يفرض البرومبت ما تحجبه البوابة (الدرس 156)."""
    if not (text or "").strip():
        return []
    from silk_economics import CONVERSION_REGISTRY, registry_category
    cat = registry_category(product)
    if not any(k[2] == cat for k in CONVERSION_REGISTRY):
        return []          # فئة بلا ثابت مسجّل — فجوة التحويل هناك مشروعة
    _absence = ("غير محسوب", "غير متاح", "not computed", "unavailable",
                "not available")
    for raw in re.split(r"[\n.؛;]+", text):
        s = _norm_ar(raw)
        if not s or not any(_norm_ar(a) in s for a in _absence):
            continue
        names_conversion = ("كثافه" in s or "density" in s
                            or (("لتر" in s or "litre" in s or "liter" in s)
                                and ("كجم" in s or "كيلوغرام" in s
                                     or "kg" in s)
                                and ("تحويل" in s or "convert" in s)))
        if names_conversion:
            return [{"check": "unit_conversion_refusal", "repairable": False,
                     "note": ("إعلان تعذّر تحويل لتر↔كجم لمنتجٍ كثافتُه "
                              "ثابت مسجّل بمصدره في سجل التحويل — الرقم "
                              "محسوب حتمياً ولا يُحجَب: "
                              + str(raw).strip()[:120])}]
    return []


def _exec_summary_body(text: str) -> "list[str] | None":
    """أسطر متن القسم ١ (الخلاصة التنفيذية) — بين `## 1.` وأول `##` تالٍ؛
    None حين لا قسم ١ أصلاً (يغطيه فحص البنية القائم لا فحوص الملخص)."""
    lines = (text or "").split("\n")
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+1\.", ln.strip()):
            start = i + 1
            break
    if start is None:
        return None
    body: list[str] = []
    for ln in lines[start:]:
        if re.match(r"^##\s+\d+\.", ln.strip()):
            break
        body.append(ln)
    return body


def _check_exec_summary_recommendation_first(text: str) -> list[dict]:
    """`exec_summary_recommendation_first` (هدف الدراسة الاحترافية البند ٤
    — تحذيري على معيار الدرس 135؛ نصُّ الهدف يطلب الحجب للوجود/السقف/
    المفردات لا لهذا، وفحص أول تشغيلة أظهر إطلاقه على نصوص مشروعة قديمة):
    أول سطر محتوى في الخلاصة التنفيذية يبدأ بسطر التوصية —
    القارئ يقرأ الأسطر الستة الأولى ويقرر، والحكم المدفون خلف جملة افتتاح
    طويلة هو عيب الدراسات المسلَّمة المؤسِّس.

    **المنطقة العمياء المعلنة (الدرس 172):** يفحص السطر الأول فقط وبكلمة
    «التوصية»/"Recommendation" في أوله (بعد تجريد **/#) — توصية مصاغة بفعل
    آخر («توصي الدراسة بـ…») في السطر الأول لا تُلتقط سلباً ولا إيجاباً:
    الفحص يطلق فقط حين لا يبدأ السطر بها وهي غائبة عن أوله. **جواب سؤال
    التأليف (الدرس 176):** معيار الكتابة نفسه يوجب «سطر التوصية وحده
    أولاً» (Part B) وتعليمة القسم ١ توجب الأطروحة أولاً — الموجّه والفحص
    على الجهة نفسها؛ لا مانع في الموجّه قد يُطلقه على مخرج صحيح."""
    body = _exec_summary_body(text)
    if body is None:
        return []
    first = ""
    for ln in body:
        s = ln.strip().lstrip("#*• ").strip()
        if s:
            first = s
            break
    if not first:
        return []          # قسم فارغ — فحص البنية/النص النائب يغطيه
    norm = _norm_ar(first)
    ok = norm.startswith(_norm_ar("التوصية")) \
        or first.lower().startswith("recommendation") \
        or norm.startswith(_norm_ar("توصي الدراسة")) \
        or norm.startswith(_norm_ar("يوصى"))
    if ok:
        return []
    # لا صدى لمحتوى السطر في الملاحظة (حارس السرية القائم: البوابة لا
    # تعيد تسريب ما رصدته) — يكفي العدّ.
    return [{"check": "exec_summary_recommendation_first",
             "repairable": True,
             "note": ("الخلاصة التنفيذية لا تفتتح بسطر التوصية — القارئ "
                      "يقرر من الأسطر الأولى (معيار الكتابة Part B)؛ "
                      f"سطرها الأول {len(first.split())} كلمة بلا توصية")}]


_SOURCE_NAME_TOKENS = (
    "Comtrade", "كومتريد", "World Bank", "البنك الدولي", "WITS",
    "FAOSTAT", "فاوستات", "GDELT", "OpenAlex", "Eurostat", "يوروستات",
    "IMF", "صندوق النقد",
)
_INTERNAL_VOCAB_TOKENS = (
    "HHI", "TAM", "SAM", "SOM", "CAGR", "بعثة", "الدرجة الموزونة",
    "غير مرصود", "فجوة معلنة", "مؤشر تركّز",
)


def _check_exec_summary_constraints(text: str) -> list[dict]:
    """`exec_summary_constraints` (البند ٤ — تحذيري على معيار الدرس 135):
    قيود الملخص التنفيذي: تحت 150 كلمة، بلا اسم مصدر، بلا مفردة قياس
    داخلية. القالب نفسه في Part B وتعليمة 6.2 — الموجّه والفحص متطابقان
    حرفياً (جواب الدرس 176، صيغا معاً في هذه الموجة).

    **المنطقة العمياء المعلنة (الدرس 172):** عدُّ الكلمات بالمسافات لا
    يقيس «تصمد وحدها»؛ و«نسبة بلا معناها» غير مقيسة هنا أصلاً (heuristic
    المعنى غير حتمي — يبقى على عاتق الموجّه وقراءة المالك)؛ وقائمتا
    المصادر والمفردات محدودتان بالمذكور."""
    body = _exec_summary_body(text)
    if body is None:
        return []
    blob = "\n".join(body)
    out: list[dict] = []
    words = [w for w in re.split(r"\s+", blob) if w.strip()]
    if len(words) > 150:
        out.append({"check": "exec_summary_constraints", "repairable": True,
                    "note": (f"الخلاصة التنفيذية {len(words)} كلمة — السقف "
                             "150: القارئ يقرر من ستة أسطر لا من صفحة")})
    hits = [t for t in _SOURCE_NAME_TOKENS if t.lower() in blob.lower()]
    if hits:
        out.append({"check": "exec_summary_constraints", "repairable": True,
                    "note": ("أسماء مصادر داخل الخلاصة التنفيذية (مكانها "
                             "الأقسام والملحق): " + "، ".join(hits[:4]))})
    vhits = [t for t in _INTERNAL_VOCAB_TOKENS
             if (_norm_ar(t) in _norm_ar(blob)) or (t.isascii() and t in blob)]
    if vhits:
        out.append({"check": "exec_summary_constraints", "repairable": True,
                    "note": ("مفردة قياس داخلية داخل الخلاصة التنفيذية: "
                             + "، ".join(vhits[:4]))})
    return out


_CLIENT_VOCAB_TERMS = (
    # هدف الدراسة الاحترافية (البند ٣): مصطلح قياس داخلي على سطح عرض عميلي.
    "الدرجة الموزونة", "مؤشر تركّز", "بعثة", "فجوة معلنة", "غير مرصود",
    "product_card", "weighted score",
)
_CLIENT_VOCAB_CONF_RE = re.compile(r"بثقة\s*\d{1,3}\s*%")


def _check_client_view_vocabulary(view: dict) -> list[dict]:
    """`client_view_vocabulary` (هدف الدراسة الاحترافية البند ٣ — تحذيري):
    مصطلح قياسٍ داخلي («الدرجة الموزونة»/«بثقة %»/«بعثة»/«مؤشر تركّز»…)
    على سطح عرضٍ يقرؤه العميل خارج نص التقرير — لوحة الأساس (سطر الدرجة
    وملاحظات الجوانب والشروط) وحدود التقرير وسطور المختصر (سابقة الدرس 146:
    المفردات المحظورة عاشت على أسطح اللوحة خارج مرمى فحوص النص).

    **المنطقة العمياء المعلنة (الدرس 172):** قائمة أنماط محدودة — مصطلح
    داخلي جديد غير مُدرَج لا يُلتقط، وقاعدة الإدراج سؤال الدرس 176 عند كل
    إضافة مفردة؛ ونص التقرير نفسه خارج هذا الفحص عمداً (تغطيه طبقة التعقيم
    وفحوصها). **جواب سؤال التأليف (الدرس 176):** الموجّه لا يُملي هذه
    المصطلحات على أسطح العرض — مصدرها قوالب i18n/render، وقد صيغت بلغة
    الزائر في نفس الموجة؛ الفحص حارسُ انحدارٍ لعودتها."""
    basis = ((view.get("decision") or {}).get("basis")
             if isinstance(view, dict) else None) or {}
    dr = (view.get("deep_research") if isinstance(view, dict) else None) or {}
    surface: list[str] = [str(basis.get("score_line") or ""),
                          str(basis.get("rule_line") or "")]
    surface += [str((r or {}).get("note") or "")
                for r in (basis.get("pillars") or [])]
    surface += [str(x) for x in (basis.get("conditions") or [])]
    surface += [str(x) for x in (dr.get("limits") or [])]
    surface += [str(x) for x in (view.get("brief") or [])
                if isinstance(view, dict)]
    blob = "\n".join(surface)
    norm = _norm_ar(blob)
    hits = sorted({t for t in _CLIENT_VOCAB_TERMS
                   if _norm_ar(t) in norm or t.lower() in blob.lower()})
    if _CLIENT_VOCAB_CONF_RE.search(blob):
        hits.append("بثقة %")
    if hits:
        return [{"check": "client_view_vocabulary", "repairable": True,
                 "note": ("مصطلح قياس داخلي على سطح عرض العميل — يُصاغ "
                          "بجملة معنى بلغة الزائر: " + "، ".join(hits))}]
    return []


# ── الموجة الرابعة (الدرس ٢٥٧): أرقامُ القياس الداخليّ على سطح العميل ────────
# قرارُ المالك: درجةُ ثقة الحكم ونسبةُ التحقّق وثقةُ المكوّن والدرجةُ من ١٠٠
# تخرج من نسخة العميل. المنعُ عند المنبع (`silk_ai_judge._summarize_verdict`)
# والكتمُ عند العرض (`client_hidden_metrics`) — وهذا **الكشفُ الدائم**: أيُّ
# سطحٍ ينسى السياسةَ لاحقاً، أو نموذجٌ يكتب التسميةَ من عنده، يُلتقَط بحزمةٍ
# حمراء لا ببلاغِ مالك. تحذيريٌّ لا حاجب («لا حجب جديداً»)، وخلف الراية:
# بدونها الأرقامُ معروضةٌ شرعاً فلا معنى لفحص غيابها.
# مراجعة §58: «40 من 100 شركة» و«ثقة عالية بأنّ…» نثرٌ تجاريّ سليم — فالدرجةُ
# تُلتقَط بقرينة قياسٍ قبلها، والتسميةُ تُستثنى حين يتبعها ما يجعلها كلاماً
# عاديّاً لا مقياساً.
_CLIENT_METRIC_PROBES: tuple = (
    re.compile(r"(?:قوة|درجة|تقييم|التقييم|نقاط|بدرجة|يبلغ|تبلغ)[^.\n]{0,25}?"
               r"\d{1,3}\s*من\s*100(?!\s*(?:شركة|مستورد|مستجيب|موزّع|موزع|عيّنة|عينة))"),
    re.compile(r"(?:ب|و)?ثقة\s*(?:عالية|متوسطة|منخفضة)"
               r"(?!\s*(?:بأن|بأنّ|لدى|في|من|أن|أنّ|بين|تجاه|نحو))"),
    re.compile(r"نسبة\s*التحق[قّ]"),
    re.compile(r"\d{1,3}\s*%\s*من\s*البيانات"),
    re.compile(r"\b(?:rate|rated|score|rating)[^.\n]{0,25}?\b\d{1,3}\s*(?:/|out of)\s*100\b",
               re.I),
    re.compile(r"\b(?:high|medium|low)\s+confidence\b(?!\s+(?:that|in|among|of))",
               re.I),
    re.compile(r"\bverification\s+rate\b", re.I),
    re.compile(r"\bconfidence\s*(?:level|score)?\s*[:=]?\s*\d{1,3}\s*%", re.I),
)


def _check_client_metric_exposure(view: dict, dr: dict) -> list[dict]:
    """`client_metric_exposure` (الموجة الرابعة — تحذيري خلف
    `SILK_CLIENT_METRIC_PRIVACY`): مقياسٌ داخليّ («NN من 100»، «بثقة عالية»،
    «نسبة التحقق»، «NN% من البيانات» ومرآتها الإنجليزية) على سطحٍ يقرؤه
    العميل — المختصرُ ونصُّ التقرير (بلا ملحقه) وحدودُه. ثنائيُّ المِجَسّ
    بالبناء (أنماطٌ عربيةٌ وإنجليزية معاً في `_CLIENT_METRIC_PROBES`)."""
    import silk_render as R
    if not R.client_metric_privacy() or not isinstance(view, dict):
        return []
    # ما يقرؤه **العميل** فقط: `basis.score_line` يبقى في العرض للمشغّل
    # والبوّابة (لا مفتاحَ يُحذَف) وتُسقِطه سطوحُ العميل بالقائمة — فلا يُفحَص.
    surfaces = {
        "brief": "\n".join(str(x) for x in (view.get("brief") or [])),
        "report": _split_off_appendix(_report_text(dr or {})),
        "limits": "\n".join(str(x) for x in ((dr or {}).get("limits") or [])),
    }
    hits = []
    for name, blob in surfaces.items():
        if not blob:
            continue
        for pat in _CLIENT_METRIC_PROBES:
            m = pat.search(blob)
            if m:
                hits.append(f"{name}: «{m.group(0)}»")
                break
    if not hits:
        return []
    return [{"check": "client_metric_exposure", "repairable": True,
             "note": ("رقمُ قياسٍ داخليّ على سطح العميل رغم سياسة الإخفاء "
                      "(SILK_CLIENT_METRIC_PRIVACY): " + "؛ ".join(hits)
                      + " — السطحُ المعنيّ لا يقرأ `client_hidden_metrics` "
                      "أو الكاتبُ كتب التسميةَ من عنده")}]


# ── الموجة الخامسة: رسمٌ بقيمةٍ بلا حقيقةٍ خلفها ──────────────────────────
def _chart_backing_numbers(dr: dict) -> set:
    """كلُّ رقمٍ يجوز رسمُه: حقائقُ البعثات وأرقامُ العرض الاقتصادي وسلسلةُ
    الواردات — المجموعةُ التي **يجب** أن تنتمي إليها كلُّ قيمةٍ مرسومة."""
    nums: set = set()

    def add(v) -> None:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.add(round(float(v), 6))

    for m in ((dr or {}).get("missions") or {}).values():
        findings = (m.get("findings") if isinstance(m, dict)
                    else getattr(m, "findings", None)) or []
        for f in findings:
            val = f.get("value") if isinstance(f, dict) else getattr(f, "value", None)
            add(val)
            if isinstance(val, dict):
                for k, v in val.items():
                    add(v)
                    if k == "top_suppliers" and isinstance(v, list):
                        for row in v:
                            if isinstance(row, dict):
                                add(row.get("share"))
    eco = (dr or {}).get("economics") or {}
    add(eco.get("hhi"))
    for st in (eco.get("waterfall") or []):
        if isinstance(st, dict):
            add(st.get("value"))
    rs = eco.get("reverse_solve") or {}
    add(rs.get("max_exw"))
    add(rs.get("shelf_price"))
    for sc in (rs.get("scenarios") or []):
        if isinstance(sc, dict):
            add(sc.get("max_exw"))
    for e in (eco.get("decision_numbers") or []):
        if isinstance(e, dict):
            add(e.get("value"))
            rng = e.get("range") or {}
            add(rng.get("low"))
            add(rng.get("high"))
    anchor_p = eco.get("anchor_price") or {}
    for k in ("per_unit", "per_kg", "per_litre", "raw_value", "value_usd"):
        add(anchor_p.get(k))
    for pt in (((dr or {}).get("imports") or {}).get("series") or []):
        if isinstance(pt, dict):
            add(pt.get("value"))
    return nums


def _check_chart_backing(dr: dict) -> list[dict]:
    """`chart_without_backing_value` (الموجة الخامسة — تحذيريّ، وخلف راية
    الرسوم بالبناء: بلا مفتاح `charts` لا فحص): قيمةٌ مرسومة بلا مقابلٍ في
    حقائق البعثات ولا في أرقام العرض الاقتصادي = رقمٌ ظهر في الرسم من عند
    المُصيِّر لا من البيانات — عائلةُ الاختلاق نفسُها على سطحٍ بصريّ. ورسمٌ
    بسلسلةٍ فارغة يُلتقَط أيضاً (قاعدةُ «لا رسمَ بلا بيانات»).

    وحدُّ ما يُثبِته مُعلَنٌ (مراجعة §58): المجموعةُ المرجعية تُبنى من العرض
    نفسِه الذي تقرؤه الرسوم، فالفحصُ يُثبِت **أن لا حسابَ في المُصيِّر** — لا
    أنّ الرقمَ صحيحٌ في أصله (ذلك شأنُ فحوص المحرّك). ووحدةُ الرقم وسياقُه
    ليسا من عمله: يحرسهما بانو الرسوم واختباراتُهم."""
    charts = (dr or {}).get("charts")
    if not isinstance(charts, list) or not charts:
        return []
    backing = _chart_backing_numbers(dr)
    hits: list[str] = []
    for ch in charts:
        if not isinstance(ch, dict):
            continue
        cid = str(ch.get("id") or "?")
        rows = [r for r in (ch.get("series") or []) if isinstance(r, dict)]
        if not rows:
            hits.append(f"{cid}: سلسلةٌ فارغة")
            continue
        vals = [ch.get("value")] if "value" in ch else []
        for r in rows:
            vals += [r.get("value"), r.get("low"), r.get("high")]
        for v in vals:
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            if round(float(v), 6) not in backing:
                hits.append(f"{cid}: {v}")
                break
    if not hits:
        return []
    return [{"check": "chart_without_backing_value", "repairable": True,
             "note": ("قيمةٌ على رسمٍ بلا حقيقةٍ خلفها (أو رسمٌ بلا سلسلة): "
                      + "؛ ".join(hits[:5])
                      + " — الرسمُ يقرأ من العرض المبنيّ حصراً، فقيمةٌ لا "
                        "مقابلَ لها تعني حساباً جديداً في مُصيِّر")}]


# مدى وحدةِ كلِّ مقياسٍ مرسوم — ثابتٌ مستقلٌّ عن القارئ (أرضيةُ HHI 100 هي
# نفسُها في `_structured_competition`: تحسم الحصةَ الملتبسة 84.05).
_CHART_METRIC_RANGE = {"hhi": (100.0, 10_000.0)}


def _chart_metric_reference(dr: dict, metric: str,
                            ledger: "dict | None") -> "dict | None":
    """سجلُّ المحرّك للمقياس (`ledger.entries[metric]`) — أو None.

    السجلُّ يُمرَّر من العرض (`view["ledger"]`، مبنيّاً من النتيجة الخام قبل
    أن يُسقِط `_dp` الأدلةَ الأصلية)؛ وبدونه يُبنى من `dr` نفسِه."""
    entries = (ledger or {}).get("entries") if ledger else None
    if entries is None:
        try:
            import silk_fact_ledger as _FL
            entries = _FL.build_ledger({"deep_research": dr or {}}).get(
                "entries") or {}
        except Exception:  # noqa: BLE001 — تعذّر السجلّ = لا مرجع
            return None
    e = entries.get(metric) or {}
    return e if e.get("value") is not None else None


def _check_chart_metric_identity(dr: dict,
                                 ledger: "dict | None" = None) -> list[dict]:
    """`chart_metric_identity_mismatch` (الدرس ٢٧٠ — تحذيريّ، خلف راية
    الرسوم بالبناء): رسمٌ يُعلن مقياسَه (`metric`) يُفحَص بالهوية لا بالوجود.

    ما يُثبِته (مُعلَنٌ حدُّه، مراجعة §58):
    ١) **الوحدة** — القيمةُ داخل مدى المقياس (HHI 100–10000) أيّاً كان مصدرُها:
       حصةُ مورّدٍ 84.05 مرسومةً HHI تُلتقَط حتى لو قرأها القارئ النثريّ.
    ٢) **السجلّ** — حين يحمل سجلُّ المحرّك قيمةً للمقياس، يجب أن تطابقها قيمةُ
       الرسم وسنتُه. هذا يلتقط رسماً بُني من قارئٍ آخر غير السجلّ؛ ولا يدّعي
       إثباتَ صحّة الرقم في أصله (ذلك شأنُ فحوص المحرّك).
    `_check_chart_backing` يُثبت فقط أن الرقم موجودٌ في مكانٍ ما من الأدلة.
    رسمٌ بلا `metric` خارج نطاق هذا الفحص."""
    charts = (dr or {}).get("charts")
    if not isinstance(charts, list) or not charts:
        return []
    hits: list[str] = []
    for ch in charts:
        if not isinstance(ch, dict) or not ch.get("metric"):
            continue
        cid = str(ch.get("id") or "?")
        metric = str(ch["metric"])
        v = ch.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            hits.append(f"{cid}: قيمةٌ غير رقمية لمقياس {metric}")
            continue
        lo_hi = _CHART_METRIC_RANGE.get(metric)
        if lo_hi and not (lo_hi[0] <= float(v) <= lo_hi[1]):
            hits.append(f"{cid}: {v:g} خارج مقياس {metric} "
                        f"({lo_hi[0]:g}–{lo_hi[1]:g})")
            continue
        ref = _chart_metric_reference(dr, metric, ledger)
        if ref is None:
            continue
        try:
            rv = float(ref["value"])
        except (TypeError, ValueError):
            continue
        if abs(float(v) - rv) > 1e-6:
            hits.append(f"{cid}: {v:g} ≠ {metric} في السجلّ {rv:g}")
            continue
        cy, ry = str(ch.get("year") or ""), ref.get("year")
        if cy and ry and cy != str(ry):
            hits.append(f"{cid}: سنة {cy} ≠ سنة {metric} في السجلّ {ry}")
    if not hits:
        return []
    return [{"check": "chart_metric_identity_mismatch", "repairable": True,
             "note": ("رسمٌ لا تطابق قيمتُه أو سنتُه حقيقةَ المقياس الذي "
                      "يُعلنه: " + "؛ ".join(hits[:5])
                      + " — الرسمُ يقرأ القيمةَ والسنةَ والمصدرَ من حقيقةٍ "
                        "واحدة، لا من رقمٍ موجودٍ في مكانٍ آخر")}]


# فحوصٌ **تقرأ تسميةَ الثقة في النثر** وتصير — مع خصوصية أرقام القياس —
# خارجَ مسار التوقّع: النثرُ لا يستلم التسميةَ فلا يكتبها. **لا يُحذَف منها
# شيء** (اثنان في `FAIL_TRIGGER_CHECKS` المجمَّدة تقرؤها عشراتُ الاختبارات
# عقداً). القرارُ المُسجَّل (الدرس ٩٨ — حارسٌ لا يُطلِق عيب): كلُّها تُعاد
# قراءتها **حارسَ «صحيحٌ إن ظهر»** — شبكةُ التقاطِ تسريبٍ يكتبه النموذجُ من
# عنده أو تقريرٍ مخزَّنٍ يُعاد عرضُه، وتبقى قادرةً على الإطلاق على مسارات
# `/analyze` والأكاديميّ والمشغّل التي تحتفظ بالتسمية. ومع
# `client_metric_exposure` يكتمل الزوج: صحّةٌ-إن-ظهر + غيابٌ-مطلوب.
# سجلٌّ تعريفيّ يقرؤه الاختبار (tests/test_client_metric_privacy.py): كلُّ
# اسمٍ يجب أن يُصدِره فحصٌ قائم، ويجب أن يُطلِق فعلاً على نصٍّ مُسرَّب والرايةُ
# مفعَّلة.
PRESENCE_CONDITIONAL_CHECKS: dict = {
    "confidence_band_mismatch":
        "حاجبٌ مجمَّد: تسميةٌ لا تطابق رقمها — يُطلِق فقط إن ظهر الزوج",
    "confidence_value_conflict":
        "حاجبٌ مجمَّد: نسبتا ثقةٍ مختلفتان — يُطلِق فقط إن ظهرت نسبتان",
    "narrative_confidence_mismatch":
        "تحذيري: نسبةُ النثر تخالف نسبةَ الحكم — يُطلِق فقط إن ظهرت نسبة",
    "high_confidence_with_missing_pillar":
        "حاجبٌ مُفعَّلٌ براية: «ثقة عالية» مع جانبٍ مجهول — يقرأ العرضَ "
        "والنثرَ فيبقى قادراً على الإطلاق على تسريبٍ في أيّهما",
    "chart_without_backing_value":
        "تحذيري: قيمةٌ مرسومة بلا حقيقةٍ خلفها — يُطلِق فقط إن وُجدت رسوم "
        "(راية SILK_REPORT_CHARTS)",
    "client_view_vocabulary":
        "تحذيري: قاعدةُ «بثقة %» وحدَها تصير مشروطةً بالظهور؛ بقيّةُ مفرداته "
        "تُطلِق كما كانت",
}


# ── الموجة الرابعة (الدرس ٢٥٨): مبلغٌ بدقّةٍ عشرية زائفة ──────────────────
# نمطُ `hhi_false_precision` حرفياً على المبالغ: المُصلِحُ
# `silk_render._fix_amount_false_precision` يقرّب قبل التخزين/العرض، وهذا
# الفحصُ يلتقط ما فات الإصلاحَ. تحذيريٌّ (لا حجبَ جديداً) وخلف راية الواردات
# — نفسِ راية المُصلِح — فمطفأةً البوّابةُ حرفياً كما كانت.
_AMOUNT_DECIMAL_RE = re.compile(
    r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d{5,})\.\d{3,}(?!\d)")


def _check_amount_false_precision(text: str) -> list[dict]:
    """`amount_false_precision` — مبلغٌ كبيرٌ (فواصلُ آلافٍ أو ≥٥ خانات) بثلاث
    منازلَ عشريةٍ فأكثر: دقّةٌ لم تُحسَب فعلاً بهذا التفصيل (رقمُ استيرادٍ
    بالدولار لا يحمل أجزاءَ السنت)."""
    import silk_render as R
    if not text or not R.imports_spotlight():
        return []
    # الملاحقُ خارج النطاق — الدقّةُ الكاملة هناك مشروعة (نفسُ حدّ المُصلِح).
    m = _AMOUNT_DECIMAL_RE.search(_split_off_appendix(text))
    if not m:
        return []
    return [{"check": "amount_false_precision", "repairable": True,
             "note": (f"مبلغٌ بدقّةٍ عشرية زائفة «{m.group(0)}» — يُعرَض "
                      "بمنزلتين كحدٍّ أقصى (silk_render._fix_amount_false_"
                      "precision)؛ الرقمُ المخزَّن لا يُمَسّ")}]


def _check_uncomputed_repetition(text: str) -> list[dict]:
    """`uncomputed_repetition` (هدف الدراسة الاحترافية البند ٢ — تحذيري على
    معيار الدرس 135): أكثر من إعلانَي غيابٍ داخل قسم «أرقام القرار» —
    الغياب المتكرر بلا تفسير هو عيب دراسة #14 المؤسِّس (خمس «غير محسوب»)؛
    البديل المفروض سطرُ الفتح الواحد + المعادلات مجمّعة.

    **المنطقة العمياء المعلنة (الدرس 172):** يعدّ المفردتين القانونيتين
    (غير محسوب/غير متاح + مرآتاهما الإنجليزيتان) داخل القسم المعنون فقط —
    إعلانُ غيابٍ مُعاد صياغته أو الواقع خارج القسم لا يُعدّ. **جواب سؤال
    التأليف (الدرس 176):** معيار الكتابة يوجب طباعة المتعذر بمعادلته
    وناقصه — خمسة أرقام متعذرة تعني خمسة «الناقص:» مشروعة؛ لذلك يَعدّ هذا
    الفحص مفردتي الغياب لا كلمة «الناقص»، وموجّه الكاتب يفرض سطر الفتح
    الواحد في نفس الموجة (الدرس 156)."""
    if not (text or "").strip():
        return []
    from silk_style_contract import (DECISION_NUMBERS_HEADING,
                                     DECISION_NUMBERS_HEADING_EN)
    ar = _norm_ar(DECISION_NUMBERS_HEADING)
    en = DECISION_NUMBERS_HEADING_EN.lower()
    lines = text.split("\n")
    start = None
    for i, ln in enumerate(lines):
        p = _norm_ar(ln).strip()
        if p and (p.startswith(("#", "**")) or p in (ar, en)) \
                and (ar in p or en in p):
            start = i + 1
            break
    if start is None:
        return []
    section: list[str] = []
    for ln in lines[start:]:
        if ln.strip().startswith("#"):
            break
        section.append(ln)
    body = _norm_ar("\n".join(section))
    count = sum(body.count(_norm_ar(a))
                for a in ("غير محسوب", "غير متاح")) \
        + sum("\n".join(section).lower().count(a)
              for a in ("not computed", "unavailable"))
    if count > 2:
        return [{"check": "uncomputed_repetition", "repairable": True,
                 "note": (f"قسم «أرقام القرار» يعلن الغياب {count} مرات — "
                          "المطلوب سطر الفتح الواحد (ما الذي يفتحه رقم "
                          "واحد) ثم المعادلات مجمّعة، لا تكرار «غير محسوب» "
                          "لكل رقم (عيب دراسة #14)")}]
    return []


def _check_estimate_fields_complete(view: dict) -> list[dict]:
    """`estimate_fields_complete` (هدف الدراسة الاحترافية البند ٧ — تحذيري):
    تقديرٌ في «أرقام القرار» (`tier="estimated"`) ظهر بلا حقوله الأربعة
    (طريقة الاشتقاق/المدى/سبيل التأكيد/مدته)، أو مدى أوسع من ±50% ومعه
    قيمة مطبوعة — عقد البند ٧: التقدير يُعلن مداه وسبيل تأكيده أو لا
    يُطبع رقماً.

    **المنطقة العمياء المعلنة (الدرس 172):** يلتقط الوسم `tier="estimated"`
    فقط — رقمٌ تقديريّ دخل العرض من مسار آخر بلا هذا الوسم لا يُفحص هنا
    (يغطيه عقد عدم الاختلاق العام)؛ وفجوات `tier="gap"` خارج نطاقه عمداً
    (حقولها الثلاثة يفرضها `build_decision_numbers` بنيوياً). **جواب سؤال
    التأليف (الدرس 176):** الموجّه لا يُملي تقديراً بلا حقول — الأرقام
    تُحسب مسبقاً في `silk_economics.build_decision_numbers` (نمط Z-01)
    والكاتب ينقلها؛ الفحص حارسُ انحدارٍ على مُنتِج البنية لا على الكاتب."""
    dr = (view.get("deep_research") if isinstance(view, dict) else None) or {}
    eco = dr.get("economics") or {}
    bad: list[str] = []
    for ent in (eco.get("decision_numbers") or []):
        if not isinstance(ent, dict) or ent.get("tier") != "estimated":
            continue
        name = str(ent.get("name") or "؟")
        rng = ent.get("range") or {}
        missing = [lbl for lbl, ok in (
            ("طريقة الاشتقاق", bool(str(ent.get("method") or "").strip())),
            ("المدى", rng.get("low") is not None
             and rng.get("high") is not None),
            ("سبيل التأكيد", bool(str(ent.get("confirm") or "").strip())),
            ("مدة التأكيد", bool(str(ent.get("confirm_time") or "").strip())),
        ) if not ok]
        if missing:
            bad.append(f"{name}: بلا {'/'.join(missing)}")
        if ent.get("too_wide") and ent.get("value") is not None:
            bad.append(f"{name}: مدى أوسع من ±50% ومعه قيمة مطبوعة")
    if bad:
        return [{"check": "estimate_fields_complete", "repairable": True,
                 "note": ("تقدير بلا عقده الكامل (حقوله الأربعة / حجب "
                          "الواسع): " + "؛ ".join(bad))}]
    return []


def _check_min_pillars_scored(view: dict) -> list[dict]:
    """`min_pillars_scored` (أمر إصلاح المحرّك، البند 2 وجدول فحوص البوابة):
    «درجة موزونة 84%» بعمودٍ واحد (تقرير #11) متوسّطٌ على أوزانٍ فارغة —
    القاعدة البنيوية تعيش في `silk_decision.decide`؛ هذا حارسُ انحدارٍ
    حتميّ على القالب النهائي لأي مسارٍ يمرّر درجةً من غيرها."""
    row = ((view.get("markets") or [None])[0]
           if isinstance(view, dict) else None) or {}
    # `entry_decision` هو ما يبنيه العرض فعلاً (درس 186 — انظر التعليق في
    # `_check_pillar_narrative_sync`)؛ «decision» احتياط للصفوف الخام.
    dec = row.get("entry_decision") or row.get("decision") or {}
    if not isinstance(dec, dict) or dec.get("error"):
        return []
    if dec.get("score") is None:
        return []
    pillars = dec.get("pillars") or {}
    computed = sum(1 for p in pillars.values()
                   if isinstance(p, dict) and p.get("value") is not None)
    try:
        from silk_decision import _min_scored_pillars, _N_PILLARS
        floor, total = _min_scored_pillars(), _N_PILLARS
    except Exception:  # noqa: BLE001 — الحارس لا يسقط بغياب المحرّك
        floor, total = 3, 5
    # درجةٌ بلا قاموس أعمدةٍ أصلاً (مسارٌ أجنبيّ يمرّر رقماً) أسوأ الحالات
    # لا أسلمها — computed=0 يُفشِلها؛ لا شرطَ `pillars` (مراجعة §58).
    if computed < floor:
        return [{"check": "min_pillars_scored", "repairable": False,
                 "note": (f"درجة موزونة معروضة و{computed} فقط من {total} "
                          f"أعمدة محسوبة (الحد الأدنى {floor}) — متوسّطٌ "
                          "على أوزانٍ فارغة لا يُسلَّم")}]
    return []


def _competition_unit_finding(field: str, v, lo: float, hi: float) -> dict:
    return {
        "check": "competition_unit_valid", "repairable": False,
        "note": (f"قيمة حقل المنافسة {field}={float(v):g} خارج مدى وحدته "
                 f"المعلن [{lo:g}–{hi:g}] — كمّيةٌ بوحدةٍ أخرى تسرّبت للحقل "
                 "(حادثة انقلاب الحكم 26%→84%) ولا تُستهلَك")}


def _check_competition_unit_valid(view: dict) -> list[dict]:
    """`competition_unit_valid` (حاجبُ تسليم، `_REGRESSION_GUARD_FIRED`): قيمتا
    حقلَي المنافسة الخام ضمن مدى وحدتها — HHI في [0، 10000] والحصة في [0، 100].

    **درس 186 (إحياء حارس ميّت).** كان يقرأ `markets[i].research.pillar_inputs`
    — مفتاحٌ لا يبنيه `build_view` على مسار /research (يُملأ على /analyze فقط،
    silk_engine._enrich_research) — والبوابة لا تعمل إلا على /research، فالحارسُ
    الحاجب المكتوب لحادثة 26%→84% **على مسار /research نفسه** لم يُطلق قطّ عليه.
    القيمُ الخام الحقيقية على /research في اكتشافات بعثة المنافسين قبل أن يقصّها
    `silk_deep_pillars._structured_competition` — فهنا يرى الحارسُ ما قد يحمل
    خطأ الوحدة. المسار القديم (`pillar_inputs`) يبقى احتياطاً معلناً لأي عرض
    /analyze يمرّر الحقل."""
    findings: list[dict] = []
    dr = (view.get("deep_research") or {}) if isinstance(view, dict) else {}
    # المسار الحيّ (/research): dr.missions.competitors.findings[].value الخام.
    comp = (((dr.get("missions") or {}).get("competitors") or {})
            .get("findings") or [])
    for f in comp:
        v = (f or {}).get("value") if isinstance(f, dict) else None
        if not isinstance(v, dict):
            continue
        hhi = v.get("hhi")
        if isinstance(hhi, (int, float)) and not isinstance(hhi, bool) \
                and not (0.0 <= float(hhi) <= 10_000.0):
            findings.append(_competition_unit_finding("hhi", hhi, 0.0, 10_000.0))
        for sup in (v.get("top_suppliers") or []):
            sh = sup.get("share") if isinstance(sup, dict) else None
            if isinstance(sh, (int, float)) and not isinstance(sh, bool) \
                    and not (0.0 <= float(sh) <= 100.0):
                findings.append(_competition_unit_finding(
                    "top_supplier_share_pct", sh, 0.0, 100.0))
    # الاحتياط (/analyze): pillar_inputs إن مرّره العرض.
    rows = (view.get("markets") or []) if isinstance(view, dict) else []
    for row in rows:
        ci = ((((row or {}).get("research") or {}).get("pillar_inputs")
               or {}).get("competition_intensity") or {})
        for field, lo, hi in (("hhi", 0.0, 10_000.0),
                              ("top_supplier_share_pct", 0.0, 100.0)):
            v = ci.get(field)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            if not (lo <= float(v) <= hi):
                findings.append(_competition_unit_finding(field, v, lo, hi))
    return findings


def consecutive_clean_runs(check: str, n: int = 3, *,
                           _list=None, _get=None) -> dict:
    """عدّادُ معيار التصعيد الرقمي (الدرس 135) — كم دراسةً حيةً مكتملةً
    **متتاليةً** (من الأحدث) مرّت بلا أي إصابةٍ للفحص المسمّى، وهل بلغ
    العدُّ هدفَ التصعيد n.

    كان معيارُ التصعيد وعداً موثقاً بلا آليةِ قياس (موجة سدّ الفجوات
    الثانية): نتائج البوابة تُخزَّن داخل json_blob ولا شيء يعدّها عبر
    التحليلات. الدلالات المحافظة:
      • دراسةٌ بلا مفتاح quality_gate أصلاً (البوابة تخطّاها استثناءٌ
        مبتلَع في api._attach_quality_gate) **مجهولةٌ لا نظيفة** — تقطع
        العدّ؛ انقطاعُ بنيةٍ لا يصنع تصعيداً كاذباً.
      • الدراسات الهرمتية/البرهانية (test_run) تُتخطّى ولا تُحتسب.
    نمطُ الحقن (`_list`/`_get`) من silk_consistency.check_against_history."""
    if _list is None or _get is None:
        import silk_storage
        _list = _list or silk_storage.list_analyses
        _get = _get or silk_storage.get_analysis
    streak = 0
    for row in _list():
        if str((row or {}).get("status") or "") != "completed":
            continue
        try:
            full = _get(row["id"]) or {}
        except Exception:  # noqa: BLE001 — صفٌّ تالف لا يوقف العدّ كله
            continue
        view = full.get("view") if isinstance(full.get("view"), dict) else full
        if (view or {}).get("test_run"):
            continue
        dr = (view or {}).get("deep_research") or {}
        if "quality_gate" not in dr:
            break
        if any(f.get("check") == check
               for f in ((dr["quality_gate"] or {}).get("findings") or [])):
            break
        streak += 1
        if streak >= n:
            break
    return {"check": check, "target": n, "streak": streak,
            "ready": streak >= n}


def _ledger_findings(view: dict) -> list[dict]:
    """ملاحظاتُ سجلّ الحقائق على النصّ المُصيَّر — قائمةٌ فارغة بلا سجلّ.

    تُستدعى على المسارين (بـ`deep_research` وبدونه): تقريرُ /analyze كان
    يمرّ بلا فحصِ اتساقٍ إطلاقاً، وهو الذي تقرؤه لوحةُ المصنع.
    """
    if not isinstance(view, dict) or not view.get("ledger"):
        return []
    try:
        import silk_fact_ledger as _FL
        import silk_reports
        text = silk_reports.render_markdown(view)
        return _FL.check(view, text)
    except Exception as exc:  # noqa: BLE001 — الفحصُ إضافةٌ لا شرطُ حكم
        log.warning("ledger check skipped: %s", exc)
        return []


def run_quality_gate(view: dict) -> dict:
    """شغّل بوابة الجودة على `view["deep_research"]` — يعيد
    {"verdict": PASS|WARN|FAIL, "findings": [...], "methodology_notes": [...]}.

    `findings`: كل بنود الفحص (قابل للإصلاح أو لا). `methodology_notes`:
    نصوص عربية جاهزة للعرض داخل قسم "منهجية البحث ونطاقه" — البنود غير
    القابلة للإصلاح فقط (القابلة للإصلاح مُصلَحة فعلاً في طبقة العرض،
    عرضها كملاحظة منهجية يكرر معلومة صحيحة الآن بلا داعٍ)."""
    dr = view.get("deep_research") if isinstance(view, dict) else None
    if not dr:
        # الدرس ٢٦٢: تقاريرُ /analyze كانت تمرّ **بلا أيّ فحصِ اتساق** (تعود
        # PASS فوراً) — وهي التي يقرؤها المصنع. فحصُ السجلّ يعمل عليها الآن
        # على نصّها المُصيَّر، **والحكمُ يُحسَب من ملاحظاته** بنفس قاعدة
        # المسار العميق: تثبيتُ PASS هنا كان يجعل الحاجبَ عاجزاً عن الحجب
        # على المسار الذي أُضيف من أجله (مراجعة §58).
        _lf = _ledger_findings(view)
        _severe = [f for f in _lf if not f["repairable"]]
        return {"verdict": (FAIL if any(
            f["check"] in effective_fail_triggers() for f in _severe)
            else (WARN if _lf else PASS)),
                "findings": _lf,
                "methodology_notes": [f["note"] for f in _severe]}

    text = ((dr.get("report") or {}).get("text") or "")
    summaries = " ".join(str((m or {}).get("summary") or "")
                         for m in (dr.get("missions") or {}).values())
    combined_text = text + "\n" + summaries

    # الموجة B (البند G-06): اللغةُ تُقرأ هنا لأنّ فحوصاً حاجزةً صارت تتفرّع
    # بها (نصٌّ نائب، إحالةٌ معلَّقة، شظيةٌ يتيمة) — كانت تُقرأ بعدها فتنكسر.
    _lang = _view_lang(view)
    findings: list[dict] = []
    # البند 2 (أمر إصلاح المحرّك): حارسُ انحدارٍ خلف القاعدة البنيوية في
    # `silk_decision` — درجةٌ معروضة بأقل من الحد الأدنى من الأعمدة تُفشِل.
    findings += _check_min_pillars_scored(view)
    # البند 1 (جدول البوابة): قيمة منافسة خارج مدى وحدتها لا تُسلَّم.
    findings += _check_competition_unit_valid(view)
    # البند 3: تنافر اللوحة والسرد — فشل بناء (أمر إصلاح المحرّك).
    findings += _check_pillar_narrative_sync(view)
    # البند 4: توصيةٌ بمنتجٍ خارج بند بيانات التجارة — تسليمٌ يتوقف.
    findings += _check_hs_recommendation_match(view)
    # تصحيح المُشرِف (#13): سمة منتج خارج الجدول لا تمرّ صامتة — تُعلَن.
    if _lang == "ar":
        findings += _check_unclassified_product_attribute(view)
    # البند 5: رقم مشتق بلا مدخلات مرصودة — لا يُسلَّم.
    findings += _check_derived_number_has_inputs(view)
    # البند 6: تناقض تسعيري محسوب بلا تحذير إلزامي — لا يُسلَّم.
    findings += _check_pricing_contradiction_flagged(view)
    # الصنف ٩: رقمٌ لبندٍ يُعلنه المحرك مجهولاً (حاجبٌ خلف رايته)، وسقفُ
    # مخاطرةٍ مفردٍ فوق أساسٍ استُبعد منه مكوّن (تحذيريّ).
    findings += _check_reference_to_nonexistent_figure(view)
    findings += _check_max_loss_without_components(view)
    # الصنف ١٢: فجوةٌ مُعلَنةٌ لمعطىً تحمله بعثتُه فعلاً — تحذيريّ.
    findings += _check_observed_value_declared_unavailable(view)
    # الصنف ١٣: خانةُ قيمةٍ خارج المنسِّق الواحد — تحذيريّ.
    findings += _check_decision_number_format_drift(view)
    # الصنف ١٠: افتراضاتُ بنية السوق — ستّةُ حرّاسَ تحذيريةٍ تقرأ النصَّ أوّلاً.
    findings += _check_zero_fx_volatility(view)
    findings += _check_target_region_missing(view, dr, _lang)
    findings += _check_broad_hs_scope_undisclosed(view)
    findings += _check_border_price_out_of_range(view)
    findings += _check_lead_outside_activity_allowlist(view)
    findings += _check_regime_not_belonging_to_country(view)
    # البند 7: ترقية حكم مع تدهور كل مؤشرات الدليل — لا تُسلَّم.
    findings += _check_verdict_evidence_direction(view)
    # البند 10: تسمية «عدم دخول» فوق متنٍ يوصي بباب دخول مسمّى — لا تُسلَّم.
    findings += _check_verdict_label_matches_content(view)
    # P2 (البنود 11–23): فحوص نصية حتمية — المُفشِلة حرّاسُ انحدار لطبقة
    # العرض (تطوي/تصحح فعلاً)، والتحذيرية جودة نثر حتى معايرة Part B.
    findings += _check_repeated_span(text)
    findings += _check_adjacent_short_stutter(text)
    from silk_price_units import report_price_issues
    findings += report_price_issues(text)
    findings += _check_cross_universe_ratio(text)
    findings += _check_table_row_stutter(text)
    findings += _check_empty_citation(text)
    findings += _check_dead_table(text)
    findings += _check_system_language_leak(text)
    # الصنف ١ (موجة عيوب التقرير): لغةُ نظامٍ داخلية تصل صاحبَ القرار —
    # تحذيريّ، وبلاغُه يحمل القسمَ والنصَّ. يقرأ قوائمه من
    # `silk_style_contract` (المصدرُ الذي يقرؤه الموجّهُ والمراجعُ أيضاً).
    findings += _check_reader_language_leak(text, _lang)
    # الصوتُ البشريّ: نثرٌ مبنيٌّ على صيغٍ جاهزة — تحذيريّ بلا راية.
    findings += _check_robotic_stock_phrase(text)
    # الصنف ٢ (موجة عيوب التقرير): جملةٌ كسرتها خانةٌ فارغة، أو إحالةٌ إلى ما
    # أُعلِن غائباً، أو صدى كيانٍ في وصفِه — تحذيريّ. مِعيارُ «سليم» هو
    # `silk_i18n.repair_interpolation` نفسُها (قاعدةُ الإصلاح = قاعدةُ الفحص).
    findings += _check_template_interpolation(text, _lang)
    # الصنف ٣ (موجة عيوب التقرير): عرضُ الأرقام والوحدات والتواريخ — أربعُ
    # قواعدَ تحذيرية، حرّاسُ انحدارٍ للمُنسِّق الواحد وحرّاسٌ أصليّون لنثرِ
    # الكاتب الذي لا يمرّ عليه.
    # الصنف ٤ (موجة عيوب التقرير): تسميةُ الجهة الواحدة، والمصطلحُ بلا
    # تعريفه — تحذيريّتان. تسمياتُ النشاط الإنجليزية يغطّيها
    # `language_consistency` الحاجز أصلاً، فلا قاعدةَ ثانيةً لها.
    # الصنف ٥ (موجة عيوب التقرير): إعادةُ صياغةٍ عبر الأقسام، وتكرارُ
    # الرابط داخل الفقرة — قناتان لا يبلغهما `_check_repeated_span`
    # (نطاقُه الفقرة وتكرارُه حرفيّ) ولا عدّادُ `_check_style` المستنديّ.
    # الصنف ٦ (موجة عيوب التقرير): قراءتان لمؤشرٍ واحد بلا تسميةِ الفرق —
    # حاجبٌ خلف رايةِ `SILK_FIGURE_STORE` وتحذيريٌّ بدونها؛ ونسبةٌ واحدة
    # لكيانين تحذيرٌ دائم.
    findings += _check_metric_value_divergence(view, dr)
    # الصنف ٧: عددٌ مذكورٌ يخالف القائمةَ الواحدة — حاجبٌ خلف رايته.
    findings += _check_open_conditions_count_mismatch(view, dr)
    # الصنف ٨: «ثقة عالية» مع جانبٍ أساسيٍّ مجهول — حاجبٌ خلف رايته.
    findings += _check_high_confidence_with_missing_pillar(view, dr)
    findings += _check_shared_value_across_entities(dr)
    findings += _check_cross_section_near_duplicate(text)
    findings += _check_connector_repeated_in_paragraph(text, _lang)
    findings += _check_authority_naming_drift(view, dr, _lang)
    findings += _check_defined_term_without_definition(view, dr)
    findings += _check_score_format_drift(text)
    findings += _check_amount_without_currency(text)
    findings += _check_stale_data_without_year(dr, text)
    findings += _check_observation_date_equals_run_date(view)
    findings += _check_absence_vocabulary(text)
    # D4 (دراسة #12): مفردات الغياب على **أسطح العرض** أيضاً — جدول الأعمدة
    # («لم يُرصَد بعد») وشروط القرار وحدود التقرير قوائم view لا يمر عليها
    # فحص النص؛ تُجمَع وتُفحص بنفس القاعدة التحذيرية.
    _basis = ((view.get("decision") or {}).get("basis")
              if isinstance(view, dict) else None) or {}
    _surface = [str((r or {}).get("note") or "")
                for r in (_basis.get("pillars") or [])]
    _surface += [str(x) for x in (_basis.get("conditions") or [])]
    _surface += [str(x) for x in (dr.get("limits") or [])]
    findings += [dict(f, note=f["note"] + " — على سطح العرض (لوحة/شروط/حدود)")
                 for f in _check_absence_vocabulary("\n".join(_surface))]
    findings += _check_decimal_precision(text)
    findings += _check_sentence_length(text)
    findings += _check_decision_numbers_present(text)
    # البند ٢ (هدف الدراسة الاحترافية): تكرار إعلان الغياب داخل أرقام القرار
    # — تحذيري (معيار التصعيد الرقمي نفسه، الدرس 135).
    findings += _check_uncomputed_repetition(text)
    # البند ٣: مصطلح قياس داخلي على أسطح عرض العميل — تحذيري (درس 146).
    findings += _check_client_view_vocabulary(view)
    # الموجة الرابعة: أرقامُ القياس على سطح العميل رغم سياسة الإخفاء، ومبلغٌ
    # بدقّةٍ زائفة — تحذيريّان خلف رايتيهما.
    findings += _check_client_metric_exposure(view, dr)
    findings += _check_amount_false_precision(text)
    # الموجة الخامسة: رسمٌ بقيمةٍ بلا حقيقة — تحذيريّ خلف راية الرسوم.
    findings += _check_chart_backing(dr)
    # الدرس ٢٧٠: هويةُ المقياس المرسوم — لا وجودُ الرقم وحده.
    findings += _check_chart_metric_identity(dr, view.get("ledger"))
    # البند ٧: تقدير بلا حقوله الأربعة أو واسعٌ معه قيمة — تحذيري.
    findings += _check_estimate_fields_complete(view)
    # البند ٤ (هدف الدراسة الاحترافية): الملخص التنفيذي يفتتح بالتوصية
    # (حاجز حتمي) وقيوده الأسلوبية تحذيرية (درس 135).
    findings += _check_exec_summary_recommendation_first(text)
    findings += _check_exec_summary_constraints(text)
    # البند 18 (F5): تكرار جملة التحذير السياقي بدل الصندوق الواحد + النجوم.
    findings += _check_caveat_repetition(text)
    # هدف الدراسة الاحترافية (البند ١): فجوةُ تحويلٍ لثابتٍ مسجّل لا تُسلَّم —
    # على نص التقرير وملخّصات البعثات معاً (النص #14 المؤسِّس جاء من النثر).
    findings += _check_unit_conversion_refusal(
        combined_text, (view.get("product") if isinstance(view, dict) else "")
        or dr.get("product") or "")
    findings += _check_markdown_and_raw_json(combined_text)
    findings += _check_raw_confidence(combined_text)
    # ملخّصات البعثات عبارات قصيرة عمداً بلا علامة ترقيم ختامية بالاصطلاح
    # (راجع أي AgentReport.summary في المشروع) — فحص التقطيع يقتصر على نص
    # التقرير السردي الكامل (كاتب التقرير) حيث التقطيع الحقيقي مرصود فعلاً.
    findings += _check_mid_word_truncation(text)
    findings += _check_trailing_ellipsis(text)
    # D3 (دراسة #12): «حدود هذا التقرير» قائمةُ view منفصلة عن نص التقرير —
    # سطرُها المبتور («…بيانات اقتصادية فعلية للسنوات السابقة…») كان يفلت
    # من الفحص أعلاه. كلُّ حدٍّ كتلةٌ مستقلة كي يُفحَص ذيلُه بذاته.
    findings += _check_trailing_ellipsis(
        "\n\n".join(str(x) for x in (dr.get("limits") or [])))
    findings += _check_orphan_short_token(text, _lang)
    findings += _check_dangling_cross_reference(text, _lang)
    findings += _check_stray_percent_punctuation(text)
    findings += _check_entity_near_duplicates(text)
    findings += _check_confidence_band_label(text)
    findings += _check_lpi_edition_year(text)
    findings += _check_recommendation_tier_label_consistency(dr, _lang)
    findings += _check_near_duplicate_figures(text)
    findings += _check_hhi_false_precision(text)
    findings += _check_supplier_rank_contiguity(text)
    findings += _check_client_section_would_be_placeholder(dr)
    findings += _check_client_scaffold_leak(combined_text)
    findings += _check_placeholder_leak(combined_text, _lang)
    findings += _check_gaps_closing_contradiction(dr)
    findings += _check_internal_plumbing_leak(text)
    # ── الموجة ٠: اللغة — قناتان منفصلتان تماماً ──────────────────────────
    # (١) **الاتساق** حاجزٌ ⇒ يدخل `findings` ويقع في `FAIL_TRIGGER_CHECKS`.
    # (٢) **الجودة** تحذيريّةٌ ⇒ قناةٌ خاصّة بها (`language_quality`) لا
    #     `findings`: تركيبةُ `findings` عقدٌ مُختبَرٌ في عشرات الاختبارات،
    #     وحقنُ ملاحظةٍ أسلوبية فيها يخلط حكماً متدرّجاً بحكمٍ ثنائيّ —
    #     وهو بالضبط الخلط الذي طُلِب تفكيكه. الفصلُ بقناتين أقوى من الفصل
    #     بتسميتين داخل قناةٍ واحدة.
    # (٣) فحصٌ عربيُّ الأنماط بلا مرآةٍ إنجليزية **يُعلَن مُتخطّى** في قناته
    #     الخاصّة — لا يُدَّعى أنه مرّ، ولا يُقحَم في تشخيص العميل.
    skipped: list[dict] = []
    if _lang == "ar":
        findings += _check_english_field_and_mission_key_leak(text)
    else:
        skipped.append({
            "check": "english_field_and_mission_key_leak",
            "reason": ("أنماطه مبنيّة على «إنجليزيّةٌ داخل نصٍّ عربيّ» فلا "
                       "معنى لها على تقريرٍ إنجليزيّ — التغطية البديلة: "
                       "حارس مفردات العميل الإنجليزي "
                       "`_CLIENT_FORBIDDEN_PATTERNS_EN`")})
        # **إعلانُ ما يخمُد** (مراجعة ذاتية): فحوصٌ أخرى تُمفصِل على عباراتٍ
        # عربية حرفية، فتصير على نصٍّ إنجليزيّ **صامتةً لا ناجحة**. حكمُ PASS
        # من بوابةٍ نصفُها خامد ادّعاءُ جودةٍ لم تُقَس — يُعلَن، لا يُخفى.
        # (التغطيةُ الفعلية للإنجليزية: بوابةُ اتساق اللغة الحاجزة + حارسُ
        # مفردات العميل الإنجليزي + كلُّ الفحوص **البنيوية** المبنيّة على `dr`
        # وهي تعمل في اللغتين سواءً.)
        skipped += [{"check": c, "reason": r} for c, r in _AR_ONLY_CHECKS]
    findings += _check_language_consistency(text, _lang, view)
    findings += _check_regulatory_blocker(view)
    findings += _check_narrative_matches_the_verdict(view)
    language_quality = _check_language_quality(text, _lang)
    findings += _check_confidentiality_leaks(combined_text)
    findings += _check_style(text)
    findings += _check_bare_partner_codes(dr)
    findings += _check_intersection_insufficiency(dr, _lang)
    findings += _check_section_structure(dr, _lang)
    findings += _check_cagr_consistency(dr)
    findings += _check_currency_label_mismatch(dr)
    findings += _check_evidence_body_numeric_consistency(dr)
    findings += _check_source_coverage(dr)
    findings += _check_agent_health(dr)
    findings += _check_audit_coverage(dr)
    findings += _check_analyst_layer_failure(dr)
    # PR A (بلاغ تحليل ٧) — ثلاث بوابات حاجبة جديدة: تعارض قيمة الثقة (§A1)،
    # تعارض تسمية الحكم (§A2)، وTAM أصغر من تدفّق دولة واحدة (§A3).
    findings += _check_confidence_value_conflict(text)
    findings += _check_verdict_label_conflict(dr)
    findings += _check_tam_below_single_country_flow(dr)
    findings += _check_market_sizing_derivation(dr)
    findings += _check_narrative_money_grounded(dr)
    # P0 (تحليل ٧): سردُ تباين المرآة، وتصعيدُ التقادُم القائد لاستنتاج.
    findings += _check_mirror_divergence_contraction_narrative(dr)
    findings += _check_stale_year_driving_conclusion(dr)
    # بلاغ المالك (تحليل ٧): إشارةُ CAGR تنقلب بتغيير سنة الأساس المرصودة.
    findings += _check_cagr_sign_flips_under_base_year(dr)
    # PR B (بلاغ تحليل ٧): تلوّث عملةٍ خارج السوق (§B3، حاجب)، وبعثةُ اتجاهاتٍ
    # «مكتملة» بلا بياناتها الأساسية (§B5، ملاحظة منهجية لا حاجبة).
    findings += _check_off_market_currency(dr)
    findings += _check_trends_hollow_completion(dr)
    # الموجة ١ (توجيه المنصّة): عقد المصدر + قِدم البيانات — تحذيريان فقط،
    # لا يدخلان FAIL_TRIGGER_CHECKS (قرار مالك 2026-08-19: لا حجب جديداً).
    findings += _check_source_contract_completeness(dr)
    findings += _check_vintage_expired_facts(dr)
    # الموجة 2أ: مقياس HHI الموحّد + إعادة حساب CAGR — تحذيريان فقط.
    findings += _check_hhi_scale(dr)
    findings += _check_cagr_recompute(dr)
    findings += _check_cagr_endpoint_lag(dr)
    # الموجة ٣: المحرك الاقتصادي + قابلية مقارنة الأسعار — تحذيرية فقط.
    findings += _check_economics_present(dr)
    findings += _check_price_comparability(dr, _lang)
    findings += _check_generic_conversion_refusal(dr, _lang)
    # الموجة ٤ (Gate B): قفل اتساق الرمز + اتساق المواصفة — تحذيريان.
    findings += _check_hs_consistency_lock(view, dr)
    findings += _check_spec_evidence_coherence(dr)
    # الموجة ٥: الجدول الزمني للنفاذ — تحذيري.
    findings += _check_access_timeline_presence(
        dr, _lang, regulatory=(view.get("regulatory")
                               if isinstance(view, dict) else None))
    findings += _check_curated_reference_consulted(dr)
    # الموجة ٦: انضباط أفعال طبقات الأدلة — تحذيري (سابقة D-25).
    findings += _check_epistemic_verb_discipline(dr, _lang)
    # سدّ الخياطة: مرساة السعر تطابق الشكل الموصى به — تحذيري، نائم بلا حقل.
    findings += _check_anchor_matches_recommended_form(dr)
    # حرّاس عائلة (تشغيلة الحليب–الأردن 2026-08-19) — كلها تحذيرية:
    # سجلّ فجوات واحد، مقام كل نسبة معلَن، وسنة المصدر لا سنة مفترضة.
    findings += _check_sufficiency_contradiction(view, dr)
    findings += _check_metric_value_conflict(view, dr, _lang)
    findings += _check_lpi_year_mismatch(dr)
    # لغة التاجر — تحذيري (سطح العميل يُصلَح حتمياً في silk_reports).
    findings += _check_plain_language(view, dr)
    # الدرس ٢٦٢: مقابلةُ النصّ المُصيَّر بسجلّ الحقائق الواحد — تحذيريّة في
    # وضع القياس، وحاجبةٌ تحت `SILK_LEDGER_ENFORCE` بعد محاولة الإصلاح.
    findings += _ledger_findings(view)

    non_repairable = [f for f in findings if not f["repairable"]]
    guard_fired = [f for f in findings if f["check"] in _REGRESSION_GUARD_FIRED]
    severe = non_repairable + guard_fired
    if not findings:
        verdict = PASS
    elif any(f["check"] in effective_fail_triggers() for f in non_repairable) \
            or guard_fired:
        verdict = FAIL
    else:
        verdict = WARN

    methodology_notes = [f["note"] for f in severe]
    return {"verdict": verdict, "findings": findings,
            "methodology_notes": methodology_notes,
            # الموجة ٠ — قناتان إضافيّتان **لا تمسّان `findings` ولا الحكم**:
            # `language_quality` ملاحظاتٌ أسلوبية متدرّجة للمشغّل، و
            # `skipped_checks` إعلانُ ما لم يُفحَص ولماذا (لا مرورَ صامت).
            "language_quality": language_quality,
            "skipped_checks": skipped,
            "report_language": _lang,
            # الموجة ٦ (الجزء ٩): سجلات الفشل الموحّدة للبنود الشديدة —
            # مفتاح إضافي؛ الأشكال القائمة (findings/409) كما هي حرفياً.
            "failure_records": [
                failure_record("Gate D", f["check"],
                               "blocking" if verdict == FAIL else "warning",
                               f["note"])
                for f in severe]}


# ══════════ الموجة ٧ — سجلّ تدقيق التوجيه · DIRECTIVE_AUDIT_CHECKS ══════════
# (توجيه المنصّة، الجزء ٨): خريطة كل بند تدقيق ← الفحص المنفّذ وشدته.
# **سجل تعريفي (توثيق-كشيفرة)** يقرؤه المشغّل والاختبار — الفحوص نفسها
# مسجّلة أعلاه في run_quality_gate؛ الشدة الحالية كلها تحذيرية للبنود
# الجديدة (قرار مالك 2026-08-19: لا حجب جديداً — الترقية قرار مالك لاحق).
DIRECTIVE_AUDIT_CHECKS: dict = {
    "1-سجل اشتقاق التصنيف وقفله": ("hs_consistency_lock", "WARN"),
    "2-لا خلاصة كمية من رمز مستبدل": ("spec_evidence_coherence", "WARN"),
    # درس 186 (تصحيح ادعاء تغطية — نمط البند 19): `cagr_recompute` يعيد حساب
    # CAGR من **سلسلةٍ رقمية** في الاكتشاف، وعرضُ /research لا يحمل سلسلةً
    # لكل بعثة (trend=None، والاكتشافات بلا series) — فالفحصُ على شكل بيانات
    # /analyze لا /research (المسار الوحيد للبوابة). سجلٌّ يدّعي تغطيةً غائبة
    # يُسكِت السؤال.
    "3-إعادة حساب المشتقات (CAGR)": (
        "cagr_recompute_mismatch — يحتاج سلسلةً رقمية؛ شكل بيانات /analyze "
        "لا /research (لا سلسلة في عرض العمق)", "غير مغطّى على /research"),
    "3ب-مقياس HHI الموحّد": ("hhi_wrong_scale", "WARN"),
    "4-تطبيع الأسعار قبل المقارنة": ("price_comparability_gaps", "WARN"),
    "5-مرساة السعر بشكل المنتج الموصى به": ("anchor_form_mismatch", "WARN"),
    "4ب-تسمية خاصية التعذر": ("generic_conversion_refusal", "WARN"),
    "6-المحرك الاقتصادي حاضر": ("economics_missing_despite_inputs", "WARN"),
    "9-الجدول الزمني للنفاذ": ("access_timeline_missing", "WARN"),
    "12-اكتمال بطاقة النسب": ("source_contract_incomplete", "WARN"),
    "13-انضباط أفعال الطبقات": ("epistemic_verb_discipline", "WARN"),
    "16-قِدم البيانات بطبقتين": ("vintage_expired_facts_present", "WARN"),
    # حرّاس عائلة تشغيلة الحليب–الأردن (تحذيرية):
    "18ب-سجل فجوات واحد لكل سطوح الحكم": ("sufficiency_contradiction", "WARN"),
    # درس 186: `metric_value_conflict` يقارن `value_usd` مورّدٍ بإجمالي
    # الواردات؛ موردو /research بالحصة (%) لا بقيمةٍ دولارية — فلا يقع
    # التعارض بشكله على /research (بيانات /analyze). صادقٌ أصدق من تزييف.
    "12ب-لا قيمتان لمؤشر واحد": (
        "metric_value_conflict — يحتاج مورّدين بـvalue_usd؛ شكل /analyze لا "
        "/research (موردو العمق بالحصة%)", "غير مغطّى على /research"),
    "16ب-سنة المؤشر من المصدر": ("lpi_year_mismatch", "WARN"),
    "20ب-لغة تاجر لا أكاديمية": ("plain_language_jargon", "WARN"),
    # بنود يغطيها القائم قبل التوجيه (حاجبة أصلاً — لم تُمَسّ):
    "17-تباين المرآة مفكَّك": ("mirror_divergence_contraction_narrative",
                               "قائم"),
    # **الموجة B (البند D-02) — تصحيحُ سجلٍّ كان يكذب.** كان هذا البند
    # مُسجَّلاً «بنيوي» بآليّة `decision_rule (silk_decision)`؛ والتدقيق أثبت
    # أنّ `silk_decision.decide` **لا يعمل لدراسة مصنعٍ في أيٍّ من الوضعين**
    # (`docs/ENGINE_AUDIT.md` D-01)، فلا قاعدةَ قرارٍ تصل تقريرَ المصنع.
    # سجلٌّ يدّعي تغطيةً غيرَ موجودة أسوأُ من سجلٍّ ناقص: يُسكِت السؤال.
    # يعود «بنيوي» حين تُغلَق D-01 في الموجة D.
    "19-قاعدة القرار قبل الحكم": (
        "decision_rule (silk_decision) — /analyze فقط؛ مسارُ دراسة المصنع "
        "بلا محرّك قرارٍ حتميّ (ENGINE_AUDIT D-01، الموجة D)", "غير مغطّى"),
    "20-لا صياغات محظورة": ("style_* (القائمة القائمة)", "قائم"),
}
