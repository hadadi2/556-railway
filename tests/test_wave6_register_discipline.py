"""الموجة ٦ — انضباط السجل اللغوي (طبقات الأدلة نحوياً، بلا شارات — WS10
سليم) + سجل الفشل الموحّد (الجزء ٩). هرمتي.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_quality_gate as Q  # noqa: E402
import silk_style_contract as S  # noqa: E402


def test_verb_rule_extends_both_contracts_not_replaces():
    assert S.EPISTEMIC_VERB_RULE in S.ACADEMIC_WRITER_CONTRACT
    assert S.EPISTEMIC_VERB_RULE in S.WRITER_STYLE_CONTRACT
    # D-23: العقد الأكاديمي القائم لم يُستبدل — سطره المميز باقٍ.
    assert "عقد السجل الأكاديمي" in S.ACADEMIC_WRITER_CONTRACT


def test_verb_rule_uses_no_visible_badges_or_tier_words():
    # WS10: لا شارات ✓/◐/○ في القاعدة نفسها.
    for ch in ("✓", "◐", "○"):
        assert ch not in S.EPISTEMIC_VERB_RULE


def test_epistemic_check_fires_on_assertive_parameterized_number():
    dr = {"economics": {"reverse_solve": {
        "max_exw": 4.46, "scenarios": [{"scenario": "متوسط"}]}},
        "report": {"text": "يبلغ أقصى سعر المصنع 4.46 دولاراً للوحدة."}}
    f = Q._check_epistemic_verb_discipline(dr)
    assert f and f[0]["repairable"] is True
    assert "epistemic_verb_discipline" not in Q.FAIL_TRIGGER_CHECKS


def test_epistemic_check_quiet_with_conditional_framing():
    dr = {"economics": {"reverse_solve": {
        "max_exw": 4.46, "scenarios": [{"scenario": "متوسط"}]}},
        "report": {"text": "بافتراض هامش الموزّع 20%، أقصى سعر المصنع 4.46."}}
    assert Q._check_epistemic_verb_discipline(dr) == []


def test_epistemic_check_quiet_when_no_parameters():
    dr = {"economics": {"reverse_solve": {"max_exw": 8.0, "scenarios": []}},
          "report": {"text": "يبلغ أقصى سعر المصنع 8.0."}}
    assert Q._check_epistemic_verb_discipline(dr) == []


def test_failure_record_shape_and_attachment():
    rec = Q.failure_record("Gate B", "hs_consistency_lock", "warning",
                           "تفصيل", "وحّد الرمز")
    assert rec == {"gate": "Gate B", "check": "hs_consistency_lock",
                   "severity": "warning", "detail": "تفصيل",
                   "action": "وحّد الرمز"}
    out = Q.run_quality_gate({"deep_research": {
        "missions": {}, "report": {"text": ""}, "verdict": {}}})
    assert "failure_records" in out
    assert isinstance(out["failure_records"], list)


def test_ws10_guards_still_green():
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         "tests/test_ws10_deterministic_no_evidence_columns.py",
         "tests/test_ws10_writer_prompt_no_evidence_columns.py"],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stdout[-800:]
