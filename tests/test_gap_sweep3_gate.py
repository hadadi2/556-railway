"""موجة صيد الفجوات الثالثة — أقفال بوابة الجودة والعقود · gate-family locks.

الصياد الثاني (2026-08-25): فحوص FAIL موثقة «حاجزة» خارج مجموعتي الحجب،
إعفاء الإفصاح عربي فيعاقب الإفصاح الإنجليزي، مطابقة عملة خام تهزمها أل
التعريف والتشكيل، مرآة إنجليزية شرطها ينفي نفسه، ترقيم بداية السطر يُفشِل
بغير حق، فرع WARN ميت في ملخص الجودة، وموجّه يأمر بعنوان لا فرع إنجليزي له.
هرمتي. Run: python3 -m pytest tests/test_gap_sweep3_gate.py -q
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import silk_quality_gate as QG                          # noqa: E402
import silk_export_gate as EG                           # noqa: E402
import silk_style_contract as SC                        # noqa: E402


# ── B4: S-01/S-02 حاجزان فعلاً لا توثيقاً ────────────────────────────────

def test_s01_s02_barriers_are_wired_into_the_fail_set():
    """`recommendation_tier_mislabel` و`intersection_insufficiency` موثقان
    «حاجزين» (S-01/S-02) لكنهما لم يكونا في أي من مجموعتي الحجب — توصية
    «ادخل» فوق حكم مشروط كانت تُسلَّم 200 (الدرس 98: حارس لا يمكن أن يحجب)."""
    assert "recommendation_tier_mislabel" in QG.FAIL_TRIGGER_CHECKS
    assert "intersection_insufficiency" in QG.FAIL_TRIGGER_CHECKS
    drivers = EG._fail_drivers([
        {"check": "intersection_insufficiency", "repairable": False},
        {"check": "recommendation_tier_mislabel", "repairable": False},
    ])
    assert drivers == ["intersection_insufficiency",
                      "recommendation_tier_mislabel"]


# ── B5: إفصاح حساسية سنة الأساس بالإنجليزية يُعفي كما العربي ─────────────

_FLIP_SERIES_DR = {
    "report": {"text": ""},
    "missions": {},
}


def _dr_with_series(text: str) -> dict:
    # سلسلة تنقلب إشارتها بالأساس: 2018=100 → 2023=90 (انكماش) لكن 2019=60
    # → 2023=90 (نموّ). نقاط البعثات بشكلها المخزون (dict).
    rows = [(2018, 100.0), (2019, 60.0), (2023, 90.0)]
    return {"report": {"text": text}, "missions": {"m": {
        "findings": [{"value": v, "data_year": y,
                      "note": f"واردات {y} (USD)"} for y, v in rows]}}}


def test_cagr_check_fires_without_disclosure_and_exempts_english():
    """القفل السلوكي الكامل: بلا إفصاح يُطلق؛ الإفصاح الإنجليزي يُعفي."""
    dr = _dr_with_series("السوق في نموّ واضح خلال السلسلة.")
    assert QG._check_cagr_sign_flips_under_base_year(dr), \
        "فحص انقلاب الإشارة لا يطلق على سلسلة منقلبة بلا إفصاح"
    en = _dr_with_series("Growth is unresolved due to base-year "
                         "sensitivity; CAGR flips with the base year.")
    assert QG._check_cagr_sign_flips_under_base_year(en) == []


def test_base_year_disclosure_regex_has_english_mirror():
    """تقرير إنجليزي يصرّح بحساسية سنة الأساس (كما يأمر الموجّه 3.8) كان
    يُعاقَب FAIL لأن إعفاء الإفصاح عربي المِجَسّ — المرآة تُعفي الآن."""
    ar = "الاتجاه غير محسوم لحساسيته لسنة الأساس."
    en = "The trend is unresolved due to base-year sensitivity."
    en2 = "The CAGR sign depends on the base year chosen."
    assert QG._BASE_YEAR_DISCLOSED_RE.search(ar)
    assert QG._BASE_YEAR_DISCLOSED_RE.search(en), "لا مرآة إنجليزية للإعفاء"
    assert QG._BASE_YEAR_DISCLOSED_RE.search(en2)


# ── B6: مطابقة العملة تنجو من أل التعريف والتشكيل ────────────────────────

def test_off_market_currency_catches_definite_and_diacritized_forms():
    """نص حادثة §B3 الأصلية حرفياً («بالريال العُماني» — بأل التعريف
    والتشكيل) كان يفلت من المطابقة الخام — التطبيع يلتقطه الآن."""
    dr = {"report": {"text": "اقتبس التقرير سعراً بالريال العُماني 1.2"},
          "market": {"iso3": "YEM"}}
    hits = QG._check_off_market_currency(dr)
    assert hits, "الشكل المعرَّف المشكول أفلت من فحص العملة"
    assert hits[0]["check"] == "off_market_currency"
    # الشكل النكرة القائم يبقى ملتقطاً.
    dr2 = {"report": {"text": "سعر مرصود 1.2 ريال عماني للكيلو"},
           "market": {"iso3": "YEM"}}
    assert QG._check_off_market_currency(dr2)
    # عملة السوق نفسها مشروعة.
    dr3 = {"report": {"text": "بالريال العُماني"}, "market": {"iso3": "OMN"}}
    assert QG._check_off_market_currency(dr3) == []


def test_off_market_currency_has_english_mirror():
    dr = {"report": {"text": "The shelf price was quoted in Omani rials."},
          "market": {"iso3": "YEM"}}
    assert QG._check_off_market_currency(dr), \
        "عملة خارج السوق بالإنجليزية تفلت — لا مرآة"


# ── B7: مرآة الإحالة المعلقة الإنجليزية كانت تنفي نفسها ──────────────────

def test_dangling_methodology_reference_en_can_actually_fire():
    """شرط الإعفاء («methodology» في النص) كان جزءاً من عبارة الإحالة نفسها
    فلا يطلق الفحص أبداً — الإحالة تُستبعد قبل البحث عن القسم الفعلي."""
    hits = QG._dangling_cross_reference_en(
        "For the full caveat, see the methodology note.")
    assert any(h["check"] == "dangling_cross_reference" for h in hits), \
        "مرآة الإحالة المعلقة الإنجليزية لا يمكن أن تطلق — شرط ينفي نفسه"
    # وجود قسم منهجية فعلي يُعفي.
    ok = QG._dangling_cross_reference_en(
        "See the methodology note.\n\n## Methodology\nWe measured X.")
    assert not any(h["check"] == "dangling_cross_reference" for h in ok)


# ── B9: ترقيم بداية السطر مشروع ─────────────────────────────────────────

def test_line_start_enumeration_is_not_inline():
    """«(1)» في **بداية** سطر قائمة هو البديل الذي يقترحه الموجّه نفسه —
    كان `\\s` يبتلع `\\n` فيُفشِل القائمة المشروعة؛ وسط السطر يبقى ممنوعاً."""
    legit = "المتطلبات:\n(1) شهادة المنشأ\n(2) شهادة صحية"
    assert not QG._INLINE_ENUM_RE.search(legit), \
        "ترقيم بداية السطر عُدّ داخلياً — إيجاب كاذب حاجب"
    inline = "تشمل المتطلبات (1) شهادة المنشأ و(2) شهادة صحية."
    assert QG._INLINE_ENUM_RE.search(inline)


# ── B8: فرع WARN في ملخص جودة المصنع حي ─────────────────────────────────

def test_client_quality_summary_warn_branch_is_reachable():
    """كان يقارن بـ"WARN" بينما ثابت البوابة "PASS-WITH-WARNINGS" — تقرير
    مثقل بالملاحظات كان يُعلن للمصنع نجاحاً نظيفاً."""
    s = EG.client_quality_summary(
        {"verdict": QG.WARN, "blocking": [1, 2]}, "ar")
    assert "ملاحظات" in s["note"], s
    s_en = EG.client_quality_summary(
        {"verdict": QG.WARN, "blocking": []}, "en")
    assert "notes" in s_en["note"], s_en
    clean = EG.client_quality_summary({"verdict": "PASS", "blocking": []}, "ar")
    assert "ملاحظات" not in clean["note"]


# ── B11/B2: قائمة الإعلان بأسماء فحوص حقيقية ─────────────────────────────

def test_declared_ar_only_entries_name_real_emitted_checks():
    """كانت القائمة تسمّي فحوصاً لا وجود لها (confidence_band_label/
    style_alarmist) — والاسم الخاطئ أخفى عن قفل G-06 أن فحصاً حاجباً خامد.
    قناة skipped_checks تعرض هذه الأسماء للمشغّل فتكون حقيقية، ولا فحص
    حاجب فيها (G-06: الحاجب يُرآى لا يُعلَن)."""
    src = open(os.path.join(_ROOT, "silk_quality_gate.py"),
               encoding="utf-8").read()
    declared = {c for c, *_ in QG._AR_ONLY_CHECKS}
    for name in declared:
        assert f'"check": "{name}"' in src, name
    assert "confidence_band_label" not in declared
    assert "style_alarmist" not in declared
    assert not (declared & set(QG.FAIL_TRIGGER_CHECKS)), \
        "فحص حاجب معلن خامداً — يجب مرآته لا إعلانه"


def test_blocking_checks_now_fire_on_english_text():
    """المرايا الإنجليزية الجديدة سلوكياً: تسمية نطاق مخالفة، حكمان حاسمان،
    وتناقض دليل/متن — كلها كانت خامدة كلياً على lang=en."""
    # confidence_band_mismatch: «high (50%)» مخالفة للسلم (المتوقع low).
    assert any(h["check"] == "confidence_band_mismatch"
               for h in QG._check_confidence_band_label(
                   "Demand data confidence is high (50%) overall."))
    # verdict_label_conflict: تسميتان حاسمتان إثباتاً بالإنجليزية.
    dr = {"report": {"text":
          "Our assessment: Enter the market. Later the annex asserts "
          "Do not enter at this time as the standing recommendation."}}
    assert QG._check_verdict_label_conflict(dr)
    # evidence_body_numeric_contradiction: دليل 1M مقابل متن $10 million.
    dr2 = {"report": {"text":
           "Total imports reached 10 million dollars in 2023."},
           "missions": {"m": {"findings": [
               {"value": 1_000_000.0,
                "note": "HS040900 total imports 2023 (USD)"}]}}}
    hits = QG._check_evidence_body_numeric_consistency(dr2)
    assert any(h["check"] == "evidence_body_numeric_contradiction"
               for h in hits), hits


def test_confidence_value_conflict_fires_on_english():
    hits = QG._check_confidence_value_conflict(
        "Confidence is rated low (50%) in the demand section, while the "
        "annex states a confidence: 73% for the same series.")
    assert hits, "تعارض نسبتي الثقة بالإنجليزية يفلت — لا مرآة"


# ── B12/B13: أسماء متقادمة في سجل التدقيق والكتالوج ──────────────────────

def test_directive_audit_names_the_real_mirror_check():
    row = QG.DIRECTIVE_AUDIT_CHECKS.get("17-تباين المرآة مفكَّك")
    assert row and "mirror_divergence_contraction_narrative" in row[0], row


def test_report_writer_catalog_row_states_eleven_sections():
    import silk_ai_judge  # noqa: F401 — تسجيل صفوفه في الكتالوج عند الاستيراد
    import silk_missions  # noqa: F401 — صف report_writer يُسجَّل من هنا
    import silk_agents as SA
    row = next(a for a in SA.AGENT_CATALOG if a["key"] == "report_writer")
    assert "أحد عشر" in row["role"], row["role"]
    assert "خمسة عشر" not in row["role"]


# ── B3: عنوان «شرطا قلب الحكم» له فرع إنجليزي ومسجَّل ───────────────────

def test_verdict_flip_heading_has_english_branch_and_is_registered():
    """الموجّه كان يفرض '### شروط إعادة تقييم القرار' حرفياً بلا فرع لغة — على تقرير
    إنجليزي يناقض جدار اللغة ويُفشِل language_consistency (الموجّه يأمر بما
    تحجبه البوابة — عائلة الدرس 156)."""
    import silk_ai_judge as AJ
    src = open(os.path.join(_ROOT, "silk_ai_judge.py"),
               encoding="utf-8").read()
    assert "### Decision flip conditions" in src, "لا فرع إنجليزياً للعنوان"
    for lit in ("### شروط إعادة تقييم القرار", "### Decision flip conditions",
                "### المنتجات المنافسة وأسعارها",
                "### Competing products and their prices"):
        assert lit in AJ.MANDATED_OUTPUT_LITERALS, f"غير مسجَّل: {lit}"


def test_flip_heading_mandate_branches_on_lang_in_source():
    """الفرع مشروط باللغة في نقطة الفرض نفسها (بنية المصدر): العنوان العربي
    لا يُفرَض إلا خلف فرع lang — لا فرض عربياً غير مشروط على lang=en."""
    src = open(os.path.join(_ROOT, "silk_ai_judge.py"),
               encoding="utf-8").read()
    idx = src.find("'### شروط إعادة تقييم القرار'")
    assert idx != -1
    window = src[max(0, idx - 300):idx]
    assert 'if lang == "en"' in window, \
        "العنوان العربي يُفرَض بلا فرع لغة — يناقض جدار اللغة على lang=en"


# ── B10: سقف تقسيم الجملة الإنجليزي موحَّد على ٣٥ ────────────────────────

def test_english_tone_rule_split_threshold_matches_unified_cap():
    """"split anything over twenty-five words" ناقض المعيار الموحّد (متوسط
    ≤25، أقصى 35) داخل العقد نفسه — القاعدتان تُسلَّمان معاً للكاتب."""
    assert "thirty-five" in SC.PROFESSIONAL_TONE_RULE_EN
    assert "over twenty-five" not in SC.PROFESSIONAL_TONE_RULE_EN
