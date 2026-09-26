"""البند ٢٨٤ — حارسُ اتجاه الأقواس يرفض تقاريرَ سليمة، والواجهةُ تسمّيه «معطَّل».

بلاغ المالك (2026-09-26): «توليد ملف PDF معطَّل على الخادم حالياً — أبلغ
الإدارة» يتكرّر. الدليلُ الإنتاجيّ (Railway، الدراسة ٧): LibreOffice حوّل
المستندَ بنجاح ثمّ رُفِض الـPDF في فحص الأقواس (WP-5، عتبة صفر)، والمسارُ
يحوّل **أيَّ** RuntimeError إلى `pdf_unavailable` فتعرض الصفحةُ «معطَّل».

سببان في المقياس القديم (يُجمِّع المحارفَ على خطّ الأساس عبر الصفحة كلّها
ثمّ يحكم على كلّ صفٍّ وحده) — كلاهما أُعيد إنتاجه على ٤١ PDF حقيقيّ الشكل:
١) خليّتا جدولٍ متجاورتان على خطّ أساسٍ واحد: `)` تُغلق زوجاً من سطرٍ سابق في
   خليّة، و`(` تفتح زوجاً يُكمَل في السطر التالي في خليّةٍ أخرى — تُقرآن `()`.
٢) نصفا زوجين تشظّيا عند لفّ السطر في الفقرة نفسِها يتوازنان فيُقرآن زوجاً مقلوباً.
الإصلاح: الأقواسُ تُقرَن **بترتيب القراءة عبر المستند** (أعلى⇐أسفل، ويمين⇐يسار
داخل مقطعٍ عربيّ) — مقطعٌ لكلّ (كتلة fitz، خطّ أساس) كي تنفصل الخلايا. والفشلُ
برمزٍ يسمّيه: `pdf_unavailable` (المحرّك غائب) / `pdf_failed` / `pdf_rejected`.

Lock tests, written before the fix: the bracket gate must not reject a
correctly rendered report, must still catch a genuinely inverted build, and a
gate rejection must never reach the factory as «PDF disabled on the server».
"""
from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AR = "مرحبا بالسوق"          # حروفٌ عربية تجعل المقطعَ عربيَّ الأغلبية


def _seg(y, block, items):
    """مقطعٌ على خطّ أساس `y` في كتلة `block`: items = [(x, "نص")...] —
    كلُّ نصٍّ يُفرَد محارفَ متجاورةً ابتداءً من x."""
    chars = []
    for x, text in items:
        for i, c in enumerate(text):
            chars.append((x + 4 * i, c))
    return (y, block, chars)


def _fake_fitz(pages):
    """fitz مزيّفة متعدّدةُ الصفحات والكتل: pages = [[seg, ...], ...]."""
    class _Page:
        def __init__(self, segs):
            self.segs = segs

        def get_text(self, kind=None):
            blocks = {}
            for y, block, chars in self.segs:
                blocks.setdefault(block, []).append({"spans": [{
                    "origin": (0.0, y),
                    "chars": [{"bbox": (x, y - 8, x + 4, y), "c": c}
                              for x, c in chars]}]})
            return {"blocks": [{"lines": blocks[b]} for b in sorted(blocks)]}

    class _Pdf:
        def __enter__(self):
            return [_Page(p) for p in pages]

        def __exit__(self, *a):
            return False

    return types.SimpleNamespace(open=lambda p: _Pdf())


def _measure(monkeypatch, pages):
    import silk_reports as R
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(pages))
    return R.bracket_orientation_counts("/tmp/any.pdf")


def test_a_pair_split_across_table_cells_is_not_an_inverted_pair(monkeypatch):
    """الحالةُ الإنتاجية (صفّ «أقصى خسارة» في النموذج المالي): الخليّةُ اليمنى
    تُغلق على هذا السطر زوجاً فتحته في السطر السابق، واليسرى تفتح زوجاً يُغلق في
    السطر التالي. على خطّ الأساس المشترك يقرأ المقياسُ القديم `()` مقلوباً."""
    pages = [[
        _seg(100, 0, [(300, AR), (396, "(")]),                   # الخليّة اليمنى: فتح
        _seg(120, 0, [(300, ")"), (310, AR)]),                   # ... وإغلاقٌ هنا
        _seg(120, 1, [(150, AR), (285, "(")]),                   # الخليّة اليسرى: فتح
        _seg(140, 1, [(150, ")"), (160, AR)]),                   # ... وإغلاقٌ هنا
    ]]
    ok, inverted, _ = _measure(monkeypatch, pages)
    assert inverted == 0
    assert ok == 2


