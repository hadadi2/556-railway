"""حُرّاسُ مراجعةِ موجةِ الأعمدة/السقف المدفوع — one lock per review finding.

كلُّ اختبارٍ يقفل إصلاحَ ملاحظةِ `/code-review` قبل الدمج (البند ٥٨:
self-review catches what hermetic tests structurally cannot — ثمّ يُقفَل
الإصلاحُ باختبار). هرمتيٌّ بالكامل: قراءةُ مصدرٍ + سلوكٌ محليّ، بلا شبكة.

Run: python3 -m pytest tests/test_pillar_paidcap_review_fixes.py -q
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def _read(rel: str) -> str:
    """اقرأ ملف مصدرٍ — و«api.py» تعني **طبقة الـAPI كاملةً**.

    البند ٧ (تدقيق 2026-08-27): جسم تشغيلة `/research` انتقل حرفياً إلى
    `silk_research_pipeline.py`. الحُرّاس هنا تسأل «هل الوصلة في مسار
    الطلب؟» لا «هل هي في هذا الملف؟» — فحدود الملفات تفصيلُ إعادة
    هيكلة، والوصلة هي العقد. راجع `tests/api_source.py`.
    """
    if rel == "api.py":
        from tests.api_source import api_layer
        return api_layer()
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ── #1 · مفتاحُ بعثةِ الاقتصاد الكلّي الصحيح ─────────────────────────────
def test_pillar_inputs_read_demographics_economy_not_phantom_key():
    import silk_deep_pillars as DP
    src = _read("silk_deep_pillars.py")
    assert "macro_economy" not in src, "المفتاحُ الوهميّ عاد"
    assert 'demographics_economy") + trade' in src
    gdp_note = "نصيب الفرد من الناتج المحلي 52000 دولار"
    dr = {"missions": {"demographics_economy": {
        "findings": [{"value": gdp_note, "note": gdp_note}]}}}
    pi = DP.build_pillar_inputs(dr)
    assert pi["market_attractiveness"]["gdp_per_capita_usd"] == 52000.0


# ── #12 · المقدار والوزن في استخراج الرقم ────────────────────────────────
def test_numeric_rejects_weight_as_usd_and_applies_magnitude():
    import silk_deep_pillars as DP

    def F(note):
        return [{"value": note, "note": note}]
    assert DP._numeric(F("الوزن الصافي للواردات 2,300,000 كجم"),
                       "tam_usd") is None
    assert DP._numeric(F("إجمالي الواردات 350 مليون دولار"),
                       "tam_usd") == 350_000_000.0
    assert DP._numeric(F("واردات السوق 3.5 مليار دولار"),
                       "tam_usd") == 3_500_000_000.0
    assert DP._numeric(F("قيمة الوحدة الحدودية 3.2 دولار/كجم"),
                       "border_unit_value_usd_kg") == 3.2
    # مراجعة §58 (self-review): المقدارُ لا ينزف من رقمٍ لاحقٍ إلى السنة
    assert DP._numeric(F("واردات 2023: 129.6 مليون دولار"),
                       "tam_usd") == 129_600_000.0
    # مطابقةُ رمزٍ كاملٍ لا تحت-سلسلة: «طن» جزءُ «قطن»، «kg» جزءُ «background»
    assert DP._numeric(F("واردات 350 قطن مصري خام"), "tam_usd") is None
    assert DP._numeric(F("GDP per capita 25000 background"),
                       "gdp_per_capita_usd") == 25000.0
    assert DP._numeric(F("نصيب الفرد خالف التوقعات 52000 دولار"),
                       "gdp_per_capita_usd") == 52000.0
    # إعادة مراجعة §58: المقدارُ لا يُطبَّق على مقياسٍ غيرِ مالٍ مطلق (نسبة)
    assert DP._numeric(F("حصة السعودية 5 من أصل مليون وحدة"),
                       "saudi_share_pct") == 5.0
    # مُميِّزُ الرقمِ واحدٌ مُشترَك بين الوحدتين (لا تكرار)
    import silk_economics as E
    assert E._num_to_float_eu("2,350") == DP._num_to_float("2,350") == 2350.0
    # إعادة مراجعة §58×٣: رقمٌ بشكلِ سنةٍ × مقدار لا يُختلَق قيمةً (عقد الاختلاق)
    assert DP._numeric(F("واردات عام 2023 مليون دولار في السوق"),
                       "tam_usd") is None


# ── #4 · الفاصلةُ فاصلُ آلافٍ لا عشريّ في اقتصاد البعثات ─────────────────
def test_mission_numeric_treats_comma_as_thousands():
    import silk_economics as E
    dr = {"missions": {"competitors": {"findings": [
        {"value": "HHI يقارب 3,400", "note": "HHI يقارب 3,400"}]}}}
    val, _ = E._mission_numeric(dr, "competitors", E._HHI_WORDS, 0.0, 10_000.0)
    assert val == 3400.0, val
    assert E.hhi_is_high(val) is True
    dr2 = {"missions": {"competitors": {"findings": [
        {"value": "HHI يقارب 2,350", "note": "HHI يقارب 2,350"}]}}}
    v2, _ = E._mission_numeric(dr2, "competitors", E._HHI_WORDS, 0.0, 10_000.0)
    assert v2 == 2350.0, v2
    # مراجعة §58 (self-review): الفاصلةُ العشريّةُ الأوروبية لا تُضخَّم ١٠٠×
    dr3 = {"missions": {"competitors": {"findings": [
        {"value": "HHI يقارب 2,35", "note": "HHI يقارب 2,35"}]}}}
    v3, _ = E._mission_numeric(dr3, "competitors", E._HHI_WORDS, 0.0, 10_000.0)
    assert v3 == 2.35, v3
    # السلوكُ أعلاه يُثبِت التمييز؛ والبنيةُ: يمرّ الرقمُ بمُميِّز الآلاف/العشريّ
    assert "_num_to_float_eu(m.group(1))" in _read("silk_economics.py")


# ── #9 · قاعدةُ القرار نِسَبٌ مئوية لا كسورٌ خام ─────────────────────────
def test_decision_rule_text_uses_percentages_only():
    import silk_decision as D
    rule = D.decision_rule_text()
    assert "0.65" not in rule and "0.45" not in rule
    assert "65%" in rule and "45%" in rule and "60%" in rule


# ── #14 · `_provenance` بلا مُعامِلِ لغةٍ ميّت ───────────────────────────
def test_provenance_has_no_dead_lang_param():
    import inspect

    import silk_render as R
    params = list(inspect.signature(R._provenance).parameters)
    assert params == ["result"], params


# ── #15 · فرعا FAIL في ملخّص الجودة متطابقان ⇒ طُوِيا ────────────────────
def test_client_quality_summary_fail_note_collapsed():
    import silk_export_gate as EG
    for lang in ("ar", "en"):
        out = EG.client_quality_summary({"verdict": "FAIL", "blocking": [1]},
                                        lang)
        assert out["note"] == EG.factory_message(lang)
    src = _read("silk_export_gate.py")
    assert 'factory_message("en"))' not in src, "الفرعُ الزائدُ عاد"


# ── #10 · صمّامُ استرجاعِ WGI يُحترَم على مسار م٤ ───────────────────────
def test_gap_recovery_wgi_route_respects_valve(monkeypatch):
    import silk_gap_recovery as G
    src = _read("silk_gap_recovery.py")
    assert 'recoverer_enabled("wgi") and _recover_wgi(' in src
    monkeypatch.setenv("SILK_GAP_RECOVER_WGI", "0")
    assert G.recoverer_enabled("wgi") is False


# ── #11 · ميزانيةُ الويب لا تُستنزَف بلا-عمليّات ────────────────────────
def test_gap_recovery_web_budget_charged_only_on_real_call():
    src = _read("silk_gap_recovery.py")
    # م٥: الخصمُ داخل فرعِ تفعيل web_search حصراً (وهو مطفأٌ بنيوياً ⇒ لا خصم)
    assert 'if recoverer_enabled("web_search"):' in src
    # الموزّعون: `web_used += 1` **داخل** فرعِ التفعيل لا قبله
    assert ('            if recoverer_enabled("distributors"):\n'
            '                web_used += 1\n') in src


# ── #3 · نسخُ SQLite لا يُسرِّب واصفات ملفّات ────────────────────────────
def test_backup_closes_connections_no_fd_leak(tmp_path, monkeypatch):
    import sqlite3

    import silk_backup as B
    db = tmp_path / "src.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE t(x)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()
    monkeypatch.setattr(B, "_targets", lambda: [("t", str(db))])
    dest = str(tmp_path / "bk")

    def _fd_count():
        try:
            return len(os.listdir("/proc/self/fd"))
        except OSError:
            pytest.skip("لا /proc/self/fd على هذه المنصّة")
    B.run_backup(dest)
    before = _fd_count()
    for _ in range(30):
        B.run_backup(dest)
    after = _fd_count()
    assert after - before <= 2, f"تسريبُ واصفات: {before} -> {after}"
    # R5 (DB-6/CONC-7): النسخُ يمرّ بالمُوصِّل المشترك — الإبرةُ تتبعه؛ تأكيدُ
    # الواصفات أعلاه هو القفلُ السلوكيّ، والإبرةُ تُبقي `closing` صريحاً.
    assert "closing(silk_sqlite.connect(src" in _read("silk_backup.py")


# ── #6 · بوّابةُ تأكيد HS على التعميق المدفوع ───────────────────────────
def test_web_deepen_does_not_forge_hs_confirmed():
    src = _read("web/index.html")
    assert "hs_confirmed:!!S.hsConfirmed," in src
    assert "hs_confirmed:!!(S.raw&&S.raw.hs_code)" not in src


# ── #7 · الكاتبُ يستلم سطرَ الفجوات الحقيقيّ ─────────────────────────────
def test_writer_verdict_summary_carries_real_mission_gaps():
    import silk_ai_judge as J

    class R:
        def __init__(self, summary, failed=False):
            self.summary, self.failed = summary, failed
            self.agent_name, self.findings = "x", []
    missions = {"trade_flow": R("مبني على استشهاد. فجوات: لا بيانات أسعار")}
    gaps = J._mission_declared_gaps(missions)
    assert any("لا بيانات أسعار" in g for g in gaps)
    v = {"verdict": "PRELIMINARY GO", "confidence": 0.5,
         "data_gaps": [], "contributing_findings": []}
    line = J._summarize_verdict(v, gaps)
    tail = line.split("الفجوات المعلنة:")[1]
    assert "لا شيء" not in tail and "تحتاج تحققاً" in tail


# ── #8 · رفضُ الجودةِ على المصنع = 409 لا 501/503 ────────────────────────
def test_client_artifact_gate_error_is_distinct_type():
    import silk_reports as REP
    assert issubclass(REP.ClientArtifactGateError, RuntimeError)
    e = REP.ClientArtifactGateError("x", findings=[{"check": "c", "note": "n"}])
    assert e.findings and e.findings[0]["check"] == "c"
    papi = _read("silk_platform/api.py")
    assert "_sr.ClientArtifactGateError as exc" in papi
    assert '_artifact_gate_409(exc, row, "docx")' in papi
    assert '_artifact_gate_409(exc, row, "pdf")' in papi


# ── #2 + #13 · لا حجزَ سقفٍ مدفوع لتصديرٍ لا يستدعي كلود ─────────────────
def test_client_prose_needed_gates_paid_reservation():
    import silk_export_gate as EG
    assert EG.client_prose_needed({}) is False
    assert EG.client_prose_needed({"client_fallback_prose": {"x": "y"},
                                   "report": {"text": "## 1. ش"}}) is False
    assert "_eg.client_prose_needed(_dr)" in _read("api.py")
    assert "_eg.client_prose_needed(_dr)" in _read("silk_platform/api.py")


# ── #5 · صفُّ السوق العميق يحمل country/score/confidence ─────────────────
def test_deep_market_row_source_carries_country_and_score():
    api = _read("api.py")
    assert '"country": market_ref.name_ar or market_ref.name_en,' in api
    assert 'row["total_score"] = decision.get("score")' in api
    assert 'row["confidence"] = decision.get("confidence")' in api
    assert 'isinstance(_score, (int, float))' in _read("silk_render.py")
