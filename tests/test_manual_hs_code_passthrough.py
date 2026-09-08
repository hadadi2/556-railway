"""الرمز الجمركي المكتوب يدوياً — عام لكل الفصول (بلاغ 2026-08-19).

الحادثة: مشغّل يكتب 040120 بنفسه (حليب 1–6٪ دسم) فتردّه بوّابة تمايز المحور
٤٢٢ «اختر البند المطابق» — وهو قد اختاره فعلاً؛ وفي مسارٍ آخر يُستبدَل رمزُه
صامتاً بما يقترحه المجسّ. القاعدتان العامّتان:

  (١) رمزٌ يكتبه المستخدم وهو **أحد مرشّحي المحور ذاتهم** = إجابةُ السؤال.
  (٢) المجسّ **يقترح ولا يستبدل** رمزاً كتبه المستخدم.

ورمزٌ خارج القائمة يبقى مُبوَّباً (حارس LESSONS ٧٩ لا يُنقَض). هرمتي.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_hand_typed_code_inside_the_axis_list_is_not_re_gated():
    import silk_hs_confirm as C
    # «حليب» + 040120: ترويسة تنقسم بمحور نسبة الدهن ⇒ البوّابة كانت تردّ 422.
    blocked_blind = C.preflight_block("حليب", "040120", user_supplied=False)
    blocked_typed = C.preflight_block("حليب", "040120", user_supplied=True)
    if blocked_blind is None:
        import pytest
        pytest.skip("بوّابة المحور لا تُطلَق لهذه البذرة — لا شيء يُقاس هنا")
    assert blocked_blind.get("error") == "hs_axis_disambiguation_needed"
    assert blocked_typed is None, (
        "رمزٌ كتبه المشغّل وهو أحد المرشّحين ما زال يُردّ — الحلقة مغلقة عليه")


def test_a_typed_code_outside_the_candidate_list_stays_gated():
    import silk_hs_confirm as C
    # رمزٌ من فصلٍ آخر تماماً لمنتج «حليب» — لا يُؤكَّد لمجرّد كتابته.
    out = C.preflight_block("حليب", "870323", user_supplied=True)
    assert out is None or out.get("error"), "قناة تأكيد عمياء لأي رمز مكتوب"
    if out:
        assert out.get("error") in ("hs_axis_disambiguation_needed",
                                    "hs_confirmation_failed",
                                    "hs_confidence_too_low")


def test_code_in_candidates_matches_on_normalized_hs6_only():
    from silk_hs_confirm import _code_in_candidates
    cands = [{"hs6": "040120"}, {"hs6": "040110"}]
    assert _code_in_candidates("040120", cands)
    assert _code_in_candidates("0401.20", cands)      # منقّطاً
    assert _code_in_candidates(" 040120 ", cands)
    assert not _code_in_candidates("040150", cands)
    assert not _code_in_candidates("0401", cands)     # أقصر من HS6 = لا تطابق
    assert not _code_in_candidates(None, cands)


def test_probe_never_silently_replaces_a_user_typed_code(monkeypatch):
    import silk_hs_confirm as C
    monkeypatch.setattr(C, "preflight_block",
                        lambda *a, **k: {"error": "hs_axis_disambiguation_needed",
                                         "candidates": [{"hs6": "040110"}],
                                         "hs_confirmation": {}})
    monkeypatch.setattr(C, "resolve_or_probe",
                        lambda *a, **k: {"hs6": "040110", "resolved_from": "web"})
    code, prov, block = C.preflight_resolve("حليب", "040120",
                                            user_supplied=True)
    assert code == "040120", "رمز المستخدم استُبدل صامتاً بمقترح المجسّ"
    assert prov is None
    # بلا رمزٍ من المستخدم (حسمٌ آليّ) يبقى السلوك القديم حرفياً.
    code2, prov2, _ = C.preflight_resolve("حليب", "040120",
                                          user_supplied=False)
    assert code2 == "040110" and prov2 is not None


def test_explicit_code_path_does_not_consult_the_name_keyed_cache(monkeypatch):
    """ذاكرة التصنيف مفتاحها اسم المنتج — دراسة 040110 سابقة لا تلوّث 040120،
    لأن الرمز الصريح المطابق للمرشّحين لا يصل مسار المجسّ/الذاكرة أصلاً."""
    import silk_hs_confirm as C
    hits = {"n": 0}

    def _boom(*a, **k):
        hits["n"] += 1
        return {"hs6": "040110", "resolved_from": "web"}
    monkeypatch.setattr(C, "resolve_or_probe", _boom)
    C.preflight_resolve("حليب", "040120", user_supplied=True)
    assert hits["n"] == 0, "الرمز الصريح استشار المجسّ/الذاكرة"


def test_all_api_entry_points_declare_user_supplied():
    # الدرس ١٢٠: الصيغة صارت `_hs_user_supplied(req)` — تميّز رمزَ الكتالوج
    # المُعاد (hs_source="catalog") عن اختيار الإنسان الحاضر؛ العائلة نفسها.
    src = open(os.path.join(_ROOT, "api.py"), encoding="utf-8").read()
    # موجةُ خطّ التصنيف أضافت نقطةَ اختناقٍ رابعة تُصرّح بالمصدر نفسه
    # (`_classify_product_hs` — تصنيفٌ قبل أيّ بوّابة). العددُ الصلب كان
    # يُحمِّر على **إضافة** حارسٍ لا على غيابه، فالقفلُ صار على الأرضيّة.
    assert src.count("user_supplied=_hs_user_supplied(req)") >= 3, (
        "أحد مسارات الدخول (/analyze، /deepen، /research) لا يُصرّح "
        "بمصدر الرمز — الإصلاح على مسارٍ واحد ممنوع (الدرسان ٣٥/٣٧)")
    assert "def _hs_user_supplied" in src
    # وكلُّ مسارٍ ينفق يمرّ بخطّ التصنيف الواحد قبل أيّ بوّابة أو حجز.
    assert src.count("_classify_product_hs(") >= 3, (
        "مسارُ إنفاقٍ لا يمرّ بخطّ التصنيف الواحد")


def test_platform_typed_code_reaches_the_body_as_user_supplied():
    """مسار المنصّة يبني ResearchRequest بالرمز نفسه ⇒ يرث الإصلاح تلقائياً —
    ومنذ الدرس ١٢٠ يمرّر مصدرَ الرمز (`hs_source`) معه فيُميَّز الكتالوجيّ."""
    src = open(os.path.join(_ROOT, "api.py"), encoding="utf-8").read()
    i = src.find("def _platform_deep_run")
    assert i > 0
    # R5 (2026-09-05): نافذةُ ٢٤٠٠ حرفاً كانت تحصر الدالّة قبل تعليقات R2/R4 —
    # الجسمُ كاملاً حتى التعريف التالي بنفس المسافة البادئة.
    _end = src.find("\n    def ", i + 10)
    body = src[i:_end if _end > 0 else i + 6000]
    assert "hs_code=(hs_code or None)" in body
    assert "hs_source=(hs_source or None)" in body
    # R2 أضاف `on_allocated=` إلى النداء — الإبرةُ على بادئة النداء لا على قوسٍ مغلق.
    assert "_research_impl(req" in body


def test_lessons79_guard_still_green():
    """الحارس القائم: رمزٌ مكتوب خارج القائمة لا يُؤكَّد تلقائياً."""
    p = os.path.join(_ROOT, "tests/test_platform_deep_real_path.py")
    src = open(p, encoding="utf-8").read()
    assert "def test_a_hand_typed_code_outside_the_list_is_not_auto_confirmed" in src
