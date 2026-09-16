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


class _env:
    """متغيّراتُ بيئةٍ باستعادةٍ مضمونة — الاصطلاحُ القائم في هذه الحزمة."""

    def __init__(self, **vals):
        self.vals = vals
        self.old = {}

    def __enter__(self):
        for k, v in self.vals.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


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


# **التثبيتةُ الموجَبة الوحيدة** — نثرُها يحمل العيوبَ عمداً، فتُستثنى من كلّ
# تأكيدٍ سالب **بالاسم** لا بصمت (وتُثبَت إطلاقاتُها في اختبارها الخاصّ).
_POSITIVE_FIXTURES = ("egypt_olive_oil",)


def _canonical_keys() -> list:
    """كلُّ المدوّنات — للقياس والعرض."""
    from tools import gen_verdict_baseline as B
    return sorted(B.CANONICAL_BLOBS)


def _negative_keys() -> list:
    """المدوّناتُ التي يجب أن تمرّ بصفرِ إطلاقة."""
    return [k for k in _canonical_keys() if k not in _POSITIVE_FIXTURES]


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


def test_c1_alef_hamza_does_not_collide_with_the_preposition_ila():
    """**تصادمٌ رصده حارسٌ قائم** (`test_quality_gate_stays_warn…`): «إلى»
    تُطبَّع إلى «الي» بتوحيد الهمزات، وكذلك «آلي» — فكان حرفُ الجرّ الأكثرُ
    شيوعاً في العربية يُبلَّغ «لغةَ نظام» في كلّ تقرير.

    العلاجُ: المفرداتُ ذاتُ المعنيين تُطابَق بتطبيعٍ **يحفظ صيغةَ الألف**
    (حركاتٌ وتطويلٌ فقط). حارسُ انحدارٍ دائم — أيُّ عودةٍ لتوحيد الهمزات في
    هذه القناة تُحمِّر هنا."""
    from silk_quality_gate import _check_reader_language_leak as chk
    for text in ("## 5. المستهلك\nتنوّعت المؤشرات بلا إشارةٍ حاسمةٍ إلى "
                 "انقلاب.",
                 "## 3. السوق\nانتقل الطلبُ إلى العبوات الصغيرة.",
                 "## 9. المخاطر\nيؤدّي التأخيرُ إلى غرامةٍ تعاقدية."):
        assert chk(text) == [], text
    # والمعنى التقنيّ ما زال يُلتقَط.
    assert chk("## 2. المنهجية\nرمز HS مُصنَّفٌ آلياً بلا مراجعة.")


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
        for key in _negative_keys():
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
        for key in _negative_keys():
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
        for key in _negative_keys():
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


# ════════════ الصنف ٣ — عرضُ الأرقام والوحدات والتواريخ ════════════

def test_c3_one_formatter_thousands_separator_and_two_decimals():
    """**العيبُ المرصود حرفياً**: «36,234,200.146 مقابل 26730».

    أحدُهما بفاصلِ آلافٍ بلا عشور والآخرُ بلا فاصلٍ أصلاً — المقارنةُ بينهما
    تُقرأ خطأً. المُنسِّقُ الواحد يعطي الاثنين شكلاً واحداً.
    """
    import silk_narrative as N
    assert N.fmt_number(36234200.146) == "36,234,200.15"
    assert N.fmt_number(26730) == "26,730"
    assert N.fmt_number(None) == N.GAP
    assert N.fmt_number("نص") == "نص"


def test_c3_percentages_are_capped_at_two_decimals():
    """«12.416666666666666%» كانت تخرج من `{n:g}` — الحدُّ منزلتان."""
    import silk_narrative as N
    assert N.fmt_pct(12.416666666666666) == "12.42%"
    assert N.fmt_pct(84.05) == "84.05%"
    assert N.fmt_pct(84.0) == "84%"
    assert N.fmt_pct(-3.5, signed=True) == "-3.5%"
    assert N.fmt_pct(3.5, signed=True) == "+3.5%"
    assert N.fmt_pct(None) == N.GAP


def test_c3_score_has_exactly_one_form():
    """الدرجةُ ظهرت 65 و0.65 و65% في تقريرٍ واحد — صيغةٌ واحدة الآن."""
    import silk_narrative as N
    assert N.fmt_score(0.65) == "65 من 100"
    assert N.fmt_score(65) == "65 من 100"
    assert N.fmt_score(0.65) == N.fmt_score(65), "الكسرُ والعددُ صيغةٌ واحدة"
    assert N.fmt_score(None) == N.GAP


def test_c3_amount_carries_its_currency_and_never_invents_one():
    """العملةُ وسيطٌ صريح: غيابُها يُخرِج الرقمَ عارياً **كي يُلتقَط**، لا
    يُستَر بعملةٍ مختلَقة (عقدُ عدم الاختلاق نفسُه)."""
    import silk_narrative as N
    assert N.fmt_amount(48530000, "USD") == "48.53 مليون دولار"
    assert N.fmt_amount(7120000, "EUR") == "7.12 مليون يورو"
    assert N.fmt_amount(1234, "SAR") == "1,234 ريال"
    assert N.fmt_amount(1234) == "1,234", "لا عملةَ مفترضة"
    # رمزٌ ISO غيرُ مُسجَّلٍ عربياً يمرّ كما هو — لا تخمينَ اسم.
    assert N.fmt_amount(1000, "CHF") == "1,000 CHF"


