"""عدّاد الاستهلاك المدفوع اليومي — daily paid-layer usage counter (stdlib SQLite).

سقف التكلفة (الموجة ٠): يَعُدّ تفعيلات الطبقات المدفوعة في اليوم ويرفض ما يتجاوز
السقف قبل تشغيل أي وكيل. The cap is enforced by api.py BEFORE any agent runs:
requests that would exceed it get HTTP 429, so a public deployment cannot be
drained of paid credits.

- الحد من متغير البيئة `SILK_PAID_DAILY_CAP` (عدد صحيح). غير مضبوط => لا سقف
  (وضع التطوير) — الإنتاج يضبطه دوماً. Unset => no cap (dev mode); production
  must set it.
- العدّاد في ملف SQLite مستقل (`data/usage.db` افتراضياً، أو `SILK_USAGE_DB`)
  حتى لا يلمس بيانات التحليلات في `data/silk.db` إطلاقاً.
- كل شيء stdlib، ولا نداء شبكة — نفس فلسفة `silk_storage.py`.
"""
from __future__ import annotations

import contextlib
import datetime
import logging
import os
import sqlite3

log = logging.getLogger(__name__)

_DEFAULT_PATH = os.path.join("data", "usage.db")


def _db_path() -> str:
    """مسار قاعدة العدّاد — usage DB path (env-overridable).

    `SILK_USAGE_DB` أولاً، ثم اشتقاق من `SILK_DATA_DIR` (القرص الدائم)،
    ثم الافتراضي المحلي. Explicit var wins; SILK_DATA_DIR derives; local default.
    """
    explicit = os.environ.get("SILK_USAGE_DB", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("SILK_DATA_DIR", "").strip()
    if base:
        return os.path.join(base, "usage.db")
    return _DEFAULT_PATH


def daily_cap() -> int | None:
    """السقف اليومي من البيئة — the daily paid-call cap, or None when unset.

    غير مضبوط/غير صالح => None (لا سقف — وضع التطوير). Production sets
    SILK_PAID_DAILY_CAP to a non-negative integer.
    """
    raw = os.environ.get("SILK_PAID_DAILY_CAP", "").strip()
    if not raw:
        return None
    try:
        cap = int(raw)
    except ValueError:
        log.warning("SILK_PAID_DAILY_CAP=%r is not an integer — cap ignored", raw)
        return None
    return cap if cap >= 0 else None


@contextlib.contextmanager
def _open(path: str):
    """اتصالٌ يُغلَق دائماً — نفسُ عيب `silk_ops_log` الذي أُصلِح معه.

    `sqlite3.Connection` كمدير سياق **يلتزم ولا يُغلق**؛ وعلى ويندوز يُبقي
    الاتصالُ المفتوح الملفَّ محجوزاً فينهار تنظيفُ `TemporaryDirectory`
    بـ`WinError 32` — فيفشل اختبارٌ يقيس شيئاً آخر تماماً، ويضيع مع كل
    تشغيلٍ وقتُ تشخيصٍ لعطلٍ لا علاقة له بما يُختبَر.
    """
    conn = _connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _connect(path: str) -> sqlite3.Connection:
    """افتح الاتصال وأنشئ الجدول — open connection, ensure table exists."""
    import silk_sqlite
    conn = silk_sqlite.connect(path, row_factory=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS paid_usage ("
        "day TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0)"
    )
    # H6 (تدقيق): دفتر إنفاق دولاري يومي — حدّ ميزانية خشِن مكمّل لعدّاد
    # التفعيلات. عدّاد التفعيلات يحدّ *عدد* العمليات؛ هذا يحدّ *الدولارات*
    # الفعلية المُقدَّرة (تشغيلة /research قد تكلّف ~$7 لكنها تفعيلة واحدة).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS paid_usd ("
        "day TEXT PRIMARY KEY, usd REAL NOT NULL DEFAULT 0)"
    )
    return conn


def _today() -> str:
    """يوم اليوم بـUTC — today's ISO date (the counter's bucket key).

    درس 188: كان `date.today()` بالتوقيت المحلي بينما بقيةُ المنصّة UTC
    (`silk_platform.db.now_iso`، `quota.current_period`) — ضبطُ TZ في النشر
    كان يزيح حدَّ يوم السقف المدفوع عن كل النوافذ الأخرى ويعطي يوماً بـ21
    ساعة وآخرَ بـ27 عند التبديل. موحَّدٌ على UTC كالجميع.
    """
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def expected_run_usd() -> float:
    """التقدير المحجوز لتشغيلة بحث — **المصدر الواحد** (درس 188، F9): كان
    يُقرأ في ثلاثة مواضع + نسخة رابعة في silk_storage، كلٌّ بحرفيّة 3.0 خاصّة،
    فقد تتباعد. قراءةٌ محروسة لا ترفع على قيمةٍ مشوّهة."""
    raw = os.environ.get("SILK_RESEARCH_EXPECTED_USD", "").strip()
    try:
        return float(raw) if raw else 3.0
    except ValueError:
        log.warning("SILK_RESEARCH_EXPECTED_USD=%r ignored (not a number)", raw)
        return 3.0


def paid_calls_today(path: str | None = None) -> int:
    """استهلاك اليوم — paid-layer activations recorded today (0 on any error)."""
    try:
        with _open(path or _db_path()) as conn:
            row = conn.execute(
                "SELECT calls FROM paid_usage WHERE day = ?", (_today(),)
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception as e:  # noqa: BLE001 — counter must never crash the API
        log.warning("usage counter read failed: %s", e)
        return 0


def record_paid_calls(n: int, path: str | None = None) -> None:
    """سجّل تفعيلات مدفوعة — add n paid-layer activations to today's bucket."""
    if n <= 0:
        return
    try:
        with _open(path or _db_path()) as conn:
            conn.execute(
                "INSERT INTO paid_usage (day, calls) VALUES (?, ?) "
                "ON CONFLICT(day) DO UPDATE SET calls = calls + excluded.calls",
                (_today(), n),
            )
    except Exception as e:  # noqa: BLE001 — counter must never crash the API
        log.warning("usage counter write failed: %s", e)


def release_paid_calls(n: int, path: str | None = None) -> None:
    """أرجِع n تفعيلاتٍ حُجزت ثم لم تُستعمَل — EXT-16: كان الحجزُ يبقى محسوباً حين يفشل
    الحجزُ الدولاريّ التالي له، فتُستهلَك الحصّةُ اليومية بلا نداءٍ فعليّ."""
    if n <= 0:
        return
    try:
        with _open(path or _db_path()) as conn:
            conn.execute(
                "UPDATE paid_usage SET calls = MAX(0, calls - ?) WHERE day = ?",
                (n, _today()))
    except Exception as e:  # noqa: BLE001 — counter must never crash the API
        log.warning("usage counter release failed: %s", e)


def vision_allowed(path: str | None = None) -> tuple[bool, str]:
    """هل يُسمح نداءُ رؤيةٍ واحد؟ — (allowed, reason). EXT-13: الحارسُ الواحد لسطحَي
    `/products/intake` والمنصّة (كانا نسختين): مفتاحُ كلود، حارسُ المفاتيح المدفوعة بلا
    مصادقة، ثم حجزُ تفعيلةٍ واحدة من السقف اليوميّ المشترك."""
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return False, ("طبقة الرؤية تتطلّب ANTHROPIC_API_KEY — "
                       "تعذّرت قراءة الصورة، اكتب الاسم يدوياً.")
    if unprotected_paid_keys():
        return False, ("ANTHROPIC_API_KEY مضبوط بلا SILK_API_KEY — "
                       "طبقة الرؤية محجوبة (حارس 503) حتى تُضبط المصادقة.")
    if not try_reserve_paid_calls(1, path):
        return False, ("سقف الاستهلاك اليومي (SILK_PAID_DAILY_CAP) "
                       "مستنفد — تعذّرت قراءة الصورة لهذا الطلب.")
    return True, ""


def would_exceed_cap(requested: int, path: str | None = None) -> bool:
    """هل يتجاوز الطلب السقف؟ — True when cap is set AND today+requested > cap.

    فحص إخباري فقط (قراءة بلا حجز) — للحجز الفعلي استعمل
    try_reserve_paid_calls الذرّية. Informational read only; the enforcing
    path must use the atomic try_reserve_paid_calls instead.
    """
    cap = daily_cap()
    if cap is None or requested <= 0:
        return False
    return paid_calls_today(path) + requested > cap


# ── دفتر الإنفاق الدولاري اليومي (H6) — حدّ ميزانية خشِن بالدولار ──────────

def daily_usd_cap() -> float | None:
    """سقف الإنفاق اليومي بالدولار من البيئة — `SILK_PAID_DAILY_USD_CAP`، أو
    None حين غير مضبوط (لا حدّ دولاري — الافتراضي، توافق خلفي كامل)."""
    raw = os.environ.get("SILK_PAID_DAILY_USD_CAP", "").strip()
    if not raw:
        return None
    try:
        cap = float(raw)
    except ValueError:
        log.warning("SILK_PAID_DAILY_USD_CAP=%r is not a number — cap ignored", raw)
        return None
    return cap if cap >= 0 else None


def usd_spent_on(day: str, path: str | None = None) -> float:
    """إنفاق يومٍ محدَّد بالدولار (0.0 عند أي خطأ) — درس 188 (F8): الحارس
    الأوسط يقيس على **يوم الحجز** لا على «اليوم» المتحرّك، فلا يُعطَّل عبر
    منتصف الليل حين يطرح حجزَ يومٍ سابق من دلو اليوم التالي."""
    try:
        with _open(path or _db_path()) as conn:
            row = conn.execute(
                "SELECT usd FROM paid_usd WHERE day = ?", (day,)).fetchone()
        return float(row[0]) if row else 0.0
    except Exception as e:  # noqa: BLE001 — الدفتر لا يُسقِط الـAPI أبداً
        log.warning("usd ledger read failed: %s", e)
        return 0.0


def usd_spent_today(path: str | None = None) -> float:
    """إنفاق اليوم المُقدَّر بالدولار (0.0 عند أي خطأ)."""
    return usd_spent_on(_today(), path)


def record_usd(amount: float, path: str | None = None) -> None:
    """سجّل مبلغاً مُقدَّراً بالدولار في دفتر اليوم — يُستدعى بعد كل تشغيلة
    بالتكلفة الفعلية المُقدَّرة (silk_pricing). صفر/سالب => لا شيء."""
    if amount is None or amount <= 0:
        return
    try:
        with _open(path or _db_path()) as conn:
            conn.execute(
                "INSERT INTO paid_usd (day, usd) VALUES (?, ?) "
                "ON CONFLICT(day) DO UPDATE SET usd = usd + excluded.usd",
                (_today(), float(amount)),
            )
    except Exception as e:  # noqa: BLE001
        log.warning("usd ledger write failed: %s", e)


def would_exceed_usd_cap(estimated: float, path: str | None = None) -> bool:
    """هل يتجاوز الإنفاقُ المتوقَّع السقفَ الدولاري؟ — True حين السقف مضبوط
    و(المُنفَق اليوم + المتوقَّع) > السقف. فحص إخباري فقط (قراءة بلا حجز)؛
    للبوابة الفعلية استعمل try_reserve_usd الذرّية (تمنع سباق تشغيلتين
    متزامنتين). Informational read only — the enforcing path uses the atomic
    try_reserve_usd."""
    cap = daily_usd_cap()
    if cap is None or estimated <= 0:
        return False
    return usd_spent_today(path) + estimated > cap


def try_reserve_usd(estimated: float, path: str | None = None) -> bool:
    """احجز مبلغاً مُقدَّراً ذرّياً قبل بدء تشغيلة مدفوعة — atomic check-and-
    reserve بالدولار (نظير try_reserve_paid_calls للعدّاد؛ يسدّ سباق TOCTOU).

    القراءة والتسجيل داخل معاملة واحدة (BEGIN IMMEDIATE تأخذ قفل الكتابة قبل
    القراءة)، فلا يمكن لتشغيلتَي /research متزامنتين قرب السقف أن تقرآ «تحت
    السقف» معًا ثم تسجّلا معًا وتتجاوزا الحدّ الدولاري. Two concurrent /research
    runs can no longer both pass the USD gate.

    - يعيد True والحجز (المبلغ المُقدَّر) مسجَّل، أو False (تجاوز السقف) وبلا
      أي تسجيل. Returns True with the estimate reserved, or False (nothing
      recorded) when it would breach the cap.
    - بلا سقف (SILK_PAID_DAILY_USD_CAP غير مضبوط) => يسجّل التقدير ويعيد True
      دائمًا (للرصد)، ولا يُحجب المسار الافتراضي أبدًا. No cap => record and
      always allow (observability), never blocks the default path.
    - عند فشل القاعدة: يُحجب فقط إن كان السقف مضبوطًا (fail-closed، نفس فلسفة
      try_reserve_paid_calls)؛ بلا سقف يُسمَح كي لا يُكسَر المسار الافتراضي على
      عطل دفتر. On DB failure: deny iff a cap is set, else allow.

    التكلفة الفعلية تُصالَح لاحقًا عبر reconcile_usd بعد اكتمال التشغيلة، فيحمل
    الدفتر المُنفَق الحقيقي لا التقدير. The actual cost is reconciled post-run.
    """
    cap = daily_usd_cap()
    est = float(estimated or 0.0)
    if est <= 0:
        return True
    try:
        with _open(path or _db_path()) as conn:
            conn.execute("BEGIN IMMEDIATE")  # قفل كتابة قبل القراءة
            row = conn.execute(
                "SELECT usd FROM paid_usd WHERE day = ?", (_today(),)).fetchone()
            current = float(row[0]) if row else 0.0
            if cap is not None and current + est > cap:
                conn.rollback()  # لا حجز عند الرفض
                return False
            conn.execute(
                "INSERT INTO paid_usd (day, usd) VALUES (?, ?) "
                "ON CONFLICT(day) DO UPDATE SET usd = usd + excluded.usd",
                (_today(), est))
        return True  # الخروج من with يلتزم
    except Exception as e:  # noqa: BLE001 — الدفتر لا يُسقِط الـAPI أبداً
        log.warning("usd ledger reserve failed: %s", e)
        return cap is None  # سقف مضبوط => امنع (fail-closed)؛ بلا سقف => اسمح


def reconcile_usd(reserved: float, actual: float, path: str | None = None,
                  day: str | None = None) -> None:
    """صالِح حجزًا مسبقًا بالتكلفة الفعلية — بعد اكتمال التشغيلة يُطبَّق الفرق
    (actual − reserved) ذرّيًا على دفتر اليوم، فيصير الدفتر يحمل المُنفَق
    الفعلي المُقدَّر (من الرموز) بدل التقدير المحجوز مسبقًا. Swaps the reserved
    estimate for the token-derived actual, atomically.

    - الفرق صفر => لا شيء. حجز بلا تسوية (تعطّل قبل الاكتمال) يُبقي التقدير
      محجوزًا — تحفّظ مقصود (fail-closed): لا نُنقِص محاسبةً لتشغيلة قد تكون
      استهلكت. A run that crashes before reconcile keeps its full reservation.
    - الدفتر لا ينزل تحت الصفر (حماية من فرق سالب كبير/تقريب). Floored at 0.
    """
    delta = float(actual or 0.0) - float(reserved or 0.0)
    if delta == 0:
        return
    # درس 188 (F7): الفرق يُطبَّق على **يوم الحجز** لا على «اليوم» المُعاد
    # قراءته عند التسوية — تشغيلةٌ تعبر منتصف الليل كانت تُصفّر دفتر الغد
    # وتمحو إنفاق تشغيلاتٍ متزامنة (تجاوزٌ فعليّ للسقف). المُنادي يمرّر يوم
    # الحجز (created_at للتشغيلة)؛ غيابه = اليوم (توافقاً مع القديم).
    bucket = day or _today()
    try:
        with _open(path or _db_path()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT usd FROM paid_usd WHERE day = ?", (bucket,)).fetchone()
            current = float(row[0]) if row else 0.0
            new = max(0.0, current + delta)
            conn.execute(
                "INSERT INTO paid_usd (day, usd) VALUES (?, ?) "
                "ON CONFLICT(day) DO UPDATE SET usd = excluded.usd",
                (bucket, new))
    except Exception as e:  # noqa: BLE001
        log.warning("usd ledger reconcile failed: %s", e)


def try_reserve_paid_calls(n: int, path: str | None = None) -> bool:
    """احجز n تفعيلات ذرّيًا — atomic check-and-reserve in ONE transaction.

    سدّ ثغرة السباق (TOCTOU): القراءة والتسجيل داخل معاملة واحدة
    (BEGIN IMMEDIATE تأخذ قفل الكتابة قبل القراءة)، فلا يمكن لطلبين
    متزامنين قرب حدّ السقف أن يقرآ "تحت السقف" معًا ثم يسجّلا معًا.
    Two concurrent /deepen requests can no longer both pass the cap check.

    - يعيد True والحجز مسجَّل، أو False (تجاوز السقف) وبلا أي تسجيل.
    - بلا سقف (SILK_PAID_DAILY_CAP غير مضبوط) => يسجّل ويعيد True دائمًا.
    - **عند فشل القاعدة يعيد False (fail-closed، M-2):** إن تعذّر التحقق من
      العدّاد (قفل/تلف/قرص) لا نسمح بصرف رصيد مدفوع بلا محاسبة — الرفض أأمن
      من التجاوز الصامت للسقف. (المسار المجاني لا يمرّ من هنا إطلاقاً، فلا
      يتأثر بهذا القرار.) On DB failure: log and **deny** the paid call.
    """
    if n <= 0:
        return True
    cap = daily_cap()
    try:
        with _open(path or _db_path()) as conn:
            # قفل كتابة فوري قبل القراءة — write lock BEFORE the read.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT calls FROM paid_usage WHERE day = ?", (_today(),)
            ).fetchone()
            current = int(row[0]) if row else 0
            if cap is not None and current + n > cap:
                conn.rollback()  # لا حجز عند الرفض — nothing recorded on refusal
                return False
            conn.execute(
                "INSERT INTO paid_usage (day, calls) VALUES (?, ?) "
                "ON CONFLICT(day) DO UPDATE SET calls = calls + excluded.calls",
                (_today(), n),
            )
        return True  # الخروج من with يُنهي المعاملة بالالتزام — commits on exit
    except Exception as e:  # noqa: BLE001 — counter must never crash the API
        log.warning("usage counter reserve failed (failing closed): %s", e)
        return False  # M-2: deny the paid call when accounting is unavailable


# ── بوّابةُ إضافات كلود على المسار المجاني — مصدرٌ واحد لسطحين ────────────
#
# **الموجة B (البند G-05).** كانت هذه السياسةُ مغلقةً داخل `api.create_app`
# (`_free_ai_extras_allowed`)، فنسخها `silk_platform/engine_bridge` نسخةً
# ثانيةً بيدها موثِّقاً السبب حرفياً: «closure لا يُستورد». نسختان لسياسةِ
# إنفاقٍ واحدة تتباعدان عند أوّل تعديل. الآن السياسةُ هنا — في الوحدة التي
# تملك السقفَ اليوميّ والحجزَ أصلاً — ويستهلكها كلُّ سطح.
#
# One spending policy, one home: the module that already owns the cap.

_PAID_KEY_ENVS = ("LOCALPRICE_API_KEY", "VOLZA_API_KEY",
                  "EXPLEE_API_KEY", "ANTHROPIC_API_KEY")


def unprotected_paid_keys() -> list[str]:
    """مفاتيحُ مدفوعةٌ حاضرةٌ بينما `SILK_API_KEY` غيرُ مضبوط.

    وضعُ التطوير المفتوح مشروعٌ **فقط** حين تغيب المفاتيح المدفوعة كلُّها؛
    وجودُ أيٍّ منها بلا مصادقة = خدمةٌ عامّة تصرف رصيداً مدفوعاً لمجهول.
    """
    if os.environ.get("SILK_API_KEY", "").strip():
        return []
    return [k for k in _PAID_KEY_ENVS if os.environ.get(k, "").strip()]


def free_ai_extras_allowed() -> tuple[bool, str]:
    """هل تُسمَح إضافةُ كلود على المسار المجاني الآن؟ — `(allowed, reason)`.

    ثلاثُ بوّاباتٍ بالترتيب: لا مفتاحَ كلود ⇒ لا إنفاقَ ممكنٌ أصلاً (يُسمَح،
    والطبقةُ نفسُها ستتدهور بصدق)؛ نشرٌ غيرُ محميّ ⇒ حجب؛ ثمّ **حجزٌ ذرّيّ
    واحد** من السقف اليوميّ. الرفضُ يتدهور بملاحظةٍ معلنة — لا 429 على مسارٍ
    مجانيٍّ في أصله، ولا إنفاقَ خارج المحاسبة.
    """
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return True, ""            # لا مفتاح => لا إنفاق ممكن أصلاً
    if unprotected_paid_keys():
        return False, ("ANTHROPIC_API_KEY مضبوط بلا SILK_API_KEY — "
                       "إضافات كلود (ثقافة المستهلك، فلترة الكيانات) "
                       "حُجبت على المسار المجاني حتى تُضبط المصادقة.")
    if not try_reserve_paid_calls(1):
        return False, ("سقف الاستهلاك اليومي (SILK_PAID_DAILY_CAP) "
                       "مستنفد — إضافات كلود حُجبت لهذا الطلب؛ "
                       "التحليل المجاني اكتمل بدونها.")
    return True, ""
