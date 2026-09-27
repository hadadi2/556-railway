"""linter أسلوبي حتمي لنمط «دراسة السوق» — study-mode style linter (P2-6، P2-7).

> يقرأ Markdown ناتج المحرك ويعيد قائمة مخالفات `{rule, detail}`. العناوين
> وأعمدة الجداول تُقرأ من `data/study_templates_ar.yaml` نفسه (مصدر واحد، لا نسخة
> ثانية هنا). المرجع `samples/golden_malaysia_coffee_study.md` يمر بصفر مخالفات،
> والشاهد الكويتي يُرفض. المخالفات تُسجَّل ولا تحجب التسليم (يُسلَّم دائماً).
"""
from __future__ import annotations

import re

_SLOT = re.compile(r"\{[^{}]+\}")
_LIST = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
# السنة سنةٌ فقط بسياقها: «عام/لعام/في/خلال/بحلول/حتى/منذ/سنة» أو قوس قبلها، أو «م» بعدها —
# (مؤشر تركّز 2090 ليس سنة). حدود رقمية لا \b (لا يعمل بين رقم وحرف عربي).
_YEAR = re.compile(r"(?:(?<!\S)(?:عام|لعام|سنة|في|خلال|بحلول|حتى|منذ|موسم)\s+|\()"
                   r"((?:19|20)\d{2})(?!\d)"
                   r"|(?<!\d)((?:19|20)\d{2})\s?م(?![\u0600-\u06FF])")
_LAST_YEAR = re.compile(r"أحدث سنة بيانات تجارية مكتملة:\**\s*((?:19|20)\d{2})")
_TRADE_WORDS = ("واردات", "حصة", "الواردات")
# مصطلحات لا تظهر عارية في نص العميل (تُستبدل بمعناها).
BARE_TERMS = ("HHI", "CAGR", "TAM", "SAM", "SOM", "LPI", "MFN", "WGI")
# P2-7: صيغة واحدة كما في المرجع — «مؤشر تركّز الموردين»؛ البدائل مرفوضة.
HHI_FORM = "مؤشر تركّز الموردين"
HHI_ALTERNATIVES = ("مؤشر تركّز السوق", "مؤشر تركز السوق", "مؤشر هيرفندال",
                    "مؤشر هيرفيندال", "مؤشر التركز")
# صيغ المعجم الرسمي: كل قسم نثري يحمل واحدة على الأقل.
LEXICON = ("ويُعد", "وتُعد", "تُعد", "ويُلاحظ", "ويتعين", "يتعين", "غير أن",
           "وبناءً على ذلك", "في حين", "وفي المقابل", "وتشير", "ويستند",
           "ويُقدَّر", "ويُفاد", "وتبقى", "ويُقترح", "توصي الدراسة", "ويستوجب",
           "وتعني", "إذ ", "بما يعادل", "بلغت", "بلغ", "تتمثل", "ولم تُعتمد")
# أقسام بنيوية (جدول/قائمة مصادر) لا يُشترط فيها المعجم.
LEXICON_EXEMPT = ("## تاسعاً: خطة التنفيذ (90 يوماً)", "## المصادر وحدود الدراسة")
_META_LINE = re.compile(r"^\*\*(?:المصادر|ما لم يتسنّ توثيقه):")


def _templates() -> dict:
    from silk_study_render import load_templates
    return load_templates()


def expected_headings() -> list[str]:
    """عناوين «##» الحرفية بالترتيب من ملف القوالب."""
    return [b["text"] for b in _templates().get("blocks", [])
            if b.get("type") == "heading" and b["text"].startswith("## ")]


def expected_tables() -> list[tuple[str, ...]]:
    return [tuple(b["columns"]) for b in _templates().get("blocks", [])
            if b.get("type") == "table"]


def _cells(line: str) -> tuple[str, ...]:
    return tuple(c.strip() for c in line.strip().strip("|").split("|"))


