"""أقفال عيوب الدراسة الحية #13 (أول PDF منزَّل بعد نشر #246).

ثمانية عيوب من قراءة الـPDF التسع عشرة صفحة — أخطرها انحداران لصنفين
سبق إغلاقهما: توصية «حليب الأطفال» (بند 1901) لم يلتقطها فحص البند 4
لأن قائمته كانت مجمّدة (#11 ثم #13 من نفس الصنف)، وازدواجان حرفيان
(«تحتاج تحققا تحتاج تحققا»، «لا يتوفر س لا يتوفر سعر») تحت عتبات
الفحوص الثلاثة. كل fixture هنا نص #13 الحرفي. هرمتي. Run:
  python3 -m pytest tests/test_study13_live_defects.py -q
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import silk_quality_gate as QG                           # noqa: E402


# ── البند 7: توصية خارج بند التجارة — المرجع لا القائمة المجمدة ──────────

_RECS = ("## 10. التوصيات الاستراتيجية\n"
         "يوصى باستهداف فئات الحليب المتخصص كحليب البروتين وحليب "
         "الأطفال، بدل منافسة الحليب السائل العام المهيمن.\n")


def _milk_view(text):
    return {"hs_code": "040120", "product": "حليب",
            "deep_research": {"report": {"text": text}}}


def test_infant_formula_recommendation_trips_hs_match():
    """نص #13 الحرفي: «حليب الأطفال» بند 1901 والدراسة 0401 — الفحص كان
    أعمى (قائمة 0402 مجمدة) فشُحن الانحدار الثاني من صنف #11."""
    out = QG._check_hs_recommendation_match(_milk_view(_RECS))
    assert out and "1901" in out[0]["note"]


def test_definition_window_mention_does_not_trip():
    t = _RECS.replace("## 10. التوصيات الاستراتيجية",
                      "## 2. منهجية البحث ونطاقه")
    assert QG._check_hs_recommendation_match(_milk_view(t)) == []


def test_same_heading_study_is_not_flagged():
    view = {"hs_code": "190110", "product": "حليب الأطفال",
            "deep_research": {"report": {"text": _RECS}}}
    assert QG._check_hs_recommendation_match(view) == []


def test_attr_phrases_lives_in_the_reference_not_the_gate():
    """الجدول صار صفوف بيانات في المرجع الواحد — كل عائلة جديدة تضيف
    عباراتها هناك، والبوابة تستهلكه (الاسم المحلي مرساة الدرس 124)."""
    import silk_hs_reference as HR
    assert QG._HS_ATTR_HEADINGS is HR.ATTR_PHRASES
    assert HR.ATTR_PHRASES["حليب الأطفال"][0] == "1901"
    assert HR.definition("190110")           # صف 1901 من التسميات الرسمية


def test_unclassified_attribute_is_declared_not_silent():
    """جواب سؤال المُشرِف المسجل: سمة خارج الجدول لا تمر صامتة — ملاحظة
    منهجية واحدة تسمّيها («بروتين» غير محسومة التصنيف فلا تُجدوَل)."""
    out = QG._check_unclassified_product_attribute(_milk_view(_RECS))
    assert out and "بروتين" in out[0]["note"]
    assert out[0]["check"] == "unclassified_product_attribute"


def test_unclassified_detector_negatives():
    """صفة من تعريف البند («السائل») وصفات العموم («العام»/«المتخصص»)
    والكلمات العارية بعد الأساس (أفعال/جار ومجرور — دورة C4) لا تُعلَن؛
    والكاشف لا يقود FAIL (تحذير مشغّل يُحسم لا حجب ولا ملاحظة عميل)."""
    t = ("## 10. التوصيات الاستراتيجية\n"
         "ركّز على الحليب السائل ضمن السوق العام بخطة الحليب المتخصص. "
         "نمت واردات الحليب بنسبة كبيرة والحليب يشهد إقبالاً عبر الحدود.\n")
    assert QG._check_unclassified_product_attribute(_milk_view(t)) == []
    assert "unclassified_product_attribute" not in QG._REGRESSION_GUARD_FIRED
    assert "unclassified_product_attribute" not in QG.FAIL_TRIGGER_CHECKS


