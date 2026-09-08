"""كنّاس القرص الدائم — the persistent-disk janitor (retention sweeper).

**لماذا (تدقيق 2026-08-27، البند ١١).** كل ما يُكتب على وحدة Railway ينمو بلا
سقف: آثار `data/traces/*.jsonl` (تحمل البرومبتات كاملةً فهي الأضخم)، ملفات
`cache/` (الـTTL يُفحَص **عند القراءة** فقط — فملفٌ لا يُقرَأ ثانيةً يبقى
للأبد)، وصفوف `ops_errors`/`watchdog_records` التي تتراكم بلا حدّ. أول عرَض
لامتلاء القرص ليس تحذيراً لطيفاً: هو **فشل حفظ تحليل مدفوع** — أسوأ عرَضٍ
ممكن، ويقع بعد أن يكون العميل قد دفع.

**المبدأ الحاكم — لا حذف لشيءٍ ذي قيمة تعاقدية.** الكنّاس **لا يمسّ**
`data/silk.db` (قاعدة التحليلات: «Never delete or modify existing data»،
`CLAUDE.md`) ولا `silk_store.db` (مخزن الحقائق — إعادة جلبه تكلّف مالاً) ولا
`usage.db` (دفتر المحاسبة). يمسّ ثلاثة أصنافٍ **قابلة لإعادة التوليد أو
تشخيصية بطبعها** فقط.

**صمّام الميزة الجديدة (الدرس ٧٠): مطفأ افتراضياً.** بلا `SILK_RETENTION_DAYS`
لا يُحذَف شيء إطلاقاً — التفعيل قرار مالك.

Retention sweeper for regenerable/diagnostic artifacts only; never the
analyses DB, the fact store, or the usage ledger. Off unless configured.
"""
import glob
import logging
import os
import time

log = logging.getLogger(__name__)

# سقوفٌ منفصلة لكل صنف: الأثر أضخم وأسرع تقادماً من صفّ خطأٍ تشغيلي.
# Per-class windows override SILK_RETENTION_DAYS; traces/cache default 30, ops off.
_DEFAULTS = {
    "traces": "SILK_TRACE_RETENTION_DAYS",
    "cache": "SILK_CACHE_RETENTION_DAYS",
    "ops": "SILK_OPS_RETENTION_DAYS",
}


def _days(kind: str) -> float:
    """نافذة الاحتفاظ؛ صفر يعطّلها، والآثار والذاكرة افتراضهما ٣٠ يوماً."""
    raw = os.environ.get(_DEFAULTS[kind], "").strip()
    if not raw:
        raw = os.environ.get("SILK_RETENTION_DAYS", "").strip()
    if not raw and kind in {"cache", "traces"}:
        # EXT-4 (قرار المالك 2026-09-05): ذاكرةُ الطلبات تُكنَس بعد ٣٠ يوماً افتراضياً —
        # آثار التشخيص ٣٠ يوماً أيضاً؛ نقاط تفتيش الأدلة محفوظة في SQLite ولا تُكنس.
        return 30.0
    try:
        return max(0.0, float(raw or 0))
    except ValueError:
        log.warning("retention value for %s is not a number: %r", kind, raw)
        return 0.0


# لاحقاتٌ لا تُحذَف أبداً مهما كان المجلّد المضبوط (مراجعة §58): مشغّلٌ يوجّه
# `SILK_CACHE_DIR` بالخطأ لجذر الوحدة كان سيجعل الكنّاس يحذف **قواعد الإنتاج**.
# الكنّاس شبكةُ أمانٍ للقرص، لا يجوز أن يصير هو الكارثة.
# Extensions the janitor must never delete, whatever directory it is pointed at.
# **المطابقة على نهاية الاسم كاملاً لا على `splitext`** (مراجعة §58):
# `splitext("x.json.gz")` يعيد `.gz` وحدها، و`silk.db-journal` امتدادُه
# `.db-journal` لا `.db` — فحارسٌ يقارن الامتداد وحده كان سيسمح بحذف دفتر
# تراجُع SQLite (وهو جزءٌ من القاعدة الحيّة، حذفُه أثناء معاملةٍ يفسدها).
_NEVER_DELETE = (".db", ".db-wal", ".db-shm", ".db-journal", ".sqlite",
                 ".sqlite3", ".csv", ".py", ".sql", ".json.gz")