def test_c3_observation_date_is_never_borrowed_from_the_clock():
    import silk_narrative as N
    assert N.fmt_observed_at("") == "تاريخ الرصد غير معروف"
    assert N.fmt_observed_at(None, "en") == "observation date unknown"
    assert N.fmt_observed_at("2024-03-01") == "2024-03-01"


def test_c3_elapsed_projection_year_is_detectable():
    """«يُتوقَّع أن يبلغ في 2024» مكتوبةً في 2026 خطأٌ زمنيّ يصل القارئ."""
    import silk_narrative as N
    assert N.past_tense_projection(2024, today_year=2026) is True
    assert N.past_tense_projection(2026, today_year=2026) is False
    assert N.past_tense_projection(2030, today_year=2026) is False
    assert N.past_tense_projection(None) is False


def test_c3_all_competing_formatters_now_share_one_source():
    """خمسُ عائلاتٍ متوازية صارت مصدراً واحداً — بأسمائها القائمة كما هي."""
    import silk_narrative as N
    from silk_decision import _pct
    from silk_reports import _fmt, _readable_number
    assert _fmt(36234200.146) == N.fmt_number(36234200.146)
    assert _readable_number(38000000.0) == N.fmt_amount(38000000.0)
    assert N.fmt_money(48530000) == N.fmt_amount(48530000, "USD")
    # `_pct` عقدُها كسرٌ 0–1 بلا منازل — المخرَجُ كما كان حرفياً.
    assert _pct(0.65) == "65%" and _pct(None) == "—"


def test_c3_gate_catches_score_format_drift():
    from silk_quality_gate import _check_score_format_drift as chk
    drift = ("## 1. الخلاصة التنفيذية\nقوة الفرصة 65 من 100.\n"
             "## 4. أساس الحكم\nالدرجة 0.65 لهذه السوق.")
    out = chk(drift)
    assert out and out[0]["check"] == "score_format_drift"
    assert chk("## 1. الخلاصة\nقوة الفرصة 65 من 100.") == []


def test_c3_gate_catches_amount_without_currency_but_not_units():
    from silk_quality_gate import _check_amount_without_currency as chk
    assert chk("## 3. السوق\nيستورد السوق 7.12 مليون سنوياً من الصنف.")
    # عملةٌ قريبة ⇒ سليم؛ وسياقٌ غيرُ ماليٍّ ⇒ سليم.
    assert chk("## 3. السوق\nيستورد السوق 7.12 مليون دولار سنوياً.") == []
    assert chk("## 5. المستهلك\nعدد السكان 38 مليون نسمة.") == []
    assert chk("## 8. اللوجستيات\nطاقةُ المصنع 2 مليون طن سنوياً.") == []


def test_c3_gate_catches_a_stale_figure_mentioned_without_its_year():
    """إنفاذُ البند 2.1 من إفصاح جودة البيانات — كان أمراً بلا حارس."""
    from silk_quality_gate import _check_stale_data_without_year as chk
    dr = {"report": {"text": "## 1. الخلاصة\nدخل الفرد 1106 دولار سنوياً."},
          "missions": {"eco": {"findings": [
              {"value": 1106, "data_year": 2013, "source": "World Bank"}]}},
          "analyst": {"by_category": {}}}
    out = chk(dr)
    assert out and out[0]["check"] == "stale_data_without_year"
    # نفسُ الرقم بسنته المطبوعة قريباً ⇒ سليم.
    dr2 = dict(dr, report={"text": "## 1. الخلاصة\nدخل الفرد 1106 دولار "
                                   "وفق بيانات 2013."})
    assert chk(dr2) == []
    # ودليلٌ متقادِمٌ **لا يذكره المتن** لا يُلام عليه التقرير.
    dr3 = dict(dr, report={"text": "## 1. الخلاصة\nالتوصية: تمهّل."})
    assert chk(dr3) == []


def test_c3_gate_catches_observation_date_equal_to_the_run_date():
    from silk_quality_gate import \
        _check_observation_date_equals_run_date as chk
    same = {"date": "2026-09-16", "deep_research": {
        "report": {"text": "تاريخ الرصد 2026-09-16 لسعر الرف."}}}
    assert chk(same) and chk(same)[0]["check"] == \
        "observation_date_equals_run_date"
    diff = {"date": "2026-09-16", "deep_research": {
        "report": {"text": "تاريخ الرصد 2024-03-01 لسعر الرف."}}}
    assert chk(diff) == []