def test_orphan_halves_of_wrapped_lines_are_not_an_inverted_pair(monkeypatch):
    """النمطُ `()()` (فقرة «الأسعار مَعلَمات معلنة»): إغلاقٌ يتيمٌ من السطر
    السابق يمينَ السطر، وزوجٌ سليمٌ في الوسط، وفتحٌ يتيمٌ يُكمَل في السطر التالي
    يسارَه — لا انقلابَ فيه."""
    pages = [[
        _seg(100, 0, [(100, "("), (110, AR)]),
        _seg(120, 0, [(100, "("), (110, AR), (200, ")"), (210, AR),
                      (300, "("), (310, AR), (400, ")"), (410, AR)]),
        _seg(140, 0, [(100, AR), (400, ")"), (410, AR)]),
    ]]
    ok, inverted, _ = _measure(monkeypatch, pages)
    assert inverted == 0
    assert ok == 3


def test_a_left_to_right_cell_on_an_arabic_row_is_not_judged(monkeypatch):
    """خليّةُ الهاتف LTR (تقرير ٧، commit 13fc62f): `(+966)` في خليّةٍ لاتينية
    على صفٍّ عربيّ الأغلبية — ترتيبُ `()` فيها هو الصحيح."""
    pages = [[
        _seg(100, 0, [(300, AR), (380, AR)]),
        _seg(100, 1, [(100, "(+966) 12 345 6789")]),
    ]]
    ok, inverted, _ = _measure(monkeypatch, pages)
    assert inverted == 0


def test_a_pair_continued_across_a_page_break_is_not_inverted(monkeypatch):
    """فقرةٌ تنقسم بين صفحتين: القوسُ يُفتح أسفلَ الأولى ويُغلق أعلى الثانية."""
    pages = [
        [_seg(700, 0, [(100, "("), (110, AR)])],
        [_seg(60, 0, [(300, AR), (380, ")"), (390, AR)])],
    ]
    ok, inverted, _ = _measure(monkeypatch, pages)
    assert (ok, inverted) == (1, 0)


def test_a_genuinely_inverted_pair_is_still_caught(monkeypatch):
    """الوجهُ الآخر: القوسُ الافتتاحيُّ على يسار مقطعه في سطرٍ عربيّ."""
    pages = [[_seg(100, 0, [(100, "("), (110, AR), (200, ")"), (210, AR)])]]
    _ok, inverted, _ = _measure(monkeypatch, pages)
    assert inverted == 1


def test_a_stale_open_bracket_does_not_hide_a_later_inversion(monkeypatch):
    """قوسٌ افتتاحيٌّ لم يُغلَق (نصٌّ مبتور) لا يبتلع انقلاباً بعيداً عنه —
    الأزواجُ السليمة تُغلَق خلال بضعة أسطر، فالمعلَّقُ يسقط بعد نافذةٍ محدودة."""
    import silk_reports as R
    gap = R._BRACKET_EXPIRED_ROWS + 3
    pages = [[_seg(100, 0, [(100, "("), (110, AR)])]
             + [_seg(100 + 20 * i, 0, [(100, AR)]) for i in range(1, gap)]
             + [_seg(100 + 20 * gap, 0, [(100, "("), (110, AR),
                                         (200, ")"), (210, AR)])]]
    _ok, inverted, _ = _measure(monkeypatch, pages)
    assert inverted == 1


def test_a_long_wrapped_pair_past_the_window_is_skipped_not_inverted(monkeypatch):
    """مراجعةٌ ذاتية: قوسٌ طويلٌ في خليّةٍ ضيّقة يتجاوز نافذةَ الحمل — ختاميُّه
    **يُتخطّى** (لا حكم) ولا يُعَدّ مقلوباً، وإلا عاد الرفضُ الكاذب نفسُه."""
    import silk_reports as R
    n = R._BRACKET_CARRY_ROWS + 3
    pages = [[_seg(100, 0, [(300, AR), (396, "(")])]
             + [_seg(100 + 20 * i, 0, [(300, AR)]) for i in range(1, n)]
             + [_seg(100 + 20 * n, 0, [(300, ")"), (310, AR)])]]
    ok, inverted, skipped = _measure(monkeypatch, pages)
    assert (ok, inverted) == (0, 0)
    assert skipped >= 1


def test_an_old_latin_orphan_does_not_hide_an_inversion(monkeypatch):
    """مراجعةٌ ذاتية: رابطٌ مبتورٌ `(UN Comtrade` (مقطعٌ لاتينيّ لم يُغلَق) لا
    يُقرَن بختاميٍّ عربيٍّ مقلوب بعد عدّة أسطر."""
    pages = [[
        _seg(100, 0, [(100, "(UN Comtrade data")]),
        _seg(120, 0, [(100, AR)]),
        _seg(140, 0, [(100, AR)]),
        _seg(160, 0, [(100, AR)]),
        _seg(180, 0, [(100, "("), (110, AR), (200, ")"), (210, AR)]),
    ]]
    _ok, inverted, _ = _measure(monkeypatch, pages)
    assert inverted == 1


