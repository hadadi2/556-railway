"""مجدول مهام المنصّة — in-process job scheduler (PR-2).

خيطٌ داخل العملية لا خدمة cron منفصلة — نفس سابقة `silk_collectors.start_scheduler`
وسببها البنيوي: وحدة تخزين Railway تُركَّب على خدمة واحدة فقط، فمهمّةٌ في خدمة
أخرى لن ترى قاعدة المنصّة. Opt-in، وخيط daemon، وفشلُ تشغيلةٍ يُسجَّل ولا يقتل الخيط.

المواعيد من المواصفة (§12):
- تصفير الحصص الشهري: أوّل الشهر 00:00 UTC (يتخطّى Basic).
- فوترة التخزين: أوّل الشهر 01:00 UTC.
- تنظيف الجلسات: يومياً 02:00 UTC (+ تقليم عدّادات الخنق).

منطق «هل حلّ الموعد؟» دالّة نقيّة (`due_jobs`) تأخذ الوقت وسجلّ آخر تشغيلة،
فتُختبَر بلا نوم ولا خيوط. The due-time logic is pure and unit-testable.
"""
from __future__ import annotations

import datetime
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()

# اسم المهمّة → (يوم الشهر أو None ليومية، ساعة UTC)
JOB_SCHEDULE: dict[str, tuple[int | None, int]] = {
    "monthly_quota_reset": (1, 0),    # أوّل الشهر 00:00
    "storage_billing": (1, 1),        # أوّل الشهر 01:00
    "session_cleanup": (None, 2),     # يومياً 02:00
}


_billing_off_noted = False


def job_schedule() -> dict:
    """المهامُ المجدولةُ فعلاً — P3 (BIZ-6، تدقيق 2026-09-01): فوترةُ التخزين كانت
    مجدولةً افتراضياً بينما تفعيلُ الفوترة **قرارُ مالكٍ مؤجَّل**، فتُخصَم من محافظ
    المصانع بلا أن يقرّرها أحد. تُدرَج الآن بـ`SILK_PLATFORM_STORAGE_BILLING=1` فقط؛
    الدالّةُ `run_storage_billing` تبقى قابلةً للنداء المباشر (اختباراتٌ وأداةُ مالك)."""
    global _billing_off_noted
    out = dict(JOB_SCHEDULE)
    on = os.environ.get("SILK_PLATFORM_STORAGE_BILLING", "").strip().lower()
    if on not in ("1", "true", "yes", "on"):
        out.pop("storage_billing", None)
        if not _billing_off_noted:
            # مرّةً واحدةً لكلّ عملية: السطرُ للمشغّل الذي ينتظر فاتورةً لا تأتي.
            # صمتٌ **معلَن** لا صمتٌ خفيّ (وليس لكلّ دورةِ استطلاع).
            _billing_off_noted = True
            log.info("scheduler: storage_billing skipped — "
                     "SILK_PLATFORM_STORAGE_BILLING is not set")
    return out


def _slot(name: str, now: datetime.datetime) -> str:
    """مُعرِّف الفتحة الحالية للمهمّة — a stable id for the current due window.

    الشهرية تُعرَّف بـ'YYYY-MM' واليومية بـ'YYYY-MM-DD'، فيصير «هل نُفِّذت في
    هذه الفتحة؟» مقارنةَ نصٍّ واحدة — وتصير المهمّة **خاملة التكرار** حتى لو
    استُدعيت الحلقة مراراً في نفس الساعة. Slot id ⇒ idempotent within a window.
    """
    day, _hour = job_schedule().get(name, JOB_SCHEDULE[name])
    if day is None:
        return now.strftime("%Y-%m-%d")
    return now.strftime("%Y-%m")


def due_jobs(now: datetime.datetime, last_run: dict[str, str]) -> list[str]:
    """المهام التي حلّ موعدها ولم تُنفَّذ في فتحتها — pure; no I/O, no sleeping.

    `last_run` يربط اسم المهمّة بمُعرِّف آخر فتحة نُفِّذت فيها.

    **اللحاق بعد التوقّف** (catch-up): المهمّة الشهرية تستحقّ التشغيل في أي يوم
    **بعد** موعدها من نفس الشهر لا في يومه فقط. لو كانت الحاوية متوقّفة يوم ١
    (نشر، إعادة تشغيل، تعطّل) لكانت فوترة التخزين تُسقَط لذلك الشهر كلّه صمتاً —
    والدفتر غير قابل للتعديل فلا تُصحَّح لاحقاً. المهمّتان الشهريّتان محروستان
    بمفتاح الفترة (خاملتا التكرار) فالتشغيل المتأخّر آمن وأصحّ من الإسقاط.
    A monthly job missed because the process was down still runs later that
    month; both monthly jobs are period-guarded, so late execution is safe.
    """
    out: list[str] = []
    for name, (day, hour) in job_schedule().items():
        if day is None:                       # يومية · daily
            if now.hour < hour:
                continue
        else:                                 # شهرية + لحاق · monthly with catch-up
            if now.day < day:
                continue
            if now.day == day and now.hour < hour:
                continue
        if last_run.get(name) == _slot(name, now):
            continue          # نُفِّذت سلفاً في هذه الفتحة
        out.append(name)
    return out