def test_c3_new_rules_fire_once_on_the_canonical_set_and_it_is_a_true_positive():
    """شرطُ القبول مع **استثناءٍ واحدٍ مُعلَن**: إطلاقةٌ حقيقية لا كاذبة.

    مدوّنةُ اليمن تذكر «دخل الفرد 1106 دولار» من بيانات 2013 في الخلاصة
    التنفيذية بلا سنةٍ مطبوعة — وهو **العيبُ المرصود حرفياً** («بيانات
    2018 بلا سنةٍ مطبوعة»). القاعدةُ صادقة، والمدوّنةُ مجمّدةٌ بقرار مالك
    فلا تُعدَّل نثراً لتمرير موجة. الإطلاقةُ مُعدَّدةٌ هنا كي لا تنمو صامتة.
    """
    import silk_quality_gate as G
    import silk_render
    from tools import gen_verdict_baseline as B
    new = ("score_format_drift", "amount_without_currency",
           "stale_data_without_year", "observation_date_equals_run_date")
    hits: dict = {}
    with block_network():
        for key in _negative_keys():
            mod, fn = B.CANONICAL_BLOBS[key]
            blob = getattr(importlib.import_module(mod), fn)()
            out = G.run_quality_gate(silk_render.build_view(blob))
            got = sorted(f["check"] for f in out["findings"]
                         if f["check"] in new)
            if got:
                hits[key] = got
    assert hits == {"yemen": ["stale_data_without_year"]}, hits


def test_c3_rules_are_wired_and_warning_only():
    import inspect

    import silk_quality_gate as G
    src = inspect.getsource(G.run_quality_gate)
    for fn in ("_check_score_format_drift", "_check_amount_without_currency",
               "_check_stale_data_without_year",
               "_check_observation_date_equals_run_date"):
        assert fn in src, fn
    for check in ("score_format_drift", "amount_without_currency",
                  "stale_data_without_year",
                  "observation_date_equals_run_date"):
        assert check not in G.FAIL_TRIGGER_CHECKS, check


# ════════════ الصنف ٤ — انزياحُ التسمية والمصطلح ════════════

def test_c4_one_authority_two_names_is_caught():
    """**العيبُ المرصود حرفياً**: «الحكومة الحوثية» و«السلطات الحوثية»."""
    from silk_quality_gate import _check_authority_naming_drift as chk
    dr = {"report": {"text": "## 7. التنظيم والوصول للسوق\n"
                             "فرضت الحكومة الحوثية قيوداً على الاستيراد. "
                             "وتشترط السلطات الحوثية تصريحاً مسبقاً."}}
    out = chk({}, dr)
    assert out and out[0]["check"] == "authority_naming_drift"
    # البلاغُ يحمل الهجاءَ الأصليّ لا المُطبَّع («الحكمه» خطأٌ في ذاته).
    assert "الحكومة الحوثية" in out[0]["note"]
    assert "السلطات الحوثية" in out[0]["note"]


def test_c4_bare_government_is_caught_only_when_two_authorities_exist():
    """«الحكومة» عارية مبهمةٌ **حين تتعدّد الجهات** لا دائماً — الفرقُ عمليّ:
    كلُّ جهةٍ منفذٌ وقيودٌ ورسومٌ مختلفة."""
    from silk_quality_gate import _check_authority_naming_drift as chk
    two = {"report": {"text": "## 7. التنظيم\nتفرض حكومة صنعاء رسماً، "
                              "وتشترط سلطات عدن تصريحاً. وتفرض الحكومة "
                              "قيداً ثالثاً."}}
    out = chk({}, two)
    assert out and "بلا نسبةٍ" in out[0]["note"]
    # جهةٌ واحدةٌ مسمّاة ⇒ لا إبهام.
    one = {"report": {"text": "## 7. التنظيم\nتفرض حكومة صنعاء رسماً."}}
    assert chk({}, one) == []


def test_c4_accusative_objects_are_not_mistaken_for_authorities():
    """تضييقٌ جاء من القياس: «تفرض الحكومة قيداً» — «قيداً» مفعولُ الفعل لا
    نسبةُ جهة، والتنوينُ إشارةٌ صرفيةٌ عربيةٌ حقيقية. وبلا هذا التضييق
    كانت القاعدةُ تعدّ ثلاثَ «جهات» في جملةٍ فيها جهتان."""
    from silk_quality_gate import _check_authority_naming_drift as chk
    objects = {"report": {"text": "## 7. التنظيم\nتفرض الحكومة قيداً "
                                  "وتشترط السلطة تصريحاً ورسماً."}}
    assert chk({}, objects) == []
    generic = {"report": {"text": "## 7. التنظيم\nتشترط الجهة المعنية "
                                  "تصريحاً، وتفرض السلطات المحلية رسماً."}}
    assert chk({}, generic) == []


