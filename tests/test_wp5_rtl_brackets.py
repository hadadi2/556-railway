"""WP-5 (برنامج إصلاح جودة التقارير) — انعكاس الأقواس في PDF العربي.

بلاغ التدقيق (2026-07-22): الأقواس ظهرت معكوسة «) ... (» في الـPDF المُسلَّم
حول المقاطع اللاتينية/الرقمية داخل الفقرات العربية — `_finalize_rtl` كانت
تضبط bidi على مستوى الفقرة/الـrun لكن خط الأنابيب لا يحقن أي عزل اتجاه
(RLM) حول المقاطع مختلطة الاتجاه قبل تحويل LibreOffice headless. الأقفال:

1. `_bidi_isolate_brackets`: RLM بعد القوس الافتتاحي وقبل الختامي لمقطع
   لاتيني/رقمي في سياق عربي — بلا ازدواج، وبلا مساس بنصٍّ غير عربي.
2. تُطبَّق داخل `_finalize_rtl` فيحملها docx الفعلي المُصدَّر.
3. `count_suspicious_brackets` + فحص `_pdf_bracket_check` في `docx_to_pdf`:
   فوق العتبة يفشل التصدير بصوت عالٍ (لا PDF معكوس الأقواس يُسلَّم).

Run: python3 -m pytest tests/test_wp5_rtl_brackets.py -q
"""
from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

RLM = "‏"


def test_rlm_injected_after_opening_and_before_closing_bracket():
    from silk_reports import _bidi_isolate_brackets
    out = _bidi_isolate_brackets("الواردات (UN Comtrade) في نمو")
    assert f"({RLM}UN Comtrade{RLM})" in out


def test_rlm_injection_is_idempotent():
    from silk_reports import _bidi_isolate_brackets
    once = _bidi_isolate_brackets("متوسط السعر (6 USD/kg) مؤشر")
    assert _bidi_isolate_brackets(once) == once


def test_non_arabic_text_and_arabic_only_parentheticals_untouched():
    from silk_reports import _bidi_isolate_brackets
    latin = "See (UN Comtrade) for details"
    assert _bidi_isolate_brackets(latin) == latin       # لا سياق عربي
    arabic = "الواردات (مرتفعة) هذا العام"
    assert _bidi_isolate_brackets(arabic) == arabic     # لا مقطع لاتيني/رقمي


def test_finalize_rtl_applies_bracket_isolation_to_real_docx(tmp_path):
    pytest.importorskip("docx")
    from docx import Document
    from silk_reports import _finalize_rtl
    doc = Document()
    doc.add_paragraph("مؤشر التركز (HHI 2500) مرتفع نسبياً")
    _finalize_rtl(doc)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert f"({RLM}HHI 2500{RLM})" in text


def test_count_suspicious_brackets_detects_mirroring_signature():
    """الدالّةُ نفسُها لم تتغيّر — لكنّها صارت **تشخيصيةً** لا حَكَماً.

    تدقيق 2026-08-27 (W-01/W-04) قاس أنّ عدَّها يرتفع على مستندٍ سليم وينخفض
    على مقلوب، فأُخرِجت من البوّابة. تبقى مقفولةً هنا لأنّها تقيس شيئاً حقيقياً
    (جودةَ **طبقة النصّ** المستخرَجة) وتُقرَأ في `tools/rtl_calibration`."""
    from silk_reports import count_suspicious_brackets
    mirrored = "التقرير يظهر ) قيمة مقلوبة (\nوسطر آخر معلق (\nونهاية ("
    assert count_suspicious_brackets(mirrored) == 3
    clean = "الواردات (UN Comtrade) مستقرة (HHI 2500) تماماً."
    assert count_suspicious_brackets(clean) == 0


