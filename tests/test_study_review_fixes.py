"""إصلاحات المراجعة الكاملة لنمط الدراسة (#54 → PR #55)."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _case():
    with open(os.path.join(_ROOT, "evals", "golden_set", "malaysia_coffee_fixture.json"), encoding="utf-8") as f:
        return json.load(f)


# ── (٢) أسماء المزوّدين في المصادر ─────────────────────────────────────────
def test_vendor_names_never_reach_study_sources():
    from silk_study_case import _used_sources, public_source
    assert public_source("Web Search (Serper) — zuba.com.my") == "zuba.com.my"
    assert public_source("GDELT") == "بحث الويب"
    assert public_source("UN Comtrade") == "UN Comtrade"
    dr = {"missions": {"m": {"findings": [{"value": 1, "source": "Web Search (Serper) — shop.my"}]}}}
    out = _used_sources(dr, dr["missions"], None, None, None, None)
    assert out == ["shop.my"]


def test_study_docx_exports_on_a_live_shape_with_web_sources(tmp_path):
    from silk_study_export import study_docx
    c = _case()
    c["sources"] = c["sources"] + ["shop.my"]
    path, _ = study_docx({"study_case": c}, str(tmp_path / "s.docx"))
    assert os.path.exists(path)


def test_docx_guard_checks_table_cells_too(tmp_path):
    import pytest
    import silk_reports as R
    from silk_study_export import markdown_to_docx
    md = "## الملخص التنفيذي\n\nنص.\n\n| المنتج | المصدر |\n|---|---|\n| بن | Serper |\n"
    with pytest.raises(R.ReportGateError):
        markdown_to_docx(md, str(tmp_path / "x.docx"))


# ── (٣) أرقام البعثات الحية في raw_evidence ────────────────────────────────
def test_live_claim_findings_expose_typed_numbers_from_raw_evidence():
    from silk_study_case import _findings, build_case
    claim = {"value": "التعرفة صفر وفق WITS", "source": "LLMAgent", "confidence": 0.8,
             "raw_evidence": [{"value": 0.0, "source": "WITS", "note": "تعرفة MFN 090121 (2024)",
                               "confidence": 0.9, "data_year": 2024, "status": "ok"},
                              {"value": 4.4, "source": "World Bank", "note": "PA.NUS.FCRF (2025)",
                               "confidence": 0.95, "data_year": 2025}]}
    dr = {"missions": {"tariffs_agreements": {"findings": [claim]}}}
    vals = [f.get("value") for f in _findings(dr, "tariffs_agreements")]
    assert 0.0 in vals and 4.4 in vals and "التعرفة صفر وفق WITS" in vals


def test_live_tariff_is_read_from_raw_evidence_and_not_confused_with_fx():
    from silk_study_case import build_case
    claim = {"value": "التعرفة صفر", "source": "LLMAgent", "confidence": 0.8,
             "raw_evidence": [{"value": 4.4, "source": "World Bank", "note": "PA.NUS.FCRF (2025)",
                               "confidence": 0.95, "data_year": 2025},
                              {"value": 0.0, "source": "WITS", "note": "تعرفة MFN 090121 (2024)",
                               "confidence": 0.9, "data_year": 2024}]}
    c = build_case({"deep_research": {"missions": {"tariffs_agreements": {"findings": [claim]}}},
                    "product": "قهوة", "hs_code": "090121", "market": "Malaysia"})
    assert c["tariff"]["status"] == "exempt" and c["tariff"]["rate_pct"] == 0.0


# ── (٤) حصة السعودية خارج أول عشرة ─────────────────────────────────────────
def test_saudi_outside_top_rows_is_unknown_not_absent():
    import silk_deep_pillars
    from silk_study_case import build_case
    from silk_study_numbers import compute
    rows = [{"partner": "Indonesia", "share": 20.0}, {"partner": "Viet Nam", "share": 15.0}]
    with patch.object(silk_deep_pillars, "top_supplier_shares", return_value=(rows, {"year": 2024})):
        c = build_case({"deep_research": {}, "product": "قهوة", "hs_code": "090121", "market": "Malaysia"})
    assert c["suppliers"]["saudi_share_pct"] is None
    assert compute(c)["saudi_absent"] is False
    full = rows + [{"partner": "Italy", "share": 65.0}]
    with patch.object(silk_deep_pillars, "top_supplier_shares", return_value=(full, {"year": 2024})):
        c2 = build_case({"deep_research": {}, "product": "قهوة", "hs_code": "090121", "market": "Malaysia"})
    assert c2["suppliers"]["saudi_share_pct"] == 0.0 and compute(c2)["saudi_absent"] is True


# ── (٥) لا «سوق مستقرة» ولا «لا ضغط» بلا دليل ──────────────────────────────
def test_no_unbacked_stability_or_inflation_claims():
    from silk_study_render import render_study
    c = _case()
    c["market"]["iso2"] = "XX"                      # بلا ملف معرفة
    c["macro"]["inflation_pct"] = 12.0
    out = render_study(c, {}, )
    assert "سوقاً مستقرة" not in out
    assert "لا تُظهر ضغطاً على القوة الشرائية" not in out