def _env_days(name: str, default: int) -> int:
    """نافذةُ احتفاظٍ بالأيام من البيئة — فارغ/غير صالح = الافتراض؛ سالبٌ = 0."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def run_job(name: str) -> object:
    """نفّذ مهمّةً واحدة باتصالها الخاص — returns the job's result.

    كل مهمّة تفتح اتصالها وتغلقه، فتشغيلةٌ فاشلة لا تترك اتصالاً معلّقاً.
    """
    from . import auth, db, jobs, throttle
    conn = db.connect()
    try:
        if name == "monthly_quota_reset":
            return jobs.run_monthly_quota_reset(conn)
        if name == "storage_billing":
            return jobs.run_storage_billing(conn)
        if name == "session_cleanup":
            from . import audit, notifications
            removed = auth.cleanup_expired_sessions(conn)
            pruned = throttle.prune(conn)      # تقليم عدّادات الخنق المنتهية
            tokens = auth.cleanup_reset_tokens(conn)   # درس 190 (F13)
            # R7 (AUTH-20): قيودُ الشراء تُحذَف بعد نافذة الاحتفاظ (٣٦٥ يوماً افتراضاً).
            audit.prune_checkout(
                conn, days=_env_days("SILK_PLATFORM_CHECKOUT_RETENTION_DAYS", 365))
            # R5 (DB-16 / AUTH-20): نوافذُ احتفاظٍ من البيئة — مطفأة (0) ما عدا
            # تنقيةَ بيانات التواصل في قيود الشراء (٩٠ يوماً افتراضاً).
            notif = notifications.prune(
                conn, read_days=_env_days("SILK_PLATFORM_NOTIF_RETENTION_DAYS", 0))
            audit_rows = audit.prune(
                conn, days=_env_days("SILK_PLATFORM_AUDIT_RETENTION_DAYS", 0))
            scrubbed = audit.scrub_checkout_pii(
                conn, days=_env_days("SILK_PLATFORM_CHECKOUT_PII_DAYS", 90))
            return {"sessions_removed": removed, "throttle_pruned": pruned,
                    "reset_tokens_removed": tokens,
                    "notifications_pruned": notif, "audit_pruned": audit_rows,
                    "checkout_pii_scrubbed": scrubbed}
        raise ValueError(f"unknown job: {name}")
    finally:
        conn.close()


def run_due(now: datetime.datetime | None = None,
            last_run: dict[str, str] | None = None) -> dict[str, object]:
    """نفّذ كل ما حلّ موعده وحدّث سجلّ الفتحات — one pass; testable directly.

    يُعدِّل `last_run` في مكانه (المُنادي يحتفظ به). فشلُ مهمّةٍ يُسجَّل ولا
    يمنع البقيّة، و**لا يُوسَم كمنفَّذ** كي تُعاد المحاولة في المرور التالي.
    A failed job is not marked done, so the next pass retries it.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    last_run = last_run if last_run is not None else {}
    results: dict[str, object] = {}
    for name in due_jobs(now, last_run):
        try:
            results[name] = run_job(name)
            last_run[name] = _slot(name, now)
            log.info("platform job %s done: %s", name, results[name])
        except Exception as exc:  # noqa: BLE001 — تشغيلة تفشل، الخيط يبقى حيّاً
            results[name] = f"failed: {exc}"
            log.warning("platform job %s failed: %s", name, exc)
    return results


_sweeper_started = False


def sweep_pass() -> None:
    """كنسةٌ واحدة: الصفوف القديمة بلا سجلّ تشغيلة (`sweep_orphans`) + — حين يكون
    خيطُ مُشرِف التشغيلات مطفأً — دورةُ المشرف نفسها (R2 §58 #4): المهلةُ
    القصوى والنبضة والتقادم لا تختفي مع الصمّام، بل تنتقل إلى هذه الكنسة."""
    from . import db, engine_bridge, study_runtime
    conn = db.connect()
    try:
        engine_bridge.sweep_orphans(conn)
    finally:
        conn.close()
    if not study_runtime.supervisor_enabled():
        study_runtime.tick()
    # R7 (AUTH-12): تنظيفُ الجلسات/الرموز/العدّادات مرّةً كلَّ ساعة من هنا — كان
    # رهينَ المجدول الاختياري (`SILK_PLATFORM_SCHEDULER=1`) فلا يدور على النشر.
    slot = _cleanup_due()
    if slot is not None:
        try:
            run_job("session_cleanup")
        except Exception as exc:  # noqa: BLE001 — كنسةٌ جانبية لا تُسقط الكانس
            logging.getLogger(__name__).warning("hourly session cleanup failed: %s", exc)
        else:
            _mark_cleanup_done(slot)   # مراجعة: الخانةُ تُستهلَك بعد النجاح فيُعاد الفاشل


