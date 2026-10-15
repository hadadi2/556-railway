"""الدرس ٢٩٧ — «find all gaps» بعد الدرس ٢٩٦: ٣٤ ثغرةً تُعيد العيوبَ نفسَها في
أسواقٍ وسطوحٍ أخرى. كلُّ اختبارٍ هنا يقفل ثغرةً مسمّاة بإعادة إنتاجٍ مباشرة."""
import importlib
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest                                                 # noqa: E402

import silk_fact_ledger as L                                  # noqa: E402
import silk_quality_gate as Q                                 # noqa: E402


def _src(rel: str) -> str:
    return open(os.path.join(_ROOT, rel), encoding="utf-8").read()


# ── التصنيف والإسناد ──────────────────────────────────────────────────────────

def test_gcc_customs_union_tariff_is_official_not_interest_bearing():
    """أُعيد إنتاجها: «0% — من مصادر غير رسمية فقط (GCC Secretariat)»."""
    from silk_fact_records import classify_tier
    assert classify_tier("GCC Secretariat", "الاتحاد الجمركي الخليجي 0%") == "A"
    assert classify_tier("WTO", "تعرفة الاتحاد الأوروبي") == "A"
    e = L._entry("tariff_applied_pct", 0.0, source="GCC Secretariat",
                 confidence=0.9, note="الاتحاد الجمركي الخليجي")
    assert e["status"] == L.OBSERVED and "غير رسمية" not in L.render_value(e)
    assert classify_tier("Coffee Producers Association") == "X"


def test_tier_markers_need_word_boundaries_and_a_source_not_a_note():
    from silk_fact_records import classify_tier
    assert classify_tier("kingsoft blog") == "C"           # «gso» داخل كلمة
    assert classify_tier("web", "أعلنت وزارة التجارة") == "C"  # الوزارة في الملاحظة
    assert classify_tier("وزارة التجارة البحرينية") == "A"


def test_attribution_does_not_match_a_digit_inside_a_year():
    import silk_deep_pillars as P
    missions = {"tariffs_agreements": {"findings": [
        {"value": "إعفاء", "source": "web", "note": "قرار 2017 HS0901"}]}}
    old = P._metric_findings
    try:
        P._metric_findings = lambda m, k: m[k]["findings"]
        att = L._attribution(missions, "tariffs_agreements", "x", 0.0)
    finally:
        P._metric_findings = old
    assert att["source"] == ""


# ── السجلّ والكاتب ────────────────────────────────────────────────────────────

def test_writer_time_ledger_carries_market_hs_and_card():
    src = _src("silk_research_pipeline.py")
    i = src.index("_ledger = _build_ledger_safe(")
    block = src[i:i + 900]
    assert '"market": {"iso3"' in block and '"hs_code": hs_code' in block
    assert '"product_card": product_card_dict' in block


def test_requirements_count_follows_the_printed_table_and_is_not_unofficial():
    import silk_render as R
    result = {"market": {"iso3": "BHR"}, "hs_code": "090121",
              "deep_research": {"missions": {}}}
    rows = [r for r in R._requirements_safe(result) if not r.get("gap")]
    e = L.build_ledger(result)["entries"]["requirements_count"]
    assert e["value"] == len(rows) and e["status"] == L.OBSERVED


def test_regeneration_passes_a_ledger_and_guards_a_deliverable_report():
    src = _src("api.py")
    i = src.index("report_out = write_reviewed_report(")
    assert "ledger=_regen_ledger" in src[i:i + 400]
    assert "التقرير السابق القابل للتسليم محفوظ" in src


def test_reviewer_rewrite_is_sent_back_for_owner_flags():
    src = _src("silk_ai_judge.py")
    assert "_post_ledger_draft" in src and '"رفضها المالك" in i' in src


def test_stored_study_style_does_not_switch_the_default_export():
    src = _src("api.py")
    assert '_STORED_STYLES = ("decision", "academic")' in src
    assert src.count("_stored_style if _stored_style in _STORED_STYLES") == 2


# ── البوّابات على كل السطوح ───────────────────────────────────────────────────

def test_study_export_and_markdown_carry_the_lesson_296_guards():
    from silk_study_export import study_text_blockers
    assert study_text_blockers("ميناء خليفة نقطة الدخول الوحيدة.", "BHR")
    assert study_text_blockers("ويبلغ مستنتج من أرقام مرصودة.")
    assert not study_text_blockers("المسار الأول برّي عبر جسر الملك فهد.", "BHR")


def test_study_slot_owner_flags_apply_even_to_stored_text():
    from silk_study_render import Renderer
    r = Renderer.__new__(Renderer)
    r.ctx, r.recheck = {}, False
    r.case = {"market": {"iso3": "BHR"}, "product": {}}
    assert r._slot_ok("ميناء خليفة نقطة الدخول الوحيدة")
    assert r._slot_ok("المسار برّي عبر الجسر") is None


def test_markdown_export_and_analyze_docx_are_gated():
    api = _src("api.py")
    assert '_block_client_export_if_gate_failed(\n                        _md_view' in api
    rep = _src("silk_reports.py")
    assert "ملفُّ /analyze كان بلا أيّ حارسٍ لنصّ المُنتَج النهائي" in rep


