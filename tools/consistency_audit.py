"""قياسُ تناقضات التقارير قبل الإصلاح وبعده — قراءةٌ محضة (الدرس ٢٦٢).

طلبُ المالك (2026-09-19، بلاغ التقرير 6): «أعطني جدولاً بعدد التناقضات قبل
الإصلاح وبعده». الأداةُ تُجيب ذلك بأثرٍ لا بحدس: تبني العرضَ من كل مدوّنةٍ
قانونية (أو من قاعدة الإنتاج) وتُشغّل فحصَ سجلّ الحقائق على النصّ المُصيَّر
فعلاً، وتعدّ الملاحظات.

صفرُ كتابة، صفرُ نداءٍ مدفوع، صفرُ شبكة: `build_view` + `render_markdown` +
`silk_fact_ledger.check` حسابٌ محضٌ فوق المخزَّن. قاعدةُ الإنتاج تُفتَح
`mode=ro` (نمط `tools/audit_study_reports.py` و`export_captured.py`).

التشغيل:

    python3 tools/consistency_audit.py                # المدوّنات + العيّنات
    python3 tools/consistency_audit.py --json
    python3 tools/consistency_audit.py --db /data/silk.db        # الإنتاج
    python3 tools/consistency_audit.py --db /data/silk.db --id 6 # دراسةٌ بعينها

«قبل» تُقاس بإطفاء السجلّ (`SILK_FACT_LEDGER_OFF=1`) فيعود قارئُ التعرفة
إلى مساره الضيّق القديم — فرقُ العمودين هو أثرُ الإصلاح مقيساً لا مُدّعىً.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
for _p in (_REPO_ROOT, _TOOLS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LEGACY_FLAG = "SILK_FACT_LEDGER_OFF"


def _audit_one(blob: dict) -> dict:
    """ملاحظاتُ الاتساق لنتيجةٍ واحدة — {count, checks, tariff}."""
    import silk_fact_ledger as FL
    import silk_render
    import silk_reports
    view = silk_render.build_view(blob)
    try:
        text = silk_reports.render_markdown(view)
    except Exception as exc:  # noqa: BLE001 — تقريرٌ يتعذّر تصييره يُعلَن
        return {"count": None, "checks": [f"render_failed: {exc}"],
                "tariff": None}
    findings = FL.check(view, text)
    entry = ((view.get("ledger") or {}).get("entries") or {}).get(
        "tariff_applied_pct") or {}
    eco = (view.get("deep_research") or {}).get("economics") or {}
    return {"count": len(findings),
            "checks": sorted({f["check"] for f in findings}),
            "tariff": entry.get("value"),
            "tariff_status": entry.get("status"),
            "max_exw": (eco.get("reverse_solve") or {}).get("max_exw")}


def _with_legacy(blob: dict) -> dict:
    """القياسُ بسلوك ما قبل الإصلاح — قارئُ التعرفة الضيّق."""
    prev = os.environ.get(LEGACY_FLAG)
    os.environ[LEGACY_FLAG] = "1"
    try:
        _reload_readers()
        return _audit_one(blob)
    finally:
        if prev is None:
            os.environ.pop(LEGACY_FLAG, None)
        else:
            os.environ[LEGACY_FLAG] = prev
        _reload_readers()


def _reload_readers() -> None:
    import importlib
    import silk_deep_pillars
    import silk_economics
    importlib.reload(silk_economics)
    importlib.reload(silk_deep_pillars)


def _canonical_rows() -> list:
    import importlib
    from tools import gen_verdict_baseline as B
    rows = []
    for key in sorted(B.CANONICAL_BLOBS):
        mod, fn = B.CANONICAL_BLOBS[key]
        blob = getattr(importlib.import_module(mod), fn)()
        rows.append((key, blob))
    return rows


def _db_rows(db_path: str, only_id: "int | None") -> list:
    """صفوفُ التحليلات من قاعدة الإنتاج — **قراءةٌ فقط** (`mode=ro`)."""
    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT id, result_json FROM analyses"
        args: tuple = ()
        if only_id is not None:
            sql += " WHERE id = ?"
            args = (int(only_id),)
        sql += " ORDER BY id"
        out = []
        for row in conn.execute(sql, args):
            try:
                out.append((str(row["id"]), json.loads(row["result_json"])))
            except Exception as exc:  # noqa: BLE001 — صفٌّ تالفٌ يُعلَن
                out.append((str(row["id"]), {"_error": str(exc)}))
        return out
    finally:
        conn.close()


def audit(rows: list, legacy: bool = True) -> list:
    out = []
    for key, blob in rows:
        if blob.get("_error"):
            out.append({"report": key, "before": None, "after": None,
                        "checks": [blob["_error"]]})
            continue
        after = _audit_one(blob)
        before = _with_legacy(blob) if legacy else {"count": None,
                                                    "checks": []}
        out.append({"report": key,
                    "before": before.get("count"),
                    "after": after.get("count"),
                    "checks": after.get("checks"),
                    "tariff_before": before.get("tariff"),
                    "tariff_after": after.get("tariff"),
                    "max_exw_before": before.get("max_exw"),
                    "max_exw_after": after.get("max_exw")})
    return out


def _print_table(rows: list) -> None:
    print(f"{'التقرير':26} {'قبل':>5} {'بعد':>5}  {'تعرفة قبل/بعد':>18}  الأصناف")
    for r in rows:
        tb, ta = r.get("tariff_before"), r.get("tariff_after")
        tcol = f"{tb if tb is not None else '—'}/{ta if ta is not None else '—'}"
        print(f"{r['report']:26} {str(r['before']):>5} {str(r['after']):>5}  "
              f"{tcol:>18}  {'، '.join(r.get('checks') or []) or '—'}")
    tot_b = sum(r["before"] for r in rows if isinstance(r["before"], int))
    tot_a = sum(r["after"] for r in rows if isinstance(r["after"], int))
    print(f"\nالمجموع: قبل {tot_b} · بعد {tot_a}")
    fixed = [r["report"] for r in rows
             if r.get("tariff_before") is None and r.get("tariff_after") is not None]
    if fixed:
        print("تقاريرُ حُسب اقتصادُها على تعرفة 0% بينما البعثة تحملها: "
              + "، ".join(fixed))
        for r in rows:
            if r["report"] in fixed and r.get("max_exw_before") is not None:
                print(f"  {r['report']}: أقصى سعر مصنع "
                      f"{r['max_exw_before']} → {r['max_exw_after']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", help="قاعدةُ الإنتاج (قراءةٌ فقط)")
    ap.add_argument("--id", type=int, help="دراسةٌ بعينها (مع --db)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-legacy", action="store_true",
                    help="لا تقِس عمودَ «قبل» (أسرع)")
    args = ap.parse_args()
    rows = _db_rows(args.db, args.id) if args.db else _canonical_rows()
    result = audit(rows, legacy=not args.no_legacy)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        _print_table(result)


if __name__ == "__main__":
    main()
