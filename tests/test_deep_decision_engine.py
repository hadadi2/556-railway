"""الموجة D · الجذر ١ + D-01 + D-04 + P-01 + R-03 — القرارُ يعود إلى محرّكه.

> **العطل** (`docs/ENGINE_AUDIT.md`): الحكمُ الذي يقرؤه المصنعُ على غلاف تقريره
> كان من `JuryCommittee.evaluate` — وهو يفرّع على **نجاح الوكلاء لا على السوق**:
> نجحت البعثاتُ الاثنتا عشرة ⇒ «توصية أولية بالدخول»؛ فشل واحدٌ ⇒ «غير محسومة».
> أي أنّ **مؤشّرَ اكتمالِ بياناتٍ يُقدَّم توصيةً تجارية**.
>
> و`silk_decision` — خمسةُ أعمدة بأوزانٍ A/B وقاعدةٍ معلنة قبل الحكم وحجّةٍ
> مضادّة — موجودٌ ويعمل على `/analyze` ولا يصل مسارَ المصنع إطلاقاً: القدرةُ في
> الشيفرة والغيابُ في المسار الذي يشتريه العميل.

**الجذرُ واحدٌ لا ستّة:** `api.py` يثبّت `markets: []`، و`build_view` يبني كلَّ
ما يتعلّق بالسوق من `markets[0]`. فسقط معاً: محرّكُ القرار · بوّابةُ الأهلية ·
حارسا الدرس ٨٨ · تحذيرُ القِدَم · الأعمدةُ في تقرير العميل.
"""
from __future__ import annotations

import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import silk_deep_pillars as DP                          # noqa: E402
import silk_render                                      # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dr(**missions) -> dict:
    return {"missions": {k: {"findings": v, "failed": False}
                         for k, v in missions.items()}}


def _f(value, note="", **kw):
    return {"value": value, "note": note, **kw}


# ── المُستخرِجُ يقرأ النثرَ كما يقرأ الأرقام ──────────────────────────────

def test_pillar_inputs_are_extracted_from_prose_findings():
    """درسُ الموجة C يسري هنا: البعثاتُ تُعيد جملاً لا أرقاماً.

    استثناءٌ مقصود (البند 1 من أمر إصلاح المحرّك — تقرير #11): مقياسا
    المنافسة (HHI/حصة الأكبر) لم يعودا يُقرآن من النثر إطلاقاً — المدى
    النثريّ (0–10000) يبتلع الحصص (0–100) وقد قلب الحكم 26%→84%؛ مصدرهما
    ملخّص `comtrade_competitors` المُهيكل حصراً، وغيابُه فجوةٌ معلنة."""
    pi = DP.build_pillar_inputs(_dr(
        trade_flow=[_f("واردات السوق 2023 بلغت 42,000,000 دولار", "واردات")],
        competitors=[_f("HHI يقارب 940", "تركّز")]))
    assert pi["market_attractiveness"]["tam_usd"] == 42_000_000.0
    assert pi["competition_intensity"]["hhi"] is None


def test_an_unobserved_input_stays_none_never_zero():
    """عمودٌ بمدخلٍ ناقص يُعيد المحرّكُ تسويةَ أوزانه ويُعلن الشرط.

    ملؤه بصفرٍ يُنتِج درجةً **تبدو محسوبةً وهي مختلَقة** — وهو خرقُ عقد
    التأسيس بشكلٍ أخطر من الغياب، لأنّ الصفرَ يدخل المتوسّط بلا أن يُرى.
    """
    pi = DP.build_pillar_inputs(_dr(trade_flow=[]))
    for key in ("tam_usd", "import_cagr_pct", "saudi_share_pct"):
        assert pi["market_attractiveness"][key] is None, key


def test_a_year_is_never_mistaken_for_a_market_size():
    """«واردات 2023» تحمل رقمين — والسنةُ ليست حجمَ سوق."""
    pi = DP.build_pillar_inputs(_dr(trade_flow=[_f("2023", "واردات 2023")]))
    assert pi["market_attractiveness"]["tam_usd"] is None


def test_a_metric_string_is_not_counted_as_a_named_competitor():
    """«HHI يقارب 940» ليس شركة.

    عدُّه يرفع مدخلَ عمود المنافسة، و`_pillar_competition` يقرؤه إشارةَ
    **تغطية** — فيبدو المشهدُ التنافسيّ مرصوداً أكثر ممّا هو.
    """
    pi = DP.build_pillar_inputs(_dr(competitors=[
        _f("HHI يقارب 940", "تركّز"), _f("حصة أكبر مورّد 32%", "حصة"),
        _f("Albert Heijn", "منافس")]))
    assert pi["competition_intensity"]["named_company_count"] == 1


