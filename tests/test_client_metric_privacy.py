"""الموجة الرابعة — الدرس ٢٥٧: أرقامُ القياس الداخليّ تخرج من نسخة العميل.

client metric privacy: the decision confidence (label + %), the overall score
out of 100, the verification rate and the per-component confidence column
leave the CLIENT surfaces only — behind `SILK_CLIENT_METRIC_PRIVACY`.

**القرار** (المالك، ٢٠٢٦-٠٩-١٧ بعد دراسة ماليزيا المحجوبة): هذه الأرقام «لا
تفيد القارئ وتفتح بابَ التساؤل على أيّ أساسٍ بُنيت وكيف تُحتسَب». وهي بعينها
الحلُّ الجذريّ لعائلة الحجب (الدرس ٢٥٤): نصٌّ لا يحمل تسميةَ ثقةٍ لا يمكن أن
يتناقض معها.

**العقدُ المقفول هنا:**
1. مطفأةً: العرضُ والموجّهُ بايتاً ببايت كما كانا (لا مفتاحَ جديداً).
2. مفعَّلةً: الكاتبُ **لا يستلم** الرقمَ (منعٌ عند المنبع)، وكلُّ سطحِ عميل
   (المنصّة/docx) يقرأ قائمةً **واحدة** من العرض فيُسقِط السطرَ كاملاً.
3. مُصلِحاتُ الثقة الخام تحذف ولا تُعيد الحقن (الفخُّ المقيس).
4. الفحوصُ التي تقرأ التسميةَ في النثر تبقى قادرةً على الإطلاق على تسريب
   (الدرس ٩٨ — حارسُ «صحيحٌ إن ظهر»)، ومعها فحصٌ جديد «غيابٌ مطلوب».
5. الموجّهُ المبنيُّ فعلاً لا يحمل إبرةً تلتقطها البوّابة (الدرس ١٨٦ + ٢٥٤).
"""
import os
import re

import pytest

import silk_quality_gate as Q
import silk_render as R

_FLAGS = ("SILK_CLIENT_METRIC_PRIVACY", "SILK_IMPORTS_SPOTLIGHT",
          "SILK_REPORT_CHARTS", "SILK_CONFIDENCE_DISCIPLINE")

_PILLARS_GAP = {"market": {"value": None}, "competition": {"value": 0.52},
                "profit": {"value": None}}
_DECISION = {"schema": "silk.decision/v1", "verdict": "CONDITIONAL-GO",
             "score": 0.64, "confidence": 0.80, "coverage": 0.8,
             "weights_option": "A", "conditions": [], "pillars": _PILLARS_GAP}
_REPORT = ("## 1. الخلاصة التنفيذية\nنوصي بدخولٍ مشروط.\n\n"
           "## 3. نظرة عامة على السوق وحجمه\nواردات 2024 بلغت 89.4 مليون دولار.\n\n"
           "## 10. التوصيات الاستراتيجية\nالحكم دخول مشروط لأن جانب الربحية "
           "لا نعرفه بعد.\n")


def _result() -> dict:
    """نتيجةُ بحثٍ عميق بالشكل الذي يُلحِقه `_attach_deep_market_row` فعلاً —
    صفُّ سوقٍ واحد يحمل `decision` ومكوّناتٍ، لا مدوّنةٌ مُعاد تركيبها."""
    return {
        "market": {"name_ar": "ماليزيا", "name_en": "Malaysia", "iso3": "MYS"},
        "product": "قهوة محمصة", "hs_code": "090121",
        "deep_research": {
            "missions": {},
            "verdict": {"verdict": "CONDITIONAL-GO", "confidence": 0.80,
                        "contributing_findings": [1] * 12},
            "report": {"text": _REPORT}},
        "markets": [{
            "country": "ماليزيا", "iso3": "MYS", "total_score": 0.64,
            "confidence": 0.80, "rank": 1, "deep": True,
            "components": {"market_size": {
                "value": 51358600.874, "source": "UN Comtrade",
                "confidence": 0.9, "data_year": 2021, "note": ""}},
            "decision": dict(_DECISION)}]}


def _clear(monkeypatch) -> None:
    for f in _FLAGS:
        monkeypatch.delenv(f, raising=False)


