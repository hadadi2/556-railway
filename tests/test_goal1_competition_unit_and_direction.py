"""البند 1 من أمر إصلاح محرّك التقارير — وحدة حقل المنافسة واتجاهه.

الدليل (direct reproduction — تقريرا #10/#11 حليب/الأردن): حقل المنافسة قَبِل
كمّيتين — HHI=8258 في #10 وحصةً مئوية 84.05 في #11 — لأن الاستخراج النثريّ
يلتقط أول رقم في المدى (0–10000) قرب الكلمة، والمدى يبتلع الحصص (0–100)،
فانقلب الحكم 26%→84% من هذا الحقل وحده. الفكس: hhi/حصة الأكبر من ملخّص
`comtrade_competitors` المُهيكل حصراً + علم `incumbent_is_self` مستقل.

القبول (نصّ الأمر حرفياً): HHI=7118 ⇒ درجة العمود ≤25%؛ حصة مورّد واحد 84%
⇒ ≤25%. هرمتي. Run:
  python3 -m pytest tests/test_goal1_competition_unit_and_direction.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_decision as D                                # noqa: E402
import silk_deep_pillars as DP                           # noqa: E402


def _consumed(pi: dict) -> float:
    """درجة العمود كما تدخل المجموع الموزون فعلاً (1 − الشدة)."""
    p = D._pillar_competition(pi)
    assert p["value"] is not None
    return 1.0 - p["value"]


# افتراضات المدوّنة = الحالة المرجعية 040120 (تقرير #11 الصحيح: HHI 7118،
# حصة 84.05) — أمر المُشرِف: لا مدوّنة إيجابية على أرقام بند 040110
# الخاطئ؛ حالة #10 التاريخية تبقى في اختبارها المسمّى صراحةً أدناه.
def _summary_dp(hhi=7118, partner="Saudi Arabia", share=84.05):
    return {"value": {"year": 2023, "hhi": hhi, "supplier_count": 7,
                      "top_suppliers": [{"partner": partner, "share": share}]},
            "source": "UN Comtrade", "confidence": 0.9, "data_year": 2023,
            "note": f"HS040120 مورّدو الأردن 2023: 7 دولة مرصودة، "
                    f"مؤشر تركّز HHI={hhi}"}


def _dr(findings):
    return {"missions": {"competitors": {"findings": findings}}}


def test_acceptance_hhi_7118_scores_at_most_25pct():
    assert _consumed({"hhi": 7118}) <= 0.25


def test_acceptance_single_supplier_share_84_scores_at_most_25pct():
    assert _consumed({"top_supplier_share_pct": 84.0}) <= 0.25


def test_report10_reference_inputs_score_low():
    """مدخلات #10 الفعلية (HHI 8258 + حصة 90.61) ⇒ درجة منخفضة كما كانت."""
    assert _consumed({"hhi": 8258, "top_supplier_share_pct": 90.61}) <= 0.25


def test_share_in_prose_is_never_read_as_hhi():
    """قلب حادثة #11: نثرٌ يحمل «تركّز» و84.05 بلا ملخّص مُهيكل ⇒ لا HHI
    مُختلَق ولا حصة — فجوة معلنة يعيد `decide` تسوية أوزانه عندها."""
    prose = {"value": "تستحوذ السعودية على 84.05% من الواردات",
             "source": "بحث ويب", "confidence": 0.5,
             "note": "مؤشر تركّز السوق مرتفع وفق حصة أكبر مورّد 84.05"}
    pi = DP.build_pillar_inputs(_dr([prose]))
    comp = pi["competition_intensity"]
    assert comp["hhi"] is None
    assert comp["top_supplier_share_pct"] is None


def test_structured_summary_feeds_both_metrics_and_incumbent_flag():
    pi = DP.build_pillar_inputs(_dr([_summary_dp()]))
    comp = pi["competition_intensity"]
    assert comp["hhi"] == 7118
    assert comp["top_supplier_share_pct"] == 84.05
    assert comp["incumbent_is_self"] is True
    # ومن نفس المدخلات: العمود منخفض والحكم لا «يكافئ» الانغلاق
    assert _consumed(comp) <= 0.25


def test_incumbent_flag_reaches_decision_without_changing_score():
    saudi = DP.build_pillar_inputs(_dr([_summary_dp()]))
    spain = DP.build_pillar_inputs(
        _dr([_summary_dp(partner="Spain")]))
    d_saudi = D.decide({"coverage": 1.0, "pillar_inputs": saudi})
    d_spain = D.decide({"coverage": 1.0, "pillar_inputs": spain})
    assert d_saudi["incumbent_is_self"] is True
    assert not d_spain["incumbent_is_self"]
    # علمٌ لا درجة: الدرجتان متطابقتان
    assert d_saudi["score"] == d_spain["score"]


