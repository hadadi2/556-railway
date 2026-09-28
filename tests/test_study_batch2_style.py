"""الدفعة ٢ — الأسلوب (P2-2، P2-3، P2-4، P2-6، P2-7) لنمط «دراسة السوق».

P2-2 ترويسة حتمية بقيم الحالة؛ P2-3 نموذج أسلوبي لكل فراغ (ب)/(ج) فقط؛ P2-4 عقد
فراغ قصير بلا اسم منتج/سوق؛ P2-6 linter: المرجع صفر مخالفات والشاهد الكويتي يُرفض؛
P2-7 صيغة واحدة «مؤشر تركّز الموردين». + التصدير لا ينادي النموذج أبداً.
"""
from __future__ import annotations

import ast
import copy
import csv
import glob
import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIX = os.path.join(_ROOT, "evals", "golden_set", "malaysia_coffee_fixture.json")
_REF = os.path.join(_ROOT, "samples", "golden_malaysia_coffee_study.md")
_KW = os.path.join(_ROOT, "samples", "kuwait_peanut_butter_research_report.md")


def _case():
    with open(_FIX, encoding="utf-8") as f:
        return json.load(f)


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# ── P2-2 الترويسة ─────────────────────────────────────────────────────────
def test_header_lines_come_from_the_case_and_last_complete_year_skips_provisional():
    from silk_study_render import render_study
    c = copy.deepcopy(_case())
    c["product"]["name_full"] = "منتج تجريبي"
    c["prepared"] = {"year": 2027, "month": 3, "collected_on": "2027-03-01"}
    c["imports"]["series"][-1]["complete"] = False          # آخر سنة أولية
    last = max(r["year"] for r in c["imports"]["series"] if r["complete"])
    out = render_study(c, {})
    head = out.split("---", 1)[0]
    assert f"**المنتج:** منتج تجريبي (البند الجمركي {c['product']['hs']})" in head
    assert f"**بلد المنشأ:** {c['product']['origin_ar']}" in head
    assert f"**السوق المستهدفة:** {c['market']['name_ar']}" in head
    assert "**تاريخ الإعداد:** مارس 2027" in head
    assert f"**أحدث سنة بيانات تجارية مكتملة:** {last}" in head


