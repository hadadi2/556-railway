"""مُوصِّل SQLite واحد لكل مخازن المسار الرئيسي — one SQLite connector.

**لماذا وُجد هذا الملف (تدقيق 2026-08-27، البند ٢).** سباكة الاتصال كانت
مكرّرة خمس مرّات حرفياً (`silk_storage`/`silk_store`/`silk_usage`/
`silk_watchdog`/`silk_ops_log`): إنشاء المجلد الأب، ثم `sqlite3.connect`،
ثم `row_factory`. وحين عضّت حادثة «database is locked» المنصّةَ فعلاً، وصل
الإصلاح (`timeout` + `PRAGMA busy_timeout`) نسخةَ المنصّة **وحدها**
(`silk_platform/db.py:51`) وبقيت الخمسة على المهلة الافتراضية (٥ ثوانٍ) رغم
أن طوبولوجيا التزامن واحدة: خيوط التحديث الدوري والنسخ الاحتياطي وتشغيلات
`/research` الخلفية تكتب بينما طلبات HTTP تقرأ. نسخةٌ سادسة من الإصلاح كانت
ستُنسى كما نُسيت الخمس؛ فالموضع صار **واحداً**.

**ما يفعله `connect`:**

- `timeout=30` + `PRAGMA busy_timeout=30000` — الكاتب في SQLite وحيد، فبدل
  رمي «database is locked» فوراً تتسلسل المعاملات المتزامنة منتظرةً. الرقمان
  معاً مقصودان: `timeout` يحكم انتظار بايثون قبل رفع الاستثناء، و`busy_timeout`
  يحكم انتظار محرّك SQLite نفسه داخل المعاملة.
- `row_factory = sqlite3.Row` افتراضياً (الوصول بالاسم) — يُطفأ بـ
  `row_factory=False` لمخزنٍ يقرأ بالفهرس فقط.
- `PRAGMA foreign_keys = ON` عند `foreign_keys=True` فقط (SQLite يعطّلها
  افتراضياً؛ مخازن المسار الرئيسي بلا قيود FK).

stdlib فقط، بلا أي استيراد من هذا الريبو — فيبقى قابلاً للاستيراد من أي وحدة
بلا دورة استيراد.

One connector for every main-path store: creates the parent directory, opens
the connection with a 30-second lock wait (both the Python-level timeout and
SQLite's own busy_timeout), and sets `row_factory` — so the "database is
locked" fix lives in exactly one place instead of being re-applied per store.
"""
import logging
import os
import sqlite3

log = logging.getLogger(__name__)

# R5 (تدقيق 2026-09-01، DB-6/CONC-6): وضعُ دفتر اليومية. WAL افتراضاً — كاتبٌ
# طويل (حفظُ تشغيلةٍ مدفوعة، نسخٌ احتياطي) كان يحجب كلَّ قارئ HTTP حتى ٣٠
# ثانية في وضع DELETE. الرجوعُ بالبيئة `SILK_SQLITE_JOURNAL_MODE=delete`
# (يقلب الملفَّ الدائم نفسَه عند أوّل اتصال). قيمةٌ غير معروفة = `wal`.
_JOURNAL_MODES = frozenset({"wal", "delete", "truncate", "persist", "memory", "off"})
_journal_warned: set[str] = set()


def journal_mode() -> str:
    """الوضع المطلوب من البيئة — `wal` ما لم يُطلَب غيره صراحةً."""
    raw = os.environ.get("SILK_SQLITE_JOURNAL_MODE", "").strip().lower()
    return raw if raw in _JOURNAL_MODES else "wal"


def _apply_journal_mode(conn: sqlite3.Connection, path: str) -> None:
    """طبّق الوضع؛ تعذُّرُه (نظام ملفات للقراءة فقط/شبكي) تحذيرٌ واحد لا فشلُ اتصال."""
    mode = journal_mode()
    try:
        got = str(conn.execute(f"PRAGMA journal_mode={mode}").fetchone()[0]).lower()
        if got == "wal":
            # مع WAL يكفي NORMAL: الالتزامُ متينٌ عند نقطة التفتيش، والقراءةُ لا
            # تنتظر fsync كلَّ معاملة (خيارُ SQLite الموصى به لـWAL).
            conn.execute("PRAGMA synchronous=NORMAL")
        elif got != mode and got != "memory" and path not in _journal_warned:
            # SQLite يعيد الوضعَ الفعليّ لا المطلوب — رفضُه (ملفٌّ للقراءة فقط،
            # نظامُ ملفات شبكي) صمتٌ لا يجوز (مراجعة §58): تحذيرٌ واحد لكل مسار.
            _journal_warned.add(path)
            log.warning("journal_mode=%s requested but %s stays on %s", mode, path, got)
    except sqlite3.OperationalError as exc:
        if path not in _journal_warned:
            _journal_warned.add(path)
            log.warning("journal_mode=%s unavailable for %s (%s) — staying on "
                        "the default mode", mode, path, exc)


def iter_statements(script: str):
    """قسّم سكربت SQL إلى جملٍ كاملة — R5 (DB-1/TEST-10).

    `executescript` يلتزم ضمنياً قبل تنفيذه، فترحيلٌ من أربع جمل `ALTER` يعطب
    بين الثانية والرابعة كان يترك نصفَه ملتزَماً وصفَّ نسختِه غائباً — وإعادةُ
    التطبيق تنفجر بـ«duplicate column» فتُعطِّل كلَّ `/platform`. هنا تُنفَّذ الجملُ
    واحدةً واحدة داخل معاملةٍ صريحة. `sqlite3.complete_statement` يعرف الفواصل
    داخل النصوص والتعليقات وأجسام `CREATE TRIGGER … BEGIN … END`.
    """
    buf: list[str] = []
    for line in script.splitlines(keepends=True):
        buf.append(line)
        chunk = "".join(buf)
        if sqlite3.complete_statement(chunk):
            stmt = chunk.strip()
            buf = []
            if stmt:
                yield stmt
    rest = "".join(buf).strip()
    if rest and any(not ln.strip().startswith("--")
                    for ln in rest.splitlines() if ln.strip()):
        yield rest

# مهلة انتظار القفل بالثواني — نفس قيمة `silk_platform/db.py` التي أثبتتها
# حادثة القفل الحقيقية. Lock-wait seconds (matches the platform's proven value).
LOCK_TIMEOUT_S = 30


def connect(path: str, *, foreign_keys: bool = False,
            row_factory: bool = True) -> sqlite3.Connection:
    """افتح اتصالاً بمهلة قفلٍ صريحة — open a lock-tolerant connection."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=LOCK_TIMEOUT_S)
    if row_factory:
        conn.row_factory = sqlite3.Row
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {LOCK_TIMEOUT_S * 1000}")
    _apply_journal_mode(conn, path)
    return conn
