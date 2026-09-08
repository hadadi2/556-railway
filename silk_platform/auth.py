"""المصادقة والجلسات — login, sessions, password reset, role resolution.

- تسجيل الدخول: تحقّق ثابت الزمن (لا تعداد مستخدمين بالتوقيت) → جلسة برمز خام
  يُعرض مرّة واحدة، مُخزَّن مجزّأً.
- الجلسة: انتهاء بعدم النشاط 24 ساعة (نافذة منزلقة)؛ جلسات متزامنة مستقلّة.
- إعادة التعيين: رمز أحادي الاستخدام محدود الزمن.

Constant-time login (no user enumeration via timing); hashed session tokens;
sliding 24h inactivity expiry; single-use reset tokens.
"""
from __future__ import annotations

import os
import datetime
import sqlite3

from . import passwords, tokens
from .db import now_iso
from .models import AuthContext, Role

SESSION_TTL_HOURS = 24
# R7 (AUTH-11): عمرٌ مطلق للجلسة (٣٠ يوماً افتراضاً) — النافذةُ المنزلقة وحدها كانت
# تُبقي جلسةً مسروقة حيّةً إلى الأبد ما دامت تُستعمل.
SESSION_ABSOLUTE_HOURS = 720


def session_absolute_hours() -> int:
    raw = os.environ.get("SILK_PLATFORM_SESSION_ABSOLUTE_HOURS", "").strip()
    try:
        return max(1, int(raw)) if raw else SESSION_ABSOLUTE_HOURS
    except ValueError:
        return SESSION_ABSOLUTE_HOURS
RESET_TTL_MINUTES = 30
# لا تكتب نافذة النشاط لكل طلب — الكتابة fsync على كل GET تتنافس مع الكاتب
# الوحيد في SQLite. نُحدّثها فقط بعد مضيّ هذه المدّة، ودلالة الـ24 ساعة سليمة
# لأن أي طلب داخل النافذة يمدّها. Coarse sliding: same 24h semantics, far fewer writes.
ACTIVITY_WRITE_GRANULARITY_S = 300

# هاش وهمي صالح لتشغيل تحقّق حين لا يوجد مستخدم — يوحّد زمن الردّ فيمنع تعداد
# المستخدمين عبر التوقيت. يُحسَب كسولاً مرّة واحدة: حسابه وقت الاستيراد كان
# يدفع ثمن bcrypt عامل ١٢ (~٢٥٠ms) في كل إقلاع وكل جلسة اختبار بلا فائدة.
# A valid dummy hash burned when the user is absent — computed lazily once.
_DUMMY_HASH_CACHE: str | None = None


def _dummy_hash() -> str:
    """هاش وهمي مُذكَّر — memoized dummy hash (no bcrypt cost at import time)."""
    global _DUMMY_HASH_CACHE
    if _DUMMY_HASH_CACHE is None:
        _DUMMY_HASH_CACHE = passwords.hash_password("Dummy-Password-0",
                                                    enforce_policy=False)
    return _DUMMY_HASH_CACHE


def _parse(ts: str) -> datetime.datetime:
    """حوّل طابعاً زمنياً مخزّناً إلى datetime واعٍ بالمنطقة — parse a stored stamp."""
    raw = ts.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _may_act(row) -> bool:
    """**المُسنَد الواحد** لـ«هل لهذا المستخدم أن يتصرّف؟».

    ليس الاستعلامُ وحدَه هو المشترك بل الشرطُ نفسُه: شرطٌ مكتوبٌ ثلاثَ مرّات
    ثلاثةُ تعريفات تفترق عند أوّل حالةِ تعليقٍ جديدة (`locked_until`،
    `pending_deletion`…) تُضاف إلى واحدةٍ منها. The predicate itself is shared,
    not merely the SQL — otherwise "one definition" is a docstring, not a fact.
    """
    return bool(row) and bool(row["user_active"]) and bool(row["account_active"])

