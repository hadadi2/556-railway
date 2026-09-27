"""الدفعة ٣ — الاتساق والمنطق (P3-1…P3-8) لنمط «دراسة السوق»."""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIX = os.path.join(_ROOT, "evals", "golden_set", "malaysia_coffee_fixture.json")
_REF = os.path.join(_ROOT, "samples", "golden_malaysia_coffee_study.md")


def _case():
    with open(_FIX, encoding="utf-8") as f:
        return json.load(f)


def _ref():
    with open(_REF, encoding="utf-8") as f:
        return f.read()


def _kn():
    from silk_study_render import load_knowledge
    return load_knowledge("090121", "MY")


# ── P3-1 سجل الادعاءات ─────────────────────────────────────────────────
def test_claims_registry_has_every_status_family_from_the_case():
    from silk_study_claims import build_claims
    st = {c["status"] for c in build_claims(_case(), _kn())}
    assert {"documented", "reported", "gap", "estimate_rule"} <= st


def test_reference_has_no_claim_status_conflict():
    from silk_study_claims import build_claims
    from silk_study_linter import lint
    assert lint(_ref(), build_claims(_case(), _kn())) == []


def test_reported_claim_stated_as_fact_is_rejected():
    from silk_study_claims import build_claims
    from silk_study_linter import lint
    bad = _ref().replace("وأن السلاسل الكبرى يُفاد بأنها تشترط شهادة حلال",
                         "وأن السلاسل الكبرى تشترط شهادة حلال")
    rules = [v["rule"] for v in lint(bad, build_claims(_case(), _kn()))]
    assert "claim_status_conflict" in rules


def test_live_case_loads_reported_claims_from_approved_knowledge():
    from silk_study_case import build_case
    c = build_case({"deep_research": {}, "product": "قهوة", "hs_code": "090121", "market": "Malaysia"})
    assert [x["id"] for x in c["claims_reported"]] == ["chains_require_halal"]


# ── P3-3 الفجوات والمصادر ───────────────────────────────────────────────
def test_live_gaps_carry_owner_and_render_it():
    from silk_study_case import build_case
    from silk_study_render import render_study
    c = build_case({"deep_research": {}, "product": "قهوة", "hs_code": "090121", "market": "Vietnam"})
    assert c["gaps"] and all(g["owner"] for g in c["gaps"])
    out = render_study(c, {})
    assert "(يستكملها: UN Comtrade (سحب لاحق))" in out
    assert "يستكملها: ملف معرفة معتمد" in out or "يستكملها: فريق البحث" in out


def test_gap_without_owner_in_live_case_is_rejected():
    from silk_study_claims import build_claims, conflicts
    c = _case()
    c["live"] = True
    c["gaps"] = [{"label": "فجوة بلا جهة", "owner": None}]
    assert any(v["rule"] == "gap_without_owner" for v in conflicts("", build_claims(c)))


def test_source_named_in_body_but_missing_from_list_is_rejected():
    from silk_study_linter import lint
    bad = _ref().replace("صندوق النقد الدولي (النمو، التضخم)؛ ", "")
    assert "صندوق النقد الدولي" in bad.split("**المصادر:**")[0]
    assert any(v["rule"] == "source_missing" for v in lint(bad))


# ── P3-8 مرجع الرف بالشريحة والعتبة المؤقتة ─────────────────────────────
def test_reference_case_yields_15_usd_provisional_threshold():
    from silk_study_case import provisional_threshold
    c = _case()
    shelf = [{"usd_kg": 35.0}, {"usd_kg": 13.0}, {"usd_kg": 6.0}]   # صفوف المرجع
    assert provisional_threshold(shelf) == c["decision"]["provisional_threshold_usd"] == 15
    assert provisional_threshold([]) is None


def test_provisional_threshold_is_flagged_and_does_not_change_decision():
    from silk_study_case import build_case
    from silk_synthesis import study_decision
    c = build_case({"deep_research": {"verdict": {"verdict": "CONDITIONAL-GO"}},
                    "product": "قهوة", "hs_code": "090121", "market": "Malaysia"})
    assert c["decision"]["threshold_provisional"] is True
    assert c["decision"]["type"] == study_decision({"verdict": "CONDITIONAL-GO"})
    from silk_study_claims import build_claims
    c["decision"]["provisional_threshold_usd"] = 15
    rules = {x["id"]: x["status"] for x in build_claims(c)}
    assert rules["provisional_threshold"] == "estimate_rule"
    assert rules["landed_share_rule"] == "estimate_rule"


def test_shelf_anchor_prefers_rows_of_the_target_tier():
    from silk_economics import _pick_shelf_anchor
    rows = [(20.0, "بن تجاري 1 كغ", "USD", 1.0, None),
            (60.0, "بن مختص single origin 1 كغ", "USD", 1.0, None)]
    assert _pick_shelf_anchor(rows, "USD")[0][0] == 20.0
    assert _pick_shelf_anchor(rows, "USD", tier="specialty")[0][0] == 60.0
