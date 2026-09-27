"""تصدير نمط «دراسة السوق» — Markdown/Word/PDF من محرك القوالب (P2-1/P2-5).

`?style=study` على مسارات التصدير: الحالة من `silk_study_case.build_case` (نتيجة
`/research` المخزَّنة)، والمعرفة من `data/product_knowledge/<hs>_<iso2>.yaml` إن كانت
approved، والنص من `silk_study_render`. Word عبر python-docx بهوية سِلك RTL نفسها
(`_apply_rtl`/`_add_table`)، وPDF عبر `docx_to_pdf` الموجود. لا نداء نموذج هنا.
"""
from __future__ import annotations

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def study_case(found: dict) -> dict:
    from silk_study_case import build_case
    return build_case(found)


def study_markdown(found: dict, llm_fill=None) -> tuple[str, dict]:
    """(نص Markdown، تقرير التعبئة {gaps, llm_slots, missing})."""
    from silk_study_render import Renderer, load_knowledge
    case = found.get("study_case") or study_case(found)
    kn = load_knowledge(case["product"]["hs"], case["market"].get("iso2") or "")
    r = Renderer(case, kn, llm_fill=llm_fill)
    md = r.render()
    return md, {"gaps": list(r.gaps), "llm_slots": list(r.llm_slots), "missing": list(r.missing)}


def _add_runs(par, text: str) -> None:
    pos = 0
    for m in _BOLD.finditer(text):
        if m.start() > pos:
            par.add_run(text[pos:m.start()])
        par.add_run(m.group(1)).bold = True
        pos = m.end()
    if pos < len(text):
        par.add_run(text[pos:])


def markdown_to_docx(md: str, path: str, lang: str = "ar") -> str:
    """Markdown الدراسة → Word: العناوين والتسميات العريضة والجداول الخمسة حرفياً."""
    try:
        from docx import Document
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("python-docx غير مثبتة — pip install python-docx") from e
    import silk_reports as R
    doc = Document()
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln.strip() or ln.strip() == "---":
            i += 1
            continue
        if ln.startswith("# "):
            doc.add_heading(ln[2:].strip(), level=0)
        elif ln.startswith("## "):
            doc.add_heading(ln[3:].strip(), level=1)
        elif ln.startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(lines[i])
                i += 1
            cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in block
                     if not re.match(r"^\|?\s*-{3,}", row.replace("|", "|").strip())]
            cells = [c for c in cells if not all(re.fullmatch(r"-+", x or "-") for x in c)]
            if cells:
                R._add_table(doc, cells[0], cells[1:])
            continue
        else:
            p = doc.add_paragraph()
            _add_runs(p, ln.strip())
        i += 1
    R._apply_rtl(doc)
    blob = "\n".join(p.text for p in doc.paragraphs)
    hits = R._client_forbidden_hits(blob, lang)
    if hits:
        raise R.ReportGateError("تصدير الدراسة يحوي مصطلحاً ممنوعاً: " + "؛ ".join(hits[:5]))
    doc.save(path)
    return path


def study_docx(found: dict, path: str) -> tuple[str, dict]:
    md, meta = study_markdown(found)
    return markdown_to_docx(md, path), meta
