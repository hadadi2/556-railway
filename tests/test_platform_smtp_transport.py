"""الناقل التشغيلي الباقي — operator SMTP transport + password-reset email.

أُنقذت هذه الاختبارات من `test_platform_smtp_delivery.py` المحذوف مع التنقيب
(قرار مالك 2026-08-17): `smtp_transport.py` **باقٍ** لغرضين تشغيليين فقط —
بريد إعادة تعيين كلمة المرور وتنبيه الحارس الأحمر (`silk_watchdog`) — وهذه
عقوده: بناء رسالة UTF-8، رفض حقن الترويسات، الأخطاء تُنقّى ولا تُسقط الطلب.
"""
from email.header import decode_header

import pytest

from platform_helpers import client, seed
from silk_platform import api as api_mod
from silk_platform import db as pdb, smtp_transport


class _FakeSMTP:
    """ناقل SMTP مزيَّف — captures calls; never touches a real socket."""
    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=30.0):
        self.host, self.port, self.timeout = host, port, timeout
        self.ehlo_calls = 0
        self.starttls_called = False
        self.login_args = None
        self.sent = None
        self.quit_called = False
        _FakeSMTP.instances.append(self)

    def ehlo(self):
        self.ehlo_calls += 1

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        self.sent = msg

    def quit(self):
        self.quit_called = True


class _FailingSMTP(_FakeSMTP):
    def login(self, user, password):
        raise RuntimeError("auth failed: password=hunter2")


# ════════════════════════════ smtp_transport ═════════════════════════════════
def test_send_builds_utf8_message_uses_tls_and_login():
    _FakeSMTP.instances.clear()
    smtp_transport.send(host="smtp.example.com", port=587, use_tls=True,
                        username="user@example.com", password="secret",
                        from_email="from@example.com", from_name="سِلك",
                        to_email="to@example.com", subject="مرحباً Hello",
                        body="نص Body", msg_id="<abc@x>", smtp_cls=_FakeSMTP)
    inst = _FakeSMTP.instances[-1]
    assert inst.starttls_called
    assert inst.login_args == ("user@example.com", "secret")
    assert inst.quit_called
    msg = inst.sent
    assert msg["Message-ID"] == "<abc@x>"
    assert msg["To"] == "to@example.com"
    parts = decode_header(msg["Subject"])
    text = "".join(t.decode(enc or "utf-8") if isinstance(t, bytes) else t
                   for t, enc in parts)
    assert text == "مرحباً Hello"


def test_send_skips_tls_and_login_when_unset():
    _FakeSMTP.instances.clear()
    smtp_transport.send(host="h", port=25, use_tls=False, username="", password="",
                        from_email="f@x.com", from_name="F", to_email="t@x.com",
                        subject="S", body="B", msg_id="<x@y>", smtp_cls=_FakeSMTP)
    inst = _FakeSMTP.instances[-1]
    assert not inst.starttls_called
    assert inst.login_args is None
    assert inst.quit_called  # still closed even without auth


def test_send_propagates_transport_errors_and_still_closes():
    _FakeSMTP.instances.clear()
    with pytest.raises(RuntimeError):
        smtp_transport.send(host="h", port=25, use_tls=False, username="u",
                            password="p", from_email="f@x.com", from_name="F",
                            to_email="t@x.com", subject="S", body="B",
                            msg_id="<x@y>", smtp_cls=_FailingSMTP)
    assert _FakeSMTP.instances[-1].quit_called  # finally-block cleanup ran


def test_send_rejects_header_injection_in_recipient():
    """بريدٌ محفوظ بلا تحقّق شكل (`prospects.email` منذ PR-1) لا يُدرِج ترويسات.

    لا شيء أعلى هذا الملف يتحقّق من شكل البريد؛ هنا أوّل نقطة تلمس ترويسة
    SMTP حقيقية فهي نقطة الفرض الصحيحة — CRLF مُضمَّن يُرفَض بدل أن يُدرِج
    `Bcc:` أو مستلماً إضافياً عبر envelope المُشتقّ من الترويسات.
    """
    _FakeSMTP.instances.clear()
    with pytest.raises(ValueError):
        smtp_transport.send(host="h", port=25, use_tls=False, username="",
                            password="", from_email="f@x.com", from_name="F",
                            to_email="victim@x.com\r\nBcc: attacker@evil.com",
                            subject="S", body="B", msg_id="<x@y>", smtp_cls=_FakeSMTP)
    assert _FakeSMTP.instances == []  # rejected before any connection opened


