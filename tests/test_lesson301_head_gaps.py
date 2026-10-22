"""الدرس ٣٠١ — «find all gaps» بعد الدرس ٣٠٠ (رأسُ السلسلة آخرُ سنةٍ مصرَّحة).

ثلاث عدسات (أسطحٌ لم تُحدَّث، البوّابةُ والكاتب، ثوابتُ الحوافّ على 3,566 سلسلة مولَّدة) وجدت
أسطحاً بقيت تقرأ سنةَ المرآة رأساً أو تحسب منها نموّاً، وحوافَّ تكسر الوسم. كلُّ قفلٍ هنا
كُتب قبل إصلاحه ويعيد إنتاج الحالة حرفياً (direct reproduction).

Lesson 301 locks: every surface that still read a mirror year as the head / growth window,
plus edge cases of the lesson-300 head. Written test-first.
"""
import os
import sys
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools"), os.path.join(_ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import silk_deep_pillars as P                                  # noqa: E402
from silk_data_layer import DataPoint                         # noqa: E402
from test_lesson300_series_head import _bahrain_blob, _missions, _pt  # noqa: E402

_AR = ("؀", "ۿ")


def _has_ar(s) -> bool:
    return any(_AR[0] <= ch <= _AR[1] for ch in str(s or ""))


def _dr(missions: dict, text: str = "") -> dict:
    from silk_render import _dp
    return {"missions": {k: {"findings": [_dp(f) for f in v["findings"]]}
                         for k, v in missions.items()},
            "report": {"text": text}}


# ── البوّابة: لا نموَّ من المرآة ولا «أحدث سنة» منها ─────────────────────────────

def test_gate_series_window_is_closed_when_growth_is_refused():
    import silk_quality_gate as Q
    text = "شهدت واردات السوق نمواً ملحوظاً في السنوات الأخيرة."
    mirror_only = _missions(direct=(), mirror=((2021, 10e6), (2022, 6e6), (2023, 8e6)))
    assert Q._annual_import_series(_dr(mirror_only, text)) == {}
    assert Q._check_cagr_sign_flips_under_base_year(_dr(mirror_only, text)) == []
    one_direct = _missions(direct=((2023, 8e6),), mirror=((2021, 10e6), (2022, 6e6)))
    assert Q._check_cagr_sign_flips_under_base_year(_dr(one_direct, text)) == []


def test_gate_endpoint_lag_ignores_a_mirror_year():
    import silk_quality_gate as Q

    def dr(mirror_status):
        return {"missions": {"trade_flow": {"findings": [
            {"value": 15120000.0, "data_year": 2025, "confidence": 0.6,
             "source": "UN Comtrade (مرآة)" if mirror_status else "UN Comtrade",
             "status": "mirrored" if mirror_status else "",
             "note": "إجمالي واردات السوق سنة 2025" + (" (مرآة)" if mirror_status else "")},
            {"value": 9170000.0, "source": "UN Comtrade", "confidence": 0.9, "data_year": 2024,
             "note": "إجمالي واردات السوق سنة 2024"},
            {"value": "CAGR 2019–2024 بنحو 13.7%", "source": "UN Comtrade", "confidence": 0.8,
             "note": "CAGR 2019–2024 محسوب من التصريح المباشر"}]}}}
    assert Q._check_cagr_endpoint_lag(dr(True)) == []
    assert Q._check_cagr_endpoint_lag(dr(False))          # الضابط: سنةٌ مباشرة أحدث تبقى تُطلق


def test_figure_store_decision_reading_prefers_the_direct_head_over_a_newer_mirror():
    import silk_figure_store as FS
    st = FS.build(_missions())
    figs = {f["id"]: f for f in st["figures"]}
    did = st["decision_reading"]["imports"]
    assert figs[did]["method"] == "direct" and figs[did]["year"] == 2024
    # بلا مباشرٍ أصلاً تبقى المرآةُ قراءةَ القرار (قراءة المالك ٢).
    st2 = FS.build(_missions(direct=(), mirror=((2023, 9e6), (2024, 10e6))))
    f2 = {f["id"]: f for f in st2["figures"]}
    assert f2[st2["decision_reading"]["imports"]]["year"] == 2024