def test_no_named_competitor_is_none_not_zero():
    """`0` تُقرأ «سوقٌ بلا منافسين» — وهي ادّعاءٌ لم يُرصَد."""
    assert DP.build_pillar_inputs(_dr(competitors=[
        _f("HHI 940", "تركّز")]))["competition_intensity"][
        "named_company_count"] is None


# ── R-03 · بوّابةُ الأهلية بنيويّةٌ لا نصّية ──────────────────────────────

def test_the_eligibility_gate_is_read_from_the_structural_blocker_state():
    """تُقرأ من حالة الحواجز (الموجة C) لا بمطابقة عبارةٍ في نثر."""
    open_hard = DP.build_pillar_inputs(
        _dr(), regulatory={"open_hard": [{"item": "إدراج المنشأة"}],
                           "all": [{}, {}]})["regulatory_fit"]
    assert open_hard["eligibility_gate"] is True
    assert open_hard["entry_requirements_count"] == 2
    clear = DP.build_pillar_inputs(
        _dr(), regulatory={"open_hard": [], "all": [{}]})["regulatory_fit"]
    assert clear["eligibility_gate"] is False


def test_an_open_hard_blocker_surfaces_as_a_leading_condition():
    """الحاجزُ المفتوح يتصدّر شروطَ القرار — لا يُذكَر عرَضاً في الذيل."""
    d = DP.decide_for_deep(
        _dr(trade_flow=[_f("واردات السوق 42,000,000 دولار", "واردات")]),
        regulatory={"open_hard": [{"item": "إدراج المنشأة"}], "all": [{}]})
    assert d and d.get("conditions")
    assert "بوابة أهلية" in d["conditions"][0], (
        "الحاجزُ الصلبُ المفتوح لا يتصدّر الشروط (R-01/R-03)")


# ── D-01 · محرّكٌ واحد، بلا منطقِ قرارٍ ثانٍ ─────────────────────────────

def test_the_decision_comes_from_the_one_engine():
    d = DP.decide_for_deep(_dr(
        trade_flow=[_f("واردات السوق 42,000,000 دولار", "واردات")],
        competitors=[_f("HHI يقارب 940", "تركّز")]))
    assert d["schema"] == "silk.decision/v1", "ليس مُخرَجَ المحرّك الواحد"
    assert d.get("decision_rule"), "قاعدةُ القرار قبل الحكم غائبة"
    assert d.get("counter_case"), "الحجّةُ المضادّة غائبة"


def test_confidence_is_coverage_times_computed_pillars():
    """الثقةُ **معلَنةُ الأساس** لا رقمٌ حدسيّ: تغطيةٌ × نسبةُ الأعمدة المحسوبة.

    البند 2 (أمر إصلاح المحرّك): دون ٣ أعمدة لا درجةَ ولا ثقة أصلاً — فالصيغة
    تُختبَر على حزمةٍ تحسب ٣ أعمدة، ودونها `None` معلَن."""
    comp_summary = {"value": {"year": 2023, "hhi": 2400, "supplier_count": 9,
                              "top_suppliers": [{"partner": "Spain",
                                                 "share": 41.0}]},
                    "source": "UN Comtrade", "confidence": 0.9,
                    "note": "مورّدون، مؤشر تركّز HHI=2400"}
    dr3 = _dr(trade_flow=[_f("واردات السوق 42,000,000 دولار", "واردات")],
              competitors=[comp_summary],
              risk_news=[_f("الاستقرار السياسي -0.4", "الاستقرار السياسي"),
                         _f("LPI 2.9", "LPI")])
    d = DP.decide_for_deep(dr3)
    assert d["confidence"] == round(
        DP.coverage_of(dr3) * (5 - len(d["missing_pillars"])) / 5, 2)
    # دون الحدّ: لا ثقةَ تُطبَع (كانت تُحسَب حتى بلا درجة — ثغرة تدقيق الامتناع)
    d1 = DP.decide_for_deep(_dr(
        trade_flow=[_f("واردات السوق 42,000,000 دولار", "واردات")]))
    assert d1["confidence"] is None and d1["score"] is None


def test_a_failed_mission_lowers_coverage_honestly():
    dr = _dr(trade_flow=[_f(1, "واردات")])
    dr["missions"]["risk_news"] = {"findings": [], "failed": True}
    assert DP.coverage_of(dr) == 0.5


