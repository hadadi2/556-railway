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
