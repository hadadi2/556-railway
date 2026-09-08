"""البند 8 من أمر إصلاح المحرّك — الحجة المضادة تشترط عمودين مختلفين.

الدليل (direct reproduction — تقرير #11): «أقوى الأعمدة: شدة المنافسة
(84%) … أضعف الأعمدة: شدة المنافسة (84%)» — نفس العمود لأن واحداً فقط
حُسب. المطلوب حرفياً: القالب يشترط عمودين مختلفين وإلا أُسقط القسم بدل
جملة تناقض نفسها. هرمتي. Run:
  python3 -m pytest tests/test_goal8_counter_case_two_pillars.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_decision as D                                # noqa: E402


def _decision(pillars):
    return {"verdict": "CONDITIONAL-GO", "score": 0.5, "confidence": 0.4,
            "pillars": pillars, "conditions": []}


def test_single_pillar_counter_case_abstains_declaredly():
    cc = D.counter_case(_decision({"competition": {"value": 0.16}}))
    assert cc.get("skipped") == "single_pillar"
    assert not cc.get("case") and not cc.get("rebuttal")


def test_two_pillars_build_a_real_counter_case():
    cc = D.counter_case(_decision({"competition": {"value": 0.16},
                                   "market": {"value": 0.7}}))
    assert not cc.get("skipped")
    assert cc.get("case") and cc.get("rebuttal")
    # الجملة لا تقارن عموداً بنفسه أبداً
    assert cc["case"].count("شدة المنافسة") <= 1


def test_render_omits_the_section_for_a_skipped_case():
    """`skipped` صادقة ⇒ لا سطر حجة مضادة في العرض — ولا بديل محسوب."""
    import silk_render as R
    ed = {"schema": "silk.decision/v1", "score": 0.5, "confidence": 0.4,
          "verdict": "CONDITIONAL-GO", "decision_rule": "قاعدة",
          "pillars": {"competition": {"value": 0.16, "missing": []}},
          "counter_case": {"skipped": "single_pillar", "case": "",
                           "rebuttal": ""}}
    out = R.decision_basis(ed)
    assert out is not None
    assert not out.get("counter_case_line")


def test_full_decide_path_never_compares_a_pillar_to_itself():
    """عبر `decide` كاملاً مع الصمام المخفوض إلى عمود واحد — لا جملة
    «أقوى/أضعف» بنفس العمود في المخرج."""
    from unittest import mock
    with mock.patch.dict(os.environ, {"SILK_MIN_SCORED_PILLARS": "1"}):
        d = D.decide({"market_attractiveness": {},
                      "competition_intensity": {"hhi": 2400.0},
                      "regulatory_fit": {}, "profitability": {},
                      "risk": {}})
    cc = d.get("counter_case") or {}
    if cc.get("case"):
        assert cc["case"].count("شدة المنافسة") <= 1
    else:
        # امتناع معلَن بأي فرع (عمود واحد / دون الحد) — لا جملة ذاتية التناقض
        assert cc.get("skipped") in ("single_pillar", "insufficient_pillars")
