"""ناقل SMTP التشغيلي — the operator SMTP transport (stdlib `smtplib` only).

بعد حذف التنقيب نهائياً (قرار مالك 2026-08-17) بقي هذا الملف **للتشغيلي
حصراً**: بريد إعادة تعيين كلمة المرور (`api._send_password_reset_email`)
وتنبيه الحارس الأحمر (`silk_watchdog._maybe_alert_red`) — لا حملات مستأجرين.

`send()` تأخذ بيانات اعتماد **نصّية صريحة** ومظروف رسالة، وتُرسِل. `smtp_cls`
مُدخَل حقناً — الإنتاج يمرّر `smtplib.SMTP` (الافتراضي)، والاختبارات الهرمتية
تمرّر بديلاً مزيَّفاً فلا تُفتَح أي مقبس شبكة حقيقي أثناء `pytest`.

Operator-only since the prospecting deletion: password-reset email + watchdog
RED alert. `smtp_cls` is injected; hermetic tests never open a socket.
"""
from __future__ import annotations

import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr


def base_url() -> str:
    """الأصل العام للمنصّة — public origin used to build absolute links.

    كانت في `unsubscribe.py` (المحذوف مع التنقيب — قرار مالك 2026-08-17)؛
    نُقلت لا أُعيدت كتابتها: رابط بريد إعادة التعيين هو المستهلك الباقي،
    والمصدر يبقى واحداً كي لا يختلف الافتراض بين مواضع.
    Relocated from the deleted unsubscribe.py — its surviving consumer is the
    password-reset email link; still the single resolver.
    """
    return os.environ.get("SILK_PLATFORM_BASE_URL", "http://localhost:8000").rstrip("/")


def safe_error(exc: Exception) -> str:
    """نصّ خطأ مُنقّى للتخزين — redact secrets before persisting SMTP errors.

    كانت `email_queue._safe_error` (المحذوف)؛ المستهلك الباقي تدقيقُ فشل بريد
    إعادة التعيين. تمرّ بمُنقّي المشروع القائم كي لا يتسرّب سرّ في حقل تشخيصي.
    Relocated from the deleted email_queue.py; reuses the repo's redactor.
    """
    text = str(exc)[:300]
    try:
        import silk_diagnostics
        return silk_diagnostics._redact(text)
    except Exception:  # noqa: BLE001 — المُنقّي أفضل جهد؛ لا يمنع تسجيل الخطأ
        return text


def operator_config_from_env() -> dict | None:
    """تهيئة SMTP التشغيلية من البيئة — env-configured transactional SMTP.

    منفصلة عمداً عن `smtp_configs` المستأجَرة المشفَّرة في القاعدة: بريد
    إعادة تعيين كلمة المرور يصدر **قبل** أي جلسة مُصادَقة، فلا تهيئة مستأجَر
    تصلح مصدراً له. `None` إن لم يُضبَط الحدّ الأدنى (مضيف + مرسل) — نصف
    تهيئة كان سيُرسِل بلا مضيف فيفشل بعطلٍ غامض بدل التصريح الواضح بالغياب.
    Deliberately separate from tenant-owned `smtp_configs`: a password-reset
    email fires before any authenticated session exists. `None` when the
    minimum (host + from-address) isn't set — declared absence, not a vague
    connection failure.
    """
    host = os.environ.get("SILK_PLATFORM_OPERATOR_SMTP_HOST", "").strip()
    from_email = os.environ.get("SILK_PLATFORM_OPERATOR_SMTP_FROM_EMAIL", "").strip()
    if not host or not from_email:
        return None
    try:
        port = int(os.environ.get("SILK_PLATFORM_OPERATOR_SMTP_PORT", "587") or 587)
    except ValueError:
        port = 587
    return {
        "host": host, "port": port,
        "use_tls": os.environ.get("SILK_PLATFORM_OPERATOR_SMTP_USE_TLS", "1") == "1",
        "username": os.environ.get("SILK_PLATFORM_OPERATOR_SMTP_USERNAME", ""),
        "password": os.environ.get("SILK_PLATFORM_OPERATOR_SMTP_PASSWORD", ""),
        "from_email": from_email,
        "from_name": os.environ.get("SILK_PLATFORM_OPERATOR_SMTP_FROM_NAME", "Silk"),
    }