def _writer_prompt(monkeypatch) -> str:
    """الموجّهُ الذي يستلمه الكاتبُ فعلاً — يُقتنَص من نداء `_call` (الدرس ١٨٦)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-called")
    import silk_ai_judge as J
    seen: dict = {}

    def _fake_call(system, user, *a, **k):
        seen.setdefault("user", user)
        return ""

    monkeypatch.setattr(J, "_call", _fake_call)
    J.deep_report({}, "مسوّدة المحلل", _result()["deep_research"]["verdict"],
                  "قهوة محمصة", "Malaysia", hs_code="090121",
                  entry_decision=dict(_DECISION))
    assert seen.get("user")
    return seen["user"]


# ── (١) مطفأةً: لا حرفَ يتغيّر ─────────────────────────────────────────────

def test_flag_off_view_and_prompt_are_byte_identical(monkeypatch):
    _clear(monkeypatch)
    v = R.build_view(_result())
    assert "client_hidden_metrics" not in v
    assert "client_hidden_metrics" not in (v["decision"].get("basis") or {})
    assert "imports" not in v["deep_research"]
    assert "charts" not in v["deep_research"]
    p_unset = _writer_prompt(monkeypatch)
    monkeypatch.setenv("SILK_CLIENT_METRIC_PRIVACY", "0")
    assert _writer_prompt(monkeypatch) == p_unset
    assert "الثقة: عالية (80%)" in p_unset
    assert "تخترع نسبة ثقة" in p_unset


# ── (٢) مفعَّلةً: قائمةٌ واحدة يقرؤها كلُّ سطح ─────────────────────────────

def test_hidden_list_is_declared_once_and_reaches_the_view(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_CLIENT_METRIC_PRIVACY", "1")
    v = R.build_view(_result())
    assert v["client_hidden_metrics"] == list(R.CLIENT_HIDDEN_METRICS)
    assert set(v["client_hidden_metrics"]) == {
        "score", "confidence", "verification", "component_confidence"}
    basis = v["decision"]["basis"]
    assert basis["client_hidden_metrics"] == v["client_hidden_metrics"]
    # **لا مفتاحَ يُحذَف ولا رقمَ يتغيّر**: المحرّكُ والبوّابةُ يقرؤون كما هم.
    assert basis["score_pct"] == 64 and basis["confidence_pct"] == 80
    assert basis.get("score_line")
    assert v["markets"][0]["confidence"] == 0.80
    assert v["markets"][0]["components_detail"][0]["confidence"] == 0.9


def test_client_docx_carries_none_of_the_four_metrics(monkeypatch, tmp_path):
    pytest.importorskip("docx")
    from tests.conftest import docx_all_text
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_HERMETIC", "1")
    monkeypatch.setenv("SILK_CLIENT_METRIC_PRIVACY", "1")
    import silk_reports as SR
    v = R.build_view(_result())
    out = SR.render_client_docx(v, str(tmp_path / "client.docx"))
    text = docx_all_text(out)
    assert v["decision"]["basis"]["head"] in text, "أساسُ الحكم نفسُه باقٍ"
    assert "من 100" not in text, "الدرجةُ الكلية وصلت العميل"
    assert not re.search(r"بدرجة ثقة|ثقة (?:عالية|متوسطة|منخفضة)", text)
    assert "مؤشّر تغطية المصادر" not in text, "قسمُ نسبة التحقّق وصل العميل"
    assert not re.search(r"\d{1,3}\s*%\s*من\s*البيانات", text)
    # وبلا الراية يبقى القسمُ والسطرُ كما كانا (عقدُ الحياد).
    monkeypatch.delenv("SILK_CLIENT_METRIC_PRIVACY")
    v0 = R.build_view(_result())
    t0 = docx_all_text(SR.render_client_docx(v0, str(tmp_path / "c0.docx")))
    assert "من 100" in t0


# ── (٣) المنعُ عند المنبع: الكاتبُ لا يستلم الرقم ولا إبرةً ممنوعة ──────────

def test_writer_prompt_has_no_metric_and_no_gate_needle(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_CLIENT_METRIC_PRIVACY", "1")
    prompt = _writer_prompt(monkeypatch)
    assert "الثقة: " not in prompt
    assert "عالية (80%)" not in prompt
    assert "تخترع نسبة ثقة" not in prompt
    assert "الحكم: دخول مشروط" in prompt
    # الدرس ٢٥٤: لا نمطَ حاجبٍ ثابتٍ يُطابِق الموجّهَ المبنيَّ فعلاً.
    for check, (pat_name, _src) in Q.PROSE_LITERAL_BLOCKERS.items():
        assert getattr(Q, pat_name).search(prompt) is None, check
    # ولا إبرةَ الفحص الجديد نفسِه (وإلّا عاقبنا الكاتبَ على نسخ تعليمتنا).
    for pat in Q._CLIENT_METRIC_PROBES:
        m = pat.search(prompt)
        assert m is None, f"الموجّه يحمل إبرةَ الكشف: {m.group(0)!r}"
    for pat in Q._CONF_PCT_RES:
        assert pat.search(prompt) is None
    assert Q._RAW_CONFIDENCE_RE.search(prompt) is None


def test_privacy_wins_over_confidence_discipline(monkeypatch):
    """التوليفة: الانضباطُ مفعَّل والخصوصيةُ مفعَّلة ⇒ لا تسميةَ ولا سقف."""
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_CONFIDENCE_DISCIPLINE", "1")
    monkeypatch.setenv("SILK_CLIENT_METRIC_PRIVACY", "1")
    prompt = _writer_prompt(monkeypatch)
    assert "الثقة: " not in prompt
    assert "سقف تسمية درجة الثقة" not in prompt
    assert Q._HIGH_CONF_RE.search(prompt) is None


# ── (٤) الفخُّ المقيس: المُصلِحُ يحذف ولا يُعيد الحقن ─────────────────────

def test_raw_confidence_sanitizer_strips_instead_of_relabelling(monkeypatch):
    _clear(monkeypatch)
    src = "وفق UN Comtrade (بثقة 0.9) نمت الواردات؛ ثقة: 0.64 للحصة."
    off = R._strip_internal_plumbing(src)
    assert "عالية (90%)" in off, "بلا الراية: إعادةُ الصياغة القائمة"
    monkeypatch.setenv("SILK_CLIENT_METRIC_PRIVACY", "1")
    on = R._strip_internal_plumbing(src)
    assert "ثقة" not in on, on
    assert "%" not in on and "0.9" not in on and "0.64" not in on
    assert "()" not in on and "( )" not in on
    assert "نمت الواردات" in on
    # مراجعة §58 — ثلاثُ حالاتٍ كانت تُخرِج حطاماً: حدُّ الكلمة، وقوسُ استشهادٍ
    # لا يخصّ المقطع، وفاصلةٌ تسبقه داخل القوس.
    a = R._strip_internal_plumbing("درجة الثقة: 0.8 في هذا الحكم.")
    assert "درجة ال" not in a and "في هذا الحكم" in a and "0.8" not in a
    b = R._strip_internal_plumbing("الثقة 0.64 للحصة")
    assert b.strip().startswith("للحصة") and "الل" not in b
    c = R._strip_internal_plumbing(
        "نمت الواردات (المصدر: كومتريد، ثقة 0.9) بقوة.")
    assert c == "نمت الواردات (المصدر: كومتريد) بقوة.", c
    assert Q._RAW_CONFIDENCE_RE.search(a + b + c) is None
    # المرآةُ الإنجليزية: «confidence 0.8» تُحذَف لا تُعرَّب تسميةً.
    en = R._strip_internal_plumbing("Based on Comtrade (confidence 0.8) growth")
    assert "0.8" not in en and "درجة الثقة" not in en


# ── (٥) الدرس ٩٨: القديمُ يُطلِق على تسريب، والجديدُ يطلب الغياب ────────────

def test_presence_conditional_checks_are_real_and_still_fire(monkeypatch):
    import pathlib
    src = pathlib.Path("silk_quality_gate.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'"check":\s*"(\w+)"', src))
    for check, reason in Q.PRESENCE_CONDITIONAL_CHECKS.items():
        assert check in emitted, f"{check}: اسمٌ لا يُصدِره أيُّ فحص"
        assert len(reason) > 20
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_CLIENT_METRIC_PRIVACY", "1")
    assert any(f["check"] == "confidence_band_mismatch"
               for f in Q._check_confidence_band_label("الحكم بثقة عالية (68%)."))
    assert any(f["check"] == "confidence_value_conflict"
               for f in Q._check_confidence_value_conflict(
                   "ثقة منخفضة (50%) في الملخّص، وثقة (80%) في الختام."))
    view = {"markets": [{"entry_decision": dict(_DECISION)}],
            "decision": {"basis": {}},
            "deep_research": {"report": {"text": "دخول مشروط بدرجة ثقة عالية."}}}
    hit = Q._check_high_confidence_with_missing_pillar(view, view["deep_research"])
    assert hit and hit[0]["check"] == "high_confidence_with_missing_pillar"


def test_client_metric_exposure_fires_on_a_leak_and_is_silent_when_clean(monkeypatch):
    _clear(monkeypatch)
    leaked = {"decision": {"basis": {}},
              "brief": ["التوصية: دخول مشروط"],
              "deep_research": {"report": {"text": "قوة الفرصة 64 من 100 "
                                                   "بثقة عالية."},
                                "limits": ["نسبة التحقق 80%"]}}
    assert Q._check_client_metric_exposure(leaked, leaked["deep_research"]) == [], \
        "بلا الراية الأرقامُ معروضةٌ شرعاً — لا فحص"
    monkeypatch.setenv("SILK_CLIENT_METRIC_PRIVACY", "1")
    out = Q._check_client_metric_exposure(leaked, leaked["deep_research"])
    assert out and out[0]["check"] == "client_metric_exposure"
    assert out[0]["repairable"] is True, "تحذيريٌّ — لا حجب جديداً"
    assert "report" in out[0]["note"] and "limits" in out[0]["note"]
    clean = R.build_view(_result())
    assert Q._check_client_metric_exposure(clean, clean["deep_research"]) == []
    # الإنجليزية مرآةٌ لا استثناء.
    en = {"decision": {"basis": {}}, "brief": [],
          "deep_research": {"report": {"text": "We rate it 64 out of 100 with "
                                               "high confidence."}, "limits": []}}
    assert Q._check_client_metric_exposure(en, en["deep_research"])
    # مراجعة §58: نثرٌ تجاريّ سليم لا يُلتقَط — «40 من 100 شركة»، «ثقة عالية بأنّ».
    prose = {"decision": {"basis": {}}, "brief": [],
             "deep_research": {"report": {"text": "استجابت 40 من 100 شركة "
                                                  "للمسح، وهناك ثقة عالية بأنّ "
                                                  "الطلب مستمر."}, "limits": []}}
    assert Q._check_client_metric_exposure(prose, prose["deep_research"]) == []


def test_the_gate_delivers_the_malaysia_shape_with_privacy_on(monkeypatch):
    """نفسُ الشكل الذي حُجب (عمودان أساسيان مجهولان + ٨٠٪) — مع الخصوصية لا
    حاجبَ ثقةٍ ولا تسريبَ مقياس، والحكمُ ليس FAIL بسبب أيٍّ منهما."""
    _clear(monkeypatch)
    monkeypatch.setenv("SILK_CONFIDENCE_DISCIPLINE", "1")
    monkeypatch.setenv("SILK_CLIENT_METRIC_PRIVACY", "1")
    v = R.build_view(_result())
    out = Q.run_quality_gate(v)
    names = {f["check"] for f in out["findings"]}
    assert "high_confidence_with_missing_pillar" not in names
    assert "client_metric_exposure" not in names
    assert "confidence_band_mismatch" not in names


# ── (٦) صفحةُ المنصّة تقرأ القائمةَ من العرض لا من راية ─────────────────────

def test_platform_page_reads_the_hidden_list_from_the_view():
    import pathlib
    page = pathlib.Path("web/platform.html").read_text(encoding="utf-8")
    body = page.split("function viewReportBtn(")[1].split("\nfunction ")[0]
    assert "v.client_hidden_metrics" in body
    # «verification» قسمُ docx وحدَه (لا نظيرَ له في نافذة المنصّة) — الثلاثةُ
    # الباقية تُقرَأ من القائمة نفسِها هنا.
    for m in ("score", "confidence", "component_confidence"):
        assert f'_hide("{m}")' in body, m
    # الدرجةُ المخفيّةُ نصّاً لا تُرسَم بيانياً.
    assert 'mkts.length && !_hide("score")' in body
    # ولا راية تُقرَأ في الصفحة — المصدرُ الواحد هو العرض.
    assert "SILK_CLIENT_METRIC_PRIVACY" not in page