def test_the_extractor_holds_no_decision_logic():
    """**حارسٌ بنيويّ:** لا عتباتِ حكمٍ ولا أوزانَ ولا تسمياتِ حكمٍ هنا.

    نسخُ منطق القرار كان سيُنتِج محرّكاً موازياً — وهو ما تحظره «حكمٌ واحد».
    """
    src = io.open(os.path.join(_ROOT, "silk_deep_pillars.py"),
                  encoding="utf-8").read()
    body = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    for banned in ("GO", "NO-GO", "CONDITIONAL", "WEIGHT", "verdict ="):
        assert banned not in body, f"منطقُ قرارٍ تسرّب إلى المُستخرِج: {banned}"
    tree = ast.parse(src)
    assert any(isinstance(n, ast.ImportFrom) or isinstance(n, ast.Import)
               for n in ast.walk(tree)), "لا استيراد"
    # المحرّكُ يُستورَد كسولاً داخل الدالّة — لا يُعاد تعريفُ `decide` هنا.
    assert "def decide(" not in src, "أُعيد تعريفُ `decide` — محرّكٌ ثانٍ"


# ── الجذر ١ · الصفُّ يفتح ستّةَ أبواب ────────────────────────────────────

def _view_with_row():
    from canonical_netherlands import netherlands_research_blob
    from silk_requirements_agent import regulatory_state
    r = netherlands_research_blob()
    dr = r["deep_research"]
    reg = regulatory_state("NLD", "080410")
    r["markets"] = [{"iso3": "NLD", "name_ar": "هولندا", "rank": 1,
                     "deep": True, "regulatory": reg,
                     "components": DP.build_components(dr),
                     "decision": DP.decide_for_deep(dr, regulatory=reg)}]
    return silk_render.build_view(r, "ar"), dr


def test_d04_the_view_no_longer_claims_there_are_no_ranked_markets():
    """رسالةٌ متناقضة على مسارٍ يحلّل سوقاً واحدةً بعمق."""
    view, _ = _view_with_row()
    d = view["decision"]
    assert d.get("verdict"), "القرارُ ما يزال فارغاً (D-04)"
    assert "لا أسواق مرتّبة" not in str(d.get("why") or "")


def test_the_canonical_decision_path_is_used_not_a_second_one():
    """القرارُ المحسوب يسلك مسارَ `build_view` القائم — لا صياغةَ ثانية.

    أضفتُ فرعاً ثانياً أثناء التنفيذ ثمّ حذفتُه: كان يصوغ القرارَ من الصفّ
    بنفسه، أي مسارَ عرضٍ ثانياً لنفس الحكم.
    """
    src = io.open(os.path.join(_ROOT, "silk_render.py"), encoding="utf-8").read()
    assert "_decision_from_engine" not in src, "عاد مسارُ العرض الثاني"
    d = _view_with_row()[0]["decision"]
    assert d.get("rule"), "قاعدةُ القرار قبل الحكم لا تصل العرض"
    assert d.get("counter_case"), "الحجّةُ المضادّة لا تصل العرض"


def test_p01_the_pillars_and_weights_reach_the_client_surface():
    """الأعمدةُ الخمسة بأوزانها **ومعادلةِ كلٍّ منها** تصل تقرير العميل."""
    view, _ = _view_with_row()
    ed = view["markets"][0].get("entry_decision") or {}
    assert ed.get("schema"), "قرارُ الدخول لا يصل صفَّ العرض (P-01)"
    assert set(ed.get("pillars") or {}) == {
        "market", "competition", "regulatory", "profit", "risk"}
    assert (ed.get("scores_by_option") or {}).keys() >= {"A", "B"}
    assert ed["pillars"]["competition"].get("basis"), "العمودُ بلا معادلة"


def test_x03_the_row_carries_components_so_the_lesson88_guards_can_read_it():
    """**الجذرُ وحدَه لم يكن كافياً.**

    `build_view` يبني `components_detail` من `row["components"]`؛ فصفٌّ بلا
    مكوّنات يُبقي الحارسَين خامدَين **بشكلٍ آخر** — مقيسٌ: صفر قبل، أربعة بعد.
    """
    view, _ = _view_with_row()
    cd = view["markets"][0].get("components_detail") or []
    assert len(cd) >= 4, "الصفُّ بلا مكوّنات — الحارسان خامدان (X-03)"
    valued = [c for c in cd if c.get("value") is not None]
    assert valued, "لا مكوّنَ بقيمة"
    assert all(c.get("source") for c in valued), "رقمٌ بلا سطر مصدر"