def message_id(kind: str, row_id: int, domain: str = "silk-platform.local") -> str:
    """مُعرِّف رسالة حتمي — deterministic Message-ID, doubles as the resend key.

    مُشتقّ من (kind, row_id) لا عشوائي: إعادة معالجة نفس الصفّ (الحاصد بعد
    عطل) تنتج **نفس** المعرّف، فخوادم البريد التي تُميّز بـMessage-ID تعامل
    المحاولتين كرسالة واحدة بدل تكرارٍ فعلي — هذا هو مفتاح idempotency
    المطلوب؛ SMTP نفسه بلا آلية تسليم-مرّة-واحدة أصيلة.
    Deterministic, not random: a re-send of the same row (reaper after a
    crash) reproduces the identical Message-ID, so downstream MTAs that
    dedupe by it treat the retry as the same message — the idempotency key
    the roadmap calls for, since raw SMTP has no native exactly-once delivery.
    """
    return f"<platform-{kind}-{row_id}@{domain}>"


def _reject_header_injection(value: str, field: str) -> None:
    """ارفض حقن ترويسة — reject embedded CR/LF before it reaches a header.

    لا شيء في المنصّة يتحقّق من شكل بريد العميل (`prospects.email` يُقبَل كما
    هو منذ PR-1)؛ هذا الملف هو أوّل مكان يضع تلك القيمة في ترويسة SMTP حقيقية،
    فهو نقطة الفرض الصحيحة. بلا هذا، بريدٌ محفوظ كـ`"x@y.com\\r\\nBcc: z@evil"`
    يُدرِج مستلمين/ترويسات إضافية عبر `send_message`'s header-derived envelope.
    No layer above this ever validated email *shape*; this is the first place
    that value reaches a real SMTP header, so it's the correct enforcement
    point — otherwise a stored `"x@y.com\\r\\nBcc: z@evil"` injects extra
    recipients/headers via `send_message`'s header-derived envelope.
    """
    if "\r" in value or "\n" in value:
        raise ValueError(f"{field} contains illegal control characters")


def send(*, host: str, port: int, use_tls: bool, username: str, password: str,
         from_email: str, from_name: str, to_email: str, subject: str,
         body: str, msg_id: str, smtp_cls=None, timeout: float = 30.0) -> None:
    """أرسل رسالة نصّية واحدة — build a UTF-8 MIME message and send it.

    ترفع أي عطل نقل كما هو (لا تبتلعه) — `email_queue.process_queue` هو من
    يُسجِّل الفشل ويُعلمه؛ الابتلاع هنا كان سيُخفي عطلاً حقيقياً عن الطابور.
    Propagates transport failures — the caller (process_queue) is the single
    place that records/declares them; swallowing here would hide a real fault.
    """
    for value, field in ((to_email, "to_email"), (from_email, "from_email"),
                        (from_name or "", "from_name"), (subject or "", "subject")):
        _reject_header_injection(value, field)
    smtp_cls = smtp_cls or smtplib.SMTP
    msg = MIMEText(body or "", "plain", "utf-8")
    msg["Subject"] = str(Header(subject or "", "utf-8"))
    msg["From"] = formataddr((str(Header(from_name or "", "utf-8")), from_email))
    msg["To"] = to_email
    msg["Message-ID"] = msg_id

    client = smtp_cls(host, int(port), timeout=timeout)
    try:
        client.ehlo()
        if use_tls:
            client.starttls()
            client.ehlo()
        if username:
            client.login(username, password)
        client.send_message(msg)
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001 — فشل الإغلاق لا يُخفي فشل الإرسال
            pass


# ── R7 (AUTH-3): تسليمٌ خلفيّ · background delivery ──────────────────────────
# مجمّعٌ صغير (عاملان) لرسائل إعادة التعيين: الطلبُ يعود فوراً فلا يفضح زمنُه
# وجودَ البريد. `wait_pending` للاختبارات والإغلاق الرشيق.
import threading as _threading  # noqa: E402
from concurrent.futures import ThreadPoolExecutor as _TPE, wait as _cf_wait  # noqa: E402

_POOL: _TPE | None = None
_PENDING: set = set()
_PLOCK = _threading.Lock()


def _pool() -> _TPE:
    global _POOL
    with _PLOCK:
        if _POOL is None:
            _POOL = _TPE(max_workers=2, thread_name_prefix="silk-smtp")
        return _POOL


def send_async(work) -> None:
    """نفّذ `work()` في الخلفية — لا يرفع أبداً للمنادي."""
    fut = _pool().submit(work)
    with _PLOCK:
        _PENDING.add(fut)
    fut.add_done_callback(lambda f: _PENDING.discard(f))


def wait_pending(timeout: float = 10.0) -> None:
    """انتظر الرسائلَ المعلّقة — للاختبارات ولحدث الإغلاق."""
    with _PLOCK:
        pending = list(_PENDING)
    if pending:
        _cf_wait(pending, timeout=timeout)
