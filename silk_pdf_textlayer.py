"""تطبيعُ طبقةِ النصّ العربية في الـPDF — Arabic PDF text-layer normalization.

## العطل (تدقيق 2026-08-27، دليلٌ مباشر)

تقريرُ العميل يُسلَّم PDF. **الورقةُ سليمةٌ بصريًّا** — أُثبِت بلقطاتٍ مكبَّرةٍ
من الـPDF الإنتاجيّ — لكنّ **طبقةَ النصّ** المدمجة مبعثرة: النسخُ واللصقُ
والبحثُ (Ctrl+F) وقارئُ الشاشة تُخرِج `غري` بدل `غير`، و`ال يوجد` بدل
`لا يوجد`، و`األسعار` بدل `الأسعار`.

## الجذر — ليس ما بدا أوّلَ مرّة

فحصُ خرائط `ToUnicode` في الـPDF الإنتاجيّ أظهر أنّها **سليمةٌ ومنطقية**:

    glyph 29: 'ير'   glyph 3E: 'شر'   glyph 46: 'سر'
    glyph 05: 'لأ'   glyph 32: 'صى'   glyph 37: 'كي'

فـLibreOffice لا تُخطئ. العطلُ في **المستخرِج**: يعكس سلسلةَ المحارف
**كاملةً** كي يقلب اتجاهَ السطر، فيقلب معها ترتيبَ المحارف **داخل** كلّ
عنقودٍ متعدّدِ المحارف (رباطُ لام-ألف، ورباطاتُ الخطّ الاختيارية).

النموذجُ تنبّأ بكلّ حالةٍ رُصدت، حرفيًّا — خمسٌ من خمس:

| العنقود | الكلمة   | المتوقَّع | المرصود |
|---------|----------|-----------|---------|
| `ير`    | غير      | `غري`     | `غري`   |
| `شر`    | المباشر  | `المبارش` | `المبارش` |
| `سر`    | مسرد     | `مرسد`    | `مرسد`  |
| `صى`    | موصى     | `موىص`    | `موىص`  |
| `لأ`    | الأسعار  | `األسعار` | `األسعار` |

والمستخرِجان المستقلّان (MuPDF وpoppler) يعطيان النتيجةَ نفسَها — أي أنّ
«عكسَ السلسلة كاملةً» سلوكُهما معًا.

## العلاج

اعكِس **مسبقًا** ترتيبَ الوحدات في كلّ وجهةٍ عربيةٍ متعدّدةِ المحارف داخل
`ToUnicode`، فيُنتِج عكسُ المستخرِجِ الترتيبَ المنطقيَّ الصحيح. القياسُ على
تقرير العميل الحقيقيّ: **١٥ رمزًا مقلوبًا ⇐ صفر**، و**٠ سليم ⇐ ١٥**، في
المستخرِجَين معًا؛ و**٥/٥ صفحاتٍ متطابقةٌ بكسليًّا** (التصييرُ لا يُمَسّ).

**ولا يُمَسّ الخطّ (§7).** كان البديلُ تبديلَ العائلة، وهو (أ) لا يُصلِح
رباطَ لام-ألف — يقع في Amiri وNoto وPlex معًا — و(ب) يغيّر قرارَ مالكٍ
مستقرًّا بلا داعٍ.

## الافتراضُ المُعلَن (اقرأه قبل تعديل هذا الملفّ)

هذا التطبيعُ يفترض مستخرِجًا **يعكس السلسلةَ كاملةً**. مستخرِجٌ يعالج
العناقيدَ صحيحًا سيقرأ الناتجَ مقلوبًا. القرارُ مقصود: نُحسِّن للمستخرِجَين
اللذين يستعملهما الناسُ فعلًا (MuPDF وpoppler، وكلاهما مقيسٌ هنا)، ولا
نُحسِّن لمستخرِجٍ افتراضيٍّ لا دليلَ على وجوده. مُسجَّلٌ في
`docs/DEEP_RESEARCH_DECISIONS.md`.

The ToUnicode CMap is correct; the extractor reverses the whole string and
so flips each multi-char cluster's interior. Pre-reversing those clusters
cancels it out. Rendering is untouched — pixel-identical.
"""
from __future__ import annotations

import logging
import os
import re

log = logging.getLogger(__name__)

