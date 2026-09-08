"""تطبيعُ طبقةِ نصّ الـPDF العربية — أقفالٌ هرمتية (بلا soffice ولا PDF حقيقيّ).

العطلُ الذي تحرسه هذه الأقفال: تقريرُ العميل سليمٌ على الورق ومبعثرٌ في طبقة
نصّه — النسخُ والبحثُ (Ctrl+F) وقارئُ الشاشة يُخرجون `غري` بدل `غير`. الجذرُ
أنّ المستخرِج يعكس السلسلةَ كاملةً فيقلب داخلَ كلّ عنقودِ رباط، والعلاجُ عكسُ
الوجهات العربية متعدّدة المحارف مسبقًا في `ToUnicode`.

الأقفالُ هنا تحرس **حدودَ التحويل** (ما يُمَسّ وما لا يُمَسّ) و**سلامةَ
الارتداد** (تعثُّرٌ ⇒ الأصلُ بايتًا ببايت). القفلُ الإنتاجيّ الحيّ يعيش في
`tests/test_wave2_first_pdf_cluster.py` (يحتاج soffice ⇒ e2e-live-shape).

Run: python3 -m pytest tests/test_pdf_textlayer.py -q
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import silk_pdf_textlayer as T  # noqa: E402


def _cmap(*entries: str) -> bytes:
    body = "\n".join(entries)
    return (f"/CMapName/Adobe-Identity-UCS def\n"
            f"{len(entries)} beginbfchar\n{body}\nendbfchar\nendcmap").encode()


# ── حدودُ التحويل: ما يُقلَب وما لا يُمَسّ ──────────────────────────────────

def test_units_are_reversed_not_hex_digits():
    """**الوحدات (٤ خانات) لا الخانات.** عكسُ الخانات (`06440623` ⇒
    `32604460`) يُنتِج نقاطَ ترميزٍ لا علاقةَ لها بالنصّ — إفسادٌ صامتٌ
    لطبقة النصّ كلّها. `لأ` ⇒ `أل` هو الصواب."""
    out, clusters = T.flip_cmap_bytes(_cmap("<05> <06440623>"))
    assert b"<06230644>" in out, out
    assert b"06440623" not in out
    assert clusters == ["لأ"]      # لأ بصورته المنطقية


def test_single_char_destination_is_untouched():
    """وجهةٌ بمحرفٍ واحد لا عنقودَ فيها — المساسُ بها عبثٌ ومخاطرة."""
    src = _cmap("<01> <0642>")
    out, clusters = T.flip_cmap_bytes(src)
    assert out == src
    assert clusters == []


def test_latin_ligature_destination_is_untouched():
    """`ﬁ` ⇒ `fi` رباطٌ لاتينيٌّ يُستخرَج صحيحًا أصلًا (لا عكسَ للسطر
    اللاتينيّ) — قلبُه يكسر ما يعمل."""
    src = _cmap("<10> <00660069>")            # "fi"
    out, clusters = T.flip_cmap_bytes(src)
    assert out == src and clusters == []


def test_mixed_arabic_latin_destination_is_untouched():
    """شرطُ «كلُّها عربية» صريح: وجهةٌ مختلطةٌ لا يُعرَف اتجاهُ استخراجها."""
    src = _cmap("<11> <06440041>")            # ل + A
    out, clusters = T.flip_cmap_bytes(src)
    assert out == src and clusters == []


def test_destination_not_divisible_by_four_is_untouched():
    """طولٌ لا ينقسم على ٤ ليس UTF-16BE سليمًا — لا نُخمّن تقسيمَه."""
    src = _cmap("<12> <064406>")
    out, clusters = T.flip_cmap_bytes(src)
    assert out == src and clusters == []


def test_only_bfchar_sections_are_edited_never_bfrange():
    """`bfrange` قد تحمل وجهةً **مصفوفةً** فيلتبس الرمزُ بالوجهة على أيّ
    تعبيرٍ نمطيّ ساذج. المستنداتُ المقيسة لا تحمله (٠ من ٣ تدفّقات)،
    فحصرُ التعديل في `bfchar` يُبقي العلاجَ كاملًا والمجهولَ غيرَ مَمسوس."""
    src = (b"beginbfrange\n<20> <2F> <06440623>\nendbfrange\n"
           b"1 beginbfchar\n<05> <06440623>\nendbfchar")
    out, clusters = T.flip_cmap_bytes(src)
    assert b"beginbfrange\n<20> <2F> <06440623>\nendbfrange" in out, out
    assert clusters == ["لأ"]       # عنقودُ bfchar وحدَه


def test_three_unit_cluster_reverses_fully():
    """عنقودٌ ثلاثيٌّ (نادرٌ لكنّه ممكن) يُعكَس كاملًا لا جزئيًّا."""
    out, _ = T.flip_cmap_bytes(_cmap("<13> <064406230627>"))
    assert b"<062706230644>" in out


# ── مقياسُ القبول ───────────────────────────────────────────────────────────

def test_cluster_score_counts_both_orientations():
    """المقياسُ مُعايَرٌ ذاتيًّا: العناقيدُ تأتي من خريطة المستند نفسِه،
    فلا قائمةَ كلماتٍ مكتوبةً بخطّ اليد تنجرف عن المحتوى."""
    clusters = ["ير"]               # ير
    assert T.cluster_score("غير وغير", clusters) == (2, 0)
    assert T.cluster_score("غري وغري", clusters) == (0, 2)


def test_palindromic_cluster_carries_no_signal():
    """عنقودٌ يساوي معكوسَه لا يميّز الحالتين — يُتجاهَل بدل أن يُضخّم العدّ."""
    assert T.cluster_score("للل", ["لل"]) == (0, 0)


# ── سلامةُ الارتداد: تعثُّرٌ ⇒ الأصلُ كما هو ────────────────────────────────

def test_kill_switch_leaves_the_file_untouched(tmp_path, monkeypatch):
    """`SILK_PDF_TEXTLAYER_FIX=0` يُطفئه — والملفُّ يبقى بايتًا ببايت."""
    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-1.7\noriginal")
    monkeypatch.setenv("SILK_PDF_TEXTLAYER_FIX", "0")
    assert T.normalize_arabic_text_layer(str(f)) is False
    assert f.read_bytes() == b"%PDF-1.7\noriginal"


def test_missing_pymupdf_is_a_declared_skip_not_a_crash(tmp_path, monkeypatch):
    """بلا pymupdf: `False` بسطرِ تشخيص — لا استثناءَ يُسقِط تصديرَ العميل."""
    import builtins
    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-1.7\noriginal")
    monkeypatch.delenv("SILK_PDF_TEXTLAYER_FIX", raising=False)
    monkeypatch.delitem(sys.modules, "fitz", raising=False)
    real = builtins.__import__

    def _no_fitz(name, *a, **kw):
        if name == "fitz":
            raise ImportError("no fitz")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _no_fitz)
    assert T.normalize_arabic_text_layer(str(f)) is False
    assert f.read_bytes() == b"%PDF-1.7\noriginal"


def test_unreadable_file_never_raises_on_the_export_path(tmp_path, monkeypatch):
    """هذه الدالّةُ تقع على مسار تصديرٍ للعميل: أيُّ تعثّرٍ يعيد `False`
    ولا يرفع أبدًا — وإلا صار إصلاحُ جودةٍ سببَ 503."""
    monkeypatch.delenv("SILK_PDF_TEXTLAYER_FIX", raising=False)
    pytest.importorskip("fitz")
    f = tmp_path / "broken.pdf"
    f.write_bytes(b"not a pdf at all")
    assert T.normalize_arabic_text_layer(str(f)) is False
    assert f.read_bytes() == b"not a pdf at all"


def test_pdf_without_arabic_clusters_is_left_alone(tmp_path, monkeypatch):
    """مستندٌ بلا عنقودٍ عربيّ: لا تطبيعَ ولا كتابة — لا نُعيد حفظَ ملفٍّ
    بلا سبب (إعادةُ الحفظ وحدَها تغيّر بايتاته)."""
    fitz = pytest.importorskip("fitz")
    monkeypatch.delenv("SILK_PDF_TEXTLAYER_FIX", raising=False)
    f = tmp_path / "latin.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Plain latin text")
    doc.save(str(f))
    doc.close()
    before = f.read_bytes()
    assert T.normalize_arabic_text_layer(str(f)) is False
    assert f.read_bytes() == before


def test_wired_into_docx_to_pdf_before_the_bracket_gate():
    """الترتيبُ مقصود: التطبيعُ **قبل** فحص الأقواس كي يفحصَ الحارسُ
    المستندَ المُسلَّم فعلًا لا نسخةً سابقة."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "silk_reports.py"), encoding="utf-8").read()
    body = src.split("def docx_to_pdf(")[1].split("\ndef ")[0]
    assert "normalize_arabic_text_layer(" in body
    assert (body.index("normalize_arabic_text_layer(")
            < body.index("_pdf_bracket_check(")), \
        "التطبيعُ يجب أن يسبق فحصَ الأقواس"


def test_english_export_never_normalizes():
    """العطلُ ثنائيُّ الاتجاه (bidi) بحت — مستندٌ إنجليزيٌّ لا يُمَسّ."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "silk_reports.py"), encoding="utf-8").read()
    body = src.split("def docx_to_pdf(")[1].split("\ndef ")[0]
    i = body.index("normalize_arabic_text_layer(")
    assert "is_rtl(lang)" in body[max(0, i - 300):i], \
        "التطبيعُ غيرُ مشروطٍ باتجاه RTL"
