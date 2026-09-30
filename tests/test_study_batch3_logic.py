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
    assert c["decision"]["threshold_provisional"] is (c["decision"]["provisional_threshold_usd"] is not None)
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


# ── P3-6 الحجة المضادة ───────────────────────────────────────────────────
def test_counter_kind_ranking_is_deterministic():
    from silk_study_numbers import compute
    c = _case()
    assert compute(c)["counter_kind"] == "saudi_absent"
    c2 = copy.deepcopy(c)
    c2["suppliers"]["saudi_share_pct"] = 2.0
    c2["suppliers"]["top"][0]["share_pct"] = 35.0
    assert compute(c2)["counter_kind"] == "dominant_supplier"


def test_counter_section_without_flip_is_rejected_and_reference_passes():
    from silk_study_linter import lint
    ref = _ref()
    assert not [v for v in lint(ref) if v["rule"] == "counter_without_flip"]
    start = ref.index("## ثامناً")
    end = ref.index("## تاسعاً")
    bad = ref[:start] + "## ثامناً: الاعتبارات المضادة للتوصية\n\nلا شيء يُذكر هنا.\n\n" + ref[end:]
    assert any(v["rule"] == "counter_without_flip" for v in lint(bad))


def test_batch3_4_variants_are_approved_by_owner():
    """اعتمدها المالك 2026-09-28 — لا نسخة معلّقة في ملف المراجعة (بوابة pending نفسها
    يحميها اختبار المحرك بملف مراجعة مؤقت)."""
    from silk_study_render import pending_variants
    p = pending_variants()
    assert not any(t.startswith("تتمثل الحجة الأقوى") or t.startswith("وتنقلب هذه الاعتبارات")
                   or "بميزة القرب" in t for t in p)


def test_review_fix_variants_are_approved_and_render_without_allow_pending():
    """اعتمدها المالك 2026-09-30: «غير مرصودة» لحصة السعودية و«ضغط» التضخم."""
    from silk_study_render import pending_variants, render_study
    p = pending_variants()
    assert not any("لا تظهر المملكة" in t or "قد يضغط على القوة الشرائية" in t for t in p)
    c = _case()
    c["macro"]["inflation_pct"] = 12.0
    assert "قد يضغط على القوة الشرائية" in render_study(c, _kn())
    c2 = _case()
    c2["suppliers"]["saudi_share_pct"] = None
    assert "لا تظهر المملكة" in render_study(c2, _kn())


# ── P3-4 ملف المصدّر ─────────────────────────────────────────────────────
def test_processor_exporter_credited_with_direct_buying_benefit_is_critical():
    from silk_study_linter import lint
    bad = _ref() + "\nيفيد المصدّر توجه الشراء المباشر من الدول المزارعة.\n"
    rules = [v["rule"] for v in lint(bad, exporter_type="processor_of_imported_input")]
    assert "exporter_benefit" in rules
    assert "exporter_benefit" not in [v["rule"] for v in lint(bad, exporter_type="agri_producer")]
    assert not [v for v in lint(_ref(), exporter_type="processor_of_imported_input")]


def test_exporter_type_selects_raw_cost_clause():
    from silk_study_render import render_study
    out = render_study(_case(), _kn())
    assert "دون تكلفة استيراد" in out
    c = _case()
    c["product"]["exporter_type"] = "agri_producer"
    out2 = render_study(c, _kn())
    assert "دون تكلفة استيراد" not in out2 and "بميزة القرب الجغرافي من السوق" in out2


def test_research_request_rejects_unknown_exporter_type():
    import tempfile
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    with patch.dict(os.environ, {"SILK_API_KEY": "s", "SILK_DATA_DIR": tempfile.mkdtemp()}):
        import api
        r = TestClient(api.create_app()).post("/research", headers={"X-API-Key": "s"}, json={
            "product": "قهوة", "market": "Malaysia", "hs_code": "090121", "hs_confirmed": True,
            "exporter_type": "wizard", "persist": False})
    assert r.status_code == 422 and "exporter_type" in r.text