# نطاقاتُ العربية (بلا ما هو خارج BMP — لا عربيةَ خارجه في نصوصنا، وعكسُ
# زوجٍ بديلٍ يُنتِج ترميزًا غير صالح).
_AR_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
              (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))

# **`bfchar` حصرًا.** الوجهةُ في `bfrange` قد تأتي مصفوفةً (`[<d1> <d2>…]`)
# فيلتبس فيها الرمزُ بالوجهة على أيّ تعبيرٍ نمطيّ ساذج. المستنداتُ المقيسة
# لا تحمل `bfrange` إطلاقًا (0 من 3 تدفّقات)، فحصرُ التعديل هنا يُبقي
# العلاجَ كاملًا ويجعل المجهولَ غيرَ مَمسوس. Conservative by construction.
_BFCHAR_BLOCK = re.compile(rb"beginbfchar(.*?)endbfchar", re.S)
_BFCHAR_ENTRY = re.compile(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>")

_ENV_FLAG = "SILK_PDF_TEXTLAYER_FIX"


def _is_arabic(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _AR_RANGES)


def _units(hex_dest: str) -> "list[str] | None":
    """قسّم وجهةً hex إلى وحدات UTF-16 (٤ خانات) — `None` إن لم تنقسم.

    **الوحدات لا الخانات**: عكسُ الخانات يُفسِد الترميز تمامًا."""
    if len(hex_dest) % 4 or len(hex_dest) < 8:
        return None
    return [hex_dest[i:i + 4] for i in range(0, len(hex_dest), 4)]


def flip_cmap_bytes(raw: bytes) -> "tuple[bytes, list[str]]":
    """اعكِس وجهاتِ `bfchar` العربيةَ متعدّدةَ المحارف — يعيد (البايتات،
    العناقيدَ المقلوبة بصورتها **المنطقية**).

    ما لا يُمَسّ: الوجهةُ أحاديّةُ المحرف · اللاتينيةُ متعدّدة (`ﬁ` ⇒ `fi`) ·
    المختلطةُ عربيّ/لاتينيّ · ما لا ينقسم على ٤ · كلُّ ما خارج `bfchar`."""
    clusters: list[str] = []

    def _entry(m: "re.Match") -> bytes:
        code, dest = m.group(1), m.group(2)
        units = _units(dest.decode("ascii"))
        if units is None:
            return m.group(0)
        if not all(_is_arabic(int(u, 16)) for u in units):
            return m.group(0)
        clusters.append("".join(chr(int(u, 16)) for u in units))
        flipped = "".join(reversed(units)).encode("ascii")
        return b"<" + code + b"> <" + flipped + b">"

    def _block(m: "re.Match") -> bytes:
        body = m.group(1)
        # أمانُ الاقتران: الكتلةُ أزواجُ `<رمز> <وجهة>`، فعددُ الرموز زوجيٌّ
        # حتمًا. كتلةٌ مشوَّهةٌ (عددٌ فرديّ) تُزيح كلَّ اقترانٍ بعدها فتجعل
        # رمزًا يُقرأ وجهةً — تُترَك كما هي بدل التخمين.
        if len(re.findall(rb"<[0-9A-Fa-f]+>", body)) % 2:
            log.warning("arabic text-layer: كتلةُ bfchar غيرُ متوازنة — تُترَك")
            return m.group(0)
        return b"beginbfchar" + _BFCHAR_ENTRY.sub(_entry, body) + b"endbfchar"

    return _BFCHAR_BLOCK.sub(_block, raw), clusters


def cluster_score(text: str, clusters: "list[str]") -> "tuple[int, int]":
    """(بالصورة المنطقية، بالصورة المقلوبة) لعناقيد هذا المستند في نصٍّ
    مستخرَج — مقياسُ قبولٍ **مُعايَرٌ ذاتيًّا**: العناقيدُ تُقرأ من خريطة
    المستند نفسِه، فلا قائمةَ كلماتٍ مكتوبةً بخطّ اليد تنجرف عن المحتوى.

    العنقودُ الذي يساوي معكوسَه (لو وُجد) يُتجاهَل — لا إشارةَ فيه."""
    fwd = rev = 0
    for c in clusters:
        r = c[::-1]
        if r == c:
            continue
        fwd += text.count(c)
        rev += text.count(r)
    return fwd, rev


def _extract_all(path: str) -> "list[str]":
    """النصُّ المستخرَج بكلّ مستخرِجٍ متاح (fitz دائمًا، pdftotext إن وُجد).

    الفحصُ يقع على ما هو **متاحٌ فعلًا** — بيئةٌ بلا pdftotext تُقاس بـfitz
    وحدَه، ولا يُدَّعى أنّ الثاني فُحِص."""
    import shutil
    import subprocess
    out: list[str] = []
    try:
        import fitz
        with fitz.open(path) as doc:
            out.append("".join(p.get_text() for p in doc).replace("\n", ""))
    except Exception as e:  # noqa: BLE001
        log.warning("text-layer verify: fitz extraction failed: %s", e)
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-enc", "UTF-8", path, "-"],
                               capture_output=True, timeout=120)
            out.append(r.stdout.decode("utf-8", "replace").replace("\n", ""))
        except Exception as e:  # noqa: BLE001
            log.warning("text-layer verify: pdftotext failed: %s", e)
    return out


