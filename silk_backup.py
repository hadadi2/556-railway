"""نسخ احتياطي لقواعد SQLite — in-process SQLite backup (stdlib only).

**الفجوة التي يغلقها (تدقيق 2026-08-17):** السجلّ التراكمي المدفوع الثمن
(التحليلات + مخزن الحقائق + المنصّة متعددة المستأجرين + العدّادات) يعيش كله
على وحدة تخزين واحدة **بلا أي نسخة ثانية** — تلف الوحدة أو حذف خاطئ يمحو كل
شيء، والقاعدة «لا تُحذف بيانات silk.db أبداً» كانت بلا حماية مادية. الفجوة
معترف بها في `docs/ANALYSIS.md` («no backups») ومخطّطة في REBUILD_PLAN (M8)
بلا تنفيذ.

**التصميم يحترم القيود المستقرة:**
- خيط داخل العملية (نفس نمط `silk_collectors.start_scheduler`) — لا خدمة cron
  منفصلة لأن وحدة Railway تُركَّب على خدمة واحدة بالضبط.
- stdlib فقط: `sqlite3.Connection.backup` (نسخة متّسقة حتى مع كاتب نشط —
  لا نسخ ملفات ساذج يلتقط نصف معاملة)، `glob` للدورة.
- **الصمّام مطفأ افتراضياً** (`SILK_BACKUP_HOURS` غير مضبوط = لا خيط) — قاعدة
  الأعلام الجديدة (الدرس ٧٠): التفعيل قرار مالك بعد الدمج.
- كل فشل لكل هدف = بند معلن في المانيفست، لا انهيار ولا صمت (عائلة الدرس ٢٦:
  الفشل يظهر للمشغّل).

المخارج: `run_backup()` يدوي/مجدول؛ `GET /ops/backup` (محروسة بالمفتاح) تشغّل
نسخة وتعيد المانيفست؛ `GET /ops/backup/{name}` تنزّل أحدث نسخة لمخزنٍ مسمّى
كي يسحبها المالك خارج Railway.
"""
from __future__ import annotations

import datetime
import glob
import logging
import os
import sqlite3
import shutil
import tarfile
import threading
from contextlib import closing, suppress as contextlib_suppress

log = logging.getLogger(__name__)

# أسماء المخازن المدعومة — المصدر الواحد الذي تقرؤه نقطة التنزيل في api.py
# (كانت قائمة منسوخة هناك: هدف جديد هنا كان سيبقى 404 هناك للأبد — §58).
# R5 (تدقيق 2026-09-01، DB-9): `platform_files` = أرشيفُ صور المصانع المرفوعة —
# صفوفُ `images` كانت تُنسَخ وملفّاتُها لا، فاسترجاعٌ يعيد صفوفاً تشير إلى فراغ.
STORE_NAMES = ("silk", "store", "usage", "ops_errors", "watchdog", "platform",
               "platform_files")
UPLOADS_NAME = "platform_files"

# أهداف النسخ: (اسم منطقي، دالّة تُرجِع المسار وقت النداء). الاستيراد كسول
# داخل كل محلّ كي تبقى الوحدة قابلة للاستيراد بلا أي تبعية، وتعذُّر محلٍّ
# واحد لا يمنع بقية الأهداف (فجوة معلنة في المانيفست).
def _targets() -> list[tuple[str, str]]:
    """المخازن القائمة فعلاً وقت النداء — (name, path) للملفات الموجودة فقط."""
    out: list[tuple[str, str]] = []

    def _try(name: str, fn) -> None:
        try:
            p = fn()
            if p and os.path.exists(p):
                out.append((name, p))
        except Exception as e:  # noqa: BLE001 — هدف متعذّر ≠ تعطيل البقية
            log.warning("backup target %s unresolvable: %s", name, e)

    _try("silk", lambda: __import__("silk_storage")._db_path())
    _try("store", lambda: __import__("silk_store")._db_path())
    _try("usage", lambda: __import__("silk_usage")._db_path())
    _try("ops_errors", lambda: __import__("silk_ops_log")._db_path())
    _try("watchdog", lambda: __import__("silk_watchdog")._db_path())
    _try("platform",
         lambda: __import__("silk_platform.db", fromlist=["db_path"]).db_path())
    return out


