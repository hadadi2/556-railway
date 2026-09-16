"""موجةُ عيوب التقرير — الطبقةُ اللغوية (الأصناف ١–٥)، اختبارٌ أوّلاً.

كلُّ صنفٍ هنا يُعيد إنتاجَ العيب المرصود ثمّ يثبت أن الجذرَ سُدّ **عند
المولّد** (قالب/موجّه/طبقةُ عرض) لا في نصّ تقريرٍ واحد، وأنّ قاعدةَ البوابة
تُطلِق على عائلته في أيّ تقريرٍ مستقبليّ لأيّ سوقٍ ومنتج.

القاعدةُ الحاكمة للطبقة اللغوية: **صفرُ تغييرٍ في القيم** — لا درجة ولا حكم
ولا ثقة ولا أيّ رقمٍ مخزَّن. الإثباتُ بسكربت لا بالعين:
`tools/report_quality_baseline.py compare` + `tests/test_verdict_score_baseline.py`.

Run: python3 -m pytest tests/test_report_quality_reader_layer.py -q
"""
from __future__ import annotations

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from conftest import block_network, docx_all_text  # noqa: E402


# ════════════════════════ أدواتُ إعادة الإنتاج ════════════════════════

def _production_view(blob_key: str) -> dict:
    """عرضٌ مبنيٌّ **كما يبنيه الإنتاج** لا كما تحمله المدوّنة المخزَّنة.

    المدوّناتُ القانونية العشر مُجمَّدةٌ بـ`markets: []` (التُقطت قبل
    `_attach_deep_market_row`)، ولذلك **لا تُشغِّل `silk_render.decision_basis`
    إطلاقاً** — وهي منطقةٌ عمياء تُعلَن لا تُخفى: كلُّ عيبٍ في مسار
    «أساس الحكم ← docx العميل» غيرُ قابلٍ لإعادة الإنتاج من المدوّنة وحدها.
    هذا المُعِدُّ يبني الصفَّ بنفس مفاتيح
    `silk_research_pipeline._attach_deep_market_row` (`decision` +
    `components` + `total_score`/`confidence`) فيُشغِّل المسار فعلاً.
    """
    import silk_deep_pillars
    import silk_render
    from tools import gen_verdict_baseline as B

    mod, fn = B.CANONICAL_BLOBS[blob_key]
    blob = getattr(importlib.import_module(mod), fn)()
    dr = blob.get("deep_research") or {}
    market = blob.get("market") or {}
    dec = silk_deep_pillars.decide_for_deep(dr, product_card=None,
                                            regulatory=None)
    row = {
        "iso3": market.get("iso3") or "XXX",
        "name_ar": market.get("name_ar") or "سوق",
        "name_en": market.get("name_en") or "Market",
        "country": market.get("name_ar") or market.get("name_en") or "سوق",
        "rank": 1, "deep": True,
        "components": silk_deep_pillars.build_components(dr),
        "decision": dec,
    }
    if dec.get("score") is not None:
        row["total_score"] = dec["score"]
    if dec.get("confidence") is not None:
        row["confidence"] = dec["confidence"]
    blob = dict(blob)
    blob["markets"] = [row]
    return silk_render.build_view(blob)


def _canonical_keys() -> list:
    from tools import gen_verdict_baseline as B
    return sorted(B.CANONICAL_BLOBS)


# ════════════════ الصنف ١ — لغةُ النظام تصل القارئ ════════════════

# العشرُ المرصودة حرفياً في بلاغ المالك — بذرةُ القائمة المحظورة.
_OBSERVED_LEAKS = (
    "لم تصل معادلة محسوبة مسبقاً",
    "لم يتمكن الاستدعاء من جلب أي سجل",
    "عطل تقني في واجهة",
    "خارج أساس الحكم الآلي",
    "بعثة بحثية",
    "تقاطع المحلل بلا أدلة كافية",
    "وحدة نقدية",
    "وحدة ريال لكل دولار",
    "العمود الأقوى",
    "هامش المضاهاة",
    "بفئة تكلفة",
)