def test_exporter_type_enum_matches_case_module():
    import api  # noqa: F401
    from silk_study_case import EXPORTER_TYPES
    src = open(os.path.join(_ROOT, "api.py"), encoding="utf-8").read()
    for t in EXPORTER_TYPES:
        assert f'"{t}"' in src


# ── P3-5 الميزة مشروطة ───────────────────────────────────────────────────
def test_unconditioned_advantage_is_rejected_and_reference_passes():
    from silk_study_linter import lint
    assert not [v for v in lint(_ref()) if v["rule"] == "unconditioned_advantage"]
    bad = _ref() + "\n\nالميزة الأبرز للمنتج السعودي هي جودته العالية.\n"
    assert any(v["rule"] == "unconditioned_advantage" for v in lint(bad))


def test_advantage_brief_demands_a_feasibility_condition():
    from silk_study_render import load_templates
    assert "شرط جدواها" in load_templates()["llm_briefs"]["s3_advantage"]


# ── P3-7 سعر الحدود ──────────────────────────────────────────────────────
def test_border_price_as_negotiation_reference_is_rejected():
    from silk_study_linter import lint
    assert not [v for v in lint(_ref()) if v["rule"] == "border_as_reference"]
    bad = _ref() + "\n\nويُعد متوسط سعر الاستيراد مرجعاً للتفاوض مع الموزع.\n"
    assert any(v["rule"] == "border_as_reference" for v in lint(bad))


# ── P3-2 قاموس الحالة ────────────────────────────────────────────────────
def test_vocab_variant_is_rejected_and_reference_passes():
    from silk_study_linter import lint
    assert not [v for v in lint(_ref()) if v["rule"] == "vocab_variant"]
    bad = _ref().replace("للقهوة المختصة", "للقهوة الفاخرة", 1)
    assert bad != _ref()
    assert any(v["rule"] == "vocab_variant" for v in lint(bad))


def test_every_banned_vocab_form_has_an_approved_counterpart():
    import yaml
    with open(os.path.join(_ROOT, "data", "study_status_vocab.yaml"), encoding="utf-8") as f:
        d = yaml.safe_load(f)
    for fam in d.values():
        assert fam["canonical"] and all(good for good in fam["banned"].values())


def test_tier_filter_stays_inside_the_local_currency_and_declares_dropped_rows():
    from silk_economics import _pick_shelf_anchor
    rows = [(20.0, "بن تقليدي 1 كغ", "MYR", 1.0, None),
            (9.0, "بن specialty 1 كغ", "USD", 1.0, None)]
    anchor, dropped = _pick_shelf_anchor(rows, "MYR", tier="specialty")
    assert anchor[2] == "MYR" and dropped.get("بعملة أخرى") == 1
    rows2 = rows + [(70.0, "بن specialty 1 كغ", "MYR", 1.0, None)]
    anchor2, dropped2 = _pick_shelf_anchor(rows2, "MYR", tier="specialty")
    assert anchor2[0] == 70.0 and dropped2.get("من شريحة أخرى") == 1


def test_premium_default_tier_does_not_narrow_and_words_match_whole():
    """مراجعة (١٣): «premium» (افتراضي الواجهة) لا يصفّي؛ «مختص» لا تُطابق «مختصر»."""
    from silk_economics import _pick_shelf_anchor
    rows = [(20.0, "بن تقليدي 1 كغ", "MYR", 1.0, None),
            (70.0, "بن premium 1 كغ", "MYR", 1.0, None)]
    anchor, dropped = _pick_shelf_anchor(rows, "MYR", tier="premium")
    assert anchor[0] == 20.0 and "من شريحة أخرى" not in dropped
    rows2 = [(20.0, "بن مختصر 1 كغ", "MYR", 1.0, None),
             (70.0, "بن مختص 1 كغ", "MYR", 1.0, None)]
    anchor2, _ = _pick_shelf_anchor(rows2, "MYR", tier="specialty")
    assert anchor2[0] == 70.0
    rows3 = [(20.0, "بن تجاري 1 كغ", "MYR", 1.0, None),
             (70.0, "القهوة المختصة 1 كغ", "MYR", 1.0, None)]
    assert _pick_shelf_anchor(rows3, "MYR", tier="specialty")[0][0] == 70.0


