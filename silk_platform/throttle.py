"""خنق محاولات الدخول — cross-process login throttle (platform DB backed).

بلاغ المالك: حالةٌ على مستوى الوحدة (dict) تنفصل لكل worker process، فسقف «١٠
محاولات» يصير ١٠×عدد العمّال فعلياً، ويُصفَّر كلّياً عند كل إعادة نشر. النشر
الحالي عملية uvicorn واحدة (Dockerfile/railway.json بلا `--workers`)، لكن إضافة
عامل ثانٍ لاحقاً كانت ستُضعف الحماية **صامتةً**. الحالة هنا في قاعدة المنصّة:
مشتركة بين كل العمليات وتصمد لإعادة التشغيل، فلا يعتمد الأمان على طوبولوجيا النشر.

Shared, restart-durable throttle state. No Redis: the platform DB is already the
one shared store (stdlib-first, per the repo's settled decisions).
"""
from __future__ import annotations

import datetime
import os
import sqlite3

MAX_FAILURES = 10
WINDOW_S = 300

# نوافذ العدّادات المسمّاة الافتراضية (درس 187): نافذة العدّاد تحكم **كل**
# مسارات الكتابة والكنس لصفوفه لا القراءة وحدها — `prune` كان يكنس الكل على
# نافذة الدخول فيمحو صفوف PWRESET داخل ساعتها. المصدر الواحد لبادئات api.py
# (قفل: tests/test_s58_security_fixes.py يطابقها ضد مواضع `named_limits`).
NAMED_WINDOW_DEFAULTS = {"CHECKOUT": WINDOW_S, "PWRESET": 3600,
                         "PWRESETEMAIL": 3600, "PDF": WINDOW_S,
                         "DIAG": WINDOW_S, "VISION": WINDOW_S,
                         "LOGINIP": WINDOW_S, "UPLOAD": WINDOW_S,
                         # R7 (AUTH-1/AUTH-20): عدّادا بريدٍ — ١٥ دقيقة للدخول، ساعةٌ للشراء.
                         "LOGINEMAIL": 900, "CHECKOUTEMAIL": 3600,
                         "EPPREVIEW": 60, "EPFUNNEL": 3600}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return max(1, int(raw)) if raw else default
    except ValueError:
        return default


def _limits() -> tuple[int, int]:
    """السقف والنافذة (قابلان للضبط بالبيئة) — max failures and window seconds."""
    return (_env_int("SILK_PLATFORM_LOGIN_MAX_FAILURES", MAX_FAILURES),
            _env_int("SILK_PLATFORM_LOGIN_WINDOW_S", WINDOW_S))


def named_limits(prefix: str, default_max: int,
                 default_window_s: int = WINDOW_S) -> tuple[int, int]:
    """حدود مستقلة لعدّادٍ مسمّى — §58 H1/L4: كانت عدّادات checkout والتشخيص
    تستعير متغيّري **الدخول** فرفعُ تسامح الدخول يوسّع صامتاً ميزانياتٍ لا
    علاقة لها به (منها مسابير مدفوعة). كل عدّاد باسمه:
    `SILK_PLATFORM_{PREFIX}_MAX_REQUESTS` / `SILK_PLATFORM_{PREFIX}_WINDOW_S`.
    """
    return (_env_int(f"SILK_PLATFORM_{prefix}_MAX_REQUESTS", default_max),
            _env_int(f"SILK_PLATFORM_{prefix}_WINDOW_S", default_window_s))


def identity(email: str, ip: str | None) -> str:
    """هويّة الخنق — normalized (email|ip) key."""
    return f"{(email or '').strip().lower()}|{ip or '-'}"