def test_c1_every_observed_leak_phrase_is_caught():
    """إعادةُ إنتاج: كلُّ عبارةٍ من العشر المرصودة تُطلِق القاعدة.

    سبعٌ منها لا يُنتجها أيُّ قالبٍ في المستودع (من نثر الكاتب) — فالقاعدةُ
    الحتمية هي حارسُها الوحيد الممكن، وهذا الاختبار يثبت أنها فعلاً تُطلِق.
    """
    from silk_quality_gate import _check_reader_language_leak as chk
    for phrase in _OBSERVED_LEAKS:
        text = f"## 1. الخلاصة التنفيذية\nالتوصية: تمهّل. {phrase} في السوق."
        out = chk(text)
        assert any(f["check"] == "reader_language_leak" for f in out), phrase
        note = out[0]["note"]
        # البلاغُ يحمل القسمَ والنصَّ كما طلب بلاغ المالك.
        assert "الخلاصة التنفيذية" in note, phrase
        assert "التوصية: تمهّل" in note, phrase


def test_c1_raw_symbols_are_caught():
    from silk_quality_gate import _check_reader_language_leak as chk
    for tok in ("null", "undefined", "NaN", "N/A", "pipeline", "{", "}"):
        out = chk(f"## 3. السوق\nالحصة {tok} لهذا العام.")
        assert out, tok
        assert tok in out[0]["note"], tok


def test_c1_contextual_tokens_fire_only_in_the_system_sense():
    """شرطُ صدقٍ لا تسامح: «معادلة»/«واجهة»/«آلي» مشروعةٌ تجارياً.

    «معادلة» وردت ١١ مرّة في خطّ الأساس كلُّها **مأمورٌ بها** في معيار
    الكتابة؛ و«واجهة» كانت تُلتقَط من داخل «مواجهة» بلا حدِّ كلمة. قاعدةٌ
    تُطلِق على هذه إنذارٌ كاذبٌ في كلّ تقرير — فتُفحَص بالقرينة.
    """
    from silk_quality_gate import _check_reader_language_leak as chk
    legit = (
        "## 4. أرقام القرار\nمعادلة التعادل = كلفة الدخول ÷ هامش الوحدة.",
        "## 6. المشهد التنافسي\nالتهديد في مواجهة انكماش الطلب.",
        "## 5. القنوات\nواجهة المتجر تعرض الصنف في الرف الأوسط.",
        "## 8. اللوجستيات\nخطّ إنتاج آلي بطاقة 12 طناً يومياً.",
    )
    for text in legit:
        assert chk(text) == [], text
    system_sense = (
        "## 2. المنهجية\nعطل في واجهة النظام منع الجلب.",
        "## 2. المنهجية\nرمز HS 040110 مُصنَّفٌ آلياً بلا تدقيق.",
    )
    for text in system_sense:
        assert chk(text), text


def test_c1_appendix_is_exempt_like_the_decimal_rule():
    """الملحقُ التقنيّ سطحُ مدقّقٍ لا سطحُ قارئ — نفسُ استثناء دقّة العشور."""
    from silk_quality_gate import _check_reader_language_leak as chk
    body = "## 1. الخلاصة\nالتوصية: ادخل بشحنة تجريبية."
    assert chk(body) == []
    assert chk(body + "\n\n## 11. الملاحق\nالقيمة null في السجل.") == []


