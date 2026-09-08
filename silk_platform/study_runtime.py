"""مُشرِف تشغيلات الدراسات — the durable study-run runtime (R2 / RC-1، أمر المالك 2026-09-02).

لماذا: كانت تشغيلةُ الدراسة خيطَ daemon داخل عملية الويب وسجلُّها الوحيد
`studies.state='in_progress'` + قاموسٌ في الذاكرة (`engine_bridge._ACTIVE`).
لا نبضةَ حياة ولا هويّةَ إقلاع ولا سقفَ تزامن ولا إلغاء ولا ختمَ إغلاق — فإعادةُ
النشر تترك «قيد الإعداد» ساعةً كاملة، والتشغيلةُ المتجاوزة تُنفق بعد إرجاع صفّها.

هنا **القاعدة هي المرجع** (`study_runs`، الترحيل 018) لكل محاولة تنفيذ:
queued → running → completed | failed | interrupted | cancelled.

- الإطلاق يُدرج صفّ `queued` في معاملة المطالبة نفسها، ثم `dispatch()` يطالب
  بأقدم صفٍّ منتظر تحت `BEGIN IMMEDIATE` (SQLite هو الحَكَم، لا قفل بايثون) ما دام
  عددُ الجاري دون `SILK_PLATFORM_MAX_CONCURRENT_RUNS`؛ وإلا بقي منتظراً بلا خيط.
- خيطُ التشغيلة هو `engine_bridge._thread_body` نفسُه بلا تغيير في فروعه — يلفّه
  حدثُ إلغاءٍ تعاونيّ في contextvar (`silk_context.cancel_context`) يقرؤه الخطُّ
  العميق عند حدود مراحله.
- المشرفُ خيطٌ واحد (daemon) ينبض لصفوف هذه العملية، يلتقط أعلام الإلغاء من
  القاعدة، يُوقف المتجاوزَ مهلتَه، ويُقاطع صفوفاً انقطعت نبضتُها (بأيّ إقلاع).
- الإغلاق (`add_event_handler("shutdown")` في `mount()`) يوسم تشغيلات هذه العملية
  `interrupted` فوراً؛ والإقلاعُ يكنس ما انقطعت نبضتُه ثم يبدأ المنتظِر.
- **لا استئناف ذاتيّ** — قاعدة الريبو «التعافي صريح لا ذاتي»: الدراسة تعود
  مسودّةً بمؤشّر استئنافها وإشعارها، والمصنع يعيد الإطلاق بالقروش لا بالدولارات.

Threads suffice (settled owner decision — no queues, no Redis); the DB owns state.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import logging
import os
import threading
import time
import uuid

from . import audit, engine_bridge, lifecycle
from .db import connect, now_iso

log = logging.getLogger(__name__)

# هويّة هذا الإقلاع — تُقرأ من الوحدة وقت النداء (لا تُلتقط في وسيط افتراضي)
# كي تستطيع الاختبارات تقليد إقلاعٍ ثانٍ بتطعيمها.
BOOT_ID: str = uuid.uuid4().hex

ACTIVE_STATES = ("queued", "running")

_STOPPING = False
_HANDLES: dict[int, "RunHandle"] = {}
_SUPERVISOR: threading.Thread | None = None
_SUP_LOCK = threading.Lock()
_SUP_STOP = threading.Event()


def boot_id() -> str:
    """هويّة الإقلاع الحالية — read at call time so tests can monkeypatch."""
    return BOOT_ID


# ── قراءة البيئة بنمط البيت · env readers (strip, empty=unset, floor) ────────
def _env_float(name: str, default: float, floor: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        val = float(raw) if raw else default
    except ValueError:
        val = default
    return max(floor, val)


def max_concurrent() -> int:
    """سقف التشغيلات المتزامنة في هذه العملية — `SILK_PLATFORM_MAX_CONCURRENT_RUNS`
    (الافتراضي ٣، وأدناه ١). Bounded in-process execution, not horizontal scale."""
    return int(_env_float("SILK_PLATFORM_MAX_CONCURRENT_RUNS", 3, 1))


def heartbeat_s() -> float:
    """فترة النبضة بالثواني — `SILK_PLATFORM_HEARTBEAT_S` (الافتراضي ٣٠، أدناه ١)."""
    return _env_float("SILK_PLATFORM_HEARTBEAT_S", 30.0, 1.0)


def stale_s() -> float:
    """عتبة اعتبار تشغيلةٍ جارية ميتة — `SILK_PLATFORM_RUN_STALE_S` (الافتراضي
    ٣٠٠، وأدناه أربعُ نبضات: نبضةٌ بطيئة واحدة — انتظار قفل SQLite حتى ٣٠ ث —
    لا يجوز أن تُميت تشغيلةً حيّة)."""
    return _env_float("SILK_PLATFORM_RUN_STALE_S", 300.0, 4.0 * heartbeat_s())


def supervisor_enabled() -> bool:
    """خيط المشرف مشغَّل افتراضياً؛ `SILK_PLATFORM_RUN_SUPERVISOR=0` يطفئه
    (الحزمة الهرمتية تفعل ذلك وتستدعي `tick()` صراحةً)."""
    return os.environ.get("SILK_PLATFORM_RUN_SUPERVISOR", "1").strip() != "0"


@dataclasses.dataclass
class RunHandle:
    """مقبض تشغيلةٍ حيّة في هذه العملية — in-memory view of one running row."""
    run_id: int
    study_id: int
    account_id: int
    run_token: str
    mode: str
    started_monotonic: float
    cancel: threading.Event = dataclasses.field(default_factory=threading.Event)
    cancel_reason: str | None = None
    analysis_id: int | None = None
    thread: threading.Thread | None = None
    finalized: bool = False          # حسمه المشرف (مهلة) — لا يُعاد كل دورة


# ── إنشاء التشغيلة · create (inside the launch transaction) ──────────────────
def create_run(conn, *, study_id: int, run_token: str, mode: str,
               params: dict) -> int:
    """أدرج صفّ `queued` في معاملة المُنادي — **لا يلتزم** (كنمط audit.record).

    صفٌّ نشطٌ يتيم لنفس الدراسة (خيطٌ مات قبل إغلاق صفّه) يُوسَم `superseded`
    أولاً: الدراسةُ مسودّةٌ فعلاً وإلا لما نجحت مطالبتُها، ورمزُها الجديد يسيّج
    أيّ خيطٍ قديم — فلا يحجب فهرسُ الفرادة إطلاقاً مشروعاً.
    """
    now = now_iso()
    conn.execute(
        "UPDATE study_runs SET state = 'interrupted', error_code = 'superseded', "
        "error_text = ?, finished_at = ? "
        "WHERE study_id = ? AND state IN ('queued','running')",
        ("تجاوزتها محاولةُ إطلاقٍ أحدث", now, study_id))
    cur = conn.execute(
        "INSERT INTO study_runs (study_id, run_token, state, mode, params_json, "
        "created_at) VALUES (?, ?, 'queued', ?, ?, ?)",
        (study_id, run_token, mode,
         json.dumps(params or {}, ensure_ascii=False, default=str), now))
    run_id = int(cur.lastrowid)
    log.info("study_run_created run_id=%s study_id=%s mode=%s", run_id, study_id,
             mode)
    return run_id


# ── المطالبة والتشغيل · claim + start ────────────────────────────────────────
def dispatch() -> int:
    """طالِب بالمنتظِر ما دامت فتحةٌ متاحة وابدأ خيطه — يعيد عدد ما بدأ.

    الحَكَمُ هو SQLite: `BEGIN IMMEDIATE` ثم عدّ الجاري ثم `UPDATE … WHERE
    state='queued'` بفحص rowcount. لا قفلَ بايثون حول كتابة القاعدة (تدقيق
    التصميم: قفلٌ ممسوك أثناء انتظار قفل SQLite كان يشلّ كنسَ الأيتام وخيوطَ
    الإنهاء ٣٠ ثانية). العدُّ من القاعدة يجعل السقف مشتركاً حتى بين حاويتين
    متداخلتين عند النشر — وصفٌّ ميت يحتلّ فتحته حتى تنقطع نبضتُه (معلَن).
    """
    if _STOPPING:
        return 0
    claimed: list[dict] = []
    conn = connect()
    try:
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        try:
            cap = max_concurrent()
            # §58 #1 (حزام ثانٍ): صفٌّ منتظر لدراسةٍ لم تعد «قيد الإعداد» (أُرشفت/
            # أُغلقت/عادت مسودّةً بطريقٍ آخر) يُغلَق هنا — لا يُنفَّذ أبداً على
            # دراسةٍ سياجُ إنهائها سيرفض نتيجتَه ويحبس حصّتَه.
            conn.execute(
                "UPDATE study_runs SET state = 'cancelled', finished_at = ?, "
                "error_code = 'cancelled', error_text = ? "
                "WHERE state = 'queued' AND study_id IN "
                "(SELECT id FROM studies WHERE state != 'in_progress')",
                (now_iso(), "أُغلقت التشغيلة المنتظرة: الدراسة لم تعد قيد الإعداد"))
            running = int(conn.execute(
                "SELECT COUNT(*) FROM study_runs WHERE state = 'running'"
            ).fetchone()[0])
            while running < cap and not _STOPPING:   # §58 #7: لا مطالبة بعد بدء الإغلاق
                row = conn.execute(
                    "SELECT r.id, r.study_id, r.run_token, r.mode, r.params_json, "
                    "s.owner_id FROM study_runs r JOIN studies s ON s.id = r.study_id "
                    "WHERE r.state = 'queued' AND s.state = 'in_progress' "
                    "ORDER BY r.id LIMIT 1").fetchone()
                if row is None:
                    break
                now = now_iso()
                cur = conn.execute(
                    "UPDATE study_runs SET state = 'running', boot_id = ?, "
                    "started_at = ?, heartbeat_at = ? "
                    "WHERE id = ? AND state = 'queued'",
                    (boot_id(), now, now, int(row["id"])))
                if cur.rowcount == 0:      # لا يقع تحت IMMEDIATE — حزام أمان
                    break
                claimed.append(dict(row))
                running += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()
    started = 0
    for row in claimed:
        log.info("study_run_claimed run_id=%s study_id=%s boot_id=%s",
                 row["id"], row["study_id"], boot_id())
        started += _start_claimed(row)
    return started


def _start_claimed(row: dict) -> int:
    try:
        params = json.loads(row.get("params_json") or "{}")
    except Exception:  # noqa: BLE001 — لقطةٌ فاسدة = فشلٌ معلَن لا انهيار
        params = {}
    handle = RunHandle(run_id=int(row["id"]), study_id=int(row["study_id"]),
                       account_id=int(row["owner_id"]),
                       run_token=str(row["run_token"]),
                       mode=str(row.get("mode") or "quick"),
                       started_monotonic=time.monotonic())
    t = threading.Thread(target=_worker, args=(handle, params), daemon=True,
                         name=f"study-run-{handle.study_id}")
    handle.thread = t
    with engine_bridge._LOCK:
        _HANDLES[handle.run_id] = handle
        engine_bridge._ACTIVE[handle.study_id] = (handle.run_token,
                                                  handle.started_monotonic)
        engine_bridge._THREADS.append(t)
        engine_bridge._THREADS[:] = [x for x in engine_bridge._THREADS
                                     if x.is_alive() or x is t]
    # §58 #10: إلغاءٌ سُجِّل في القاعدة بين التزام المطالبة وتسجيل المقبض
    # يُلتقَط الآن لا في الدورة التالية — الخيط يبدأ وحدثُه مضبوط.
    try:
        conn = connect()
        try:
            flagged = conn.execute(
                "SELECT cancel_requested_at FROM study_runs WHERE id = ?",
                (handle.run_id,)).fetchone()
        finally:
            conn.close()
        if flagged is not None and flagged[0]:
            handle.cancel_reason = handle.cancel_reason or "requested"
            handle.cancel.set()
    except Exception as exc:  # noqa: BLE001 — الدورة التالية تلتقطه
        log.warning("study_run early cancel-flag read failed run_id=%s: %s",
                    handle.run_id, exc)
    try:
        t.start()
    except Exception as exc:  # noqa: BLE001 — تعذّر بدء خيط = فشلٌ معلَن على الصفّ
        log.exception("study_run_start_failed run_id=%s: %s", handle.run_id, exc)
        with engine_bridge._LOCK:
            _HANDLES.pop(handle.run_id, None)
            if engine_bridge._ACTIVE.get(handle.study_id, ("", 0.0))[0] == handle.run_token:
                engine_bridge._ACTIVE.pop(handle.study_id, None)
        engine_bridge._finish_failure(
            handle.study_id, handle.account_id,
            "عطل داخلي في جسر التشغيل — أعد الإطلاق", run_token=handle.run_token,
            run_state="failed", error_code="bridge_crash")
        return 0
    log.info("study_run_started run_id=%s study_id=%s thread=%s", handle.run_id,
             handle.study_id, t.name)
    return 1


def _worker(handle: RunHandle, params: dict) -> None:
    import silk_context
    try:
        with silk_context.cancel_context(handle.cancel):
            engine_bridge._thread_body(
                handle.study_id, handle.account_id,
                str(params.get("product") or ""), params.get("hs_code"),
                params.get("market_pref"), bool(params.get("hs_confirmed")),
                handle.run_token, str(params.get("lang") or "ar"),
                params.get("product_card"), params.get("resume_analysis_id"),
                run=handle,
                # R4.7/R4.8: لقطةُ الوسائط تحمل مصدرَ البند وإقرارَ التنبيه —
                # تُعاد كما سُجِّلت وقت الإطلاق (لا تُقرأ من الصفّ الحيّ).
                hs_source=params.get("hs_source"),
                advisories_ack=bool(params.get("advisories_ack")))
    finally:
        # §58 #11: املأ الفتحة **قبل** شطب المقبض — فلا نافذةَ يبدو فيها الطابور
        # خامداً بينما مطالبةٌ تالية على وشك التسجيل (السقف يُعَدّ من القاعدة).
        if not _STOPPING:
            try:
                dispatch()            # املأ الفتحة التي تحرّرت للتوّ
            except Exception as exc:  # noqa: BLE001 — الطابور يُعاد فحصه في النبضة
                log.warning("study_run dispatch after finish failed: %s", exc)
        with engine_bridge._LOCK:
            if _HANDLES.get(handle.run_id) is handle:
                _HANDLES.pop(handle.run_id, None)


# ── النبضة والتقادم والمهلة · tick ───────────────────────────────────────────
def _handles() -> list[RunHandle]:
    with engine_bridge._LOCK:
        return list(_HANDLES.values())


def _cutoff_iso(seconds: float) -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sweep_stale() -> int:
    """قاطِع صفوفاً جارية انقطعت نبضتُها — بعُمر النبضة وحده، أيًّا كان إقلاعها.

    لا شرطَ على `boot_id`: صفٌّ من هذه العملية بلا مقبضٍ حيّ (خيطٌ لم يغلق صفّه)
    ينقطع نبضُه هو الآخر. صفوفٌ نبضتُها طازجة تُترك — قد تكون حيّةً في حاوية
    أخرى أثناء نشرٍ متداخل؛ لا حكم بلا دليل.
    """
    live = {h.run_id for h in _handles()}
    conn = connect()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT r.id, r.study_id, r.run_token, r.analysis_id, r.boot_id, "
            "r.heartbeat_at, r.cancel_requested_at, s.owner_id FROM study_runs r "
            "JOIN studies s ON s.id = r.study_id "
            "WHERE r.state = 'running' AND (r.heartbeat_at IS NULL "
            "OR r.heartbeat_at < ?)", (_cutoff_iso(stale_s()),)).fetchall()]
    finally:
        conn.close()
    done = 0
    for r in rows:
        if r["id"] in live:
            continue
        done += _interrupt_run(r)
    return done


def _interrupt_run(row: dict) -> int:
    """وسمُ تشغيلةٍ انقطعت: الدراسة مسودّةً بسببٍ معلَن + مؤشّر استئناف + إرجاع
    الحصّة + إشعار — عبر `_finish_failure` نفسه (نفس المعاملة، نفس السياج).

    §58 #9: إن كان المصنعُ قد طلب الإلغاء قبل موت العملية فالنهاية «أُلغيت»
    باسم طلبه، لا «انقطع» — نفس الإرجاع، اسمٌ صادق.
    """
    cancelled = bool(row.get("cancel_requested_at"))
    kwargs: dict = dict(run_token=row.get("run_token"),
                        analysis_id=row.get("analysis_id"),
                        run_state="cancelled" if cancelled else "interrupted",
                        error_code="cancelled" if cancelled else "interrupted")
    if cancelled:
        kwargs.update(notify_kind="study_cancelled",
                      notify_title_fmt=engine_bridge.CANCELLED_TITLE_FMT)
    try:
        engine_bridge._finish_failure(
            int(row["study_id"]), int(row["owner_id"]),
            (engine_bridge.CANCELLED_REASON if cancelled
             else engine_bridge.INTERRUPTED_REASON), **kwargs)
    except Exception as exc:  # noqa: BLE001 — الكنسة التالية تعيد المحاولة
        log.warning("study_run_interrupt_failed run_id=%s error=%s", row.get("id"), exc)
        return 0
    log.warning("study_run_interrupted run_id=%s study_id=%s boot_id=%s "
                "heartbeat_at=%s outcome=%s", row.get("id"), row.get("study_id"),
                row.get("boot_id") or "-", row.get("heartbeat_at") or "-",
                kwargs["run_state"])
    aid = row.get("analysis_id")
    if aid:
        # صفُّ المحرّك لهذه المحاولة: لا يبقى 'running' ثلاثين دقيقة حتى الحاصد —
        # واجهةُ فشل المحرّك نفسُها (خاملة التكرار عبر `usd_reconciled`).
        try:
            import silk_storage
            eng = silk_storage.get_research_run(int(aid))
            if eng and eng.get("status") == "running":
                silk_storage.mark_research_failed(
                    int(aid), "interrupted: platform study run stopped by "
                              "process shutdown or restart")
                silk_storage.reconcile_failed_run_usd(int(aid))
        except Exception as exc:  # noqa: BLE001 — حاصد المحرّك يلتقطه لاحقاً
            log.warning("engine run %s interrupt reconcile skipped: %s", aid, exc)
    return 1


def tick() -> dict:
    """دورة مشرفٍ واحدة — تُستدعى من الخيط دورياً ومن الاختبارات صراحةً.

    كل خطوة بمعاملتها وحارسها؛ لا تُسقِط بعضُها بعضاً ولا ترفع أبداً.
    """
    out = {"heartbeat": 0, "cancel_flags": 0, "timed_out": 0, "interrupted": 0,
           "dispatched": 0}
    handles = _handles()
    ids = [h.run_id for h in handles]
    if ids:
        marks = ",".join("?" * len(ids))
        # (أ) النبضة أولاً وباتصالها الخاصّ — خطوةٌ بطيئة لاحقة لا تؤخّرها.
        try:
            conn = connect()
            try:
                cur = conn.execute(
                    f"UPDATE study_runs SET heartbeat_at = ? WHERE id IN ({marks}) "
                    "AND state = 'running'", (now_iso(), *ids))
                conn.commit()
                out["heartbeat"] = cur.rowcount
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 — نبضةٌ فائتة تُعوَّض في التالية
            log.warning("study_run_heartbeat_failed runs=%s error=%s", ids, exc)
        # (ب) أعلام الإلغاء من القاعدة — تشمل طلباً وُجِّه لعمليةٍ أخرى.
        try:
            conn = connect()
            try:
                flagged = [int(r[0]) for r in conn.execute(
                    f"SELECT id FROM study_runs WHERE id IN ({marks}) "
                    "AND cancel_requested_at IS NOT NULL", ids).fetchall()]
            finally:
                conn.close()
            for h in handles:
                if h.run_id in flagged and not h.cancel.is_set():
                    h.cancel_reason = h.cancel_reason or "requested"
                    h.cancel.set()
                    out["cancel_flags"] += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("study_run cancel-flag scan failed: %s", exc)
    # (ج) المهلة القصوى: إشارةُ إلغاءٍ تعاونيّة **و**حسمٌ فوريّ للصفّ — الدراسة
    # لا تبقى «قيد الإعداد» بعد نافذتها (نفس ضمانة الكنس القديم)، والخيط يتوقّف
    # عند نقطة تفتيشه التالية ويجد إنهاءَه مسيَّجاً بالرمز.
    for h in handles:
        if h.finalized or h.cancel_reason == "shutdown":
            continue
        grace = engine_bridge._orphan_grace_s(h.mode)
        if time.monotonic() - h.started_monotonic < grace:
            continue
        # §58 #8: طلبُ إلغاءٍ سابق من المصنع يبقى اسمَ النهاية — المهلة تحسم
        # الصفّ لكنها لا تُعيد تسمية طلبه «تعثّراً».
        prior = h.cancel_reason
        h.cancel_reason = prior or "timeout"
        h.cancel.set()
        try:
            if prior == "requested":
                engine_bridge._finish_failure(
                    h.study_id, h.account_id, engine_bridge.CANCELLED_REASON,
                    run_token=h.run_token, analysis_id=h.analysis_id,
                    run_state="cancelled", error_code="cancelled",
                    notify_kind="study_cancelled",
                    notify_title_fmt=engine_bridge.CANCELLED_TITLE_FMT)
            else:
                engine_bridge._finish_failure(
                    h.study_id, h.account_id, engine_bridge.TIMEOUT_REASON,
                    run_token=h.run_token, analysis_id=h.analysis_id,
                    run_state="failed", error_code="timeout")
            h.finalized = True
            out["timed_out"] += 1
            log.warning("study_run_timeout run_id=%s study_id=%s grace_s=%s "
                        "outcome=%s", h.run_id, h.study_id, grace,
                        "cancelled" if prior == "requested" else "timeout")
        except Exception as exc:  # noqa: BLE001
            log.warning("study_run timeout finalize failed run_id=%s: %s",
                        h.run_id, exc)
    # (د) صفوفٌ انقطعت نبضتُها — أيًّا كان إقلاعها.
    try:
        out["interrupted"] = _sweep_stale()
    except Exception as exc:  # noqa: BLE001
        log.warning("study_run stale sweep failed: %s", exc)
    # (هـ) املأ الفتحات.
    if not _STOPPING:
        try:
            out["dispatched"] = dispatch()
        except Exception as exc:  # noqa: BLE001
            log.warning("study_run dispatch failed: %s", exc)
    return out


# ── الإقلاع والإغلاق · boot recovery + shutdown ──────────────────────────────
def recover() -> dict:
    """عند التركيب: قاطِع ما انقطعت نبضتُه ثم ابدأ المنتظِر — بلا استئنافٍ ذاتيّ.

    صفٌّ `queued` من إقلاعٍ سابق طلبٌ دائم لم يُنفق شيئاً — بدؤه آمن. صفٌّ
    `running` نبضتُه طازجة يُترك (نشرٌ متداخل) وتحسمه النبضاتُ التالية.
    """
    global _STOPPING
    _STOPPING = False
    out = {"interrupted": 0, "dispatched": 0}
    try:
        out["interrupted"] = _sweep_stale()
    except Exception as exc:  # noqa: BLE001 — التعافي تحسينُ إقلاعٍ لا شرطُه
        log.warning("study_run recovery sweep failed: %s", exc)
    try:
        out["dispatched"] = dispatch()
    except Exception as exc:  # noqa: BLE001
        log.warning("study_run recovery dispatch failed: %s", exc)
    if out["interrupted"] or out["dispatched"]:
        log.info("study_run_recovered boot_id=%s interrupted=%s dispatched=%s",
                 boot_id(), out["interrupted"], out["dispatched"])
    return out


def start() -> threading.Thread | None:
    """ابدأ خيط المشرف (daemon) — خاملُ التكرار؛ لا خيط إن أُطفئ بالبيئة."""
    global _SUPERVISOR, _SUP_STOP
    if not supervisor_enabled():
        return None
    with _SUP_LOCK:
        if (_SUPERVISOR is not None and _SUPERVISOR.is_alive()
                and not _SUP_STOP.is_set()):
            return _SUPERVISOR

        # حدثٌ خاص بكل جيل: لا يُعاد clear لحدث خيط قديم فيستيقظ مجدداً.
        # Per-generation interruptible wait; never resurrect a stopped loop.
        stop = threading.Event()
        _SUP_STOP = stop

        def _loop() -> None:
            while not stop.wait(heartbeat_s()):
                if _STOPPING:
                    break
                try:
                    tick()
                except Exception as exc:  # noqa: BLE001 — الخيط لا يموت بخطأ دورة
                    log.warning("study runtime tick failed: %s", exc)

        t = threading.Thread(target=_loop, name="silk-platform-run-supervisor",
                             daemon=True)
        _SUPERVISOR = t
        t.start()
        log.info("platform run supervisor started (heartbeat=%.0fs cap=%s)",
                 heartbeat_s(), max_concurrent())
        return t


def shutdown(join_s: float = 2.0) -> dict:
    """عند إغلاق العملية: أوقف المطالبة، أشِر بالإلغاء، ووسم تشغيلات **هذه**
    العملية `interrupted` فوراً — لا «مكتملة» لعملٍ لم ينتهِ، ولا «جارية» لخيطٍ
    سيموت مع العملية. خاملُ التكرار؛ صفوفُ الإقلاعات الأخرى لا تُمَسّ."""
    global _STOPPING
    _STOPPING = True
    _SUP_STOP.set()
    out = {"interrupted": 0}
    for h in _handles():
        h.cancel_reason = h.cancel_reason or "shutdown"
        h.cancel.set()
    # §58 #7: أوقف المشرف **قبل** لقطة الصفوف — مطالبةٌ كانت داخل معاملتها
    # لا تُفلت من الختم (والمطالبة نفسها تفحص علم الإغلاق داخل المعاملة).
    sup = _SUPERVISOR
    if sup is not None and sup.is_alive() and sup is not threading.current_thread():
        sup.join(timeout=join_s)
    try:
        conn = connect()
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT r.id, r.study_id, r.run_token, r.analysis_id, r.boot_id, "
                "r.heartbeat_at, r.cancel_requested_at, s.owner_id FROM study_runs r "
                "JOIN studies s ON s.id = r.study_id "
                "WHERE r.state = 'running' AND r.boot_id = ?",
                (boot_id(),)).fetchall()]
        finally:
            conn.close()
        for r in rows:
            out["interrupted"] += _interrupt_run(r)
    except Exception as exc:  # noqa: BLE001 — الإقلاع التالي يكنس بالنبضة
        log.warning("study_runtime_shutdown sweep failed: %s", exc)
    log.warning("study_runtime_shutdown boot_id=%s interrupted=%s", boot_id(),
                out["interrupted"])
    return out


# ── الإلغاء · cooperative cancellation ───────────────────────────────────────
def request_cancel(conn, *, study_id: int, account_id: int,
                   actor_user_id: int | None) -> dict:
    """اطلب إلغاء التشغيلة النشطة لدراسة — المنتظِرة تُرجَع فوراً، والجارية
    تُشار إليها تعاونياً (تتوقّف عند نقطة تفتيشها التالية).

    المُنادي يملك المعاملة؛ هنا نلتزم **قبل** `_finish_failure` (يفتح اتصاله
    الخاصّ — وإلا انتظر قفلَنا نحن حتى مهلته). سباقُ «قُرئت منتظرةً ثم طالب بها
    المشرف»: rowcount=0 ⇒ نهبط إلى فرع الجاري بدل الادعاء بإلغاءٍ لم يقع.

    تدقيق الفرق النهائي (2026-09-02): الفرع المنتظِر كان يُغلق صفّ `study_runs`
    (state='cancelled') ويلتزم **قبل** استدعاء `_finish_failure` — عطلٌ بين
    الالتزامين يترك الصفَّ «أُلغيت» والدراسة «قيد الإعداد» بلا تشغيلةٍ نشطة حتى
    نافذة الكنس القديم. الآن نكتفي هنا بعلَم الإلغاء (يبقى الصفّ `queued`)
    ونترك `_finish_failure` يُغلقه على سياجه الخاصّ (`_close_run_row`) في نفس
    التزامها — فعطلٌ قبل ذلك الالتزام يترك صفّاً `queued` بعلَم إلغاءٍ مضبوط،
    قابلاً للمطالبة عادةً، يُلغي نفسه عند نقطة تفتيشه الأولى.
    """
    row = conn.execute(
        "SELECT id, state, run_token FROM study_runs WHERE study_id = ? "
        "AND state IN ('queued','running') ORDER BY id DESC LIMIT 1",
        (study_id,)).fetchone()
    if row is None:
        raise lifecycle.LifecycleError(
            "study_not_running", "لا تشغيلة جارية لهذه الدراسة")
    run_id, token = int(row["id"]), str(row["run_token"])
    now = now_iso()
    if row["state"] == "queued":
        cur = conn.execute(
            "UPDATE study_runs SET cancel_requested_at = ? WHERE id = ? "
            "AND state = 'queued' AND cancel_requested_at IS NULL",
            (now, run_id))
        if cur.rowcount:
            audit.record(conn, action="study_cancel_requested",
                         user_id=actor_user_id, account_id=account_id,
                         resource_type="study", resource_id=study_id,
                         changes={"run_id": run_id, "was": "queued"})
            conn.commit()
            log.info("study_run_cancel_requested run_id=%s study_id=%s was=queued",
                     run_id, study_id)
            engine_bridge._finish_failure(
                study_id, account_id, engine_bridge.CANCELLED_QUEUED_REASON,
                run_token=token, run_state="cancelled", error_code="cancelled",
                notify_kind="study_cancelled",
                notify_title_fmt=engine_bridge.CANCELLED_TITLE_FMT)
            return {"ok": True, "run_state": "cancelled"}
    requested = conn.execute(
        "UPDATE study_runs SET cancel_requested_at = ? WHERE id = ? "
        "AND state = 'running' AND cancel_requested_at IS NULL", (now, run_id))
    if not requested.rowcount:
        current = conn.execute(
            "SELECT state, cancel_requested_at FROM study_runs WHERE id=?", (run_id,)).fetchone()
        if current and current["state"] in ("queued", "running") and current["cancel_requested_at"]:
            return {"ok": True, "run_state": "cancelling"}
        raise lifecycle.LifecycleError("study_not_running", "انتهت التشغيلة قبل قبول طلب الإلغاء")
    audit.record(conn, action="study_cancel_requested", user_id=actor_user_id,
                 account_id=account_id, resource_type="study",
                 resource_id=study_id, changes={"run_id": run_id, "was": "running"})
    conn.commit()
    with engine_bridge._LOCK:
        h = _HANDLES.get(run_id)
    if h is not None:
        h.cancel_reason = h.cancel_reason or "requested"
        h.cancel.set()
    log.info("study_run_cancel_requested run_id=%s study_id=%s was=running "
             "owned_here=%s", run_id, study_id, h is not None)
    return {"ok": True, "run_state": "cancelling"}


# ── قراءات · read helpers for the API layer ──────────────────────────────────
def run_view(conn, study_ids: list[int]) -> dict[int, dict]:
    """حالة التشغيلة النشطة لكل دراسة — يُرفَق بالردود القائمة لا يستبدل مفاتيحها.
    بلا `boot_id`/`params_json`: سباكةُ المشغّل تبقى على الخادم."""
    ids = [int(i) for i in study_ids if i is not None]
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT study_id, state, started_at, heartbeat_at, cancel_requested_at "
        f"FROM study_runs WHERE study_id IN ({marks}) "
        "AND state IN ('queued','running')", ids).fetchall()
    return {int(r["study_id"]): {
        "state": r["state"], "queued": r["state"] == "queued",
        "cancel_requested": bool(r["cancel_requested_at"]),
        "started_at": r["started_at"], "heartbeat_at": r["heartbeat_at"]}
        for r in rows}


def last_run_view(conn, study_ids: list[int]) -> dict[int, dict]:
    """آخر تشغيلة **منتهية** لكل دراسة — R3 (تدقيق 2026-09-01، RC-5/FE-1).

    `run_view` يقرأ النشط وحده، فكانت الدراسة العائدة مسودّةً تفقد اسمَ نهايتها:
    «انقطعت» بإعادة نشر و«أُلغيت» بطلب المصنع و«تعثّرت» بعطل كلّها سطرٌ أحمر
    واحد على الشاشة. الصفوفُ مرتّبة بالمعرّف فيغلب الأحدث. بلا سباكة المشغّل
    (`boot_id`/`params_json`) — تبقى على الخادم كما في `run_view`.
    """
    ids = [int(i) for i in study_ids if i is not None]
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT study_id, state, error_code, finished_at FROM study_runs "
        f"WHERE study_id IN ({marks}) AND state NOT IN ('queued','running') "
        "ORDER BY id", ids).fetchall()
    return {int(r["study_id"]): {"state": r["state"],
                                 "error_code": r["error_code"],
                                 "finished_at": r["finished_at"]}
            for r in rows}


def active_state(study_id: int) -> str | None:
    """حالة التشغيلة النشطة لدراسة (queued|running) أو None — باتصالٍ قصير."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT state FROM study_runs WHERE study_id = ? "
            "AND state IN ('queued','running') ORDER BY id DESC LIMIT 1",
            (study_id,)).fetchone()
        return str(row["state"]) if row else None
    finally:
        conn.close()