def test_c4_authority_config_is_validated_when_present():
    """تهيئةٌ مُدقَّقة لا تفريعٌ في الشيفرة: سوقٌ مُعلَنةٌ متعدّدةَ السلطات
    لا تُقبَل بأقلّ من تسميتين موثَّقتين — وإلّا صار الإعلانُ ادّعاءً."""
    import copy

    import silk_profiles as P
    assert P.validate_all() == [], "الأسواقُ المُهيَّأة صارت غيرَ صالحة"
    base = P.market_profile("QAT")
    assert base, "مدخلُ QAT مفقود"
    cited = {"source_url": "https://example.org", "review_date": "2026-09-16"}
    bad = copy.deepcopy(base)
    bad["multi_authority"] = dict(cited, value=True)
    bad["authorities"] = [dict(cited, value="جهة أ")]
    errs = P.validate_market("QAT", bad)
    assert any("multi_authority=true" in x for x in errs), errs
    # تسميةٌ بلا استشهاد مرفوضةٌ كأيّ حقيقةٍ أخرى.
    uncited = copy.deepcopy(base)
    uncited["authorities"] = [{"value": "جهة أ"}]
    assert any("authorities[0].source_url" in x
               for x in P.validate_market("QAT", uncited))
    # وحضورُ التسميتين موثَّقتين يمرّ.
    good = copy.deepcopy(base)
    good["multi_authority"] = dict(cited, value=True)
    good["authorities"] = [dict(cited, value="جهة أ"), dict(cited, value="جهة ب")]
    assert P.validate_market("QAT", good) == []


def test_c4_english_activity_labels_are_translated_at_the_display_boundary():
    """«Import export company» و«Food broker» في جدولٍ عربيّ — العيبُ المرصود.

    الترجمةُ عند حدِّ العرض لا في طبقة الجلب (البيانات الخام كما هي)، ومن
    جدولٍ واحد. وغيرُ المُدرَجة **تمرّ بحالها** فيلتقطها حاجزُ اتساق اللغة
    بدل أن تُستَر بترجمةٍ مختلَقة — نفسُ منطقِ العملة في الصنف ٣.
    """
    from silk_reports import _clean_leads
    from silk_style_contract import activity_label_ar
    assert activity_label_ar("Import export company") == "شركة استيراد وتصدير"
    assert activity_label_ar("Food broker") == "وسيط أغذية"
    assert activity_label_ar("IMPORT_EXPORT_COMPANY") == "شركة استيراد وتصدير"
    assert activity_label_ar("Nut Roastery") == "Nut Roastery", "لا ترجمةَ مخمَّنة"
    rows = [{"name": "شركة الخليج للتجارة", "category": "Import export company",
             "address": "الكويت", "phone": "+96512345678"},
            {"name": "مؤسسة النور", "category": "Food broker",
             "address": "الكويت", "phone": "+96512345679"}]
    out = _clean_leads(rows, {"market": {"iso3": "KWT", "name_en": "Kuwait",
                                         "name_ar": "الكويت"}})
    assert [r["category"] for r in out] == ["شركة استيراد وتصدير",
                                            "وسيط أغذية"]


def test_c4_english_activity_label_is_already_blocked_by_the_language_gate():
    """عيبٌ واحدٌ بحارسٍ واحد: القاعدةُ الحاجزة القائمة تكفي، فلا ثانيةَ له.

    يُقاس لا يُفترَض — وإلّا صار «مغطّى» ادّعاءً كادّعاءات السجلّ التي
    صحّحها الدرس 186."""
    from silk_quality_gate import _check_language_consistency
    table = ("## 12. قائمة مستوردين وموزعين\n"
             "| الاسم | النشاط |\n|---|---|\n"
             "| شركة الخليج | Import export company |\n")
    out = _check_language_consistency(table, "ar", {})
    assert out and out[0]["check"] == "language_consistency"
    import silk_quality_gate as G
    assert "language_consistency" in G.FAIL_TRIGGER_CHECKS, "الحارسُ حاجز"


def test_c4_definitions_render_only_when_the_term_appears():
    """تعريفٌ ثابتٌ من سطرٍ واحد **يُعرَض حين يَرِد المصطلح** — لا مسرداً
    كاملاً في كلّ تقرير، ولا شرحاً مقحوماً وسطَ الجملة."""
    import silk_render
    text = ("واردات المرآة تفوق البيانات المباشرة، وسعر الحدود 2.1 دولار، "
            "ونسبة التحقّق 64%.")
    _, gloss = silk_render._apply_merchant_language(text)
    terms = {g["term"] for g in gloss}
    assert {"المرآة", "البيانات المباشرة", "سعر الحدود"} <= terms, terms
    assert any("التحق" in t for t in terms)
    # هجاءان لمصطلحٍ واحد لا يُنتجان تعريفين في مسردٍ واحد.
    glosses = [g["gloss"] for g in gloss]
    assert len(glosses) == len(set(glosses)), glosses
    # ونصٌّ بلا أيّ مصطلحٍ لا يحمل مسرداً.
    _, empty = silk_render._apply_merchant_language(
        "التوصية: ادخل بشحنة تجريبية بحجم 2 طن.")
    assert empty == []


def test_c4_gate_catches_a_term_used_without_its_definition():
    from silk_quality_gate import \
        _check_defined_term_without_definition as chk
    undef = {"report": {"text": "## 3. السوق\nبيانات المرآة أعلى من "
                                "البيانات المباشرة."}, "glossary": []}
    out = chk({}, undef)
    assert out and out[0]["check"] == "defined_term_without_definition"
    defined = dict(undef, glossary=[{"term": "بيانات المرآة", "gloss": "…"},
                                    {"term": "البيانات المباشرة",
                                     "gloss": "…"}])
    assert chk({}, defined) == []


