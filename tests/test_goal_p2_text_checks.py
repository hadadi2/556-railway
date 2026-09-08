"""P2 من أمر إصلاح المحرّك (البنود 11–24) — فحوص نصية حتمية + إصلاحات عرض.

الدليل direct reproduction من التقريرين #10/#11 حرفياً: التكرار الثماني
(«…فئة جملة ضيقة م وهذا التناقض متوقَّع…»)، الفاصلة اليتيمة «(، World Bank
…)» و«(اهتمام=100، /)»، جدول TAM/SAM/SOM الميت، وسم «العامل منذ 1991 —
بيانات 1991»، «يرد أسفل هذا القسم آلياً»، وتحذير حجم السوق المقارن بذروة
2021 بدل مرجع 2023. + برهان المُطبِّع الواحد (أمر المُشرِف): الإبرة
المنوَّنة تطابق نصاً مجرَّداً والعكس. هرمتي. Run:
  python3 -m pytest tests/test_goal_p2_text_checks.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_quality_gate as QG                           # noqa: E402
import silk_render as R                                  # noqa: E402


# ── المُطبِّع الواحد (شرط المُشرِف الحاجب قبل الإغلاق) ─────────────────────

def test_normalizer_tanween_needle_matches_plain_text_and_reverse():
    """إبرة منوَّنة ↔ نص مجرَّد، بالاتجاهين — حادثة «أساساً/أساسا» لا تعود."""
    assert QG._norm_ar("أساساً للتفاوض") == QG._norm_ar("أساسا للتفاوض")
    assert QG._norm_ar("لم يُحدَّد") == QG._norm_ar("لم يحدد")
    assert QG._norm_ar("يتعذّر الحساب") == QG._norm_ar("يتعذر الحساب")
    # توحيد الهمزات والتاء المربوطة والألف المقصورة والتطويل
    assert QG._norm_ar("إجمالي الواردات") == QG._norm_ar("اجمالي الواردات")
    assert QG._norm_ar("فئة مجاورة") == QG._norm_ar("فئه مجاورة")
    assert QG._norm_ar("الأعلـــى") == QG._norm_ar("الاعلى")


def test_goal_family_checks_route_both_sides_through_the_normalizer():
    """جملة مشكولة بالكامل تلتقطها إبر الفحوص غير المشكولة — عبر الفحص
    الفعلي لا المُطبِّع وحده."""
    view = {"deep_research": {"missions": {}, "report": {
        "text": "اسْتَقَرَّ سِعْرُ الصَّرْفِ للدِّينارِ عِنْدَ 0.71."}},
        "markets": [{"entry_decision": {          # مفتاح العرض الحقيقي (درس 186)
            "schema": "silk.decision/v1", "score": 0.5,
            "pillars": {"risk": {"value": 0.4,
                                 "missing": ["fx_stability"]}}}}]}
    assert any(f["check"] == "pillar_narrative_sync"
               for f in QG._check_pillar_narrative_sync(view))


# ── البند 11: repeated_span ────────────────────────────────────────────────

def test_repeated_span_catches_the_stutter_family():
    dup = ("تسجّل الفئة الضيقة مؤشر تركّز سوق مرتفعاً جداً هنا "
           "تسجّل الفئة الضيقة مؤشر تركّز سوق مرتفعاً جداً هنا")
    filler = " ".join(f"كلمة{i}" for i in range(30))
    out = QG._check_repeated_span(filler + " " + dup + " " + filler)
    assert out and out[0]["check"] == "repeated_span"


def test_repeated_span_ignores_tables_headings_and_distant_repeats():
    table = "| السيناريو | شحن |\n| --- | --- |\n| منخفض | 5 |\n"
    body = (table + "## 1. عنوان\n" + table
            + " ".join(f"كلمة{i}" for i in range(120)))
    assert QG._check_repeated_span(body) == []


# ── البند 12: trailing_ellipsis سطرياً على مسار md (موجة سدّ الفجوات F3) ──

def test_mid_block_bullet_ellipsis_is_caught_on_md_path():
    """حادثة البند 12 حرفياً: «الديموغرافيا والاقتصاد الكلي: …» بندٌ في
    منتصف قائمة الفجوات — الفحص الكتلي يرى نهاية الكتلة فقط فكان البتر
    غير مرئي على مسار md (السطري docx فقط)."""
    block = ("- لم يتوفر من المصادر الرسمية أي رقم لهذه الفئة تحديداً…\n"
             "- الديموغرافيا والاقتصاد الكلي: بيانات ناقصة من المصدرين…\n"
             "- بند سليم يختم القائمة بجملة تامة ومكتملة الأركان.")
    out = QG._check_trailing_ellipsis(block)
    assert len(out) == 2
    assert all(f["check"] == "trailing_ellipsis" for f in out)


def test_line_level_ellipsis_keeps_docx_contract_quotes_and_short_lines():
    """نفس استثناءات عقد docx: سطر اقتباس («>») وقصير (≤25) لا يُعلَّمان،
    وكتلة تنتهي بالحذف لا تزدوج إصابتها."""
    assert QG._check_trailing_ellipsis("> اقتباس حرفي طويل جداً ينتهي بحذف…\n"
                                       "- سطر سليم يختم الكتلة هنا.") == []
    assert QG._check_trailing_ellipsis("- قصير…\n- سطر سليم يختم هنا.") == []
    tail = QG._check_trailing_ellipsis(
        "فقرة واحدة طويلة بما يكفي لتجاوز الحارس تنتهي ببتر غير نظيف…")
    assert len(tail) == 1


# ── البند 16: إكمال قائمة مفردات الغياب (موجة سدّ الفجوات F4) ─────────────

def test_absence_vocabulary_flags_all_nine_order_terms():
    """نص البند 16 يسمّي تسع صيغ تُختزل في اثنتين — «غير مرصود» و«غير مذكور»
    كانتا ناقصتين من القائمة بلا توثيق. المعتمدتان لا تُعلَّمان."""
    out = QG._check_absence_vocabulary(
        "السعر غير مرصود هنا والوزن غير مذكور في المصدر")
    assert out and out[0]["check"] == "absence_vocabulary"
    assert "غير مرصود" in out[0]["note"] and "غير مذكور" in out[0]["note"]
    assert QG._check_absence_vocabulary(
        "الرقم غير متاح والهامش غير محسوب") == []


def test_writer_prompt_no_longer_mandates_a_forbidden_absence_term():
    """التناقض الذاتي: الموجّه كان يفرض «وزن غير مذكور» في خلايا الأسعار
    ويحظر «غير مذكور» في قواعد الإخراج بعدها بأسطر — الخلية الآن
    «الوزن غير متاح» ولا موضع يفرض مفردة محظورة."""
    import silk_ai_judge as AJ
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_ai_judge.py"),
        encoding="utf-8").read()
    assert "«الوزن غير متاح»" in src
    assert "«وزن غير مذكور»" not in src
    import silk_render as SR
    assert SR._price_row_reason("علبة 5 دولار") == "الوزن غير متاح"
    assert AJ  # الاستيراد نفسه جزء من العقد الهرمتي


# ── البند 18: الصندوق الواحد + فحص تكرار التحذير (موجة سدّ الفجوات F5) ────

def test_caveat_repetition_flags_multiple_contextual_warnings():
    """جملة «مؤشر سياقي» تكررت أربع مرات في تقرير #10 — >1 = إصابة؛
    ظهور واحد (أو صفر) مشروع."""
    four = "تُقرأ الأرقام كمؤشر سياقي لفئة مجاورة. " * 4
    out = QG._check_caveat_repetition(four)
    assert out and out[0]["check"] == "caveat_repetition"
    assert "4" in out[0]["note"]
    assert QG._check_caveat_repetition(
        "تُقرأ الأرقام كمؤشر سياقي مرة واحدة هنا.") == []
    assert QG._check_caveat_repetition("نص بلا تحذير إطلاقاً.") == []


def test_view_builds_one_deterministic_caveat_box_when_hs_flagged():
    """صندوق التحذير الواحد يُبنى حتمياً في build_view عند تعليم الرمز —
    ويصل مُصدِّر md مرة واحدة أعلى التقرير؛ وبلا تعليم يبقى فارغاً."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools"))
    from canonical_netherlands import netherlands_research_blob
    blob = netherlands_research_blob()
    blob["hs_confirmation"] = {
        "hs_code": "040110", "code_desc": "حليب غير مركّز ≤1% دسم",
        "confirmed": False, "missing_terms": ["مجفف"]}
    v = R.build_view(blob, "ar")
    box = v["deep_research"]["caveat_box"]
    assert box and "040110" in box and "(*)" in box
    from silk_reports import render_markdown
    md = render_markdown(v)
    assert md.count(box) == 1
    # وبلا تعليم: صندوق فارغ (لا تحذير مختلَق)
    v_ok = R.build_view(netherlands_research_blob(), "ar")
    assert v_ok["deep_research"]["caveat_box"] == ""


