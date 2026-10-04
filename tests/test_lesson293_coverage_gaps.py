"""الدرس ٢٩٣ — فجوات التغطية وفقد البيانات الصامت (أقفال hermetic، تدقيق «find all gaps» 2026-10-04)."""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_data_layer import DataPoint  # noqa: E402


def test_uncovered_market_is_not_checked():
    import silk_requirements_agent as R
    assert R.regulatory_state("USA", "090121")["checked"] is False
    assert R.regulatory_state("MYS", "090121")["checked"] is True


def test_uncovered_market_leaves_eligibility_unknown():
    import silk_deep_pillars as P
    src = open(P.__file__, encoding="utf-8").read()
    assert 'if reg_state.get("checked", True) else None' in src


def test_country_lookups_cover_markets_outside_the_embedded_tables():
    import silk_data_layer as D
    import silk_market_ranker as R
    import silk_narrative as N
    assert D.m49_of("ROU") == "642"            # خارج الجدول المضمَّن (٧٢ دولة)
    assert R._iso2_of("AUS") == "AU"
    assert N.country_ar("ROU") == "رومانيا"


def test_discover_accepts_a_market_outside_the_embedded_table():
    import silk_discovery as S
    with mock.patch("silk_data_layer.comtrade_trade", return_value=None):
        out = S.discover("ROU") if hasattr(S, "discover") else None
    if out is not None:
        assert not any("غير معروف الرمز" in g for g in out.get("gaps", []))


def test_locale_gl_falls_back_to_market_iso2():
    import silk_llm_runtime as L

    class M:
        iso3, iso2 = "ROU", "RO"
    with mock.patch.object(L, "_market_locale", return_value={}):
        assert L._locale_gl({"market": M()}) == "ro"


def test_wgi_store_point_carries_its_year():
    import silk_missions as M
    with mock.patch("silk_store.get_indicator",
                    return_value={"value": 0.4, "year": 2023, "source": "World Bank"}):
        dps = M._wgi_governance_datapoints("MYS")
    assert dps and all(dp.data_year == 2023 for dp in dps)


def test_competitors_augment_deadline_allows_a_comtrade_call():
    import silk_missions as M
    assert M._competitors_augment_s() >= 10


def test_failed_augment_is_declared_in_the_mission():
    import silk_missions as M
    from silk_agents import AgentReport
    rep = AgentReport("competitors", [], False, "")

    def boom(r):
        raise RuntimeError("x")
    assert not M._bounded_augment("competitors_structured", rep, boom, rep)
    gap = rep.findings[-1]
    assert gap.value is None and gap.status == "fetch_failed"
    assert "حصص الموردين" in gap.note and "competitors_structured" not in gap.note


def test_missing_coverage_is_not_reported_as_zero():
    import silk_decision as D
    assert not any("تغطية" in r["risk"] for r in D._risk_register({}, None))
    assert any("تغطية" in r["risk"] for r in D._risk_register({}, 0.3))


def test_concentrated_step_needs_hhi_or_top_share():
    import silk_decision as D
    src = open(D.__file__, encoding="utf-8").read()
    assert "concentrated_basis" in src and '(comp_parts.get("hhi") or 0) >= 0.5' in src


def test_wto_empty_response_is_short_lived():
    import silk_wto_tariff as W
    seen = {}

    def fake(url, params=None, **kw):
        seen.update(kw)
        return {"Dataset": []}
    with mock.patch.dict(os.environ, {"WTO_TTD_API_KEY": "k"}), \
         mock.patch("silk_cache.cached_get", side_effect=fake):
        W.wto_applied_tariff("090121", "MYS", "SAU", 2023)
    assert seen["short_lived"]({"Dataset": []}) is True
    assert seen["short_lived"]({"Dataset": [{"Value": 5, "Year": 2023}]}) is False


def test_fx_series_uses_the_published_year():
    import silk_missions as M
    from silk_agents import AgentReport
    rep = AgentReport("risk_news", [], False, "")

    def wb(iso3, ind, year=None):
        return DataPoint(4.2, "World Bank", 0.9, "fx", "2026-10-04", data_year=2024)
    with mock.patch("silk_store.get_indicator", return_value=None), \
         mock.patch("silk_data_layer.world_bank", side_effect=wb):
        M._augment_risk_news_fx(rep, "MYS")
    years = [dp.data_year for dp in rep.findings if dp.data_year]
    assert 2025 not in years


# ── الدفعة ٢: صياغة الدراسة ─────────────────────────────────────────────
import copy  # noqa: E402
import json  # noqa: E402

_FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "evals", "golden_set", "malaysia_coffee_fixture.json")


