"""جرد إطلاق أنماط الاستدلال — هدف الدراسة الاحترافية، البند ٦.

يطبّق `silk_inference.derive_hypotheses` على المدونات العشر المجمّدة (أو
قاعدة الإنتاج قراءةً فقط) ويطبع أي نمط أطلق على أي دراسة — مادة بند
التقرير النهائي «أي نمط أطلق على أي دراسة مخزنة»، وكاشف النمط الميت
(صفر إطلاق دائم) والنمط عديم القيمة (إطلاق على كل شيء).

    python3 tools/inference_audit.py --blobs
    python3 tools/inference_audit.py --db data/silk.db
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

from silk_inference import derive_hypotheses  # noqa: E402


def _audit(items: "list[tuple[str, dict]]") -> None:
    per_pattern: dict[str, list[str]] = {}
    for key, dr in items:
        hyps = derive_hypotheses(dr)
        names = [h["pattern"] for h in hyps]
        print(f"• {key}: " + ("، ".join(names) if names else "لا إطلاق"))
        for h in hyps:
            per_pattern.setdefault(h["pattern"], []).append(key)
    print("\n— حسب النمط:")
    from silk_inference import _PATTERNS
    all_names = [p.__name__.lstrip("_p_") for p in _PATTERNS]
    for name in ("channel_redirection", "wrong_heading", "unserved_niche",
                 "import_volatility", "no_seasonal_stockpiling",
                 "currency_stable"):
        fired = per_pattern.get(name, [])
        tag = ("⚠ لم يطلق على أي دراسة" if not fired else
               ("⚠ أطلق على الكل" if len(fired) == len(items) and
                len(items) > 2 else ""))
        print(f"  {name}: {len(fired)} ({'، '.join(fired)}) {tag}".rstrip())
    _ = all_names


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--blobs", action="store_true")
    g.add_argument("--db")
    args = ap.parse_args()
    items: list[tuple[str, dict]] = []
    if args.blobs:
        import importlib
        from gen_verdict_baseline import CANONICAL_BLOBS
        for key, (mod, fn) in sorted(CANONICAL_BLOBS.items()):
            blob = getattr(importlib.import_module(mod), fn)()
            items.append((key, blob.get("deep_research") or {}))
    else:
        uri = f"file:{os.path.abspath(args.db)}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            for rid, raw in con.execute(
                    "SELECT id, json_blob FROM analyses").fetchall():
                try:
                    blob = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                dr = (blob or {}).get("deep_research") or {}
                if dr.get("missions"):
                    items.append((str(rid), dr))
        finally:
            con.close()
    _audit(items)


if __name__ == "__main__":
    main()