def test_unclassified_detector_c4_refinements():
    """دورة C4: (أ) «حليب اللوز» كانت تسقط في substring («وز» داخل «وزنا»)
    — تُعلَن الآن؛ (ب) العرض بالنص الخام لا المطبَّع؛ (ج) الملاحظة قابلة
    للإصلاح (تحذير مشغّل — لا تُطبع ملاحظةً منهجية للعميل)."""
    t = ("## 10. التوصيات الاستراتيجية\n"
         "فرصة واعدة في حليب اللوز لدى شريحة الأغذية الصحية.\n")
    out = QG._check_unclassified_product_attribute(_milk_view(t))
    assert out and "اللوز" in out[0]["note"]
    assert out[0]["repairable"] is True


# ── البند 8: الازدواج القصير الملاصق ─────────────────────────────────────

_P3 = ("الحكم المعتمد لهذه الدراسة هو الدخول المشروط بثقة عالية بلغت "
       "80%، مقابل خمس بنود تحتاج تحققا تحتاج تحققا إضافيا قبل الالتزام "
       "الكامل.")
_P8 = ("لذا تعلن فجوة مقارنة تنافسية صريحة: لا يتوفر س لا يتوفر سعر "
       "تجزئة مرصود لحليب سائل غير مركز.")


def test_study13_stutters_trip_the_new_check():
    for t in (_P3, _P8):
        out = QG._check_adjacent_short_stutter(t)
        assert out and out[0]["check"] == "adjacent_short_stutter", t[:40]


def test_short_stutter_drives_fail():
    """نفس عائلة repeated_span/table_row_stutter — عضو مجموعة الإفشال."""
    assert "adjacent_short_stutter" in QG._REGRESSION_GUARD_FIRED


def test_short_stutter_negatives():
    for t in ("نما الطلب جدا جدا في السنوات الأخيرة.",
              "بلغ الطلب في الأردن. في الأردن يتركز الاستهلاك في عمان.",
              "تحرك من 1.77 مليون دولار في 2019 إلى 7.74 مليون دولار "
              "في 2020 ثم إلى 14.38 مليون دولار في 2021.",
              "حصة المورد وحصة الموردين مجتمعتين تتجاوزان النصف."):
        assert QG._check_adjacent_short_stutter(t) == [], t[:40]


def test_joiner_repairs_the_truncated_short_tail():
    """بصمة ص8 عند دمج إكمال حقيقي: «لا يتوفر س» + «لا يتوفر سعر …» —
    كانت تحت عتبة الـ24 حرفاً فتصل ملتحمة مزدوجة."""
    import silk_ai_judge as AJ
    base = "لذا تعلن فجوة مقارنة تنافسية صريحة: لا يتوفر س"
    cont = "لا يتوفر سعر تجزئة مرصود لحليب سائل غير مركز."
    b, c = AJ._trim_join_stutter(base, cont)
    joined = f"{b} {c}"
    assert "لا يتوفر س لا يتوفر" not in joined
    assert "لا يتوفر سعر تجزئة" in joined


def test_joiner_negative_directions():
    """تصحيح المُشرِف: البتر الكاذب أسوأ من الازدواج — جملة جديدة مشروعة
    بعد نقطة لا تُقص، وامتداد كلمة واحدة لا يُقص."""
    import silk_ai_judge as AJ
    base = "ونمو الطلب واضح في الأردن."
    cont = "في الأردن يتجه المستهلكون للحليب المبرد."
    assert AJ._trim_join_stutter(base, cont) == (base, cont)
    base2, cont2 = "قرر المستورد", "المستوردون الآخرون ينتظرون."
    assert AJ._trim_join_stutter(base2, cont2) == (base2, cont2)