def test_c4_zero_false_positives_across_every_canonical_blob():
    import silk_quality_gate as G
    import silk_render
    from tools import gen_verdict_baseline as B
    new = ("authority_naming_drift", "defined_term_without_definition")
    with block_network():
        for key in _negative_keys():
            mod, fn = B.CANONICAL_BLOBS[key]
            blob = getattr(importlib.import_module(mod), fn)()
            out = G.run_quality_gate(silk_render.build_view(blob))
            hits = [f["note"] for f in out["findings"]
                    if f["check"] in new]
            assert hits == [], (key, hits)


def test_c4_rules_are_wired_and_warning_only():
    import inspect

    import silk_quality_gate as G
    src = inspect.getsource(G.run_quality_gate)
    assert "_check_authority_naming_drift" in src
    assert "_check_defined_term_without_definition" in src
    for check in ("authority_naming_drift",
                  "defined_term_without_definition"):
        assert check not in G.FAIL_TRIGGER_CHECKS, check


def test_c4_authority_rule_has_an_english_mirror():
    """قفلُ التكافؤ (`test_no_undeclared_arabic_only_check_survives`) التقطَ
    أنّ الصيغةَ الأولى عربيةُ المِجَسّ وحدها — فتخمُد صامتةً على تقريرٍ
    إنجليزيّ والمشغّلُ يقرأ PASS ويظنّه قياساً.

    والعيبُ قائمٌ بالإنجليزية أيضاً («the Houthi government» / «the Houthi
    authorities»)، فالمرآةُ أصدقُ من إعلانِ خمود. والبلاغُ بترتيبٍ طبيعيّ
    إنجليزياً لا مقلوباً."""
    from silk_quality_gate import _check_authority_naming_drift as chk
    drift = {"report": {"text": "## 7. Regulation\nThe Houthi government "
                                "imposed import limits. The Houthi "
                                "authorities require a prior permit."}}
    out = chk({}, drift, "en")
    assert out and out[0]["check"] == "authority_naming_drift"
    assert "Houthi government" in out[0]["note"]
    assert "Houthi authorities" in out[0]["note"]
    bare = {"report": {"text": "## 7. Regulation\nThe Sanaa authorities "
                               "charge a fee and the Aden government "
                               "requires a permit. The government also "
                               "adds a levy."}}
    assert chk({}, bare, "en")
    single = {"report": {"text": "## 7. Regulation\nThe Sanaa authorities "
                                 "charge a fee on shipments."}}
    assert chk({}, single, "en") == []


# ════════════════════ الصنف ٥ — التكرار ════════════════════

def test_c5_the_same_fact_explained_in_two_sections_is_caught():
    """**العيبُ المرصود**: القرارُ التنظيميّ نفسُه مشروحٌ في خمسة أقسام.

    **إعادةُ صياغةٍ** لا تكرارٌ حرفيّ — فلا يبلغها `_check_repeated_span`
    (تكرارُه حرفيٌّ ونطاقُه الفقرةُ الواحدة)."""
    from silk_quality_gate import _check_cross_section_near_duplicate as chk
    dup = ("## 7. التنظيم والوصول للسوق\nيشترط قرارُ الإدراج الأوروبيُّ "
           "تسجيلَ المنشأة لدى الجهة المختصة قبل أيِّ شحنةٍ من أصلٍ "
           "حيواني.\n\n"
           "## 9. تقييم المخاطر\nتسجيلُ المنشأة لدى الجهة المختصة شرطٌ "
           "يشترطه قرارُ الإدراج الأوروبيُّ قبل أيِّ شحنةٍ من أصلٍ حيواني.\n")
    out = chk(dup)
    assert out and out[0]["check"] == "cross_section_near_duplicate"
    # البلاغُ يسمّي القسمين كي يعرف المشغّلُ أيَّهما يُختصَر.
    assert "التنظيم والوصول للسوق" in out[0]["note"]
    assert "تقييم المخاطر" in out[0]["note"]


def test_c5_detail_inside_one_section_is_not_repetition():
    """تفصيلٌ متدرّجٌ داخل قسمِه مشروع — العيبُ عبورُ الأقسام."""
    from silk_quality_gate import _check_cross_section_near_duplicate as chk
    same_section = ("## 7. التنظيم\nيشترط قرارُ الإدراج تسجيلَ المنشأة لدى "
                    "الجهة المختصة قبل الشحن.\nوتسجيلُ المنشأة لدى الجهة "
                    "المختصة يشترطه قرارُ الإدراج قبل الشحن.\n")
    assert chk(same_section) == []
    distinct = ("## 4. الديناميكيات\nانكمش السوق 22% خلال أربع سنوات "
                "متتالية بحسب بيانات الجمارك.\n\n"
                "## 5. المستهلك\nارتفع الطلبُ على العبوات الصغيرة في المدن "
                "الكبرى وفق مؤشرات البحث.\n")
    assert chk(distinct) == []


