"""اختبارات طبقة سد الفجوات — gap recovery layer locks (المرحلة 0).

هرمتية بالكامل: كل نداء شبكة مُرقَّع. تثبت قيود الأمر التنفيذي:
الصمّام مُطفأ افتراضياً والإطفاء = ناتج مطابق حرفياً؛ التصنيف السباعي؛
OPS لا يصل للعميل ويُسجَّل للمشغّل؛ المسارات م٢/م٣/م٤ تسترجع وتحذف الفجوة
من الملخّص؛ م٥ محكوم بحاجز الرصيد والسقف؛ السقوف تُحترم؛ الدمج الإلزامي؛
فشل الطبقة كلياً لا يوقف المسار؛ وAST يمنع استدعاءها من داخل وكيل.
"""
from __future__ import annotations

import ast
import copy
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_gap_recovery as GR  # noqa: E402
from silk_agents import AgentReport  # noqa: E402
from silk_data_layer import DataPoint  # noqa: E402
from silk_market_resolver import MarketRef  # noqa: E402


class _Env:
    """عازل بيئة مضمون الاسترجاع (LESSONS 55)."""

    def __init__(self, **vals):
        self.vals, self.old = vals, {}

    def __enter__(self):
        for k, v in self.vals.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _mref() -> MarketRef:
    return MarketRef(iso3="JOR", m49="400", name_en="Jordan", name_ar="الأردن")


def _reports(**summaries) -> dict:
    return {k: AgentReport(f"LLMMissionAgent:{k}", [], False, s)
            for k, s in summaries.items()}


# ── الصمّام · the valve ─────────────────────────────────────────────────────

def test_disabled_by_default_and_output_is_untouched():
    with _Env(SILK_GAP_RECOVERY_ENABLED=None):
        assert GR.enabled() is False
        reports = _reports(risk_news="نتائج | فجوات: الاستقرار السياسي غير متاح")
        before = copy.deepcopy({k: (v.summary, len(v.findings))
                                for k, v in reports.items()})
        out = GR.recover(reports, market_ref=_mref())
        assert out == {"enabled": False}
        after = {k: (v.summary, len(v.findings)) for k, v in reports.items()}
        assert after == before  # الإطفاء = ناتج مطابق حرفياً


# ── التصنيف · classification ────────────────────────────────────────────────

def test_classification_seven_way():
    assert GR.classify("WTO TTD غير مُهيَّأ (WTO_TTD_API_KEY غير مضبوط)") == GR.OPS
    assert GR.classify("تجاوز حد المعدل 429 من Google Trends") == GR.RATE
    assert GR.classify("حصص الدول المورّدة والأوزان بالأطنان غير متاحة") == GR.FIELD
    assert GR.classify("نصيب الفرد من الاستهلاك غير متاح") == GR.DERIVE
    assert GR.classify("الاستقرار السياسي غير متاح بسبب خطأ في واجهة البنك الدولي") == GR.FETCH
    assert GR.classify("البيان خلف اشتراك مدفوع") == GR.PAID
    assert GR.classify("بيان غير مجموع في أي مصدر معروف") == GR.NONE
    assert GR.classify("فشل عام", status="fetch_failed") == GR.FETCH


def test_priority_tiers():
    assert GR.priority("التعرفة الجمركية غير متاحة") == 1
    assert GR.priority("موسمية رمضان غير متاحة") == 2
    assert GR.priority("نسبة الفئة العمرية 15-24") == 3


# ── OPS — قاعدة ملزمة: لا يصل للعميل، يُسجَّل للمشغّل ───────────────────────

def test_ops_removed_from_summary_and_logged_to_operator():
    reports = _reports(
        tariff="نتائج | فجوات: WTO TTD غير مُهيَّأ (WTO_TTD_API_KEY غير مضبوط)")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1", SILK_GAP_TIMEOUT_S="1"), \
            patch("silk_ops_log.record_service_failure") as rec:
        out = GR.recover(reports, market_ref=_mref())
    assert "غير مضبوط" not in reports["tariff"].summary
    assert "فجوات:" not in reports["tariff"].summary
    assert out["ops"] and out["ops"][0]["mission"] == "tariff"
    assert rec.called  # سُجّل للمشغّل (LESSONS 26)