def test_joiner_does_not_cut_gender_morphology_echo():
    """دورة C4 (direct reproduction): «المحلي»→«المحلية» صرفُ جنسٍ يحقق
    البصمة بكلمة تامة — الذيل المُسقَط يُشترط شظيةً (≤3 أحرف) فلا يُقص
    نصٌّ مشروع وحدُّ جملته."""
    import silk_ai_judge as AJ
    base = "وترتفع الأسعار في السوق المحلي"
    cont = "في السوق المحلية الأسعار أعلى بنسبة 20%."
    assert AJ._trim_join_stutter(base, cont) == (base, cont)


# ── البند 1: سقالة الاستشهاد لا تبلغ رف أسعار العميل ─────────────────────

def test_price_row_note_cleaner_study13_cases():
    from silk_render import _clean_price_row_note as clean
    assert clean("[مرجع سوق] مبني على: مرجع locale") == ""
    assert clean("[قنوات توزيع] مبني على: مرجع locale") == ""
    out = clean("[حجم السوق] مبني على: HS040120 إجمالي استيراد الأردن "
                "من العالم 2024, USD")
    assert out == "البند 040120 إجمالي استيراد الأردن من العالم 2024 بالدولار"
    retail = "المراعي 350غم بسعر 2.25 دينار في Talabat Mart، رصد 2024"
    assert clean(retail) == retail            # الرصد الحقيقي لا يُمَسّ


def test_client_guard_rejects_the_scaffold_needles():
    import silk_reports as SR
    hits = SR._client_forbidden_hits(
        "التموضع يتطلب بطاقة المنتج و[حجم السوق] مبني على: كذا مع "
        "مرجع locale")
    labels = {h.split(":")[0] for h in hits}
    assert {"product_card", "citation_scaffold", "locale_ref"} <= labels
    assert SR._client_forbidden_hits("القرار مبني على أرقام مرصودة.") == []


# ── البند 2: لغة الزائر لا لغة المدخلات على أسطح المحرك ──────────────────

def test_render_surfaces_ask_for_the_input_not_the_card():
    import silk_render as R
    import silk_i18n
    assert "بطاقة" not in R.PRICE_UNLOCK_LINE
    assert "سعر المصنع" in R.PRICE_UNLOCK_LINE
    for key in ("price_unlock", "gap_how_price_competitiveness"):
        for lang in ("ar", "en"):
            v = silk_i18n.t(key, lang)
            assert "بطاقة" not in v and "product card" not in v, (key, lang)


def test_economics_gap_line_is_visitor_language():
    src = open(os.path.join(_ROOT, "silk_economics.py"), encoding="utf-8").read()
    assert "بطاقة المنتج ليكتمل الشلال" not in src
    assert "أدخل سعر المصنع " in src


# ── البند 3: قسم التغطية يسمّي ما يعدّه ──────────────────────────────────

def test_coverage_labels_name_verification_tiers():
    import silk_i18n
    assert silk_i18n.t("coverage_col_kind", "ar") == "رتبة التحقق"
    assert "رسمي أوّلي" not in silk_i18n.t("coverage_primary", "ar")
    assert "متحقق" in silk_i18n.t(
        "coverage_primary", "ar").replace("ُ", "").replace("َ", "").replace("ّ", "")
    # رتبة ○ منقسمة: قيمة حاضرة لم يكتمل تحققها ≠ فجوة معلنة بلا قيمة
    assert "لم يكتمل التحقق" in silk_i18n.t("coverage_unverified", "ar")
    assert "بلا قيمة" in silk_i18n.t("coverage_gap", "ar")


