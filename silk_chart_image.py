"""رسمُ التقرير صورةً — من عقد `deep_research.charts` نفسِه، بلا تبعيةٍ جديدة.

Report charts as PNG images, rendered from the same pure-data contract the web
page draws (`silk_render._charts_view`): `{id, kind, unit, title, section,
series, source, year, note}`. The renderer adds **no** computation — it draws
what the view already decided — so Word/PDF and the dashboard can never drift.

المحرّك `pymupdf` (مثبَّتٌ في متطلبات الإنتاج أصلاً — لا تبعيةَ جديدة): الأشرطة
أشكالٌ متجهة، والنصُّ العربيّ عبر `insert_htmlbox` (يشكّل العربية صحيحاً؛
مسارُ SVG لا يشكّلها فلا يُستخدم هنا). الخطُّ IBM Plex Sans Arabic من صورة
النشر إن وُجد، وإلا خطُّ المحرّك الافتراضي (يشكّل العربية أيضاً).

القواعدُ نفسُها: سلسلةٌ فارغة ⇒ لا صورة (`None`)؛ قيمةٌ غائبة «—» بلا عمود؛
الألوانُ من الهوية؛ وأيُّ استثناءٍ ⇒ `None` مع سطرِ سجلّ — التصديرُ لا يسقط
لأجل صورة.
"""
from __future__ import annotations

import logging
import math
import os

log = logging.getLogger(__name__)

# ألوانُ الهوية (نفسُ الخمسة المسموحة في `web/platform.html`).
_BLUE = (0x25 / 255, 0x63 / 255, 0xEB / 255)
_GOLD = (0xC9 / 255, 0xA2 / 255, 0x27 / 255)
_TRACK = (0xEE / 255, 0xF2 / 255, 0xF7 / 255)
_MUTED = (0x64 / 255, 0x74 / 255, 0x8B / 255)
_INK = (0x11 / 255, 0x28 / 255, 0x37 / 255)

_FONT_DIRS = ("/usr/share/fonts/truetype/ibmplex",)
_FONT_FILES = ("IBMPlexSansArabic-Regular.ttf",)

# هندسةُ الصورة (نقاطُ PDF؛ التصديرُ بـ`_DPI`).
_W = 560.0
_ROW = 26.0
_BAR_H = 16.0
_GUT = 210.0          # خانةُ التسمية (يمين)
_VAL = 86.0           # خانةُ القيمة المطبوعة (يسار)
_DPI = 200


def _font_css():
    """(css, archive) لخطٍّ عربيّ من صورة النشر — ("", None) إن لم يوجد."""
    try:
        import pymupdf
    except ImportError:
        return "", None
    for d in _FONT_DIRS:
        for f in _FONT_FILES:
            if os.path.exists(os.path.join(d, f)):
                arch = pymupdf.Archive()
                arch.add(d)
                return ("@font-face{font-family:silkar;src:url(%s);}"
                        "*{font-family:silkar;}" % f), arch
    return "", None


def _jsround(x: float) -> int:
    """تدويرُ `Math.round` حرفياً: نصفٌ إلى الأعلى (نحو +∞) لا تدويرُ المصرفيّ.

    مراجعة §58: `round()` في بايثون يدوّر النصفَ إلى الزوجيّ، فـ41.25% تُطبَع
    «41.2%» في المستند و«41.3%» على الشاشة — رقمٌ واحدٌ بقيمتين على سطحين.
    المصيّران يطبعان الرقمَ نفسَه أو فرقٌ يُنسَب إلى البيانات وهو من الطبع.
    """
    return math.floor(x + 0.5)


def _plain(x: float) -> str:
    """الرقمُ بلا صيغةٍ علمية وبلا أصفارٍ زائدة — كما تطبعه JS."""
    s = f"{x:.10f}".rstrip("0").rstrip(".")
    return s or "0"


def _num(chart: dict, value) -> str:
    """الرقمُ كما تطبعه الواجهة — `_chartNum` بمنطقه نفسِه (وحدةٌ واحدة)."""
    if value is None:
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    unit = str(chart.get("unit") or "")
    if unit == "%":
        return f"{_plain(_jsround(n * 10) / 10)}%"
    if unit == "index":
        return str(_jsround(n))
    if unit == "USD":
        a = abs(n)
        if a >= 1e9:
            return f"${_plain(_jsround(n / 1e7) / 100)}B"
        if a >= 1e6:
            return f"${_plain(_jsround(n / 1e4) / 100)}M"
        if a >= 1e3:
            return f"${_plain(_jsround(n / 10) / 100)}K"
        # مبالغُ الوحدة (سعرُ مصنعٍ/رفّ) تحت المئة: منزلتان — «$3» بدل «$3.10»
        # تُخفي فرقاً تجارياً حقيقياً.
        return (f"${_plain(_jsround(n * 100) / 100)}" if a < 100
                else f"${_jsround(n)}")
    # وحداتٌ أخرى: فواصلُ الآلاف ومنزلتان كحدٍّ أقصى (`toLocaleString`).
    return f"{_jsround(n * 100) / 100:,.2f}".rstrip("0").rstrip(".")