# ── م٤ — WGI من نقطة النهاية البديلة ────────────────────────────────────────

def test_m4_wgi_recovery_appends_finding_and_drops_clause():
    reports = _reports(
        risk_news="نتائج | فجوات: الاستقرار السياسي غير متاح بسبب خطأ في واجهة البنك الدولي")
    fake = DataPoint(value=-0.4, source="World Bank", confidence=0.9,
                     note="PV.EST 2023", retrieved_at="2026-08-19")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1"), \
            patch("silk_data_layer.world_bank", return_value=fake) as wb:
        out = GR.recover(reports, market_ref=_mref())
    assert wb.called
    r = reports["risk_news"]
    assert any("طبقة سد الفجوات" in f.note for f in r.findings)
    assert "فجوات:" not in r.summary
    assert out["closed"] == 1 and out["by_route"].get("م٤") == 1


def test_m4_failure_leaves_declared_gap_not_fabrication():
    reports = _reports(
        risk_news="نتائج | فجوات: الاستقرار السياسي غير متاح بسبب خطأ في واجهة البنك الدولي")
    none_dp = DataPoint(value=None, source="World Bank", confidence=0.0,
                        note="فشل", retrieved_at="2026-08-19")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1", SILK_GAP_MAX_WEB_SEARCH="0"), \
            patch("silk_data_layer.world_bank", return_value=none_dp):
        out = GR.recover(reports, market_ref=_mref())
    assert reports["risk_news"].findings == []      # لا اختلاق
    assert "فجوات:" in reports["risk_news"].summary  # الفجوة تبقى معلنة
    assert out["residual"] and out["residual"][0]["tried"]


# ── م٢ — توسيع استعلام Comtrade (حصص + أوزان) ──────────────────────────────

def test_m2_partner_shares_from_same_source():
    reports = _reports(
        market_size="نتائج | فجوات: حصص الدول المورّدة والأوزان بالأطنان غير متاحة")
    recs = [{"partnerDesc": "France", "primaryValue": 600.0, "netWgt": 100.0},
            {"partnerDesc": "Egypt", "primaryValue": 400.0, "netWgt": 90.0}]
    with _Env(SILK_GAP_RECOVERY_ENABLED="1"), \
            patch("silk_data_layer.comtrade_trade", return_value=recs):
        out = GR.recover(reports, market_ref=_mref(), hs_code="040120",
                         year=2024)
    r = reports["market_size"]
    shares = [f.value for f in r.findings]
    assert 60.0 in shares and 40.0 in shares
    assert all("م٢" in f.note for f in r.findings)
    assert out["by_route"].get("م٢") == 1


# ── م٣ — الاشتقاق الحسابي المعلَن ───────────────────────────────────────────

def test_m3_per_capita_derived_with_formula_and_mostantaj_tag():
    r = AgentReport("LLMMissionAgent:consumption", [
        DataPoint(value=1_000_000.0, source="UN Comtrade", confidence=0.8,
                  note="إجمالي واردات الحليب", retrieved_at="2026-08-19",
                  data_year=2024)],
        False, "نتائج | فجوات: نصيب الفرد من الاستهلاك غير متاح")
    pop = DataPoint(value=10_000_000.0, source="World Bank", confidence=0.9,
                    note="SP.POP.TOTL", retrieved_at="2026-08-19")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1"), \
            patch("silk_data_layer.world_bank", return_value=pop):
        out = GR.recover({"consumption": r}, market_ref=_mref())
    derived = [f for f in r.findings if "مستنتَج" in (f.note or "")]
    assert derived and derived[0].value == 0.1
    assert "÷" in derived[0].note            # المعادلة مذكورة
    assert derived[0].confidence <= 0.6      # مشتق لا مشاهد
    assert out["by_route"].get("م٣") == 1


# ── م٥ — محكوم بحاجز الرصيد والسقف والأولوية ────────────────────────────────