# ── السجلّ: الرسمُ وسطرُ المرآة الموسوم لا يُعاقَبان ─────────────────────────────────

def test_imports_chart_shows_the_mirror_after_the_head_apart_not_as_a_bar():
    from silk_render import _chart_imports_trend, _imports_view
    iv = _imports_view({"markets": []}, {"missions": _missions()}, "ar")
    ch = _chart_imports_trend(iv, "ar")
    assert [p["year"] for p in ch["series"]] == [2019, 2022, 2023, 2024]
    assert ch["year"] == "2019–2024"
    assert "2025" in ch["note"] and "مرآة" in ch["note"]   # منفصلةٌ موسومة في تعليق الرسم


def test_ledger_check_accepts_a_labelled_mirror_year_and_still_flags_an_unlabelled_one():
    import silk_fact_ledger as L
    from silk_render import _chart_imports_trend, _imports_view
    led = L.build_ledger({"deep_research": {"missions": _missions()}})
    iv = _imports_view({"markets": []}, {"missions": _missions()}, "ar")
    view = {"ledger": led, "deep_research": {"charts": [_chart_imports_trend(iv, "ar")]}}
    ok = ("بلغت واردات السوق 9.17 مليون دولار في 2024. وتقدير المرآة لواردات 2025 من بيانات "
          "الدول الشريكة نحو 15.12 مليون دولار.")
    checks = {f["check"] for f in L.check(view, ok)}
    assert "ledger_series_year_mismatch" not in checks and "chart_year_mismatch" not in checks
    bad = "بلغت واردات السوق 15.12 مليون دولار في 2025."
    assert "ledger_series_year_mismatch" in {f["check"] for f in L.check(view, bad)}


# ── الحوافّ: الإسنادُ والوسمُ والسنةُ الجزئية ──────────────────────────────────────

def test_direct_head_is_attributed_to_the_direct_finding_not_an_equal_mirror_one():
    import silk_fact_ledger as L
    same = {"trade_flow": {"findings": [_pt(2022, 3_039_000.0, True), _pt(2022, 3_039_000.0)]}}
    ms = P.build_components({"missions": same})["market_size"]
    assert "مرآة" not in ms["source"] and ms["confidence"] == 0.9
    m = _missions(direct=((2022, 4e6), (2023, 5e6)), mirror=((2021, 5e6),))
    mi = L.build_ledger({"deep_research": {"missions": m}})["entries"]["market_imports_usd"]
    assert not mi.get("mirrored") and mi["status"] == "observed" and mi.get("year") == 2023


def test_only_a_partial_mirror_year_is_labelled_and_never_market_size():
    import silk_fact_ledger as L
    from silk_render import _imports_view
    import datetime as _dt
    cur = _dt.date.today().year
    m = _missions(direct=(), mirror=((cur, 10e6),))
    e = L.build_ledger({"deep_research": {"missions": m}})["entries"]["imports_latest_year"]
    assert e.get("mirrored") and e["status"] == "weak" and "صرّحت بها السوق" not in e["note"]
    assert "مرآة" in L.render_value(e, "ar")
    iv = _imports_view({"markets": []}, {"missions": m}, "ar")
    assert "مرآة" in iv["value_line"]
    # سنةٌ جارية (جزئية) لا تصير حجمَ السوق (الدرس ٢٩٠) — فجوةٌ معلنة لا رقمٌ جزئي.
    assert P.build_pillar_inputs({"missions": m})["market_attractiveness"]["tam_usd"] is None
    assert P.build_components({"missions": m})["market_size"]["value"] is None