def test_c1_the_three_real_templates_no_longer_speak_to_a_developer():
    """الثلاثُ الموجودةُ فعلاً في المستودع — مُصلَحةٌ في **منشئها**."""
    import silk_decision
    import silk_i18n
    import silk_render

    # (١) قالبُ i18n لم يبقَ يسمّي بنيةً داخلية.
    for lang in ("ar", "en"):
        line = silk_i18n.t("limit_analyst_thin", lang, label="الطلب")
        assert "تقاطع المحلل" not in line
        assert "analyst intersection" not in line
        assert "الطلب" in line or "الطلب" in str(line)
    # (٢) سردُ المحرّك بمفردةِ القارئ «الجانب» لا «العمود» — يُفحَص على
    #     **النصّ المُنتَج** لا على شيفرة الوحدة: سطرُ توثيقٍ داخليّ يذكر
    #     «أضعف الأعمدة» لا يصل قارئاً، وفحصُ المصدر يصطاده كاذباً.
    banned = ("العمود الأقوى", "العمود الأضعف", "أقوى الأعمدة",
              "أضعف الأعمدة", "عمود ضعيف", "عمود قوي", "لا أعمدة محسوبة")
    emitted = []
    with block_network():
        for key in _canonical_keys():
            view = _production_view(key)
            basis = ((view.get("decision") or {}).get("basis") or {})
            emitted.append(str(basis.get("counter_case_line") or ""))
            emitted += [str(c) for c in (basis.get("conditions") or [])]
            emitted += [str((r or {}).get("note") or "")
                        for r in (basis.get("pillars") or [])]
    blob = "\n".join(emitted)
    assert blob.strip(), "لم يُنتِج أيُّ سوقٍ نصَّ أساسِ حكم — المسار خامد"
    for term in banned:
        assert term not in blob, term
    # (٣) «هامش المضاهاة» نحتٌ يحظره الموجّه — لا تطبعه طبقةُ العرض بعدها.
    for mod in (silk_render, __import__("silk_reports")):
        text = open(mod.__file__, encoding="utf-8").read()
        assert "هامشك عند المضاهاة" not in text, mod.__name__


def test_c1_counter_case_reaches_the_client_docx_in_reader_language():
    """**إعادةُ إنتاجٍ مباشرة** لمسار التسريب الحقيقيّ، من طرفٍ إلى طرف.

    الجذرُ المرصود: `silk_decision.counter_case` → `entry_decision` →
    `silk_render.decision_basis` → `counter_case_line` → **docx العميل**
    (`silk_reports._client_decision_basis`). قبل الإصلاح كانت مدوّنةُ
    الجزائر (الحكمُ الوحيد المشروط بجانبين محسوبين) تُسلِّم «العمود الأقوى»
    و«العمود الأضعف» حرفياً في وورد العميل العربيّ.
    """
    import silk_reports
    import tempfile
    view = _production_view("dza_peanut_butter")
    line = ((view.get("decision") or {}).get("basis") or {}).get(
        "counter_case_line") or ""
    assert line, "لم يُبنَ سطرُ الحجة المضادة — المسارُ لم يُشغَّل فعلاً"
    for banned in ("العمود", "الأعمدة", "الدرجة الموزونة"):
        assert banned not in line, banned
    assert "الجوانب" in line, "المفردةُ المعتمدة للقارئ «الجانب» غائبة"

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "client.docx")
        silk_reports.render_client_docx(view, path)
        txt = docx_all_text(path)
    for banned in ("العمود الأقوى", "العمود الأضعف", "الدرجة الموزونة"):
        assert banned not in txt, banned


def test_c1_stored_blobs_before_the_fix_are_still_sanitized():
    """شبكةُ الأمان: مدوّنةٌ مخزَّنةٌ **قبل** الإصلاح تحمل المفردةَ القديمة —
    الزوجُ الواحد يستبدلها (سابقة `test_weighted_score_sanitized_as_backstop`).
    """
    from silk_reports import _client_sanitize
    out = _client_sanitize(
        "من جهةٍ العمود الأقوى «الملاءمة التنظيمية» ومن جهةٍ العمود الأضعف "
        "«شدة المنافسة»، وبلغت الدرجة الموزونة 66%.", "ar")
    for banned in ("العمود الأقوى", "العمود الأضعف", "الدرجة الموزونة"):
        assert banned not in out, banned
    assert "66%" in out, "الرقمُ لا يُمَسّ — تُستبدَل التسمية لا القيمة"