def test_old_unit_hhi_zero_to_one_is_rescaled():
    pi = DP.build_pillar_inputs(_dr([_summary_dp(0.7118)]))
    assert pi["competition_intensity"]["hhi"] == 7118


def test_out_of_range_share_is_declared_not_consumed():
    bad = _summary_dp(share=8470.0)   # وحدة خاطئة في حقل الحصة
    pi = DP.build_pillar_inputs(_dr([bad]))
    assert pi["competition_intensity"]["top_supplier_share_pct"] is None


def test_numeric_valued_finding_is_still_read_as_hhi():
    """احتياط rung-2 (مراجعة §58): نتيجةٌ **قيمتُها رقم** بكلمة المؤشّر
    (شكل المدوّنات القانونية والإلحاقات الحتمية) تبقى مقروءة — النموذج لا
    يُنتج قيماً رقمية أصلاً فلا التباس وحدة، وأرضية 100 تحسم البقية."""
    numeric = {"value": 940, "source": "UN Comtrade", "confidence": 0.9,
               "note": "HHI تركّز السوق"}
    pi = DP.build_pillar_inputs(_dr([numeric]))
    assert pi["competition_intensity"]["hhi"] == 940


def test_numeric_share_near_concentration_word_is_not_hhi():
    """قيمة رقمية 84.05 بجوار «تركّز» دون أرضية HHI (100) ⇒ ليست HHI."""
    ambiguous = {"value": 84.05, "source": "بحث ويب", "confidence": 0.5,
                 "note": "تركّز السوق وفق حصة أكبر مورّد"}
    pi = DP.build_pillar_inputs(_dr([ambiguous]))
    assert pi["competition_intensity"]["hhi"] is None


def test_unresolvable_top_partner_leaves_incumbent_unknown():
    """اسم شريك غير محلول («Unclassified area…») ⇒ الهوية غير مرصودة —
    `incumbent_is_self=None` لا نفيٌ واثق (عقد عدم الاختلاق يشمل النفي)."""
    pi = DP.build_pillar_inputs(_dr([_summary_dp(
        partner="Unclassified area (Comtrade code 682)")]))
    assert pi["competition_intensity"]["incumbent_is_self"] is None


def test_structured_hhi_outside_unit_range_is_declared_not_consumed():
    """موجة سدّ الفجوات (F1): مدى الوحدة يُفرَض على المسار المُهيكل أيضاً —
    حصة تسرّبت لمفتاح hhi (قيمة الحادثة 84.05) كانت تنجو خاماً فتعطي
    «HHI 84» ودرجة منافسة 98%. خارج [100، 10000] ⇒ None معلَن."""
    pi = DP.build_pillar_inputs(_dr([_summary_dp(hhi=84.05)]))
    assert pi["competition_intensity"]["hhi"] is None
    corrupt = DP.build_pillar_inputs(_dr([_summary_dp(hhi=48000)]))
    assert corrupt["competition_intensity"]["hhi"] is None


def test_analyze_pillar_inputs_carry_incumbent_flag():
    """موجة سدّ الفجوات (F1): علم `incumbent_is_self` يصل مسار /analyze
    أيضاً — كان المسار العميق وحده ينتجه فبقي None دوماً على /analyze."""
    import silk_research as R
    outputs = {"competitor": {"findings": [
        {"metric": "hhi", "value": 7118},
        {"metric": "top_supplier_share_pct", "value": 84.05},
        {"metric": "supplier_countries",
         "value": [{"partner": "Saudi Arabia", "code": "682",
                    "share": 84.05, "value_usd": 5_840_000}]}]}}
    pi = R._pillar_inputs(outputs)
    assert pi["competition_intensity"]["incumbent_is_self"] is True
    spain = {"competitor": {"findings": [
        {"metric": "supplier_countries",
         "value": [{"partner": "Spain", "code": "724", "share": 41.0,
                    "value_usd": 1_000_000}]}]}}
    assert (R._pillar_inputs(spain)["competition_intensity"]
            ["incumbent_is_self"] is False)


def test_analyze_unresolved_top_partner_leaves_incumbent_unknown():
    """اسم غير محلول أو غياب صفوف المورّدين ⇒ None لا نفي واثق (نفس عقد
    المسار العميق — عدم الاختلاق يشمل النفي)."""
    import silk_research as R
    empty = R._pillar_inputs({"competitor": {"findings": []}})
    assert empty["competition_intensity"]["incumbent_is_self"] is None
    unresolved = {"competitor": {"findings": [
        {"metric": "supplier_countries",
         "value": [{"partner": "Unclassified area (code 682)",
                    "share": 84.05, "value_usd": 1}]}]}}
    assert (R._pillar_inputs(unresolved)["competition_intensity"]
            ["incumbent_is_self"] is None)


