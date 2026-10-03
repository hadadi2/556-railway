"""الدرس 289 — الدراسة ٩ (قهوة محمصة 090121 → ماليزيا) حُجبت عند التسليم.

الدليل (سجل Railway، 2026-10-03 09:04–09:16): الدراسة انطلقت بعد #57 ثم رفضتها بوابة
الجودة بـ`pillar_narrative_sync`، والسجل يحمل «يفوق إجمالي واردات البند المرصود لسنة
المرجع 2024 (90,121$) بمقدار 570×» — رمزُ البند 090121 قُرئ مبلغاً. الأقفال هنا:

* حارسُ المعقولية لا يقرأ رقماً من ملاحظة فجوة ولا رمزَ بند ولا نسبةً ولا سنةً مبلغاً،
  ومرتكزُ الواردات من سلسلة الواردات المُهيكلة (`import_series`) قبل النثر.
* بندُ «الحصة السعودية» في `pillar_narrative_sync` يحجب سرداً لقيمةٍ (رقم/صفر/ضئيل)
  لا توصيةً أو هدفاً بلا قيمة («بناء الحصة السعودية»).
* حجبُ التصدير يكتب ملاحظات البوابة في السجل — فيُقرأ المكوّن من سجل Railway بلا مفتاح.
* Trends: ردٌّ ناقص البنية (IndexError داخل pytrends) لا يُسجَّل عطلاً.
* أداتا التعرفة: الشريك = السوق نفسها يُستبدَل بالسعودية معلَناً.
هرمتي. Run: python3 -m pytest tests/test_study9_delivery_block.py -q
"""
import logging
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── المعقولية: لا رقم مختلَق من رمز بند أو ملاحظة فجوة ─────────────────────

def test_num_usd_reads_amounts_not_codes_years_gaps_or_percentages():
    from silk_plausibility import _num_usd
    assert _num_usd(None, "HS090121 استيراد Malaysia 2024: تعذّر الجلب") is None
    assert _num_usd("تعتمد ماليزيا على استيراد البن المحمص",
                    "[trade] مبني على: HS090121 إجمالي استيراد 2024") is None
    assert _num_usd({"year": 2024, "hhi": 1200}) is None
    assert _num_usd("واردات البند HS 090121 بلغت 61.5 مليون دولار") == 61_500_000.0
    assert _num_usd("البند 0901.21 بقيمة 7,000,000 دولار") == 7_000_000.0
    assert _num_usd("نمت الواردات 12% في 2024") is None
    assert _num_usd("حصة 0.4٪ من الواردات") is None
    assert _num_usd("2025-2030 حجم السوق 51.36 مليون") == 51_360_000.0
    assert _num_usd("في ٢٠٢٤ بلغ ٦١٫٥ مليون دولار") == 61_500_000.0
    # العقود القائمة (test_hf_attribution_truncation_plausibility) باقية.
    assert _num_usd("3 الفئات المدروسة") == 3.0
    assert _num_usd("497 مليون دولار") == 497_000_000.0
    assert _num_usd(74_870_000) == 74_870_000.0


def test_hs_code_in_a_gap_note_is_never_the_import_anchor():
    import silk_plausibility as P
    dr = {"missions": {"trade_flow": {"findings": [
        {"value": 61_500_000, "note": "HS090121 إجمالي استيراد Malaysia من العالم 2023, USD",
         "data_year": 2023, "source": "UN Comtrade", "confidence": 0.9},
        {"value": None, "note": "HS090121 استيراد Malaysia 2024: تعذّر الجلب",
         "status": "fetch_failed", "source": "UN Comtrade", "confidence": 0.0},
        {"value": "تعتمد ماليزيا اعتماداً متزايداً على استيراد البن المحمص",
         "note": "[trade] مبني على: HS090121 إجمالي استيراد Malaysia 2024"},
    ]}}}
    anchors = P._anchors(dr)
    assert anchors["imports_usd"] == 61_500_000 and anchors["imports_year"] == 2023, anchors


def test_live_claims_anchor_on_the_typed_import_series():
    """البعثة الحيّة: قيم الحقائق نصوص ادعاء والأرقام المُهيكلة في raw_evidence — المرتكزُ منها."""
    import silk_plausibility as P

    def raw(value, year):
        return {"value": value, "source": "UN Comtrade", "confidence": 0.9, "data_year": year,
                "note": f"HS090121 إجمالي استيراد Malaysia من العالم {year}, USD"}
    result = {"deep_research": {"missions": {
        "trade_flow": {"findings": [
            {"value": "نمت واردات ماليزيا 12% في 2024", "note": "[trade] مبني على: dp1, dp2",
             "raw_evidence": [raw(61_500_000.0, 2023), raw(74_870_000.0, 2024)]}]},
        "consumer_culture": {"findings": [
            {"value": "حجم السوق 51.36 مليون دولار", "note": "تقدير حجم السوق الكامل"}]},
    }}}
    anchors = P._anchors(result["deep_research"])
    assert anchors["imports_usd"] == 74_870_000.0 and anchors["imports_year"] == 2024, anchors
    assert P.check_magnitudes(result) == []          # 51.36م$ ≤ 20× واردات 74.87م$


