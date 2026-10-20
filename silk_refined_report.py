"""التقرير المنقَّح بيد المالك عبر MCP — owner-refined report (قرار المالك 2026-10-20).

المسار: المالك يسحب **نصّ الكاتب المخزَّن** (`deep_research.report.report`) إلى كلود
(Desktop/Code) عبر خادم MCP (`tools/silk_mcp.py`)، ينقّحه هناك على اشتراكه الشخصي —
**لا نداء كلود مدفوعاً من الخادم** (سبب القرار: مرحلةُ تلميعٍ داخل المسار تكلّف لكل
تقرير) — ثم يعيده بـ`POST /analyses/{id}/report/refined` فيحلّ مكان نصّ الكاتب
وتصدر منه ملفات العميل (docx/pdf/md) بالقالب الرسمي نفسه.

**الطرفان يتكلّمان صيغةً واحدة** (مراجعة §58، الملاحظة ١): ما يُسحَب هو النصّ
المخزَّن نفسه لا المستند المعروض للعميل، وما يُعاد يُخزَّن مكانه — فلا يتداخل قالبٌ
داخل قالب، وفحوص العناوين والطول والأرقام تقارن شيئاً بمثله.

ما يحميه هذا الملف (حتمي بالكامل، صفر نداء خارجي):
  ١. **لا رقم جديد** — كل عددٍ في المنقَّح وارد في الأصل (عقد عدم الاختلاق، البند ٨).
     الأرقام الهندية تُوحَّد قبل المقارنة. حدُّ الفحص معلَن: عضويةُ العدد لا ارتباطُه
     بادّعائه — إعادةُ تركيب رقمَين واردَين في ادّعاءٍ جديد يبقى على المالك عند المراجعة.
  ٢. **عناوين الأقسام محفوظة** (`#`…`######`) — القالب والبوّابة يقرآنها حرفياً.
  ٣. **عناصر السجلّ `{{…}}` محفوظة ولا جديدة** — `silk_fact_ledger` يملؤها عند
     التصيير ويرصد بها البيانات البائتة (الدرس ٢٦٢)؛ ضياعُها = رقمٌ يتجمّد بلا رصد.
  ٤. **لا بترٌ صامت** — نصٌّ أقصر من نصف الأصل يُرفَض (كلود قد يعيد قسماً واحداً).
  ٥. الأصل يُحفَظ مرّةً واحدة في `report_original` فلا يُفقَد نصٌّ دفع المالك ثمنه.
بوّابة التسليم نفسها (`silk_export_gate.evaluate`) تُعاد على العرض الجديد في نقطة
النهاية — رفضها = لا حفظ. هذه الوحدة تُجهِّز وتفحص فقط؛ لا تخزين هنا.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

# الأرقام الهندية (العربية المشرقية) والفارسية → ASCII قبل أي مقارنة.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_FIGURE = re.compile(r"\d+(?:[.,٫٬]\d+)*")
_HEAD = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
# نفس الشكل الرخو في `silk_fact_ledger._LOOSE_TOKEN_RE` — أي «{{…}}» عنصرٌ يُملأ آلياً.
_TOKEN = re.compile(r"\{\{[^{}\n]{0,120}\}\}")
_WS = re.compile(r"\s+")

# نسبة الطول الأدنى للنصّ المنقَّح إلى الأصل — أدنى منها = بترٌ لا تنقيح.
MIN_LENGTH_RATIO = 0.5


def _canon_figure(tok: str) -> str:
    """صورة قانونية للعدد: فواصل الآلاف تُسقَط، الفاصلة العشرية العربية «٫» → «.»."""
    return tok.replace(",", "").replace("٬", "").replace("٫", ".")


def extract_figures(text: str) -> set[str]:
    """مجموعة الأعداد في النصّ بصورتها القانونية (بعد توحيد الأرقام الهندية)."""
    norm = (text or "").translate(_DIGITS)
    return {_canon_figure(m.group(0)) for m in _FIGURE.finditer(norm)}


def new_figures(refined: str, original: str) -> list[str]:
    """الأعداد الواردة في المنقَّح وغير الواردة في الأصل."""
    extra = extract_figures(refined) - extract_figures(original)
    return sorted(extra, key=lambda s: (len(s), s))


def section_heads(text: str) -> list[str]:
    """عناوين Markdown (`#`…`######`) بترتيبها، بمسافاتٍ موحَّدة."""
    return [_WS.sub(" ", h).strip() for h in _HEAD.findall(text or "")]


def missing_heads(original: str, refined: str) -> list[str]:
    """عناوين الأصل الغائبة عن المنقَّح — القالب يحتاجها حرفياً."""
    have = set(section_heads(refined))
    return [h for h in section_heads(original) if h not in have]


def placeholders(text: str) -> list[str]:
    """عناصر السجلّ «{{…}}» بترتيب ورودها بلا تكرار (بعد توحيد المسافات داخلها)."""
    out: list[str] = []
    for m in _TOKEN.finditer(text or ""):
        tok = _WS.sub(" ", m.group(0))
        if tok not in out:
            out.append(tok)
    return out


def verify(refined: str, original: str) -> list[dict]:
    """الفحوص الحتمية قبل أي حفظ. تعيد قائمة ملاحظات؛ فارغة = مقبول.

    كل ملاحظة `{"check", "note", "items"}` بلغةٍ يفهمها المالك في كلود مباشرة —
    فيُصلِح ويعيد الإرسال بلا قراءة سجلّات."""
    out: list[dict] = []
    text = (refined or "").strip()
    if not text:
        return [{"check": "empty", "note": "النصّ المنقَّح فارغ", "items": []}]
    base = (original or "").strip()
    if base and len(text) < MIN_LENGTH_RATIO * len(base):
        out.append({"check": "truncated",
                    "note": (f"النصّ المنقَّح أقصر من نصف الأصل "
                             f"({len(text)} مقابل {len(base)} حرفاً) — أعد التقرير كاملاً"),
                    "items": []})
    heads = missing_heads(base, text)
    if heads:
        out.append({"check": "missing_heads",
                    "note": "عناوين أقسام من الأصل غائبة — أبقِ سطور العناوين كما هي",
                    "items": heads})
    orig_tok, new_tok = placeholders(base), placeholders(text)
    lost = [t for t in orig_tok if t not in new_tok]
    if lost:
        out.append({"check": "missing_placeholders",
                    "note": "عناصر «{{…}}» من الأصل غائبة — تُملأ آلياً بقيمها؛ أبقِها حرفياً في مكانها",
                    "items": lost})
    added = [t for t in new_tok if t not in orig_tok]
    if added:
        out.append({"check": "new_placeholders",
                    "note": "عناصر «{{…}}» غير واردة في الأصل — لا تُضاف عناصر جديدة",
                    "items": added})
    figs = new_figures(text, base)
    if figs:
        out.append({"check": "new_figures",
                    "note": "أرقام غير واردة في التقرير الأصلي — لا نخمّن الأرقام؛ احذفها أو أعدها كما وردت",
                    "items": figs[:20]})
    return out


def apply(report_node: dict, refined: str, *, now: str | None = None) -> dict:
    """عقدة تقرير جديدة بالنصّ المنقَّح — لا تمسّ العقدة الأصلية.

    `report_original` يُثبَّت عند أول تنقيح فقط؛ التنقيحات اللاحقة تزيد `refined_count`."""
    node = dict(report_node or {})
    if not node.get("report_original"):
        node["report_original"] = node.get("report")
    node["report"] = (refined or "").strip()
    node["refined_at"] = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    node["refined_via"] = "mcp"
    node["refined_count"] = int(node.get("refined_count") or 0) + 1
    return node