def test_c1_rule_is_one_source_read_by_prompt_reviewer_and_gate():
    """مصدرٌ واحد: العقدُ المحقون في الكاتب هو نفسُه المُدقَّق والمُنفَّذ.

    عقدٌ في الموجّه بلا قائمةٍ في الفحص = قاعدةٌ لا يمكن أن تُطلِق؛ وقائمةٌ
    في الفحص بلا عقدٍ في الموجّه = عقابٌ على ما لم يُطلَب (الدرس 176).
    """
    import inspect

    import silk_ai_judge
    import silk_quality_gate
    import silk_style_contract as S

    for name in ("WRITER_STYLE_CONTRACT", "ACADEMIC_WRITER_CONTRACT"):
        assert S.READER_LANGUAGE_RULE in getattr(S, name), name
    for name in ("WRITER_STYLE_CONTRACT_EN", "ACADEMIC_WRITER_CONTRACT_EN"):
        assert S.READER_LANGUAGE_RULE_EN in getattr(S, name), name
    assert "reader_language_rule" in inspect.getsource(
        silk_ai_judge.review_report)
    gate_src = inspect.getsource(silk_quality_gate._check_reader_language_leak)
    for const in ("FORBIDDEN_READER_PHRASES", "HARD_READER_TOKENS",
                  "CONTEXTUAL_READER_TOKENS", "SYSTEM_SENSE_CUES"):
        assert const in gate_src, const
    # وكلُّ عبارةٍ مرصودة مُدرَجةٌ فعلاً في المصدر الواحد.
    listed = set(S.FORBIDDEN_READER_PHRASES)
    for phrase in _OBSERVED_LEAKS:
        assert phrase in listed or any(
            phrase in p or p in phrase for p in listed), phrase


def test_c1_rule_is_wired_into_the_gate_verdict_path():
    """القاعدةُ مُسجَّلة في `run_quality_gate` — لا فحصٌ معزولٌ لا يُنادى
    (سابقة الدرس 98: الحارسُ الذي لا يمكن أن يُطلِق)."""
    import inspect

    import silk_quality_gate as G
    assert "_check_reader_language_leak" in inspect.getsource(
        G.run_quality_gate)
    view = {"deep_research": {
        "report": {"text": "## 1. الخلاصة\nعطل تقني في واجهة النظام."},
        "missions": {}, "verdict": {},
        "analyst": {"summary": "", "by_category": {},
                    "missing_categories": []}}}
    out = G.run_quality_gate(view)
    assert any(f["check"] == "reader_language_leak" for f in out["findings"])
    # تحذيريّ لا حاجب (قرار المالك 2026-08-19: لا حجب جديداً بلا راية).
    assert "reader_language_leak" not in G.FAIL_TRIGGER_CHECKS


def test_c1_zero_false_positives_across_every_canonical_blob():
    """شرطُ القبول: صفرُ إطلاقةٍ للقاعدة الجديدة على المدوّنات العشر.

    قاعدةٌ تُطلِق على تقريرٍ صحيح تُستهلَك تحذيراتُها فتصير عمياء — وهذا
    أسوأ من غيابها."""
    import silk_quality_gate as G
    with block_network():
        for key in _canonical_keys():
            from tools import gen_verdict_baseline as B
            import silk_render
            mod, fn = B.CANONICAL_BLOBS[key]
            blob = getattr(importlib.import_module(mod), fn)()
            out = G.run_quality_gate(silk_render.build_view(blob))
            hits = [f["note"] for f in out["findings"]
                    if f["check"] == "reader_language_leak"]
            assert hits == [], (key, hits)


def test_c1_auto_classified_phrase_becomes_reader_language_deterministically():
    """«مُصنَّفٌ آلياً» تقول كيف عمل النظام؛ القارئُ يحتاج ما يعنيه لقراره.

    الإصلاحُ حتميٌّ في طبقة العرض (نفسُ علاج البند 23) فلا يعتمد على تذكّر
    النموذج — ويسري على كلّ صيغةٍ من العائلة لا على جملةٍ واحدة."""
    import silk_render
    for raw, must in (
            ("رمز HS 040110 مُصنَّفٌ آلياً؛ وصفُه الرسمي", "بلا مراجعة بشرية"),
            ("الرمز صُنِّف آلياً على هذا البند", "بلا مراجعة بشرية"),
            ("حُسِم آلياً بالسمة الرقمية", "بلا مراجعة بشرية")):
        out = silk_render._AUTO_CLASSIFIED_RE.sub(
            r"\1\2 بلا مراجعة بشرية", raw)
        assert must in out and "آلياً" not in out, raw


# ════════════════ الصنف ٢ — خانةٌ فارغة تكسر جملة ════════════════

_SLOT_RE = __import__("re").compile(r"\{([a-zA-Z_][a-zA-Z_0-9]*)\}")