def test_message_id_is_deterministic_per_row():
    """حتميّة المعرّف = مفتاح idempotency التسليم — same row ⇒ same Message-ID."""
    assert smtp_transport.message_id("email", 42) == smtp_transport.message_id("email", 42)
    assert smtp_transport.message_id("email", 42) != smtp_transport.message_id("email", 43)


def test_operator_config_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("SILK_PLATFORM_OPERATOR_SMTP_HOST", raising=False)
    monkeypatch.delenv("SILK_PLATFORM_OPERATOR_SMTP_FROM_EMAIL", raising=False)
    assert smtp_transport.operator_config_from_env() is None


def test_operator_config_present_when_configured(monkeypatch):
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_HOST", "smtp.op.local")
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_FROM_EMAIL", "noreply@silk.local")
    cfg = smtp_transport.operator_config_from_env()
    assert cfg["host"] == "smtp.op.local"
    assert cfg["port"] == 587 and cfg["use_tls"] is True
    assert cfg["from_email"] == "noreply@silk.local"



# ════════════════════════════ password-reset delivery ═════════════════════════
def test_password_reset_sends_email_when_operator_smtp_configured(monkeypatch):
    info = seed(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_HOST", "smtp.op.local")
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_FROM_EMAIL", "noreply@silk.local")
    captured = {}
    monkeypatch.setattr(api_mod.smtp_transport, "send", lambda **kw: captured.update(kw))
    cl = client()
    r = cl.post("/platform/auth/password-reset/request",
               json={"email": info["factory_a"]["email"]})
    assert r.status_code == 200 and r.json() == {"ok": True}
    api_mod.smtp_transport.wait_pending(5)   # R7 (AUTH-3): الإرسالُ خلفيّ
    assert captured["to_email"] == info["factory_a"]["email"]
    assert "reset-password?token=" in captured["body"]


def test_password_reset_no_crash_when_operator_smtp_unconfigured(monkeypatch):
    info = seed(monkeypatch)
    monkeypatch.delenv("SILK_PLATFORM_OPERATOR_SMTP_HOST", raising=False)
    cl = client()
    r = cl.post("/platform/auth/password-reset/request",
               json={"email": info["factory_a"]["email"]})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_password_reset_email_failure_is_audited_not_raised(monkeypatch):
    info = seed(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_HOST", "smtp.op.local")
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_FROM_EMAIL", "noreply@silk.local")

    def boom(**kw):
        raise RuntimeError("smtp down")
    monkeypatch.setattr(api_mod.smtp_transport, "send", boom)
    cl = client()
    r = cl.post("/platform/auth/password-reset/request",
               json={"email": info["factory_a"]["email"]})
    assert r.status_code == 200 and r.json() == {"ok": True}
    api_mod.smtp_transport.wait_pending(5)   # R7 (AUTH-3): الإرسالُ خلفيّ — انتظره
    conn = pdb.connect()
    row = conn.execute("SELECT 1 FROM audit_log WHERE "
                       "action = 'password_reset_email_failed'").fetchone()
    assert row is not None


def test_password_reset_unknown_email_never_attempts_send(monkeypatch):
    seed(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_HOST", "smtp.op.local")
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_FROM_EMAIL", "noreply@silk.local")
    called = []
    monkeypatch.setattr(api_mod.smtp_transport, "send", lambda **kw: called.append(1))
    cl = client()
    r = cl.post("/platform/auth/password-reset/request",
               json={"email": "nobody@nowhere.local"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert called == []