_cleanup_slot: int | None = None


def _cleanup_due() -> int | None:
    """خانةُ الساعة (time//3600) إن لم يُنظَّف فيها بعد، وإلا None."""
    slot = int(time.time() // 3600)
    return None if slot == _cleanup_slot else slot


def _mark_cleanup_done(slot: int) -> None:
    global _cleanup_slot
    _cleanup_slot = slot


def reset_cleanup_slot_for_tests() -> None:
    global _cleanup_slot
    _cleanup_slot = None


def sweeper_enabled() -> bool:
    """كنسُ الأيتام الدوري — **مشغَّل افتراضياً**، يُطفأ بـ`=0` صراحةً.

    فرقُه عن `start()`: هذا لا يكتب فاتورةً ولا يصفّر حصّة — يوفّق صفوفاً
    هجرها خيطُها فقط. كان مربوطاً بالمجدول المدفوع (opt-in) فبقي مطفأً على
    النشر، فدراسةٌ ماتت بإعادة نشرٍ تعلق «قيد الإعداد» للأبد (بلاغ المالك
    2026-08-19). Reconciliation is safe by construction, so it defaults on.
    """
    return os.environ.get("SILK_PLATFORM_ORPHAN_SWEEP", "1").strip() != "0"


def start_orphan_sweeper(poll_seconds: float | None = None):
    """خيط كنسٍ دوريّ للأيتام — idempotent؛ None عند التعطيل أو التكرار."""
    global _sweeper_started
    if not sweeper_enabled():
        return None
    with _lock:
        if _sweeper_started:
            return None
        _sweeper_started = True
    try:
        poll = float(poll_seconds if poll_seconds is not None
                     else os.environ.get("SILK_PLATFORM_SWEEP_POLL_S", "300"))
    except (TypeError, ValueError):
        poll = 300.0
    poll = max(30.0, poll)

    def _loop() -> None:
        while True:
            time.sleep(poll)        # الكنسة الأولى تمّت عند التركيب
            try:
                sweep_pass()
            except Exception as exc:  # noqa: BLE001 — الحلقة تبقى حيّة
                log.warning("platform orphan sweep pass failed: %s", exc)

    thread = threading.Thread(target=_loop, name="silk-platform-sweeper",
                              daemon=True)
    thread.start()
    log.info("platform orphan sweeper started (poll=%.0fs)", poll)
    return thread


def _scheduler_tick(last_run: dict[str, str]) -> None:
    """مرورٌ واحد للمجدول — المهامُ المستحقّة فقط.

    R5 (تدقيق 2026-09-01، ENG-12): كانت الحلقة تكنس الأيتام بنفسها إلى جانب
    `start_orphan_sweeper` — كنّاسان على مؤقّتين مستقلّين، وأحدُهما يتجاهل
    `SILK_PLATFORM_ORPHAN_SWEEP=0` ولا يُنبِض المشرف. الكنسُ الدوريّ يملكه
    `start_orphan_sweeper`/`sweep_pass` وحدهما (كنسةُ التركيب تبقى في `mount`).
    """
    try:
        run_due(last_run=last_run)
    except Exception as exc:  # noqa: BLE001 — الحلقة تبقى حيّة
        log.warning("platform scheduler pass failed: %s", exc)


def start(poll_seconds: float | None = None):
    """ابدأ خيط المجدول — opt-in via SILK_PLATFORM_SCHEDULER=1; idempotent.

    غير مضبوط ⇒ **لا خيط إطلاقاً**: تشغيلة اختبار أو تطوير لا تكتب فواتير ولا
    تصفّر حصصاً في قاعدة أحد. يرجّع الخيط، أو None عند التعطيل/التكرار.
    Unset ⇒ no thread at all (tests and dev never bill or reset silently).
    """
    global _started
    if os.environ.get("SILK_PLATFORM_SCHEDULER") != "1":
        return None
    with _lock:
        if _started:
            return None
        _started = True

    try:
        poll = float(poll_seconds if poll_seconds is not None
                     else os.environ.get("SILK_PLATFORM_SCHEDULER_POLL_S", "300"))
    except (TypeError, ValueError):
        poll = 300.0
    poll = max(1.0, poll)   # حلقة بلا نوم تحرق نواة · never a spin loop

    last_run: dict[str, str] = {}

    def _loop() -> None:
        while True:
            _scheduler_tick(last_run)
            time.sleep(poll)

    thread = threading.Thread(target=_loop, name="silk-platform-scheduler",
                              daemon=True)
    thread.start()
    log.info("platform scheduler started (poll=%.0fs)", poll)
    return thread