def normalize_arabic_text_layer(pdf_path: str) -> bool:
    """طبّع طبقةَ النصّ العربية في الـPDF — `True` إن جرى التطبيع فعلًا.

    يعمل على نسخةٍ مؤقّتة، ولا يُبدِّل الأصلَ إلا إذا **تحسّن كلُّ مستخرِجٍ
    متاحٍ ولم يسُؤ أيٌّ منه**. أيُّ تعثّرٍ (لا pymupdf، لا عناقيد، فشلُ
    التحقّق، استثناءٌ) يعيد `False` ويترك الأصلَ **بايتًا ببايت** — هذه
    الدالّةُ تقع على مسار تصديرٍ للعميل، فلا يجوز أن تُسقِطه أبدًا.

    الإطفاء: `SILK_PDF_TEXTLAYER_FIX=0`."""
    if os.environ.get(_ENV_FLAG, "1").strip().lower() in ("0", "false", "no"):
        log.info("arabic text-layer normalization disabled by %s", _ENV_FLAG)
        return False
    try:
        import fitz  # pymupdf — تبعيةُ إنتاج
    except ImportError:
        log.info("arabic text-layer normalization skipped: pymupdf غير مثبّتة")
        return False

    import shutil
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="silk_txtlayer_")
    tmp_pdf = os.path.join(tmp_dir, "normalized.pdf")
    try:
        clusters: list[str] = []
        with fitz.open(pdf_path) as doc:
            for xref in range(1, doc.xref_length()):
                if not doc.xref_is_stream(xref):
                    continue
                try:
                    raw = doc.xref_stream(xref)
                except Exception:  # noqa: BLE001 — تدفّقٌ غيرُ مقروء يُتخطّى
                    continue
                if b"beginbfchar" not in raw:
                    continue
                new, found = flip_cmap_bytes(raw)
                if new != raw:
                    doc.update_stream(xref, new)
                    clusters.extend(found)
            if not clusters:
                log.info("arabic text-layer: لا عناقيد عربية — لا تطبيع")
                return False
            doc.save(tmp_pdf)

        before = _extract_all(pdf_path)
        after = _extract_all(tmp_pdf)
        if not before or len(before) != len(after):
            log.warning("arabic text-layer: تعذّر قياسُ قبل/بعد — يُترَك الأصل")
            return False
        improved = False
        for b_txt, a_txt in zip(before, after):
            b_fwd, b_rev = cluster_score(b_txt, clusters)
            a_fwd, a_rev = cluster_score(a_txt, clusters)
            log.info("arabic text-layer: منطقيّ %d⇒%d · مقلوب %d⇒%d",
                     b_fwd, a_fwd, b_rev, a_rev)
            if a_fwd < b_fwd or a_rev > b_rev:
                log.warning("arabic text-layer: مستخرِجٌ ساء — يُترَك الأصل")
                return False
            if a_fwd > b_fwd or a_rev < b_rev:
                improved = True
        if not improved:
            log.info("arabic text-layer: لا تحسّن مقيس — يُترَك الأصل")
            return False

        shutil.copyfile(tmp_pdf, pdf_path)
        log.info("arabic text-layer normalized: %d عنقودًا", len(clusters))
        return True
    except Exception as e:  # noqa: BLE001 — لا يُسقَط تصديرُ العميل أبدًا
        log.warning("arabic text-layer normalization failed: %s", e)
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
