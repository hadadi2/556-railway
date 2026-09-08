"""الموجة ٤ — سلامة التصنيف (Gate B تحذيري): سجلّ الاشتقاق الدائم، جملة
إفصاح الاستبدال، قفل اتساق الرمز، واتساق المواصفة مع الأدلة. هرمتي.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_quality_gate as Q  # noqa: E402
import silk_render as R  # noqa: E402


def test_derivation_record_always_emitted_for_valid_code():
    from tools.canonical_netherlands import netherlands_research_blob
    dr = R.build_view(netherlands_research_blob())["deep_research"]
    d = dr.get("hs_derivation")
    assert d and d["hs6"] == "080410"
    assert d["chapter"] == "08" and d["heading"] == "0804"
    assert d["basis"]  # أساس الحسم حاضر دائماً — لا سجل بلا أساس


def test_derivation_none_for_missing_or_invalid_code():
    assert R._hs_derivation({"hs_code": None}) is None
    assert R._hs_derivation({"hs_code": "20"}) is None  # لا اختلاق سجل


def test_substitution_disclosure_sentence_on_unconfirmed_code():
    rec = R._hs_derivation({
        "hs_code": "040510",
        "hs_confirmation": {"confirmed": False, "note": "تداخل ضعيف"}})
    assert rec["confirmed"] is False
    assert "لا تُنقل" in rec["substitution_note"]
    assert "لا تُبنى عليها خلاصة حجم" in rec["substitution_note"]


def test_hs_consistency_lock_flags_stray_code_in_hs_context():
    view = {"hs_code": "080410"}
    dr = {"report": {"text": "الواردات تحت رمز HS 190531 نمت — وقيمة 123456 "
                             "دولار لا علاقة لها برمز."},
          "hs_derivation": {"hs6": "080410"}}
    f = Q._check_hs_consistency_lock(view, dr)
    assert f and "190531" in f[0]["note"]
    assert "123456" not in f[0]["note"]     # رقم بلا سياق HS لا يُعلَّم
    assert f[0]["repairable"] is True
    assert "hs_consistency_lock" not in Q.FAIL_TRIGGER_CHECKS


def test_hs_consistency_lock_allows_siblings_and_disclosed_codes():
    view = {"hs_code": "080410"}
    dr = {"report": {"text": "ضمن البند 0804: الرمز 080420 (تين مجفف) "
                             "للمقارنة التفكيكية."},
          "hs_derivation": {"hs6": "080410"}}
    assert Q._check_hs_consistency_lock(view, dr) == []


def test_spec_coherence_fires_when_reframing_evidence_missing():
    dr_bad = {"hs_confirmation": {"confirmed": False},
              "report": {"text": "نص بلا وسم"}, "limits": [],
              "hs_derivation": {}}
    f = Q._check_spec_evidence_coherence(dr_bad)
    assert f and f[0]["check"] == "spec_evidence_coherence"
    from silk_hs_confirm import CONTEXTUAL_TAG
    dr_ok = {"hs_confirmation": {"confirmed": False},
             "report": {"text": "نص"}, "limits": [f"حد: {CONTEXTUAL_TAG}"],
             "hs_derivation": {}}
    assert Q._check_spec_evidence_coherence(dr_ok) == []
    dr_confirmed = {"hs_confirmation": {"confirmed": True},
                    "report": {"text": ""}, "limits": []}
    assert Q._check_spec_evidence_coherence(dr_confirmed) == []
