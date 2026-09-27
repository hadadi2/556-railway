"""الدفعة ١ — الحراس الصغار: P1-10 (انهيار المنافسين)، P1-11 (بوابة HS والصفات
الوصفية)، P6-1 (رفض العناصر النائبة في تصدير العميل). كل واحد يقفل النتيجة
F-08 / F-31 / F-18 من docs/audit/STUDY_MODE_AUDIT.md."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── P1-10 ──────────────────────────────────────────────────────────────────
def test_competitor_fetch_failure_tries_mirror_then_declares_gap_without_crash():
    from silk_data_layer import DataPoint
    from silk_llm_runtime import competition_summary_findings
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market("Malaysia")
    failed = [DataPoint(None, "UN Comtrade", 0.0, "fetch failed", "2026-09-27", status="fetch_failed")]
    calls = {"mirror": 0}

    def mirror(hs, m49, y):
        calls["mirror"] += 1
        return []
    with patch("silk_data_layer_v2.market_competitors", return_value=failed), \
            patch("silk_data_layer_v2.market_competitors_mirror", side_effect=mirror):
        out = competition_summary_findings("090121", ref, year=2024)
    assert calls["mirror"] == 1                       # الاحتياط جُرِّب فعلاً
    assert len(out) == 1 and out[0].value is None      # فجوة معلنة لا انهيار
    assert "تعذّر الجلب" in out[0].note


# ── P1-11 ──────────────────────────────────────────────────────────────────
def test_hs_gate_accepts_descriptor_the_code_itself_carries():
    from silk_hs_confirm import confirm_hs
    r = confirm_hs("قهوة محمصة غير منزوعة الكافيين", "090121")
    assert r["confirmed"] is True and not r["missing_terms"]


def test_hs_gate_still_rejects_the_original_peanut_butter_regression():
    from silk_hs_confirm import confirm_hs
    r = confirm_hs("زبدة الفول السوداني", "040510")
    assert r["confirmed"] is False


# ── P6-1 ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("leak", [
    "[سمِّ المدخل من السطر أعلاه]", "يُدرج لاحقاً", "TODO: أكمل", "placeholder text", "<الحكم المحسوب>",
])
def test_client_guard_refuses_placeholders(leak):
    from silk_reports import _client_forbidden_hits
    hits = _client_forbidden_hits("نص سليم " + leak + " نص سليم", "ar")
    assert hits and hits[0].startswith("placeholder")


def test_client_guard_keeps_plain_prose_and_html_tags():
    from silk_reports import _client_forbidden_hits
    assert not [h for h in _client_forbidden_hits("واردات ماليزيا 89.4 مليون دولار <b>2024</b>.", "ar")
                if h.startswith("placeholder")]
