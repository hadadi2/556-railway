"""هدف الدراسة الاحترافية — الموجة ١: الوحدة تتبع المنتج (عائلة الدرس 84).

الحادثة المؤسِّسة (دراسة #14، حليب×الأردن): «المراعي كامل الدسم | 1 لتر |
0.99 دينار | غير محسوب — العبوة باللتر وتحويل الكثافة إلى كجم غير متاح» —
سعرٌ و«غير محسوب» في الصف نفسه، والكثافة ثابت معروف مسجّل. القواعد المقفولة
هنا: وحدة العرض وحدةُ السوق (سوائل=لتر)؛ لا فجوة لتحويلٍ ثابتُه مسجّل؛
فحص `unit_conversion_refusal` حاجز؛ silk_render لا يملك جدول تحويلٍ موازياً.
"""
import ast
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from conftest import block_network


# ── سلطة وحدة السوق ─────────────────────────────────────────────────────────

def test_market_unit_liquids_are_litre():
    from silk_economics import market_unit
    for name in ("حليب", "لبن", "عصير", "ماء", "زيت زيتون", "milk", "juice"):
        code, label = market_unit(name)
        assert code == "litre" and label == "لتر", name


def test_market_unit_solids_and_unknown_default_kg():
    from silk_economics import market_unit
    for name in ("تمور", "عسل", "زبدة الفول السوداني", "منتج مجهول", ""):
        code, label = market_unit(name)
        assert code == "kg" and label == "كجم", name


def test_every_litre_family_has_a_registered_density():
    """ميتا: لا عائلة لترية بلا ثابت كثافة مسجّل — وإلا صار العرض باللتر
    وعداً بلا قدرة تحويل (نفس عائلة «الحارس الذي لا يمكن أن يُطلق»)."""
    from silk_economics import CONVERSION_REGISTRY, MARKET_UNIT_REGISTRY
    litre_families = {k for k, (code, _l) in MARKET_UNIT_REGISTRY.items()
                      if code == "litre"}
    densities = {k[2] for k in CONVERSION_REGISTRY
                 if {k[0], k[1]} == {"litre", "kg"}}
    assert litre_families <= densities, litre_families - densities


def test_conversion_never_invented_for_unknown_family():
    """عقد عدم الاختلاق: فئة بلا ثابت ⇒ (None، ملاحظة تسمّي الكثافة)."""
    from silk_economics import convert_amount
    val, note = convert_amount(1.0, "litre", "kg", "منتج مجهول")
    assert val is None
    assert "الكثافة" in note


# ── أساس الحل العكسي = وحدة السوق ───────────────────────────────────────────

def _milk_dr(price_note: str, value=0.99) -> dict:
    """بعثات تركيبية: سعرُ رفٍّ معلن بعبوة لترية + قيمة حدودية للمقارنة."""
    return {"missions": {
        "pricing_scout": {"findings": [
            {"value": value, "note": price_note,
             "source": "بعثة الأسعار", "confidence": 0.8}]},
        "trade_flow": {"findings": [
            {"value": 1.10, "note": "متوسط سعر استيراد (القيمة ÷ الوزن "
                                    "الصافي بالكجم) دولار/كجم",
             "source": "UN Comtrade", "confidence": 0.9}]},
    }}


_MILK_NOTE = "سعر رف في السوبرماركت: 0.99 دينار لعبوة 1 لتر"


def test_reverse_solve_basis_is_litre_for_milk():
    from silk_economics import economics_view
    with block_network():
        eco = economics_view(_milk_dr(_MILK_NOTE), category="حليب")
    rs = eco.get("reverse_solve")
    assert eco["market_unit"] == {"code": "litre", "label_ar": "لتر"}
    assert rs is not None, eco.get("gaps")
    assert rs["unit"] == "لتر"


def test_reverse_solve_basis_stays_kg_for_solids():
    from silk_economics import economics_view
    note = "سعر رف في السوبرماركت: 3 دينار لعبوة 500 غ"
    with block_network():
        eco = economics_view(
            {"missions": {"pricing_scout": {"findings": [
                {"value": 3.0, "note": note, "source": "بعثة الأسعار",
                 "confidence": 0.8}]}}},
            category="تمور")
    rs = eco.get("reverse_solve")
    assert rs is not None, eco.get("gaps")
    assert rs["unit"] == "كجم"


def test_no_conversion_gap_declared_for_registered_density():
    """جوهر البند ١: عبوة لترية لفئة الحليب لا تولّد أي فجوة تحويل —
    per_kg وper_litre كلاهما محسوب بثابت السجل."""
    from silk_economics import normalize_price
    np_ = normalize_price(0.99, currency="دينار", category="حليب",
                          pack_litre=1.0)
    assert np_.per_litre == 0.99
    assert np_.per_kg is not None          # 0.99 ÷ 1.03 — محسوب لا محجوب
    assert not [g for g in np_.gaps if "كثافة" in g or "تحويل" in g]


