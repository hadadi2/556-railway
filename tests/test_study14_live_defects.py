"""أقفال عيوب الدراسة الحية الرابعة #14 (حليب×الأردن، بعد نشر #247).

النص قفزة جودة (108 مؤشراً متسقاً، CAGR مُصالَح، أرقام قرار كاملة) لكن
التنزيل حُجب 409 بلا أسماء فحوص. إعادة الإنتاج المباشرة أثبتت القائد:
`language_consistency` على جملة أسماء الموزعين — محلل الكلمات اللاتينية
كان يشطر «Alyoum.jo» عند النقطة فتُسقط «jo» الصغيرة استثناء الأعلام.
حكم المُشرِف B مُثبَت هنا تجريبياً: **المحلل هو الجذر لا العتبة**.
كل fixture نص #14 الحرفي. هرمتي. Run:
  python3 -m pytest tests/test_study14_live_defects.py -q
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import silk_deep_pillars as DP                           # noqa: E402
import silk_export_gate as EG                            # noqa: E402
import silk_i18n                                         # noqa: E402
import silk_quality_gate as QG                           # noqa: E402
import silk_render as SR                                 # noqa: E402


# ── البند 1 + B: النطاق رمز واحد في كاشف المقاطع الأجنبية ────────────────

# الجملة الحرفية التي قادت حجب #14 (قائمة موزعين يفرضها الموجّه نفسه:
# «مرشّحين بالاسم») — «Alyoum.jo» كانت تُشطَر إلى «Alyoum» + «jo».
_DISTRIBUTORS = (
    "توجد أيضاً منصات تجارة إلكترونية أقل توثيقاً مثل HyperMax وYanboot "
    "وAlyoum.jo، وموزّعون محليون غير مؤكدين مثل Kaylani Food Center "
    "العامل منذ 1991، وAlyoum Food، وMaryland Global.")


def test_study14_distributor_sentence_is_not_foreign_prose():
    """direct reproduction قبل الفكس: المقطع يُقرأ نثراً إنجليزياً فيقود
    409. بعد ضم الرموز المنقوطة: صفر مقاطع، والفحص الحاجز صامت."""
    assert silk_i18n.foreign_prose_spans(_DISTRIBUTORS, "ar") == []
    assert QG._check_language_consistency(_DISTRIBUTORS, "ar") == []


def test_capitalized_name_list_without_domain_is_clean():
    """حكم B: fixtures الصنف الأوسع — 12+ اسماً لاتينياً بلا نطاق نظيفة
    أصلاً، فالعتبة (11 كلمة) لم تكن الجذر؛ المحلل المنقوط هو الجذر."""
    names = ("الموزعون المرشحون هم HyperMax وYanboot وSafeway وCarrefour "
             "وCozmo وTalabat Mart وKaylani Food Center وAlyoum Food "
             "وMaryland Global وMSC de Jordan وMarks Spencer وNestle Trade.")
    assert silk_i18n.foreign_prose_spans(names, "ar") == []


def test_real_english_prose_with_domain_still_fires():
    """الاتجاه السالب: نثر إنجليزي حقيقي (كلمات صغيرة تفصلها مسافات)
    يتخلله نطاق يبقى مقطعاً أجنبياً — الفكس لا يفتح ثغرة تسريب لغة."""
    prose = ("please visit our site Alyoum.jo for more details about the "
             "current wholesale offers available in the Amman market today")
    assert silk_i18n.foreign_prose_spans(prose, "ar")


def test_title_heavy_english_prose_still_fires():
    """C4 (الملاحظة 4): جملة إنجليزية حقيقية يغلب عليها الترميز الكبير
    (سلاسل أسماء) لكن فيها فعل/وصل صغيران — نثرٌ يُلتقط: المعيار «كلمتان
    صغيرتان خارج أدوات الأعلام» لا نسبة تُهزم بكثافة الأسماء."""
    for prose in ("The Jordan Food and Drug Administration regulates "
                  "Milk Powder imports",
                  "Saudi Exports Program supports Dairy Products entering "
                  "the Jordanian Market"):
        assert silk_i18n.foreign_prose_spans(prose, "ar"), prose


def test_single_name_particle_is_not_prose_evidence():
    """«MSC de Jordan» وحدها (قائمة فحص B نفسها): أداة الاسم «de» صنف نحوي
    مغلق لا دليل نثر — لا مقطع."""
    assert silk_i18n.foreign_prose_spans("المرشح MSC de Jordan موثّق.",
                                         "ar") == []


def test_dotted_token_is_one_word():
    """الرمز المنقوط الملتصق كلمة واحدة تبدأ بحرف كبير — يصمد استثناء
    الأعلام البنيوي؛ النقطة المتبوعة بمسافة تبقى حدّ جملة لا وصلة."""
    spans_a = silk_i18n.foreign_prose_spans("المصدر Alyoum.jo موثّق.", "ar")
    assert spans_a == []


# ── البند 2 + C: مُرقِّع البادئة المبتورة («سوي سويسرا») ─────────────────

def test_truncated_prefix_stutter_is_repaired_with_audit_log():
    """الخلية الحرفية من جدول أسعار #14 تُطوى، وكل رقعة تحمل سجل تدقيق
    (قبل/بعد/الموضع) — شرط المُشرِف C: لا تعديل صامتاً على نص مُسلَّم."""
    cell = "نيدو بودرة بالألياف | سوي سويسرا (نستله) | 750 غرام"
    fixed, repairs = SR._fix_truncated_prefix_stutter(cell)
    assert "سوي سويسرا" not in fixed and "سويسرا (نستله)" in fixed
    assert len(repairs) == 1
    assert repairs[0]["before"] == "سوي سويسرا"
    assert repairs[0]["after"] == "سويسرا"
    assert isinstance(repairs[0]["offset"], int) and repairs[0]["offset"] > 0


def test_prefix_stutter_negatives_are_untouched():
    """حدود الرقعة المعلنة: بادئة قصيرة («في فيينا»)، قائمة الإيقاف
    («سوف»/«عبد»)، وحد السطر (طيّه يحذف \\n فيدمج خليتين) — كلها تمرّ
    حتى داخل صفوف الجداول."""
    for s in ("| التقى الوفد في فيينا بالمنظمة. |",
              "| سوف سوفت الشركة أعمالها. |",
              "| التقى عبد عبدالله في عمّان. |",
              "| انتهى الصف بسوي |\n| سويسرا بدأت الخلية التالية. |"):
        fixed, repairs = SR._fix_truncated_prefix_stutter(s)
        assert fixed == s and repairs == []


def test_prefix_stutter_leaves_free_prose_alone():
    """C4 (الملاحظة 3): تراكيب عربية مشروعة تطابق التوقيع في النثر الحر
    («أما أمام»، «كان كانون») — النطاق صفوف الجداول حصراً، والنثر الحر
    منطقة عمى معلنة (بتر كاذب أسوأ من ازدواج مرئي)."""
    for s in ("أما أمام المنافسة الحادة فإن المنتج السعودي يتقدم.",
              "كان كانون الأول شهر الذروة في المبيعات.",
              "ورد اسم سوي سويسرا في نثر حر خارج أي جدول."):
        fixed, repairs = SR._fix_truncated_prefix_stutter(s)
        assert fixed == s and repairs == [], s
    # وقائمة الإيقاف تحمي التركيبين حتى داخل خلية جدول.
    for s in ("| أما أمام المنافسة الحادة | قيمة |",
              "| كان كانون الأول شهر الذروة | قيمة |"):
        fixed, repairs = SR._fix_truncated_prefix_stutter(s)
        assert fixed == s and repairs == [], s


def test_render_repairs_channel_exists_in_view_builder():
    """قناة التدقيق `render_repairs` معقودة في باني العرض نفسه — الرقعة
    بلا قناة ظهور رقعة صامتة (مرساة نصية على المصدر لا تشغيلة كاملة)."""
    src = open(os.path.join(_ROOT, "silk_render.py"), encoding="utf-8").read()
    assert '"render_repairs": _prefix_repairs' in src
    assert "_fix_truncated_prefix_stutter(_report_text_glossed)" in src


# ── البند 3: الشدّة داخل مؤهل كاشف السمة («المدعّم» لا «المدع») ──────────

def test_attribute_qualifier_keeps_diacritics():
    """الجملة الحرفية من #14: «الحليب المدعّم بالبروتين» — التشكيل داخل
    الكلمة لا يقطع الالتقاط فتُعرض السمة كاملة لا مبتورة («المدع»)."""
    view = {"hs_code": "040120", "product": "حليب",
            "deep_research": {"report": {"text": (
                "## 10. التوصيات الاستراتيجية\n"
                "توجيه الشحنة نحو فئة الحليب المدعّم بالبروتين.\n")}}}
    out = QG._check_unclassified_product_attribute(view)
    assert out and "المدعّم" in out[0]["note"]
    assert "المدع " not in out[0]["note"] + " "


# ── البند 4: وسم «الأحدث المتاح» على نقاط سلسلة تاريخية ──────────────────

# سرد سلسلة #14 الحرفي (مختصراً بجُمله الثلاث): 2019/2020 وُسمتا «الأحدث
# المتاح» بينما 2023 في الجملة المجاورة من الفقرة نفسها — دلالة مقلوبة.
_SERIES = ("بلغت واردات الأردن ذروتها عند 14.38 مليون دولار في 2021، "
           "ثم 6.95 مليون دولار في 2023. تحوّل المسار من صعود بدأ من "
           "1.77 مليون دولار في 2019. ومرّ بـ7.74 مليون دولار في 2020.")


def test_series_years_are_not_tagged_when_paragraph_reaches_fresh_year():
    """نطاق الفقرة (فكس هذه الموجة): سنة سلسلة قديمة في جملة، والسنة
    الحديثة في جملة مجاورة من الفقرة نفسها — الوسم يُكبح."""
    for yr in (2019, 2020):
        start = _SERIES.find(str(yr))
        assert start > 0
        assert SR._year_in_growth_span(_SERIES, start, start + 4, yr)


def test_yemen_two_old_facts_still_both_tagged():
    """شرط اليمن باقٍ: فقرة حقيقتين قديمتين بلا سنة حديثة — لا كبح،
    كلتاهما تستحق الوسم (السنة الكابحة يجب أن تكون حديثة هي نفسها)."""
    s = "استقر المؤشر عند 2.1 (2013) ثم 31.5% (2018) في آخر رصد."
    start = s.find("2013")
    assert not SR._year_in_growth_span(s, start, start + 4, 2013)


def test_lpi_standalone_old_fact_in_other_paragraph_still_tagged():
    """حقيقة قديمة مستقلة في فقرتها (LPI 2018 — سطر #14 الحرفي): السلسلة
    الحديثة في فقرة أخرى لا تكبحها — حدود \\n تفصل الفقرتين."""
    s = ("بلغت الواردات 6.95 مليون دولار في 2023.\n"
         "مؤشر أداء لوجستي بلغ 2.69 لعام 2018 وفق البنك الدولي.")
    start = s.rfind("2018")
    assert not SR._year_in_growth_span(s, start, start + 4, 2018)


# ── E1: نسبة مقامُها من عالمٍ مختلف عن بسطها (نصيب الفرد من الواردات) ────

def test_cross_universe_ratio_fires_on_study14_line():
    """السطر الحرفي من جدول #14 — نصيب فرد مشتق من الواردات يُعلَن
    تحذيرياً (الموجّه يحظره الآن نصاً؛ هذا حارس انحدار القاعدة)."""
    line = ("| نصيب الفرد التقديري من الواردات الرسمية "
            "| نحو 0.60 دولار سنوياً (مشتق) |")
    out = QG._check_cross_universe_ratio(line)
    assert out and out[0]["check"] == "cross_universe_ratio"
    assert out[0]["repairable"] is True


def test_cross_universe_ratio_is_warn_tier_and_silent_on_gdp():
    """قرار المُشرِف D احترازاً: الفحص الجديد تحذيري لا حاجب (خارج مجموعتي
    الإفشال)، ونصيب الفرد من الناتج (البنك الدولي) في سطرٍ والواردات في
    آخر لا يطلقانه."""
    assert "cross_universe_ratio" not in QG._REGRESSION_GUARD_FIRED
    assert "cross_universe_ratio" not in QG.FAIL_TRIGGER_CHECKS
    quiet = ("نصيب الفرد من الناتج المحلي 4,850 دولاراً (البنك الدولي).\n"
             "بلغت الواردات الرسمية 6.95 مليون دولار في 2023.")
    assert QG._check_cross_universe_ratio(quiet) == []


# ── E2: مكوّن saudi_position من ملخّص المنافسين المُهيكل ─────────────────

_COMP_FINDING = {
    "value": {"hhi": 7118, "year": 2023,
              "top_suppliers": [{"partner": "Saudi Arabia", "share": 84.05},
                                {"partner": "UAE", "share": 6.2}]},
    "source": "UN Comtrade", "data_year": 2023, "confidence": 0.9,
    "note": "ملخص مُهيكل للموردين",
}


def test_saudi_position_falls_back_to_competitors_summary():
    """انحدار «—، 0%» ثلاث دراسات: بعثة trade_flow لا تنتج saudi_share_pct
    رقمية أصلاً؛ الاحتياط يقرأ الحصة من الملخّص المُهيكل الفائز لبعثة
    المنافسين بنفس عقد الإسناد (المصدر/السنة/الثقة من النتيجة نفسها)."""
    dr = {"missions": {
        "trade_flow": {"findings": [
            {"value": "نثر بلا رقم حصة", "source": "بحث ويب", "note": "-"}]},
        "competitors": {"findings": [_COMP_FINDING]},
        "demographics_economy": {"findings": []},
    }}
    sp = DP.build_components(dr)["saudi_position"]
    assert sp["value"] == 84.05
    assert sp["source"] == "UN Comtrade" and sp["data_year"] == 2023
    assert sp["confidence"] == 0.9


def test_saudi_share_absent_row_stays_declared_none():
    """لا صف سعودياً في الملخّص = (None, None) — فجوة معلنة لا صفر مختلَق
    (عقد عدم الاختلاق)."""
    share, f = DP._saudi_share_from_competitors([{
        "value": {"hhi": 3000,
                  "top_suppliers": [{"partner": "UAE", "share": 40}]},
        "source": "UN Comtrade", "note": ""}])
    assert share is None and f is None


# ── E3: المباشرية قبل اكتمال الحصة + المباشر الرقمي مرشح لا احتياطاً ─────

_MIRROR_STRUCTURED = {
    "value": {"hhi": 4185, "year": 2025,
              "top_suppliers": [{"partner": "Saudi Arabia", "share": 61.45}]},
    "source": "UN Comtrade (مرآة الشركاء)", "data_year": 2025,
    "confidence": 0.6, "note": "بيانات مرآة",
}
_NUMERIC_DIRECT = {
    "value": 7118, "source": "UN Comtrade", "data_year": 2023,
    "confidence": 0.9, "note": "تركّز الموردين HHI محسوب من بيانات مباشرة",
}


def test_direct_numeric_hhi_beats_structured_mirror():
    """عيب #14 (نفس صنف D5 في #12): جدول المكوّنات عرض مرآة 4185 بينما
    السرد يقود بالمباشر 7118 — المباشر الرقمي صار مرشحاً منافساً (كان
    احتياطاً لا يعمل إلا بغياب كل مُهيكل) والمباشرية قبل اكتمال الحصة."""
    hhi, _sh, _pt, win = DP._structured_competition(
        [_MIRROR_STRUCTURED, _NUMERIC_DIRECT])
    assert hhi == 7118 and win is _NUMERIC_DIRECT


def test_mirror_only_is_still_consumed():
    """المرآة وحدها تبقى مستهلَكة معلَنة — الفكس لا يُفقد بيانات صالحة."""
    hhi, _sh, _pt, win = DP._structured_competition([_MIRROR_STRUCTURED])
    assert hhi == 4185 and win is _MIRROR_STRUCTURED


def test_direct_structured_still_wins_over_direct_numeric():
    """مباشر مُهيكل كامل يغلب المباشر الرقمي (أقفال D5 الثلاثة صامدة —
    الصلاحية أولاً ثم المباشرية ثم اكتمال الحصة ثم الأحدث سنةً)."""
    direct_structured = {
        "value": {"hhi": 5000, "year": 2024,
                  "top_suppliers": [{"partner": "Saudi Arabia", "share": 70}]},
        "source": "UN Comtrade", "data_year": 2024, "confidence": 0.9,
        "note": "",
    }
    hhi, *_ = DP._structured_competition(
        [_MIRROR_STRUCTURED, _NUMERIC_DIRECT, direct_structured])
    assert hhi == 5000


def test_numeric_winner_does_not_drop_observed_share_or_saudi_row():
    """C4 (الملاحظة 1): فوز المرشح الرقمي (بلا موردين) لا يُسقِط الحصة
    المرصودة — الحصة/الاسم يُكمَّلان من أفضل ملخّص مُهيكل يحملهما، وصف
    الشريك السعودي يُقرأ من الملخّصات مباشرة لا من فائز HHI."""
    hhi, share, partner, _f = DP._structured_competition(
        [_MIRROR_STRUCTURED, _NUMERIC_DIRECT])
    assert hhi == 7118 and share == 61.45
    assert partner and "saudi" in partner.lower()
    s, f = DP._saudi_share_from_competitors(
        [_MIRROR_STRUCTURED, _NUMERIC_DIRECT])
    assert s == 61.45 and f is _MIRROR_STRUCTURED
    dr = {"missions": {"trade_flow": {"findings": []},
                       "competitors": {"findings": [_MIRROR_STRUCTURED,
                                                    _NUMERIC_DIRECT]},
                       "demographics_economy": {"findings": []}}}
    assert DP.build_components(dr)["saudi_position"]["value"] == 61.45


def test_numeric_only_findings_keep_the_share_fallback():
    """C4 (الملاحظة 2): بلا أي ملخّص مُهيكل — حقيقتا HHI وحصة رقميتان —
    الحصة لا تضيع بفوز مرشح HHI الرقمي (عقد الاحتياط ما قبل الموجة)."""
    share_fact = {"value": 84.05, "source": "UN Comtrade",
                  "data_year": 2023, "note": "حصة أكبر مورد share 84.05"}
    hhi, share, _p, _f = DP._structured_competition(
        [_NUMERIC_DIRECT, share_fact])
    assert hhi == 7118 and share == 84.05


def test_numeric_value_only_prefers_latest_fact_year():
    """C4 (الملاحظة 7): بين حقائق رقمية متطابقة الإبرة تفوز أحدث سنة حقيقة
    (قاعدة D5 نفسها) لا أول وصول — مرآة 2019 لا تحجب مباشر 2024."""
    old_mirror = {"value": 4000, "source": "UN Comtrade (مرآة)",
                  "data_year": 2019, "note": "تركّز الموردين HHI"}
    fresh_direct = {"value": 7118, "source": "UN Comtrade",
                    "data_year": 2024, "note": "تركّز الموردين HHI"}
    val, f = DP._numeric_value_only([old_mirror, fresh_direct],
                                    "hhi", 100.0, 10_000.0)
    assert val == 7118 and f is fresh_direct


# ── F: أسماء الفحوص وقائد الحكم على كل سطح حجب ───────────────────────────

_FAIL_DECISION = {
    "verdict": "FAIL",
    "blocking": [{"check": "language_consistency", "repairable": False},
                 {"check": "trends_hollow_completion", "repairable": False}],
    "fail_drivers": ["language_consistency"],
}


def test_client_quality_summary_carries_names_on_fail():
    """حجب #14 وصل المالك بلا أسماء فحوص («رفض ينزل الملف») — ملخّص
    الجودة على FAIL يحمل الأسماء الحاجبة وقائد الحكم معاً."""
    out = EG.client_quality_summary(_FAIL_DECISION)
    assert out["blocked_checks"] == ["language_consistency",
                                    "trends_hollow_completion"]
    assert out["fail_drivers"] == ["language_consistency"]


def test_client_quality_summary_additive_only_on_pass():
    """المفتاحان إضافيان على FAIL حصراً — شكل PASS القائم حرفياً كما هو
    (نفس عقد `test_fail_drivers_field_is_additive_only`)."""
    out = EG.client_quality_summary({"verdict": "PASS", "blocking": []})
    assert "blocked_checks" not in out and "fail_drivers" not in out


def test_record_block_stores_fail_drivers_in_ops_context(monkeypatch):
    """سجل العمليات يحفظ قائد الحكم مع كل سجل حجب — «لا أستطيع التصرف في
    حجبٍ لا يقول ما الذي فشل»."""
    import silk_ops_log
    captured = {}

    def _rec(kind, msg, context=None):
        captured.update({"kind": kind, "context": context or {}})

    monkeypatch.setattr(silk_ops_log, "record_error", _rec)
    EG.record_block(7, "حليب", "الأردن", [], ["language_consistency"],
                    "pdf", surface="factory",
                    fail_drivers=["language_consistency"])
    assert captured["kind"] == "quality_gate_blocked_export"
    assert captured["context"]["fail_drivers"] == ["language_consistency"]


def test_platform_ui_renders_driver_and_check_names():
    """لافتة المنصة ومعالج زر PDF يعرضان الأسماء لا العدد وحده — السطح
    الذي واجه المالك هو الذي كان أعمى."""
    html = open(os.path.join(_ROOT, "web", "platform.html"),
                encoding="utf-8").read()
    assert "قائد الحجب" in html
    assert "الفحوص الحاجبة" in html
    assert "fail_drivers" in html and "blocked_checks" in html


def test_api_block_paths_pass_fail_drivers():
    """مواقع النداء الأربعة تمرّر قائد الحكم للسجل **وللحمولة** — C4
    (الملاحظة 6): مسار المُنتَج كان يمرّره للسجل وحده فيبقى سطر «قائد
    الحجب» أعمى على ذلك السطح (مرساة نصية — المسار الحي تغطيه اختبارات
    البوابة القائمة)."""
    for path in ("api.py", os.path.join("silk_platform", "api.py")):
        src = open(os.path.join(_ROOT, path), encoding="utf-8").read()
        assert "fail_drivers=" in src, path
        assert "fail_drivers=_drivers" in src, path


def test_cross_universe_ratio_survives_diacritics():
    """C4 (الملاحظة 5): الإبرتان على السطر المطبَّع معاً — السطر المشكول
    («نصيبُ الفرد») يُلتقط، ونسبة سليمة المقام موسومة «(مشتق)» لا تُتَّهم
    باشتقاق من الواردات."""
    hit = QG._check_cross_universe_ratio(
        "| نصيبُ الفرد التقديري من الواردات الرسمية | 0.60 دولار (مشتق) |")
    assert hit
    assert QG._check_cross_universe_ratio(
        "نصيب الفرد من الناتج المحلي 4,850 دولاراً (مشتق).") == []


def test_render_repairs_is_stripped_from_factory_payloads():
    """C4 (الملاحظة 9 — G-04): سجل رقع العرض قناة مشغّل؛ حمولات المصنع
    تُجرَّد منه في نفس نقطة الاختناق البنيوية لمفاتيح التكلفة."""
    from silk_platform import engine_bridge as EB
    payload = {"deep_research": {"render_repairs": [{"before": "س"}],
                                 "report": {"text": "نص"}}}
    out = EB.strip_cost_keys(payload)
    assert "render_repairs" not in out["deep_research"]
    assert out["deep_research"]["report"]["text"] == "نص"


# ── إعادة الإنتاج الكاملة: نص #14 لا يقود أي فحص نصي حاجب ────────────────

def test_study14_fixtures_produce_no_text_fail_driver():
    """المقاطع الحرفية التي قادت أو لامست الحجب — عبر البوابة كاملة بشكل
    العرض الحقيقي: لا `language_consistency` ولا أي قائد نصي من صنف
    الحادثة. المستثنيات الثلاث آثارُ تركيبة مقتطفٍ لا خصائصُ #14: فحصا
    اكتمال البنية يطلقان بحق على نصٍّ ليس تقريراً بأحد عشر قسماً، وفحص
    التغطية على عرضٍ بلا سجل أدلة (فرع T-01 «صفر مؤشرات»). (قائد الإنتاج
    البنيوي إن تكرر الحجب بعد النشر تكشفه لوحة fail_drivers — سلك F.)"""
    text = "\n".join([_DISTRIBUTORS, _SERIES,
                      "| نصيب الفرد التقديري من الواردات الرسمية "
                      "| نحو 0.60 دولار سنوياً (مشتق) |"])
    res = QG.run_quality_gate({"deep_research": {"report": {"text": text}}})
    fired = {f.get("check") for f in res["findings"]}
    assert "language_consistency" not in fired
    _snippet_artifacts = {"source_coverage_below_threshold",
                          "section_structure", "client_section_placeholder"}
    text_drivers = (fired - _snippet_artifacts) & (
        QG._REGRESSION_GUARD_FIRED | QG.FAIL_TRIGGER_CHECKS)
    assert not text_drivers, text_drivers
