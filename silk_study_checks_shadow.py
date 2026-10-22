"""فحوصُ الدراسة الحتمية في وضع الظلّ — PR-B البند (ب)، الدرس ٣٠٢.

قرار المالك: فحوصُ F1–F7 (`silk_study_checks`) تعمل على كلّ دراسةٍ **تحذيراً فقط** لأسبوع
مع تسجيل النتائج، ثم تتحوّل إلى رفضٍ فحصاً فحصاً (البند ج) بعد قراءة تقرير الإنذارات.

* رايةٌ واحدة قابلة للعكس: `SILK_STUDY_CHECKS` = `shadow` (الافتراضي) أو `off`. لا قيمةَ رفضٍ
  في هذا البند؛ أيُّ قيمةٍ أخرى تُقرأ ظلّاً.
* الظلُّ لا يحجب ولا يمسّ النتيجةَ ولا مستندَ العميل ولا حكمَ البوّابة — يقرأ ويسجّل فقط.
* التخزين: جدولٌ حلقيّ `study_checks` في قاعدة سجلّ المشغّل (`silk_ops_log` — مستقلّةٌ عن
  `silk.db`)، سقفُه `SILK_STUDY_CHECKS_CAP` (افتراضياً 2000 صفّ).
* أيُّ عطلٍ قناةٌ جانبية صامتة (تحذيرٌ في السجلّ) — لا يكسر التشغيلة.

Shadow-mode wiring of the deterministic study checks: record, never block.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import logging
import os

log = logging.getLogger(__name__)

_DEFAULT_CAP = 2000


def mode() -> str:
    """`off` يطفئ الظلّ؛ كلُّ ما سواه (ومنه الغياب) `shadow`."""
    return "off" if os.environ.get("SILK_STUDY_CHECKS", "").strip().lower() == "off" else "shadow"


def _cap() -> int:
    try:
        return max(1, int(os.environ.get("SILK_STUDY_CHECKS_CAP", _DEFAULT_CAP)))
    except ValueError:
        return _DEFAULT_CAP


@contextlib.contextmanager
def _open():
    """اتصالٌ يُغلَق دائماً بقاعدة سجلّ المشغّل (نمطُ `silk_ops_log._open`)."""
    import silk_ops_log
    import silk_sqlite
    conn = silk_sqlite.connect(silk_ops_log._db_path())
    try:
        with conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS study_checks ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER, source TEXT NOT NULL, "
                "statuses_json TEXT NOT NULL, fails_json TEXT NOT NULL, created_at TEXT NOT NULL)")
            yield conn
    finally:
        conn.close()


def _summarize(findings: list) -> tuple:
    statuses = {f.check: f.status for f in findings}
    fails = []
    for f in findings:
        if f.status != "FAIL":
            continue
        items = [i for i in (f.items or []) if isinstance(i, dict)]
        bad = [i for i in items if i.get("status") == "FAIL"] or items
        first = bad[0] if bad else {}
        fails.append({"check": f.check, "note": str(f.note or "")[:200],
                      "why": str(first.get("why") or "")[:300],
                      "where": str(first.get("where") or "")[:80],
                      "count": len(bad)})
    return statuses, fails


def run_and_record(found: dict, analysis_id: "int | None" = None,
                   source: str = "pipeline") -> "dict | None":
    """شغّل F1–F7 على نتيجةٍ كاملة وسجّلها — يعيد الملخّص، أو None (مطفأ/تعذّر)."""
    if mode() == "off":
        return None
    dr = (found or {}).get("deep_research") if isinstance(found, dict) else None
    rep = (dr or {}).get("report") if isinstance(dr, dict) else None
    if not (isinstance(rep, dict) and (rep.get("report") or rep.get("text"))):
        return None                      # لا تقريرَ كاتبٍ = ليست دراسةً تُفحص
    if str(found.get("lang") or "ar").lower().startswith("en"):
        return None                      # أنماطُ F1–F7 عربية — قياسُ تقريرٍ إنجليزيّ يضلّل التقرير
    try:
        import silk_study_checks as C
        doc = C.StudyDoc.from_result(found)
        statuses, fails = _summarize(C.run_all(doc))
    except Exception as e:  # noqa: BLE001 — ظلٌّ لا يكسر التشغيلة
        log.warning("study checks shadow skipped (analysis %s): %s", analysis_id, e)
        return None
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with _open() as conn:
            if source == "post_deploy" and analysis_id is not None:
                # كلُّ إقلاعٍ يعيد فحصَ الدراسات نفسها — صفٌّ واحدٌ لكلّ دراسة لا صفٌّ لكلّ
                # إقلاع (لا يُغرِق الحلقةَ ولا يضاعف التقرير، مراجعة §58).
                conn.execute("DELETE FROM study_checks WHERE source = 'post_deploy' "
                             "AND analysis_id = ?", (analysis_id,))
            conn.execute(
                "INSERT INTO study_checks (analysis_id, source, statuses_json, fails_json, "
                "created_at) VALUES (?, ?, ?, ?, ?)",
                (analysis_id, source, json.dumps(statuses, ensure_ascii=False),
                 json.dumps(fails, ensure_ascii=False), now))
            conn.execute(
                "DELETE FROM study_checks WHERE id NOT IN (SELECT id FROM study_checks "
                "ORDER BY id DESC LIMIT ?)", (_cap(),))
    except Exception as e:  # noqa: BLE001
        log.warning("study checks shadow not stored: %s", e)
    return {"analysis_id": analysis_id, "source": source, "statuses": statuses,
            "fails": fails, "created_at": now}


def recent(n: int = 20) -> list:
    """أحدثُ n تشغيلة (الأحدث أولاً)."""
    try:
        with _open() as conn:
            rows = conn.execute(
                "SELECT analysis_id, source, statuses_json, fails_json, created_at "
                "FROM study_checks ORDER BY id DESC LIMIT ?", (max(1, int(n)),)).fetchall()
    except Exception as e:  # noqa: BLE001
        log.warning("study checks shadow read failed: %s", e)
        return []
    out = []
    for r in rows:
        try:      # صفٌّ تالف لا يُسقط القراءة (القراءةُ تتدهور بأمان، عقدُ سجلّ المشغّل)
            out.append({"analysis_id": r[0], "source": r[1],
                        "statuses": json.loads(r[2] or "{}"),
                        "fails": json.loads(r[3] or "[]"), "created_at": r[4]})
        except ValueError:
            continue
    return out


def report(days: int = 7) -> dict:
    """تقريرُ الأسبوع: لكلّ فحصٍ عددُ PASS/WARN/FAIL/SKIP في النافذة، وعددُ الدراسات."""
    since = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=max(1, int(days)))).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [r for r in recent(_cap()) if r["created_at"] >= since]

    def _count(rs: list) -> dict:
        by: dict = {}
        for r in rs:
            for chk, st in r["statuses"].items():
                by.setdefault(chk, {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0})
                by[chk][st] = by[chk].get(st, 0) + 1
        return dict(sorted(by.items()))
    # مراجعة §58: آخرُ حالةٍ لكلّ دراسة (والصفُّ بلا معرّفٍ يُعدّ وحدَه) — تكرارُ الفحص على
    # الدراسة نفسها (إعادةُ توليد، تنقيح، إقلاع) لا يضاعف الإنذار.
    latest: dict = {}
    for i, r in enumerate(rows):                       # recent() الأحدثُ أولاً
        latest.setdefault(r["analysis_id"] if r["analysis_id"] is not None else f"_{i}", r)
    uniq = list(latest.values())
    return {"mode": mode(), "days": int(days), "since": since, "runs": len(rows),
            "studies": len({r["analysis_id"] for r in rows if r["analysis_id"] is not None}),
            "by_check": _count(uniq),
            "by_source": {s: _count([r for r in rows if r["source"] == s])
                          for s in sorted({r["source"] for r in rows})}}


def run_async(found: dict, analysis_id: "int | None" = None, source: str = "pipeline"):
    """الظلُّ في خيطٍ جانبيّ على **نسخة** — لا يضيف زمناً لمسار الإكمال ولا يقرأ قاموساً
    يتغيّر تحته (مراجعة §58). يعيد الخيط أو None (مطفأ/تعذّر النسخ)."""
    if mode() == "off":
        return None
    try:
        import copy
        import threading
        snap = copy.deepcopy(found)
    except Exception as e:  # noqa: BLE001
        log.warning("study checks shadow copy failed: %s", e)
        return None
    t = threading.Thread(target=run_and_record, args=(snap, analysis_id, source),
                         daemon=True, name="silk-study-checks-shadow")
    t.start()
    return t


def audit_stored(path: "str | None" = None, limit: int = 200) -> int:
    """بعد النشر: شغّل الظلَّ على أحدث الدراسات العميقة المخزَّنة **بالشيفرة الحالية** —
    العرضُ المخزَّن يُسقَط فيُبنى من جديد (لا يُقاس عرضُ الشيفرة التي شغّلت الدراسة)،
    ودراسةٌ واحدة في الذاكرة كلَّ مرّة (مراجعة §58)."""
    if mode() == "off":
        return 0
    import silk_storage
    db = path or silk_storage._db_path()
    if not os.path.exists(db):
        return 0
    with silk_storage._open(db) as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM analyses WHERE kind = 'research' ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),)).fetchall()]
    n = 0
    for aid in ids:
        try:
            blob = silk_storage.get_analysis(aid, path=db) or {}
        except Exception as e:  # noqa: BLE001
            log.warning("study checks shadow: analysis %s unreadable: %s", aid, e)
            continue
        blob.pop("view", None)
        if run_and_record(blob, analysis_id=aid, source="post_deploy"):
            n += 1
    return n
