#!/bin/sh
# نقطةُ دخول الحاوية — R7 (التدقيق الجنائي 2026-09-01، SEC-8/EXT-15): الخادمُ كان
# يعمل **جذراً** داخل الحاوية (LibreOffice يحلّل مستنداتٍ من مدخلات المستخدم).
# يُهيّأ القرصُ الدائم للمستخدم `silk` ثم تُسقَط الصلاحيات عبر `setpriv`؛
# `SILK_RUN_AS_ROOT=1` مخرجٌ تشخيصيّ صريح لا يُضبَط في الإنتاج.
# Drop root before exec; SILK_RUN_AS_ROOT=1 is a diagnostic escape hatch only.
set -eu
if [ "${SILK_RUN_AS_ROOT:-0}" = "1" ] || [ "$(id -u)" != "0" ]; then
    exec "$@"
fi
# كلُّ مسارِ مخزنٍ موجَّهٍ صراحةً (المتغيّراتُ الفردية تفوز على SILK_DATA_DIR) يُملَّك أيضاً —
# `SILK_DB=/data/silk.db` بلا `SILK_DATA_DIR` شكلٌ موثَّق كان يبقى للجذر فلا يكتبه uid 10001.
own_dir() {
    [ -n "$1" ] || return 0
    mkdir -p "$1" || echo "entrypoint: mkdir $1 failed" >&2
    chown -R silk:silk "$1" || echo "entrypoint: chown $1 failed" >&2
}
own_dir "${SILK_DATA_DIR:-}"
for f in "${SILK_DB:-}" "${SILK_STORE_DB:-}" "${SILK_USAGE_DB:-}" "${SILK_OPS_LOG_DB:-}" \
         "${SILK_WATCHDOG_DB:-}" "${SILK_PLATFORM_DB:-}"; do
    [ -n "$f" ] && own_dir "$(dirname "$f")"
done
for d in "${SILK_CACHE_DIR:-}" "${SILK_PLATFORM_STORAGE_DIR:-}" "${SILK_TRACE_DIR:-}"; do
    own_dir "$d"
done
exec setpriv --reuid=silk --regid=silk --init-groups "$@"