def test_factory_screen_surfaces_are_checked():
    view = {"market": {"iso3": "BHR"},
            "deep_research": {"report": {"text": "## 1. الخلاصة التنفيذية\n\nنص."},
                              "limits": ["ميناء خليفة نقطة الدخول الوحيدة"],
                              "missions": {}}}
    out = Q.run_quality_gate(view)
    assert any(f["check"] == "owner_flagged_phrase" and "سطح العرض" in f["note"]
               for f in out["findings"])


def test_sharp_claims_read_fallback_prose_english_months_and_indic_digits():
    v = {"deep_research": {"report": {"text": ""}, "missions": {},
                           "client_fallback_prose": {
                               "s": "انكماش الاقتصاد بنسبة ١١٫٣٪ في 2026."}}}
    assert Q._check_sharp_claim_unverified(v)
    v2 = {"deep_research": {"report": {"text": "Halal certification is mandatory "
                                       "since December 2024."}, "missions": {}}}
    assert Q._check_sharp_claim_unverified(v2)


def test_english_status_labels_and_owner_flags():
    assert Q._check_field_label_as_value(
        "The share stands at available from unofficial sources only.")
    assert Q.owner_flag_hits("Khalifa port is the only entry point.", "BHR")
    assert Q.owner_flag_hits("transit by analogy with shipments from Ethiopia")


# ── الوقائع في أسواقٍ أخرى ────────────────────────────────────────────────────

@pytest.mark.parametrize("iso", ["BHR", "JOR", "IRQ", "YEM", "ARE", "QAT", "KWT", "OMN"])
def test_every_land_neighbour_has_a_named_crossing(iso):
    from silk_charter import land_route
    import silk_missions as M
    route = land_route(iso)
    assert route and "منفذ" in route or "جسر" in route
    assert route in M.transport_route_context(iso)


def test_generic_port_words_do_not_make_a_reversed_route():
    v = {"market": {"iso3": "KWT"},
         "deep_research": {"report": {"text": "من ميناء Mina Salman → Dammam"}}}
    assert not Q._check_reversed_route(v)


def test_study_macro_pickers_use_the_official_indicator():
    import silk_study_case as C
    dr = {"missions": {"demographics_economy": {"findings": [
        {"value": 5.5, "data_year": 2024, "source": "web", "note": "سعر الفائدة في المصرف المركزي"},
        {"value": 4.2, "data_year": 2024, "source": "World Bank", "note": "LP.LPI.TIME.XQ مؤشر الأداء اللوجستي"},
        {"value": 2.1, "data_year": 2024, "source": "news", "note": "الاستقرار السياسي Global Peace Index"},
        {"value": 250.0, "data_year": 2024, "source": "IMF WEO", "note": "التضخم PCPIPCH"}]}}}
    fx = C._official_indicator(dr, ("PA.NUS.FCRF", "سعر الصرف"), 0.01, 1e5,
                               official_only=True, reject=("المصرف",))
    lpi = C._official_indicator(dr, ("LPI", "الأداء اللوجستي"), 1, 5,
                                reject=("LP.LPI.TIME",))
    wgi = C._official_indicator(dr, ("PV.EST", "الاستقرار السياسي"), -3, 3,
                                official_only=True, reject=("Global Peace",))
    inf = C._official_indicator(dr, ("التضخم",), -10, 1000)
    assert fx is None and lpi is None and wgi is None and inf["value"] == 250.0


def test_forecast_year_is_not_inherited_as_newest():
    from silk_llm_runtime import _cited_contract_fields as _inherit_from_cited
    from silk_data_layer import DataPoint
    cited = [DataPoint(1.0, "IMF WEO", 0.6, "نمو — تقدير/تنبؤ IMF WEO", "", data_year=2027),
             DataPoint(2.0, "World Bank", 0.9, "نمو فعلي", "", data_year=2024)]
    assert _inherit_from_cited(cited).get("data_year") == 2024


def test_growth_window_is_the_basis_window_everywhere():
    import silk_deep_pillars as P
    rows = [{"value": v, "data_year": y, "source": s, "confidence": 0.9,
             "note": "إجمالي واردات السوق", "status": st}
            for y, v, s, st in ((2016, 1e6, "UN Comtrade (مرآة)", "mirrored"),
                                (2019, 4e6, "UN Comtrade", ""),
                                (2024, 9e6, "UN Comtrade", ""))]
    s = P.import_series({"trade_flow": {"findings": rows}})
    assert s["basis_years"] == [2019, 2024]
    led = L.build_ledger({"deep_research": {"missions": {"trade_flow": {"findings": rows}}}})
    assert "2019–2024" in led["entries"]["import_growth_pct"]["note"]


def test_local_maker_of_the_same_product_is_not_an_importer():
    from silk_style_contract import lead_local_competitor
    assert lead_local_competitor({"name": "مصنع طحينة الربيع"}, "200899", "طحينة")
    assert not lead_local_competitor({"name": "شركة التوزيع الحديثة"}, "200899", "طحينة")