def test_count_suspicious_brackets_is_not_wired_into_the_gate():
    """قفلُ الانحدار: البوّابةُ لا تعود إلى المقياس المُعاكِس الإشارة.

    إعادةُ ربطه بـ`_pdf_bracket_check` تُعيد حرفياً حادثة 2026-08-27: كلُّ
    تصديرِ PDF عربيٍّ يرتدّ 503 على بيئةٍ فيها pymupdf."""
    import os as _os
    src = open(_os.path.join(_os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))), "silk_reports.py"), encoding="utf-8").read()
    body = src.split("def _pdf_bracket_check(")[1].split("\ndef ")[0]
    assert "count_suspicious_brackets" not in body, \
        "المقياسُ المُعاكِسُ الإشارة عاد إلى البوّابة"
    assert "bracket_orientation_counts" in body


def test_is_arabic_majority_excludes_latin_and_numeric_rows():
    """الصفُّ لاتينيُّ الأغلبية أساسُه LTR فترتيبُ `()` فيه هو الصحيح — لا
    يُقاس عليه اتجاهٌ إطلاقاً، وإلا صار كلُّ سطرِ مصدرٍ إنذاراً كاذباً."""
    from silk_reports import is_arabic_majority
    assert is_arabic_majority("الواردات مستقرة")
    assert is_arabic_majority("الواردات (UN) مستقرة هذا العام")
    assert not is_arabic_majority("UN Comtrade (2024)")
    assert not is_arabic_majority("080410")
    assert not is_arabic_majority("")


def test_classify_bracket_sequence_reads_rtl_orientation():
    """في سياق RTL يُصيَّر القوسُ الافتتاحيُّ المنطقيّ على **يمين** مقطعه،
    فترتيبُ المحارف على المحور x (يسار⇐يمين) يكون `)(` للسليم و`()` للمقلوب."""
    from silk_reports import classify_bracket_sequence as C
    assert C(")(", "(", ")") == (1, 0)          # سليم
    assert C("()", "(", ")") == (0, 1)          # مقلوب
    assert C(")()(", "(", ")") == (2, 0)        # مقطعان سليمان متتاليان
    assert C("()()", "(", ")") == (0, 2)        # مقطعان مقلوبان
    assert C("][", "[", "]") == (1, 0)          # نفسُ العقد للأقواس المربّعة


def test_classify_ignores_unbalanced_row_no_false_alarm():
    """قوسٌ يتيمٌ خلّفه لفُّ السطر كان يزيح كلَّ الأزواج التالية فيقلبَ حكمَها.

    قِيس مباشرةً على تقرير العميل الحقيقي: صفٌّ واحدٌ بتسلسل `()(` (زوجٌ سليم
    + قوسٌ افتتاحيٌّ تشظّى إلى السطر التالي) كان يُحسَب زوجاً **مقلوباً**.
    العقدُ الآن: لا حكمَ حيث لا توازن."""
    from silk_reports import classify_bracket_sequence as C
    assert C("()(", "(", ")") == (0, 0)
    assert C("(", "(", ")") == (0, 0)
    assert C(")", "(", ")") == (0, 0)


def _fake_fitz(rows):
    """fitz مزيّفة: `rows` قائمةُ صفوفٍ، كلُّ صفٍّ [(x, char), ...] على خطّ
    أساسٍ واحد — تُعيد بنيةَ `rawdict` التي يقرؤها المقياسُ الحقيقي."""
    class _Page:
        def get_text(self, kind=None):
            spans = []
            for i, row in enumerate(rows):
                spans.append({
                    "origin": (0.0, 100.0 + 20 * i),
                    "chars": [{"bbox": (x, 0, x + 5, 10), "c": c}
                              for x, c in row],
                })
            return {"blocks": [{"lines": [{"spans": spans}]}]}

    class _Pdf:
        def __enter__(self):
            return [_Page()]

        def __exit__(self, *a):
            return False

    return types.SimpleNamespace(open=lambda p: _Pdf())