def test_named_source_coverage_line_present_in_section():
    """سطر الإسناد المسمّى الحقيقي (compute_source_coverage) يظهر في القسم
    — غيابه جعل «2 رسمي أولي» يُقرأ انهيار إسناد بجوار ثقة 80%."""
    import pytest
    docx = pytest.importorskip("docx")
    import silk_reports as SR
    doc = docx.Document()
    dr = {"missions": {"m": {"findings": [
        {"value": 18.6, "confidence": 0.9, "source": "UN Comtrade",
         "retrieval_method": "official_api"},
        {"value": None, "confidence": 0.0, "source": "UN Comtrade"},
    ]}}}
    SR._client_confidence_section(doc, dr, "ar")
    text = "\n".join(p.text for p in doc.paragraphs)
    cells = [c.text for t in doc.tables for r in t.rows for c in r.cells]
    assert "وعلى مستوى الإسناد" in text
    assert "فجوة معلنة بلا قيمة" in cells
    assert "مصدر رسمي أوّلي" not in text + " ".join(cells)


# ── البند 4: ذيل «لا تمنع القرار» يقال مرة واحدة ─────────────────────────

def test_nonblocking_tail_said_once_not_per_bullet():
    import pytest
    docx = pytest.importorskip("docx")
    import silk_reports as SR
    doc = docx.Document()
    dr = {"missions": {
        "pricing_scout": {"summary": "ملخص | فجوات: لا بيانات أسعار جملة؛ "
                                     "لا أسعار موسمية؛ لا سلة مقارنة"},
    }}
    SR._client_gaps_section(doc, dr, "ar")
    text = "\n".join(p.text for p in doc.paragraphs)
    assert text.count("لا تمنع القرار") == 1
    assert "فجوة بيانات معلنة —" not in text


# ── البند 5: قيمة لغة التقرير مقروءة لا رمزاً ────────────────────────────

def test_report_language_metadata_value_is_humanized():
    import pytest
    docx = pytest.importorskip("docx")
    import silk_reports as SR
    doc = docx.Document()
    SR._stamp_report_metadata(doc, {"report_meta": {"study_id": 13}}, "ar")
    cells = [c.text for t in doc.tables for r in t.rows for c in r.cells]
    assert "العربية" in cells
    assert "ar" not in cells                     # الرمز الخام لا يُعرَض
    assert any("silk.report" in c for c in cells)   # عقد التتبع باقٍ


# ── البند 6: نافذة النمو إلى أحدث سنة مرصودة + الفحص المرافق ─────────────

def test_growth_window_backfills_freshest_observed_year(monkeypatch):
    """القاعدة الدائمة: TAM 2024 مرصود حيّاً والمخزن بارد له — النافذة
    كانت تقف عند 2023 (نص #13: CAGR ‏2019–2023 وTAM ‏2024 معاً)."""
    import silk_research as SRCH
    import silk_store

    def fake_store(hs, iso3, y):
        data = {2020: 7.74e6, 2021: 14.38e6, 2022: 9.33e6, 2023: 6.95e6}
        if y in data:
            return {"total_usd": data[y]}
        raise KeyError(y)
    monkeypatch.setattr(silk_store, "market_imports_from_store", fake_store)
    pairs = SRCH._growth_window_pairs("040120", "JOR", 2024, 18.62e6)
    assert pairs[-1] == (2024, 18.62e6)
    # وبلا TAM مرصود تبقى السنة فجوة معلنة — لا اختلاق
    pairs2 = SRCH._growth_window_pairs("040120", "JOR", 2024, None)
    assert pairs2[-1] == (2024, None)


def test_cagr_endpoint_lag_check_fires_and_stays_silent():
    dr = {"missions": {"market_size": {"findings": [
        {"note": "TAM = إجمالي واردات السوق المرصودة HS040120 سنة 2024",
         "value": 18.6e6, "confidence": 0.9},
        {"note": "CAGR عبر السنوات المرصودة 2019–2023", "value": 41.2,
         "confidence": 0.9}]}}}
    out = QG._check_cagr_endpoint_lag(dr)
    assert out and out[0]["check"] == "cagr_endpoint_lag"
    assert "cagr_endpoint_lag" not in QG._REGRESSION_GUARD_FIRED
    dr["missions"]["market_size"]["findings"][1]["note"] = \
        "CAGR عبر السنوات المرصودة 2019–2024"
    assert QG._check_cagr_endpoint_lag(dr) == []