# ما لا يكون مقصوداً في أيّ نصٍّ معروضٍ سليم — نفسُ معايير قاعدة البوابة.
_INTERP_DEFECTS = (
    ("خانةٌ لم تُحشَ", __import__("re").compile(r"[{}]")),
    ("قوسٌ فارغ", __import__("re").compile("«\\s*»|\\(\\s*\\)|\\[\\s*\\]")),
    ("نقطتان متدلّيتان",
     __import__("re").compile(r":\s*(?:$|[.،؛,;])", __import__("re").M)),
    ("فراغٌ مزدوج", __import__("re").compile(r"[ \t]{2,}(?!$)",
                                             __import__("re").M)),
    ("ترقيمٌ يتيم",
     __import__("re").compile(r"[—–]\s*(?:$|[.،؛,;])|،\s*[،.]|,\s*[,.]",
                              __import__("re").M)),
    ("نسبةٌ بلا رقمها",
     __import__("re").compile(r"(?<![\d٠-٩])%")),
)


def _slotted_pairs() -> list:
    """كلُّ (مفتاح، لغة) يحمل خانةً — عدا صيغِ الفراغ نفسها."""
    import silk_i18n as I
    out = []
    for key, row in I.TERMS.items():
        if key.endswith(I._EMPTY_SUFFIX):
            continue
        for lang in ("ar", "en"):
            tpl = row.get(lang)
            if isinstance(tpl, str) and _SLOT_RE.search(tpl):
                out.append((key, lang, sorted(set(_SLOT_RE.findall(tpl)))))
    return out


def test_c2_every_template_survives_all_slots_empty():
    """**إعادةُ إنتاجٍ مُقاسة:** كان ٦٣ من ٨٦ زوجاً ينكسر بتفريغ خاناته.

    القاعدة: أيُّ قالبٍ يُعرَض بخاناتٍ فارغة يخرج جملةً سليمة — إمّا بصيغةِ
    فراغٍ نحوية صريحة (`<key>_empty`) أو بإصلاحٍ مكانيكيّ حتميّ.
    """
    import silk_i18n as I
    pairs = _slotted_pairs()
    assert len(pairs) >= 80, f"عددُ القوالب ذاتِ الخانات انخفض ({len(pairs)}) — تحقّق"
    broken = []
    for key, lang, slots in pairs:
        out = I.t(key, lang, **{s: "" for s in slots})
        hits = [name for name, rx in _INTERP_DEFECTS if rx.search(out)]
        if hits:
            broken.append((key, lang, hits, " ".join(out.split())[:70]))
    assert broken == [], broken


def test_c2_empty_variant_wins_over_mechanical_repair_when_registered():
    """جملةٌ تدّعي رقماً لا يُصلِحها تنظيف — تُقدَّم صيغةُ الفراغ الصريحة."""
    import silk_i18n as I
    out = I.t("decision_weighted_line", "ar", score="", conf="")
    assert "من 100" not in out, "الجملةُ ما زالت تدّعي درجةً غير محسوبة"
    from silk_quality_gate import _norm_ar
    assert _norm_ar("غير محسوبة") in _norm_ar(out)
    # وبخانةٍ ممتلئةٍ لا يتغيّر شيء — المسارُ القائم سليم.
    full = I.t("decision_weighted_line", "ar", score=65, conf=80)
    assert "65" in full and "80" in full and "من 100" in full


def test_c2_zero_slot_calls_are_untouched():
    """عقدُ عدم المساس: بلا خانةٍ فارغة، `t()` كما كانت حرفاً."""
    import silk_i18n as I
    assert I.t("pillar_col", "ar") == "الجانب"
    assert I.t("limit_hs_classification", "ar", detail="رمز غير مؤكّد") == \
        "تصنيف HS: رمز غير مؤكّد"
    # والصفرُ ليس فراغاً — رقمٌ مشروع.
    assert "0" in I.t("cond_pillar_weak", "ar", pillar="المنافسة", pct=0)