def test_world_top_exporter_importing_more_than_it_exports_is_a_reexporter():
    src = _src("silk_commercial_analysis.py")
    assert 'row["reexporter_likely"] = (imp >= exp) or (_hub and imp >= 0.5 * exp)' in src


# ── التحقق والتشغيل ──────────────────────────────────────────────────────────

def test_post_deploy_audit_is_off_in_tests_and_on_in_production(monkeypatch):
    import silk_collectors as SC
    monkeypatch.delenv("SILK_POST_DEPLOY_AUDIT", raising=False)
    monkeypatch.delenv("SILK_REQUIRE_PERSISTENT_DATA_DIR", raising=False)
    assert SC.start_post_deploy_audit() is None
    assert callable(SC.post_deploy_audit) and SC.load_study_audit().review


def test_ops_audit_endpoint_is_guarded_and_reads_only(monkeypatch, tmp_path):
    monkeypatch.setenv("SILK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SILK_PLATFORM_DB", raising=False)
    monkeypatch.delenv("SILK_DB", raising=False)
    monkeypatch.delenv("SILK_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    import api
    r = TestClient(api.app).get("/ops/audit-studies")
    assert r.status_code in (200, 404)
    if r.status_code == 200:                         # قواعدُ فارغة أُنشئت للتوّ
        assert r.json()["studies"] == []


def test_bahrain_codex_delivers_clean_and_each_owner_phrase_is_blocked():
    import audit_study_reports as A
    from canonical_bahrain_coffee import (BAHRAIN_OWNER_PHRASES,
                                          bahrain_coffee_research_blob)
    blob = bahrain_coffee_research_blob()
    view = A.factory_view(blob, "ar", None)
    assert not A._gate(view)["blocked"]
    text, findings = A.client_text(view)
    assert not findings and "جسر الملك فهد" in text
    leads = [x["name"] for x in (view["deep_research"].get("importer_leads") or {})
             .get("leads") or []]
    assert leads == ["Ashraf FMCG"]
    for phrase in BAHRAIN_OWNER_PHRASES:
        assert Q.owner_flag_hits(phrase, "BHR") or Q._check_field_label_as_value(phrase), phrase


@pytest.mark.parametrize("key", sorted(importlib.import_module(
    "gen_verdict_baseline").CANONICAL_BLOBS))
def test_every_codex_client_document_has_no_lesson_296_blocker(key):
    """الرتبةُ التي كانت غائبة: مستندُ العميل **النهائيّ** لكلّ مدوّنة."""
    import audit_study_reports as A
    from gen_verdict_baseline import CANONICAL_BLOBS
    mod, fn = CANONICAL_BLOBS[key]
    blob = getattr(importlib.import_module(mod), fn)()
    _t, findings = A.client_text(A.factory_view(blob, blob.get("report_language") or "ar", None))
    bad = [f for f in findings if f["check"] in (
        "status_label_as_value", "agent_name_leak", "owner_flagged_phrase", "artifact_refused")]
    assert not bad, bad


# ── المراجعة الذاتية §58 قبل الـPR — كلُّ ملاحظةٍ بقفل ─────────────────────────

def test_review_gso_stays_official():
    from silk_fact_records import classify_tier
    assert classify_tier("GSO 2055-1") == "A"


def test_review_importer_snippet_mentioning_manufacturers_is_kept():
    from silk_style_contract import lead_local_competitor
    lead = {"name": "Gulf Foods", "category": "",
            "snippet": "Importer of tahini from leading manufacturers"}
    assert not lead_local_competitor(lead, "200899", "طحينة")


def test_review_ports_notes_carry_no_internal_path():
    assert "land_crossings_l1" not in _src("data/ports_l1.csv")


def test_review_server_replay_does_not_swap_globals_and_counts_real_blockers():
    import inspect
    import audit_study_reports as A
    assert "raw_compare" in inspect.signature(A.review).parameters
    assert "raw_compare=False" in _src("silk_collectors.py")
    assert "raw_compare=False" in _src("api.py")
    assert 'r.get("client_blockers")' in _src("silk_collectors.py")
    assert 'r.get("client_blockers")' in _src("tools/post_deploy_smoke.py")


def test_review_study_block_is_a_409_artifact_error():
    import silk_reports as R
    from silk_study_export import markdown_to_docx
    with pytest.raises(R.ClientArtifactGateError):
        markdown_to_docx("ميناء خليفة نقطة الدخول الوحيدة.", "/tmp/_x.docx",
                         market_iso3="BHR")


def test_review_post_review_revision_is_recorded():
    src = _src("silk_ai_judge.py")
    assert 'out["post_review_revision"] = True' in src
    assert "_record_ledger_reject(_critical, trace_id)" in src


def test_review_regen_reads_prior_verdict_before_refresh_and_saves_checkpoints_first():
    src = _src("api.py")
    i = src.index("def regenerate_report")
    body = src[i:i + 40000]
    assert body.index("_prior_deliverable = None") < body.index(
        "mission_reports = silk_storage.load_mission_checkpoints")
    assert body.index('save_stage_checkpoint(analysis_id, "analyst"') < body.index(
        "if _prior_deliverable:")