def test_m5_blocked_when_ai_extras_blocked():
    reports = _reports(pricing="نتائج | فجوات: أسعار الرف غير متاحة")
    import silk_context
    with _Env(SILK_GAP_RECOVERY_ENABLED="1"), \
            silk_context.block_ai_extras(), \
            patch("silk_llm_runtime.run_llm_agent") as llm:
        GR.recover(reports, market_ref=_mref())
    assert not llm.called


def test_m5_cap_zero_means_no_model_call():
    reports = _reports(pricing="نتائج | فجوات: أسعار الرف غير متاحة")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1", SILK_GAP_MAX_WEB_SEARCH="0"), \
            patch("silk_llm_runtime.run_llm_agent") as llm:
        GR.recover(reports, market_ref=_mref())
    assert not llm.called


def test_m5_priority3_never_reaches_web_search():
    reports = _reports(demo="نتائج | فجوات: نسبة الفئة العمرية 15-24 غير متاحة")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1"), \
            patch("silk_llm_runtime.run_llm_agent") as llm:
        GR.recover(reports, market_ref=_mref())
    assert not llm.called


# ── السقوف والدمج · caps + mandatory dedup ──────────────────────────────────

def test_timeout_cap_stops_the_layer():
    reports = _reports(
        a="نتائج | فجوات: الاستقرار السياسي غير متاح بسبب خطأ في واجهة البنك الدولي",
        b="نتائج | فجوات: سيادة القانون غير متاحة بسبب خطأ في واجهة البنك الدولي")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1", SILK_GAP_TIMEOUT_S="0",
              SILK_GAP_MAX_WEB_SEARCH="0"), \
            patch("silk_gap_recovery.time.monotonic", return_value=100.0), \
            patch("silk_data_layer.world_bank") as wb:
        out = GR.recover(reports, market_ref=_mref())
    assert not wb.called            # المهلة صفر — لا نداء واحد
    assert out["after"] == out["before"]


def test_identical_gaps_across_missions_are_merged():
    clause = "حصص الدول المورّدة غير متاحة"
    reports = _reports(a=f"نتائج | فجوات: {clause}",
                       b=f"نتائج | فجوات: {clause}")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1", SILK_GAP_MAX_WEB_SEARCH="0"), \
            patch("silk_data_layer.comtrade_trade", return_value=None):
        out = GR.recover(reports, market_ref=_mref(), hs_code="040120",
                         year=2024)
    assert out["before"] == 1                       # دمج إلزامي (§7)
    assert "فجوات:" not in reports["b"].summary     # المكرّرة حُذفت


# ── لا حجب: فشل الطبقة كلياً لا يوقف المسار ─────────────────────────────────

def test_pipeline_wraps_recover_in_try_except():
    # البند ٧ (تدقيق 2026-08-27): الحارس يسأل عن طبقة الـAPI
    # لا عن ملف — الجسم انتقل لـsilk_research_pipeline حرفياً.
    from tests.api_source import api_layer
    src = api_layer()
    assert "silk_gap_recovery.recover(" in src
    idx = src.index("silk_gap_recovery.recover(")
    window = src[idx - 600:idx + 600]
    assert "try:" in window and "except Exception" in window, (
        "نداء الطبقة في api.py غير محاط بـtry/except — فشلها سيوقف التشغيلة")


# ── AST: لا وكيل يستدعي الطبقة — تُستدعى من المسار فقط ─────────────────────

def test_no_agent_module_imports_gap_recovery():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    forbidden = ["silk_missions.py", "silk_llm_runtime.py", "silk_research.py",
                 "silk_agents.py", "silk_trends_agent.py", "silk_data_layer.py"]
    for name in forbidden:
        tree = ast.parse(open(os.path.join(root, name), encoding="utf-8").read())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            assert "silk_gap_recovery" not in mods, (
                f"{name} يستورد طبقة سد الفجوات — ممنوع استدعاؤها من داخل وكيل")


# ── §6 الموزعون: بيان النقص خلف الصمّام ─────────────────────────────────────

