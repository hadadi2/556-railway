"""الدرس ٢٩٥ — رقمٌ مختلَق من الملء، ولغةُ نظامٍ تصل المصنع، وحجبٌ على نصٍّ سليم.

كلُّ مثالٍ هنا أُعيد إنتاجه مباشرةً في تدقيق 2026-10-14 (أربعة مسارات فحص) —
قرار المالك: «حوّل كل مثال أعدت إنتاجه إلى اختبار ثابت».
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import silk_fact_ledger as L                                  # noqa: E402


def _led(**facts):
    entries = {}
    for key, value in facts.items():
        entries[key] = L._entry(key, value, source="UN Comtrade",
                                confidence=0.9, note="x")
    return {"entries": entries, "order": list(entries), "gaps": []}


# ── (١) الملء: لا رقمَ مختلَق، والجملةُ الناقصة تُحذَف كاملة ─────────────────

def test_decimal_point_is_not_a_sentence_end():
    """«89.4» كانت تُقطَع فيبقى «غير متاح.4 مليون دولار» — رقمٌ بلا أصل."""
    out, info = L.bind("بلغت الواردات في {{imports_latest_year}} نحو 89.4 "
                       "مليون دولار. والسوق مفتوح.", _led(imports_latest_year=None))
    assert out == "والسوق مفتوح."
    assert ".4" not in out and "4 مليون" not in out
    assert len(info["dropped"]) == 1 and "89.4" in info["dropped"][0]


def test_decimal_survives_when_the_fact_is_present():
    out, _ = L.bind("مؤشر التركّز {{hhi}} وقيمته 2.5 ضعف المتوسط.",
                    _led(hhi=3800.0))
    assert "2.5 ضعف" in out and "{{" not in out


def test_unknown_or_malformed_token_drops_its_sentence():
    led = _led(hhi=3800.0)
    for tok in ("{{bogus_key}}", "{{status:المفتاح}}", "{{imports_2024}}"):
        out, info = L.bind(f"السوق واعد. القيمة {tok} هنا. والخطوة التالية "
                           "الاعتماد.", led)
        assert out == "السوق واعد. والخطوة التالية الاعتماد.", (tok, out)
        assert info["unknown"], tok


def test_missing_sentence_token_drops_the_line():
    out, _ = L.bind("- {{imports_latest_year:sentence}}",
                    _led(imports_latest_year=None))
    assert out == ""


def test_self_describing_fact_is_kept_not_dropped():
    """«لا شروط مفتوحة» حقيقةٌ لا غياب — تبقى."""
    led = {"entries": {"open_conditions": L._entry(
        "open_conditions", 0, source="engine")}, "order": [], "gaps": []}
    out, _ = L.bind("{{open_conditions:sentence}}", led)
    assert out == "لا شروط مفتوحة."


def test_label_written_before_a_sentence_token_is_not_echoed():
    """كان يخرج «الشروط المفتوحة — الشروط المفتوحة شرطان»."""
    led = {"entries": {"open_conditions": L._entry(
        "open_conditions", 2, source="engine")}, "order": [], "gaps": []}
    out, _ = L.bind("- **الشروط المفتوحة** — {{open_conditions:sentence}}", led)
    assert out == "- الشروط المفتوحة شرطان."


def test_table_cell_keeps_its_column_with_the_gap_word():
    out, _ = L.bind("| السنة | {{imports_latest_year}} | {{status:المفتاح}} |",
                    _led(imports_latest_year=None))
    assert out == "| السنة | غير متاح | غير متاح |"


def test_repair_split_does_not_cut_decimals():
    assert L._SENT_SPLIT_RE.split("نحو 89.4 مليون.")[0] == "نحو 89.4 مليون."


# ── (٢) ما يراه المصنع: لا معرّفَ ولا نصَّ عطلٍ ولا لغةَ نظام ───────────────

import silk_export_gate as G                                  # noqa: E402
import silk_reports as SR                                     # noqa: E402
from silk_platform import engine_bridge as EB                 # noqa: E402

_LEAKS = ("_", "Error", "$", "التشغيلة", "بعثة", "المحرّك", "يُغلقه",
          "للدعم", "ANTHROPIC", "SILK_")


def test_factory_block_payload_has_no_check_ids_and_no_gate_wording():
    out = G.factory_detail([{"check": "adjacent_short_stutter"},
                            {"check": "ledger_token_unbound"}], "ar",
                           fail_drivers=["adjacent_short_stutter"])
    blob = str(out)
    assert "adjacent_short_stutter" not in blob
    assert "ledger_token_unbound" not in blob
    assert "يُغلقه" not in blob
    assert "أعِد توليد" not in out["message"]       # لا زرَّ يفعل ذلك للمصنع


def test_read_surface_summary_has_no_check_ids():
    d = G.client_quality_summary({"verdict": "FAIL", "fail_drivers":
                                  ["dangling_cross_reference"],
                                  "blocking": [{"check":
                                                "dangling_cross_reference"}]})
    assert "dangling_cross_reference" not in str(d)
    assert "blocked_checks" not in d and "fail_drivers" not in d


def test_passed_with_notes_points_to_a_section_the_client_copy_has():
    d = G.client_quality_summary({"verdict": "PASS-WITH-WARNINGS"})
    assert "حدود المنهجية" not in d["note"]
    assert "ما لم يكتمل للقرار" in d["note"]


def test_failed_run_reason_hides_the_technical_detail():
    raw = ("اكتملت البعثات والتحليل وحُفظا (رقم التحليل 41)؛ الطبقة الفاشلة: "
           "طبقة التحليل الشامل — السبب: anthropic.APIStatusError: "
           "overloaded_error (529) التكلفة الفعلية المسجَّلة 1.80$ لا تُستردّ")
    for reason, code in ((raw, "empty"),
                         ("تعذّر إكمال الدراسة. (التفصيل: research_run_failed)",
                          "engine_failed"),
                         ("محرّك البحث العميق غير جاهز: ANTHROPIC_API_KEY غير "
                          "مضبوط", None)):
        shown = EB.customer_failure_text(reason, code)
        assert not any(m in shown for m in _LEAKS), shown
    assert EB.customer_failure_text(EB.TIMEOUT_REASON) == EB.TIMEOUT_REASON


def test_stored_run_error_is_cleaned_on_the_way_out():
    row = EB.strip_cost_keys({"run_error": "تعذّر (التفصيل: engine_http_500)"})
    assert "engine_http_500" not in row["run_error"]


def test_quota_refusal_is_a_sentence_not_a_code():
    txt = EB.quota_refusal_text("monthly_quota_exceeded", 5, 5)
    assert "monthly_quota_exceeded" not in txt and "5 من 5" in txt


def test_confidence_phrase_leaves_no_broken_remnant_in_client_text():
    for t in ("الحكم مراقبة السوق بدرجة (درجة الثقة). نمو.",
              "الحكم WATCH بدرجة ثقة 0.6 (confidence). نمو.",
              "الحكم مشروط بدرجة ثقة مسقوفة، والطلب ينمو."):
        out = SR._client_sanitize(t, "ar")
        assert "بدرجة" not in out and "التوثيق" not in out, out
    assert "بدرجة كبيرة" in SR._client_sanitize("يتأثر بدرجة كبيرة بالسعر.",
                                                 "ar")


def test_screen_text_drops_the_sections_the_client_docx_drops():
    text = ("## 1. الخلاصة التنفيذية\nالسوق واعد.\n"
            "## 2. منهجية البحث ونطاقه\nاثنتا عشرة بعثة بحث ثم كاتب التقرير "
            "بدورتَي مراجعة.\n## 3. نظرة عامة\nالواردات 42 مليون دولار.")
    out = SR.client_screen_text(text, "ar")
    assert "بعثة" not in out and "كاتب التقرير" not in out
    assert "السوق واعد." in out and "42 مليون دولار" in out


def test_client_strings_say_study_not_run():
    import silk_i18n as I
    for key in ("leads_none", "limit_source_fetch_failed",
                "decision_weighted_line_empty"):
        assert "التشغيل" not in I.TERMS[key]["ar"], key


# ── (٣) التسليم: ثلاث عائلات تحجب، والباقي ملاحظة ────────────────────────────

import copy                                                   # noqa: E402

import silk_quality_gate as Q                                 # noqa: E402

for _p in (os.path.join(_ROOT, "tools"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _view_with(extra: str) -> dict:
    os.environ.setdefault("SILK_HERMETIC", "1")
    import silk_render as R
    from canonical_netherlands import netherlands_research_blob
    blob = copy.deepcopy(netherlands_research_blob())
    v = R.build_view(blob)
    rep = v["deep_research"]["report"]
    rep["text"] = rep["text"] + "\n\n" + extra
    return v


#: نصٌّ عربيٌّ احترافيٌّ سليم كان يحجب التسليم — كلُّ سطرٍ أُعيد إنتاجه.
_LEGIT = {
    "verdict_label_conflict": "التوصية: دخول مشروط. على المصدّر مواصلة "
                              "مراقبة السوق شهرياً.",
    "recommendation_tier_mislabel": "التوصية بالدخول المشروط لأن الطلب ينمو.",
    "confidence_value_conflict": "التعرفة منخفضة (5%) وحصة المملكة منخفضة (3%).",
    "confidence_band_mismatch": "حصة عالية (38%) والرسوم متوسطة (10%).",
    "language_consistency": "يشترط المشتري شهادة تحليل (certificate of "
                            "analysis) وسعر تسليم (free on board).",
    "style_inline_enumeration": "تشترط المادة (5) من اللائحة وسم المنتج، كما "
                                "يوضح الجدول (2).",
    "orphan_short_token": "- حجم الواردات 2023: 1,250 طن",
    "table_row_stutter": "| البند | الحالة | الحالة | الحالة |\n|---|---|---|---|\n"
                         "| شهادة حلال | مطلوب | مطلوب | مطلوبة |",
    "style_connector_excess": " ".join(["بالإضافة إلى ذلك ينمو الطلب."] * 5),
    "open_conditions_count_mismatch": "يتطلب التسجيل 3 شروط فنية، وباب "
                                      "التسجيل مفتوح طوال العام.",
    "adjacent_short_stutter": "**نقطة التعادل التشغيلي** — نقطة التعادل "
                              "التشغيلي = التكاليف الثابتة ÷ هامش المساهمة.",
    "gaps_closing_contradiction": "لا توجد فجوة بيانات جوهرية في هذا القسم.",
    "repeated_span": ("بلغت الواردات 42 مليون دولار (UN Comtrade، واردات "
                      "هولندا المبلّغة، البند 080410، 2023) والحصة 3% (UN "
                      "Comtrade، واردات هولندا المبلّغة، البند 080410، 2023)."),
    "reversed_route": "مسافة النقل البري البحرين – الدمام نحو 70 كم.",
    "dangling_cross_reference": "يراجع المصدّر «دليل المستورد» قبل الشحن.",
    "trailing_ellipsis": "- القهوة العربية والتركية والإسبريسو...",
    "unit_conversion_refusal": "كثافة الإنفاق الإعلاني غير متاحة.",
}


def test_delivery_blocks_only_three_families():
    assert Q.DELIVERY_BLOCKING_CHECKS == (
        Q.DELIVERY_FABRICATION | Q.DELIVERY_INTERNAL_TOKENS
        | Q.DELIVERY_SYSTEM_LANGUAGE | frozenset({"gate_crash"}))
    for check in _LEGIT:
        assert check not in Q.DELIVERY_BLOCKING_CHECKS, check


def test_legitimate_professional_text_is_delivered():
    for check, extra in _LEGIT.items():
        d = G.evaluate(_view_with(extra))
        assert d["verdict"] != "FAIL", (check, d["fail_drivers"])


def test_fabrication_and_internal_tokens_still_block():
    d = G.evaluate(_view_with("القيمة {{tariff_applied_pct غير مملوءة."))
    assert d["verdict"] == "FAIL" and "ledger_token_unbound" in d["fail_drivers"]
    d = G.evaluate(_view_with("رصد وكيل pricing_scout الأسعار."))
    assert d["verdict"] == "FAIL" and "mission_key_leak" in d["fail_drivers"]
    d = G.evaluate(_view_with("صاغ كلود هذا القسم."))
    assert d["verdict"] == "FAIL" and "claude_mention" in d["fail_drivers"]


def test_kept_blockers_no_longer_fire_on_legitimate_text():
    leak = Q._check_english_field_and_mission_key_leak
    assert not leak("المنافسون المباشرون (direct competitors) ولوجستيات "
                    "التبريد (cold chain logistics).")
    assert leak("رصد وكيل pricing_scout الأسعار.")
    pats = dict((c, rx) for c, rx, _n in Q._CONFIDENTIALITY_LEAK_PATTERNS)
    assert not pats["research_track_leak"].search("مسار البحث عن موزّع محلي")
    assert not pats["research_track_leak"].search("مسارات البحث والتطوير")
    assert pats["research_track_leak"].search("وفق مسار البحث الثالث")
    for seg in ("يحتاج حساب نقطة التعادل إلى 3 مدخلات",
                "كما في القسم 7 أدناه", "تنص المادة (5) على ذلك"):
        assert not Q._shows_a_value(Q._norm_ar(seg), False), seg
    assert Q._shows_a_value(Q._norm_ar("نقطة التعادل 1200 وحدة"), False)


def test_label_then_formula_with_dash_is_not_a_stutter():
    assert not Q._check_adjacent_short_stutter(_LEGIT["adjacent_short_stutter"])
    assert Q._check_adjacent_short_stutter("تحتاج تحققا تحتاج تحققا إضافيا.")


# ── (٤) ملاحظات المراجعة الذاتية (§58) ──────────────────────────────────────

def test_numbered_heading_keeps_its_title_when_its_fact_is_missing():
    out, _ = L.bind("## 3. حجم السوق في {{imports_latest_year}}",
                    _led(imports_latest_year=None))
    assert out.startswith("## 3. حجم السوق")


def test_dropped_bold_sentence_leaves_no_orphan_marker():
    out, _ = L.bind("**بلغت الواردات {{imports_latest_year}}.** والسوق مفتوح.",
                    _led(imports_latest_year=None))
    assert out == "والسوق مفتوح."


def test_missing_open_conditions_is_not_rendered_as_none():
    """«لا شروط مفتوحة» حين لم يُحسَب العدد نفيٌ مختلَق."""
    led = {"entries": {"open_conditions": L._entry("open_conditions", None)},
           "order": [], "gaps": []}
    assert L.bind("{{open_conditions:sentence}}", led)[0] == ""


def test_flag_gated_check_does_not_block_delivery_when_its_flag_is_off():
    f = [{"check": "reference_to_nonexistent_figure", "repairable": False}]
    old = os.environ.pop("SILK_DERIVED_PROVENANCE", None)
    try:
        assert Q.delivery_blockers(f) == []
    finally:
        if old is not None:
            os.environ["SILK_DERIVED_PROVENANCE"] = old


def test_confidence_removal_keeps_spaces_and_periods():
    for src, want in (("الحكم مراقبة بدرجة ثقة 62 والسوق كبير.",
                       "الحكم مراقبة والسوق كبير."),
                      ("الحكم مراقبة بدرجة ثقة 62. السوق كبير.",
                       "الحكم مراقبة. السوق كبير."),
                      ("الحكم بدرجة ثقة عالية جداً.", "الحكم.")):
        assert SR._client_sanitize(src, "ar") == want


def test_failure_text_keeps_the_instruction_the_factory_needs():
    shown = EB.customer_failure_text(
        "تعذّر تصنيف المنتج: مطابقة ضعيفة في hs_seed.csv (0.41) — أدخل رمز "
        "HS يدوياً ثم أعد الإطلاق", "unclassified")
    assert "أدخل رمز HS يدوياً" in shown and "hs_seed" not in shown
    cap = EB.customer_failure_text("متوقَّعة بنحو 1.8$. أُنفِق 12.5$ اليوم.")
    assert "غداً" in cap and "$" not in cap
    legacy = EB.customer_failure_text("لم تنطلق: monthly_quota_exceeded — 5 من 5")
    assert "monthly_quota_exceeded" not in legacy and "حصّتك الشهرية" in legacy


def test_every_delivery_blocker_has_its_own_sentence():
    assert all(c in G._CLIENT_REASONS for c in Q.DELIVERY_BLOCKING_CHECKS)


def test_brief_demand_number_is_not_rounded_into_a_new_value():
    from silk_narrative import fmt_number
    assert fmt_number(0.4) == "0.4" and fmt_number(42000000) == "42,000,000"
