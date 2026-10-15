"""الدرس ٢٩٨ — «find all gaps» بعد الدرس ٢٩٧: ثغراتُ آلة المنع نفسِها (أداةُ
إعادة التشغيل، وتدقيقُ ما بعد النشر، وسجلُّ البلاغات) وسطوحٌ لم يبلغها الحارس
(المختصر، /ask، Markdown /analyze، شاشةُ المصنع، نمطُ الدراسة). كلُّ اختبارٍ
يقفل ثغرةً مسمّاة بإعادة إنتاجٍ مباشرة."""
import json
import os
import sqlite3
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest                                                 # noqa: E402

import silk_quality_gate as Q                                 # noqa: E402


def _src(rel: str) -> str:
    return open(os.path.join(_ROOT, rel), encoding="utf-8").read()


def _analyze_blob() -> dict:
    with open(os.path.join(_ROOT, "samples", "analysis_latest.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


# ── سجلُّ بلاغات المالك ──────────────────────────────────────────────────────

def test_every_flag_matches_its_example_and_not_its_near_miss():
    rows = Q.owner_flags()
    assert len(rows) >= 18
    for r in rows:
        iso = sorted(r["markets"])[0] if r["markets"] else ""
        assert (r.get("near_miss") or "").strip(), r["id"]
        assert Q.owner_flag_hits(r["example"], iso), r["id"]
        assert not Q.owner_flag_hits(r["near_miss"], iso), r["id"]


@pytest.mark.parametrize("text", [
    "يسـجل مستنتج من أرقام مرصودة",            # تطويل
    "المؤشـرات المرصودة المساهمة 97",
    "فشل‌عمليات جمع البيانات",             # محرفٌ صفريّ العرض
    "استكمال الحصة و١ مكونات أخرى",             # رقمٌ هنديّ
    "قياساً على الشحنات من إثيوبيا",
    "المنفذ الوحيد للدخول",
    "المنفذ الرئيسي والوحيد",
    "بوابة الدخول الوحيدة",
    "Data-collection failed",
    "the source is reach-agent",
    "main and only gateway",
    "التدفق العكسي قد يقلب الحكم",
    "بيانات كومتريد ليست رسمية",
    "UN Comtrade (non-official)",
    "متاح من مصادر غير رسمية فقط (UN Comtrade)",
    "Saudi share and 1 other components",
    "97 contributing indicators",
    "Lavazza (Switzerland)",
    "إيلي السويسرية",
])
def test_owner_flag_variants_found_by_the_audit_are_caught(text):
    assert Q.owner_flag_hits(text, "BHR"), text


def test_market_scoped_flag_reads_the_market_from_markets_or_deep_research():
    phrase = "ميناء خليفة نقطة الدخول الوحيدة."
    assert Q._view_iso3({"markets": [{"iso3": "bhr"}]}) == "BHR"
    assert Q._view_iso3({"deep_research": {"market": {"iso3": "BHR"}}}) == "BHR"
    assert Q._check_owner_flags(phrase, Q._view_iso3({"markets": [{"iso3": "BHR"}]}))


# ── الادّعاءُ الحادّ ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "انكمش الاقتصاد البحريني بنسبة 11.3% في 2026.",
    "تراجع الناتج المحلي 11.3% العام المقبل.",
    "The economy contracted by 11.3% in 2026.",
    "GDP is expected to shrink 11.3% this year.",
    "Decree No. 61/2024 makes halal certification mandatory.",
    "شهادة الحلال إلزامية بموجب القرار الوزاري 61/2024.",
    "شهادة الحلال إلزامية بالقرار رقم 61 لسنة 2024.",
])
def test_sharp_claim_catches_every_contraction_verb_and_decree_form(text):
    assert Q._check_sharp_claim_unverified({}, text), text


@pytest.mark.parametrize("text", [
    "نمت الواردات 21% بين 2019 و2024.",
    "نمو الاقتصاد 2.8% وفق IMF.",
    "في ظل تباطؤ الاقتصاد تراجعت أسعار التجزئة 9%.",
])
def test_sharp_claim_near_misses_pass(text):
    assert not Q._check_sharp_claim_unverified({}, text)


def test_a_skipped_growth_verb_does_not_swallow_a_later_contraction():
    assert Q._check_sharp_claim_unverified(
        {}, "نمو الاقتصاد 2% ثم تراجع الناتج 8% في 2026.")


def test_a_backed_sharp_claim_passes_from_any_official_row_in_the_view():
    view = {"markets": [{"components_detail": [
        {"value": -11.3, "source": "IMF WEO", "name": "gdp_growth"}]}]}
    assert not Q._check_sharp_claim_unverified(view, "انكمش الاقتصاد 11.3% في 2026.")


