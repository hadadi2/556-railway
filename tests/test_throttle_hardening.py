"""تقوية خنق المنصّة (find all gaps مجموعة 4 — درس 190، قرار مالك 2026-08-27).

F1 (أخطرها، أولاً بأمر المالك): هويّة الدخول محجوزة الفضاء فلا يزوّرها بريدٌ =
اسمُ عدّادٍ مسمّى. F3: ذرّية قيد تدقيق تغيير كلمة المرور. F6: عدّاد دخول بحسب
IP يحدّ الرشّ. F2: عتبة بريد إعادة التعيين أعلى تحدّ قفل الضحية. F16: مسح عدّاد
التأكيد عند النجاح. F11: قفل 187 يطابق النافذة لا التسجيل. F13: تنظيف رموز
إعادة التعيين.

Hermetic؛ منصّة معزولة (conftest).
"""
from __future__ import annotations

import datetime
import pathlib

from tests.platform_helpers import client, seed

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _rows(ident: str, n: int) -> None:
    from silk_platform import db as pdb
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    conn = pdb.connect()
    try:
        for _ in range(n):
            conn.execute(
                "INSERT INTO login_attempts (identity, created_at) VALUES (?,?)",
                (ident, now))
        conn.commit()
    finally:
        conn.close()


# ── F1: هويّة الدخول لا تصطدم بعدّادٍ مسمّى ────────────────────────────────

def test_login_identity_cannot_collide_with_a_named_counter():
    from silk_platform import throttle
    # بريدٌ = «pwreset» لا يُنتِج هويّة عدّاد PWRESET.
    assert throttle.login_identity("pwreset", "1.2.3.4") \
        != throttle.identity("pwreset", "1.2.3.4")
    assert throttle.login_identity("pwreset", "1.2.3.4").startswith("login|")


def test_login_failure_does_not_prune_a_colliding_pwreset_counter(monkeypatch):
    """الحادثة: بريدُ دخولٍ = «pwreset» كان يشذّب عدّاد PWRESET بنافذة الدخول.
    الآن الفضاء المحجوز يفصلهما — عدّاد pwreset يبقى ممتلئاً."""
    seed(monkeypatch)
    from silk_platform import db as pdb, throttle
    pwreset_ident = throttle.identity("pwreset", "testclient")
    _rows(pwreset_ident, 5)   # عدّاد PWRESET ممتلئ
    with client() as cl:
        cl.post("/platform/auth/login",
                json={"email": "pwreset", "password": "x"})   # فشل دخول
    conn = pdb.connect()
    try:
        c = conn.execute(
            "SELECT COUNT(*) FROM login_attempts WHERE identity = ?",
            (pwreset_ident,)).fetchone()[0]
    finally:
        conn.close()
    assert c == 5, "دخولٌ بهويّةٍ متصادمة شذّب عدّاد PWRESET"


# ── F6: عدّاد الدخول بحسب IP ──────────────────────────────────────────────

def test_login_ip_counter_bounds_password_spraying(monkeypatch):
    """50 فشلاً من IP واحد عبر حساباتٍ كثيرة ⇒ الدخول التالي (أيُّ بريد) 429."""
    seed(monkeypatch)
    from silk_platform import throttle
    _rows(throttle.login_ip_identity("testclient"), 50)
    with client() as cl:
        r = cl.post("/platform/auth/login",
                    json={"email": "brand-new@x.example", "password": "x"})
        assert r.status_code == 429, r.text


# ── F2: عتبة بريد إعادة التعيين مستقلّة أعلى ───────────────────────────────

def test_pwreset_email_counter_uses_a_higher_independent_window():
    from silk_platform import throttle
    assert throttle.named_limits("PWRESETEMAIL", 15, 3600) == (15, 3600)
    src = (_ROOT / "silk_platform" / "api.py").read_text(encoding="utf-8")
    assert 'named_limits("PWRESETEMAIL", 15, 3600)' in src
    # عدّاد البريد يُفحَص ويُدرَج بحدوده المستقلّة لا بحدود IP.
    assert "throttle.record_failure(conn, ident_email, email_limits)" in src


# ── F3: ذرّية قيد التدقيق ─────────────────────────────────────────────────

def test_password_change_records_audit_before_clear_commits():
    """قيد التدقيق يُسجَّل قبل `throttle.clear` (الالتزام الوحيد) — فلا كلمةَ
    مبدَّلةً بلا أثر عند تعطّلٍ بينهما."""
    src = (_ROOT / "silk_platform" / "api.py").read_text(encoding="utf-8")
    changed = src.index('action="password_changed"')
    clear = src.index("throttle.clear(conn, ident)   # DELETE + commit ذرّي للكلّ")
    assert changed < clear, "clear يلتزم قبل قيد التدقيق (ذرّية مكسورة)"


# ── F16: مسح عدّاد التأكيد عند النجاح ──────────────────────────────────────

def test_reset_confirm_clears_counter_on_success(monkeypatch):
    info = seed(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_EXPOSE_RESET_TOKEN", "1")
    from silk_platform import db as pdb, throttle
    with client() as cl:
        raw = cl.post("/platform/auth/password-reset/request",
                      json={"email": info["admin"]["email"]}).json()["reset_token"]
        # قبل التأكيد: عدّاد التأكيد لهذا الـIP فيه صفوف (الطلب لا يمسّه؛
        # نبذر بعضاً لنثبت المسح).
        _rows(throttle.identity("pwreset-confirm", "testclient"), 2)
        ok = cl.post("/platform/auth/password-reset/confirm",
                     json={"token": raw, "new_password": "NewPass123"})
        assert ok.status_code == 200, ok.text
    conn = pdb.connect()
    try:
        c = conn.execute(
            "SELECT COUNT(*) FROM login_attempts WHERE identity = ?",
            (throttle.identity("pwreset-confirm", "testclient"),)).fetchone()[0]
    finally:
        conn.close()
    assert c == 0, "التأكيد الناجح لم يمسح عدّاد التأكيد"


# ── F13: تنظيف رموز إعادة التعيين ─────────────────────────────────────────

def test_cleanup_reset_tokens_removes_expired_and_used(monkeypatch):
    seed(monkeypatch)
    from silk_platform import auth, db as pdb
    conn = pdb.connect()
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        past = (now - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        future = (now + datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        nows = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute("INSERT INTO password_reset_tokens (user_id, token_hash, "
                     "created_at, expires_at) VALUES (1,'h_expired',?,?)",
                     (past, past))
        conn.execute("INSERT INTO password_reset_tokens (user_id, token_hash, "
                     "created_at, expires_at, used_at) VALUES (1,'h_used',?,?,?)",
                     (past, future, nows))
        conn.execute("INSERT INTO password_reset_tokens (user_id, token_hash, "
                     "created_at, expires_at) VALUES (1,'h_valid',?,?)",
                     (nows, future))
        conn.commit()
        removed = auth.cleanup_reset_tokens(conn)
        assert removed == 2
        left = {r[0] for r in conn.execute(
            "SELECT token_hash FROM password_reset_tokens").fetchall()}
        assert left == {"h_valid"}
    finally:
        conn.close()