def test_leads_shortfall_statement_only_when_enabled():
    import silk_gmaps
    q_off = None
    with _Env(SILK_GAP_RECOVERY_ENABLED=None):
        q_off = silk_gmaps.localized_queries("تمور", _mref())
    with _Env(SILK_GAP_RECOVERY_ENABLED="1"):
        q_on = silk_gmaps.localized_queries("تمور", _mref())
    assert q_on[:len(q_off)] == q_off               # إضافي بحت
    assert any("FMCG" in q for q in q_on)
    assert any("موزع أغذية" in q for q in q_on)
    assert not any("FMCG" in q for q in q_off)      # الإطفاء = اليوم حرفياً


# ── أقفال المراجعة الذاتية §58 على هذه الموجة ───────────────────────────────

def test_m2_excludes_world_aggregate_row():
    """صف العالم (partnerCode 0) لا يدخل المقام ولا يظهر كمورّد."""
    reports = _reports(
        market_size="نتائج | فجوات: حصص الدول المورّدة والأوزان بالأطنان غير متاحة")
    recs = [{"partnerCode": "0", "partnerDesc": "World", "primaryValue": 1000.0},
            {"partnerCode": "251", "partnerDesc": "France", "primaryValue": 600.0},
            {"partnerCode": "818", "partnerDesc": "Egypt", "primaryValue": 400.0}]
    with _Env(SILK_GAP_RECOVERY_ENABLED="1"), \
            patch("silk_data_layer.comtrade_trade", return_value=recs):
        GR.recover(reports, market_ref=_mref(), hs_code="040120", year=2024)
    r = reports["market_size"]
    assert sorted(f.value for f in r.findings) == [40.0, 60.0]
    assert not any("World" in (f.note or "") for f in r.findings)


def test_paid_gap_mentioning_api_key_stays_declared_not_ops():
    """فجوة مدفوعة تذكر مفتاحها تبقى معلنة للعميل — لا تُحذف كعطل تشغيلي."""
    text = "بيانات Volza خلف اشتراك مدفوع — مفتاح API غير مضبوط"
    assert GR.classify(text) == GR.PAID
    reports = _reports(pricing=f"نتائج | فجوات: {text}")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1", SILK_GAP_MAX_WEB_SEARCH="0"):
        out = GR.recover(reports, market_ref=_mref())
    assert "فجوات:" in reports["pricing"].summary   # بقيت معلنة
    assert not out["ops"]


def test_m3_never_divides_a_share_percentage():
    """نسبة حصة («حصة X من واردات…») لا تُستعمل بسطاً في نصيب الفرد."""
    r = AgentReport("LLMMissionAgent:consumption", [
        DataPoint(value=60.0, source="UN Comtrade", confidence=0.8,
                  note="حصة فرنسا من واردات الأردن لعام 2024 (٪ من القيمة)",
                  retrieved_at="2026-08-19")],
        False, "نتائج | فجوات: نصيب الفرد من الاستهلاك غير متاح")
    pop = DataPoint(value=10_000_000.0, source="World Bank", confidence=0.9,
                    note="SP.POP.TOTL", retrieved_at="2026-08-19")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1", SILK_GAP_MAX_WEB_SEARCH="0"), \
            patch("silk_data_layer.world_bank", return_value=pop):
        GR.recover({"consumption": r}, market_ref=_mref())
    assert not any("مستنتَج" in (f.note or "") for f in r.findings)
    assert "فجوات:" in r.summary                    # بقيت فجوة معلنة


def test_health_metric_counts_recoverable_only():
    """PAID/NONE لا تدخل مقام مؤشر الصحة — لا إنذار كاذب بخلل سجل البدائل."""
    fake = DataPoint(value=-0.4, source="World Bank", confidence=0.9,
                     note="PV.EST 2023", retrieved_at="2026-08-19")
    reports = _reports(
        a="ن | فجوات: الاستقرار السياسي غير متاح بسبب خطأ في واجهة البنك الدولي",
        b="ن | فجوات: بيان خلف اشتراك مدفوع",
        c="ن | فجوات: بيان غير مجموع في أي مصدر معروف")
    with _Env(SILK_GAP_RECOVERY_ENABLED="1", SILK_GAP_MAX_WEB_SEARCH="0"), \
            patch("silk_data_layer.world_bank", return_value=fake):
        out = GR.recover(reports, market_ref=_mref())
    assert out["health"] == "ok"    # القابل الوحيد للاسترجاع أُغلق