def test_c5_similarity_threshold_separates_measured_negatives_from_the_defect():
    """العتبةُ مُعايَرةٌ **بفصلٍ مقيس** لا بسؤالٍ أضعف.

    القيمةُ الأولى (0.55) قِيست بـ«هل يبلغ زوجٌ 0.45؟» فكانت **تفوّت العيبَ
    الحقيقيّ** (0.538) — قياسٌ ناقصٌ يُطمئن وهو أخطرُ من غيابه. القياسُ
    الكامل: أعلى تشابهٍ في المدوّنات السالبة، وتشابهُ العيب في الموجَبة.
    """
    import silk_quality_gate as G
    import silk_render
    from tools import gen_verdict_baseline as B

    def _max_sim(key: str) -> float:
        mod, fn = B.CANONICAL_BLOBS[key]
        blob = getattr(importlib.import_module(mod), fn)()
        text = G._split_off_appendix(
            (silk_render.build_view(blob).get("deep_research") or {}
             ).get("report", {}).get("text") or "")
        sents = G._xsec_sentences(text)
        best = 0.0
        for i in range(len(sents)):
            for j in range(i + 1, len(sents)):
                if sents[i][0] == sents[j][0]:
                    continue
                a, b = sents[i][2], sents[j][2]
                union = len(a | b)
                if union:
                    best = max(best, len(a & b) / union)
        return best

    with block_network():
        worst_negative = max(_max_sim(k) for k in _negative_keys())
        positive = max(_max_sim(k) for k in _POSITIVE_FIXTURES)
    assert worst_negative <= 0.35, worst_negative
    assert positive >= 0.50, positive
    assert worst_negative < G._XSEC_SIM_DEFAULT < positive, (
        worst_negative, G._XSEC_SIM_DEFAULT, positive)


def test_c5_connector_repeated_inside_one_paragraph_is_caught():
    """«وهذا يعني» في كلّ فقرةٍ تقريباً — عيبٌ في **التوزيع** لا في المجموع.

    عدّادُ `_check_style` مستنديٌّ بعتبةِ خمس: مرّتان في فقرةٍ ومرّةٌ في
    فقرتين = أربعٌ، فيمرّ."""
    from silk_quality_gate import \
        _check_connector_repeated_in_paragraph as chk
    twice = ("## 4. ديناميكيات السوق\nانكمش السوق 22% وهذا يعني ضيقَ "
             "الفرصة، وارتفع سعرُ الرف وهذا يعني هامشاً أوسع.\n")
    out = chk(twice)
    assert out and out[0]["check"] == "connector_repeated_in_paragraph"
    assert "ديناميكيات السوق" in out[0]["note"], \
        "القسمُ يُنسَب لعنوانه لا «قبل أول عنوان»"
    once = ("## 4. الديناميكيات\n\nانكمش السوق 22% وهذا يعني ضيقَ الفرصة.\n\n"
            "## 5. المستهلك\n\nارتفع الطلبُ على العبوات الصغيرة.\n")
    assert chk(once) == []


def test_c5_connector_rule_has_an_english_mirror_and_skips_tables():
    from silk_quality_gate import \
        _check_connector_repeated_in_paragraph as chk
    en = ("## 4. Dynamics\n\nThe market shrank 22%, which means a narrower "
          "window, and shelf prices rose, which means a wider margin.\n")
    assert chk(en, "en")
    assert chk("## 4. Dynamics\n\nThe market shrank 22%, which means a "
               "narrower window.\n", "en") == []
    # خليّةُ جدولٍ ليست فقرةَ نثر.
    assert chk("## 6. الجدول\n| الجانب | وهذا يعني | وهذا يعني |\n"
               "|---|---|---|\n") == []


def test_c5_connector_list_is_one_source_read_by_prompt_and_gate():
    """قاعدةٌ تحظر رابطاً لا يعدّه فحصٌ أمنيةٌ لا قاعدة."""
    import inspect

    import silk_quality_gate as G
    import silk_style_contract as S
    assert "وهذا يعني" in S.REPEATED_CONNECTORS
    assert "this means" in S.REPEATED_CONNECTORS_EN
    for name in ("WRITER_STYLE_CONTRACT", "ACADEMIC_WRITER_CONTRACT"):
        assert S.SINGLE_EXPLANATION_RULE in getattr(S, name), name
    for name in ("WRITER_STYLE_CONTRACT_EN", "ACADEMIC_WRITER_CONTRACT_EN"):
        assert S.SINGLE_EXPLANATION_RULE_EN in getattr(S, name), name
    gate = inspect.getsource(G._check_connector_repeated_in_paragraph)
    assert "REPEATED_CONNECTORS" in gate
    # والقاعدةُ تسمّي «وهذا يعني» صريحاً في نصّها.
    assert "وهذا يعني" in S.SINGLE_EXPLANATION_RULE


def test_c5_zero_false_positives_across_every_canonical_blob():
    import silk_quality_gate as G
    import silk_render
    from tools import gen_verdict_baseline as B
    new = ("cross_section_near_duplicate",
           "connector_repeated_in_paragraph")
    with block_network():
        for key in _negative_keys():
            mod, fn = B.CANONICAL_BLOBS[key]
            blob = getattr(importlib.import_module(mod), fn)()
            out = G.run_quality_gate(silk_render.build_view(blob))
            hits = [f["note"] for f in out["findings"]
                    if f["check"] in new]
            assert hits == [], (key, hits)