def test_sharp_claims_are_checked_on_every_surface():
    import silk_study_export as SE
    assert SE.study_text_blockers("شهادة الحلال إلزامية بالقرار رقم 61 لسنة 2024.", "BHR")
    gate = _src("silk_quality_gate.py")
    assert "+ _check_sharp_claim_unverified(view, _atxt)" in gate          # /analyze
    assert "+ _check_sharp_claim_unverified(view, _screen_txt))]" in gate  # شاشة المصنع
    api = _src("api.py")
    assert '_QG._check_sharp_claim_unverified(found, out["answer"])' in api  # /ask
    assert "_QG._check_sharp_claim_unverified(_bv, text)" in api           # المختصر
    assert "silk_reports.analyze_artifact_findings(_md_view, text)" in api  # report.md


# ── «غير متاح» والسجلُّ يحمل القيمة ─────────────────────────────────────────

@pytest.mark.parametrize("win", [
    " لا تتوفر بيانات", " غير معروفة", ": N/A", ": no data", " could not be estimated",
    " تبقى غير معروفة",
])
def test_absence_phrasings_right_after_the_label_are_recognised(win):
    import silk_fact_ledger as L
    assert L._absence(win), win


def test_a_wider_absence_word_about_something_else_is_not_a_mismatch():
    """مراجعة §58: «واردات السوق كبيرة وأسماء المستوردين غير معروفة» جملةٌ سليمة."""
    import silk_fact_ledger as L
    assert not L._absence(" كبيرة وأسماء المستوردين غير معروفة بعد.")


@pytest.mark.parametrize("text", [
    "Lavazza (Italy) and Nespresso (Switzerland)",
    "لافازا (إيطاليا) ونستله (سويسرا)",
    "| Lavazza | Italy | Nespresso | Switzerland |",
    "the chilly Swiss Alps",
])
def test_brand_origin_row_spares_correct_competitor_lists(text):
    assert not Q.owner_flag_hits(text, "BHR"), text


def test_ask_context_puts_ledger_values_first():
    import silk_render as R
    from gen_client_report_sample import build_sample_view
    ctx = R.analysis_context({"view": build_sample_view("ar")})
    assert "سجلّ الحقائق — واردات السوق" in ctx
    assert ctx.index("سجلّ الحقائق") < ctx.index("التقرير المكتوب")


# ── الإسناد والتصنيف ─────────────────────────────────────────────────────────

def _missions(note: str) -> dict:
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    return {"trade_flow": AgentReport(
        "LLMAgent:trade_flow", [DataPoint("x", "Src A", 0.9, note, "2026-10-15")],
        False, "s")}


@pytest.mark.parametrize("note,value", [
    ("1,150 tonnes", 150.0), ("150,000 USD", 150.0), ("سنة 2017", 2017.0)])
def test_attribution_ignores_thousands_separators_and_yearish_values(note, value):
    import silk_fact_ledger as L
    assert L._attribution(_missions(note), "trade_flow", "m", value)["source"] == ""


def test_attribution_still_matches_the_real_number():
    import silk_fact_ledger as L
    assert L._attribution(_missions("150 tonnes"), "trade_flow", "m", 150.0)["source"] == "Src A"


def test_interest_bearing_source_name_stays_x_even_with_an_official_word():
    from silk_fact_records import classify_tier
    assert classify_tier("Bahrain Chamber of Commerce — customs data") == "X"
    assert classify_tier("Coffee Producers Association / Ministry of Agriculture") == "X"
    assert classify_tier("GCC Secretariat", "الاتحاد الجمركي الخليجي") == "A"


# ── أداةُ إعادة التشغيل وتدقيقُ ما بعد النشر ─────────────────────────────────

def test_non_deep_study_is_rebuilt_with_render_docx_not_reported_blocked():
    import audit_study_reports as A
    blob = _analyze_blob()
    assert not blob.get("deep_research")
    _t, findings = A.client_text(A.factory_view(blob, "ar", None))
    assert not [f for f in findings if f["check"] == "artifact_refused"], findings


def _seed(tmp_path, n: int):
    import silk_storage
    from canonical_bahrain_coffee import bahrain_coffee_research_blob
    edb = str(tmp_path / "silk.db")
    silk_storage.init_db(edb)
    ids = [silk_storage.save_analysis(bahrain_coffee_research_blob(), path=edb)
           for _ in range(n)]
    pdb = str(tmp_path / "platform.db")
    con = sqlite3.connect(pdb)
    con.execute("CREATE TABLE studies (id INTEGER PRIMARY KEY, analysis_id INTEGER,"
                " product TEXT, market_pref TEXT, state TEXT, report_language TEXT,"
                " run_error TEXT)")
    for i, aid in enumerate(ids, 1):
        con.execute("INSERT INTO studies VALUES (?,?,?,?,?,?,?)",
                    (i, aid, "قهوة", "BHR", "done", "ar", None))
    con.commit()
    con.close()
    return pdb, edb, ids