def test_prose_import_anchor_keeps_the_existing_fallback_contract():
    """بلا سلسلة مُهيكلة يبقى النثر احتياطاً (عقد test_g41/test_hf قائم) — بمدى tam_usd."""
    import silk_plausibility as P
    dr = {"missions": {"m": {"findings": [
        {"value": "7,000,000 دولار", "source": "UN Comtrade", "note": "إجمالي استيراد QAT من العالم"},
        {"value": "23 دولة مورّدة", "source": "UN Comtrade", "note": "عدد مصادر الاستيراد"},
    ]}}}
    assert P._anchors(dr)["imports_usd"] == 7_000_000.0


# ── pillar_narrative_sync: الحصة السعودية ─────────────────────────────────

def _view(text):
    return {"deep_research": {"missions": {}, "report": {"text": text}},
            "markets": [{"decision": {"schema": "silk.decision/v1", "score": 0.5, "pillars": {
                "market": {"value": 0.5, "missing": ["saudi_momentum"]}}}}]}


def _sync(text):
    import silk_quality_gate as QG
    return [f for f in QG._check_pillar_narrative_sync(_view(text))]


def test_saudi_share_recommendation_is_not_a_narrated_measurement():
    assert _sync("نوصي ببناء الحصة السعودية تدريجياً عبر موزّع محلي.") == []
    assert _sync("تعزيز حصة السعودية في السوق يتطلب شريكاً محلياً.") == []
    assert _sync("| الحصة السعودية | — |") == []
    assert _sync("لا يوجد مورّد سعودي في هذه السوق حالياً.") == []


def test_saudi_share_value_while_unmeasured_still_blocks():
    assert _sync("الحصة السعودية صفر في هذه السوق.")
    assert _sync("تبلغ حصة السعودية 0% من الواردات.")
    assert _sync("تستحوذ السعودية على 3٪ من السوق.")
    assert _sync("الحصة السعودية ضئيلة جداً.")


# ── حجب التصدير يُقرأ من السجل ─────────────────────────────────────────────

def test_blocked_export_writes_the_gate_notes_to_the_log(caplog):
    import silk_export_gate as EG
    digest = [{"check": "pillar_narrative_sync",
               "note": "اللوحة تعلن «الحصة السعودية» غير مرصود بينما متن التقرير يسرده"}]
    with mock.patch("silk_watchdog.record_blocked_export"), \
            mock.patch("silk_ops_log.record_error"), \
            caplog.at_level(logging.WARNING, logger=EG.log.name):
        EG.record_block(9, "قهوة محمصة", "Malaysia", [], digest, "pdf", surface="platform",
                        fail_drivers=["pillar_narrative_sync"])
    text = caplog.text
    assert "pillar_narrative_sync" in text and "الحصة السعودية" in text and "analysis=9" in text


# ── Trends وأداتا التعرفة ─────────────────────────────────────────────────

def test_trends_short_related_reply_is_not_logged_as_a_failure(caplog):
    """pytrends 4.9.2 يفهرس rankedList[0]/[1] بلا حماية — ردٌّ قصير يرمي IndexError
    («list index out of range» في سجل الدراسة ٩): غيابٌ لا عطل. KeyError (تغيّر بنية) يبقى تحذيراً."""
    import silk_trends_agent as T
    with caplog.at_level(logging.INFO, logger=T.log.name):
        T._log_related_failure("related_topics", "قهوة محمصة", IndexError("list index out of range"))
        T._log_related_failure("related_queries", "قهوة محمصة", KeyError("token"))
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1 and "token" in warnings[0].getMessage()
    assert any(r.levelno == logging.INFO and "related_topics" in r.getMessage()
               for r in caplog.records)


def test_tariff_tools_never_query_a_market_against_itself():
    import silk_llm_runtime as RT
    from silk_data_layer import DataPoint
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market("Malaysia")
    seen = []

    def fake(hs, iso3, partner_iso3="SAU", year=None):
        seen.append(partner_iso3)
        return DataPoint(None, "World Bank WITS", 0.0, "لا سجل", "2026-10-03")
    with mock.patch("silk_tariffs_agent.tariff_with_fallback", side_effect=fake):
        out = RT._tool_wits_tariff({"partner_iso3": "mys"}, {"hs_code": "090121", "market": ref})
        RT._tool_wits_tariff({"partner_iso3": "ARE"}, {"hs_code": "090121", "market": ref})
    assert seen == ["SAU", "ARE"]
    assert "الشريك المطلوب" in out[0].note and "partner_iso3" not in out[0].note
    assert out[0].note.rstrip().endswith(".")