def test_pricing_contradiction_alive_on_litre_basis():
    """فحص التناقض (البند 6 القائم) يبقى حياً حين يُعرض الأساس باللتر —
    المقارنة الحدودية تُحوَّل داخلياً بثابت الكثافة لا تُعطَّل."""
    from silk_economics import economics_view
    # سعر رف متدنٍّ جداً بالدولار ⇒ أقصى EXW أدنى بكثير من سعر الحدود.
    note = "سعر رف في السوبرماركت: 0.30 $ لعبوة 1 لتر"
    with block_network():
        eco = economics_view(_milk_dr(note, value=0.30), category="حليب")
    rs = eco.get("reverse_solve")
    assert rs is not None and rs["unit"] == "لتر"
    pc = eco.get("pricing_contradiction")
    assert pc is not None
    assert pc["reference_import_price_usd_kg"] == 1.10


# ── فحص البوابة الحاجز ─────────────────────────────────────────────────────

_STUDY14_SENTENCE = ("السعر التجزئي 0.99 دينار للعبوة، والسعر للكيلوغرام "
                     "غير محسوب — العبوة باللتر وتحويل الكثافة إلى كجم "
                     "غير متاح.")


def test_gate_fires_on_study14_family_text_for_milk():
    from silk_quality_gate import _check_unit_conversion_refusal
    found = _check_unit_conversion_refusal(_STUDY14_SENTENCE, "حليب")
    assert found and found[0]["check"] == "unit_conversion_refusal"
    assert found[0]["repairable"] is False


def test_gate_silent_for_category_without_constant():
    """تمور بلا ثابت كثافة — فجوة التحويل هناك مشروعة، الفحص صامت عمداً."""
    from silk_quality_gate import _check_unit_conversion_refusal
    assert _check_unit_conversion_refusal(_STUDY14_SENTENCE, "تمور") == []


def test_gate_silent_on_clean_text_and_legitimate_pack_gap():
    from silk_quality_gate import _check_unit_conversion_refusal
    clean = "استورد الأردن 6.95 مليون دولار سنة 2023 والسعر 0.99 دينار للتر."
    pack_gap = ("حجم العبوة (كجم أو لتر) غير متاح — السعر/كجم والسعر/لتر "
                "غير محسوبَين، لا تخمين")
    assert _check_unit_conversion_refusal(clean, "حليب") == []
    # فجوة حجم عبوةٍ مشروعة تذكر لتر+كجم لكن بلا «تحويل/كثافة» — لا إطلاق.
    assert _check_unit_conversion_refusal(pack_gap, "حليب") == []


def test_gate_fires_on_english_density_refusal():
    from silk_quality_gate import _check_unit_conversion_refusal
    en = ("Price per kg: not computed - the pack is per litre and the "
          "density conversion is unavailable.")
    assert _check_unit_conversion_refusal(en, "milk")


def test_unit_conversion_refusal_is_a_fail_trigger():
    from silk_quality_gate import FAIL_TRIGGER_CHECKS
    assert "unit_conversion_refusal" in FAIL_TRIGGER_CHECKS


def test_gate_wired_into_run_quality_gate():
    """الفحص موصول فعلاً: view كامل بنص #14 يفشل البوابة FAIL."""
    import silk_quality_gate as qg
    view = {"product": "حليب",
            "deep_research": {"report": {"text": _STUDY14_SENTENCE},
                              "missions": {}}}
    with block_network():
        out = qg.run_quality_gate(view)
    names = {f["check"] for f in out["findings"]}
    assert "unit_conversion_refusal" in names
    assert out["verdict"] == "FAIL"


# ── لا مسار تحويل موازٍ في طبقة العرض ──────────────────────────────────────

def test_render_owns_no_conversion_table():
    """قاعدة العرض الواحد: silk_render يكشف حضور الوحدة (regex) ولا يملك
    ثوابت تحويلٍ خاصة — الكثافة تعيش في silk_economics حصراً."""
    import silk_render
    src = inspect.getsource(silk_render)
    assert "CONVERSION_REGISTRY" not in src.replace(
        "from silk_economics import", "")  # لا تعريف ولا نسخة محلية
    assert "1.03" not in src               # لا ثابت كثافة مزروع
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            assert node.id != "CONVERSION_REGISTRY"


def test_writer_prompt_forbids_naming_registered_conversion_as_gap():
    """الدرس 156: البرومبت لا يفرض ما تحجبه البوابة — سطر الفجوة القسري
    يمنع تسمية التحويل/الكثافة مدخلاً ناقصاً (العربية والإنجليزية)."""
    import silk_ai_judge
    src = inspect.getsource(silk_ai_judge.deep_report)
    assert "ممنوع تسمية تحويل اللتر إلى الكيلوغرام" in src
    assert "Never name a litre-to-kg" in src


# ── أداة التدقيق ────────────────────────────────────────────────────────────

def test_audit_tool_flags_study14_blob_shape():
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    from audit_unit_gaps import audit_blob, offending_sentences
    blob = {"product": "حليب",
            "deep_research": {"report": {"text": _STUDY14_SENTENCE},
                              "missions": {}, "economics": {}}}
    hit = audit_blob("x", blob)
    assert hit and hit["hits"]
    assert offending_sentences("نص سليم بلا فجوات") == []
    # فئة بلا ثابت ⇒ لا إصابة (نفس عمياء الفحص، معلنة).
    assert audit_blob("y", {"product": "تمور",
                            "deep_research": blob["deep_research"]}) is None
