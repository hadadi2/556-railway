"""الدرس ٣٠٠ (PR-B البند أ، قرار المالك 2026-10-21) — رأسُ سلسلة الواردات آخرُ سنةٍ مصرَّحة.

دراسة قهوة البحرين (المرجع ١): السلسلةُ المباشرة 2019–2024 (4.83→9.17 مليون دولار) وسنةُ
مرآةٍ أحدث (2025، 15.12 مليون من تصريحات الشركاء). كان الرأسُ والنموُّ يُبنيان على سنة المرآة
فطُبع «15.12 مليون في 2025» و«نمو 213% ومركّب 20.9%» — تكرّر في أربع دراساتٍ مدفوعة.
القاعدة الآن (نصّ المالك): «آخر سنة بتصريح مباشر هي الرأس، وسنة المرآة تُعرض منفصلة ومعلَّمة،
ولا يُحسب منها نمو ولا معدل سنوي». وقراءتُه الثانية: رقمُ المرآة مسموحٌ موسوماً حين لا مباشرَ.

Lesson 300 locks: the series head is the latest directly-declared year; a mirror year is shown
apart and labelled; growth and CAGR never use mirror years. Written test-first.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import silk_deep_pillars as P                                  # noqa: E402
from silk_data_layer import DataPoint                         # noqa: E402

_DIRECT = ((2019, 4_830_000.0), (2022, 8_260_000.0), (2023, 8_770_000.0),
           (2024, 9_170_000.0))
_MIRROR = ((2025, 15_120_000.0),)


def _pt(year, value, mirrored=False):
    return DataPoint(value, "UN Comtrade (مرآة)" if mirrored else "UN Comtrade",
                     0.6 if mirrored else 0.9,
                     f"إجمالي واردات السوق HS090121 {year}" + (" (مرآة)" if mirrored else ""),
                     "2026-10-20", status="mirrored" if mirrored else "", data_year=year)


def _missions(direct=_DIRECT, mirror=_MIRROR, extra=()):
    rows = [_pt(y, v) for y, v in direct] + [_pt(y, v, True) for y, v in mirror]
    return {"trade_flow": {"findings": rows + list(extra)}}


def _bahrain_blob(direct=_DIRECT, mirror=_MIRROR):
    """الدراسة المموّهة (`tools/canonical_bahrain_coffee`) بسلسلة المرجع ١ نفسِها."""
    from canonical_bahrain_coffee import bahrain_coffee_research_blob
    blob = bahrain_coffee_research_blob()
    tf = blob["deep_research"]["missions"]["trade_flow"]
    tf.findings[:] = [_pt(y, v) for y, v in direct] + [_pt(y, v, True) for y, v in mirror]
    return blob


# ── import_series: الرأسُ والنموّ ───────────────────────────────────────────

def test_head_is_the_last_direct_year_and_the_mirror_year_stands_apart():
    s = P.import_series(_missions())
    assert s["head"]["year"] == 2024 and s["head"]["value"] == 9_170_000.0
    assert s["head_is_mirror"] is False
    assert [(p["year"], p["value"]) for p in s["mirror_after_head"]] == [(2025, 15_120_000.0)]
    assert all(p["mirrored"] for p in s["mirror_after_head"])
    # السلسلةُ نفسُها تبقى كاملةً للجدول والرسم — المرآةُ صفٌّ موسوم لا محذوف.
    assert [p["year"] for p in s["series"]] == [2019, 2022, 2023, 2024, 2025]


def test_growth_and_cagr_are_computed_from_direct_years_only():
    s = P.import_series(_missions())
    assert s["basis_years"] == [2019, 2024]
    assert s["basis_year_set"] == [2019, 2022, 2023, 2024]
    assert s["growth_pct"] == 89.9                      # 4.83 → 9.17، لا 213%
    assert s["cagr_pct"] == 13.7                        # لا 20.9%
    assert s["growth_refused"] is None


def test_no_growth_is_computed_from_mirror_years():
    # مباشرٌ واحد + سنتا مرآة: لا نموَّ (كان يُحسب على السلسلة كلّها).
    one_direct = P.import_series(_missions(direct=((2022, 8e6),),
                                           mirror=((2023, 9e6), (2024, 10e6))))
    assert one_direct["growth_pct"] is None and one_direct["cagr_pct"] is None
    assert one_direct["basis_years"] is None and one_direct["basis_year_set"] == []
    assert one_direct["growth_refused"] == "mirror_only"
    assert one_direct["head"]["year"] == 2022 and one_direct["head_is_mirror"] is False
    # مرآةٌ فقط: الرأسُ آخرُ سنةِ مرآة **موسوماً** (قراءة المالك ٢)، ولا نموّ.
    mirror_only = P.import_series(_missions(direct=(), mirror=((2023, 9e6), (2024, 10e6))))
    assert mirror_only["head"]["year"] == 2024 and mirror_only["head_is_mirror"] is True
    assert mirror_only["mirror_after_head"] == []
    assert mirror_only["growth_pct"] is None and mirror_only["growth_refused"] == "mirror_only"
    # سنةٌ واحدة: لا نموّ لنقصٍ لا لمرآة — السببان لا يُخلطان.
    single = P.import_series(_missions(direct=((2024, 9e6),), mirror=()))
    assert single["growth_refused"] is None and single["growth_pct"] is None


def test_base_year_and_market_size_follow_the_direct_head():
    m = _missions()
    assert P.base_year(m) == 2024
    pi = P.build_pillar_inputs({"missions": m})["market_attractiveness"]
    assert pi["tam_usd"] == 9_170_000.0
    assert pi["import_cagr_pct"] == 13.7


def test_a_refused_mirror_growth_does_not_fall_back_to_a_prose_cagr():
    """النموُّ المرفوض لأنه مرآة لا يعود من نثر البعثة (قد يكون محسوباً على المرآة نفسِها)."""
    prose = DataPoint(21.0, "بحث ويب", 0.5, "معدل النمو السنوي المركب للواردات 21%",
                      "2026-10-20")
    m = _missions(direct=((2022, 8e6),), mirror=((2023, 9e6), (2024, 10e6)), extra=(prose,))
    assert P.build_pillar_inputs({"missions": m})["market_attractiveness"]["import_cagr_pct"] is None
    # بلا سلسلةٍ أصلاً يبقى النثرُ احتياطاً كما كان (لا تغيير خارج البند).
    bare = {"trade_flow": {"findings": [prose]}}
    assert P.build_pillar_inputs({"missions": bare})["market_attractiveness"]["import_cagr_pct"] == 21.0


def test_existing_partial_rules_still_hold_under_the_direct_head():
    # سنةُ مرآةٍ أخيرةٌ ناقصة (< 80%) تبقى جزئية، والرأسُ آخرُ مباشرة.
    low = _missions(direct=((2022, 100e6), (2023, 100e6)), mirror=((2024, 50e6),))
    s = P.import_series(low)
    assert s["series"][-1]["partial"] is True
    assert s["head"]["year"] == 2023 and P.base_year(low) == 2023
    assert s["mirror_after_head"] == []                 # الجزئيةُ لها وسمُها الخاص


# ── سجلّ الحقائق ─────────────────────────────────────────────────────────────

def test_ledger_head_and_growth_are_direct():
    import silk_fact_ledger as L
    led = L.build_ledger({"deep_research": {"missions": _missions()}})["entries"]
    assert led["imports_latest_year"]["value"] == 2024
    mi = led["market_imports_usd"]
    assert mi["value"] == 9_170_000.0 and not mi.get("mirrored") and mi["status"] == "observed"
    assert led["import_growth_pct"]["value"] == 89.9
    assert "2019–2024" in led["import_growth_pct"]["note"]
    assert led["import_cagr_pct"]["value"] == 13.7
    # السنةُ الموسومة تبقى في بنود السلسلة (الجدول) — لا تُحذف.
    items = led["imports_latest_year"].get("items") or []
    assert any(p["year"] == 2025 and p["mirrored"] for p in items)


def test_ledger_says_why_mirror_growth_is_not_computed():
    import silk_fact_ledger as L
    m = _missions(direct=(), mirror=((2023, 9e6), (2024, 10e6)))
    led = L.build_ledger({"deep_research": {"missions": m}})["entries"]
    g = led["import_growth_pct"]
    assert g["value"] is None and "مرآة" in g["note"]
    assert led["import_cagr_pct"]["value"] is None


# ── العرض: سطرُ القيمة وسطرُ المرآة ──────────────────────────────────────────

def test_imports_view_heads_with_the_direct_year_and_shows_the_mirror_apart():
    from silk_render import _imports_view
    iv = _imports_view({"markets": []}, {"missions": _missions()}, "ar")
    assert iv["latest_year"] == 2024 and iv["latest_value_usd"] == 9_170_000.0
    assert "2024" in iv["value_line"] and "9.17" in iv["value_line"]
    assert "2025" not in iv["value_line"] and "15.12" not in iv["value_line"]
    assert "89.9" in iv["growth_line"] and "13.7" in iv["growth_line"]
    assert "213" not in iv["growth_line"]
    ml = iv["mirror_line"]
    assert "2025" in ml and "15.12" in ml and "مرآة" in ml
    assert "النمو" in ml                                 # يقول صراحةً إنه خارج حساب النمو


def test_imports_view_labels_a_mirror_head_when_no_direct_figure_exists():
    from silk_render import _imports_view
    m = _missions(direct=(), mirror=((2023, 9e6), (2024, 10e6)))
    iv = _imports_view({"markets": []}, {"missions": m}, "ar")
    assert "2024" in iv["value_line"] and "مرآة" in iv["value_line"]
    assert "growth_line" not in iv
    assert "مرآة" in iv["note"]
    en = _imports_view({"markets": []}, {"missions": m}, "en")
    assert "mirror" in en["value_line"]
    assert not any("؀" <= ch <= "ۿ" for k in ("value_line", "note", "mirror_line")
                   for ch in str(en.get(k) or ""))


def test_imports_view_english_mirror_line_has_no_arabic_script():
    from silk_render import _imports_view
    en = _imports_view({"markets": []}, {"missions": _missions()}, "en")
    assert "2024" in en["value_line"] and "2025" in en["mirror_line"]
    assert not any("؀" <= ch <= "ۿ" for ch in en["mirror_line"])


# ── F3 (أداة القياس): الرأسُ المصلَح يمرّ، والمرآةُ الموسومة بلا مباشرٍ تمرّ ──────

_REPORT = """## 1. الخلاصة التنفيذية