def test_c5_rules_are_wired_and_warning_only():
    import inspect

    import silk_quality_gate as G
    src = inspect.getsource(G.run_quality_gate)
    assert "_check_cross_section_near_duplicate" in src
    assert "_check_connector_repeated_in_paragraph" in src
    for check in ("cross_section_near_duplicate",
                  "connector_repeated_in_paragraph"):
        assert check not in G.FAIL_TRIGGER_CHECKS, check


# ══════ المراجعةُ الذاتية بعد الجولة الأولى (أمر المالك) — سوقان جديدان ══════
#
# «بعد كل جولة ولّد تقريرين لسوقين جديدين وراجعهما بنفسك؛ ما تجده يُضاف
# كفئة جديدة بنفس الأسلوب.» — مصرُ (عملةٌ محلّية وفئةٌ واسعة) ونيجيريا
# (ضعفُ تبليغٍ مُعلَن ⇒ مرآة). ما وُجد: ثلاثُ إطلاقاتٍ صحيحةٍ لقواعد الجولة،
# وإنذاران كاذبان فيها، وعائلةٌ جديدة (الصنف ١١) في فحصٍ **حاجب**.


def test_selfreview_egypt_is_the_positive_fixture_for_the_first_round():
    """التثبيتةُ **الموجَبة**: نثرُ كاتبٍ طبيعيّ يحمل ثلاثَ عائلاتٍ مرصودة.

    الإحدى عشرةُ الأخرى سالبةٌ (صفرُ إطلاقة) — وقاعدةٌ لا تُطلِق إلّا على
    مثالٍ مصنوعٍ في اختبارٍ لا يُعرَف أنها تصطاد شيئاً في الإنتاج."""
    import silk_quality_gate as G
    import silk_render
    from tools import gen_verdict_baseline as B
    mod, fn = B.CANONICAL_BLOBS["egypt_olive_oil"]
    with block_network():
        blob = getattr(importlib.import_module(mod), fn)()
        out = G.run_quality_gate(silk_render.build_view(blob))
    got = {f["check"] for f in out["findings"]}
    assert "authority_naming_drift" in got, "«الحكومة» عاريةً بجوار جهتين"
    assert "connector_repeated_in_paragraph" in got, "«وهذا يعني» مرّتين"
    assert "template_interpolation" in got, "«بالحصة السعودية»"
    assert "cross_section_near_duplicate" in got, \
        "شرطُ التسجيل مشروحٌ في الخلاصة والتنظيم معاً (الصنف ٥)"
    echo = [f["note"] for f in out["findings"]
            if f["check"] == "template_interpolation"]
    assert any("السعودية" in n for n in echo), echo


def test_selfreview_only_egypt_fires_on_the_first_round_rules():
    """شرطُ القبول على **اثنتي عشرة** مدوّنة: التثبيتةُ الموجَبة وحدها،
    زائداً إطلاقةَ اليمن الحقيقية المُعدَّدة في الصنف ٣."""
    import silk_quality_gate as G
    import silk_render
    from tools import gen_verdict_baseline as B
    mine = ("reader_language_leak", "template_interpolation",
            "score_format_drift", "amount_without_currency",
            "stale_data_without_year", "observation_date_equals_run_date",
            "authority_naming_drift", "defined_term_without_definition",
            "cross_section_near_duplicate",
            "connector_repeated_in_paragraph")
    hits: dict = {}
    with block_network():
        for key in sorted(B.CANONICAL_BLOBS):
            mod, fn = B.CANONICAL_BLOBS[key]
            blob = getattr(importlib.import_module(mod), fn)()
            out = G.run_quality_gate(silk_render.build_view(blob))
            got = sorted({f["check"] for f in out["findings"]
                          if f["check"] in mine})
            if got:
                hits[key] = got
    assert hits == {
        # العتبةُ بعد المعايرة الصحيحة (0.45) تلتقط أيضاً شرطَ التسجيل
        # المشروحَ في الخلاصة والتنظيم معاً — رابعُ عيبٍ في التثبيتة الموجَبة.
        "egypt_olive_oil": ["authority_naming_drift",
                            "connector_repeated_in_paragraph",
                            "cross_section_near_duplicate",
                            "template_interpolation"],
        "yemen": ["stale_data_without_year"],
    }, hits