def test_incomplete_mirror_year_behind_a_current_year_point_is_partial():
    import datetime as _dt
    cur = _dt.date.today().year
    m = _missions(direct=(), mirror=((cur - 4, 100e6), (cur - 3, 100e6), (cur - 2, 100e6),
                                     (cur - 1, 30e6), (cur, 5e6)))
    s = P.import_series(m)
    by = {p["year"]: p for p in s["series"]}
    assert by[cur - 1]["partial"] and by[cur - 1].get("partial_reason") == "mirror_incomplete"
    assert s["head"]["year"] == cur - 2 and s["head"]["value"] == 100e6


def test_english_imports_source_carries_no_arabic_when_the_head_is_mirror():
    from silk_render import _chart_imports_trend, _imports_view
    m = _missions(direct=(), mirror=((2023, 9e6), (2024, 10e6)))
    en = _imports_view({"markets": []}, {"missions": m}, "en")
    assert not _has_ar(en["source"]) and "mirror" in en["source"]
    assert not _has_ar(_chart_imports_trend(en, "en")["source"])


# ── F3 (أداة القياس): سنةٌ مباشرةٌ جزئية ليست «تصريحاً مباشراً» ─────────────────────

def test_f3_does_not_count_a_partial_current_year_as_a_direct_figure():
    import datetime as _dt
    import silk_study_checks as C
    cur = _dt.date.today().year
    blob = _bahrain_blob(direct=((cur, 1e6),), mirror=((cur - 2, 5e6), (cur - 1, 6e6)))
    blob["deep_research"]["report"] = {"report": "## 1. الخلاصة التنفيذية\n\nنص.\n",
                                       "review_cycles": 1, "unresolved_notes": []}
    f3 = C.check_mirror(C.StudyDoc.from_result(blob))
    assert not any(i.get("where") == "سجلّ الحقائق" for i in f3.items), f3.items


# ── نمط «دراسة السوق» ──────────────────────────────────────────────────────────

def _provisional(year):
    return lambda y, today=None: int(y) == year


def test_study_header_year_is_complete_not_provisional():
    import silk_study_render as R
    from silk_study_case import build_case
    import datetime as _dt
    last = _dt.date.today().year - 1
    d = tuple((y, 6e6 + (y - last + 4) * 1e6) for y in range(last - 4, last + 1))
    with mock.patch.object(P, "is_provisional_year", _provisional(last)):
        case = build_case(_bahrain_blob(direct=d, mirror=()))
    assert R._last_complete_year(case) == last - 1
    assert R._provisional_year(last, case) == f"{last} (أولي)"


def test_study_unit_values_come_from_the_direct_window():
    from silk_study_case import build_case
    blob = _bahrain_blob(direct=((2019, 4e6), (2020, 5e6), (2021, 6e6), (2022, 7e6),
                                 (2023, 8e6), (2024, 9e6)),
                         mirror=((2018, 3.6e6), (2025, 15e6)))
    kg = {2018: 400e3, 2019: 400e3, 2020: 480e3, 2021: 100e3, 2022: 640e3, 2023: 720e3,
          2024: 800e3, 2025: 1000e3}
    tf = blob["deep_research"]["missions"]["trade_flow"]
    tf.findings += [DataPoint(w, "UN Comtrade", 0.9, f"صافي الوزن كجم {y}", "2026-10-20",
                              data_year=y) for y, w in kg.items()]
    imp = build_case(blob)["imports"]
    assert imp["unit_value_first"] == 10.0                  # 2019 مباشر، لا مرآة 2018 (9.0)
    assert imp["unit_value_last_reliable"] == 11.25         # 2024 مباشر، لا مرآة 2025 (15.0)


def test_study_mode_labels_a_mirror_head_when_the_market_declares_nothing():
    from silk_study_case import build_case
    from silk_study_render import render_study
    case = build_case(_bahrain_blob(direct=(), mirror=((2023, 9e6), (2024, 10e6))))
    assert "تصريحات الاستيراد لدى" not in case["imports"]["source_line"]
    assert "مرآة" in case["imports"]["source_line"]
    md = render_study(case)
    assert "**أحدث سنة بيانات تجارية مكتملة:** 2024 (تقدير من بيانات الشركاء)" in md


