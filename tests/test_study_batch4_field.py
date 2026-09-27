"""الدفعة ٤ — المعلومات الميدانية (P4-1…P4-4) لنمط «دراسة السوق»."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LEADS = [{"name": "De Espresso Coffee", "category": "coffee importer"},
         {"name": "Kopi Roasters", "category": "coffee roaster"},
         {"name": "Jaya Grocer", "category": "supermarket"},
         {"name": "ABC Trading", "category": "trading company"}]
CHAN = [{"value": {"title": "Jaya Grocer coffee aisle", "snippet": "Jaya Grocer stocks specialty coffee beans",
                   "url": "https://example.org/jaya"}, "retrieved_at": "2026-09-20"},
        {"value": {"title": "AEON halal", "snippet": "AEON requires halal certificate for suppliers",
                   "url": "https://example.org/aeon"}}]


def _found(leads=LEADS, chan=CHAN, pricing=()):
    return {"deep_research": {"importer_leads": {"leads": list(leads)},
                              "missions": {"channels_importers": {"findings": list(chan)},
                                           "pricing_scout": {"findings": list(pricing)}}},
            "product": "قهوة محمصة", "hs_code": "090121", "market": "Malaysia"}


# ── P4-1 ───────────────────────────────────────────────────────────────
def test_three_classified_entities_and_a_reasoned_exclusion_line():
    from silk_study_entities import classify
    ents, excluded = classify(LEADS, CHAN, "090121", "قهوة محمصة", "MYS")
    roles = {e["name"]: e["role"] for e in ents}
    assert roles == {"De Espresso Coffee": "مرشح لطلب عرض أسعار",
                     "Kopi Roasters": "منافس", "Jaya Grocer": "قناة رصد"}
    assert all(e["product_confirmed"] and set(e) >= {"name", "type", "role", "evidence_url", "date"}
               for e in ents)
    assert next(e for e in ents if e["name"] == "Jaya Grocer")["evidence_url"] == "https://example.org/jaya"
    assert excluded == "ABC Trading"


def test_case_uses_structured_entities_and_renders_exclusion_sentence():
    from silk_study_case import build_case
    c = build_case(_found())
    assert [e["name"] for e in c["entities"]["rows"]][:1] == ["De Espresso Coffee"]
    assert c["entities"]["excluded_text"] == "ABC Trading"
    assert c["entities"]["importer_candidates"] == 1
    assert all(e["desc"] != "جهة مرصودة" for e in c["entities"]["rows"])


# ── P4-2 ───────────────────────────────────────────────────────────────
def test_shelf_rows_carry_segment_source_date_and_equivalence():
    from silk_study_case import build_case, shelf_segment
    assert shelf_segment("Nescafé Gold jar") == "جماهيري"
    assert shelf_segment("Single origin Ethiopia beans") == "مختص"
    assert shelf_segment("Kopi O traditional") == "تقليدي"
    assert shelf_segment("Nescafé 3in1 mix") == "غير مكافئ"
    pricing = [{"value": 35, "note": "Nescafé Gold 35 USD/kg", "source": "Zuba", "retrieved_at": "2026-09-21T10:00"},
               {"value": 60, "note": "Single origin beans 60 USD/kg", "source": "Shop", "retrieved_at": "2026-09-21"},
               {"value": 9, "note": "3in1 mix 9 USD/kg", "source": "Mart"}]
    c = build_case(_found(pricing=pricing))
    rows = {r["segment"]: r for r in c["shelf_prices"]["rows"]}
    assert set(rows) == {"جماهيري", "مختص", "غير مكافئ"}
    assert rows["جماهيري"]["source"] == "Zuba، 2026-09-21"
    assert rows["غير مكافئ"]["equivalent"] is False
    assert c["shelf_prices"]["segment_price_observed"] is True        # صف «مختص» مرصود


def test_table_has_classification_column_values():
    from silk_study_case import build_case
    from silk_study_render import Renderer
    pricing = [{"value": 35, "note": "Nescafé Gold 35 USD/kg", "source": "Zuba"}]
    r = Renderer(build_case(_found(pricing=pricing)), {})
    assert r._rows("shelf_prices")[0][1] == "جماهيري"


# ── P4-3 ───────────────────────────────────────────────────────────────
def test_outlet_condition_enters_registry_as_reported_and_linter_guards_it():
    from silk_study_case import build_case
    from silk_study_claims import build_claims, conflicts
    leads = LEADS + [{"name": "AEON", "category": "hypermarket"}]
    chan = CHAN + [{"value": {"title": "AEON coffee", "snippet": "AEON sells roasted coffee beans",
                              "url": "https://example.org/aeon2"}}]
    c = build_case(_found(leads=leads, chan=chan))
    cl = {x["id"]: x for x in build_claims(c)}
    assert cl["outlet_req:AEON"]["status"] == "reported"
    assert conflicts("وAEON يشترط شهادة الحلال للتعاقد.", list(cl.values()))
    assert not conflicts("ويُفاد بأن AEON يشترط شهادة الحلال.", list(cl.values()))


# ── P4-4 ───────────────────────────────────────────────────────────────
def test_fewer_than_two_entities_is_a_gap_with_a_named_directory():
    from silk_study_case import build_case
    c = build_case(_found(leads=LEADS[:1], chan=[]))
    g = next(g for g in c["gaps"] if g["label"] == "مستوردون مؤكدون بالاسم")
    assert "JAKIM" in g["owner"] and "MIHAS" in g["owner"]
    two = [LEADS[0], {"name": "Coffee Link Distributors", "category": "coffee distributor"}]
    c2 = build_case(_found(leads=two, chan=[]))
    assert not [g for g in c2["gaps"] if g["label"] == "مستوردون مؤكدون بالاسم"]


def test_market_without_directory_falls_back_to_chamber_of_commerce():
    from silk_study_case import _gap
    assert "غرفة التجارة" in _gap("مستوردون مؤكدون بالاسم", "ZZZ")["owner"]


def test_study_mode_third_party_imports_are_in_production_requirements():
    """الدرس ٢٨٦: yaml استُعمل في محرك الدراسة منذ P0-T ولم يُدرَج في requirements.txt —
    الإنتاج يُثبّت هذا الملف وحده، فكان نمط study يسقط هناك صامتاً."""
    import ast
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "requirements.txt"), encoding="utf-8") as f:
        reqs = f.read().lower()
    dist = {"yaml": "pyyaml", "docx": "python-docx"}
    for path in glob.glob(os.path.join(root, "silk_study_*.py")):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for n in names:
                top = n.split(".")[0]
                if top in dist:
                    assert dist[top] in reqs, (os.path.basename(path), top)


def test_counts_agree_importer_plus_roaster_is_still_a_gap():
    from silk_study_case import build_case
    c = build_case(_found(leads=LEADS[:2], chan=[]))     # مستورد + محمصة
    assert c["entities"]["importer_candidates"] == 1
    assert any(g["label"] == "مستوردون مؤكدون بالاسم" for g in c["gaps"])
    assert any("جهتين أو ثلاث" in r["text"] for r in c["decision"]["requirements"])


def test_negated_or_comparative_snippet_is_not_an_outlet_claim():
    from silk_study_entities import outlet_claims
    for txt in ("AEON does not require halal certification.",
                "Unlike AEON, Mydin requires halal certificate.",
                "AEON import requirements: certificate of origin."):
        assert not outlet_claims([{"value": {"snippet": txt, "url": "u"}}], ["AEON"]), txt
    assert outlet_claims([{"value": {"snippet": "AEON requires halal certificate for suppliers.",
                                     "url": "u"}}], ["AEON"])


def test_feminine_predicate_form_is_still_caught_by_linter():
    from silk_study_claims import build_claims, conflicts
    c = {"claims_reported": [{"id": "outlet_req:AEON", "text": "t", "anchors": ["AEON"],
                              "predicate": "يشترط", "predicates": ["يشترط", "تشترط"]}]}
    assert conflicts("شركة AEON تشترط شهادة الحلال.", build_claims(c))


def test_role_words_match_whole_words_only():
    from silk_study_entities import role_of
    assert role_of({"category": "coffee importer & roaster"}) == "مرشح لطلب عرض أسعار"
    assert role_of({"category": "supply chain services"}) == "شريك محتمل"
    assert role_of({"category": "important partner"}) == "شريك محتمل"


def test_segments_are_keyed_by_hs_chapter_and_target_rows_leave_the_range():
    from silk_study_case import build_case, shelf_segment, threshold_from
    assert shelf_segment("Trail mix peanut butter", "200811") == "غير محدد"
    pricing = [{"value": 35, "note": "Nescafé Gold 35 USD/kg", "source": "Zuba"},
               {"value": 60, "note": "Single origin beans 60 USD/kg", "source": "Shop"}]
    c = build_case(_found(pricing=pricing))
    rows = {r["segment"]: r for r in c["shelf_prices"]["rows"]}
    assert rows["مختص"]["equivalent"] is False and rows["جماهيري"]["equivalent"] is True
    assert threshold_from(c["shelf_prices"]["rows"]) == (27, False)   # 60 × 45%، غير مؤقتة
    assert c["decision"]["threshold_provisional"] is False


def test_object_findings_keep_their_date():
    from types import SimpleNamespace
    from silk_study_case import _findings
    dr = {"missions": {"pricing_scout": SimpleNamespace(findings=[SimpleNamespace(
        value=1, source="s", note="n", data_year=None, status="", confidence=0.5,
        retrieved_at="2026-09-21")])}}
    assert _findings(dr, "pricing_scout")[0]["retrieved_at"] == "2026-09-21"


def test_entity_requirement_ordinal_comes_from_real_requirements():
    from silk_study_arabic import ordinal_m
    from silk_study_case import build_case
    from silk_study_render import Renderer
    c = build_case(_found(leads=LEADS[:1], chan=[]))
    rid = next(r["id"] for r in c["decision"]["requirements"] if "جهتين أو ثلاث" in r["text"])
    r = Renderer(c, {})
    assert r.ctx["entity_req_ordinal"] == ordinal_m(rid)
    assert r.ctx["entity_para"] == "no_excluded"            # لا مستبعد ⇒ النسخة بلا جملة الاستبعاد
    assert "JAKIM" in r.ctx["directories_phrase"]