def test_c2_prose_criterion_differs_from_the_slot_criterion():
    """قناتان بمِعيارَيهما: شرطةٌ آخرَ سطرٍ في نثرٍ مطويّ **ليست** عطباً.

    قياسٌ على مدوّنة Nadec: «… (UHT) —» سطرٌ تكمله الجملةُ التالية. معيارُ
    القالب يراها يتيمة؛ معيارُ النثر لا. قناةٌ بمعيارٍ خاطئ تُنتِج إنذاراً
    كاذباً في كلّ تقريرٍ مطويِّ الأسطر."""
    import silk_i18n as I
    wrapped = "رمز HS 040110 (حليب طازج دسمه ≤1%)، بينما المنتج كامل الدسم —"
    assert I.tidy_punctuation(wrapped) == wrapped
    assert I.repair_interpolation("تصنيف HS:") == "تصنيف HS"
    assert I.tidy_punctuation("التوصية:") == "التوصية:"


def test_c2_gate_catches_each_defect_family():
    from silk_quality_gate import _check_template_interpolation as chk
    for text in (
            "## 1. الخلاصة\nالسوق {label} يستوعب الصنف.",
            "## 2. المنهجية\nاعتمدنا مصادر رسمية () في هذا التقرير.",
            "## 3. السوق\nينقصه:",
            "## 4. الأرقام\nالشريحة المحسوبة أعلاه رغم أن حجمها غير محسوب.",
            "## 5. المنافسة\nثم السعودية بالحصة السعودية البالغة 10.44%."):
        out = chk(text)
        assert out, text
        assert all(f["check"] == "template_interpolation" for f in out)


def test_c2_measured_exemptions_do_not_fire():
    """ثلاثةُ استثناءاتٍ مُعايَرةٌ على خطّ الأساس — لا تخميناً."""
    from silk_quality_gate import _check_template_interpolation as chk
    for text in (
            # وحدةٌ مكرّرة في سلّم أسعار — تكرارُها شرطُ المقارنة.
            "## 4. الأسعار\n0.85 دينار/لتر مقابل 0.55 دينار/لتر للمحلية.",
            "## 3. السوق\n7.12 مليون دولار مقابل 2.09 مليون دولار.",
            # شرحٌ مقحوم داخل قوس — قناةُ الصنف ٤ لا هذه.
            "## 6. المنافسة\nمؤشر التركّز HHI (مؤشر يقيس تركّز السوق).",
            # نثرٌ مطويٌّ بشرطةٍ آخرَ السطر.
            "## 2. المنهجية\nرمز HS 040110 (حليب طازج) —\nبينما المنتج كامل.",
            # جدولٌ وعنوانٌ — فراغُ المحاذاة مقصود.
            "## 7. الجدول\n| الجانب | قوّته |\n|---|---|\n| السوق | 89% |"):
        assert chk(text) == [], text


def test_c2_zero_false_positives_across_every_canonical_blob():
    import silk_quality_gate as G
    import silk_render
    from tools import gen_verdict_baseline as B
    with block_network():
        for key in _canonical_keys():
            mod, fn = B.CANONICAL_BLOBS[key]
            blob = getattr(importlib.import_module(mod), fn)()
            out = G.run_quality_gate(silk_render.build_view(blob))
            hits = [f["note"] for f in out["findings"]
                    if f["check"] == "template_interpolation"]
            assert hits == [], (key, hits)


def test_c2_rule_is_one_source_and_wired_into_the_gate():
    import inspect

    import silk_quality_gate as G
    import silk_style_contract as S
    for name in ("WRITER_STYLE_CONTRACT", "ACADEMIC_WRITER_CONTRACT"):
        assert S.REFERENTIAL_INTEGRITY_RULE in getattr(S, name), name
    for name in ("WRITER_STYLE_CONTRACT_EN", "ACADEMIC_WRITER_CONTRACT_EN"):
        assert S.REFERENTIAL_INTEGRITY_RULE_EN in getattr(S, name), name
    assert "_check_template_interpolation" in inspect.getsource(
        G.run_quality_gate)
    assert "template_interpolation" not in G.FAIL_TRIGGER_CHECKS


def test_c2_render_layer_repairs_prose_punctuation_deterministically():
    """الإصلاحُ في طبقة العرض لا في تذكّر النموذج (امتدادُ علاج البند 13)."""
    import silk_render
    out = silk_render._strip_internal_plumbing(
        "بقيمة 7.12 مليون دولار سنوياً ، بمعدّل نموّ موجب . ومصادر رسمية ()")
    assert "سنوياً ،" not in out and "موجب ." not in out and "()" not in out
