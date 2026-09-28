"""الدفعة ٥ — حلقة المراجعة وسقف التكلفة (P5-1…P5-6) لنمط «دراسة السوق»."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIX = os.path.join(_ROOT, "evals", "golden_set", "malaysia_coffee_fixture.json")
GOOD = "ويُلاحظ أن الطلب يتركز في المدن الكبرى."


def _case(no_knowledge=True):
    with open(_FIX, encoding="utf-8") as f:
        c = json.load(f)
    if no_knowledge:
        c["market"]["iso2"] = "XX"
    return c


# ── P5-1 ───────────────────────────────────────────────────────────────
def test_slot_with_vocab_variant_is_retried_then_declared_gap():
    from silk_study_render import Renderer
    calls = []

    def llm(sid, prompt):
        calls.append(sid)
        return "ويُلاحظ إقبال على القهوة الفاخرة."
    r = Renderer(_case(), {}, llm_fill=llm)
    out = r.render()
    per = {s: calls.count(s) for s in set(calls)}
    assert per and all(n == 2 for n in per.values())
    assert "الفاخرة" not in out and r.gaps


def test_unconditioned_advantage_rejected_only_in_advantage_slot():
    from silk_study_linter import slot_violations
    assert slot_violations("الميزة الأبرز الجودة.", sid="s3_advantage")
    assert not slot_violations("الميزة الأبرز الجودة.", sid="s2_patterns")


# ── P5-2 المراجع ───────────────────────────────────────────────────────
def test_review_study_parses_schema_and_rejects_invalid_score():
    from unittest.mock import patch
    import silk_ai_judge as J
    ok = json.dumps({"score": 8.7, "notes": [{"location": "s2_caveat", "severity": "high", "fix": "x"},
                                             {"location": "s2", "severity": "weird", "fix": "y"}]})
    with patch.object(J, "available", return_value=True), patch.object(J, "_call", return_value=ok):
        r = J.review_study("## نص", "")
    assert r == {"score": 8.7, "notes": [{"location": "s2_caveat", "severity": "high", "fix": "x"}]}
    for bad in ("not json", json.dumps({"score": 42}), json.dumps({"notes": []})):
        with patch.object(J, "available", return_value=True), patch.object(J, "_call", return_value=bad):
            assert J.review_study("## نص") is None            # لا درجة مختلقة


def test_reviewer_uses_a_model_other_than_the_writer():
    from unittest.mock import patch
    import silk_ai_judge as J
    seen = {}

    def call(system, user, max_tokens=1600, model=None, **kw):
        seen["model"] = model
        return json.dumps({"score": 9, "notes": []})
    with patch.object(J, "available", return_value=True), patch.object(J, "_call", side_effect=call):
        J.review_study("## نص")
    assert seen["model"] and seen["model"] != J._MODEL


def _tail(reviews, fill=None, guard=None):
    from silk_study_review import run_study_tail
    it = iter(reviews)
    calls = []

    def f(sid, prompt):
        calls.append((sid, prompt))
        return fill(sid, prompt) if fill else GOOD
    out = run_study_tail(_case(), {}, f, lambda md, facts="": next(it), guard=guard)
    return out, calls


def test_note_on_type_a_paragraph_goes_to_ops_log_not_rewrite():
    from unittest.mock import patch
    import silk_ops_log
    logged = []
    rev = [{"score": 7.0, "notes": [{"location": "## أولاً: حجم السوق واتجاهاته",
                                     "severity": "high", "fix": "رقم خاطئ في القالب"}]}]
    with patch.object(silk_ops_log, "record_error", side_effect=lambda k, r, c=None: logged.append(k)):
        out, calls = _tail(rev)
    first_fill = len(calls)
    assert out["rounds"] == 0 and len(calls) == first_fill      # لا إعادة ملء
    assert "template_error" in logged


# ── P5-3 / P5-4 ────────────────────────────────────────────────────────
def test_score_above_nine_stops_after_one_review():
    out, calls = _tail([{"score": 9.2, "notes": []}])
    assert out["rounds"] == 0 and out["score"] == 9.2 and out["delivery"]["tier"] == "ready"


def test_only_slots_with_high_notes_are_refilled():
    rev = [{"score": 7.0, "notes": [{"location": "s2_caveat", "severity": "high", "fix": "أدق"},
                                    {"location": "s2_patterns", "severity": "low", "fix": "أسلوب"}]},
           {"score": 9.1, "notes": []}]
    out, calls = _tail(rev, fill=lambda sid, p: ("ويُلاحظ تحفظٌ أدق." if "ملاحظة المراجع" in p else GOOD))
    refills = [s for s, p in calls if "ملاحظة المراجع" in p]
    assert refills == ["s2_caveat"] and out["rounds"] == 1 and out["score"] == 9.1


def test_best_version_is_delivered_when_round_two_is_worse():
    rev = [{"score": 7.5, "notes": [{"location": "s2_caveat", "severity": "high", "fix": "a"}]},
           {"score": 6.0, "notes": [{"location": "s2_caveat", "severity": "high", "fix": "b"}]},
           {"score": 5.0, "notes": []}]
    n = {"i": 0}

    def fill(sid, p):
        if "ملاحظة المراجع" in p:
            n["i"] += 1
            return f"ويُلاحظ نصٌّ معدَّل رقم {'أ' * n['i']}."
        return GOOD
    out, _ = _tail(rev, fill=fill)
    assert [v["score"] for v in out["versions"]] == [7.5, 6.0, 5.0]
    assert out["best_round"] == 0 and out["score"] == 7.5
    assert out["slots"]["s2_caveat"] == GOOD


# ── P5-5 ───────────────────────────────────────────────────────────────
def test_tail_cap_stops_and_delivers_best_so_far():
    from silk_study_export import fill_slots
    k = len(fill_slots({"study_case": _case()}, lambda s, p: GOOD))   # نداءات ملء الجولة 0
    state = {"n": 0}

    def guard():
        state["n"] += 1
        return state["n"] <= k           # ملء الجولة 0 ثم يُخرق السقف قبل المراجعة
    out, _ = _tail([{"score": 9.5, "notes": []}], guard=guard)
    assert out["tail_capped"] is True and out["slots"] and out["score"] is None
    assert out["delivery"]["tier"] == "human_review"


def test_no_model_slots_means_no_review_call():
    from silk_study_review import run_study_tail
    from silk_study_render import load_knowledge
    c = _case(no_knowledge=False)
    reviewed = []
    out = run_study_tail(c, load_knowledge("090121", "MY"), lambda s, p: GOOD,
                         lambda md, f="": reviewed.append(1))
    assert not reviewed and out["delivery"]["tier"] == "no_slots"


# ── P5-6 ───────────────────────────────────────────────────────────────
def test_delivery_ladder_three_cases_and_limits_become_gaps():
    from silk_study_case import build_case
    from silk_study_review import delivery_tier
    assert delivery_tier(9.3, [])["tier"] == "ready"
    d = delivery_tier(8.4, [{"severity": "medium", "fix": "بيانات الموسمية تقديرية"},
                            {"severity": "low", "fix": "أسلوب"}])
    assert d["tier"] == "limits" and d["limits"] == ["بيانات الموسمية تقديرية"]
    low = delivery_tier(7.2, [])
    assert low["human_review"] and low["free_update"]
    assert delivery_tier(None, [])["human_review"]
    c = build_case({"deep_research": {"study_review": {"delivery": d}}, "product": "قهوة",
                    "hs_code": "090121", "market": "Vietnam"})
    g = next(g for g in c["gaps"] if g["label"] == "بيانات الموسمية تقديرية")
    assert g["owner"]


def test_ops_studies_endpoint_lists_review_economics():
    import tempfile
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with patch.dict(os.environ, {"SILK_API_KEY": "s", "SILK_DATA_DIR": tempfile.mkdtemp()}), \
            patch("silk_storage._db_path", return_value=db):
        from silk_storage import save_analysis
        save_analysis({"kind": "research", "product": "قهوة", "deep_research": {"study_review": {
            "score": 8.4, "rounds": 1, "best_round": 1, "cost_usd": 0.12, "seconds": 9.0,
            "tail_capped": False, "delivery": {"tier": "limits"}}},
            "data_economics": {"cost_usd_estimate": 2.1, "cost_usd_by_stage": {"study_slots": 0.12}}})
        import api
        cl = TestClient(api.create_app())
        assert cl.get("/ops/studies").status_code == 401
        r = cl.get("/ops/studies", headers={"X-API-Key": "s"})
    assert r.status_code == 200
    row = r.json()["studies"][0]
    assert row["score"] == 8.4 and row["delivery"] == "limits" and row["tail_cost_usd"] == 0.12


def test_pipeline_stores_study_review_with_tail_economics():
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
    from test_study_batch2_style import _run
    res = _run({})
    sr = res["deep_research"]["study_review"]
    # المراجع المزيف يعيد نصاً لا JSON ⇒ لا درجة مختلقة ⇒ مراجعة بشرية، والتسليم قائم.
    assert sr["score"] is None and sr["delivery"]["tier"] == "human_review"
    assert sr["cost_usd"] is not None and sr["seconds"] is not None
    assert res["deep_research"]["study_slots"]
