"""عيوب الدراسة الحية #12 (حليب×الأردن، HS 040120، بيانات 2024) — الأقفال.

الدليل (direct reproduction — تقرير #12 المُسلَّم من الإنتاج): خمسة عيوب
مرصودة حرفياً بعد اكتمال أمر إصلاح المحرّك، كلٌّ بجذره المثبَت بإعادة
إنتاج تنفيذية:
  D1 صفّا جدول ملتحمان ببتر خلية («يُق» + الصف كاملاً) — قاصّ التلعثم
     يشترط مسافةً قبل التداخل وبداية الصف يسبقها سطر جديد.
  D2 وسم «(الأحدث المتاح)» على سنوات سردٍ تاريخي — مقسِّم الجمل يعدّ
     نقطة «1.77» العشرية نهايةَ جملة فيعزل كل سنة عن أحدث منها.
  D3 سطر حدود ينتهي بـ«…» — بتر ملخص البعثة عند 500 حرف يضيفها داخل
     قائمة الفجوات، والحدود لا يمر عليها فحص.
  D5 «مكوّنات أفضل سوق» يعرض قيمة 2019 (1.77M) بدل 18.6M (2024) والمرآة
     2025 بدل المباشر — أول مطابقة تفوز لا الأحدث/الأمتن.
(D4 — مفردات الغياب على أسطح اللوحة — أقفاله أدناه بفحص نص المصدر.)

هرمتي. Run: python3 -m pytest tests/test_study12_live_defects.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name: str) -> str:
    with open(os.path.join(_ROOT, name), encoding="utf-8") as fh:
        return fh.read()


# ── D1 — تلعثم صف الجدول ──────────────────────────────────────────────

_D1_BASE = ("نص سابق سليم.\n\n| المتغير | القيمة |\n|---|---|\n"
            "| عدد سكان الأردن (2024، مرجع سِلك) | 11.6 مليون نسمة |\n"
            "| عدد السكان المسلمين المقدَّر | يُق")
_D1_CONT = ("| عدد السكان المسلمين المقدَّر | يُقدَّر بنحو 11.2 مليون "
            "نسمة، بضرب عدد السكان في نسبة 97% |")


def test_join_stutter_trims_across_table_row_boundary():
    """D1: التداخل المسبوق بسطر جديد (بداية صف جدول) يُقصّ كما المسبوق
    بمسافة — كان `_find_join_overlap` يشترط مسافةً حصراً فالتحم الصفان."""
    import silk_ai_judge as AJ
    base, cont = AJ._trim_join_stutter(_D1_BASE, _D1_CONT)
    joined = base + " " + cont
    assert joined.count("عدد السكان المسلمين المقدَّر") == 1
    assert "| يُق |" not in joined
    assert "يُقدَّر بنحو 11.2 مليون" in joined


def test_join_stutter_space_boundary_still_trims():
    """الضابط: سلوك حدّ المسافة القائم (دراسة #10) لم يمسّه القبول بـ\\n."""
    import silk_ai_judge as AJ
    base = "يشير التحليل إلى أن قاعدة المقارنة لهذا الانكماش الحاد م"
    cont = "قاعدة المقارنة لهذا الانكماش الحاد مؤقتة وترتبط بقاع 2019."
    b, c = AJ._trim_join_stutter(base, cont)
    assert (b + " " + c).count("قاعدة المقارنة لهذا الانكماش الحاد") == 1


def test_gate_table_row_stutter_flags_glued_duplicate_cells():
    """D1 (حارس الانحدار، توقيع C1): خلية قصيرة بادئة صارمة لخلية لاحقة
    في نفس الصف (أي مسافة) تُفشِل — و`repeated_span` يبقى مستثنياً الجداول."""
    import silk_quality_gate as QG
    glued = ("| المتغير | القيمة |\n|---|---|\n"
             "| عدد السكان المسلمين المقدَّر | يُق "
             "| عدد السكان المسلمين المقدَّر | يُقدَّر بنحو 11.2 مليون نسمة |")
    view = {"deep_research": {"report": {"text": glued}, "missions": {}}}
    out = QG.run_quality_gate(view)
    assert any(f["check"] == "table_row_stutter" for f in out["findings"])
    assert out["verdict"] == QG.FAIL
    clean = ("| المنتج | المنشأ |\n|---|---|\n"
             "| حليب بوردة | السعودية |\n| حليب لونا | غير متاح |")
    ok = QG.run_quality_gate(
        {"deep_research": {"report": {"text": clean}, "missions": {}}})
    assert not any(f["check"] == "table_row_stutter" for f in ok["findings"])


def test_table_row_stutter_never_flags_identical_or_numeric_cells():
    """اتجاها C1: التطابق التام وحده مشروع (خليتا «غير متاح»)، وبادئة
    الأرقام («5» بادئة «5.84 مليون») ليست بتراً — كلاهما يمرّ."""
    import silk_quality_gate as QG
    twins = ("| الحد الأدنى | غير متاح | الحد الأعلى | غير متاح |\n"
             "| النطاق | 5 | الذروة | 5.84 مليون دولار |")
    assert QG._check_table_row_stutter(twins) == []
    refined = "| الفئة | حليب | الوصف | حليب كامل الدسم |"
    assert QG._check_table_row_stutter(refined) == []


def test_table_row_stutter_tolerates_arabic_morphological_pairs():
    """دورة §58 الثانية (direct reproduction للملاحظة): الصرف العربي يجعل
    البادئة وحدها كاذبة — مذكر/مؤنث الغياب وضمير الملكية في صف واحد
    يمرّان؛ الإطلاق يشترط دليلَ إعادة الصف (خلية أخرى مكررة حرفياً)."""
    import silk_quality_gate as QG
    fem = "| السعر بالتجزئة | غير متاح | ملاحظة | غير متاحة |"
    assert QG._check_table_row_stutter(fem) == []
    clitic = "| الفئة | حليب | الوصف | حليبنا الطازج |"
    assert QG._check_table_row_stutter(clitic) == []


# ── D2 — وسم التقادم على سرد سلسلة ────────────────────────────────────

_D2_SERIES = ("بلغت 1.77 مليون دولار في 2019 ثم قفزت إلى 7.74 مليون دولار "
              "في 2020، فبلغت ذروتها عند 14.4 مليون دولار في 2021 ثم "
              "تراجعت إلى 9.33 مليون دولار في 2022 ثم إلى 6.95 مليون "
              "دولار في 2023، قبل أن تنقلب صعوداً إلى 18.6 مليون دولار "
              "في 2024 وفق UN Comtrade.")


def test_series_narrative_with_decimal_figures_gets_no_stale_stamp():
    """D2: جملة سلسلة بكسور عشرية — النقطة بين رقمين ليست حدّ جملة،
    فالسنوات القديمة ترى 2024 في جملتها ولا تُوسم «الأحدث المتاح»."""
    import silk_render as SR
    out = SR._tag_stale_years(_D2_SERIES, {2019, 2020, 2021})
    assert "الأحدث المتاح" not in out


def test_lone_stale_year_is_still_stamped():
    """الضابط: سنة قديمة وحيدة بلا أحدث منها في جملتها تبقى موسومة."""
    import silk_render as SR
    s = "صُنِّف الميناء وفق دليل الموانئ العالمي لعام 2019 تصنيفاً متدنياً."
    out = SR._tag_stale_years(s, {2019})
    assert "الأحدث المتاح" in out


# ── D3 — حدود بلا «…» ────────────────────────────────────────────────

def test_gaps_blob_cuts_at_gap_boundary_never_midway():
    """D3(أ): بتر كتلة «| فجوات:» يقع عند حدّ فجوة كاملة («؛») — الفجوة
    التي لا تسعها النافذة تُسقَط كاملةً بعدد معلَن، لا «…» على محتواها."""
    from silk_llm_runtime import _gaps_blob
    gaps = ["نمو السكان السنوي غير متاح",
            "نسبة الشباب (تحت 30 سنة) غير متاحة",
            "بيانات اقتصادية فعلية للسنوات السابقة قبل 2019 غير متاحة "
            "من المصدرين الرسميين المعتمدين في هذه الدراسة"]
    out = _gaps_blob("ملخص البعثة", gaps, max_len=120)
    assert "…" not in out
    assert "نمو السكان السنوي غير متاح" in out
    assert "غير مدرجة" in out
    # §58 (الملاحظة 8): العدّاد مقطع أنبوب مستقل — لا يصير سطرَ حدودٍ
    # بلا مرجع عبر _mission_gap_lines.
    import silk_render as SR
    lines = SR._mission_gap_lines("الديموغرافيا والاقتصاد الكلي", out)
    assert lines and all("غير مدرجة" not in ln for ln in lines)


def test_mission_gap_lines_drop_truncated_fragment():
    """D3(ب): شظية فجوة تنتهي بـ«…» (بترٌ سابق وصل المخزن) تُسقَط دفاعياً
    — نص البند 12: امنع البتر أو أسقط السطر."""
    import silk_render as SR
    summary = ("ملخص | فجوات: نمو السكان السنوي غير متاح؛ "
               "بيانات اقتصادية فعلية للسنوات السابقة… | نداءات أدوات: 4")
    lines = SR._mission_gap_lines("الديموغرافيا والاقتصاد الكلي", summary)
    assert lines == ["الديموغرافيا والاقتصاد الكلي: نمو السكان السنوي غير متاح"]


def test_quality_gate_flags_truncated_limit_line():
    """D3(ج): سطر حدود ينتهي بـ«…» يصل البوابة — كانت تفحص نص التقرير
    فقط بينما «حدود هذا التقرير» قائمة view منفصلة."""
    import silk_quality_gate as QG
    view = {"deep_research": {
        "report": {"text": "نص سليم يكفي طوله لفحص عادي."}, "missions": {},
        "limits": ["الديموغرافيا والاقتصاد الكلي: بيانات اقتصادية فعلية "
                   "للسنوات السابقة…"]}}
    out = QG.run_quality_gate(view)
    assert any(f["check"] == "trailing_ellipsis" for f in out["findings"])
    ok = QG.run_quality_gate({"deep_research": {
        "report": {"text": "نص سليم يكفي طوله لفحص عادي."}, "missions": {},
        "limits": ["تدفقات التجارة: تفاصيل أكبر الدول المصدرة غير متاحة"]}})
    assert not any(f["check"] == "trailing_ellipsis" for f in ok["findings"])


# ── D4 — مفردات الغياب على أسطح اللوحة ───────────────────────────────

def test_view_surface_producers_use_canonical_absence_vocabulary():
    """D4: منتجو سلاسل العرض (i18n/القرار/اللوحة/التقارير/المترجم) لا
    يحملون المفردات المحظورة — الثنائية القانونية «غير متاح»/«غير محسوب»."""
    from silk_quality_gate import _ABSENCE_FORBIDDEN
    import silk_i18n
    for key in ("pillar_missing_lead", "cond_pillar_missing",
                "not_observed", "price_not_observed"):
        for lang in ("ar",):
            val = silk_i18n._STRINGS[key][lang] \
                if key in getattr(silk_i18n, "_STRINGS", {}) \
                else silk_i18n.t(key, lang)
            for term in _ABSENCE_FORBIDDEN:
                assert term not in val, (key, term)
    for fname in ("silk_decision.py", "silk_narrative.py"):
        src = _src(fname)
        assert "لم يُرصَد" not in src.replace("لم يُرصَد بعد»", ""), fname
    for fname in ("web/platform.html", "web/index.html"):
        src = _src(fname)
        assert "غير مرصود" not in src, fname
        assert "فجوة معلنة" not in src, fname


def test_absence_vocabulary_check_scans_view_surfaces():
    """D4 (البوابة): الفحص التحذيري يمسح سلاسل العرض (أعمدة/شروط/حدود/
    مكونات) لا نص التقرير وحده."""
    import silk_quality_gate as QG
    view = {"deep_research": {
        "report": {"text": "نص سليم بلا مفردات محظورة."}, "missions": {},
        "limits": []},
        "markets": [{"decision": {"schema": "s", "verdict": "GO",
                                  "score": 0.7, "pillars": {}},
                     }],
        "decision": {"basis": {"pillars": [
            {"name": "هامش الربحية", "strength_pct": None,
             "note": "لم يُرصَد بعد: هامش السعر عند الحدود"}]}}}
    out = QG.run_quality_gate(view)
    assert any(f["check"] == "absence_vocabulary" for f in out["findings"])


# ── D5 — اختيار قيم المكونات ─────────────────────────────────────────

def _dp(value, note, year=None, source="UN Comtrade", conf=0.9):
    return {"value": value, "note": note, "source": source,
            "confidence": conf, "data_year": year}


def test_numeric_prefers_latest_fact_year_over_first_match():
    """D5(أ): بين المطابقات الصالحة يفوز أحدثُ سنة حقيقة — كانت أول
    مطابقة (2019: 1.77M) تفوز على 18.6M (2024) لأن البعثة تسرد الأقدم أولاً."""
    import silk_deep_pillars as DP
    findings = [
        _dp(1_770_000, "HS040120 إجمالي استيراد Jordan من العالم 2019, USD",
            2019),
        _dp(7_740_000, "HS040120 إجمالي استيراد Jordan من العالم 2020, USD",
            2020),
        _dp(18_600_000, "HS040120 إجمالي استيراد Jordan من العالم 2024, USD",
            2024),
    ]
    assert DP._numeric(findings, "tam_usd") == 18_600_000


def test_numeric_without_years_keeps_first_match():
    """الضابط: مُهيكلان بلا سنوات — أولُ مطابقة يبقى (ترتيب الأداة حتمي)."""
    import silk_deep_pillars as DP
    findings = [_dp(5_000_000, "إجمالي واردات السوق بالدولار"),
                _dp(9_000_000, "قيمة الواردات وفق مصدر آخر")]
    assert DP._numeric(findings, "tam_usd") == 5_000_000


def test_prose_span_years_do_not_shadow_a_real_tool_fact():
    """§58/C2 بالنثر الحرفي من دراسة #12: «من 1.77 مليون دولار في 2019 إلى
    18.6 مليون دولار في 2024» — سنو النثر لا تُنقَّب فلا يقترن رقمُه الأول
    (1.77M) بسنة 2024 زوراً؛ حقيقة الأداة المُهيكلة (2024) تفوز."""
    import silk_deep_pillars as DP
    prose = {"value": "قفزت واردات الأردن من الحليب من 1.77 مليون دولار في "
                      "2019 إلى 18.6 مليون دولار في 2024 وفق UN Comtrade",
             "note": "مسار الواردات عبر السنوات", "source": "بحث ويب",
             "confidence": 0.5, "data_year": None}
    tool = _dp(18_600_000,
               "HS040120 إجمالي استيراد Jordan من العالم 2024, USD", 2024)
    value, src_f = DP._numeric_with_source([prose, tool], "tam_usd")
    assert value == 18_600_000
    assert src_f is tool


def test_iso_fetch_date_in_note_is_not_a_fact_year():
    """§58: «جُلبت أصلاً 2026-08-20» تاريخُ جلبٍ لا سنةَ حقيقة — لا يفوز
    نثرٌ قديم بسنةٍ مختلقة من تاريخ ISO."""
    import silk_deep_pillars as DP
    assert DP._fact_year({"value": 5, "note": "من المخزن — جُلبت أصلاً "
                          "2026-08-20", "data_year": None}) is None
    assert DP._fact_year({"value": 5, "note": "واردات عام 2024",
                          "data_year": None}) == 2024
    # تحويل الخطر المصرَّف فكساً: مدى «2019-2024» يبقى مقروءاً (أحدث
    # طرفيه) — كان استثناء «-» الأعمى يلتهم الطرفين فيفقد البندُ سنته.
    assert DP._fact_year({"value": 12, "note": "نمو مركّب 2019-2024: 12%",
                          "data_year": None}) == 2024


def test_multiple_undated_prose_candidates_declare_a_gap():
    """C2: نثران فأكثر بلا أي سنة وبلا مُهيكل بينهما = لا أساس للاختيار —
    فجوة معلنة لا انزلاق لأول وصول (آلية #12 بعينها)."""
    import silk_deep_pillars as DP
    p1 = {"value": "الواردات نحو 5 مليون دولار", "note": "ادعاء ويب",
          "source": "بحث ويب", "confidence": 0.5, "data_year": None}
    p2 = {"value": "قيمة الواردات 9 مليون دولار", "note": "ادعاء آخر",
          "source": "بحث ويب", "confidence": 0.5, "data_year": None}
    assert DP._numeric_with_source([p1, p2], "tam_usd") == (None, None)


def test_single_prose_candidate_is_consumed_with_unknown_year():
    """سؤال المُشرِف صراحةً: مرشح نثري وحيد يُستهلَك (لا اعتباط فيه) —
    وسنته تبقى مجهولة معلَنة (data_year=None في إسناد المكوّن)."""
    import silk_deep_pillars as DP
    lone = {"value": "بلغت واردات السوق 1.77 مليون دولار في 2019",
            "note": "ادعاء وحيد", "source": "بحث ويب",
            "confidence": 0.5, "data_year": None}
    value, src_f = DP._numeric_with_source([lone], "tam_usd")
    assert value == 1_770_000
    assert src_f is lone
    dr = {"missions": {"trade_flow": {"findings": [lone]},
                       "competitors": {"findings": []},
                       "demographics_economy": {"findings": []}}}
    comps = DP.build_components(dr)
    assert comps["market_size"]["value"] == 1_770_000
    assert comps["market_size"]["data_year"] is None   # مجهولة معلَنة


def test_structured_competition_prefers_direct_over_mirror():
    """D5(ب): قاموس مباشر (2024، ثقة 0.9) يفوز على قاموس مرآة (2025،
    ثقة 0.6) — كان أول قاموس يفوز بترتيب الوصول."""
    import silk_deep_pillars as DP
    mirror = {"value": {"year": 2025, "hhi": 4185, "supplier_count": 10,
                        "top_suppliers": [{"partner": "Saudi Arabia",
                                           "share": 61.45}]},
              "source": "UN Comtrade (مرآة)", "confidence": 0.6,
              "note": "HS040120 مورّدو الأردن 2025 (مرآة): HHI=4185",
              "data_year": 2025}
    direct = {"value": {"year": 2024, "hhi": 9040, "supplier_count": 8,
                        "top_suppliers": [{"partner": "Saudi Arabia",
                                           "share": 95.04}]},
              "source": "UN Comtrade", "confidence": 0.9,
              "note": "HS040120 مورّدو الأردن 2024: HHI=9040",
              "data_year": 2024}
    hhi, share, partner, f = DP._structured_competition([mirror, direct])
    assert hhi == 9040
    assert share == 95.04
    # ومرآتان فقط: الأحدث يفوز
    m2 = dict(mirror)
    m2["value"] = dict(mirror["value"], year=2023, hhi=7118)
    m2["data_year"] = 2023
    hhi2, _s, _p, _f = DP._structured_competition([m2, mirror])
    assert hhi2 == 4185
    # §58 (الملاحظة 5): مباشرٌ بقيمة خارج المدى (⇒ None) لا يحجب مرآةً صالحة
    bad_direct = dict(direct)
    bad_direct["value"] = dict(direct["value"], hhi=50)   # دون أرضية 100
    hhi3, _s3, _p3, _f3 = DP._structured_competition([bad_direct, mirror])
    assert hhi3 == 4185


def test_component_confidence_comes_from_winning_finding():
    """D5(ج): ثقة المكوّن من النتيجة الفائزة (0.9 مباشر / 0.6 مرآة) لا
    حرفية 0.6 الثابتة — والإسناد (مصدر/سنة) من النتيجة الفائزة نفسها."""
    import silk_deep_pillars as DP
    dr = {"missions": {"trade_flow": {"findings": [
        _dp(1_770_000, "HS040120 إجمالي استيراد Jordan من العالم 2019, USD",
            2019, conf=0.9),
        _dp(18_600_000, "HS040120 إجمالي استيراد Jordan من العالم 2024, USD",
            2024, conf=0.9),
    ]}, "competitors": {"findings": []},
        "demographics_economy": {"findings": []}}}
    comps = DP.build_components(dr)
    ms = comps["market_size"]
    assert ms["value"] == 18_600_000
    assert ms["data_year"] == 2024
    assert ms["confidence"] == 0.9
    assert comps["competition"]["confidence"] == 0.0   # الغائب صفر كما هو