def _sections(md: str) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for ln in md.splitlines():
        if ln.startswith("## "):
            out.append((ln.strip(), []))
        elif out:
            out[-1][1].append(ln)
    return out


def lint(md: str, claims: list[dict] | None = None) -> list[dict]:
    v: list[dict] = []
    add = lambda rule, detail: v.append({"rule": rule, "detail": detail})  # noqa: E731
    lines = md.splitlines()

    # (١) العناوين: حرفية، كاملة، بالترتيب.
    got = [ln.strip() for ln in lines if ln.startswith("## ")]
    exp = expected_headings()
    for h in got:
        if h not in exp:
            add("heading_not_literal", h)
    for h in exp:
        if h not in got:
            add("heading_missing", h)
    if [h for h in got if h in exp] != [h for h in exp if h in got]:
        add("heading_order", "ترتيب العناوين يخالف القالب")
    if any(ln.startswith("### ") for ln in lines):
        add("heading_not_literal", "عنوان فرعي «###» خارج القالب")

    # (٢) التعداد النقطي خارج الجداول ممنوع.
    for ln in lines:
        if _LIST.match(ln):
            add("list_outside_table", ln.strip()[:60])

    # (٣) الجداول: رأس كل جدول يطابق أحد الأعمدة الخمسة حرفياً، وكلها حاضرة.
    tables = expected_tables()
    seen: list[tuple[str, ...]] = []
    for i, ln in enumerate(lines):
        if (ln.startswith("|") and i + 1 < len(lines)
                and re.match(r"^\|\s*:?-{3,}", lines[i + 1])):
            head = _cells(ln)
            seen.append(head)
            if head not in tables:
                add("table_columns", " | ".join(head))
    for t in tables:
        if t not in seen:
            add("table_missing", " | ".join(t))

    # (٤) المحظورات والمصطلحات العارية والصيغة الموحدة لمؤشر التركّز.
    prose = "\n".join(ln for ln in lines if not ln.startswith("|"))
    try:
        from silk_reports import _client_forbidden_hits
        for h in _client_forbidden_hits(prose, "ar"):
            add("forbidden", h)
    except Exception:  # noqa: BLE001 — الحارس تحسين لا شرط
        pass
    for t in BARE_TERMS:
        if re.search(rf"(?<![A-Za-z]){t}(?![A-Za-z])", prose):
            add("bare_term", t)
    for alt in HHI_ALTERNATIVES:
        if alt in prose:
            add("hhi_form", f"«{alt}» بدل «{HHI_FORM}»")

    # (٥) كل قسم نثري يحمل صيغة واحدة على الأقل من المعجم.
    for head, body in _sections(md):
        text = " ".join(b for b in body if b.strip() and not b.startswith("|"))
        if head in LEXICON_EXEMPT:
            continue
        if len(text) > 80 and not any(w in text for w in LEXICON):
            add("section_without_lexicon", head)

    # (٦) لا خلط أولي بمكتمل: جملة تجارية بسنة بعد آخر سنة مكتملة تُوسم «أولي».
    m = _LAST_YEAR.search(md)
    if m:
        last = int(m.group(1))
        body = "\n".join(ln for ln in prose.splitlines() if not _META_LINE.match(ln))
        for sent in re.split(r"(?<=[.؛])\s+|\n+", body):
            years = [int(a or b) for a, b in _YEAR.findall(sent)]
            if (any(y > last for y in years) and any(w in sent for w in _TRADE_WORDS)
                    and "أولي" not in sent):
                add("provisional_unmarked", sent.strip()[:80])

    # (٧) لا فراغ قالب متسرِّب.
    if _SLOT.search(prose):
        add("slot_leak", _SLOT.search(prose).group(0))
    # (٨) P3-1: لا ادعاء «يُفاد» بصيغة تقرير في أي موضع.
    if claims:
        from silk_study_claims import conflicts
        v.extend(conflicts(md, claims))
    return v
