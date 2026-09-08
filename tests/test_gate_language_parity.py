"""تكافؤُ بوّابةِ الجودة بين لغتَي التقرير · gate parity across report languages.

> **الحادثة.** الموجة ٠ («لغة المصنع تحكم لغة التقرير»، PR #217) جعلت التقريرَ
> يخرج بالإنجليزية للمصنع الإنجليزيّ، وبقيت مِجَسّاتُ بوّابة الجودة عربيةً
> حرفية. فصار **سبعةُ فحوصٍ** على تقريرٍ إنجليزيّ إمّا صامتاً — واثنان منها
> **حاجزان** (`recommendation_tier_mislabel` و`intersection_insufficiency`) —
> أو **كاذبَ الاشتعال** يلوم تقريراً صحيحاً بملاحظةٍ عربية. وحكمُ `PASS` من
> بوّابةٍ نصفُها خامد ادّعاءُ جودةٍ لم تُقَس.
>
> **The incident.** Wave 0 made the report language follow the factory's, but
> the quality gate's probes stayed Arabic string literals. Seven checks became
> either silent on an English report (two of them blocking) or false-firing on
> a correct one. A PASS from a half-dormant gate is a quality claim that was
> never measured.

كلُّ حالةٍ هنا **إعادةُ إنتاجٍ مباشرة** (`direct reproduction`): نفسُ العيب
مكتوباً في اللغتين، والعقدُ أنّ الفحص يشتعل فيهما معاً — أو يصمت فيهما معاً.
والقفلُ البنيويّ في آخر الملفّ يمنع عودةَ العائلة كلِّها: أيّ فحصٍ جديدٍ
يُمفصِل على عبارةٍ عربيةٍ حرفية دون مرآةٍ إنجليزية يُحمِّر CI ما لم يُعلَن
صراحةً في `_AR_ONLY_CHECKS`.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

import silk_i18n
import silk_quality_gate as G


# ══════════════════════════════════════════════════════════════════════════
# ١) إعادةُ الإنتاج المباشرة — ستُّ حالات، كلٌّ في اللغتين
# ══════════════════════════════════════════════════════════════════════════

def _tier_dr(text: str) -> dict:
    """حكمٌ مشروط + متنٌ يذكر تسمية الدرجة الأعلى (§H-2)."""
    return {"report": {"text": text}, "verdict": {"verdict": "CONDITIONAL-GO"}}


@pytest.mark.parametrize("lang,text", [
    ("ar", "الحكم دخول مشروط. ومع ذلك فإن التوصية بالدخول قائمة لهذا المنتج."),
    ("en", "The verdict is conditional entry. Recommendation: Enter the "
           "market."),
])
def test_s01_tier_mislabel_blocks_in_both_languages(lang, text):
    """S-01 — الحاجزُ يشتعل في اللغتين، والتسميةُ من مصدرِ التسمية نفسِه."""
    out = G._check_recommendation_tier_label_consistency(_tier_dr(text), lang)
    assert out, f"الحاجز لم يشتعل على «{lang}» — تقريرٌ يناقض حكمَه يُشحن"
    assert out[0]["check"] == "recommendation_tier_mislabel"
    assert out[0]["repairable"] is False, "هذا حاجزٌ لا ملاحظةٌ قابلة للإصلاح"
    # التسميةُ المذكورة في الملاحظة هي تسميةُ العرض نفسُها — لا نسخةٌ حرفية.
    assert silk_i18n.t("verdict_go", lang) in out[0]["note"]


@pytest.mark.parametrize("lang,text", [
    ("ar", "الحكم دخول مشروط، ويتحول إلى درجة أعلى إذا تحقق شرطان."),
    ("en", "The verdict is conditional entry; it upgrades once two "
           "conditions are met."),
])
def test_s01_clean_conditional_body_passes_in_both_languages(lang, text):
    """المرآةُ السالبة: متنٌ سليمٌ لا يُلام في أيٍّ من اللغتين."""
    assert G._check_recommendation_tier_label_consistency(
        _tier_dr(text), lang) == []


def _intersection_dr(text: str) -> dict:
    return {"report": {"text": text},
            "analyst": {"by_category": {"price_competitiveness": [1, 2]}}}


@pytest.mark.parametrize("lang,text", [
    ("ar", "التنافسية السعرية: دليل غير كافٍ لهذا التقاطع."),
    ("en", "Price competitiveness: insufficient evidence for this "
           "intersection."),
])
def test_s02_intersection_insufficiency_blocks_in_both_languages(lang, text):
    """S-02 — «دليل غير كافٍ» فوق تقاطعٍ يحمل بنوداً فعلية: حاجزٌ في اللغتين."""
    out = G._check_intersection_insufficiency(_intersection_dr(text), lang)
    assert out, f"الحاجز صامتٌ على «{lang}» — إعلانُ عجزٍ فوق أدلةٍ موجودة"
    assert out[0]["repairable"] is False


@pytest.mark.parametrize("lang,text", [
    ("ar", "التنافسية السعرية: السعر المرصود 6.5 مقابل 7.2 للمنافس."),
    ("en", "Price competitiveness: the observed price is 6.5 against a "
           "competitor at 7.2."),
])
def test_s02_computed_intersection_passes_in_both_languages(lang, text):
    assert G._check_intersection_insufficiency(_intersection_dr(text),
                                               lang) == []


def _anchor_dr(text: str) -> dict:
    return {"economics": {"anchor_price": {"gaps": ["وحدة غير معلومة"],
                                           "per_kg": None}},
            "report": {"text": text}}


@pytest.mark.parametrize("lang,text", [
    ("ar", "السعر المرصود 5 دولار/كجم في السوق المستهدف."),
    ("en", "The observed price is USD 5 per kg in the target market."),
])
def test_s03_price_comparability_declared_in_both_languages(lang, text):
    """S-03 — مقارنةٌ على أساس الكيلو فوق مرساةٍ غير مطبَّعة تُعلَن في اللغتين."""
    out = G._check_price_comparability(_anchor_dr(text), lang)
    assert out and out[0]["check"] == "price_comparability_gaps"


@pytest.mark.parametrize("lang,text", [
    ("ar", "السعر المرصود 5 دولار للعبوة."),
    ("en", "The observed price is USD 5 per pack."),
])
def test_s03_no_per_kg_claim_stays_quiet_in_both_languages(lang, text):
    """لا ادّعاءَ كيلوجرام ⇒ لا تحذير — في اللغتين (لا ضجيجَ بنيويّ)."""
    assert G._check_price_comparability(_anchor_dr(text), lang) == []


@pytest.mark.parametrize("lang,text", [
    ("ar", "يتعذر التحويل إلى السعر لكل كيلوجرام."),
    ("en", "Conversion is not possible to a per-kilogram price."),
])
def test_s04_generic_conversion_refusal_caught_in_both_languages(lang, text):
    """S-04 — الرفضُ العامّ بلا تسمية الخاصية المفقودة ممنوعٌ في اللغتين."""
    out = G._check_generic_conversion_refusal({"report": {"text": text}}, lang)
    assert out and out[0]["check"] == "generic_conversion_refusal"


@pytest.mark.parametrize("lang,text", [
    ("ar", "حجم العبوة غير مرصود، فالسعر/كجم فجوة معلنة."),
    ("en", "Pack size was not observed, so the price per kilogram is a "
           "declared gap."),
])
def test_s04_named_physical_gap_is_allowed_in_both_languages(lang, text):
    """تعذّرٌ **مُسمّى** (حجم العبوة) مسموحٌ — العقدُ يمنع العموم لا الإعلان."""
    assert G._check_generic_conversion_refusal({"report": {"text": text}},
                                               lang) == []


def _timeline_dr(text: str) -> dict:
    return {"missions": {"customs_requirements": {"failed": False}},
            "report": {"text": text},
            "regulatory": {"access_timeline":
                           {"total_days": {"min": 45, "max": 60}}}}


@pytest.mark.parametrize("lang,text", [
    ("ar", "المدة الكلية من قرار الدخول حتى أول شحنة نظامية: 45–60 يوماً."),
    ("en", "Total lead time from the entry decision to the first compliant "
           "shipment: 45-60 days."),
])
def test_s05_stated_timeline_is_not_falsely_blamed(lang, text):
    """S-05 (كاذبُ الاشتعال) — تقريرٌ **يذكر** المدة لا يُلام في أيٍّ من اللغتين.

    الانحدارُ المقفول: الإنجليزيُّ الصحيح كان يُلام، وبملاحظةٍ **عربية** تُحقَن
    في مسارٍ إنجليزيّ."""
    assert G._check_access_timeline_presence(_timeline_dr(text), lang) == []


@pytest.mark.parametrize("lang,text", [
    ("ar", "قسم الاشتراطات يذكر الرسوم والوثائق فقط."),
    ("en", "The requirements section lists fees and documents only."),
])
def test_s05_missing_timeline_is_declared_in_both_languages(lang, text):
    """والاتجاهُ المعاكس يبقى عاملاً: غيابُ المدة يُعلَن في اللغتين."""
    out = G._check_access_timeline_presence(_timeline_dr(text), lang)
    assert out and out[0]["check"] == "access_timeline_missing"


def _exw_dr(text: str) -> dict:
    return {"economics": {"reverse_solve": {"scenarios": [1],
                                            "max_exw": 2.9762}},
            "report": {"text": text}}


@pytest.mark.parametrize("lang,text", [
    ("ar", "بافتراض سيناريو متوسط، أقصى سعر مصنع 2.9762 وحدة."),
    ("en", "Assuming the medium scenario, the maximum ex-works price is "
           "2.9762."),
])
def test_s06_conditional_phrasing_accepted_in_both_languages(lang, text):
    """S-06 (كاذبُ الاشتعال) — صياغةٌ شرطيةٌ سليمة تُقبَل في اللغتين."""
    assert G._check_epistemic_verb_discipline(_exw_dr(text), lang) == []


@pytest.mark.parametrize("lang,text", [
    ("ar", "أقصى سعر مصنع قابل للمنافسة هو 2.9762 وحدة."),
    ("en", "The maximum competitive ex-works price is 2.9762."),
])
def test_s06_bare_parameter_number_is_flagged_in_both_languages(lang, text):
    """والاتجاهُ المعاكس: رقمُ معلمةٍ بلا شرطٍ يُوسَم في اللغتين — الحارسُ
    قادرٌ على الفشل (الدرس ٩٨)."""
    out = G._check_epistemic_verb_discipline(_exw_dr(text), lang)
    assert out and out[0]["check"] == "epistemic_verb_discipline"


# ══════════════════════════════════════════════════════════════════════════
# ٢) عقدُ المعجم — كلُّ مفهومٍ يحمل اللغتين، ولا مجسَّ فارغ
# ══════════════════════════════════════════════════════════════════════════

def test_every_probe_concept_carries_both_languages():
    """مِجَسٌّ بلغةٍ واحدة = فحصٌ صامتٌ على اللغة الأخرى — يُمنَع بنيوياً."""
    for key, row in G._GATE_PROBES.items():
        for lang in silk_i18n.LANGS:
            assert row.get(lang), f"«{key}» ينقصه مِجَسّ «{lang}»"
            assert all(str(p).strip() for p in row[lang]), \
                f"«{key}/{lang}» يحوي مِجَسّاً فارغاً"


def test_probe_lookup_is_case_insensitive_on_english():
    """المتنُ يكتب «Per kg» و«per kg» سواءً — الالتقاطُ لا يفرّق."""
    assert G._hits("Priced at USD 5 Per Kg.", "per_kg_claim", "en")
    assert G._hits("TOTAL LEAD TIME: 45 days", "access_timeline", "en")


def test_unknown_probe_key_raises_rather_than_silently_passing():
    """مفتاحٌ غير مسجَّل يرفع — لا يعود فارغاً فيصير الفحصُ صامتاً."""
    with pytest.raises(KeyError):
        G._probe("no_such_concept", "ar")


def test_category_labels_are_bilingual_and_reach_the_english_limit_line():
    """S-08 — اسمُ التقاطع كان عربياً داخل جملةٍ إنجليزية، وحارسُ تسرّب اللغة
    لا يلتقطه (كلمتان — دون `_MIN_PROSE_WORDS`). المصدرُ الواحد يمنعه."""
    from silk_market_analyst import _CATEGORY_LABELS
    from silk_render import _category_label
    for cat in _CATEGORY_LABELS:
        en = _category_label(cat, "en")
        ar = _category_label(cat, "ar")
        assert en and ar and en != ar, f"«{cat}» بلا تسميتين متمايزتين"
        assert not re.search(r"[؀-ۿ]", en), \
            f"تسميةُ «{cat}» الإنجليزية تحوي حرفاً عربياً: {en!r}"
    line = silk_i18n.t("limit_analyst_thin", "en",
                       label=_category_label("price_competitiveness", "en"))
    assert not re.search(r"[؀-ۿ]", line), f"سطرُ حدٍّ إنجليزيّ مهجَّن: {line!r}"


# ══════════════════════════════════════════════════════════════════════════
# ٣) القفلُ البنيويّ — لا فحصَ عربيَّ المِجَسّ غيرَ مُعلَن (قانون بلا إنفاذ = أمنية)
# ══════════════════════════════════════════════════════════════════════════

_AR_CHAR_RE = re.compile(r"[؀-ۿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
# **مراجعة ذاتية §58.** رموزُ التهريب في التعابير النمطية (`\n`, `\d`, `\s`)
# تحمل حروفاً لاتينية، فكان مِجَسٌّ عربيٌّ خالص مثل `r"واردات[^،\n]{0,60}"`
# يُقرأ «ثنائيَّ اللغة» فيفلت من الحارس. تُنزَع قبل الحكم — لا محتوى فيها.
_RE_ESCAPE_RE = re.compile(r"\\[a-zA-Z]")
_TEXT_NAMES = ("text", "combined_text", "body", "window", "ctx", "blob",
               "prose")


def _module_constants(tree: ast.Module, src: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            seg = ast.get_source_segment(src, node.value) or ""
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    out[tgt.id] = seg
    return out


def _probe_payload(seg: str) -> str:
    """المحتوى النصّي الفعليّ لثابتٍ نمطيّ — probe text inside a constant.

    **صيد الفجوات ٣ (الدرس ١٥٧).** كان المقطعُ المصدريُّ كاملاً يُصنَّف
    لغوياً، فحروفُ الغلاف اللاتينية (`re.compile(`, `re.I`) تجعل كلَّ مِجَسٍّ
    عربيٍّ محضٍ مخزونٍ في ثابتِ وحدةٍ «ثنائيَّ اللغة» — فالكاشفُ يعيد صفرَ
    مخالفين دائماً (حارسٌ أعمى بنيوياً). هنا تُستخرَج **السلاسلُ الحرفية
    فقط** من المقطع (أنماط re.compile، مفاتيح القواميس، عناصر القوائم)."""
    if not seg:
        return ""
    try:
        node = ast.parse(seg.strip(), mode="eval").body
    except SyntaxError:
        return seg
    lits: list[str] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            lits.append(n.value)
    return "\n".join(lits) if lits else seg


def _loop_vars(fn: ast.FunctionDef, consts: dict[str, str]) -> dict[str, str]:
    """متغيّراتُ الحلقات المقيَّدة بثوابت الوحدة — `for rex in _CONF_PCT_RES`
    و`for phrase, iso3 in _PHRASES.items()` كانت تنحلّ إلى "" فتختفي من نظر
    الكاشف كلياً (نفس الدرس ١٥٧)."""
    out: dict[str, str] = {}
    for node in ast.walk(fn):
        if not isinstance(node, (ast.For, ast.comprehension)):
            continue
        it = node.iter
        base = None
        if isinstance(it, ast.Name):
            base = it.id
        elif isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) \
                and isinstance(it.func.value, ast.Name):
            base = it.func.value.id
        if not base or base not in consts:
            continue
        seg = consts[base]
        targets = ([node.target] if isinstance(node.target, ast.Name)
                   else list(getattr(node.target, "elts", [])))
        for t in targets:
            if isinstance(t, ast.Name):
                out[t.id] = seg
    return out


def _text_probes(fn: ast.FunctionDef, consts: dict[str, str]) -> list[str]:
    """السلاسلُ التي تُطابَق فعلاً على نصِّ التقرير داخل هذه الدالة.

    عمداً محافظٌ: يقرأ فقط ما يُقارَن بمتغيّرٍ اسمُه من `_TEXT_NAMES` — فلا
    يُحسب نصُّ الملاحظة (عربيٌّ دائماً بالتصميم) مِجَسّاً."""
    found: list[str] = []
    loop_map = _loop_vars(fn, consts)

    def _resolve(name: str) -> str:
        return _probe_payload(consts.get(name, "") or loop_map.get(name, ""))

    def _lit(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
        elif isinstance(node, ast.Name):
            found.append(_resolve(node.id))

    for node in ast.walk(fn):
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)) and \
                        any(w in ast.unparse(comp) for w in _TEXT_NAMES):
                    _lit(node.left)
        elif isinstance(node, ast.Call):
            fname = getattr(node.func, "attr",
                            getattr(node.func, "id", "")) or ""
            args = " ".join(ast.unparse(a) for a in node.args)
            owner = getattr(node.func, "value", None)
            if fname in ("search", "match", "finditer", "findall",
                         "fullmatch") and \
                    any(w in args for w in _TEXT_NAMES):
                if isinstance(owner, ast.Name):
                    found.append(_resolve(owner.id))
                for a in node.args:
                    _lit(a)
            elif fname in ("find", "count", "index", "startswith",
                           "endswith") and owner is not None and \
                    any(w in ast.unparse(owner) for w in _TEXT_NAMES):
                for a in node.args:
                    _lit(a)
    return [p for p in found if p]


def _arabic_only_probe_checks() -> list[str]:
    """أسماءُ الفحوص التي تُمفصِل على عربيةٍ حرفية بلا وعيٍ باللغة."""
    src = pathlib.Path("silk_quality_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    consts = _module_constants(tree, src)
    offenders = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef)
                and node.name.startswith("_check_")):
            continue
        seg = ast.get_source_segment(src, node) or ""
        # **مراجعة ذاتية §58.** كان الشرطُ `.get("text")` وحدَه، فأعفى كلَّ
        # فحصٍ يقرأ المتنَ عبر المساعد `_report_text(dr)` — ومنها فحصٌ
        # عربيُّ المِجَسّ صامتٌ على الإنجليزية وغيرُ مُعلَن. حارسٌ يُعفي
        # نصفَ ما يحرسه ليس حارساً.
        # موجة سدّ الفجوات الثانية: عائلة P2 كلها تأخذ المتن **معاملاً**
        # (`_check_x(text: str)`) فكانت خارج نظر القفل بأكملها — أربعة
        # فحوص عربية المِجَسّ خامدة على الإنجليزية بلا إعلان والكاشف
        # يعيد []. الشرط يشمل المعامل النصي الآن.
        takes_text_param = any(a.arg == "text" for a in node.args.args)
        if not (takes_text_param or re.search(
                r'\.get\("text"\)|combined_text|_report_text\(', seg)):
            continue
        aware = ("lang" in [a.arg for a in node.args.args]
                 or "silk_i18n" in seg or "_hits(" in seg)
        if aware:
            continue
        probes = _text_probes(node, consts)
        bare = [_RE_ESCAPE_RE.sub("", p) for p in probes]
        arabic = [p for p in bare if _AR_CHAR_RE.search(p)]
        latin = [p for p in bare if _LATIN_RE.search(p)]
        if arabic and not latin:
            offenders.append(node.name)
    return sorted(offenders)


def test_the_detector_can_actually_fail():
    """الحارسُ يُثبِت قدرتَه على الفشل قبل أن يُصدَّق (الدرس ٩٨): نفسُ التحليل
    على دالةٍ عربيةِ المِجَسّ مصطنعة يجب أن يلتقطها."""
    src = (
        'def _check_toy(dr: dict) -> list[dict]:\n'
        '    text = ((dr.get("report") or {}).get("text") or "")\n'
        '    if "عبارة ممنوعة" in text:\n'
        '        return [{"check": "toy", "repairable": True, "note": "x"}]\n'
        '    return []\n')
    tree = ast.parse(src)
    fn = tree.body[0]
    probes = _text_probes(fn, {})
    assert any(_AR_CHAR_RE.search(p) for p in probes), \
        "المحلّلُ لا يرى مِجَسّاً عربياً صريحاً — حارسٌ عاجزٌ عن الفشل"


def test_no_undeclared_arabic_only_check_survives():
    """**القفلُ الدائم.** كلُّ فحصٍ يقرأ متنَ التقرير إمّا ثنائيُّ المِجَسّ
    (يأخذ `lang` / يستعمل `_hits`) أو **مُعلَنٌ** في `_AR_ONLY_CHECKS`.

    وإلا فهو فحصٌ يخمُد صامتاً على تقريرٍ إنجليزيّ — والمشغّلُ يقرأ `PASS`
    ويظنّه قياساً. هذا هو بعينه العطلُ الذي أنتج هذه الموجة."""
    offenders = _arabic_only_probe_checks()
    declared = {c for c, *_ in G._AR_ONLY_CHECKS}
    # الإعلانُ بأسماء الفحوص **المُصدَرة** (قناةُ skipped_checks تعرضها
    # للمشغّل)، واسمُ الدالة قد يخالفها (`_check_confidence_band_label` يُصدِر
    # `confidence_band_mismatch`) — فالمطابقةُ على المُصدَر واسمِ الدالة معاً.
    src = pathlib.Path("silk_quality_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    emitted: dict[str, set] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and \
                node.name.startswith("_check_"):
            seg = ast.get_source_segment(src, node) or ""
            emitted[node.name] = set(
                re.findall(r'"check":\s*"(\w+)"', seg))
    undeclared = [f for f in offenders
                  if not any(d in f or d in emitted.get(f, set())
                             for d in declared)]
    assert undeclared == [], (
        "فحوصٌ عربيةُ المِجَسّ بلا مرآةٍ إنجليزية ولا إعلانٍ في "
        f"`_AR_ONLY_CHECKS`: {undeclared} — أضِف مِجَسّاً إنجليزياً في "
        "`_GATE_PROBES` أو أعلِنها صراحةً؛ الصمتُ غيرُ المعلَن ممنوع")


def test_declared_ar_only_list_states_a_reason_for_each_entry():
    """القائمةُ مصدرُ صدقِ البوّابة أمام المشغّل — لا بندَ بلا سبب مقروء."""
    assert G._AR_ONLY_CHECKS, "قائمةُ الإعلان فارغة — إمّا خطأٌ أو حذفٌ صامت"
    for row in G._AR_ONLY_CHECKS:
        check, reason = row[0], row[1]
        assert check.strip() and len(reason.strip()) > 20, \
            f"بندُ «{check}» بلا سببٍ مفهوم"

# ══════════════════════════════════════════════════════════════════════════
# ٤) أقفالُ المراجعة الذاتية (§58) — مرآةٌ أضعفُ من أصلها أسوأُ من غيابها
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang,text", [
    ("ar", "الحكم دخول مشروط، وتكلفة الدخول إلى السوق 40 ألف دولار."),
    ("en", "The verdict is conditional entry. The cost to enter the market "
           "is USD 40,000."),
])
def test_a_tier_label_without_a_claim_cue_is_not_a_verdict(lang, text):
    """«Enter the market» عبارةُ فعلٍ شائعة — ذكرُها في جملةِ تكلفةٍ ليس
    ادّعاءَ حكم. حاجزٌ يشتعل على تقريرٍ سليم يُفقِد البوّابةَ مصداقيّتها
    تماماً كحاجزٍ صامت."""
    assert G._check_recommendation_tier_label_consistency(
        _tier_dr(text), lang) == []


@pytest.mark.parametrize("lang,text", [
    ("ar", "بشكل عام، دليل غير كافٍ حول التسعير في هذه السوق."),
    ("en", "Overall, insufficient evidence was found on pricing in this "
           "market."),
])
def test_insufficiency_is_never_attributed_to_an_unlocated_intersection(
        lang, text):
    """تقاطعٌ لا يُعثَر على اسمه في المتن لا يُلام: النافذةُ كانت تتّسع إلى
    المتن كلِّه، فجملةٌ واحدة تُنتِج حاجزاً لكلّ تقاطعٍ ذي بنود (خمسةً على
    الإنجليزية دائماً — اسمُ التقاطع مصطلحُ عرضٍ لا يكتبه الكاتب)."""
    dr = {"report": {"text": text},
          "analyst": {"by_category": {k: [1, 2] for k in
                                      ("demand", "entry_cost",
                                       "price_competitiveness",
                                       "entry_door", "swot")}}}
    assert G._check_intersection_insufficiency(dr, lang) == []


def test_english_conditional_probes_are_not_common_words():
    """مِجَسّاتُ الصياغة الشرطية الإنجليزية صياغاتُ افتراضٍ صريحة: «under
    the» و«if » كانتا تُطفئان الفحصَ على أيّ متنٍ عاديّ."""
    for banned in ("under the", "if ", "the ", "a "):
        assert banned not in G._probe("parameter_conditional", "en"),             f"مِجَسٌّ إنجليزيّ فضفاض «{banned}» يُطفئ الفحص"
    dr = {"economics": {"reverse_solve": {"scenarios": [1],
                                          "max_exw": 2.9762}},
          "report": {"text": "Under the current plan the maximum ex-works "
                             "price is 2.9762."}}
    assert G._check_epistemic_verb_discipline(dr, "en"),         "رقمُ معلمةٍ مُقرَّرٌ بلا افتراضٍ صريح مرّ — المرآةُ أضعفُ من أصلها"


@pytest.mark.parametrize("lang,text", [
    ("ar", "واردات الأردن 7.67 مليون دولار هذا العام"),
    ("en", "Imports of Jordan reached 7.67 million dollars this year"),
])
def test_denominator_conflict_guard_reads_both_languages(lang, text):
    """حارسُ تناقض المقام كان يُمفصِل على «واردات» حرفياً — ورمزُ التهريب
    `\n` في نمطه أخفاه عن كاشف الأحادية اللغوية نفسِه."""
    view = {"markets": [{
        "components_detail": [{"name": "market_size", "value": 20_000_000.0}],
        "supplier_countries": [{"partner": "Saudi Arabia",
                                "value_usd": 7_670_000.0}]}]}
    out = G._check_metric_value_conflict(view, {"report": {"text": text}},
                                         lang)
    assert out and out[0]["check"] == "metric_value_conflict"


def test_the_detector_sees_through_regex_escapes():
    r"""`\n`/`\d` تحملان حروفاً لاتينية — فكان مِجَسٌّ عربيٌّ خالص يُقرأ
    «ثنائيَّ اللغة» ويفلت. القفلُ يُثبِت أنّ التهريبَ لم يعد يُعمي الكاشف."""
    src = ('def _check_toy(dr: dict) -> list[dict]:\n'
           '    text = ((dr.get("report") or {}).get("text") or "")\n'
           '    for m in re.finditer(r"واردات[^،\\n]{0,60}", text):\n'
           '        return [{"check": "toy", "repairable": True}]\n'
           '    return []\n')
    probes = _text_probes(ast.parse(src).body[0], {})
    bare = [_RE_ESCAPE_RE.sub("", p) for p in probes]
    assert bare and any(_AR_CHAR_RE.search(p) for p in bare)
    assert not any(_LATIN_RE.search(p) for p in bare), \
        "رمزُ التهريب ما زال يُقرأ لاتينيّةً — الكاشفُ أعمى عن عائلةٍ كاملة"


def test_the_detector_sees_module_constant_regexes_and_loop_vars():
    """**صيد الفجوات ٣ (الدرس ١٥٧).** مِجَسٌّ عربيٌّ في ثابت وحدةٍ
    (`_TOY_RE = re.compile(...)`) كان يُصنَّف «ثنائيَّ اللغة» لأنّ حروفَ
    الغلاف `re.compile(` لاتينية؛ ومتغيّرُ الحلقة (`for rex in _RES`) كان
    ينحلّ إلى "" فيختفي. الكاشفُ الأعمى أعاد صفرَ مخالفين بينما خمسةُ فحوصٍ
    حاجبةٍ خامدةٌ فعلاً — حارسُ فراغٍ للقدرتين المُصلَحتين."""
    consts = {"_TOY_RE": 're.compile(r"عبارة ممنوعة")',
              "_TOY_RES": '[re.compile(r"مجس اول"), re.compile(r"مجس ثان")]'}
    src1 = ('def _check_toy(text: str) -> list[dict]:\n'
            '    if _TOY_RE.search(text):\n'
            '        return [{"check": "toy", "repairable": True}]\n'
            '    return []\n')
    probes = _text_probes(ast.parse(src1).body[0], consts)
    bare = [_RE_ESCAPE_RE.sub("", p) for p in probes]
    assert any(_AR_CHAR_RE.search(p) and not _LATIN_RE.search(p)
               for p in bare), \
        "ثابتُ الوحدة النمطيّ ما زال يُقرأ بغلافه اللاتيني — كاشفٌ أعمى"
    src2 = ('def _check_toy2(text: str) -> list[dict]:\n'
            '    for rex in _TOY_RES:\n'
            '        if rex.search(text):\n'
            '            return [{"check": "toy2", "repairable": True}]\n'
            '    return []\n')
    probes2 = _text_probes(ast.parse(src2).body[0], consts)
    bare2 = [_RE_ESCAPE_RE.sub("", p) for p in probes2]
    assert any(_AR_CHAR_RE.search(p) and not _LATIN_RE.search(p)
               for p in bare2), \
        "متغيّرُ الحلقة ما زال ينحلّ إلى \"\" — الكاشفُ لا يرى القوائم"


def test_methodology_notes_channel_reaches_both_languages():
    """قناةُ `methodology_notes` (مستهلكٌ واحد) كانت تُطابِق «منهجية» حرفياً
    فتسقط صامتةً على تقريرٍ إنجليزيّ — ملاحظاتُ بوّابةٍ لا تبلغ أيَّ مصنوع."""
    import os
    import re as _re
    import tempfile
    import zipfile
    import silk_render as _R
    import silk_reports as _P
    from tools.canonical_netherlands import netherlands_research_blob
    for lang, head, want in (
            ("ar", "## 2. منهجية البحث ونطاقه", "حدود المنهجية"),
            # العنوانُ يبقى عربياً — قسمُ المشغّل أحاديُّ اللغة؛ المُصلَح هو
            # أنّ الملاحظاتِ لم تكن تبلغ المصنوعَ أصلاً على الإنجليزية.
            ("en", "## 2. Research Methodology and Scope",
             "حدود المنهجية")):
        blob = netherlands_research_blob()
        blob["deep_research"]["report"]["report"] = head + "\nBody.\n"
        view = _R.build_view(blob, lang)
        view["deep_research"]["quality_gate"] = {
            "methodology_notes": ["ملاحظة منهجية مقيسة"]}
        path = os.path.join(tempfile.mkdtemp(), "o.docx")
        _P.render_docx(view, path)
        with zipfile.ZipFile(path) as z:
            body = _re.sub(r"<[^>]+>", "",
                           z.read("word/document.xml").decode("utf-8"))
        assert "ملاحظة منهجية مقيسة" in body, (
            f"ملاحظاتُ البوّابة لا تبلغ مصنوعَ «{lang}»")
        assert want in body, f"عنوانُ الحدود ليس بلغة التقرير «{lang}»"

# ── جولةُ المراجعة الثانية (§58) — إصلاحٌ يُضعِف حارساً هو انحدار ──────────

@pytest.mark.parametrize("lang,text", [
    ("ar", "واردات الأردن 7,670,000 دولار هذا العام"),
    ("en", "Imports of Jordan reached 7,670,000 dollars this year"),
])
def test_denominator_guard_survives_comma_grouped_figures(lang, text):
    """الفاصلةُ اللاتينية تفصل الآحاد لا الجُمَل: وضعُها في صنف إنهاء المقطع
    قطعَ «7,670,000» فأسقط الالتقاطَ في اللغتين — «توسيعُ» الحارس كان
    تضييقاً له."""
    view = {"markets": [{
        "components_detail": [{"name": "market_size", "value": 20_000_000.0}],
        "supplier_countries": [{"partner": "Saudi Arabia",
                                "value_usd": 7_670_000.0}]}]}
    assert G._check_metric_value_conflict(view, {"report": {"text": text}},
                                          lang)


def test_a_claim_cue_in_another_clause_is_not_this_label_s_claim():
    """«We recommend a conditional entry now, and the exporter may enter the
    market later» ادّعاءٌ **للحكم الصحيح** — لا للتسمية الأعلى."""
    assert G._check_recommendation_tier_label_consistency(
        _tier_dr("We recommend a conditional entry now, and the exporter "
                 "may enter the market later."), "en") == []


def test_access_timeline_probe_is_not_satisfied_by_any_total_time():
    """«total time» وحدَها تُطفئ الفحصَ على متنٍ لا يذكر مدةَ النفاذ."""
    assert "total time" not in G._probe("access_timeline", "en")
    dr = {"missions": {"customs_requirements": {"failed": False}},
          "report": {"text": "The total time in transit is 12 days."},
          "regulatory": {"access_timeline": {"total_days": {"min": 45,
                                                           "max": 60}}}}
    assert G._check_access_timeline_presence(dr, "en"), \
        "مدةُ النفاذ غائبةٌ والفحصُ صامت — مِجَسٌّ فضفاض أطفأه"


def test_operator_deep_section_stays_single_language():
    """قسمُ المشغّل عربيٌّ بالكامل — عنوانٌ إنجليزيٌّ وحيدٌ بين عربيّاتٍ قسمٌ
    مهجَّن. المُصلَح هو **سقوطُ القناة** لا لغةُ عنوانها."""
    src = pathlib.Path("silk_reports.py").read_text(encoding="utf-8")
    i = src.index("def _docx_deep_research(")
    body = src[i:i + 6000]
    assert "حدود المنهجية وجودة البيانات" in body
    assert "methodology_limits_head" not in src, \
        "مصطلحٌ في المعجم بلا مستهلك — وهو بعينه ما تُصلحه هذه الموجة"
