"""صمّامات الطبقات المرئية (طلب المالك 2026-08-19) — إطفاء فوري بلا نشر.

كل طبقة أضافها التوجيه وتراها العين لها مفتاح واحد؛ **الافتراض ON** (يطابق
سلوك الإنتاج الذي تحقّق منه المالك)، والإطفاء يعيد سلوك ما قبل الموجة حرفياً.
هرمتي — بلا شبكة.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_VALVES = ("ECONOMICS_SECTION", "GAP_REGISTER", "VERDICT_STRUCTURE",
           # الموجة ٠ — لغةُ المصنع تحكم لغةَ التقرير: طبقةٌ مرئيةٌ للعميل،
           # فلها مفتاح إطفاءٍ فوريّ كسائرها (البند ٩١).
           "REPORT_LANGUAGE")


def _view(monkeypatch=None):
    import silk_render as R
    from tools.canonical_netherlands import netherlands_research_blob
    return R.build_view(netherlands_research_blob())


def test_every_valve_defaults_to_on(monkeypatch):
    """الافتراض ON — عبر monkeypatch لا os.environ.pop (استرجاع مضمون،
    قاعدة عزل البيئة في هذا الريبو — مراجعة ذاتية §58)."""
    import silk_render as R
    for name in _VALVES:
        monkeypatch.delenv(f"SILK_{name}_ENABLED", raising=False)
        assert R.layer_enabled(name) is True, f"{name} ليس ON افتراضياً"
    from silk_style_contract import epistemic_rule
    monkeypatch.delenv("SILK_EPISTEMIC_VERBS_ENABLED", raising=False)
    assert epistemic_rule()


def test_valve_accepts_the_repo_off_vocabulary(monkeypatch):
    import silk_render as R
    for raw in ("0", "false", "no", "off", "OFF", "False"):
        monkeypatch.setenv("SILK_GAP_REGISTER_ENABLED", raw)
        assert R.layer_enabled("GAP_REGISTER") is False, raw
    for raw in ("1", "true", "on", "yes", ""):
        monkeypatch.setenv("SILK_GAP_REGISTER_ENABLED", raw)
        assert R.layer_enabled("GAP_REGISTER") is True, raw


def test_economics_section_valve_removes_only_that_layer(monkeypatch):
    on = _view()
    assert (on["deep_research"].get("economics") or {}).get("reverse_solve")
    monkeypatch.setenv("SILK_ECONOMICS_SECTION_ENABLED", "0")
    off = _view()
    assert off["deep_research"].get("economics") is None
    # لا ضرر جانبي: بقية العرض كما هو
    assert off["deep_research"]["verdict"] == on["deep_research"]["verdict"]
    assert off["deep_research"].get("report") == on["deep_research"].get("report")


def _kuwait_view():
    import silk_render as R
    from tools.canonical_kuwait_peanut_butter import kuwait_research_blob
    return R.build_view(kuwait_research_blob())


def test_gap_register_valve_keeps_the_free_text_limits(monkeypatch):
    on = _kuwait_view()
    assert on["deep_research"].get("gap_register")
    monkeypatch.setenv("SILK_GAP_REGISTER_ENABLED", "0")
    off = _kuwait_view()
    assert off["deep_research"].get("gap_register") == []
    # الحدود النصّية (سلوك ما قبل الموجة ١) تبقى — لا تقرير أنحف
    assert off["deep_research"].get("limits") == on["deep_research"].get("limits")


def test_verdict_structure_valve_keeps_the_verdict_itself(monkeypatch):
    import silk_render as R
    result = {"product": "حليب", "hs_code": "040120", "year": 2023,
              "markets": [{"country": "الأردن", "total_score": 0.55,
                           "confidence": 0.6,
                           "decision": {"schema": "silk.decision/v1",
                                        "verdict": "WATCH", "confidence": 0.6,
                                        "score": 0.55, "why": "سبب",
                                        "decision_rule": "القاعدة",
                                        "counter_case": "الحجة المضادة"},
                           "jury": {"agents_with_data": 4, "agents_total": 4,
                                    "data_gaps": []}}]}
    on = R.build_view(result)["decision"]
    assert on["rule"] and on["counter_case"]
    monkeypatch.setenv("SILK_VERDICT_STRUCTURE_ENABLED", "0")
    off = R.build_view(result)["decision"]
    assert off["rule"] is None and off["counter_case"] is None
    # الحكم نفسه لا يُمَسّ أبداً (أسبقية الحكم الواحد)
    assert off["verdict"] == on["verdict"] == "WATCH"
    assert off["confidence"] == on["confidence"]


def test_epistemic_verbs_valve_strips_only_that_rule(monkeypatch):
    from silk_style_contract import (EPISTEMIC_VERB_RULE,
                                     WRITER_STYLE_CONTRACT, epistemic_rule)
    monkeypatch.setenv("SILK_EPISTEMIC_VERBS_ENABLED", "0")
    assert epistemic_rule() == ""
    stripped = WRITER_STYLE_CONTRACT.replace("\n\n" + EPISTEMIC_VERB_RULE, "")
    assert EPISTEMIC_VERB_RULE not in stripped
    assert "عقد الأسلوب" in stripped, "الإطفاء أتلف بقية العقد"


def test_writer_honours_the_epistemic_valve():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_ai_judge.py"), encoding="utf-8").read()
    assert "epistemic_rule()" in src, "الكاتب لا يقرأ الصمّام"


def test_all_valves_are_documented_in_env_example():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".env.example")
    doc = open(p, encoding="utf-8").read()
    for name in _VALVES + ("EPISTEMIC_VERBS",):
        assert f"SILK_{name}_ENABLED" in doc, (
            f"SILK_{name}_ENABLED غير موثّق في .env.example — مفتاح لا "
            "يعرفه المشغّل لا يُعَدّ مخرجاً")
