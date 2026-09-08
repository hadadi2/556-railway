"""إحياء طبقة سد الفجوات (بلاغ الحليب–الأردن 2026-08-19) — ثلاثة عيوب:

  (A) إبرة تصنيف منسوخة يدوياً («خطأ في واجهة») لا تطابق نصّ المنتِج الحقيقي
      («البنك الدولي أعاد خطأ API: …») ⇒ NONE ⇒ تخطٍّ صامت رغم العلم مفعّلاً.
      القاعدة العامة (LESSONS 89): الإبر تُستورَد من وحدة المنتِج.
  (B) سطح الدخل: نثر «| فجوات:» وحده — `status="fetch_failed"` لم يصل المصنّف.
  (C) سجل بدائل وصفي: التعرفة (أولوية ١) بلا مسار حتمي رغم وجود سلسلة تراجع.

+ «خطأ 429» كان يصل نصَّ العميل. هرمتي بالكامل.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════ (A) الإبر من المنتِج لا نسخة متحجّرة ═══════

def test_real_world_bank_failure_text_classifies_as_fetch_not_none():
    import silk_gap_recovery as G
    from silk_data_layer import _wb_shape_error
    real = _wb_shape_error([{"message": [{"value": "Invalid value"}]}])
    assert real and "أعاد خطأ API" in real
    assert G.classify(real) == G.FETCH, (
        f"نصّ الفشل الإنتاجي {real!r} لا يُصنَّف — إبرة متحجّرة عادت")


def test_classifier_needles_are_imported_from_the_producer():
    import silk_gap_recovery as G
    from silk_data_layer import RETRIEVAL_FAILURE_NEEDLES
    assert set(RETRIEVAL_FAILURE_NEEDLES) <= set(G._PRODUCER_FAILURE_NEEDLES)
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_gap_recovery.py"),
        encoding="utf-8").read()
    assert "RETRIEVAL_FAILURE_NEEDLES" in src, "الإبر عادت نسخة يدوية"


def test_rate_needle_is_bounded_not_bare_containment():
    import silk_gap_recovery as G
    assert G.classify("استجابة 429 من المصدر") == G.RATE
    # لا مطابقة داخل رقم/عملة/سنة هجرية
    assert G.classify("حجم السوق $429M مستقر") != G.RATE
    assert G.classify("سنة 1429هـ") != G.RATE


def test_g3_class_also_sees_the_real_producer_text():
    from silk_data_layer import GAP_G3, classify_gap_class
    assert classify_gap_class("البنك الدولي أعاد خطأ API: Invalid") == GAP_G3


# ═══════ (B) السطح الخام يصل المصنّف ═══════

def test_raw_failed_findings_are_collected_from_both_shapes():
    import silk_gap_recovery as G
    from silk_data_layer import DataPoint
    dict_report = {"findings": [{"metric": "tariff", "value": None,
                                 "status": "fetch_failed", "note": "تعذّر"}]}
    assert G._raw_failed_findings(dict_report)[0]["status"] == "fetch_failed"
    dp = DataPoint(None, "World Bank", 0.0,
                   note="البنك الدولي أعاد خطأ API: x", status="fetch_failed")

    class _R:
        findings = [dp]
    got = G._raw_failed_findings(_R())
    assert got and "أعاد خطأ API" in got[0]["note"]
    # القيم الحاضرة ليست فجوات
    assert G._raw_failed_findings({"findings": [{"value": 5, "metric": "x"}]}) == []


def test_recover_sees_a_failure_the_summary_never_mentioned(monkeypatch):
    """العيب B: ملخّص نظيف تماماً + بند خام فاشل ⇒ الطبقة تحاول لا تتخطى."""
    import silk_gap_recovery as G
    from silk_data_layer import DataPoint
    monkeypatch.setenv("SILK_GAP_RECOVERY_ENABLED", "1")
    # الموجة C (§٦): الموسميةُ والموزّعون صارا **مطفأَين افتراضياً**
    # تحت الصمّام العامّ (يحتاجان دليلاً خارجياً موثَّقاً — أمرُ المالك
    # «لا تُفعِّلها عمياء»). هذه الاختباراتُ تُمرِّن مسارَيهما، فتفتح
    # صمّامَيهما صراحةً — نيّتُها محفوظةٌ والافتراضُ الجديد محترَم.
    monkeypatch.setenv("SILK_GAP_RECOVER_SEASONALITY", "1")
    monkeypatch.setenv("SILK_GAP_RECOVER_DISTRIBUTORS", "1")
    calls = {"n": 0}

    def _fake_wb(iso3, ind, year=None):
        calls["n"] += 1
        return DataPoint(0.42, "World Bank WGI", 0.8, note=f"{ind} سنة 2023")
    monkeypatch.setattr("silk_data_layer.world_bank", _fake_wb)

    report = {"summary": "بعثة المخاطر — تمّت.",   # لا مقطع «فجوات:» إطلاقاً
              "findings": [DataPoint(None, "World Bank", 0.0,
                                     note="الاستقرار السياسي — البنك الدولي "
                                          "أعاد خطأ API: Invalid value",
                                     status="fetch_failed")]}

    class _Ref:
        iso3 = "JOR"
        name_ar = "الأردن"
    log = G.recover({"risk": report}, market_ref=_Ref(), product="حليب",
                    hs_code="040120", year=2023)
    assert log.get("before", 0) >= 1, "البند الخام لم يُجمَع (العيب B قائم)"
    assert calls["n"] > 0, "لم يُحاوَل أي مسار استرجاع"
    assert log.get("closed", 0) >= 1


# ═══════ (C) مسارات بديلة حقيقية ═══════

def test_tariff_has_a_deterministic_fallback_route():
    import silk_gap_recovery as G
    assert "التعرفة" in G.FALLBACK_ROUTES
    assert "tariff_with_fallback" in G.FALLBACK_ROUTES["التعرفة"]
    assert callable(G._recover_tariff)


def test_tariff_gap_is_recovered_through_the_approved_chain(monkeypatch):
    import silk_gap_recovery as G
    from silk_data_layer import DataPoint
    monkeypatch.setenv("SILK_GAP_RECOVERY_ENABLED", "1")
    # الموجة C (§٦): الموسميةُ والموزّعون صارا **مطفأَين افتراضياً**
    # تحت الصمّام العامّ (يحتاجان دليلاً خارجياً موثَّقاً — أمرُ المالك
    # «لا تُفعِّلها عمياء»). هذه الاختباراتُ تُمرِّن مسارَيهما، فتفتح
    # صمّامَيهما صراحةً — نيّتُها محفوظةٌ والافتراضُ الجديد محترَم.
    monkeypatch.setenv("SILK_GAP_RECOVER_SEASONALITY", "1")
    monkeypatch.setenv("SILK_GAP_RECOVER_DISTRIBUTORS", "1")
    monkeypatch.setattr(
        "silk_tariffs_agent.tariff_with_fallback",
        lambda hs, mkt, partner="SAU", year=None: DataPoint(
            5.0, "WTO TTD", 0.9, note="تعرفة مطبَّقة 2023"))
    report = {"summary": "بعثة التكلفة — تمّت | فجوات: تعذّر جلب التعرفة",
              "findings": []}

    class _Ref:
        iso3 = "JOR"
        name_ar = "الأردن"
    log = G.recover({"cost": report}, market_ref=_Ref(), product="حليب",
                    hs_code="040120", year=2023)
    assert log.get("closed", 0) >= 1
    assert "م٤" in (log.get("by_route") or {})
    assert any(getattr(f, "value", None) == 5.0 for f in report["findings"])
    assert "تعذّر جلب التعرفة" not in report["summary"]


def test_layer_off_by_default_still_returns_a_clean_noop(monkeypatch):
    import silk_gap_recovery as G
    monkeypatch.delenv("SILK_GAP_RECOVERY_ENABLED", raising=False)
    assert G.recover({}, market_ref=None) == {"enabled": False}


# ═══════ تسرّب 429 إلى العميل ═══════

def test_http_status_codes_are_arabized_at_the_client_boundary():
    import silk_reports as REP
    out = REP._client_sanitize("تعذّر الجلب — خطأ 429 من المصدر")
    assert "429" not in out
    assert "تجاوز مؤقت لحدّ الاستعلامات" in out
    out2 = REP._client_sanitize("خطأ استجابة الخادم (HTTP 503): المصدر")
    assert "503" not in out2 and "HTTP" not in out2


def test_operator_surface_keeps_the_raw_status_code():
    from silk_narrative import humanize_technical_note
    txt = humanize_technical_note("HTTP 429 rate limited")
    assert "429" in txt, "المشغّل فقد رمز الحالة — تشخيصه يعتمد عليه"


def test_gap_recovery_stage_has_an_arabic_label():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "api.py"), encoding="utf-8").read()
    assert '"gap_recovery": "سدّ الفجوات"' in src


# ═══════ §6 — مسار الموزّعين (أغلى فجوة تجارياً) ═══════

def test_distributor_gap_gets_its_own_route_beyond_maps(monkeypatch):
    """بلاغ المالك: «قائمة الموزعين عادت إلى كيان واحد». الخرائط وحدها لا
    تكفي — §6 يفرض غرفة التجارة وأدلّة الشركات وصفحات «موزّعونا» لدى
    المنافسين (وهي غالباً تسرد الموزّع المحلي بالاسم)."""
    import silk_gap_recovery as G
    from silk_data_layer import DataPoint
    monkeypatch.setenv("SILK_GAP_RECOVERY_ENABLED", "1")
    # الموجة C (§٦): الموسميةُ والموزّعون صارا **مطفأَين افتراضياً**
    # تحت الصمّام العامّ (يحتاجان دليلاً خارجياً موثَّقاً — أمرُ المالك
    # «لا تُفعِّلها عمياء»). هذه الاختباراتُ تُمرِّن مسارَيهما، فتفتح
    # صمّامَيهما صراحةً — نيّتُها محفوظةٌ والافتراضُ الجديد محترَم.
    monkeypatch.setenv("SILK_GAP_RECOVER_SEASONALITY", "1")
    monkeypatch.setenv("SILK_GAP_RECOVER_DISTRIBUTORS", "1")
    seen = []

    def _fake_search(q, num=5, gl=None, hl=None):
        seen.append(q)
        return [DataPoint({"title": "Jordan Food Import Co",
                           "snippet": "distributor", "link": "https://x.jo"},
                          "بحث ويب", 0.5)]
    monkeypatch.setattr("silk_websearch_agent.web_search", _fake_search)
    report = {"summary": "بعثة القنوات — تمّت | فجوات: لم تُرصد جهات اتصال موزّعين",
              "findings": []}

    class _Ref:
        iso3, iso2 = "JOR", "JO"
        name_en, name_ar = "Jordan", "الأردن"
    log = G.recover({"channels": report}, market_ref=_Ref(), product="حليب",
                    hs_code="040120", year=2023)
    assert log.get("closed", 0) >= 1, "فجوة الموزّعين لم تُغلق"
    assert "م٤-موزعون" in (log.get("by_route") or {})
    joined = " | ".join(seen)
    assert "our distributors" in joined, "صفحات «موزّعونا» لم تُستعلَم"
    assert "chamber of commerce" in joined, "غرفة التجارة لم تُستعلَم"
    assert any("موزعو" in q or "دليل شركات" in q for q in seen), "لا استعلام عربي"
    # حالة التحقق معلَنة على كل مرشّح (الإدراج يثبت الوجود لا الاستيراد)
    notes = [getattr(f, "note", "") for f in report["findings"]]
    assert notes and all("لا نشاط الاستيراد" in n for n in notes)


def test_seasonality_rate_limit_is_retried_not_declared_a_gap(monkeypatch):
    """«موسمية رمضان» فشلت بحدّ معدل — وحدُّ المعدل ليس فجوة بيانات (§2).
    م١ كان محصوراً بعائلة الحوكمة فتمرّ الموسمية بلا أي محاولة."""
    import silk_gap_recovery as G
    from silk_data_layer import DataPoint
    monkeypatch.setenv("SILK_GAP_RECOVERY_ENABLED", "1")
    # الموجة C (§٦): الموسميةُ والموزّعون صارا **مطفأَين افتراضياً**
    # تحت الصمّام العامّ (يحتاجان دليلاً خارجياً موثَّقاً — أمرُ المالك
    # «لا تُفعِّلها عمياء»). هذه الاختباراتُ تُمرِّن مسارَيهما، فتفتح
    # صمّامَيهما صراحةً — نيّتُها محفوظةٌ والافتراضُ الجديد محترَم.
    monkeypatch.setenv("SILK_GAP_RECOVER_SEASONALITY", "1")
    monkeypatch.setenv("SILK_GAP_RECOVER_DISTRIBUTORS", "1")
    calls = {"n": 0}

    def _fake_trends(keyword, geo=None, timeframe="today 12-m"):
        calls["n"] += 1
        return DataPoint(72, "Google Trends", 0.7, note="ذروة رمضان")
    monkeypatch.setattr("silk_trends_agent.trends_interest_resilient",
                        _fake_trends)
    report = {"summary": "بعثة الموسمية — تمّت | فجوات: موسمية رمضان تعذّرت (429)",
              "findings": []}

    class _Ref:
        iso3, iso2 = "JOR", "JO"
        name_en, name_ar = "Jordan", "الأردن"
    log = G.recover({"seasonality": report}, market_ref=_Ref(), product="حليب",
                    hs_code="040120", year=2023)
    assert calls["n"] > 0, "لم تُعَد المحاولة إطلاقاً"
    assert "م١-اتجاهات" in (log.get("by_route") or {})
    assert any(getattr(f, "value", None) == 72 for f in report["findings"])


def test_every_gap_family_in_the_owners_report_has_a_route():
    """جردٌ صريح: كل عائلة فجوة ظهرت في تقرير الحليب–الأردن لها مسترجِع."""
    import silk_gap_recovery as G
    for fn in ("_recover_wgi", "_recover_tariff", "_recover_partner_shares",
               "_recover_per_capita", "_recover_seasonality",
               "_recover_distributors"):
        assert callable(getattr(G, fn, None)), f"{fn} مفقود"
    for route in ("World Bank/WGI", "UN Comtrade", "التعرفة", "الموزعون"):
        assert route in G.FALLBACK_ROUTES


def test_the_owners_eleven_gaps_close_down_to_the_paid_one(monkeypatch):
    """اختبار القبول الحاسم (§9 من الأمر): الفجوات الإحدى عشرة من تقرير
    الحليب–الأردن تُغلَق كلها عدا المدفوعة — بمزودات محاكاة، صفر كلفة.
    الهدف المُعلَن في الأمر ≤3؛ المُحقَّق 1."""
    from unittest.mock import patch
    import silk_gap_recovery as G
    from silk_data_layer import DataPoint
    monkeypatch.setenv("SILK_GAP_RECOVERY_ENABLED", "1")
    # الموجة C (§٦): الموسميةُ والموزّعون صارا **مطفأَين افتراضياً**
    # تحت الصمّام العامّ (يحتاجان دليلاً خارجياً موثَّقاً — أمرُ المالك
    # «لا تُفعِّلها عمياء»). هذه الاختباراتُ تُمرِّن مسارَيهما، فتفتح
    # صمّامَيهما صراحةً — نيّتُها محفوظةٌ والافتراضُ الجديد محترَم.
    monkeypatch.setenv("SILK_GAP_RECOVER_SEASONALITY", "1")
    monkeypatch.setenv("SILK_GAP_RECOVER_DISTRIBUTORS", "1")

    class _Ref:
        iso3, iso2, m49 = "JOR", "JO", 400
        name_en, name_ar = "Jordan", "الأردن"

    gaps = ["مؤشر الاستقرار السياسي غير متاح — البنك الدولي أعاد خطأ API",
            "سيادة القانون غير متاحة", "الجودة التنظيمية غير متاحة",
            "نصيب الفرد من الاستهلاك — تعذّر الجلب من FAOSTAT",
            "موسمية رمضان تعذّرت — حد المعدل (429)",
            "حصص الدول المصدّرة غير مرصودة", "الأوزان بالأطنان غير متاحة",
            "بيانات WTO TTD — مفتاح API غير مضبوط",
            "لم تُرصد جهات اتصال موزّعين كافية",
            "كلفة الشحن المبرّد غير مرصودة — الطبقة المدفوعة",
            "تعذّر جلب التعرفة الجمركية"]
    gap_rep = {"summary": "بعثة — تمّت | فجوات: " + "؛ ".join(gaps),
               "findings": []}
    # الإجمالي يعيش في بعثة أخرى — كما في تشغيلة حقيقية.
    size_rep = {"summary": "حجم السوق — تمّت", "findings": [
        DataPoint(8.47e6, "UN Comtrade", 0.9, note="إجمالي واردات السوق 2023")]}

    with patch("silk_data_layer.world_bank",
               lambda i, ind, year=None: DataPoint(
                   11e6 if "POP" in ind else 0.4, "WB", 0.8, note=f"{ind} 2023")), \
         patch("silk_trends_agent.trends_interest_resilient",
               lambda k, geo=None, timeframe="today 12-m": DataPoint(
                   72, "Trends", 0.7, note="ذروة رمضان")), \
         patch("silk_tariffs_agent.tariff_with_fallback",
               lambda *a, **k: DataPoint(5.0, "WTO TTD", 0.9, note="تعرفة")), \
         patch("silk_data_layer.comtrade_trade",
               lambda *a, **k: [{"partnerDesc": "Saudi Arabia",
                                 "primaryValue": 7.6e6, "netWgt": 9000}]), \
         patch("silk_websearch_agent.web_search",
               lambda q, num=5, gl=None, hl=None: [DataPoint(
                   {"title": "Jordan Food Co", "snippet": "d",
                    "link": "https://x.jo"}, "بحث", 0.5)]):
        log = G.recover({"m": gap_rep, "size": size_rep}, market_ref=_Ref(),
                        product="حليب", hs_code="040120", year=2023)

    assert log["before"] == 11
    assert log["after"] <= 3, f"هدف الأمر ≤3، المُحقَّق {log['after']}"
    assert log["closed"] >= 10
    # المدفوعة تبقى معلنة (عقد الطبقة — لا تُخفى ولا تُختلَق)
    residual = " ".join(str(r) for r in (log.get("residual") or []))
    assert "المدفوعة" in residual
    # العطل التشغيلي للمشغّل وحده، لا للعميل
    assert len(log.get("ops") or []) == 1
    assert "WTO" not in residual
    # كل المسارات الخمسة شاركت
    for route in ("م١-اتجاهات", "م٢", "م٣", "م٤", "م٤-موزعون"):
        assert route in (log.get("by_route") or {}), f"{route} لم يُستعمل"


def test_per_capita_derives_across_missions_not_just_its_own(monkeypatch):
    """الرقم يعيش في بعثة حجم السوق والفجوة تُعلَن في بعثة الاستهلاك —
    البحث داخل بعثة الفجوة وحدها كان يُفشِل الاشتقاق دائماً."""
    from unittest.mock import patch
    import silk_gap_recovery as G
    from silk_data_layer import DataPoint
    monkeypatch.setenv("SILK_GAP_RECOVERY_ENABLED", "1")
    # الموجة C (§٦): الموسميةُ والموزّعون صارا **مطفأَين افتراضياً**
    # تحت الصمّام العامّ (يحتاجان دليلاً خارجياً موثَّقاً — أمرُ المالك
    # «لا تُفعِّلها عمياء»). هذه الاختباراتُ تُمرِّن مسارَيهما، فتفتح
    # صمّامَيهما صراحةً — نيّتُها محفوظةٌ والافتراضُ الجديد محترَم.
    monkeypatch.setenv("SILK_GAP_RECOVER_SEASONALITY", "1")
    monkeypatch.setenv("SILK_GAP_RECOVER_DISTRIBUTORS", "1")

    class _Ref:
        iso3, iso2, m49 = "JOR", "JO", 400
        name_en, name_ar = "Jordan", "الأردن"
    consumption = {"summary": "الاستهلاك — تمّت | فجوات: نصيب الفرد غير متاح",
                   "findings": []}
    size = {"summary": "حجم السوق — تمّت", "findings": [
        DataPoint(8.47e6, "UN Comtrade", 0.9, note="إجمالي واردات السوق 2023")]}
    with patch("silk_data_layer.world_bank",
               lambda i, ind, year=None: DataPoint(11e6, "WB", 0.9, note="سكان")):
        log = G.recover({"c": consumption, "size": size}, market_ref=_Ref(),
                        product="حليب", hs_code="040120", year=2023)
    assert log.get("closed", 0) == 1
    derived = [f for f in consumption["findings"]
               if "مستنتَج" in (getattr(f, "note", "") or "")]
    assert derived, "لم يُشتق نصيب الفرد رغم توفر طرفَي المعادلة"
    assert "÷" in derived[0].note or "الواردات" in derived[0].note