def _known(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _rows(chart: dict) -> list:
    return [r for r in (chart.get("series") or [])
            if isinstance(r, dict) and r.get("label") is not None]


def _text(page, css, arch, rect, html) -> None:
    """نصٌّ في مستطيل — يتقلّص خطّه تلقائياً عند الضيق (`scale_low`)."""
    page.insert_htmlbox(rect, html, css=css, archive=arch, scale_low=0.4)


def _label_html(text: str, size: float = 11.5, align: str = "right",
                color: str = "#64748B") -> str:
    from html import escape
    return (f'<div dir="auto" style="font-size:{size}px;text-align:{align};'
            f'color:{color};line-height:1.25">{escape(str(text))}</div>')


def chart_png(chart: dict, lang: str = "ar") -> "bytes | None":
    """صورةُ PNG للرسم — أو `None` (بلا بيانات، أو محرّكٌ غائب، أو خطأ).

    لا حسابَ هنا: القيمُ والتسمياتُ والمصدرُ كما بناها العرض.
    """
    if not isinstance(chart, dict):
        return None
    try:
        import pymupdf
    except ImportError:
        log.warning("chart image skipped: pymupdf unavailable")
        return None
    try:
        # `_rows` كان يُنادى خارج الحماية، فسلسلةٌ غيرُ قابلةٍ للمرور (قاموسٌ
        # أو رقم) ترفع الاستثناءَ إلى التصدير نفسِه — نقضٌ لعقد هذه الدالة
        # («أيُّ استثناءٍ ⇒ None»). مراجعة §58.
        rows = _rows(chart)
        if not rows:
            return None
        kind = chart.get("kind")
        kind = kind if kind in ("bars", "range", "gauge") else "bars"
        css, arch = _font_css()
        band_room = 14.0 if kind == "gauge" else 0.0
        n = 1 if kind == "gauge" else len(rows)
        height = 26.0 + n * _ROW + band_room + 6.0    # عنوان + صفوف + هامش
        doc = pymupdf.open()
        page = doc.new_page(width=_W, height=height)
        shape = page.new_shape()
        bar_w = max(60.0, _W - _GUT - _VAL - 16.0)
        x0 = _VAL + 8.0                                # بدايةُ المسار (يسار)
        top = 26.0

        def track(y):
            shape.draw_rect(pymupdf.Rect(x0, y, x0 + bar_w, y + _BAR_H))
            shape.finish(color=None, fill=_TRACK)

        def bar(y, width, fill, alpha=1.0):
            if width <= 0:
                return
            shape.draw_rect(pymupdf.Rect(x0 + (bar_w - width), y,
                                         x0 + bar_w, y + _BAR_H))
            shape.finish(color=None, fill=fill, fill_opacity=alpha)

        # عنوانُ الرسم
        _text(page, css, arch, pymupdf.Rect(8, 4, _W - 8, 24),
              _label_html(chart.get("title") or "", 13.5, "right", "#112837"))

        if kind == "gauge":
            bands = [b for b in (chart.get("bands") or [])
                     if isinstance(b, dict) and _known(b.get("from"))
                     and _known(b.get("to"))]
            scale = float(bands[-1]["to"]) if bands else 1.0
            scale = scale if scale > 0 else 1.0
            y = top
            track(y)
            for i, b in enumerate(bands):
                xa = bar_w * float(b["from"]) / scale
                xb = bar_w * float(b["to"]) / scale
                shape.draw_rect(pymupdf.Rect(x0 + (bar_w - xb), y,
                                             x0 + (bar_w - xa), y + _BAR_H))
                shape.finish(color=None, fill=(_TRACK if i == 0 else _MUTED),
                             fill_opacity=(1.0 if i == 0 else
                                           (0.35 if i == 1 else 0.7)))
                mid = x0 + (bar_w - (xa + xb) / 2.0)
                # تسميةٌ لا تجد عرضاً تُسقَط (التراكبُ يُخفي الرسمَ نفسَه)؛
                # منطقةُ القيمة مسمّاةٌ في خانة التسمية على كلّ حال.
                if (xb - xa) >= 52.0:
                    half = max(26.0, (xb - xa) / 2.0)
                    _text(page, css, arch,
                          pymupdf.Rect(mid - half, y + _BAR_H + 1, mid + half,
                                       y + _BAR_H + 14),
                          _label_html(b.get("label") or "", 9.5, "center"))
            value = chart.get("value")
            if not _known(value):
                value = rows[0].get("value")
            if _known(value):
                xv = bar_w * min(max(0.0, float(value)), scale) / scale
                shape.draw_rect(pymupdf.Rect(x0 + (bar_w - xv) - 2, y - 3,
                                             x0 + (bar_w - xv) + 2,
                                             y + _BAR_H + 3))
                shape.finish(color=None, fill=_GOLD)
            _text(page, css, arch, pymupdf.Rect(8, y, _VAL, y + _BAR_H),
                  _label_html(_num(chart, value), 11.5, "left", "#112837"))
            _text(page, css, arch,
                  pymupdf.Rect(x0 + bar_w + 6, y, _W - 6, y + _BAR_H),
                  _label_html(rows[0].get("label") or ""))
        elif kind == "range":
            highs = [float(r["high"]) for r in rows if _known(r.get("high"))]
            scale = max(highs) if highs else 1.0
            scale = scale if scale > 0 else 1.0
            for i, r in enumerate(rows):
                y = top + i * _ROW
                track(y)
                ok = _known(r.get("low")) and _known(r.get("high"))
                shown = r.get("value") if _known(r.get("value")) else (
                    r.get("high") if ok else None)
                if ok:
                    lo = max(0.0, float(r["low"]))
                    hi = max(lo, float(r["high"]))
                    xlo = bar_w * lo / scale
                    xhi = bar_w * hi / scale
                    # عمودٌ باهتٌ حتى أدنى تقدير («على الأقلّ») وقطعةٌ صريحة
                    # لعرض المدى؛ تقديرٌ نقطيّ (أدنى = أعلى) عمودٌ كاملٌ واحد.
                    if xhi - xlo >= 2.0:
                        bar(y, xlo, _BLUE, 0.45)
                        shape.draw_rect(pymupdf.Rect(x0 + (bar_w - xhi), y,
                                                     x0 + (bar_w - xlo),
                                                     y + _BAR_H))
                        shape.finish(color=None, fill=_BLUE)
                    else:
                        bar(y, xhi, _BLUE)
                _text(page, css, arch, pymupdf.Rect(8, y, _VAL, y + _BAR_H),
                      _label_html(_num(chart, shown), 11.5, "left", "#112837"))
                _text(page, css, arch,
                      pymupdf.Rect(x0 + bar_w + 6, y, _W - 6, y + _BAR_H),
                      _label_html(r.get("label") or ""))
        else:
            vals = [float(r["value"]) for r in rows if _known(r.get("value"))]
            scale = max(vals) if vals else 1.0
            scale = scale if scale > 0 else 1.0
            for i, r in enumerate(rows):
                y = top + i * _ROW
                track(y)
                if _known(r.get("value")):
                    width = bar_w * max(0.0, float(r["value"])) / scale
                    bar(y, width, _GOLD if r.get("highlight") else _BLUE,
                        0.55 if r.get("muted") else 1.0)
                _text(page, css, arch, pymupdf.Rect(8, y, _VAL, y + _BAR_H),
                      _label_html(_num(chart, r.get("value")), 11.5, "left",
                                  "#112837"))
                _text(page, css, arch,
                      pymupdf.Rect(x0 + bar_w + 6, y, _W - 6, y + _BAR_H),
                      _label_html(r.get("label") or ""))
        shape.commit()
        pix = page.get_pixmap(dpi=_DPI)
        out = pix.tobytes("png")
        doc.close()
        return out or None
    except Exception as e:  # noqa: BLE001
        log.warning("chart image skipped (%s): %s", chart.get("id"), e)
        return None


def caption(chart: dict) -> str:
    """سطرُ إسنادِ الصورة: العنوان · المصدر · السنة · الملاحظة (بلا فراغات).

    قاموسٌ مشوَّه ⇒ "" لا استثناء — سطرُ إسنادٍ يُسقِط التصديرَ أسوأُ من غيابه.
    """
    if not isinstance(chart, dict):
        return ""
    parts = [chart.get("title"), chart.get("source"), chart.get("year"),
             chart.get("note")]
    return " · ".join(str(p) for p in parts if str(p or "").strip())