def _protected(path: str) -> bool:
    """هل يُمنَع حذفُه مهما كان النمط؟ — suffix match, not just splitext."""
    name = os.path.basename(path).lower()
    return any(name.endswith(suffix) for suffix in _NEVER_DELETE)


def _sweep_dir(path: str, days: float, pattern: str = "*") -> int:
    """احذف ملفات أقدم من النافذة — returns how many were removed."""
    if days <= 0 or not path or not os.path.isdir(path):
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for f in glob.glob(os.path.join(path, pattern)):
        if _protected(f):
            continue   # حارسٌ صلب: قاعدةُ إنتاجٍ لا تُحذَف ولو طابقت النمط
        try:
            if os.path.isfile(f) and os.path.getmtime(f) < cutoff:
                os.remove(f)
                removed += 1
        except OSError as e:   # ملفٌ اختفى/مقفل — لا يُسقِط الكنسة
            log.debug("janitor could not remove %s: %s", f, e)
    return removed


_trace_sweep_last = (None, 0.0)
import threading
_trace_sweep_lock = threading.Lock()


def sweep_traces_if_due(path: str) -> int:
    """كنس محلي عند بدء أثر، مرة في الساعة؛ بلا مجدول أو نداءات مزود."""
    global _trace_sweep_last
    with _trace_sweep_lock:
        now = time.monotonic()
        if _trace_sweep_last[0] == path and now - _trace_sweep_last[1] < 3600:
            return 0
        _trace_sweep_last = (path, now)
        return _sweep_dir(path, _days("traces"), "*.jsonl")


def _sweep_rows(days: float) -> dict:
    """قصّ صفوف السجلّات التشخيصية — ops_errors + watchdog_records.

    كلاهما تشخيصيّ بحت (بلاغُ عطلٍ قديمٍ لا يُقرأ بعد أسابيع)، وكلاهما خارج
    قاعدة التحليلات تماماً — فحذفُ القديم منهما لا يمسّ أي التزام تعاقدي.
    """
    out = {"ops_errors": 0, "watchdog_records": 0}
    if days <= 0:
        return out
    # الطابع المخزَّن **محلّيٌّ ساذج** (`datetime.now().isoformat()` في
    # `silk_ops_log.py:66` و`silk_watchdog.py:144`)، فالمقارنة النصّية يجب أن
    # تكون بنفس المنطقة وإلا انزاحت النافذة بمقدار إزاحة الحاوية عن UTC
    # (مراجعة §58). Naive-local cutoff to match how the rows are stamped.
    import datetime
    iso = datetime.datetime.fromtimestamp(
        time.time() - days * 86400).isoformat()
    for mod_name, table in (("silk_ops_log", "ops_errors"),
                            ("silk_watchdog", "watchdog_records")):
        try:
            mod = __import__(mod_name)
            conn = mod._connect(mod._db_path())
            try:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE created_at < ?", (iso,))
                conn.commit()
                out[table] = cur.rowcount or 0
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001 — الكنس تحسين، لا يُسقِط الخيط
            log.warning("janitor row sweep failed for %s: %s", table, e)
    return out


def sweep() -> dict:
    """كنسةٌ واحدة — one pass. Returns a per-class count dict (all zeros = off).

    الآثار والذاكرة القديمة فقط تُكنس افتراضياً؛ لا حذف لقاعدة بيانات.
    """
    import silk_trace
    result = {"traces": 0, "cache": 0, "ops_errors": 0, "watchdog_records": 0}

    result["traces"] = _sweep_dir(silk_trace._default_dir(), _days("traces"),
                                  "*.jsonl")

    cache_days = _days("cache")
    if cache_days > 0:
        try:
            import silk_cache
            # `*.json` حصراً: ملفات ذاكرة الطلبات كلها بهذه اللاحقة، وأيّ
            # شيء آخر في المجلّد ليس ملكاً للكنّاس (مراجعة §58).
            result["cache"] = _sweep_dir(silk_cache._cache_dir(), cache_days,
                                         "*.json")
        except Exception as e:  # noqa: BLE001
            log.warning("janitor cache sweep failed: %s", e)

    result.update(_sweep_rows(_days("ops")))
    if any(result.values()):
        log.info("janitor swept: %s", result)
    return result