def test_quality_gate_competition_unit_valid_fails_out_of_range_value():
    """موجة سدّ الفجوات (F2): فحص `competition_unit_valid` من جدول البوابة —
    قيمة خارج مدى وحدتها المعلنة (HHI خارج [0،10000] أو حصة خارج [0،100])
    على القالب النهائي تُفشِل التسليم؛ حارسُ انحدارٍ خلف رفض المنبع."""
    import silk_quality_gate as QG

    def _view(hhi=None, share=None):
        return {"deep_research": {"report": {"text": "نص"}, "missions": {}},
                "markets": [{"research": {"pillar_inputs": {
                    "competition_intensity": {
                        "hhi": hhi, "top_supplier_share_pct": share}}}}]}

    bad = QG.run_quality_gate(_view(hhi=48000))
    assert any(f["check"] == "competition_unit_valid"
               for f in bad["findings"])
    assert bad["verdict"] == QG.FAIL
    bad_share = QG.run_quality_gate(_view(share=8470.0))
    assert any(f["check"] == "competition_unit_valid"
               for f in bad_share["findings"])
    # قيم ضمن العقد أو غائبة (None) لا تُعلَّم
    ok = QG.run_quality_gate(_view(hhi=7118, share=84.05))
    assert not any(f["check"] == "competition_unit_valid"
                   for f in ok["findings"])
    absent = QG.run_quality_gate(_view())
    assert not any(f["check"] == "competition_unit_valid"
                   for f in absent["findings"])


def test_deterministic_augment_appends_structured_summary_once():
    """المسار الحي (مراجعة §58 — «أخضر هرمتياً ≠ تم»): نتائج البعثة نصوصُ
    ادعاءات، والملخّص المُهيكل يصلها بالإلحاق الحتمي (نمط D3/WGI) —
    idempotent، وفشله فجوة معلنة لا كسر."""
    from unittest import mock
    import silk_missions as sm
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint

    summary = DataPoint({"year": 2023, "hhi": 7118, "supplier_count": 7,
                         "top_suppliers": [{"partner": "Saudi Arabia",
                                            "share": 84.05}]},
                        "UN Comtrade", 0.9, "ملخّص", data_year=2023)
    report = AgentReport("LLMMissionAgent:competitors",
                         [DataPoint("ادعاء نصي عن المنافسة", "بحث", 0.5,
                                    "تركّز")], False, "ملخص")

    class _Ref:
        m49, iso3, name_en = "400", "JOR", "Jordan"

    with mock.patch("silk_llm_runtime.competition_summary_findings",
                    return_value=[summary]) as fn:
        sm._augment_competitors_structured(report, "040120", _Ref())
        sm._augment_competitors_structured(report, "040120", _Ref())
    assert fn.call_count == 1                       # الثانية وجدته حاضراً
    dicts = [dp for dp in report.findings if isinstance(dp.value, dict)]
    assert len(dicts) == 1 and dicts[0].value["hhi"] == 7118
    # ومن التقرير المُلحَق: الأعمدة تُستخرَج فعلاً
    pi = DP.build_pillar_inputs({"missions": {"competitors": report}})
    assert pi["competition_intensity"]["hhi"] == 7118


def test_components_competition_provenance_comes_from_the_same_finding():
    """الإسناد من نفس النتيجة التي أعطت الرقم — لا مصدرَ «بحث ويب» تحت رقم
    كومتريد (مراجعة §58، عقد الإسناد لكل رقم)."""
    web_prose = {"value": "نص عن تركّز السوق", "source": "بحث ويب",
                 "confidence": 0.5, "note": "تركّز مرتفع", "data_year": 2021}
    comps = DP.build_components(_dr([web_prose, _summary_dp()]))
    assert comps["competition"]["value"] == 7118
    assert "Comtrade" in comps["competition"]["source"]
    assert comps["competition"]["data_year"] == 2023


def test_components_table_competition_reads_structured_hhi_only():
    """جدول «مكوّنات أفضل سوق»: قيمة المنافسة من الملخّص المُهيكل — النثر
    الملوَّث (سنةٌ/حصةٌ قرب كلمة «تركّز») لا يصل الجدول."""
    comps = DP.build_components(_dr([_summary_dp()]))
    assert comps["competition"]["value"] == 7118
    prose_only = DP.build_components(_dr([{
        "value": "نص", "source": "بحث ويب", "confidence": 0.5,
        "note": "مؤشر تركّز 2023 قرب حصة 84.05"}]))
    assert prose_only["competition"]["value"] is None
    assert prose_only["competition"]["status"] == "no_record"