def test_negated_or_inflected_predicate_is_not_a_claim_conflict():
    from silk_study_claims import build_claims, conflicts
    cl = build_claims(_case(), _kn())
    assert not conflicts("السلاسل الكبرى لا تشترط الشهادة.", cl)
    assert not conflicts("AEON تشترطها بعض الفروع.", cl)
    assert conflicts("السلاسل الكبرى تشترط الشهادة.", cl)


def test_english_source_alias_counts_as_listed():
    from silk_study_linter import lint
    md = "## الملخص التنفيذي\n\nوفق البنك الدولي بلغ النمو.\n\n**المصادر:** World Bank PA.NUS.FCRF.\n"
    assert not [v for v in lint(md) if v["rule"] == "source_missing"]


def test_threshold_ignores_non_equivalent_rows():
    from silk_study_case import provisional_threshold
    assert provisional_threshold([{"usd_kg": 35.0}, {"usd_kg": 100.0, "equivalent": False}]) == 15


def test_counter_no_counter_renders_with_flip_and_follow_ups_match_kind():
    from silk_study_numbers import compute, counter_follow
    assert counter_follow("dominant_supplier", "conditional") == "other_go"
    assert counter_follow("saudi_absent", "conditional") == "conditional"
    from silk_study_render import Renderer
    c = _case()
    c["suppliers"]["saudi_share_pct"] = 2.0
    for t in c["suppliers"]["top"]:
        t["kind"] = "producer"
        t["share_pct"] = min(t["share_pct"], 20.0)
    n = compute(c)
    assert n["counter_kind"] in ("no_counter", "declining")
    r = Renderer(c, _kn(), allow_pending=True)
    assert r._cond("counter_kind == no_counter") == (n["counter_kind"] == "no_counter")


def test_exporter_type_flows_to_result_without_fake_product_card():
    import tempfile
    import time
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from test_study_export_route import _fake_call, _fake_tools, _fake_writer
    seen_cards = []
    import silk_research_pipeline as P
    env = {"ANTHROPIC_API_KEY": "t", "SILK_API_KEY": "s", "SILK_RATE_LIMIT": "100000",
           "SILK_DATA_DIR": tempfile.mkdtemp()}
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with patch.dict(os.environ, env), \
            patch("silk_llm_runtime._call_tools", side_effect=_fake_tools), \
            patch("silk_synthesis._call", side_effect=_fake_call), \
            patch("silk_ai_judge._call", side_effect=_fake_writer), \
            patch("silk_data_layer._cached_get", return_value=None), \
            patch("silk_data_layer._http_get", side_effect=OSError("no net")), \
            patch("silk_storage._db_path", return_value=db):
        import api
        client = TestClient(api.create_app())
        hdr = {"X-API-Key": "s"}
        r = client.post("/research", headers=hdr, json={
            "product": "قهوة محمصة", "market": "Malaysia", "hs_code": "090121",
            "persist": True, "async_run": True, "hs_confirmed": True,
            "exporter_type": "manufacturer"})
        assert r.status_code == 202, r.text
        aid = r.json()["analysis_id"]
        for _ in range(3000):
            st = client.get(f"/research/{aid}/status", headers=hdr).json()
            if st.get("status") and st["status"] != "running":
                break
            time.sleep(0.01)
        res = client.get(f"/analyses/{aid}", headers=hdr).json()
    assert res["deep_research"].get("exporter_type") == "manufacturer"
    assert not (res.get("product_card") or {}).get("exporter_type")
    assert P  # الوحدة محمَّلة


def test_approved_counter_variants_render_with_a_flip_condition():
    from tools.canonical_turkey_polymers import turkey_polymers_research_blob
    from silk_study_case import build_case
    from silk_study_linter import lint
    from silk_study_render import render_study
    c = build_case(turkey_polymers_research_blob(), exporter_type="manufacturer", segment=None)
    md = render_study(c, {})
    sec = md.split("## ثامناً")[1].split("## تاسعاً")[0]
    assert "تتمثل الحجة الأقوى" in sec or "لم تُرصد" in sec
    assert not [v for v in lint(md, exporter_type="manufacturer") if v["rule"] == "counter_without_flip"]
