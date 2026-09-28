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