def backup_dir() -> str:
    """مجلّد النسخ — `SILK_BACKUP_DIR` صريحاً، وإلا `SILK_DATA_DIR/backups`،
    وإلا `data/backups` (نفس سلّم توجيه بقية المخازن)."""
    explicit = os.environ.get("SILK_BACKUP_DIR", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("SILK_DATA_DIR", "").strip()
    if base:
        return os.path.join(base, "backups")
    return os.path.join("data", "backups")


def _keep_days() -> int:
    try:
        return max(1, int(os.environ.get("SILK_BACKUP_KEEP_DAYS", "7")))
    except ValueError:
        return 7


def run_backup(dest_dir: str | None = None) -> dict:
    """انسخ كل المخازن القائمة الآن — نسخة متّسقة عبر sqlite3.backup.

    يرجّع مانيفستاً صادقاً: ما نُسخ (بحجمه المقيس فعلاً)، وما فشل ولماذا
    (فجوة معلنة)، وما حُذف بالدورة. لا يرفع أبداً — النسخ شبكة أمان لا مسار
    تشغيل، وعطله يُعلَن في المانيفست وسجلّ العمليات.
    """
    dest = dest_dir or backup_dir()
    manifest: dict = {"ran_at": datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds"),
        "dir": dest, "files": [], "failures": [], "rotated_out": []}
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as e:
        # عقد «لا يرفع أبداً» يشمل تعذّر المجلد نفسه (وحدة غير مركّبة/قراءة
        # فقط) — فشلٌ معلن في المانيفست لا 500 عارية (ملاحظة مراجعة §58).
        manifest["failures"].append({"name": "_dest_dir", "source": dest,
                                     "error": str(e)[:300]})
        return manifest
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    for name, src in _targets():
        out_path = os.path.join(dest, f"{name}.{stamp}.db")
        tmp_path = out_path + ".tmp"
        try:
            # اكتب إلى مؤقت ثم استبدل ذرّياً — فشلٌ منتصف النسخ كان يترك ملفاً
            # مبتوراً تخدمه `latest_backup` كأحدث نسخة، والتنزيل أثناء نسخة
            # جارية كان يعيد نصف ملف (ملاحظة مراجعة §58 — عالية الخطورة):
            # شبكة الأمان لا يجوز أن تقدّم نسخة فاسدة أبداً.
            # `sqlite3.Connection.__exit__` يُنهي المعاملة ولا **يُغلِق**
            # الاتصال — فكانت كلُّ تشغيلةِ نسخٍ تُسرِّب واصفَي ملفٍّ لكلّ
            # مخزن (حتى ٦ مخازن = ١٢ واصفاً)، فيبلغ حدُّ الواصفات بعد مئاتِ
            # النداءات وتفشل فتحاتُ SQLite غيرُ المرتبطة (ملاحظة مراجعة §58).
            # R5 (DB-6/CONC-7/DB-10): المُوصِّل المشترك (مهلة ٣٠ ث لا ٥)؛ النسخُ
            # خطوةٌ واحدة عمداً — نسخٌ مقسَّط يُعاد من أوّله كلّما تغيّر المصدر
            # (كاتبٌ مستمرّ = لا نهاية؛ مراجعة §58)، وتحت WAL لا تحجب الخطوةُ
            # الواحدة الكتّابَ أصلاً. الطبعةُ ملفٌّ واحد في وضع DELETE (لا `-wal`
            # مرافق) وتُفحَص بـ`integrity_check` قبل اعتمادها — طبعةٌ فاسدة لا
            # تصل المجلّد أبداً.
            import silk_sqlite
            with closing(silk_sqlite.connect(src, row_factory=False)) as s, \
                    closing(sqlite3.connect(tmp_path)) as d:
                s.backup(d)
                d.execute("PRAGMA journal_mode=DELETE")
            verdict = _integrity(tmp_path)
            if verdict != "ok":
                raise RuntimeError(f"integrity_check: {verdict}")
            os.replace(tmp_path, out_path)
            manifest["files"].append({"name": name, "source": src,
                                      "path": out_path,
                                      "bytes": os.path.getsize(out_path)})
        except Exception as e:  # noqa: BLE001 — فشل هدف = بند معلن لا انهيار
            with contextlib_suppress(OSError):
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            manifest["failures"].append({"name": name, "source": src,
                                         "error": str(e)[:300]})
            try:
                import silk_ops_log
                silk_ops_log.record_service_failure(
                    "backup", f"backup of {name} failed: {e}",
                    context={"source": src})
            except Exception:  # noqa: BLE001
                pass
    _backup_uploads(dest, stamp, manifest)
    manifest["rotated_out"] = _rotate(dest)
    return manifest


def _integrity(path: str) -> str:
    """`PRAGMA integrity_check` على طبعةٍ — نصُّ الحكم كما يعيده SQLite."""
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)) as c:
        return str(c.execute("PRAGMA integrity_check").fetchone()[0])