def test_a_study_that_fails_to_build_never_inherits_the_previous_view(tmp_path, monkeypatch):
    import audit_study_reports as A
    pdb, edb, ids = _seed(tmp_path, 2)
    real = A.factory_view

    def flaky(blob, lang, aid=None):
        if aid == ids[1]:
            raise ValueError("boom")
        return real(blob, lang, aid)
    monkeypatch.setattr(A, "factory_view", flaky)
    rows = A.review(pdb, edb, None, False, client=True, raw_compare=False)
    assert "client_findings" in rows[0] and not A.unverifiable(rows[0])
    assert A.unverifiable(rows[1]) and "client_findings" not in rows[1]


def test_audit_pages_with_limit_and_after(tmp_path):
    import audit_study_reports as A
    pdb, edb, _ids = _seed(tmp_path, 3)
    first = A.review(pdb, edb, None, False, limit=2, after=0, raw_compare=False)
    rest = A.review(pdb, edb, None, False, limit=2, after=first[-1]["study"],
                    raw_compare=False)
    assert [r["study"] for r in first] == [1, 2] and [r["study"] for r in rest] == [3]


def test_post_deploy_result_is_counted_and_reaches_health(monkeypatch, tmp_path):
    import silk_collectors as SC
    pdb, edb = tmp_path / "p.db", tmp_path / "e.db"
    pdb.write_bytes(b"")
    edb.write_bytes(b"")
    fake = types.SimpleNamespace(
        _platform_db=lambda _c: str(pdb), _engine_db=lambda _c: str(edb),
        review=lambda *a, **k: [
            {"study": 1, "status": "ok", "gate": {"blocked": True}},
            {"study": 2, "status": "ok", "gate_error": "ValueError: x"},
            {"study": 3, "status": "ok", "gate": {"blocked": False}}],
        unverifiable=lambda r: bool(r.get("gate_error") or r.get("client_error")))
    monkeypatch.setattr(SC, "load_study_audit", lambda: fake)
    out = SC.post_deploy_audit()
    assert [b["study"] for b in out["blocked"]] == [1] and out["unverifiable"] == [2]
    assert SC.LAST_POST_DEPLOY_AUDIT["blocked"] == 1
    assert SC.LAST_POST_DEPLOY_AUDIT["unverifiable"] == 1
    from fastapi.testclient import TestClient
    import api
    h = TestClient(api.app).get("/health").json()
    assert h["post_deploy_audit"]["blocked"] == 1
    assert any("تدقيق ما بعد النشر" in w for w in h.get("warnings") or [])
    monkeypatch.delenv("SILK_API_KEY", raising=False)
    last = TestClient(api.app).get("/ops/audit-studies?last=1").json()
    assert last["last_post_deploy_audit"]["unverifiable_studies"] == [2]
    SC.LAST_POST_DEPLOY_AUDIT.clear()


def test_smoke_pages_and_counts_unverifiable_studies():
    src = _src("tools/post_deploy_smoke.py")
    assert "limit=20&after={after}" in src and "تعذّرت إعادةُ بنائها" in src


# ── التقييم والرتبة ٢ ────────────────────────────────────────────────────────

def test_eval_reports_owner_flag_hits_when_the_gate_refuses_the_document():
    import silk_evals as E
    from canonical_bahrain_coffee import bahrain_coffee_research_blob
    blob = bahrain_coffee_research_blob()
    rep = blob["deep_research"]["report"]
    rep["report"] += "\nميناء خليفة هو نقطة الدخول الوحيدة للبضائع.\n"
    out = E.structural_checks(blob, {"structural": {"no_owner_flags": True}})
    assert out["passed"] is False
    assert out["checks"]["no_owner_flags"]["hits"]


def test_rung2_server_seeds_the_bahrain_codex():
    assert "BAHRAIN_ID = silk_storage.save_analysis(bahrain_coffee_research_blob()" in _src(
        "tools/live_shape_server.py")
    assert "def test_bahrain_coffee_codex_exports_clean_over_real_http" in _src(
        "tests/test_rung2_real_server.py")


# ── سطوحُ العميل ─────────────────────────────────────────────────────────────

def test_internal_analyze_export_is_never_gated(monkeypatch, tmp_path):
    import silk_render
    import silk_reports as R
    bad = [{"check": "owner_flagged_phrase", "repairable": False, "note": "x"}]
    monkeypatch.setattr(R, "analyze_artifact_findings", lambda v, t: bad)
    view = silk_render.build_view(_analyze_blob())
    with pytest.raises(R.ClientArtifactGateError):
        R.render_docx(view, str(tmp_path / "a.docx"))
    view["internal"] = True
    assert R.render_docx(view, str(tmp_path / "b.docx"))