# ── بعثة التدفّق: نموٌّ يستشهد بسنة مرآة يُوسَم ولا يمرّ كأنه مباشر ───────────────────

def test_a_mission_growth_claim_citing_a_mirror_year_is_labelled():
    import silk_llm_runtime as rt
    from silk_market_resolver import resolve_market
    from silk_missions import MISSIONS
    reg = {"dp1": _pt(2019, 4.83e6), "dp2": _pt(2024, 9.17e6), "dp3": _pt(2025, 15.12e6, True)}

    def loop(mission, ctx, budget, timeout=None, model=None):
        return {"findings": [
            {"claim": "نمت واردات السوق 213% بمعدل مركّب 20.9% بين 2019 و2025",
             "datapoint_ids": ["dp1", "dp2", "dp3"], "confidence": 0.8, "category": "demand"},
            {"claim": "بلغت واردات السوق 9.17 مليون دولار في 2024",
             "datapoint_ids": ["dp2"], "confidence": 0.9, "category": "demand"}],
            "gaps": [], "summary": "ok", "registry": reg, "tool_calls_used": 1}
    ref, _ = resolve_market("Bahrain")
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), \
         mock.patch.object(rt, "_run_loop", loop):
        rep = rt.run_llm_agent(MISSIONS["trade_flow"], ref, product="قهوة", hs_code="090121")
    growth, level = rep.findings
    assert "مرآة" in str(growth.value) and "2025" in str(growth.value)
    assert "مرآة" not in str(level.value)                    # بندٌ لا نموَّ فيه لا يُمَسّ
    # والتعليمةُ نفسُها لا تأمر بحساب المركّب على سلسلةٍ فيها مرآة (كانت «عبر السلسلة الخمسية»).
    assert "لا تدخل حسابَ النمو" in MISSIONS["trade_flow"]["instructions"]


def test_series_path_with_each_year_named_is_not_an_unnamed_divergence():
    """«من 4.83 مليون في 2019 إلى 9.17 مليون في 2024» — مسارُ السلسلة المباشرة الذي يطلبه
    الدرس ٣٠٠ يسمّي سنةَ كلّ قراءة؛ كان يُعَدّ «قراءتين بلا تسمية الفرق» (سابقٌ على الدرس)."""
    import silk_quality_gate as Q
    named = ("## 3. نظرة عامة على السوق وحجمه\n\nنمت الواردات من 4,830,000 دولار في 2019 إلى "
             "9,170,000 دولار في 2024.\n")
    assert Q._check_metric_value_divergence({}, _dr(_missions(), named)) == []
    bare = ("## 3. نظرة عامة على السوق وحجمه\n\nتبلغ الواردات 4,830,000 دولار، وتذكر قراءة "
            "أخرى 9,170,000 دولار.\n")
    assert Q._check_metric_value_divergence({}, _dr(_missions(), bare))


def test_writer_rule_names_the_direct_base_year_and_keeps_mirror_apart():
    src = open(os.path.join(_ROOT, "silk_ai_judge.py"), encoding="utf-8").read()
    assert "أوّل سنةٍ صرّحت بها السوق" in src and "سنةُ المرآة المقدَّرة من بيانات الشركاء" in src


def test_a_lone_mirror_row_is_never_in_the_study_growth_window():
    from silk_study_case import build_case
    rows = build_case(_bahrain_blob(direct=(), mirror=((2024, 10e6),)))["imports"]["series"]
    assert rows and not any(r["in_growth_window"] for r in rows if r["mirrored"])


# ── المراجعة الذاتية (§58) على الدرس ٣٠١ ─────────────────────────────────────────