def test_s01_a_dated_component_carries_its_vintage_caveat():
    """تحذيرُ القِدَم ذو الطبقتين يعمل على المسار العميق."""
    from canonical_netherlands import netherlands_research_blob
    r = netherlands_research_blob()
    dr = r["deep_research"]
    dr["missions"]["trade_flow"]["findings"][0]["data_year"] = 2019
    r["markets"] = [{"iso3": "NLD", "rank": 1, "deep": True,
                     "components": DP.build_components(dr)}]
    cd = silk_render.build_view(r, "ar")["markets"][0]["components_detail"]
    aged = [c for c in cd if c.get("vintage")]
    assert aged, "رقمٌ من ٢٠١٩ يصل بلا تحذيرِ عمر (S-01)"
    assert "2019" in aged[0]["vintage"]


def test_a_missing_component_is_declared_not_dropped():
    """حذفُ الغائب يجعل التغطيةَ تبدو كاملةً دائماً — عطلُ الموجة B نفسُه."""
    comps = DP.build_components(_dr(trade_flow=[_f("واردات 42,000,000 دولار",
                                                   "واردات")]))
    assert set(comps) >= {"market_size", "competition", "saudi_position"}
    assert comps["competition"]["value"] is None
    assert comps["competition"]["status"] == "no_record"


# ── D-03 · «حكمٌ واحد» يُختبَر على المسار الذي انكسر ─────────────────────
#
# `tests/test_stage5_review_fixes.py::test_single_authoritative_verdict_
# everywhere` يُشغِّل `silk_engine.analyze` — أي `/analyze` وحدَه. فالمسارُ
# العميق (الذي يشتريه المصنع، وهو الذي انكسر فعلاً) بقي **بلا حارسِ حكمٍ
# واحد**. هذا نظيرُه.

def test_the_deep_path_publishes_one_verdict_not_two():
    """حكمُ المحرّك هو المنشور، والجوريةُ سطرُ كفايةٍ لا حكمٌ ثانٍ."""
    view, _ = _view_with_row()
    engine_verdict = view["markets"][0]["entry_decision"]["verdict"]
    assert view["decision"]["verdict"] == engine_verdict, (
        "الحكمُ المنشور ليس حكمَ المحرّك على المسار العميق (D-03)")


def test_no_raw_machine_verdict_code_reaches_any_client_derivative():
    """لا رمزَ آلةٍ خام في أيّ مُشتَقّ — نفسُ عقد `/analyze` حرفياً."""
    from silk_reports import render_brief, render_markdown
    from silk_render import render_text
    view, _ = _view_with_row()
    for out in (render_markdown(view), render_text(view), render_brief(view)):
        assert "CONDITIONAL-GO" not in out, "رمزُ آلةٍ خام وصل مُشتَقّاً"
        assert "PRELIMINARY GO" not in out


def test_the_jury_string_is_decoded_by_its_code_not_its_text():
    """**V-02:** نصٌّ لا يعرفه أيُّ مطابِقٍ يُفكَّك صحيحاً بالرمز البنيويّ.

    السلسلةُ المختلطة كان يفكّكها مفكّكان مستقلّان بمطابقةٍ نصّية فرعية، فقد
    يظهر الحكمُ الواحد بنبرتين — وتغييرُ حرفٍ يكسر أحدَهما بصمت.
    """
    from silk_render import _coverage_basis_tone, _verdict_label, _verdict_tone
    jury = {"basis": "data_coverage", "coverage_state": "coverage_none",
            "verdict": "صيغةٌ جديدةٌ تماماً لا يعرفها أيُّ مطابِق"}
    tone = _coverage_basis_tone(_verdict_tone(jury["verdict"]), jury)
    assert tone == "data_absent"
    assert _verdict_label(tone) == "تعذّر البحث — لا بيانات كافية لأيّ حكم"


def test_every_coverage_state_maps_to_a_declared_tone():
    from silk_agents import COVERAGE_STATES
    from silk_render import _STATE_TONE
    assert set(COVERAGE_STATES) == set(_STATE_TONE), (
        "حالةُ تغطيةٍ بلا نبرةٍ معلَنة — أو العكس")


def test_the_jury_still_emits_its_legacy_string_unchanged():
    """تكافؤٌ رجعيّ: السجلّاتُ المخزَّنة قبل الموجة تبقى مقروءة."""
    from silk_agents import AgentReport, JuryCommittee
    from silk_data_layer import DataPoint
    ok = AgentReport("A", [DataPoint(1, "s", 0.8)], False, "")
    out = JuryCommittee().evaluate([ok, AgentReport("B", [], True, "")])
    assert out["verdict"].startswith("PRELIMINARY / INCONCLUSIVE")
    assert out["coverage_state"] == "coverage_partial"