def test_questions_table_drops_an_all_dash_how_column_in_markdown_and_dashboard():
    import silk_reports as R
    view = {"ledger": {"critical_questions": [
        {"question": "س؟", "answer": "ج", "answered": True}]}}
    md = "\n".join(R._questions_md(view, "ar"))
    assert "كيف تعرفه" not in md and "| س؟ | ج |" in md
    assert "keepHow" in _src("web/index.html")


def test_entry_door_named_in_the_body_joins_the_leads_list():
    import silk_render
    import silk_reports as R
    from canonical_bahrain_coffee import bahrain_coffee_research_blob
    for mutate in ("drop", "legal_suffix"):
        blob = bahrain_coffee_research_blob()
        leads = blob["deep_research"]["importer_leads"]["leads"]
        if mutate == "drop":
            del leads[2]
        else:
            leads[2]["name"] = "ASHRAF FMCG W.L.L."
        view = silk_render.build_view(blob)
        dr = view["deep_research"]
        # العرضُ (اللوحة والشاشة) والمستندُ يقرآن القائمةَ نفسَها.
        for rows in (dr["importer_leads"]["leads"], R._leads_data(dr)[0]):
            names = [x["name"].lower() for x in rows]
            assert any(n.startswith("ashraf fmcg") for n in names), (mutate, names)
            assert not any("roaster" in n or "café" in n for n in names), names


def test_entry_door_additions_are_entities_in_this_market_only():
    import silk_render
    from canonical_bahrain_coffee import bahrain_coffee_research_blob
    from silk_data_layer import DataPoint
    blob = bahrain_coffee_research_blob()
    del blob["deep_research"]["importer_leads"]["leads"][2]
    ci = blob["deep_research"]["missions"]["channels_importers"]
    for v in ("موزّعون", "سلاسل الهايبرماركت", "Carrefour UAE"):
        ci.findings.append(DataPoint(v, "بحث ويب", 0.5, "[entry_door] x", "2026-10-15"))
    blob["deep_research"]["report"]["report"] += (
        "\nموزّعون وسلاسل الهايبرماركت وCarrefour UAE خيارات.\n")
    names = [x["name"] for x in silk_render.build_view(blob)["deep_research"]
             ["importer_leads"]["leads"]]
    assert names == ["Ashraf FMCG"], names


def test_lead_key_strips_only_a_separate_legal_suffix():
    import silk_reports as R
    assert R._lead_key("Tesco") == "tesco" and R._lead_key("Sysco") == "sysco"
    assert R._lead_key("Ashraf FMCG W.L.L.") == "ashraf fmcg"
    assert not R._key_in("cost", "costco wholesale")


def test_factory_screen_drops_only_the_flagged_sentences():
    text = ("## 8. اللوجستيات\nالمسار برّي عبر الجسر. ميناء خليفة نقطة الدخول "
            "الوحيدة. انكمش الاقتصاد 11.3% العام المقبل.\nسطر سليم.")
    out = Q.strip_flagged_sentences(text, {"market": {"iso3": "BHR"}})
    assert "الوحيدة" not in out and "11.3" not in out
    assert "المسار برّي عبر الجسر." in out and "سطر سليم." in out
    table = "| أ. | ميناء خليفة نقطة الدخول الوحيدة |\n| ب | ج |"
    assert Q.strip_flagged_sentences(table, {"market": {"iso3": "BHR"}}) == "| ب | ج |"
    assert "strip_flagged_sentences(_rep[\"text\"], view)" in _src("silk_platform/api.py")


def test_post_review_revision_must_reduce_the_critical_issues_themselves():
    src = _src("silk_ai_judge.py")
    assert ("len(_crit_after) < len(_critical) and len(_after) <= "
            "len(_ledger_unresolved)") in src


def test_a_mirror_year_between_direct_years_is_outside_the_growth_window():
    import silk_deep_pillars as P
    from canonical_bahrain_coffee import bahrain_coffee_research_blob
    from silk_data_layer import DataPoint
    blob = bahrain_coffee_research_blob()
    tf = blob["deep_research"]["missions"]["trade_flow"]
    tf.findings.append(DataPoint(5_000_000.0, "UN Comtrade (مرآة)", 0.6,
                                 "إجمالي واردات السوق HS090121 2020 (مرآة)",
                                 "2026-10-15", status="mirrored", data_year=2020))
    s = P.import_series(blob["deep_research"]["missions"])
    assert s["basis_year_set"] == [2019, 2021, 2024], s["basis_year_set"]
