"""طبقة قاعدة بيانات المنصّة — Silk platform DB layer (SQLite, stdlib only).

قاعدة بيانات مستقلّة عن محرّك ذكاء السوق (`data/silk.db`) كي لا تختلط بيانات
المستأجرين ببيانات التحليل ولا تُمسّ أبداً. `SILK_PLATFORM_DB` يوجّه الملف،
ويُشتَقّ من `SILK_DATA_DIR` (المتغيّر الموحّد لكل المخازن) حين لا يُضبَط صراحةً.

A dedicated DB, separate from the market-intelligence store. Pure stdlib
(sqlite3 + glob); imports offline, never touches the network, never fabricates.
"""
from __future__ import annotations

import datetime
import glob
import os
import re
import sqlite3

_DEFAULT_PATH = "data/platform.db"
_MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations", "platform")


def now_iso() -> str:
    """طابع زمني UTC بدقّة الثانية — ISO-8601 UTC stamp (timezone-aware)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path() -> str:
    """مسار قاعدة المنصّة وقت النداء — resolve at call time (env or default).

    `SILK_PLATFORM_DB` صريحٌ أولاً، ثم اشتقاق من `SILK_DATA_DIR`، وإلا الافتراضي.
    """
    explicit = os.environ.get("SILK_PLATFORM_DB", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("SILK_DATA_DIR", "").strip()
    if base:
        return os.path.join(base, "platform.db")
    return _DEFAULT_PATH


def connect(path: str | None = None) -> sqlite3.Connection:
    """افتح اتصالاً وفعّل قيود المفاتيح الأجنبية — open a connection.

    `row_factory=Row` للوصول بالاسم، و`PRAGMA foreign_keys=ON` كي تُفرَض قيود
    الـFK فعلياً (SQLite يعطّلها افتراضياً). المجلّد الأب يُنشأ عند الحاجة.
    """
    p = path or db_path()
    # R5 (تدقيق 2026-09-01، DB-6): المُوصِّل المشترك `silk_sqlite.connect` — نفسُ
    # المهلة (٣٠ ث) و`busy_timeout` اللذين أثبتتهما حادثة القفل، ومعهما WAL +
    # synchronous=NORMAL فلا يحجب الكاتبُ القرّاءَ (كانت المنصّةُ المخزنَ الوحيد
    # الذي يكرّر سباكة الاتصال بنفسه).
    import silk_sqlite
    return silk_sqlite.connect(p, foreign_keys=True)


def apply_migrations(path: str | None = None) -> list[str]:
    """طبّق ترحيلات migrations/platform/NNN_*.sql بالترتيب مرّة واحدة لكلٍّ.

    يرجّع قائمة النسخ المطبَّقة حديثاً. جدول التتبّع `platform_migrations`
    يُنشئه الترحيل 001 نفسه (bootstrap-safe). Idempotent.
    """
    applied: list[str] = []
    files = sorted(glob.glob(os.path.join(_MIGRATIONS_DIR, "[0-9]*.sql")))
    import silk_sqlite
    conn = connect(path)
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS platform_migrations (
                           version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)""")
        conn.commit()
        for f in files:
            version = re.match(r"(\d+)", os.path.basename(f)).group(1)
            with open(f, encoding="utf-8") as fh:
                script = fh.read()
            # R5 (تدقيق 2026-09-01، DB-1/TEST-10): **ملفٌّ = معاملةٌ واحدة**.
            # `executescript` كان يلتزم ضمنياً قبل التنفيذ فيترك نصفَ الملفّ
            # ملتزَماً بلا صفّ نسخة عند العطب — وإعادةُ الإقلاع تنفجر بـ
            # «duplicate column» على كلّ طلب. الآن: `BEGIN IMMEDIATE` ← فحصُ
            # النسخة داخل المعاملة (عاملان يُقلعان معاً) ← الجملُ واحدةً واحدة
            # (عمودٌ موجود من ترحيلٍ نصفيّ قديم يُتخطّى) ← صفُّ النسخة ← التزام؛
            # أيُّ عطبٍ = تراجعٌ كامل والرفعُ كما هو.
            conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            try:
                if conn.execute("SELECT 1 FROM platform_migrations WHERE version = ?",
                                (version,)).fetchone():
                    conn.rollback()
                    continue
                for stmt in silk_sqlite.iter_statements(script):
                    if _already_applied_alter(conn, stmt):
                        continue
                    conn.execute(stmt)
                conn.execute("INSERT INTO platform_migrations (version, applied_at) "
                             "VALUES (?, ?)", (version, now_iso()))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            applied.append(version)
    finally:
        conn.close()
    return applied


_ALTER_ADD_COLUMN_RE = re.compile(
    r"^\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.IGNORECASE)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def _already_applied_alter(conn: sqlite3.Connection, stmt: str) -> bool:
    """`ALTER TABLE … ADD COLUMN` لعمودٍ قائم (تركةُ تطبيقٍ نصفيّ قديم) يُتخطّى —
    الترحيلاتُ إضافيّة، فوجودُ العمود يعني أنّ الجملة أدّت عملها."""
    # الجملةُ قد تبدأ بسطور تعليقٍ (`-- …`) ورثتها من الملفّ — تُقشَّر قبل المطابقة.
    body = "\n".join(ln for ln in stmt.splitlines()
                    if not ln.strip().startswith("--"))
    m = _ALTER_ADD_COLUMN_RE.match(body)
    return bool(m and _column_exists(conn, m.group(1), m.group(2)))


_initialized: set[str] = set()


def init_db(path: str | None = None, *, force: bool = False) -> None:
    """هيّئ قاعدة المنصّة — apply all migrations (safe to call repeatedly).

    تُخزَّن المسارات المهيّأة كي لا يُعاد فحص الترحيلات لكل طلب. `force=True`
    يتجاهل الذاكرة (للاختبارات التي تعيد إنشاء نفس المسار). Cached per path.
    """
    p = path or db_path()
    if not force and p in _initialized:
        return
    apply_migrations(p)
    _initialized.add(p)