def test_c11_a_disclosed_mirror_gap_is_not_a_blocking_contradiction():
    """**الصنف ١١ (أ)** — تمييزُ المباشر عن المرآة عقدٌ محفوظ.

    سجلُّ الأدلة يحمل قراءتين مشروعتين لمؤشرٍ واحد (تصريحٌ مباشر + مرآة)،
    فكانت الحلقةُ تقارن قراءةَ المتن بالقراءةِ **الأخرى** وتُفشِل `FAIL`
    تقريراً يفعل بالضبط ما يُطلَب منه: يُفصِح عن الفجوة صريحاً. وذكرُ
    قراءتين بلا تمييزٍ عيبٌ حقيقيّ لكنه عائلةُ **الصنف ٦**."""
    from silk_quality_gate import \
        _check_evidence_body_numeric_consistency as chk
    dr = {"report": {"text": "## 3. السوق\nالتصريح المباشر 1.2 مليون دولار، "
                             "وبيانات المرآة 9.6 مليون دولار — فجوة ثمانية "
                             "أضعاف لم تُحسم."},
          "missions": {"trade_flow": {"findings": [
              {"value": 1_200_000, "note": "واردات مصرَّحة 2023"},
              {"value": 9_600_000, "note": "مرآة صادرات الشركاء 2023"}]}},
          "analyst": {"by_category": {}}}
    assert chk(dr) == []


def test_c11_b_per_capita_is_not_compared_against_a_total():
    """**الصنف ١١ (ب)** — عوالمُ مختلفة لا تُقارَن.

    «نصيب الفرد من الواردات 0.005 دولار» يحمل كلمة «الواردات» فيدخل
    المِجَسّ، فتُقارَن نسبةٌ للفرد بإجماليٍّ ⇒ 240,000,000× ⇒ **حجب**.
    و`_check_cross_universe_ratio` يعرف أصلاً أنّ «نصيب الفرد» عالمٌ آخر —
    فالمعرفةُ كانت في البوابة ولم تبلغ هذا الفحص."""
    from silk_quality_gate import \
        _check_evidence_body_numeric_consistency as chk
    dr = {"report": {"text": "## 4. الديناميكيات\nواردات 1.2 مليون دولار، "
                             "ونصيب الفرد من الواردات 0.005 دولار."},
          "missions": {"trade_flow": {"findings": [
              {"value": 1_200_000, "note": "واردات 2023"}]}},
          "analyst": {"by_category": {}}}
    assert chk(dr) == []


def test_c11_c_a_real_contradiction_still_blocks():
    """التضييقُ لا يُعطِّل الحاجز: رقمٌ **غيرُ مسنودٍ** في الأدلة ما زال
    يُفشِل — وإلّا صار الإصلاحُ إسكاتاً."""
    from silk_quality_gate import \
        _check_evidence_body_numeric_consistency as chk
    dr = {"report": {"text": "## 3. السوق\nواردات السوق 42 مليون دولار."},
          "missions": {"trade_flow": {"findings": [
              {"value": 1_200_000, "note": "واردات 2023"}]}},
          "analyst": {"by_category": {}}}
    out = chk(dr)
    assert out and out[0]["check"] == "evidence_body_numeric_contradiction"
    assert out[0]["repairable"] is False


def test_c11_d_sub_unit_amounts_are_not_reported_as_zero():
    """**الصنف ١١ (د)** — بلاغُ البوابة سطحُ قراءةٍ أيضاً: `{v:,.0f}` كان
    يطبع «0$» لمبلغٍ دون الوحدة، فيقرأ المشغّلُ بلاغاً بلا معنى."""
    from silk_quality_gate import _fmt_gate_num
    assert _fmt_gate_num(0.005) == "0.01" or "0.005" in _fmt_gate_num(0.005)
    assert _fmt_gate_num(1_200_000) == "1,200,000"


def test_c11_nigeria_blob_is_no_longer_blocked_by_a_false_contradiction():
    """حارسُ انحدارٍ على المدوّنة نفسِها: كانت `FAIL` بإطلاقتين كاذبتين من
    فحصٍ **حاجب** — وحجبُ تقريرٍ صحيحٍ يمنع تصديرَه للعميل فعلاً."""
    import silk_quality_gate as G
    import silk_render
    from tools import gen_verdict_baseline as B
    mod, fn = B.CANONICAL_BLOBS["nigeria_dates"]
    with block_network():
        blob = getattr(importlib.import_module(mod), fn)()
        out = G.run_quality_gate(silk_render.build_view(blob))
    got = {f["check"] for f in out["findings"]}
    assert "evidence_body_numeric_contradiction" not in got, got
    assert out["verdict"] != "FAIL", out["verdict"]


def test_selfreview_first_round_false_positives_stay_fixed():
    """الإنذاران الكاذبان اللذان رصدتهما المراجعةُ الذاتية في قواعد الجولة."""
    from silk_quality_gate import _check_template_interpolation as chk
    # (أ) تباينُ «الصغيرة/الكبيرة» تكرارٌ مشروعٌ للموصوف.
    assert chk("## 4. الديناميكيات\nانتقال الطلب إلى العبوات الصغيرة، "
               "وانخفضت حصة العبوات الكبيرة.") == []
    # (ب) نقطتان آخرَ سطرٍ **يتلوه متن** عنوانٌ مشروع.
    assert chk("## 1. الخلاصة\nالشرط الحاجب:\nتسجيل المنتج قبل الشحن.") == []
    # وكلا العيبين المرصودين ما زالا يُلتقَطان.
    assert chk("## 6. المنافسة\nثم السعودية بالحصة السعودية البالغة 10.44%.")
    assert chk("## 3. السوق\nينقصه:")
