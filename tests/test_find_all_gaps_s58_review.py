"""إصلاحات مراجعة §58 الذاتية على فرق find all gaps الكامل (2026-08-27).

/code-review على origin/main...HEAD كشف ملاحظتين عاليتين موجّهتين للعميل +
ملاحظة متانة، تعالجها هذه الأقفال (test-first):
- HHI خامٌ كسريّ (0–1) يُعرض للعميل بلا تحجيم فينقلب المركّز «موزّعاً».
- «حليب مجفف» (صلب) يُطابِق «حليب» فيُسعَّر باللتر بكثافة سائلٍ خاطئة.
- `derive_hypotheses` يرفع IndexError على منتجٍ = «ال»/فراغ.

Hermetic؛ لا شبكة.
"""
from __future__ import annotations


# ── HHI الكسريّ يُحجَّم قبل عرضه للعميل ────────────────────────────────────

def test_client_fact_scales_fractional_hhi_so_concentrated_reads_concentrated():
    from silk_reports import _client_readable_fact
    # 0.71 = HHI 7100 (مركّز جداً) — يجب ألا يُقرأ «موزّع».
    out = _client_readable_fact({"hhi": 0.71}, "تركّز")
    assert "موزّع" not in out
    assert "يسيطر" in out and "7100" in out


def test_client_fact_full_scale_hhi_unchanged():
    from silk_reports import _client_readable_fact
    out = _client_readable_fact({"hhi": 7118}, "تركّز")
    assert "7118" in out and "يسيطر" in out


def test_client_fact_low_concentration_still_distributed():
    from silk_reports import _client_readable_fact
    out = _client_readable_fact({"hhi": 0.05}, "تركّز")   # 500 — موزّع
    assert "موزّع" in out


# ── الشكل الصلب لفئةٍ سائلة يُسعَّر بالكيلوغرام ────────────────────────────

def test_powdered_milk_is_priced_by_kg_not_litre():
    from silk_economics import market_unit
    assert market_unit("حليب مجفف") == ("kg", "كجم")
    assert market_unit("milk powder") == ("kg", "كجم")
    assert market_unit("بودرة الحليب") == ("kg", "كجم")


def test_liquid_milk_stays_litre():
    from silk_economics import market_unit
    assert market_unit("حليب") == ("litre", "لتر")
    assert market_unit("حليب طازج") == ("litre", "لتر")


def test_solid_needle_does_not_misclassify_a_liquid_with_bits():
    """مراجعة ثانية (find all gaps): «حبيبات»/«granul» أُسقِطتا — سائلٌ باسمٍ
    فيه كلمة صلبة يبقى لتراً."""
    from silk_economics import market_unit
    assert market_unit("عصير بحبيبات") == ("litre", "لتر")
    assert market_unit("عصير برتقال") == ("litre", "لتر")


# ── derive_hypotheses لا يرفع على منتجٍ منحطّ ─────────────────────────────

def test_inference_handles_article_only_product_without_raising():
    import silk_inference
    for p in ("ال", "   ", ""):
        # لا استثناء (كان IndexError يُبتلَع بحارسٍ عام). دالةٌ بوسيطٍ واحد.
        silk_inference.derive_hypotheses({"missions": {}, "product": p})
        assert silk_inference._p_wrong_heading({"product": p}) is None