def has_active_run(conn, study_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM study_runs WHERE study_id = ? "
        "AND state IN ('queued','running') LIMIT 1", (study_id,)).fetchone()
    return row is not None


def _queued_count() -> int:
    conn = connect()
    try:
        return int(conn.execute(
            "SELECT COUNT(*) FROM study_runs WHERE state = 'queued'").fetchone()[0])
    except Exception:  # noqa: BLE001 — قاعدة بلا الجدول (قبل الترحيل) = لا منتظِر
        return 0
    finally:
        conn.close()


# ── مقاعد الاختبار · test seams ──────────────────────────────────────────────
def wait_idle(timeout: float = 30.0) -> bool:
    """انتظر خمود كل خيوط التشغيل **وفراغ الطابور القابل للبدء** — test seam.

    يعيد True إن لم يبقَ خيطٌ حيّ ولا صفٌّ منتظر يمكن بدؤه قبل المهلة.
    لا يُستدعى من مسار إنتاجي (يخلف `engine_bridge.wait_idle` الذي يفوّض إليه).
    """
    deadline = time.monotonic() + timeout
    while True:
        threads = [h.thread for h in _handles() if h.thread is not None]
        for t in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            t.join(timeout=remaining)
        if not _handles():
            if _STOPPING or _queued_count() == 0 or dispatch() == 0:
                with engine_bridge._LOCK:
                    engine_bridge._THREADS[:] = [t for t in engine_bridge._THREADS
                                                 if t.is_alive()]
                    return not engine_bridge._ACTIVE
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)


def reset_for_tests() -> None:
    """صفّر حالة الوحدة بين الاختبارات — علمُ الإغلاق والمقابض (conftest autouse).

    §58 #12: خيطُ اختبارٍ فاشل كان يُكمِل بعد التصفير فيطالب من قاعدة الاختبار
    التالي — يُوقَف أولاً (علم الإغلاق + إشارة إلغاء + انتظارٌ قصير) ثم يُصفَّر.
    """
    global _STOPPING
    _STOPPING = True
    _SUP_STOP.set()
    sup = _SUPERVISOR
    if sup is not None and sup is not threading.current_thread():
        sup.join(timeout=2.0)
    deadline = time.monotonic() + 2.0
    for h in _handles():
        h.cancel_reason = h.cancel_reason or "shutdown"
        h.cancel.set()
        if h.thread is not None:
            h.thread.join(timeout=max(0.0, deadline - time.monotonic()))
    with engine_bridge._LOCK:
        _HANDLES.clear()
        engine_bridge._ACTIVE.clear()
        engine_bridge._THREADS[:] = [t for t in engine_bridge._THREADS if t.is_alive()]
    _STOPPING = False
