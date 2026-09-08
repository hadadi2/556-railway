"""الملاحظات §58 المؤجّلة الثلاث (find all gaps مجموعة 5 — درس 191).

قرار المالك 2026-08-27 (المانع زال بالدليل):
- A (fx cap): تقلّبٌ >100% (عملة منهارة) كان يُسقَط فيقرأ العمود «غير مرصود»
  ويُعيد التطبيع صعوداً — انقلابُ إشارة. سلامةُ الأساس مثبتة (كل المدوّنات
  fx=None).
- B (خلط الأنواع في check_against_history): صفُّ /analyze أحدث يحجب /research
  الأقدم فيعطّل فحص «ترقية حكم على أدلة أسوأ» ويطبع «لا تشغيلة سابقة» كاذباً.
- B2 (hs_caveat يطبع None): قالبُ EN وسطرُ AR يقحمان وصفَ الرمز بلا حارس.

Hermetic؛ لا شبكة.
"""
from __future__ import annotations

import silk_deep_pillars as DP


# ── A: سقف تقلّب الصرف يسع العملة المنهارة ────────────────────────────────

def _fx(vol):
    return [{"value": vol, "note": f"[risk] تقلب سعر الصرف {vol}% — مستنتَج"}]


def test_collapsed_currency_volatility_reaches_the_pillar_not_dropped():
    """187% كان يُسقَط (>100) فيقرأ None؛ يصل الآن قيمةً حقيقية."""
    assert DP._numeric(_fx(187.4), "fx_volatility_pct") == 187.4


def test_hyperinflation_volatility_within_new_ceiling():
    assert DP._numeric(_fx(50_000.0), "fx_volatility_pct") == 50_000.0


def test_absurd_volatility_still_rejected_as_unit_error():
    assert DP._numeric(_fx(200_000.0), "fx_volatility_pct") is None


def test_moderate_volatility_unaffected():
    assert DP._numeric(_fx(18.0), "fx_volatility_pct") == 18.0


# ── B: مقارنة التاريخ داخل النوع نفسه ─────────────────────────────────────

def _research_result(deep=True):
    r = {"product": "تمور", "market": {"name_ar": "الأردن"}}
    if deep:
        r["deep_research"] = {"verdict": {"verdict": "GO"}}
    return r


def test_history_lookup_ignores_a_newer_analyze_row_shadowing_research():
    """صفُّ /analyze أحدث لا يحجب /research الأقدم — المقارنة داخل النوع."""
    import silk_consistency as SC
    rows = [
        {"id": 20, "product": "تمور", "market_name": "الأردن",
         "status": "completed", "kind": "analyze"},          # أحدث، نوع مختلف
        {"id": 10, "product": "تمور", "market_name": "الأردن",
         "status": "completed", "kind": "research"},          # الأقدم، مطابق
    ]
    blobs = {20: {"product": "تمور"},   # بلا deep_research
             10: {"deep_research": {"verdict": {"verdict": "CONDITIONAL"}}}}
    out = SC.check_against_history(
        _research_result(), _list=lambda: rows, _get=lambda i: blobs.get(i))
    assert out.get("previous_analysis_id") == 10, out


def test_history_lookup_infers_kind_for_legacy_null_rows():
    """صفٌّ قديم بلا عمود kind يُستنتَج نوعه من شكل البلوب (لا يُقصى)."""
    import silk_consistency as SC
    rows = [{"id": 7, "product": "تمور", "market_name": "الأردن",
             "status": "completed"}]   # لا مفتاح kind (قبل الترحيل)
    blobs = {7: {"deep_research": {"verdict": {"verdict": "GO"}}}}
    out = SC.check_against_history(
        _research_result(), _list=lambda: rows, _get=lambda i: blobs.get(i))
    assert out.get("previous_analysis_id") == 7, out


# ── B2: تحذير الرمز لا يطبع None حين يغيب الوصف ────────────────────────────

def test_hs_caveat_box_nodesc_key_is_bilingual_without_none():
    import silk_i18n
    for lang in ("ar", "en"):
        s = silk_i18n.t("hs_caveat_box_nodesc", lang, tag="X", hs="2008")
        assert "None" not in s and "{desc}" not in s and s.strip()


def test_hs_caveat_en_box_never_prints_none_for_absent_desc():
    import silk_i18n
    # القالب ذو الوصف يُستعمَل فقط حين يوجد وصف؛ nodesc حين يغيب — كلاهما
    # بلا None. (اختيارُ المفتاح في silk_render.build_view.)
    with_desc = silk_i18n.t("hs_caveat_box", "en", tag="X", hs="2008",
                            desc="dried dates")
    assert "dried dates" in with_desc and "None" not in with_desc
