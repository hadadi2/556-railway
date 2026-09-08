"""سجلُّ تشغيلات `/research` الجذري — R2b (التدقيق الجنائي 2026-09-01، بقيّة RC-1).

**لماذا (API-3/API-4/API-14/CONC-4/CONC-10):** المنصّةُ نالت في R2 سجلّاً دائماً
(`silk_platform/study_runtime.py`)، وبقي خيطُ `/research` الجذري خيطَ daemon بلا
سجلّ: لا سقفَ تزامن، ولا إلغاء، ولا هويّةَ إقلاع، ولا ختمَ إغلاق، والحاصدُ لا يدور
إلا مع `SILK_REFRESH_HOURS`. هذه الوحدة مرآةُ `study_runtime` للمسار الجذري:
مقابضُ في الذاكرة (عمليةٌ واحدة — نفسُ افتراض R2)، سقفٌ بـ`BoundedSemaphore`،
إلغاءٌ تعاونيّ بحدث يقرؤه `silk_context.check_cancelled`، هويّةُ إقلاع تُختَم
في لقطة التقدّم، وخيطُ حاصدٍ دوريّ مستقلّ عن التحديث الدوري.

**ما لا تفعله:** لا تستأنف تلقائياً (قرار المالك في R2)، ولا تقتل خيوطاً —
الإلغاءُ يقع عند نقطة التفتيش التالية. الصفوفُ التي يملكها إقلاعٌ آخر تبقى
للحاصد بعُمر نبضتها (الحُكمُ بالنبضة لا بالهويّة).

Root ``/research`` run registry (R2b): a bounded HTTP concurrency cap, cooperative cancel events, a periodic orphan reaper independent of ``SILK_REFRESH_HOURS``, and the shutdown stamp — the root counterpart of ``silk_platform/study_runtime``.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import threading
import time
import uuid

log = logging.getLogger(__name__)

BOOT_ID = uuid.uuid4().hex


def boot_id() -> str:
    """هويّةُ هذا الإقلاع — تُختَم في `progress_json.boot_id` لكل تشغيلة."""
    return BOOT_ID


@dataclasses.dataclass
class RunHandle:
    analysis_id: int
    origin: str                      # "http" | "platform"
    cancel: threading.Event
    started_monotonic: float
    thread: threading.Thread | None = None
    reason: str = ""
    # حدثُ إلغاءٍ خارجيّ (تشغيلةُ جسر المنصّة تحمل حدثَ `study_runtime`) — يُضبَط
    # معه كي يصل إلغاءُ المسار الجذري إلى الخطّ نفسه.
    outer: threading.Event | None = None


_RUNS: dict[int, RunHandle] = {}
_JANITOR_EVERY_S = 3600.0
_last_janitor = 0.0
_LOCK = threading.Lock()
_SLOTS: threading.BoundedSemaphore | None = None
_SLOTS_CAP = 0
_REAPER: threading.Thread | None = None
_STOP = threading.Event()
_TICK_HOOKS: list = []


def _hook_key(fn) -> tuple:
    return (getattr(fn, "__module__", ""), getattr(fn, "__qualname__", repr(fn)))


def add_tick_hook(fn) -> None:
    """سجّل دالّةً تُنادى في كلّ دورة `tick()` — R9 (CONC-3): تجديدُ لقطة `/health`
    يركب دورةَ الحاصد بدل خيطٍ ثانٍ. idempotent بالاسم المؤهَّل لا بالهويّة: إعادةُ
    تحميل `api` (الاختبارات) تصنع دالّةً جديدة بنفس الاسم فتحلّ محلّ القديمة."""
    key = _hook_key(fn)
    for i, existing in enumerate(_TICK_HOOKS):
        if _hook_key(existing) == key:
            _TICK_HOOKS[i] = fn
            return
    _TICK_HOOKS.append(fn)


def max_concurrent() -> int:
    """سقفُ تشغيلات `/research` الجذرية المتزامنة من HTTP — `SILK_MAX_CONCURRENT_RESEARCH` (٣)."""
    try:
        return max(1, int(os.environ.get("SILK_MAX_CONCURRENT_RESEARCH", "3") or "3"))
    except ValueError:
        return 3


def _slots() -> threading.BoundedSemaphore:
    global _SLOTS, _SLOTS_CAP
    cap = max_concurrent()
    with _LOCK:
        if _SLOTS is None or _SLOTS_CAP != cap:
            _SLOTS = threading.BoundedSemaphore(cap)
            _SLOTS_CAP = cap
        return _SLOTS


def try_acquire() -> bool:
    """احجز فتحةَ تشغيلٍ لتشغيلةٍ من HTTP — False فوراً حين يمتلئ السقف (503 `research_busy`).
    تشغيلاتُ المنصّة لا تمرّ من هنا (سقفُها في `study_runtime`)."""
    return _slots().acquire(blocking=False)


def _release_slot() -> None:
    try:
        _slots().release()
    except ValueError:  # حرّرت أكثر ممّا حجزت — لا يحدث إلا في الاختبارات
        pass


def register(analysis_id: int, *, origin: str = "http",
             thread: threading.Thread | None = None) -> RunHandle:
    """سجّل تشغيلةً حيّة بمقبضها — حدثُ الإلغاء يُنشأ هنا ويُقرأ في الخطّ."""
    h = RunHandle(analysis_id=int(analysis_id), origin=origin,
                  cancel=threading.Event(), started_monotonic=time.monotonic(),
                  thread=thread)
    with _LOCK:
        _RUNS[h.analysis_id] = h
    return h


def release(analysis_id: int) -> None:
    """أزل المقبض وحرّر فتحةَ HTTP إن كانت التشغيلةُ من HTTP — في `finally` دائماً."""
    with _LOCK:
        h = _RUNS.pop(int(analysis_id), None)
    if h is not None and h.origin == "http":
        _release_slot()


def handle(analysis_id: int) -> RunHandle | None:
    with _LOCK:
        return _RUNS.get(int(analysis_id))


def is_running(analysis_id: int) -> bool:
    return handle(analysis_id) is not None


def active_ids() -> list[int]:
    with _LOCK:
        return sorted(_RUNS)


def cancel(analysis_id: int, reason: str = "requested") -> bool:
    """اطلب إلغاءً تعاونياً — True إن كانت التشغيلةُ مسجَّلة هنا."""
    h = handle(analysis_id)
    if h is None:
        return False
    h.reason = reason
    h.cancel.set()
    if h.outer is not None:
        h.outer.set()
    return True


def cancel_requested(analysis_id: int) -> bool:
    h = handle(analysis_id)
    return bool(h is not None and h.cancel.is_set())


def shutdown() -> None:
    """ختمُ الإغلاق — يُنادى من معالج `shutdown` في التطبيق الجذري (API-3/CONC-5).

    كلُّ تشغيلةٍ مسجَّلة في هذا الإقلاع: يُضبَط حدثُ إلغائها، وصفُّها الذي ما زال
    `running` يُوسَم فاشلاً بسببٍ يسمّي الانقطاع، ويُصالَح حجزُه الدولاري — نفسُ ما
    يفعله `study_runtime._interrupt_run` للمنصّة. الخيوطُ daemon تموت مع العملية.
    """
    with _LOCK:
        handles = list(_RUNS.values())
    for h in handles:
        h.reason = "shutdown"
        h.cancel.set()
        if h.outer is not None:     # مراجعة: الخطُّ يقرأ الحدثَ الخارجي إن وُجد
            h.outer.set()
        try:
            import silk_storage
            row = silk_storage.get_research_run(h.analysis_id)
            if row and row.get("status") == "running":
                silk_storage.mark_research_failed(
                    h.analysis_id,
                    f"interrupted: process shutdown (boot {BOOT_ID[:8]}) — "
                    "أعد الاستئناف بـresume لتُعاد البعثات المحفوظة بلا إعادة دفع")
                silk_storage.reconcile_failed_run_usd(h.analysis_id)
        except Exception as exc:  # noqa: BLE001 — الإغلاق لا يرفع أبداً
            log.warning("shutdown stamp failed for research run %s: %s",
                        h.analysis_id, exc)
    # R9 (CONC-9/CONC-5): عمّالُ استطلاع مكشطة الخرائط يستيقظون ويخرجون الآن، لا بعد
    # انقضاء نومهم (عمّالُ مجمّع البعثات يخرجون بالإلغاء التعاوني أعلاه).
    try:
        import silk_gmaps
        silk_gmaps.stop_all()
    except Exception as exc:  # noqa: BLE001
        log.debug("gmaps stop_all skipped: %s", exc)
    _STOP.set()


def reap_interval_s() -> float:
    """فاصلُ الحاصد الدوريّ بالثواني — `SILK_ORPHAN_REAP_INTERVAL_S` (٣٠٠؛ ٠ = مطفأ)."""
    try:
        return max(0.0, float(os.environ.get("SILK_ORPHAN_REAP_INTERVAL_S", "300") or "300"))
    except ValueError:
        return 300.0


def tick() -> dict:
    """مرورٌ واحد: حصدُ تشغيلات `/research` العالقة + كنسُ الآثار — قابلٌ للاختبار مباشرةً."""
    out: dict = {"reaped": 0, "janitor": None}
    try:
        import silk_storage
        out["reaped"] = len(silk_storage.reap_orphan_research_runs(
            exclude=active_ids()) or [])
    except Exception as exc:  # noqa: BLE001 — الحاصد قناةٌ جانبية
        log.warning("research reaper tick failed: %s", exc)
    # مراجعة R2b: الكنسُ ساعيٌّ لا مع كلّ حصد (كان ١٢× إيقاعه القديم).
    global _last_janitor
    now = time.monotonic()
    if _last_janitor == 0.0 or now - _last_janitor >= _JANITOR_EVERY_S:
        _last_janitor = now
        try:
            import silk_janitor
            out["janitor"] = silk_janitor.sweep()
        except Exception as exc:  # noqa: BLE001
            log.debug("janitor sweep skipped: %s", exc)
    for fn in list(_TICK_HOOKS):              # R9: لقطةُ /health وأخواتها
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — خطّافٌ فاشل لا يُسقط الحاصد
            log.debug("tick hook %s failed: %s", getattr(fn, "__name__", fn), exc)
    return out


def start_reaper() -> threading.Thread | None:
    """ابدأ خيطَ الحاصد الدوريّ — مستقلٌّ عن `SILK_REFRESH_HOURS` (API-3). idempotent؛
    `SILK_ORPHAN_REAP_INTERVAL_S=0` = لا خيط (افتراضُ الاختبارات)."""
    global _REAPER
    interval = reap_interval_s()
    if interval <= 0:
        return None
    with _LOCK:
        if _REAPER is not None and _REAPER.is_alive():
            return _REAPER
        _STOP.clear()

        def _loop() -> None:
            while not _STOP.wait(interval):
                tick()

        _REAPER = threading.Thread(target=_loop, name="silk-research-reaper",
                                   daemon=True)
        _REAPER.start()
        return _REAPER


def reset_for_tests() -> None:
    """صفّر السجلّ — للاختبارات وحدها (كـ`study_runtime.reset_for_tests`)."""
    global _RUNS, _SLOTS, _SLOTS_CAP, _REAPER, _last_janitor
    _STOP.set()
    _last_janitor = 0.0
    with _LOCK:
        for h in _RUNS.values():
            h.cancel.set()
        _RUNS = {}
        _SLOTS = None
        _SLOTS_CAP = 0
        reaper, _REAPER = _REAPER, None
    if reaper is not None and reaper.is_alive():
        reaper.join(timeout=2)
    _STOP.clear()
    try:                      # R9: عمّالُ الخرائط أيضاً — `shutdown()` في اختبارٍ سابق لا يُطفئهم للأبد
        import silk_gmaps
        silk_gmaps._STOP.clear()
    except Exception:  # noqa: BLE001
        pass