def test_review_divergence_still_fires_on_a_same_year_conflict_beside_another_year():
    import silk_quality_gate as Q
    extra = DataPoint(12_000_000.0, "بحث ويب", 0.5, "إجمالي واردات السوق 2024 (تقدير صحفي)",
                      "2026-10-20", data_year=2024)
    m = _missions(extra=(extra,))
    body = ("## 3. نظرة عامة على السوق وحجمه\n\nنمت الواردات من 4,830,000 دولار في 2019 إلى "
            "9,170,000 دولار في 2024، وتذكر قراءة أخرى 12,000,000 دولار في 2024.\n")
    assert Q._check_metric_value_divergence({}, _dr(m, body))


def test_review_mirror_growth_label_is_narrow():
    import silk_llm_runtime as rt
    mirror_total, direct_total = _pt(2025, 15.12e6, True), _pt(2024, 9.17e6)
    share = DataPoint(45.0, "UN Comtrade (مرآة)", 0.6, "حصة الصين من الواردات (مرآة)", "x",
                      status="mirrored", data_year=2025)
    keep = (("ارتفعت حصة الصين إلى 45%", [share]),
            ("نموذج التسعير يعطي هامشاً 12%", [mirror_total]),
            ("أسطول المركبات كبير، والحصة 12%", [mirror_total]),
            ("نمت الواردات 89.9% بين 2019 و2024، وتقدير المرآة لعام 2025 نحو 15.12 مليون",
             [direct_total, mirror_total]))
    for claim, cited in keep:
        assert rt._label_mirror_growth(claim, cited) == claim, claim
    hit = rt._label_mirror_growth("نمت واردات السوق 213% بين 2019 و2025", [direct_total, mirror_total])
    assert "مرآة" in hit


def test_review_generic_supplier_wording_is_not_a_mirror_label():
    import silk_fact_ledger as L
    from silk_render import _chart_imports_trend, _imports_view
    led = L.build_ledger({"deep_research": {"missions": _missions()}})
    iv = _imports_view({"markets": []}, {"missions": _missions()}, "ar")
    view = {"ledger": led, "deep_research": {"charts": [_chart_imports_trend(iv, "ar")]}}
    for bad in ("بلغت واردات السوق من الدول المصدرة 15.12 مليون دولار في 2025.",
                "Market imports via key partnerships reached $15.1M in 2025.",
                "Per U.S. trade data, imports reached $15.1M in 2025."):
        assert "ledger_series_year_mismatch" in {f["check"] for f in L.check(view, bad)}, bad


def test_review_all_partial_mirror_point_is_labelled_in_study_mode():
    import datetime as _dt
    from silk_study_case import build_case
    cur = _dt.date.today().year
    case = build_case(_bahrain_blob(direct=(), mirror=((cur, 10e6),)))
    assert case["imports"]["head_is_mirror"] is True
    assert "تصريحات الاستيراد لدى" not in case["imports"]["source_line"]


def test_review_header_label_follows_the_returned_row():
    import silk_study_render as R
    from silk_study_case import build_case
    import datetime as _dt
    last = _dt.date.today().year - 1
    blob = _bahrain_blob(direct=((last - 3, 6e6), (last - 2, 7e6), (last, 9e6)),
                         mirror=((last - 1, 8e6),))
    with mock.patch.object(P, "is_provisional_year", _provisional(last)):
        case = build_case(blob)
    md = R.render_study(case)
    assert f"**أحدث سنة بيانات تجارية مكتملة:** {last - 1} (تقدير من بيانات الشركاء)" in md


def test_review_english_source_drops_any_arabic_mirror_spelling():
    from silk_render import _imports_view
    m = {"trade_flow": {"findings": [
        DataPoint(v, "UN Comtrade (مرآة الشركاء)", 0.6, f"إجمالي واردات السوق HS090121 {y}", "x",
                  status="mirrored", data_year=y) for y, v in ((2023, 9e6), (2024, 10e6))]}}
    en = _imports_view({"markets": []}, {"missions": m}, "en")
    assert not _has_ar(en["source"]) and "mirror" in en["source"]