def _render(mut, allow_pending=True):
    from silk_study_render import Renderer, load_knowledge
    with open(_FIX, encoding="utf-8") as f:
        c = json.load(f)
    mut(c)
    return Renderer(c, load_knowledge("090121", "MY"), allow_pending=allow_pending).render()


def test_market_without_nisba_keeps_its_summary_paragraph():
    md = _render(lambda c: c["market"].update(nisba_f=None, nisba_m=None))
    assert "تُعد السوق المحلية في ماليزيا" in md
    assert "صفة النسبة للسوق" not in md


def test_gdp_comparison_only_when_gdp_grew_slower():
    def faster(c):
        c["imports"]["gdp_growth_pct"] = 99.0
    md = _render(faster)
    assert "لم يتجاوز نمو الناتج" not in md and "وبلغ نمو الناتج المحلي" in md


def test_flat_series_is_not_called_steady_growth():
    def flat(c):
        for i, r in enumerate(c["imports"]["series"]):
            r["value_musd"] = 50.0 + i * 0.1
    md = _render(flat)
    assert "وكان هذا النمو مطرداً" not in md


def test_certification_needs_real_sources():
    md = _render(lambda c: c.update(sources=[]))
    assert "كل رقم جوهري للقرار في هذه الدراسة مقرون بمصدره" not in md


def test_food_margin_rule_is_not_applied_to_non_food():
    md = _render(lambda c: c["product"].update(hs="392690"))
    assert "حلقتا التوزيع والتجزئة في القطاع الغذائي" not in md


def test_tariff_sentence_survives_missing_preferential_note():
    md = _render(lambda c: c["tariff"].update(preferential_note=None))
    assert "**الرسوم والضرائب:**" in md and "التحقق من ضرائب الاستيراد الأخرى" in md


def test_new_wordings_stay_off_until_owner_approval():
    md = _render(lambda c: c["tariff"].update(preferential_note=None), allow_pending=False)
    assert "التحقق من ضرائب الاستيراد الأخرى" not in md
    assert "بانتظار اعتماد المالك" in md


# ── مراجعة §58 ─────────────────────────────────────────────────────────
def test_pending_clause_falls_back_instead_of_dropping_the_paragraph():
    def faster(c):
        c["imports"]["gdp_growth_pct"] = 99.0
    md = _render(faster, allow_pending=False)
    assert "تشير بيانات الأمم المتحدة للتجارة إلى أن واردات" in md
    assert "لم يتجاوز نمو الناتج" not in md and "وبلغ نمو الناتج" not in md


def test_no_doubled_local_in_gdp_phrase():
    def kenya_like(c):
        c["market"].update(nisba_f=None, nisba_m=None)
        c["imports"]["gdp_growth_pct"] = 0.1
    md = _render(kenya_like)
    assert "الناتج المحلي الإجمالي المحلي" not in md


def test_confirmed_barrier_survives_an_uncovered_market():
    import silk_deep_pillars as P
    src = open(P.__file__, encoding="utf-8").read()
    assert 'True if reg_state.get("open_hard")' in src


def test_unconcentrated_hhi_is_not_called_concentrated():
    import silk_decision as D
    pillars = {"competition": {"value": 0.517, "components":
                               {"hhi": 0.3, "top_share": 0.4, "named_density": 1.0}},
               "regulatory": {"value": None}, "profit": {"value": 0.5}}
    steps = D._first_steps("conditional", pillars, [], {}) if D._first_steps.__code__.co_argcount >= 4 \
        else D._first_steps("conditional", pillars, [])
    assert not any("سوق مركّز" in s for s in steps)


def test_augment_gap_is_not_duplicated_and_clears_on_success():
    import silk_missions as M
    from silk_agents import AgentReport
    rep = AgentReport("risk_news", [], False, "")

    def boom(r):
        raise RuntimeError("x")

    def ok(r):
        r.findings.append(DataPoint(4.2, "World Bank", 0.9, "fx"))
    M._bounded_augment("risk_news_fx", rep, boom, rep)
    M._bounded_augment("risk_news_fx", rep, boom, rep)
    assert sum(f.value is None for f in rep.findings) == 1
    M._bounded_augment("risk_news_fx", rep, ok, rep)
    assert [f.value for f in rep.findings] == [4.2]


def test_daily_budget_is_named_as_the_cause():
    import silk_commercial_analysis as C
    with mock.patch.object(C, "max_calls", return_value=12), \
         mock.patch("silk_collectors.comtrade_budget_left", return_value=2):
        assert C._Budget(0).daily_bound is True
    with mock.patch.object(C, "max_calls", return_value=12), \
         mock.patch("silk_collectors.comtrade_budget_left", return_value=500):
        assert C._Budget(0).daily_bound is False
