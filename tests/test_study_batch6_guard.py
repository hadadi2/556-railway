"""الدفعة ٦ — الحراسة والتعميم (P6-2…P6-7) لنمط «دراسة السوق»."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── P6-2 ───────────────────────────────────────────────────────────────
def _dp(value, note="", status=""):
    from silk_data_layer import DataPoint
    return DataPoint(value, "World Bank", 0.95 if value is not None else 0.0, note, "2026-09-28",
                     status=status, data_year=2023 if value is not None else None)


def test_public_indicator_retries_then_succeeds_with_unit_url_status():
    import silk_data_layer as D
    seq = [_dp(None, "PV.EST fetch failed for MYS: boom"), _dp(None, status="fetch_failed"), _dp(0.3, "PV.EST (2023)")]
    with patch.object(D, "_world_bank_for_year", side_effect=seq) as m:
        dp = D.world_bank("MYS", "PV.EST", 2023)
    assert m.call_count == 3 and dp.value == 0.3
    assert dp.status == "ok" and dp.unit and dp.url.endswith("/PV.EST") and dp.data_year == 2023


def test_permanent_failure_is_logged_not_silent():
    import silk_data_layer as D
    import silk_ops_log
    logged = []
    D._PUBLIC_FAIL_LOGGED.clear()
    with patch.object(D, "_world_bank_for_year", return_value=_dp(None, "x fetch failed for MYS")) as m, \
            patch.object(silk_ops_log, "record_error", side_effect=lambda k, r, c=None: logged.append(k)):
        dp = D.world_bank("MYS", "PA.NUS.FCRF", None)
    assert m.call_count == 3 and dp.value is None and dp.status == "fetch_failed"
    assert logged == ["data_pipeline_error"]


def test_no_published_value_is_not_retried():
    import silk_data_layer as D
    with patch.object(D, "_world_bank_for_year", return_value=_dp(None, "PV.EST: no value returned for XXX")) as m:
        D.world_bank("XXX", "PV.EST", None)
    assert m.call_count == 1


def test_other_indicators_keep_single_attempt():
    import silk_data_layer as D
    with patch.object(D, "_world_bank_for_year", return_value=_dp(None, "NY.GDP fetch failed for MYS")) as m:
        D.world_bank("MYS", "NY.GDP.MKTP.KD.ZG", None)
    assert m.call_count == 1


# ── P6-3 ───────────────────────────────────────────────────────────────
def test_stale_verification_is_flagged_and_fresh_kept():
    import datetime as dt
    from silk_study_case import verified_label
    today = dt.date(2026, 9, 28)
    assert verified_label("2026-09-23", today) == "2026-09-23"
    assert verified_label("2025-12-01", today) == "2025-12-01 (يُعاد التحقق)"
    assert verified_label("", today) is None


def test_live_case_requirement_rows_carry_verification_and_tax_authority():
    from silk_study_case import build_case
    c = build_case({"deep_research": {}, "product": "قهوة", "hs_code": "090121", "market": "Malaysia"})
    rows = c["requirements"]["rows"]
    assert rows and all(r["verified_at"] is None or r["verified_at"].startswith("20") for r in rows)
    # الضريبة بلا معدل مثبت: الجهة التي يُحدَّد من جدولها المعدل تصل القالب (لا تسقط الفقرة).
    assert c["tariff"]["sst_authority"] and "الجمارك" in c["tariff"]["sst_authority"]


# ── P6-4 ───────────────────────────────────────────────────────────────
def test_singapore_is_tagged_reexport_hub_in_live_supplier_rows():
    from silk_study_case import build_case, reexport_hubs
    import silk_deep_pillars
    assert "SGP" in reexport_hubs()
    rows = [{"partner": "Singapore", "share": 16.0}, {"partner": "Indonesia", "share": 12.0},
            {"partner": "Viet Nam", "share": 10.0}]
    with patch.object(silk_deep_pillars, "top_supplier_shares", return_value=(rows, {"year": 2024})):
        c = build_case({"deep_research": {}, "product": "قهوة", "hs_code": "090121", "market": "Malaysia"})
    kinds = {t["iso3"]: t["kind"] for t in c["suppliers"]["top"]}
    assert kinds.get("SGP") == "reexport_hub" and kinds.get("IDN") is None   # لا «منتج» مُفترَض
    from silk_study_numbers import compute
    assert compute(c)["hub"]["iso3"] == "SGP"


# ── P6-5 ───────────────────────────────────────────────────────────────
def test_golden_malaysia_item8_checks_pass_on_frozen_fixture_render():
    """يصيّر الـfixture المجمَّد (الحقول مثبّتة يدوياً) — المسار الحي تحميه اختبارات
    build_case في الدفعات ٣–٦ لا هذا الاختبار."""
    from tools.golden_set import study_check
    assert study_check("malaysia_coffee") == []


def test_golden_check_fails_when_a_source_is_removed():
    from tools.golden_set import study_check
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "samples", "golden_malaysia_coffee_study.md"), encoding="utf-8") as f:
        ref = f.read()
    assert study_check("malaysia_coffee", ref) == []
    fails = study_check("malaysia_coffee", ref.replace("وفق تقديرات صندوق النقد الدولي", "تقريباً"))
    assert fails and fails[0].startswith("gdp_imf")


def test_golden_file_has_nineteen_checks_and_context_tags():
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "evals", "golden_set", "malaysia_coffee.json"), encoding="utf-8") as f:
        spec = json.load(f)
    assert len(spec["checks"]) == 19
    assert {t["tag"] for t in spec["context_tags"]} == {"سياقي", "قاعدة تقديرية"}


# ── P6-6 حالتان مختلفتان جذرياً ──────────────────────────────────────────
# فئات حرجة لا تُقبل في أي حالة (الأخرى — جدول/قسم ناقص — فجوات بيانات معلنة).
CRITICAL = {"slot_leak", "heading_missing", "heading_not_literal", "heading_order", "forbidden",
            "claim_status_conflict", "source_missing", "provisional_unmarked", "bare_term",
            "hhi_form", "exporter_benefit", "border_as_reference", "list_outside_table"}


def test_non_food_no_halal_case_polymers_turkey_renders_without_critical_violations():
    from tools.canonical_turkey_polymers import turkey_polymers_research_blob
    from silk_study_case import build_case
    from silk_study_linter import lint
    from silk_study_render import render_study
    c = build_case(turkey_polymers_research_blob(), exporter_type="manufacturer", segment=None)
    assert c["market"]["iso3"] == "TUR" and c["product"]["hs"].startswith("39")
    md = render_study(c, {})
    bad = [v for v in lint(md, exporter_type="manufacturer") if v["rule"] in CRITICAL]
    assert not bad, bad
    assert "حلال" not in md.split("## رابعاً")[1].split("## خامساً")[0] or "لا يُلزم" in md


def test_defer_and_no_entry_cases_render_without_critical_violations():
    import json
    from silk_study_linter import lint
    from silk_study_render import load_knowledge, render_study
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "evals", "golden_set", "malaysia_coffee_fixture.json"), encoding="utf-8") as f:
        base = json.load(f)
    for dec in ("defer", "no_entry"):
        c = json.loads(json.dumps(base))
        c["decision"]["type"] = dec
        md = render_study(c, load_knowledge("090121", "MY"))
        bad = [v for v in lint(md) if v["rule"] in CRITICAL]
        assert not bad, (dec, bad)
        assert ("إرجاء" if dec == "defer" else "عدم") in md


def test_study_pdf_export_uses_the_pdf_gate(tmp_path):
    import json
    import silk_reports
    from silk_study_export import study_docx
    from tests.pdf_gate import pdf_gate
    pdf_gate("تحويل دراسة السوق")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "evals", "golden_set", "malaysia_coffee_fixture.json"), encoding="utf-8") as f:
        case = json.load(f)
    docx, _ = study_docx({"study_case": case}, str(tmp_path / "s.docx"))
    try:
        pdf = silk_reports.docx_to_pdf(docx, str(tmp_path / "s.pdf"))
    except RuntimeError as exc:
        from tests.pdf_gate import pdf_engine_broken
        pdf_engine_broken(str(exc))
    with open(pdf, "rb") as fh:
        assert fh.read(5) == b"%PDF-"


def test_fallback_transient_failure_is_retried_and_logged():
    import silk_data_layer as D
    seq = [_dp(None, "LP.LPI.OVRL.XQ: no value returned for MYS"), _dp(None, "x fetch failed for MYS")] * 3
    D._PUBLIC_FAIL_LOGGED.clear()
    with patch.object(D, "_world_bank_for_year", side_effect=seq) as m, \
            patch("silk_ops_log.record_error"):
        dp = D.world_bank("MYS", "LP.LPI.OVRL.XQ", 2023)
    assert m.call_count == 6 and dp.status == "fetch_failed"


def test_open_circuit_is_not_retried():
    import silk_data_layer as D
    with patch.object(D, "_world_bank_for_year", return_value=_dp(None, "PV.EST fetch failed for MYS: CircuitOpen")) as m:
        D.world_bank("MYS", "PV.EST", None)
    assert m.call_count == 1


def test_one_ops_row_per_market_per_day():
    import silk_data_layer as D
    D._PUBLIC_FAIL_LOGGED.clear()
    logged = []
    with patch.object(D, "_world_bank_for_year", return_value=_dp(None, "x fetch failed for MYS")), \
            patch("silk_ops_log.record_error", side_effect=lambda k, r, c=None: logged.append(k)):
        for ind in ("PV.EST", "RL.EST", "RQ.EST", "PA.NUS.FCRF"):
            D.world_bank("MYS", ind, None)
    assert logged == ["data_pipeline_error"]


def test_wgi_mission_finding_keeps_unit_url_status():
    import silk_data_layer as D
    import silk_missions as M
    ok = _dp(0.3, "PV.EST (2023)")
    with patch.object(D, "_world_bank_for_year", return_value=ok):
        out = M._wgi_governance_datapoints("MYS")
    pv = next(d for d in out if "PV.EST" in d.note)
    assert pv.unit and pv.url and pv.status == "ok" and pv.data_year == 2023


def test_sources_are_normalized_and_attributed_to_the_real_source():
    from silk_study_case import _used_sources
    fx = {"value": 4.2, "year": 2025, "source": "Bank Negara Malaysia"}
    gdp = {"value": 4.1, "year": 2025, "source": "IMF WEO"}
    dr = {"missions": {"m": {"findings": [{"value": 1, "source": "World Bank"}]}}}
    out = _used_sources(dr, dr["missions"], fx, None, None, gdp)
    assert out == sorted({"البنك الدولي", "Bank Negara Malaysia", "صندوق النقد الدولي"})


def test_mixed_sentence_citation_is_still_checked():
    from silk_study_linter import lint
    md = ("## الملخص التنفيذي\n\nبلغ سعر الصرف 4.4 وفق البنك الدولي، وتعذّر جلب مؤشر الحوكمة.\n\n"
          "**المصادر:** UN Comtrade.\n")
    assert any(v["rule"] == "source_missing" for v in lint(md))