# ── P2-4 العقد ───────────────────────────────────────────────────────────
def _names():
    words = set()
    for p in glob.glob(os.path.join(_ROOT, "data", "product_knowledge", "*.yaml")):
        words.add(yaml.safe_load(_read(p)).get("product_short", "") or "")
    with open(os.path.join(_ROOT, "data", "market_nisba_l1.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(ln for ln in f if not ln.startswith("#")):
            words.update(v for k, v in r.items() if k and v and not k.startswith("iso"))
    c = _case()
    words.update({c["product"]["short"], c["product"]["commodity"], c["market"]["name_ar"],
                  "ماليزيا", "القهوة", "البن", "Malaysia", "coffee"})
    return {w for w in words if len(w) >= 3}


def test_slot_contract_names_no_product_or_market():
    src = _read(os.path.join(_ROOT, "silk_style_contract.py"))
    tree = ast.parse(src)
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(getattr(t, "id", "") == "STUDY_SLOT_CONTRACT" for t in n.targets))
    text = ast.literal_eval(node.value)
    hits = [w for w in _names() if w in text]
    assert not hits, hits
    for must in ("ضمير المتكلم", "التعجب", "الإنجليزية", "رقم لم يُمرَّر"):
        assert must in text


# ── P2-3 النماذج ─────────────────────────────────────────────────────────
def test_exemplars_cover_every_llm_brief_with_lexicon():
    from silk_study_render import load_exemplars, load_templates
    ex = load_exemplars()
    for sid in load_templates()["llm_briefs"]:
        assert ex[sid]["reference"] and ex[sid]["lexicon"], sid
    assert all(e["reference"] for e in ex.values())


def test_every_llm_slot_receives_contract_and_its_own_exemplar():
    from silk_study_render import Renderer, load_exemplars
    from silk_style_contract import STUDY_SLOT_CONTRACT
    seen = {}

    def spy(sid, prompt):
        seen.setdefault(sid, prompt)
        return None
    Renderer(_case(), {}, llm_fill=spy).render()
    ex = load_exemplars()
    assert seen and set(seen) <= set(ex)
    for sid, prompt in seen.items():
        assert STUDY_SLOT_CONTRACT in prompt
        assert ex[sid]["reference"] in prompt, sid
        others = [o for o in ex if o != sid and len(ex[o]["reference"]) > 40
                  and ex[o]["reference"] in prompt]
        assert not others, (sid, others)


def test_type_a_paragraphs_get_no_model_call_with_approved_knowledge():
    from silk_study_render import Renderer, load_knowledge
    calls = []
    Renderer(_case(), load_knowledge("090121", "MY"),
             llm_fill=lambda s, p: calls.append(s)).render()
    assert calls == []


# ── تخزين الفراغات: خط /research ينادي، التصدير يقرأ فقط ──────────────────
def test_fill_slots_returns_only_passing_text_and_export_never_calls_model():
    from silk_study_export import fill_slots, study_markdown
    good = "ويُلاحظ أن الطلب يتركز في المدن الكبرى."
    c = _case()
    c["market"]["iso2"] = "XX"            # بلا ملف معرفة → الفراغات للنموذج
    found = {"study_case": c}
    slots = fill_slots(found, lambda sid, p: "[يُدرج]" if sid == "s2_caveat" else good)
    assert "s2_caveat" not in slots and slots.get("s2_survey") == good
    found["deep_research"] = {"study_slots": slots}
    import silk_ai_judge
    from unittest.mock import patch
    with patch.object(silk_ai_judge, "_call", side_effect=AssertionError("نداء عند التصدير")):
        md, meta = study_markdown(found)
    assert good in md and "s2_survey" in meta["llm_slots"] and "s2_caveat" in meta["gaps"]


# ── P2-6 linter ──────────────────────────────────────────────────────────
def test_reference_passes_linter_with_zero_violations():
    from silk_study_linter import lint
    assert lint(_read(_REF)) == []


def test_engine_output_for_reference_case_passes_linter():
    from silk_study_linter import lint
    from silk_study_render import load_knowledge, render_study
    assert lint(render_study(_case(), load_knowledge("090121", "MY"))) == []


def test_kuwait_witness_is_rejected_on_each_family():
    from silk_study_linter import lint
    rules = {v["rule"] for v in lint(_read(_KW))}
    for r in ("heading_not_literal", "heading_missing", "list_outside_table",
              "table_missing", "bare_term"):
        assert r in rules, (r, rules)


def test_linter_catches_unmarked_provisional_and_wrong_table_columns():
    from silk_study_linter import lint
    md = _read(_REF).replace("وفق البيانات الأولية غير المكتملة لعام 2025",
                             "في عام 2025")
    md = md.replace("| الجهة | الوصف | الدور المقترح |", "| الجهة | النشاط | الدور |")
    rules = {v["rule"] for v in lint(md)}
    assert {"provisional_unmarked", "table_columns", "table_missing"} <= rules


def test_export_meta_carries_lint_result():
    from silk_study_export import study_markdown
    _md, meta = study_markdown({"study_case": _case()})
    assert isinstance(meta["lint"], list)


# ── P2-7 صيغة مؤشر التركّز ───────────────────────────────────────────────
def test_hhi_single_form_everywhere():
    from silk_study_linter import HHI_FORM, lint
    from silk_style_contract import PLAIN_TERMS
    assert PLAIN_TERMS["HHI"] == HHI_FORM
    assert HHI_FORM in _read(_REF)
    bad = _read(_REF).replace(HHI_FORM, "مؤشر تركّز السوق", 1)
    assert any(v["rule"] == "hhi_form" for v in lint(bad))
    import silk_reports as R
    assert HHI_FORM in R._client_sanitize("صفّ المورّدين معتدل (HHI≈2100).")


# ── خط /research: الفراغات تُملأ داخل حارس الميزانية وتُخزَّن ────────────────
_SLOT_TXT = "ويُلاحظ أن الطلب يتركز في المدن الكبرى."


def _run(env_extra: dict, over_budget_after_writer: bool = False):
    import tempfile
    import time
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from test_study_export_route import _fake_call, _fake_tools

    state = {"writer_done": False, "slot_calls": 0}

    def writer_or_slot(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        from silk_style_contract import STUDY_SLOT_CONTRACT
        if STUDY_SLOT_CONTRACT in system:
            state["slot_calls"] += 1
            return _SLOT_TXT
        state["writer_done"] = True
        return "## 1. الخلاصة التنفيذية\nتقرير."
    import silk_pricing
    real_cost = silk_pricing.estimate_cost_usd

    def cost(usage):   # السقف يُخرق **بعد** الكاتب فقط → يصل الحارسُ مرحلةَ الفراغات
        out = dict(real_cost(usage))
        if over_budget_after_writer and state["writer_done"]:
            out["total_usd"] = 999.0
        return out
    env = {"ANTHROPIC_API_KEY": "t", "SILK_API_KEY": "s", "SILK_RATE_LIMIT": "100000",
           "SILK_DATA_DIR": tempfile.mkdtemp(), "SILK_STUDY_SLOTS": "1", **env_extra}
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with patch.dict(os.environ, env), \
            patch("silk_llm_runtime._call_tools", side_effect=_fake_tools), \
            patch("silk_synthesis._call", side_effect=_fake_call), \
            patch("silk_ai_judge._call", side_effect=writer_or_slot), \
            patch("silk_data_layer._cached_get", return_value=None), \
            patch("silk_data_layer._http_get", side_effect=OSError("no net")), \
            patch("silk_storage._db_path", return_value=db), \
            patch("silk_pricing.estimate_cost_usd", side_effect=cost):
        import api
        client = TestClient(api.create_app())
        hdr = {"X-API-Key": "s"}
        r = client.post("/research", headers=hdr, json={
            "product": "قهوة محمصة", "market": "Vietnam", "hs_code": "090121",
            "persist": True, "async_run": True, "hs_confirmed": True})
        assert r.status_code == 202, r.text
        aid = r.json()["analysis_id"]
        for _ in range(3000):
            st = client.get(f"/research/{aid}/status", headers=hdr).json()
            if st.get("status") and st["status"] != "running":
                break
            time.sleep(0.01)
        res = client.get(f"/analyses/{aid}", headers=hdr).json()
        res["_slot_calls"] = state["slot_calls"]
        return res


def test_pipeline_fills_and_stores_slots_with_stage_cost():
    res = _run({})
    dr = res["deep_research"]
    assert dr.get("study_slots") and set(dr["study_slots"].values()) == {_SLOT_TXT}
    assert "study_slots" in (res.get("data_economics") or {}).get("cost_usd_by_stage", {})
    assert isinstance(dr.get("study_lint"), list)


def test_pipeline_skips_slots_when_run_budget_is_exhausted():
    """الكاتب يكتمل ثم يُخرق السقف: الحارس قبل أول نداء فراغ يمنعه ويُعلن التخطّي."""
    res = _run({}, over_budget_after_writer=True)
    dr = res["deep_research"]
    assert dr.get("report", {}).get("report")          # بلغنا المرحلة فعلاً
    assert res["_slot_calls"] == 0 and not dr.get("study_slots")
    assert dr.get("study_slots_skipped")                # معلن لا صامت


def test_pipeline_slot_calls_are_capped():
    res = _run({"SILK_STUDY_SLOTS_MAX_CALLS": "3"})
    assert res["_slot_calls"] == 3 and len(res["deep_research"]["study_slots"]) == 3


def test_llm_review_mark_never_reaches_the_client_export():
    from silk_study_export import study_markdown
    c = _case()
    c["market"]["iso2"] = "XX"
    md, meta = study_markdown({"study_case": c,
                               "deep_research": {"study_slots": {"s2_survey": _SLOT_TXT}}})
    assert _SLOT_TXT in md and "s2_survey" in meta["llm_slots"]
    assert "<!--" not in md and not [v for v in meta["lint"] if v["rule"] == "forbidden"]


def test_slots_switch_off_makes_no_slot_calls():
    res = _run({"SILK_STUDY_SLOTS": "0"})
    assert not res["deep_research"].get("study_slots")


def test_fragment_slots_never_reach_the_model():
    from silk_study_render import Renderer, load_templates
    seen = []
    Renderer(_case(), {}, llm_fill=lambda sid, p: seen.append(sid)).render()
    assert seen and set(seen) <= set(load_templates()["llm_briefs"])


def test_fill_slots_keeps_paid_text_when_render_fails_later():
    import silk_study_render as R
    from unittest.mock import patch
    from silk_study_export import fill_slots
    c = _case()
    c["market"]["iso2"] = "XX"
    real = R.Renderer._render_once
    state = {"n": 0}

    def boom(self):
        state["n"] += 1
        if state["n"] == 2:
            raise R.StudyRenderError("عطل لاحق")
        return real(self)
    with patch.object(R.Renderer, "_render_once", boom):
        out = fill_slots({"study_case": c}, lambda sid, p: _SLOT_TXT)
    assert out and set(out.values()) == {_SLOT_TXT}


def test_fill_slots_guard_is_asked_before_every_call():
    from silk_study_export import fill_slots
    c = _case()
    c["market"]["iso2"] = "XX"
    asks, calls = [], []

    def guard():
        asks.append(1)
        return len(calls) < 2
    fill_slots({"study_case": c}, lambda sid, p: calls.append(sid) or _SLOT_TXT, guard=guard)
    assert len(calls) == 2 and len(asks) >= 3


def test_linter_year_needs_year_context():
    from silk_study_linter import lint
    head = "**أحدث سنة بيانات تجارية مكتملة:** 2024\n\n"
    rule = lambda t: [v for v in lint(head + t) if v["rule"] == "provisional_unmarked"]  # noqa: E731
    assert not rule("ويبلغ مؤشر تركّز الموردين 2090 وتستحوذ الهند على حصة 40%.")
    assert rule("ارتفعت الواردات في 2025م.")
    assert rule("بلغت الواردات 90 مليون دولار في عام 2025.")
    assert rule("بلغت الواردات 90 مليون دولار خلال 2025.")
    assert rule("الواردات (2025) مرتفعة.") and rule("الواردات 2025 م مرتفعة.")
    assert not rule("الواردات يكفي 2025 حصة.")          # «في» داخل كلمة ليست سياق سنة


def test_fragment_gap_drops_its_paragraph_and_names_no_internal_id():
    from silk_study_render import Renderer
    c = _case()
    out = Renderer(c, {}, llm_fill=lambda sid, p: _SLOT_TXT).render()
    assert "عند  " not in out and "، ." not in out and " ، " not in out
    assert "s1_border" not in out and "k:" not in out


def test_templates_loader_returns_independent_copies():
    from silk_study_render import load_templates
    t = load_templates()
    t["llm_briefs"]["x"] = "y"
    assert "x" not in load_templates()["llm_briefs"]