# فضاءا أسماء محجوزان (درس 190، F1): الدخول كان يبني هويّته من بريدٍ خامٍ
# **يتحكّم به المهاجم** في نفس فضاء العدّادات المسمّاة، فبريدٌ = «pwreset»
# يُنتِج الهويّة `pwreset|<ip>` عينَها ويشذّبها بنافذة الدخول (300ث) بدل
# نافذة PWRESET (3600ث) — تجاوزٌ ~10×. البادئة المحجوزة تمنع التصادم بنيوياً
# (لا بريدَ يُنتِج `login|…` كبادئةِ عدّادٍ مسمّى).
def login_identity(email: str, ip: str | None) -> str:
    """هويّة عدّاد الدخول بحسب (البريد، IP) — فضاء أسماء محجوز غير قابل للتزوير."""
    return f"login|{(email or '').strip().lower()}|{ip or '-'}"


def login_ip_identity(ip: str | None) -> str:
    """هويّة عدّاد الدخول بحسب IP وحده (درس 190، F6): يحدّ رشَّ كلمات المرور
    عبر حساباتٍ كثيرة من مصدرٍ واحد — لا يوجد سقفٌ تجميعيّ لكل IP بدونه."""
    return f"login-ip|{ip or '-'}"


def login_email_identity(email: str) -> str:
    """هويّة عدّاد الدخول بحسب البريد وحده — R7 (تدقيق 2026-09-01، AUTH-1/API-7):
    عدّادُ (بريد، IP) يتصفّر بتدوير IP، وعدّادُ IP لا يجمع على بريدٍ واحد؛ حسابٌ
    مستهدَف من عناوين كثيرة كان بلا سقف. Per-email cap, IP-independent."""
    return f"login-email|{(email or '').strip().lower()}"


def _cutoff(window_s: int) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - datetime.timedelta(seconds=window_s)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def is_throttled(conn: sqlite3.Connection, ident: str,
                 limits: tuple[int, int] | None = None) -> bool:
    """هل بلغت الهويّة السقف في النافذة؟ — shared across every worker process.

    `limits` الاختياري = (سقف، نافذة) لعدّادٍ مسمّى (`named_limits`)؛ غيابه =
    حدود الدخول الافتراضية (توافقاً مع كل المواضع القائمة).
    """
    max_failures, window_s = limits or _limits()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM login_attempts WHERE identity = ? "
        "AND created_at >= ?", (ident, _cutoff(window_s))).fetchone()
    return int(row["c"] if hasattr(row, "keys") else row[0]) >= max_failures


def record_failure(conn: sqlite3.Connection, ident: str,
                   limits: tuple[int, int] | None = None) -> None:
    """سجّل محاولة فاشلة — durable, visible to all workers immediately."""
    _, window_s = limits or _limits()
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    conn.execute("INSERT INTO login_attempts (identity, created_at) VALUES (?,?)",
                 (ident, now))
    # طهّر ما خرج من النافذة لهذه الهويّة (الجدول لا ينمو بلا حدّ).
    conn.execute("DELETE FROM login_attempts WHERE identity = ? AND created_at < ?",
                 (ident, _cutoff(window_s)))
    conn.commit()


def clear(conn: sqlite3.Connection, ident: str) -> None:
    """امسح عدّاد هويّة بعد دخول ناجح — reset on success."""
    conn.execute("DELETE FROM login_attempts WHERE identity = ?", (ident,))
    conn.commit()


def _max_window_s() -> int:
    """أطول نافذة سارية عبر كل العدّادات (بعد تجاوزات البيئة) — سقف الكنس."""
    windows = [_limits()[1]]
    windows += [_env_int(f"SILK_PLATFORM_{p}_WINDOW_S", w)
                for p, w in NAMED_WINDOW_DEFAULTS.items()]
    return max(windows)


def prune(conn: sqlite3.Connection) -> int:
    """احذف ما خرج من **أطول** نافذة — housekeeping job; returns rows removed.

    الكنس على نافذة الدخول وحدها كان يمحو صفوف عدّاد أطول نافذةً (PWRESET
    ساعة) وهي ما تزال سارية. إبقاء صفّ دخولٍ حتى أطول نافذة لا يغيّر السلوك:
    `is_throttled` يرشّح بنافذة عدّاده عند القراءة.
    """
    cur = conn.execute("DELETE FROM login_attempts WHERE created_at < ?",
                       (_cutoff(_max_window_s()),))
    conn.commit()
    return cur.rowcount

