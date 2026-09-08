"""هدف الدراسة الاحترافية — الموجة ٣: لغة الزائر والعملة (البند ٣).

القاعدة: كل مصطلح قياس داخلي يصل العميل يُستبدل بجملة معنى تحفظ الرقم
(«الدرجة الموزونة … بثقة %» → قوة الفرصة وكم تحقّقنا؛ «مؤشر تركّز HHI=»
→ من يسيطر على السوق)، وكل سعر يحمل عملته ووحدته. المصطلح الداخلي يبقى
لسطح المشغّل والملحق الفني حصراً (تأكيدات e2e على HHI هناك لم تُمسّ).
"""
import importlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import pytest

from conftest import block_network

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BANNED_CLIENT = ("الدرجة الموزونة", "العمود", "غير مرصود", "بثقة")


# ── لوحة الأساس بلغة الزائر (المصدر الواحد يغذي اللوحة وdocx) ─────────────

def test_basis_i18n_keys_speak_client_language():
    import silk_i18n as I
    for key in ("pillar_col", "pillar_not_computed", "pillar_missing_lead",
                "pillar_measured", "decision_weighted_line",
                "cond_pillar_missing", "confidence_basis_line"):
        row = I.STRINGS[key] if hasattr(I, "STRINGS") else None
        if row is None:  # بنية تخزين مختلفة — عبر المترجم
            row = {lang: I.t(key, lang) for lang in ("ar", "en")}
        for lang, txt in row.items():
            for banned in _BANNED_CLIENT:
                assert banned not in txt, (key, lang, banned)
    # الرقم يبقى حيث يحمل معنى — سطر الدرجة يحمل الرقمين بصيغة معنى.
    ar = (I.STRINGS["decision_weighted_line"]["ar"]
          if hasattr(I, "STRINGS") else I.t("decision_weighted_line", "ar"))
    assert "{score}" in ar and "{conf}" in ar
    assert "قوة هذه الفرصة" in ar


def test_decision_basis_view_is_plain_on_a_real_engine_decision():
    """الباني الواحد `decision_basis` يغذي اللوحة وdocx — يُغذّى هنا بقرار
    محرك حقيقي من مدونة الجزائر (عمود مقيس + عمود غائب معاً)."""
    import silk_deep_pillars
    from silk_render import decision_basis
    blob = getattr(importlib.import_module("canonical_dza_peanut_butter"),
                   "dza_research_blob")()
    with block_network():
        dec = silk_deep_pillars.decide_for_deep(
            blob["deep_research"], product_card=None, regulatory=None)
        basis = decision_basis(dec, None, "ar")
    assert basis, "قرار المحرك لم يُنتج لوحة أساس"
    blobtxt = " ".join(
        [str(basis.get("score_line") or ""), str(basis.get("rule_line") or "")]
        + [str((r or {}).get("note") or "") for r in basis.get("pillars") or []]
        + [str(c) for c in basis.get("conditions") or []])
    for banned in ("الدرجة الموزونة", "غير مرصود", "العمود ", "بثقة "):
        assert banned not in blobtxt, banned
    assert basis.get("not_computed") == "لا نعرفه بعد"
    assert "قوة هذه الفرصة" in str(basis.get("score_line") or "")
    # الجانب الغائب يقول ما ينقصه بلغة الزائر.
    missing_notes = [r["note"] for r in basis["pillars"]
                     if r["strength_pct"] is None]
    assert missing_notes and all("ينقصنا" in n for n in missing_notes)


# ── الأرقام بجملة معنى ─────────────────────────────────────────────────────

def test_hhi_fact_becomes_meaning_sentence_keeping_the_number():
    from silk_reports import _client_readable_fact
    high = _client_readable_fact({"hhi": 7118}, "")
    assert "7118" in high and "من 10000" in high
    assert "يسيطر على معظم السوق" in high
    assert "HHI" not in high and "مؤشر" not in high
    mid = _client_readable_fact({"hhi": 3000}, "")
    assert "يسيطران" in mid
    low = _client_readable_fact({"hhi": 900}, "")
    assert "منافسين كثر" in low


def test_weighted_score_sanitized_as_backstop():
    """مدونة مخزَّنة قديمة قد تحمل المصطلح في نص — المعقّم يستبدله."""
    from silk_reports import _client_sanitize
    out = _client_sanitize("بلغت الدرجة الموزونة 66% لهذه الدراسة")
    assert "الدرجة الموزونة" not in out
    assert "قوة الفرصة في التقييم" in out and "66%" in out


# ── العملة على كل سعر ──────────────────────────────────────────────────────

def test_scenarios_table_header_carries_currency_and_unit():
    pytest.importorskip("docx")
    from docx import Document
    from silk_reports import _client_economics_section
    from conftest import docx_all_text
    import tempfile
    dr = {"economics": {
        "anchor_price": {"per_unit": 0.99, "currency": "دينار"},
        "reverse_solve": {
            "max_exw": 0.62, "unit": "لتر", "currency": "دينار",
            "headline_scenario": "متوسط",
            "formula": "x",
            "scenarios": [{"scenario": "متوسط", "freight_pct": 12.0,
                           "distributor_pct": 20.0, "retailer_pct": 25.0,
                           "max_exw": 0.62}],
            "parameters": []},
        "gaps": []}}
    doc = Document()
    _client_economics_section(doc, dr, "ar")
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as fh:
        doc.save(fh.name)
        text = docx_all_text(fh.name)
    os.unlink(fh.name)
    assert "دينار/لتر" in text          # الرأس يحمل العملة والوحدة معاً


def test_platform_components_show_unit_and_plain_confidence():
    page = io.open(os.path.join(_ROOT, "web", "platform.html"),
                   encoding="utf-8").read()
    assert "كم تحقّقنا منه" in page
    assert "c.unit" in page              # الوحدة كانت في الحمولة وتُتجاهل


# ── فحص المفردات التحذيري ─────────────────────────────────────────────────

def test_client_view_vocabulary_fires_on_internal_terms():
    from silk_quality_gate import _check_client_view_vocabulary
    view = {"decision": {"basis": {
        "score_line": "الدرجة الموزونة لهذه الدراسة 66% بثقة 80%.",
        "pillars": [], "conditions": []}},
        "deep_research": {"limits": []}, "brief": []}
    found = _check_client_view_vocabulary(view)
    assert found and found[0]["check"] == "client_view_vocabulary"
    assert found[0]["repairable"] is True
    assert "الدرجة الموزونة" in found[0]["note"]


def test_client_view_vocabulary_silent_on_all_ten_blobs():
    """العمومية (أمر الهدف): الفحص صامت على المدونات العشر بعد إعادة
    الصياغة — منتجات وأسواق مختلفة لا حالة حليب واحدة."""
    from silk_render import build_view
    from silk_quality_gate import _check_client_view_vocabulary
    from gen_verdict_baseline import CANONICAL_BLOBS, load_blob
    noisy = {}
    with block_network():
        for key in sorted(CANONICAL_BLOBS):
            view = build_view(load_blob(key))
            got = _check_client_view_vocabulary(view)
            if got:
                noisy[key] = got[0]["note"]
    assert not noisy, noisy


def test_client_view_vocabulary_not_blocking():
    from silk_quality_gate import (FAIL_TRIGGER_CHECKS,
                                   _REGRESSION_GUARD_FIRED)
    assert "client_view_vocabulary" not in FAIL_TRIGGER_CHECKS
    assert "client_view_vocabulary" not in _REGRESSION_GUARD_FIRED
