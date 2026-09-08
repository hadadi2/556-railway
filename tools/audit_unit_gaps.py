"""تدقيق فجوات الوحدات في الدراسات المخزنة — هدف الدراسة الاحترافية، البند ١.

يمسح قاعدة الإنتاج (قراءة فقط، `sqlite3 mode=ro` — نمط `export_captured.py`)
بحثاً عن دراساتٍ حُجِب فيها رقمٌ بسبب تحويل وحدةٍ (لتر↔كجم/كثافة) تغطيه
ثوابت `CONVERSION_REGISTRY` المسجّلة — عائلة الدرس 84 ودراسة #14. بما أن
العرض يُبنى عند كل طلب تصدير، فإصلاح طبقة الاقتصاد يشفي صادرات هذه الدراسات
تلقائياً — هذه الأداة **للإحصاء والإثبات** لا للترميم.

التشغيل (قشرة خدمة Railway أو محلياً مع نسخة من القاعدة):
    python3 tools/audit_unit_gaps.py                 # قاعدة الإنتاج
    python3 tools/audit_unit_gaps.py --db path.db    # ملف بعينه
    python3 tools/audit_unit_gaps.py --blobs         # المدوّنات العشر محلياً

صفر تعديل على القاعدة؛ المخرج ملخّصُ عدٍّ + معرّفات الدراسات المصابة.
Read-only audit: studies whose report/economics declared a unit-conversion
gap the registry could resolve. Rendering is on-demand, so the layer fix
retro-heals their exports; this tool counts and proves.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
for p in (_REPO_ROOT, _TOOLS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from silk_economics import CONVERSION_REGISTRY, registry_category  # noqa: E402

_ABSENCE = ("غير محسوب", "غير متاح", "not computed", "unavailable",
            "not available")
_SPLIT_RE = re.compile(r"[\n.؛;]+")


def _covered(product: object) -> bool:
    cat = registry_category(product)
    return any(k[2] == cat for k in CONVERSION_REGISTRY)


def _names_conversion(s: str) -> bool:
    low = s.lower()
    if "كثافة" in s or "كثافه" in s or "density" in low:
        return True
    litre = "لتر" in s or "litre" in low or "liter" in low
    kg = "كجم" in s or "كيلوغرام" in s or "kg" in low
    conv = "تحويل" in s or "convert" in low
    return litre and kg and conv


def offending_sentences(text: str) -> list[str]:
    """الجمل التي تعلن فجوة تحويلٍ يغطيه السجل — نفس منطق فحص البوابة
    `_check_unit_conversion_refusal` (المنطقة العمياء نفسها معلنة هناك)."""
    out = []
    for raw in _SPLIT_RE.split(str(text or "")):
        s = raw.strip()
        if not s:
            continue
        if any(a in s or a in s.lower() for a in _ABSENCE) \
                and _names_conversion(s):
            out.append(s[:160])
    return out


def _texts_of(blob: dict) -> str:
    dr = blob.get("deep_research") or {}
    node = dr.get("report") or {}
    # الشكلان: الخام المخزّن (report.report) والعرض المطبّع (report.text).
    parts = [node if isinstance(node, str)
             else str(node.get("text") or node.get("report") or "")]
    for m in (dr.get("missions") or {}).values():
        parts.append(str((m or {}).get("summary") or ""))
    eco = dr.get("economics") or {}
    parts += [str(g) for g in (eco.get("gaps") or [])]
    return "\n".join(parts)


def audit_blob(key: str, blob: dict) -> dict | None:
    product = blob.get("product") or (blob.get("deep_research")
                                      or {}).get("product") or ""
    if not _covered(product):
        return None
    hits = offending_sentences(_texts_of(blob))
    if not hits:
        return None
    return {"id": key, "product": str(product), "hits": hits}


def _db_path(cli: str | None) -> str:
    if cli:
        return cli
    if os.environ.get("SILK_DB"):
        return os.environ["SILK_DB"]
    base = os.environ.get("SILK_DATA_DIR", "data")
    return os.path.join(base, "silk.db")


def audit_db(path: str) -> None:
    uri = f"file:{os.path.abspath(path)}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute("SELECT id, json_blob FROM analyses").fetchall()
    finally:
        con.close()
    total, parsed, affected = len(rows), 0, []
    for rid, raw in rows:
        try:
            blob = json.loads(raw)
        except (TypeError, ValueError):
            continue
        parsed += 1
        hit = audit_blob(str(rid), blob if isinstance(blob, dict) else {})
        if hit:
            affected.append(hit)
    _report(f"قاعدة {path}: {total} دراسة ({parsed} مقروءة)", affected)


def audit_blobs() -> None:
    import importlib
    from gen_verdict_baseline import CANONICAL_BLOBS
    affected = []
    for key, (mod, fn) in sorted(CANONICAL_BLOBS.items()):
        blob = getattr(importlib.import_module(mod), fn)()
        hit = audit_blob(key, blob)
        if hit:
            affected.append(hit)
    _report(f"المدوّنات المجمّدة ({len(CANONICAL_BLOBS)})", affected)


def _report(scope: str, affected: list[dict]) -> None:
    print(f"— تدقيق فجوات الوحدات · {scope}")
    if not affected:
        print("لا دراسة حُجِب فيها رقم بسبب تحويلٍ يغطيه السجل.")
        return
    print(f"{len(affected)} دراسة مصابة (صادراتها تُشفى تلقائياً بعد الفكس):")
    for a in affected:
        print(f"  • {a['id']} ({a['product']}):")
        for h in a["hits"]:
            print(f"      - {h}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", help="مسار قاعدة SQLite (افتراضياً قاعدة الخدمة)")
    ap.add_argument("--blobs", action="store_true",
                    help="افحص المدوّنات القانونية العشر محلياً بدل القاعدة")
    args = ap.parse_args()
    if args.blobs:
        audit_blobs()
        return
    path = _db_path(args.db)
    if not os.path.exists(path):
        print(f"القاعدة غير موجودة: {path} — لا شيء يُفحص (لم يُكتب شيء).")
        return
    audit_db(path)


if __name__ == "__main__":
    main()