def test_a_lone_closing_bracket_is_not_an_inversion(monkeypatch):
    """مراجعةٌ ذاتية: ختاميٌّ بلا قرين («١) النقطة الأولى») ليس زوجاً مقلوباً —
    الصفُّ غيرُ المتوازن كان يُتخطّى، ولا يصير الآن رفضاً لتقريرٍ سليم."""
    pages = [[_seg(100, 0, [(300, AR), (396, ")"), (400, "١")])]]
    assert _measure(monkeypatch, pages)[1] == 0


def test_a_line_split_by_a_fraction_of_a_point_is_one_row(monkeypatch):
    """مراجعةٌ ذاتية: تغيّرُ الخطّ يزيح خطَّ الأساس كسورَ نقطة — نصفا السطر
    الواحد (الختاميُّ على 100.04 والافتتاحيُّ على 100.06) صفٌّ واحد."""
    pages = [[_seg(100.04, 0, [(100, ")"), (110, AR)]),
              _seg(100.06, 0, [(300, AR), (396, "(")])]]
    ok, inverted, _ = _measure(monkeypatch, pages)
    assert (ok, inverted) == (1, 0)


def test_a_latin_orphan_two_rows_above_does_not_hide_an_inversion(monkeypatch):
    """مراجعةٌ ذاتية: القرنُ اللاتينيّ⇐العربيّ للسطر التالي **فقط**."""
    pages = [[
        _seg(100, 0, [(100, "(UN Comtrade data")]),
        _seg(120, 0, [(100, AR)]),
        _seg(140, 0, [(100, "("), (110, AR), (200, ")"), (210, AR)]),
    ]]
    assert _measure(monkeypatch, pages)[1] == 1


def test_a_fully_inverted_build_far_apart_counts_every_pair(monkeypatch):
    """مراجعةٌ ذاتية: قرينُ انقلابٍ تجاوز النافذةَ لا يصير «رصيداً» يُخفي
    الانقلابَ التالي — ستّةُ أزواجٍ مقلوبةٍ متباعدة تُعَدّ ستّة."""
    import silk_reports as R
    step = R._BRACKET_CARRY_ROWS + 2
    pages = [[]]
    for k in range(6):
        pages[0].append(_seg(100 + 20 * k * step, k, [
            (100, AR), (132, "("), (140, "UN"), (200, ")"), (210, AR)]))
        for j in range(1, step):
            pages[0].append(_seg(100 + 20 * (k * step + j), 100 + k, [(100, AR)]))
    ok, inverted, _ = _measure(monkeypatch, pages)
    assert (ok, inverted) == (0, 6)


def test_a_fully_inverted_build_counts_every_pair(monkeypatch):
    """مراجعةٌ ذاتية: في بناءٍ مقلوبٍ بالكامل كان كلُّ ختاميٍّ مقلوب يُغلق
    افتتاحيَّ الفقرة السابقة فيُحسَب «سليماً» — فيُعَدّ زوجٌ واحدٌ من خمسة وتمرّ
    عتبةُ `SILK_PDF_BRACKET_FAIL_MAX=1` على مستندٍ مقلوبٍ كلّه."""
    pages = [[_seg(100 + 32 * i, i, [(100, AR), (132, "("), (140, "UN"),
                                     (200, ")"), (210, AR)])
              for i in range(5)]]
    ok, inverted, _ = _measure(monkeypatch, pages)
    assert (ok, inverted) == (0, 5)


def _canonical_view(module, fn):
    tools = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import importlib

    import silk_render
    return silk_render.build_view(getattr(importlib.import_module(module), fn)())


def _pdf_tools() -> bool:
    import silk_reports
    try:
        import fitz  # noqa: F401
    except ImportError:
        return False
    return silk_reports._find_soffice() is not None


@pytest.mark.skipif(not _pdf_tools(),
                    reason="soffice/pymupdf غير متاح (يعمل في e2e-live-shape وصورة النشر)")
