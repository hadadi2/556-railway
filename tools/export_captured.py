#!/usr/bin/env python3
"""تصدير خرج المرحلة-A الحقيقي (الإنتاج) — مستقلٌّ تماماً، بلا استيراد من
هذا الريبو إطلاقاً. Standalone Stage-A capture exporter — zero repo imports.

**لماذا لا "DATABASE_URL"؟** هذا الريبو **لا يستعمل Postgres** — قرارٌ مالكٌ
مستقرّ (`docs/EXECUTION_PLAN.md`: "SQLite stays; Postgres migration deferred").
التخزينُ ملفُّ SQLite واحد (`silk_storage.py`)، ومساره في الإنتاج يُحدَّده
نفسُ متغيّرَي البيئة اللذين يقرؤهما التطبيقُ نفسُه بالضبط:
`SILK_DB` (صريح) ثم `SILK_DATA_DIR/silk.db` (البند الافتراضي على Railway،
عادةً `/data/silk.db`) — **وكلاهما موجودٌ أصلاً** في بيئة قشرة Railway لنفس
الخدمة، فلا حاجة لأيّ متغيّرٍ جديد؛ الأداة تقرأ نفس البيئة التي يقرؤها
التطبيق. راجع أيضاً `SILK_TRACE_DIR`/`SILK_DATA_DIR/traces` لملفات التتبّع.

**قراءةٌ فقط — لا كتابة ولا تعديل على قاعدة الإنتاج مطلقاً**
(`sqlite3.connect(..., mode=ro)`؛ راجع القانون في `CLAUDE.md`: "Never delete
or modify existing data in data/silk.db").

الاستعمال (من قشرة Railway لخدمة سِلك نفسها):

    # ١) تلخيصٌ أولاً — بلا كتابة أيّ ملف، لرؤية ما هو موجود فعلاً:
    python3 export_captured.py

    # ٢) بعد الاطمئنان على الملخّص، صدِّر فعلياً إلى ملفٍّ واحد:
    python3 export_captured.py --out captured_export.json

    # يمكن تجاوز المسارات المكتشَفة تلقائياً عند الحاجة:
    python3 export_captured.py --db /data/silk.db --traces-dir /data/traces

ملفُّ الخرج JSON واحد يحوي:
  {"exported_at": "...", "source": {"db_path":..., "traces_dir":...},
   "analyses": [ {id, product, hs_code, market, created_at, deep_research}, ...],
   "research_missions": [ {analysis_id, mission_key, status, completed_at,
                           market_iso3, report}, ...],
   "trace_files": [ {trace_id, path, event_count, events: [...]}, ...]}

سلّم هذا الملف الواحد للمُنفِّذ ليُطهِّره (لا أسماء/بيانات اتصال حقيقية) قبل
الْتزامه في data/captured/ — لا يُلتزَم هذا الملفّ الخام كما هو أبداً.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys


def _resolve_db_path(explicit: str | None) -> str:
    if explicit:
        return explicit
    env_db = os.environ.get("SILK_DB", "").strip()
    if env_db:
        return env_db
    data_dir = os.environ.get("SILK_DATA_DIR", "").strip()
    if data_dir:
        return os.path.join(data_dir, "silk.db")
    return "data/silk.db"


def _resolve_traces_dir(explicit: str | None) -> str:
    if explicit:
        return explicit
    env_dir = os.environ.get("SILK_TRACE_DIR", "").strip()
    if env_dir:
        return env_dir
    data_dir = os.environ.get("SILK_DATA_DIR", "").strip()
    if data_dir:
        return os.path.join(data_dir, "traces")
    return "data/traces"


def _open_readonly(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        print(f"خطأ: لا ملف قاعدة بيانات في المسار: {db_path}", file=sys.stderr)
        sys.exit(1)
    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=10)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _load_analyses(con: sqlite3.Connection) -> list:
    """كل صفوف `analyses`، مع تفسير `json_blob` بحذرٍ (فشل تفسيرٍ = تجاوزٌ
    معلَن، لا كسر الأداة كلها)."""
    if not _table_exists(con, "analyses"):
        return []
    cols = [r[1] for r in con.execute("PRAGMA table_info(analyses)").fetchall()]
    rows = con.execute(f"SELECT {', '.join(cols)} FROM analyses").fetchall()
    out = []
    for row in rows:
        rec = dict(zip(cols, row))
        blob_raw = rec.get("json_blob")
        parsed = None
        parse_error = None
        if blob_raw:
            try:
                parsed = json.loads(blob_raw)
            except Exception as exc:                       # noqa: BLE001
                parse_error = repr(exc)
        rec["_parsed_blob"] = parsed
        rec["_parse_error"] = parse_error
        rec.pop("json_blob", None)          # يُستبدَل بـ_parsed_blob أدناه
        rec.pop("request_json", None)       # قد يحمل بيانات طلب حسّاسة
        out.append(rec)
    return out


def _has_real_missions(parsed_blob) -> bool:
    if not isinstance(parsed_blob, dict):
        return False
    dr = parsed_blob.get("deep_research")
    if not isinstance(dr, dict):
        return False
    missions = dr.get("missions")
    return isinstance(missions, dict) and len(missions) > 0


def _load_research_missions(con: sqlite3.Connection) -> list:
    if not _table_exists(con, "research_missions"):
        return []
    cols = [r[1] for r in
           con.execute("PRAGMA table_info(research_missions)").fetchall()]
    rows = con.execute(f"SELECT {', '.join(cols)} FROM research_missions").fetchall()
    out = []
    for row in rows:
        rec = dict(zip(cols, row))
        report_raw = rec.get("report_json")
        if report_raw:
            try:
                rec["report"] = json.loads(report_raw)
            except Exception as exc:                       # noqa: BLE001
                rec["report"] = None
                rec["_parse_error"] = repr(exc)
        rec.pop("report_json", None)
        out.append(rec)
    return out


def _load_trace_files(traces_dir: str) -> list:
    if not os.path.isdir(traces_dir):
        return []
    out = []
    for path in sorted(glob.glob(os.path.join(traces_dir, "*.jsonl"))):
        trace_id = os.path.splitext(os.path.basename(path))[0]
        events = []
        parse_errors = 0
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except Exception:                       # noqa: BLE001
                        parse_errors += 1
        except Exception as exc:                            # noqa: BLE001
            out.append({"trace_id": trace_id, "path": path,
                       "read_error": repr(exc), "events": []})
            continue
        out.append({"trace_id": trace_id, "path": path,
                   "event_count": len(events), "parse_errors": parse_errors,
                   "events": events})
    return out


def _date_range(values: list) -> tuple:
    clean = sorted(v for v in values if v)
    if not clean:
        return None, None
    return clean[0], clean[-1]


def build_summary(analyses: list, missions: list, traces: list) -> dict:
    qualifying = [a for a in analyses if _has_real_missions(a.get("_parsed_blob"))]
    parse_failures = [a for a in analyses if a.get("_parse_error")]
    lo_all, hi_all = _date_range([a.get("created_at") for a in analyses])
    lo_q, hi_q = _date_range([a.get("created_at") for a in qualifying])
    distinct_mission_analysis_ids = {m.get("analysis_id") for m in missions}
    return {
        "analyses_total": len(analyses),
        "analyses_with_real_deep_research_missions": len(qualifying),
        "analyses_json_blob_parse_failures": len(parse_failures),
        "analyses_created_at_range_all": [lo_all, hi_all],
        "analyses_created_at_range_qualifying": [lo_q, hi_q],
        "research_missions_rows_total": len(missions),
        "research_missions_distinct_analysis_ids": len(distinct_mission_analysis_ids),
        "trace_files_found": len(traces),
        "trace_files_total_events": sum(t.get("event_count", 0) for t in traces),
    }


def print_summary(summary: dict, db_path: str, traces_dir: str) -> None:
    print("── مصدر البيانات ─────────────────────────────────────────")
    print(f"  قاعدة SQLite: {db_path}")
    print(f"  مجلّد التتبّع: {traces_dir}")
    print()
    print("── الملخّص (بلا كتابة أيّ ملف بعد) ──────────────────────────")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print()
    if summary["analyses_with_real_deep_research_missions"] == 0:
        print("تنبيه: صفر صفٍّ يحمل deep_research.missions فعلياً — لا توجد "
             "دراسةٌ مكتملة يمكن تصديرها من هذه القاعدة.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None, help="مسار صريح لملف silk.db "
                    "(افتراضياً: SILK_DB ثم SILK_DATA_DIR/silk.db ثم data/silk.db)")
    ap.add_argument("--traces-dir", default=None, help="مسار صريح لمجلّد التتبّع "
                    "(افتراضياً: SILK_TRACE_DIR ثم SILK_DATA_DIR/traces ثم data/traces)")
    ap.add_argument("--out", default=None, help="مسار ملفّ الخرج JSON — إن "
                    "غاب، تُطبَع الملخّصات فقط بلا كتابة أيّ ملف")
    args = ap.parse_args()

    db_path = _resolve_db_path(args.db)
    traces_dir = _resolve_traces_dir(args.traces_dir)

    con = _open_readonly(db_path)
    try:
        analyses = _load_analyses(con)
        missions = _load_research_missions(con)
    finally:
        con.close()
    traces = _load_trace_files(traces_dir)

    summary = build_summary(analyses, missions, traces)
    print_summary(summary, db_path, traces_dir)

    if not args.out:
        print()
        print("لم يُكتَب أيّ ملفّ (مرّر --out PATH للتصدير الفعلي بعد "
             "مراجعة الملخّص أعلاه).")
        return

    qualifying = [a for a in analyses if _has_real_missions(a.get("_parsed_blob"))]

    def _export_row(a: dict) -> dict:
        # `market` هنا مفتاحٌ قاموسيّ واحد (لا قائمة `markets`) — يضبطه
        # api.py عند بناء نتيجة /research (raw dict {iso3, m49, iso2,
        # name_en, name_ar})، بجوار deep_research في نفس القاموس.
        pb = a.get("_parsed_blob") or {}
        return {
            "id": a.get("id"), "product": pb.get("product"),
            "hs_code": pb.get("hs_code"), "market": pb.get("market"),
            "created_at": a.get("created_at"), "status": a.get("status"),
            "deep_research": pb.get("deep_research"),
        }

    export = {
        "exported_at_note": "الطابع الزمني يُضاف من يستهلك هذا الملف — لا "
                            "Date.now() هنا (سكربتٌ حتميّ التكرار)",
        "source": {"db_path": db_path, "traces_dir": traces_dir},
        "summary": summary,
        "analyses": [_export_row(a) for a in qualifying],
        "research_missions": missions,
        "trace_files": traces,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(export, fh, ensure_ascii=False, indent=2)
    print(f"كُتب: {args.out} ({len(qualifying)} دراسة مؤهَّلة، "
         f"{len(missions)} صفّ نقطة تفتيش، {len(traces)} ملفّ تتبّع)")
    print("سلّم هذا الملفّ للمُنفِّذ للتطهير والالتزام في data/captured/ — "
         "لا يُلتزَم خاماً كما هو.")


if __name__ == "__main__":
    main()