def test_pdf_bracket_check_fails_export_above_threshold(monkeypatch):
    """البوّابةُ تُفشِل التصديرَ على انقلابٍ **مُثبَتٍ هندسياً** (لا تسليم).

    الصفُّ عربيُّ الأغلبية وترتيبُ أقواسه على المحور x هو `()` — أي أنّ القوس
    الافتتاحيّ صُيِّر على **يسار** مقطعه: انقلابُ اتجاهٍ حقيقيّ."""
    import silk_reports as R
    inverted = [[(10.0, "("), (20.0, "م"), (30.0, "ر"), (40.0, ")")]]
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(inverted))
    with pytest.raises(RuntimeError, match="اتجاه الأقواس"):
        R._pdf_bracket_check("/tmp/any.pdf")
    # الترتيبُ السليمُ في سياق RTL — يمرّ بصمت.
    good = [[(10.0, ")"), (20.0, "م"), (30.0, "ر"), (40.0, "(")]]
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(good))
    R._pdf_bracket_check("/tmp/any.pdf")


def test_gate_default_threshold_is_zero_inverted_pairs(monkeypatch):
    """العتبةُ الافتراضيةُ صفر: زوجٌ مقلوبٌ **واحد** يكفي للرفض.

    كانت ٣ على المقياس القديم (الذي كان يعدّ ضجيجَ استخراج). المقياسُ الجديد
    لا يُنتِج ضجيجاً — فأيُّ هامشٍ يُتسامَح معه يعني تسليمَ مستندٍ مقلوب."""
    import silk_reports as R
    monkeypatch.delenv("SILK_PDF_BRACKET_FAIL_MAX", raising=False)
    one = [[(10.0, "("), (20.0, "م"), (30.0, ")")]]
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(one))
    with pytest.raises(RuntimeError, match="1 زوجاً"):
        R._pdf_bracket_check("/tmp/any.pdf")


def test_latin_majority_row_is_never_judged(monkeypatch):
    """سطرٌ لاتينيٌّ أساسُه LTR: `()` هو الترتيبُ الصحيح فيه — لا يُحكَم عليه."""
    import silk_reports as R
    latin = [[(10.0, "("), (20.0, "U"), (30.0, "N"), (40.0, ")")]]
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(latin))
    R._pdf_bracket_check("/tmp/any.pdf")          # لا استثناء


def test_gate_skips_loudly_without_pymupdf(monkeypatch):
    """بلا fitz: تخطٍّ صامتُ الأثر لا ادعاءَ فحصٍ لم يقع — والحزمةُ صارت
    تبعيةَ إنتاج في requirements.txt كي لا يقع هذا الفرعُ على النشر."""
    import builtins
    import silk_reports as R
    monkeypatch.delitem(sys.modules, "fitz", raising=False)
    real_import = builtins.__import__

    def _no_fitz(name, *a, **kw):
        if name == "fitz":
            raise ImportError("no fitz")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _no_fitz)
    # **None لا (0,0,0)**: العقدُ المؤسِّس — قياسٌ لم يقع لا يُقدَّم نتيجةً
    # نظيفة. صفرٌ هنا كان يُقرَأ «فُحِص فكان سليماً».
    assert R.bracket_orientation_counts("/tmp/any.pdf") is None
    R._pdf_bracket_check("/tmp/any.pdf")          # لا استثناء


def test_pymupdf_is_a_production_dependency():
    """الدرس ١٠٤ (حارسٌ خامد): البوّابةُ بلا pymupdf تتخطّى نفسَها بصمت على
    Railway. شحنُها في requirements.txt هو ما يجعل الحارسَ موجوداً فعلاً."""
    import os as _os
    root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    req = open(_os.path.join(root, "requirements.txt"), encoding="utf-8").read()
    assert "pymupdf==" in req, "pymupdf ليست تبعيةَ إنتاج — الحارسُ خامد"


def test_docx_to_pdf_wires_the_bracket_check():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_reports.py"),
        encoding="utf-8").read()
    body = src.split("def docx_to_pdf(")[1].split("\ndef ")[0]
    assert "_pdf_bracket_check(" in body


def test_calibration_tool_carries_bracket_fixtures():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "rtl_calibration.py"),
        encoding="utf-8").read()
    assert "_BRACKET_LINES" in src
    assert "build_bracket_fixture" in src
    assert "bracket_suspicious_count" in src