التوصية دخول مشروط. بلغت واردات البحرين من القهوة المحمّصة 9.17 مليون دولار عام 2024
وفق UN Comtrade.

## 3. نظرة عامة على السوق وحجمه

نمت الواردات من 4.83 مليون دولار في 2019 إلى 9.17 مليون دولار في 2024.
"""


def test_f3_passes_on_the_fixed_ledger_head():
    import silk_study_checks as C
    blob = _bahrain_blob()
    blob["deep_research"]["report"] = {"report": _REPORT, "review_cycles": 1,
                                       "unresolved_notes": []}
    doc = C.StudyDoc.from_result(blob)
    f3 = C.check_mirror(doc)
    assert f3.status == C.PASS, f3.items


def test_f3_still_fails_a_mirror_head_while_a_direct_figure_exists():
    import silk_study_checks as C
    ev = ("سجلّ الحقائق — واردات السوق: 15.12 مليون دولار (UN Comtrade (مرآة)، 2025) "
          "من بيانات الدول الشريكة (بيانات مرآة)\n"
          "[المصدر: UN Comtrade] إجمالي واردات السوق 2024: 9,170,000 دولار\n"
          "[المصدر: UN Comtrade (مرآة)] إجمالي واردات السوق 2025 (مرآة): 15,120,000 دولار")
    doc = C.StudyDoc(report=_REPORT, evidence=ev)
    f3 = C.check_mirror(doc)
    assert f3.status == C.FAIL
    assert any(i.get("where") == "سجلّ الحقائق" for i in f3.items)


def test_f3_accepts_a_labelled_mirror_head_when_the_market_declares_nothing():
    import silk_study_checks as C
    ev = ("سجلّ الحقائق — واردات السوق: 10 مليون دولار (UN Comtrade (مرآة)، 2024) "
          "من بيانات الدول الشريكة (بيانات مرآة)\n"
          "سجلّ الحقائق — أحدث سنة واردات: 2024\n"
          "[المصدر: UN Comtrade (مرآة)] إجمالي واردات السوق 2023 (مرآة): 9,000,000 دولار\n"
          "[المصدر: UN Comtrade (مرآة)] إجمالي واردات السوق 2024 (مرآة): 10,000,000 دولار")
    rep = ("## 1. الخلاصة التنفيذية\n\nبلغت واردات السوق نحو 10 مليون دولار في 2024 بتقدير "
           "من بيانات الدول الشريكة (بيانات مرآة).\n")
    f3 = C.check_mirror(C.StudyDoc(report=rep, evidence=ev))
    assert f3.status == C.PASS, f3.items


# ── أرقام الدراسة (study_numbers): الاتجاهُ والتفكيكُ لا يقرآن المرآة ───────────

def _case_series(direct=_DIRECT, mirror=_MIRROR):
    from silk_study_case import build_case
    return build_case(_bahrain_blob(direct, mirror))["imports"]["series"]


def test_study_case_growth_window_excludes_the_mirror_year_after_the_head():
    rows = {r["year"]: r for r in _case_series()}
    assert rows[2025]["mirrored"] and not rows[2025]["in_growth_window"]
    assert all(rows[y]["in_growth_window"] for y in (2019, 2022, 2023, 2024))
    from silk_study_numbers import series_shape
    shape = series_shape(list(rows.values()))
    assert shape["y_last"] == 2024 and shape["v_last"] == 9.2


def test_study_case_refused_mirror_growth_closes_the_window():
    rows = _case_series(direct=(), mirror=((2023, 9e6), (2024, 10e6)))
    assert rows and not any(r["in_growth_window"] for r in rows)
    from silk_study_numbers import decomposition, series_shape
    assert series_shape(rows)["g_first_last"] is None
    kg_rows = [dict(r, kg=1000.0 * (i + 1)) for i, r in enumerate(rows * 2)]
    assert decomposition(kg_rows)["variant"] == "not_decomposable"


# ── المراجعة الذاتية (§58) على الفرق: أسطحٌ بقيت تقرأ سنة المرآة ─────────────────

def test_review_market_size_component_is_the_direct_head():
    ms = P.build_components({"missions": _missions()})["market_size"]
    assert ms["value"] == 9_170_000.0 and ms["data_year"] == 2024
    assert "مرآة" not in ms["source"] and ms["confidence"] == 0.9


def test_review_study_mode_reads_the_head_and_labels_the_mirror_row():
    from silk_study_case import build_case
    from silk_study_render import render_study
    case = build_case(_bahrain_blob())
    assert case["imports"]["head_year"] == 2024
    md = render_study(case)
    assert "**أحدث سنة بيانات تجارية مكتملة:** 2024" in md
    assert "بين عامي 2024 و2024" not in md and "بين عامي 2023 و2024" in md
    assert "| 2025 | 15.1 (تقدير من بيانات الشركاء) |" in md
    assert "بيانات مرآة" in md and "لا تدخل حساب النمو" in md


def test_review_ledger_mirror_head_year_is_labelled_weak():
    import silk_fact_ledger as L
    m = _missions(direct=(), mirror=((2023, 9e6), (2024, 10e6)))
    e = L.build_ledger({"deep_research": {"missions": m}})["entries"]["imports_latest_year"]
    assert e["value"] == 2024 and e.get("mirrored") and e["status"] == "weak"
    assert "مرآة" in L.render_value(e, "ar")


def test_review_decomposition_excludes_only_years_inside_the_window():
    from silk_study_numbers import decomposition
    rows = [{"year": y, "value_musd": v, "kg": kg, "complete": True, "in_growth_window": w,
             "weight_anomaly": anomaly}
            for y, v, kg, w, anomaly in ((2020, 4.0, 400e3, True, False),
                                         (2021, 5.0, 480e3, True, False),
                                         (2022, 6.0, 560e3, True, False),
                                         (2023, 9.0, 900e3, False, True))]
    d = decomposition(rows)
    assert d["variant"] != "decomposable_with_excluded_last" and d["y_excl"] is None