@pytest.mark.parametrize("module,fn,kind", [
    # رُفِضت كلُّها على المقياس القديم (إعادة إنتاجٍ مباشرة، 2026-09-26).
    ("canonical_india_honey", "india_honey_research_blob", "client"),
    ("canonical_morocco_juice", "morocco_juice_research_blob", "client"),
    ("canonical_dza_peanut_butter", "dza_research_blob", "research"),
    ("canonical_libya_tahini", "libya_tahini_research_blob", "research"),
])
def test_real_reports_that_were_refused_now_pass_the_gate(tmp_path, module, fn,
                                                          kind, monkeypatch):
    """المسارُ الإنتاجيّ كاملاً (docx ⇐ LibreOffice ⇐ البوّابة) على دراساتٍ
    حقيقية الشكل كانت تُرفَض — الآن تُسلَّم، والمقياسُ قاس أزواجاً فعلاً."""
    import silk_reports
    monkeypatch.delenv("SILK_PDF_BRACKET_FAIL_MAX", raising=False)
    view = _canonical_view(module, fn)
    render = (silk_reports.render_client_pdf if kind == "client"
              else silk_reports.render_research_pdf)
    pdf = render(view, str(tmp_path / "r.pdf"))
    ok, inverted, _ = silk_reports.bracket_orientation_counts(pdf)
    assert inverted == 0
    assert ok > 0, "لم يُقَس أيُّ زوج — مقياسٌ أعمى لا سليم"


# ── التسمية: رفضُ البوّابة ليس «معطَّلاً على الخادم» ─────────────────────────

def test_each_pdf_failure_has_its_own_code():
    """ثلاثةُ أعطالٍ مختلفة كانت رمزاً واحداً (`pdf_unavailable` = «معطَّل —
    أبلغ الإدارة»). الآن: غيابُ المحرّك وحده `pdf_unavailable`."""
    import silk_reports as R
    D = R.pdf_error_detail
    assert D(R.PdfEngineUnavailable(R._PDF_UNAVAILABLE))["error"] == "pdf_unavailable"
    assert D(R.ExportEngineUnavailable(R._DOCX_HINT))["error"] == "pdf_unavailable"
    assert D(R.PdfConversionFailed(R._PDF_FAILED))["error"] == "pdf_failed"
    assert D(R.PdfBracketGateError("x"))["error"] == "pdf_rejected"
    # بوّابةُ محتوى (تناقضُ الحكم، مصطلحٌ محظور) تفشل كلَّ مرّة — لا «أعد المحاولة».
    assert D(R.ReportGateError("تناقض حكم"))["error"] == "pdf_rejected"
    # خطأٌ غير مصنَّف قد يكون عابراً — «أعد المحاولة» لا «لن يتغيّر».
    assert D(RuntimeError("can't start new thread"))["error"] == "pdf_failed"
    for cls in (R.PdfEngineUnavailable, R.PdfConversionFailed,
                R.PdfBracketGateError, R.ReportGateError,
                R.ExportEngineUnavailable):
        assert issubclass(cls, RuntimeError)    # المستدعون القدامى لا ينكسرون


def test_a_missing_python_docx_is_typed_not_matched_by_text():
    """مراجعةٌ ذاتية: غيابُ python-docx كان يُعرَف بمساواة النصّ — الآن نوعٌ."""
    import inspect

    import silk_reports as R
    src = inspect.getsource(R)
    assert "raise RuntimeError(_DOCX_HINT)" not in src
    assert src.count("raise ExportEngineUnavailable(_DOCX_HINT)") == 3
    # بوّاباتُ المحتوى الحتمية (أثرٌ برهانيّ، تناقضُ حكم، مصطلحٌ محظور) مصنَّفة.
    assert src.count("raise ReportGateError(") == 4


def test_the_failure_message_is_redacted(monkeypatch):
    """الرسالةُ تبلغ جسمَ الردّ والسجلّ — قيمُ مفاتيح البيئة تُنقّى منها."""
    import silk_reports as R
    secret = "sk-test-0123456789abcdefghijklmnopqrstuvwxyz"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    detail = R.pdf_error_detail(R.PdfConversionFailed(f"فشل مع {secret}"))
    assert secret not in detail["message"]


def test_the_bracket_gate_raises_its_own_type(monkeypatch):
    import silk_reports as R
    monkeypatch.delenv("SILK_PDF_BRACKET_FAIL_MAX", raising=False)
    pages = [[_seg(100, 0, [(100, "("), (110, AR), (200, ")"), (210, AR)])]]
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(pages))
    with pytest.raises(R.PdfBracketGateError, match="اتجاه الأقواس"):
        R._pdf_bracket_check("/tmp/any.pdf")


def test_the_factory_page_names_each_pdf_failure():
    """الصفحةُ تترجم الرمزين الجديدين — بلا ترجمةٍ كانت ستعرض نصَّ الخادم الداخليّ."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "web", "platform.html"), encoding="utf-8") as fh:
        html = fh.read()
    for code in ("pdf_failed:", "pdf_rejected:"):
        assert html.count(code) == 2, f"{code} يلزم في ERR_AR وERR_EN"