# ── P-02 · الكاتبُ يعرض الدرجة ولا يحسبها ───────────────────────────────

def test_the_writer_is_never_ordered_to_produce_a_score():
    body = "\n".join(
        l for l in io.open(os.path.join(_ROOT, "silk_ai_judge.py"),
                           encoding="utf-8").read().splitlines()
        if not l.strip().startswith("#"))
    assert "(score/confidence) في جدول Markdown صغير" not in body, (
        "الموجّهُ ما يزال يأمر بطباعة درجةٍ لا تحسبها شيفرة (P-02)")
    assert "لا تحسبها ولا تشتقّها" in body
    assert "الدرجة الرقمية غير متاحة" in body, (
        "غيابُ الدرجة بلا أمرِ إعلانٍ يدعو النموذجَ إلى ملئه")


# ── V-03 · مدحوضٌ بإعادة الإنتاج — لا «إصلاحَ» لما ليس معطوباً ───────────
#
# ادّعى الجردُ أنّ «حكمَ المرحلة ٢ يعمل ولا يصل التقرير» فيكون نداءً مدفوعاً
# مهدوراً. إعادةُ الإنتاج على المسار العميق تنفيه: القراءةُ تُخزَّن في
# `verdict["ai"]`، وتصل العرضَ، **وتُطبَع في تقرير المدقّق** موسومةً «قراءة
# تحليلية للذكاء الاصطناعي (استشارية — ليست التوصية)».
#
# فالسلوكُ صحيحٌ ومقصود: الحكمُ لا يتقدّم على الحتميّ (WP-1)، والتحليلُ يُقرأ
# على سطح المشغّل. وقرارُ المالك (2026-08-21) أن يبقى **داخلياً للمشغّل** دون
# توسيعِ سطح العميل. هذه الأقفالُ تحرس ذلك في الاتجاهين.

def _view_with_stage2_reading():
    from canonical_netherlands import netherlands_research_blob
    r = netherlands_research_blob()
    dr = r["deep_research"]
    dr["verdict"] = {**(dr.get("verdict") or {}),
                     "ai": {"verdict": "WATCH", "confidence": 0.55,
                            "reasoning": "تحليلٌ استشاريّ من المرحلة الثانية."}}
    r["markets"] = [{"iso3": "NLD", "name_ar": "هولندا", "rank": 1,
                     "deep": True, "components": DP.build_components(dr),
                     "decision": DP.decide_for_deep(dr)}]
    return silk_render.build_view(r, "ar")


def test_the_stage2_reading_is_preserved_on_the_deep_path():
    """النداءُ المدفوع ليس مهدوراً: قراءتُه تُخزَّن وتصل العرض."""
    ai = ((_view_with_stage2_reading().get("deep_research") or {})
          .get("verdict") or {}).get("ai") or {}
    assert ai.get("verdict"), "قراءةُ المرحلة ٢ تضيع على المسار العميق"
    assert ai.get("reasoning"), "سببُ القراءة يضيع"


def test_the_stage2_reading_reaches_the_operator_report_tagged():
    """تصل تقريرَ المدقّق **موسومةً** — لا توصيةً ثانية."""
    import tempfile
    from tests.conftest import docx_all_text
    path = os.path.join(tempfile.mkdtemp(), "operator.docx")
    silk_reports_mod = __import__("silk_reports")
    silk_reports_mod.render_docx(_view_with_stage2_reading(), path)
    text = docx_all_text(path)
    assert "قراءة تحليلية للذكاء الاصطناعي" in text
    assert "ليست التوصية" in text, "القراءةُ بلا وسمٍ تُقرأ حكماً ثانياً"


def test_the_stage2_reading_never_becomes_the_published_verdict():
    """WP-1 — قرارٌ مستقرّ: الحكمُ من المرحلة الحتمية حصراً."""
    view = _view_with_stage2_reading()
    published = view["decision"]["verdict"]
    ai_v = ((view.get("deep_research") or {}).get("verdict") or {}) \
        .get("ai", {}).get("verdict")
    assert ai_v == "WATCH"
    assert published != "WATCH", "قراءةُ المرحلة ٢ تقدّمت على الحكم الحتميّ"


def test_the_stage2_reading_stays_off_the_client_surface():
    """قرارُ المالك: داخليٌّ للمشغّل، لا يُوسَّع به سطحُ العميل."""
    from silk_reports import render_brief
    view = _view_with_stage2_reading()
    brief = render_brief(view)
    assert "قراءة تحليلية للذكاء الاصطناعي" not in brief
    assert "WATCH" not in brief