# ── تسجيل الدخول · login ─────────────────────────────────────────────────────
def authenticate(conn: sqlite3.Connection, email: str, password: str) -> dict | None:
    """تحقّق من بيانات الاعتماد بزمن ثابت — returns the user row or None.

    يُشغّل تحقّق تجزئة دائماً (حتى لو غاب المستخدم) فلا يتسرّب وجوده عبر التوقيت.
    Runs a hash verification unconditionally to equalize timing.
    """
    # حالةُ الحساب تُقرأ في **نفس** الاستعلام بنفس شكل `resolve_session` — تعريفٌ
    # واحد لـ«هل هذا الحساب حيّ؟» لا تعريفان يفترقان عند أوّل شرطٍ جديد.
    # One JOIN, one definition — the same shape resolve_session uses.
    row = conn.execute(
        "SELECT u.*, u.is_active AS user_active, "
        "a.is_active AS account_active FROM users u "
        "JOIN accounts a ON a.id = u.account_id WHERE u.email = ?",
        ((email or "").strip().lower(),)).fetchone()
    stored = row["password_hash"] if row else _dummy_hash()
    ok = passwords.verify_password(password or "", stored)
    if not row or not ok:
        return None
    # ارفض المستخدمَ المعطّل **والحسابَ** المعطّل — `resolve_session` يرفض كليهما
    # على كل طلب، فليتّسق تسجيلُ الدخول معه ولا يصدر رمزاً لحسابٍ موقوف. الفحصُ
    # بعد نجاح كلمة المرور فلا يتسرّب وجودُ المستخدم عبر التوقيت.
    # Reject a deactivated user OR account, matching resolve_session.
    if not _may_act(row):
        return None
    # الشكلُ المُعاد كما كان بالضبط — `account_active` عمودُ فحصٍ لا حقلُ مستخدم.
    data = dict(row)
    data.pop("user_active", None)      # أعمدةُ فحصٍ لا حقولُ مستخدم
    data.pop("account_active", None)
    return data


def create_session(conn: sqlite3.Connection, user_id: int, *,
                   ip_address: str | None = None,
                   user_agent: str | None = None) -> str:
    """أنشئ جلسة وأعِد الرمز الخام مرّة واحدة — create a session; return raw token.

    الخام يُعرض هنا فقط ولا يُخزَّن؛ القاعدة تحمل sha256 منه.
    """
    raw = tokens.new_token()
    now = _now()
    expires = now + datetime.timedelta(hours=SESSION_TTL_HOURS)
    conn.execute(
        "INSERT INTO sessions (user_id, token_hash, ip_address, user_agent, "
        "created_at, expires_at, last_activity_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, tokens.hash_token(raw), ip_address, user_agent,
         _fmt(now), _fmt(expires), _fmt(now)))
    conn.commit()
    return raw