def _uploads_dir() -> str | None:
    try:
        from silk_platform import storage
        d = storage.storage_dir()
        return d if d and os.path.isdir(d) else None
    except Exception as e:  # noqa: BLE001 — هدفٌ متعذّر ≠ تعطيل البقية
        log.warning("backup target %s unresolvable: %s", UPLOADS_NAME, e)
        return None


def _backup_uploads(dest: str, stamp: str, manifest: dict) -> None:
    """أرشِف مجلّدَ الصور المرفوعة كاملاً — R5 (DB-9). غيابُه = هدفٌ غائب لا فشل."""
    src = _uploads_dir()
    if not src:
        return
    out_path = os.path.join(dest, f"{UPLOADS_NAME}.{stamp}.tar")
    tmp_path = out_path + ".tmp"
    try:
        members = 0
        with tarfile.open(tmp_path, "w") as tar:
            for root, _dirs, files in os.walk(src):
                for name in files:
                    full = os.path.join(root, name)
                    try:
                        tar.add(full, arcname=os.path.relpath(full, src))
                    except FileNotFoundError:
                        continue   # حُذف بين المسح والقراءة — الطبعةُ التالية تلحقه
                    members += 1
        os.replace(tmp_path, out_path)
        manifest["files"].append({"name": UPLOADS_NAME, "source": src,
                                  "path": out_path,
                                  "bytes": os.path.getsize(out_path),
                                  "members": members})
    except Exception as e:  # noqa: BLE001 — فشلُ هدف = بندٌ معلَن
        with contextlib_suppress(OSError):
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        manifest["failures"].append({"name": UPLOADS_NAME, "source": src,
                                     "error": str(e)[:300]})