# ── البند 13: empty_citation + طيّ العرض ──────────────────────────────────

def test_render_folds_orphan_commas_from_empty_source_fields():
    s = R._strip_internal_plumbing(
        "قيمة (، World Bank رصد مباشر لعام 2025) ومؤشر (اهتمام=100، /) هنا")
    assert "(،" not in s and "، /)" not in s
    assert "World Bank" in s and "اهتمام=100" in s     # المحتوى يبقى


def test_gate_flags_a_surviving_orphan_comma():
    out = QG._check_empty_citation("نص فيه (، World Bank 2025) يتيم")
    assert out and out[0]["check"] == "empty_citation"
    assert QG._check_empty_citation("نص سليم (World Bank، 2025)") == []


# ── البند 15: dead_table + طيّ العرض ──────────────────────────────────────

_DEAD = ("| الشريحة | القيمة | المصدر |\n"
         "| --- | --- | --- |\n"
         "| TAM | غير متاح | غير متاح |\n"
         "| SAM | غير متاح | غير متاح |\n"
         "| SOM | غير متاح | غير متاح |\n")


def test_dead_table_check_fires_and_live_table_passes():
    assert QG._check_dead_table(_DEAD)
    live = ("| السيناريو | أقصى EXW |\n| --- | --- |\n"
            "| منخفض | 0.50 |\n| متوسط | 0.40 |\n")
    assert QG._check_dead_table(live) == []