def _fmt(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_session(conn: sqlite3.Connection, raw_token: str) -> AuthContext | None:
    """حُلّ الجلسة إلى سياق مصادقة — validate a raw token into an AuthContext.

    يرفض الرمز الغائب/المزوَّر/المنتهي (401 في النقطة النهائية)، ويُجدّد نافذة
    عدم النشاط (last_activity_at + expires_at) عند كل طلب صالح.
    Rejects missing/tampered/expired tokens; slides the inactivity window.
    """
    if not raw_token:
        return None
    row = conn.execute(
        "SELECT s.*, u.account_id AS account_id, u.role AS role, u.email AS email, "
        "u.language_preference AS lang, u.is_active AS user_active, "
        "a.is_active AS account_active "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "JOIN accounts a ON a.id = u.account_id WHERE s.token_hash = ?",
        (tokens.hash_token(raw_token),)).fetchone()
    # ارفض جلسة مستخدم أو **حساب** معطّل — reject deactivated user OR account.
    if not _may_act(row):
        return None
    now = _now()
    if _parse(row["expires_at"]) <= now:
        return None  # منتهية بعدم النشاط · expired
    try:
        if _parse(row["created_at"]) + datetime.timedelta(
                hours=session_absolute_hours()) <= now:
            return None  # R7 (AUTH-11): بلغت العمرَ المطلق · absolute lifetime hit
    except (TypeError, ValueError):
        return None  # طابعٌ تالف ⇒ لا نثق بالجلسة
    # نافذة منزلقة خشِنة: كل طلب صالح يُمدّد الانتهاء ٢٤ ساعة، لكن الكتابة تحدث
    # فقط بعد مضيّ ACTIVITY_WRITE_GRANULARITY_S على آخر تحديث — فلا معاملة كتابة
    # (fsync) على كل GET تتنافس مع كاتب SQLite الوحيد. الدلالة محفوظة: أي طلب
    # داخل النافذة يمدّها، والفارق الأقصى بين المخزَّن والفعلي هو هذه الحبيبية.
    try:
        elapsed = (now - _parse(row["last_activity_at"])).total_seconds()
    except (TypeError, ValueError):
        elapsed = ACTIVITY_WRITE_GRANULARITY_S + 1  # طابع تالف ⇒ حدّثه
    if elapsed >= ACTIVITY_WRITE_GRANULARITY_S:
        conn.execute(
            "UPDATE sessions SET last_activity_at = ?, expires_at = ? WHERE id = ?",
            (_fmt(now), _fmt(now + datetime.timedelta(hours=SESSION_TTL_HOURS)),
             row["id"]))
        conn.commit()
    return AuthContext(
        user_id=row["user_id"], account_id=row["account_id"],
        role=Role(row["role"]), email=row["email"],
        language_preference=row["lang"] or "en", session_id=row["id"])


def destroy_session(conn: sqlite3.Connection, session_id: int) -> None:
    """أنهِ جلسة واحدة — logout: delete this session only (others stay live)."""
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()


# ── إعادة تعيين كلمة المرور · password reset (single-use, time-limited) ───────
def _user_with_account(conn: sqlite3.Connection, user_id: int):
    """صفُّ المستخدم ومعه حالةُ حسابه — نفس شكل `resolve_session` (JOIN واحد).

    تعريفٌ **واحد** لـ«هل لهذا المستخدم أن يتصرّف؟» يقرأه كلُّ مسارٍ يصدر رمزاً
    أو يستهلكه، فلا يفترق سطحان عند أوّل شرطِ تعليقٍ جديد.
    One definition of "may this user act?", shared by every reset surface.
    """
    return conn.execute(
        "SELECT u.id AS id, u.is_active AS user_active, "
        "a.is_active AS account_active FROM users u "
        "JOIN accounts a ON a.id = u.account_id WHERE u.id = ?",
        (user_id,)).fetchone()


# حالاتُ الأهلية — ثوابتُ لا سلاسلُ حرفية عند المُنادي: خطأٌ مطبعيّ في مقارنةٍ
# حرفية يُطفئ فرعَ أمانٍ بصمت، أمّا الثابتُ فيرفع NameError.
RESET_MISSING = "missing"
RESET_INACTIVE = "inactive"
RESET_OK = "ok"



def user_reset_state(conn: sqlite3.Connection, user_id: int) -> str:
    """`"missing"` · `"inactive"` · `"ok"` — للمُنادي المُصادَق (مسار الأدمِن).

    الأدمِن مخوَّلٌ أصلاً، فإخفاءُ السبب عنه لا يحمي شيئاً ويجعل التشخيصَ عن بُعد
    مستحيلاً؛ أمّا المسارُ العامّ فيبقى صامتاً (٢٠٠ بلا رمز).
    """
    row = _user_with_account(conn, user_id)
    if not row:
        return RESET_MISSING
    return RESET_OK if _may_act(row) else RESET_INACTIVE


def issue_reset_token_for_user(conn: sqlite3.Connection, user_id: int) -> str | None:
    """أصدر رمز إعادة تعيين لمستخدم بمعرّفه — returns raw token, None if no user.

    يستعمله مسار الأدمِن المساعد (POST /admin/users/{id}/reset) قبل تجهيز
    توصيل البريد في PR-5. نفس دلالات الأحادية والزمن. Admin-assisted stopgap.
    """
    # لا رمزَ لمستخدمٍ معطّل ولا لحسابٍ معطّل — `resolve_session` يرفض كليهما،
    # فسطحُ إعادة التعيين لا يجوز أن يظلّ الاستثناء. No token for a suspended
    # user or account: the reset surface must not be the exception.
    row = _user_with_account(conn, user_id)
    if not _may_act(row):
        return None
    raw = tokens.new_token()
    now = _now()
    conn.execute(
        "INSERT INTO password_reset_tokens (user_id, token_hash, created_at, "
        "expires_at) VALUES (?,?,?,?)",
        (row["id"], tokens.hash_token(raw), _fmt(now),
         _fmt(now + datetime.timedelta(minutes=RESET_TTL_MINUTES))))
    conn.commit()
    return raw


def user_language_by_email(conn: sqlite3.Connection, email: str) -> str:
    """لغة المستخدم ببريده — resolves before any account context exists.

    نفس منطق `issue_reset_token`: البريد هويّة عالمية على مستوى المنصّة، فلا
    قيد حساب مُمكن هنا — الحساب نتيجةٌ لاحقة لا مدخلاً. `en` احتياطاً لبريدٍ
    غير موجود (المُنادي لا يستدعيها إلا بعد نجاح `issue_reset_token` أصلاً).
    """
    row = conn.execute("SELECT language_preference FROM users WHERE email = ?",
                       ((email or "").strip().lower(),)).fetchone()
    return row["language_preference"] if row else "en"


def issue_reset_token(conn: sqlite3.Connection, email: str) -> str | None:
    """أصدر رمز إعادة تعيين بالبريد — returns raw token, or None if no such user.

    النقطة النهائية لا تفصح عن وجود المستخدم؛ ترجع 200 دائماً بصرف النظر.
    """
    row = conn.execute("SELECT id FROM users WHERE email = ?",
                       ((email or "").strip().lower(),)).fetchone()
    if not row:
        return None
    return issue_reset_token_for_user(conn, int(row["id"]))


def consume_reset_token(conn: sqlite3.Connection, raw_token: str,
                        new_password: str) -> bool:
    """استهلك الرمز وعيّن كلمة مرور جديدة — single-use; returns success.

    يرفض الرمز المستعمَل أو المنتهي؛ يفرض سياسة كلمة المرور (يرفع
    PasswordError عند المخالفة)؛ يبطل كل جلسات المستخدم بعد التغيير.

    ويرفض أيضاً رمزَ مستخدمٍ (أو حسابٍ) عُطِّل بعد إصدارِه — والرفضُ **غيرُ
    هادم عمداً**: لا يُوسَم الرمزُ مستعمَلاً، فلو أُعيد تفعيلُ المستخدم داخل
    مهلة الرمز عاد صالحاً. البديلُ (وسمُه مستعمَلاً عند أوّل رفض) يجعل تعطيلاً
    عابراً يحرق رمزاً شرعياً بلا أثر. Refusal is deliberately non-destructive.
    """
    if not raw_token:
        return False
    token_hash = tokens.hash_token(raw_token)
    row = conn.execute(
        "SELECT * FROM password_reset_tokens WHERE token_hash = ?",
        (token_hash,)).fetchone()
    if not row or row["used_at"]:
        return False
    if _parse(row["expires_at"]) <= _now():
        return False
    # حراسةُ الإصدار وحدَها تترك نافذةَ TTL: رمزٌ صدر قبل التعطيل يظلّ صالحاً
    # بعده. تُفحَص الحالةُ **عند الاستهلاك** أيضاً بنفس التعريف الواحد.
    # Guarding issuance alone leaves the TTL window open — re-check on use.
    if not _may_act(_user_with_account(conn, int(row["user_id"]))):
        return False
    # السياسة والتجزئة **قبل** المطالبة بالرمز، كي لا تحرق كلمةٌ ضعيفة الرمز.
    passwords.validate_policy(new_password)  # raises PasswordError on violation
    new_hash = passwords.hash_password(new_password)
    # الأحادية تُفرَض ذرّياً في القاعدة لا بفحص بايثون: `AND used_at IS NULL`
    # + فحص rowcount داخل معاملة كتابة فورية، فتخسر المطالبة الثانية المتزامنة
    # ولا يُعاد استعمال رمز واحد مرّتين. Atomic single-use claim (guarded UPDATE).
    conn.commit()                      # اطوِ المعلّق قبل BEGIN الصريح
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "UPDATE password_reset_tokens SET used_at = ? "
            "WHERE id = ? AND used_at IS NULL", (now_iso(), row["id"]))
        if cur.rowcount == 0:
            conn.rollback()            # سبقنا غيرُنا · another confirm won the race
            return False
        # أعِد فحصَ الأهلية **داخل** المعاملة: الفحصُ قبل التجزئة يسبق كلمةَ
        # مرورٍ تُجزَّأ بعامل ١٢ (~٢٥٠ms)، وتعطيلٌ يُثبَّت في تلك النافذة كان
        # يمرّ فتُكتب كلمةُ مرورٍ جديدة لمستخدمٍ صار موقوفاً. Re-check inside the
        # immediate transaction — the pre-check is ~250ms of bcrypt stale.
        if not _may_act(_user_with_account(conn, int(row["user_id"]))):
            conn.rollback()
            return False
        conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                     (new_hash, now_iso(), row["user_id"]))
        # إبطال الجلسات القائمة بعد تغيير كلمة المرور · invalidate live sessions.
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["user_id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return True


def change_password(conn: sqlite3.Connection, user_id: int,
                    current_password: str, new_password: str,
                    keep_session_id: int | None = None) -> bool:
    """تغيير كلمة المرور ذاتياً — self-service (قرار المالك 2026-08-18: بروفايل).

    يتحقّق من الحالية أولاً (False عند الخطأ — النقطة تترجمها 403 بلا تسريب)،
    يفرض السياسة (`PasswordError` تصعد)، ثم يبدّل التجزئة ويُبطل **بقية**
    الجلسات مع إبقاء جلسة الطلب نفسها حيّة (خلافاً لمسار إعادة التعيين الذي
    يبطل الكل — هناك الرمز هو الهوية؛ هنا الجلسة الحالية أثبتت نفسها للتو).

    **لا يلتزم** (§58) — المُنادي يسجّل قيد التدقيق ثم يلتزم مرة واحدة، فيبقى
    التغيير الأمني وقيدُه ذرّيين (عقد `audit.record` نفسه).
    """
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?",
                       (user_id,)).fetchone()
    if not row or not passwords.verify_password(current_password or "",
                                                row["password_hash"]):
        return False
    # السياسة قبل أي كتابة — كلمة ضعيفة لا تغيّر شيئاً.
    passwords.validate_policy(new_password)
    new_hash = passwords.hash_password(new_password)
    conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                 (new_hash, now_iso(), user_id))
    if keep_session_id is not None:
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND id != ?",
                     (user_id, keep_session_id))
    else:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return True


def cleanup_expired_sessions(conn: sqlite3.Connection) -> int:
    """احذف الجلسات المنتهية — daily job; returns rows removed."""
    cur = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (_fmt(_now()),))
    conn.commit()
    return cur.rowcount


def cleanup_reset_tokens(conn: sqlite3.Connection) -> int:
    """احذف رموز إعادة التعيين المنتهية أو المستهلَكة — daily job (درس 190،
    F13): كان الجدول ينمو بلا حدّ (لا مهمة تنظيف). الصلاحية غير متأثرة —
    `consume_reset_token` يفحص `used_at`/`expires_at` — فهذا احتجازٌ فقط.
    يحذف المنتهي (`expires_at <= الآن`) أو المستهلَك (`used_at` مضبوط)."""
    cur = conn.execute(
        "DELETE FROM password_reset_tokens "
        "WHERE expires_at <= ? OR used_at IS NOT NULL", (_fmt(_now()),))
    conn.commit()
    return cur.rowcount