def restore(name: str, stamp: str, dest: str, *, overwrite: bool = False,
            backup_dir_path: str | None = None) -> dict:
    """استرجِع طبعةً إلى `dest` — R5 (DB-10/TEST-8): الاسترجاعُ شيفرةٌ تُختبَر لا وثيقة.

    قاعدة: تُفحَص سلامةُ الطبعة أولاً، ولا يُكتَب فوق وجهةٍ قائمة إلا بـ`overwrite`
    (خطوةُ «احفظ الحالية أولاً» في الدليل)؛ عند الكتابة فوقها تُزال ملفّات
    `-wal/-shm` المرافقة كي لا تُطبَّق يوميّةٌ قديمة على القاعدة المُستَرجَعة.
    الأرشيفُ (`platform_files`) يُفكّ في مجلّدٍ فارغ أو غائب. لا تلمس هذه
    الدالّة المساراتِ الحيّة بنفسها — المُنادي يسمّي الوجهة.
    """
    bdir = backup_dir_path or backup_dir()
    out: dict = {"ok": False, "name": name, "stamp": stamp, "dest": dest,
                 "integrity": "", "error": ""}
    ext = "tar" if name == UPLOADS_NAME else "db"
    src = os.path.join(bdir, f"{name}.{stamp}.{ext}")
    if not os.path.exists(src):
        out["error"] = f"no such backup: {os.path.basename(src)}"
        return out
    try:
        if ext == "db":
            verdict = _integrity(src)
            out["integrity"] = verdict
            if verdict != "ok":
                out["error"] = "backup fails integrity_check — refusing to restore"
                return out
            if os.path.exists(dest) and not overwrite:
                out["error"] = "destination exists — pass overwrite=True after saving it"
                return out
            parent = os.path.dirname(dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copyfile(src, dest + ".tmp")
            os.replace(dest + ".tmp", dest)
            for suffix in ("-wal", "-shm", "-journal"):
                with contextlib_suppress(OSError):
                    os.remove(dest + suffix)
        else:
            if os.path.isdir(dest) and os.listdir(dest) and not overwrite:
                out["error"] = "destination directory is not empty — pass overwrite=True"
                return out
            os.makedirs(dest, exist_ok=True)
            with tarfile.open(src, "r") as tar:
                tar.extractall(dest, filter="data")
            out["integrity"] = "ok"
        out["ok"] = True
    except Exception as e:  # noqa: BLE001 — فشلٌ معلَن لا انهيار
        out["error"] = str(e)[:300]
    return out


def _rotate(dest: str) -> list[str]:
    """أبقِ آخر `SILK_BACKUP_KEEP_DAYS` يوماً — احذف طبعات النسخ الأقدم فقط.

    الحذف مقصور بنمط `{name}.{YYYY-MM-DD}.db` داخل مجلّد النسخ — لا يلمس هذه
    الدالة أي ملف آخر أبداً (قاعدة «لا حذف لبيانات silk.db» تخصّ المخازن
    الحيّة؛ هذه طبعات النسخ نفسها).
    """
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=_keep_days())).strftime("%Y-%m-%d")
    removed: list[str] = []
    for f in (glob.glob(os.path.join(dest, "*.*.db"))
              + glob.glob(os.path.join(dest, "*.*.tar"))):
        base = os.path.basename(f)
        parts = base.rsplit(".", 2)
        if len(parts) != 3 or len(parts[1]) != 10:
            continue   # ليس من طبعاتنا — لا يُمَسّ
        if parts[1] < cutoff:
            try:
                os.remove(f)
                removed.append(base)
            except OSError as e:
                log.warning("backup rotation could not remove %s: %s", base, e)
    return removed


def latest_backup(name: str, dest_dir: str | None = None) -> str | None:
    """أحدث طبعة نسخ لمخزن مسمّى — None إن لم توجد (فجوة معلنة لا اختلاق)."""
    dest = dest_dir or backup_dir()
    ext = "tar" if name == UPLOADS_NAME else "db"
    files = sorted(glob.glob(os.path.join(dest, f"{name}.*.{ext}")))
    return files[-1] if files else None


# ── المجدول — خيط داخل العملية، opt-in حصراً ─────────────────────────────────
_thread: threading.Thread | None = None


def start_scheduler() -> bool:
    """ابدأ خيط النسخ الدوري — فقط مع `SILK_BACKUP_HOURS` ≥ 1 (مطفأ افتراضاً).

    نفس عقد `silk_collectors.start_scheduler`: daemon، إعادة النشر تقتله بلا
    ضرر (النسخة التالية عند أول دورة)، ونداء ثانٍ لا يبدأ خيطاً ثانياً.
    """
    global _thread
    raw = os.environ.get("SILK_BACKUP_HOURS", "").strip()
    try:
        hours = float(raw) if raw else 0.0
    except ValueError:
        hours = 0.0
    if hours <= 0 or (_thread is not None and _thread.is_alive()):
        return False

    def _loop() -> None:
        import time
        while True:
            try:
                m = run_backup()
                log.info("silk-backup: %d نسخ، %d إخفاق، %d مُدوَّر",
                         len(m["files"]), len(m["failures"]),
                         len(m["rotated_out"]))
            except Exception:  # noqa: BLE001 — لا يقتل الخيط أبداً
                log.warning("silk-backup: run failed", exc_info=True)
            time.sleep(hours * 3600)

    _thread = threading.Thread(target=_loop, name="silk-backup", daemon=True)
    _thread.start()
    return True