def test_render_collapses_a_dead_table_to_one_naming_line():
    out = R._collapse_dead_tables("قبل\n" + _DEAD + "بعد")
    assert "| TAM |" not in out
    assert "لم يُعرَض" in out and "الشريحة" in out
    assert "قبل" in out and "بعد" in out


# ── البند 14: لا وسم تقادم على سنة تأسيس ──────────────────────────────────

def test_founding_year_is_never_stamped_stale():
    s = R._tag_stale_years("كايلاني فود سنتر العامل منذ 1991 في السوق.",
                           stale_fact_years={1991})
    assert "الأحدث المتاح" not in s
    # وسنةُ بياناتٍ حقيقية تُوسَم كما كانت
    s2 = R._tag_stale_years("سجّلت الواردات في 2013 تراجعاً.",
                            stale_fact_years={2013})
    assert "الأحدث المتاح" in s2


# ── البند 16: مفردات الغياب ───────────────────────────────────────────────

def test_absence_vocabulary_flags_off_lexicon_terms_only():
    out = QG._check_absence_vocabulary(
        "القيمة لم يُرصَد بعد وهذه فجوة معلنة ويتعذّر الحساب هنا")
    assert out and "غير متاح" in out[0]["note"]
    assert QG._check_absence_vocabulary(
        "القيمة غير متاحة والهامش غير محسوب") == []


# ── البند 19: الدقة العشرية في النثر ──────────────────────────────────────

def test_decimal_precision_flags_prose_but_not_tables_or_appendix():
    assert QG._check_decimal_precision("السعر الأقصى 0.3274 دولار.")
    assert QG._check_decimal_precision("| أقصى EXW |\n| 0.3274 |") == []
    assert QG._check_decimal_precision(
        "## 11. الملاحق\nالقيمة الدقيقة 0.3274.") == []
    assert QG._check_decimal_precision("السعر 0.81 دولار (84%).") == []


# ── البند 20: طول الجملة ──────────────────────────────────────────────────

def test_sentence_length_average_over_25_warns():
    long_s = " ".join(f"كلمة{i}" for i in range(40)) + "."
    out = QG._check_sentence_length(long_s * 6)
    assert out and out[0]["check"] == "sentence_length"
    short = ("جملة قصيرة من خمس كلمات فقط. " * 8)
    assert QG._check_sentence_length(short) == []


# ── البند 23: لغة النظام ──────────────────────────────────────────────────

def test_system_language_is_stripped_at_render_and_guarded_at_gate():
    s = R._strip_internal_plumbing("يرد أسفل هذا القسم آلياً ملحق التقاطعات.")
    assert "آلياً" not in s and "ملحق التقاطعات" in s
    out = QG._check_system_language_leak("تلي هذا القسم آلياً أدلة التقاطعات")
    assert out and out[0]["check"] == "system_language_leak"


# ── البند 24: تحذير حجم السوق يسمّي الرقم والموضع وسنة المرجع ─────────────

def test_market_size_anchor_uses_reference_year_not_peak():
    dr = {"missions": {"trade_flow": {"findings": [
        {"value": 14_380_000, "note": "إجمالي واردات 2021", "data_year": 2021},
        {"value": 6_950_000, "note": "إجمالي واردات 2023", "data_year": 2023},
    ]}}}
    anchors = __import__("silk_plausibility")._anchors(dr)
    assert anchors["imports_usd"] == 6_950_000       # سنة المرجع لا الذروة
    assert anchors["imports_year"] == 2023


def test_caveat_names_figure_location_and_reference_year():
    import silk_plausibility as P
    lines = P.caveat_lines([{
        "mission": "demographics_economy", "claimed_usd": 1_300_000_000,
        "reason": ("يفوق إجمالي واردات البند المرصود لسنة المرجع 2023 "
                   "(6,950,000$) بمقدار 187× (السقف 25×)")}])
    assert len(lines) == 1
    ln = lines[0]
    assert "1,300,000,000$" in ln            # الرقم مسمّى
    assert "قسم «" in ln                      # الموضع مسمّى
    assert "2023" in ln                       # سنة المرجع مسمّاة


# ── الحرّاس المُفشِلون في عقد التصعيد ─────────────────────────────────────

def test_structural_p2_checks_are_fail_triggers_and_style_ones_are_not():
    for c in ("repeated_span", "empty_citation", "dead_table",
              "system_language_leak"):
        assert c in QG._REGRESSION_GUARD_FIRED, c
    for c in ("absence_vocabulary", "decimal_precision", "sentence_length"):
        assert c not in QG._REGRESSION_GUARD_FIRED, c
