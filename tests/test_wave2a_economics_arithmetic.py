"""الموجة 2أ — الحساب الموحّد: hhi على مقياس 0–10000 + معادلة التكلفة الواصلة
الواحدة + فحصا Gate C التحذيريان. هرمتي بالكامل.
"""
from __future__ import annotations

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_economics as E  # noqa: E402


# ── hhi — المقياس الواحد ────────────────────────────────────────────────────

def test_hhi_canonical_scale_0_10000():
    # سوق منقسم مناصفةً: 50² + 50² = 5000
    assert E.hhi([50, 50]) == 5000
    # احتكار كامل: 100² = 10000
    assert E.hhi([100]) == E.HHI_SCALE_MAX
    assert E.hhi([60, 40]) == 5200


def test_hhi_empty_is_declared_gap_not_zero():
    assert E.hhi([]) is None
    assert E.hhi(None) is None


def test_hhi_drops_invalid_values_never_zeroes():
    assert E.hhi([50, "x", None, 50]) == 5000
    assert E.hhi([-5, 100]) == 10000  # السالب يُسقَط لا يُصفَّر


def test_hhi_from_fractions_is_the_only_scale_conversion():
    assert E.hhi_from_fractions([0.5, 0.5]) == 5000
    assert E.hhi_from_fractions([]) is None


def test_hhi_is_high_threshold_2500():
    assert E.hhi_is_high(2501) and not E.hhi_is_high(2500)
    assert not E.hhi_is_high(None) and not E.hhi_is_high("x")


# ── التكلفة الواصلة — المعادلة الواحدة ──────────────────────────────────────

def test_landed_cost_formula_and_none_tariff():
    assert E.landed_cost(10, 2, 25) == 15.0
    assert E.landed_cost(10, 2, None) == 12.0  # فجوة تعرفة = بلا جمارك معلنة


def test_correlation_imports_the_canonical_formula():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "correlation.py"), encoding="utf-8").read()
    assert "from silk_economics import landed_cost" in src, (
        "correlation.py لم يعد يستورد المعادلة القانونية — نسختان ستتباعدان")
    # ولا معادلة مكرّرة محلياً:
    assert "* (1 + tariff_pct / 100.0)" not in src


def test_silk_economics_is_stdlib_only():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tree = ast.parse(open(os.path.join(root, "silk_economics.py"),
                          encoding="utf-8").read())
    for node in ast.walk(tree):
        mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                else [node.module or ""] if isinstance(node, ast.ImportFrom)
                else [])
        for m in mods:
            assert not m.startswith(("requests", "urllib", "http", "socket")), (
                f"silk_economics يستورد مكتبة شبكة: {m}")


# ── فحصا Gate C — تحذيريان لا حاجبان ────────────────────────────────────────

def test_hhi_scale_check_flags_fractional_value():
    import silk_quality_gate as Q
    dr = {"report": {"text": "المشهد التنافسي: HHI 0.31 يشير إلى تركّز."},
          "missions": {}, "verdict": {}}
    f = Q._check_hhi_scale(dr)
    assert f and f[0]["check"] == "hhi_wrong_scale" and f[0]["repairable"]
    assert "hhi_wrong_scale" not in Q.FAIL_TRIGGER_CHECKS
    clean = {"report": {"text": "HHI 940 — مشهد مفتّت."}, "missions": {}}
    assert Q._check_hhi_scale(clean) == []


def test_cagr_recompute_fires_only_on_structural_series():
    import silk_quality_gate as Q
    series = [{"year": 2020, "value": 100.0}, {"year": 2024, "value": 200.0}]
    # الصحيح: n = 4 → ‎18.9%‎؛ المعلن 26.0 (خطأ n=3 الكلاسيكي) → يُلتقط.
    dr_bad = {"missions": {"m": {"findings": [
        {"series": series, "cagr_pct": 26.0}]}}, "report": {"text": ""}}
    f = Q._check_cagr_recompute(dr_bad)
    assert f and f[0]["check"] == "cagr_recompute_mismatch"
    assert "cagr_recompute_mismatch" not in Q.FAIL_TRIGGER_CHECKS
    dr_ok = {"missions": {"m": {"findings": [
        {"series": series, "cagr_pct": 18.9}]}}, "report": {"text": ""}}
    assert Q._check_cagr_recompute(dr_ok) == []
    # بلا بنية = صمت (لا تحليل نثر).
    dr_prose = {"missions": {"m": {"findings": [
        {"value": 26.0, "note": "CAGR 26%"}]}}, "report": {"text": ""}}
    assert Q._check_cagr_recompute(dr_prose) == []


# ── الموجة 2ب — تبديل مواقع النداء إلى المقياس الموحّد ──────────────────────

def test_research_hhi_now_on_canonical_scale():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_research.py"),
        encoding="utf-8").read()
    assert "from silk_economics import hhi" in src
    assert "sum((s / 100.0) ** 2" not in src   # الحساب المحلي القديم أُزيل
    assert ">2500" in src and ">0.25" not in src


def test_decision_normalization_mathematically_identical():
    """المقام 5000 على 0–10000 ≡ 0.5 على 0–1 حرفياً — لا تغيّر درجة."""
    import silk_decision as D
    old = min(1.0, 0.31 / 0.5)          # المسار القديم على كسر 0.31
    new = D._clip(3100 / 5000.0)        # نفس السوق على المقياس الموحّد
    assert abs(old - new) < 1e-12
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_decision.py"),
        encoding="utf-8").read()
    assert "hhi_is_high" in src and "hhi > 0.25" not in src
