"""تقرير معايرة النثر — أداة نقرة المالك (هدف الدراسة الاحترافية، البند ٥).

تقيس نص أي تقرير بعدّاد النثر الحتمي (`silk_prose_meter`) وتطبع المقاييس
مع أسوأ الشواهد — قبل/بعد أي تعديل موجّه، وعلى كل دراسة حية مسلَّمة. صفر
نموذج، صفر شبكة، صفر تكلفة.

التشغيل:
    python3 tools/prose_report.py --file report.md
    python3 tools/prose_report.py --analysis-id 14        # من قاعدة الخدمة
    python3 tools/prose_report.py --blobs                 # المدونات العشر
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
for p in (_REPO_ROOT, _TOOLS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from silk_prose_meter import analyze, report_lines  # noqa: E402


def _report_text(blob: dict) -> str:
    """نص التقرير من الشكلين: الخام المخزّن (report.report) والعرض (report.text)."""
    node = ((blob or {}).get("deep_research") or {}).get("report") or {}
    if isinstance(node, str):
        return node
    return str(node.get("text") or node.get("report") or "")



def _print(title: str, text: str) -> None:
    print(f"\n═══ {title} ═══")
    if not (text or "").strip():
        print("لا نص تقرير — لا قياس.")
        return
    for line in report_lines(analyze(text)):
        print(line)


def _db_text(analysis_id: int) -> str:
    path = os.environ.get("SILK_DB") or os.path.join(
        os.environ.get("SILK_DATA_DIR", "data"), "silk.db")
    uri = f"file:{os.path.abspath(path)}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        row = con.execute("SELECT json_blob FROM analyses WHERE id = ?",
                          (analysis_id,)).fetchone()
    finally:
        con.close()
    if not row:
        raise SystemExit(f"لا تحليل بالمعرف {analysis_id} في {path}")
    blob = json.loads(row[0])
    return _report_text(blob)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--file")
    g.add_argument("--analysis-id", type=int)
    g.add_argument("--blobs", action="store_true")
    args = ap.parse_args()
    if args.file:
        _print(args.file, open(args.file, encoding="utf-8").read())
    elif args.analysis_id:
        _print(f"analysis {args.analysis_id}", _db_text(args.analysis_id))
    else:
        import importlib
        from gen_verdict_baseline import CANONICAL_BLOBS
        for key, (mod, fn) in sorted(CANONICAL_BLOBS.items()):
            blob = getattr(importlib.import_module(mod), fn)()
            text = _report_text(blob)
            _print(key, text)


if __name__ == "__main__":
    main()
