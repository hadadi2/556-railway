"""أقفال صفحة الدفع والمحوّل العام — «لا دفع وهمي أبداً» (2026-08-17).

قرارا المالك: «صفحة دفع عشان اربطها مع شركة دفع» + «لم أقرر — جهّزها عامة».
العائلات المقفلة: الطلب يُسجَّل قيدَ تدقيقٍ بسعرٍ خادمي (سعر العميل لا
يُقرأ)، لا قيد دفتر ولا Operation جديد (ترحيل SUBSCRIPTION مؤجَّل عمداً)،
كل مزوّد يرفع ProviderNotConfigured حتى بمفتاحٍ مضبوط وتحت حجب الشبكة
(يثبت ألا نداء يُحاول)، والصفحة لا تحمل شاشة نجاح دفعٍ لم يقع.
"""
from __future__ import annotations

import ast
import pathlib
from unittest import mock

from conftest import block_network as _block_network
from tests.platform_helpers import client, seed

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PAGE = (_ROOT / "web" / "checkout.html").read_text(encoding="utf-8")

_BODY = {"plan": "gold", "billing_cycle": "monthly", "name": "أحمد",
         "factory": "مصنع التمور", "email": "owner@dates.example",
         "phone": "+9665555"}


def _audit_rows(action: str):
    from silk_platform.db import connect
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM audit_log WHERE action = ?", (action,)).fetchall()]
    finally:
        conn.close()


def _ledger_count() -> int:
    from silk_platform.db import connect
    conn = connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM ledger_entries").fetchone()[0]
    finally:
        conn.close()


# ── ١) الطلب يُسجَّل بسعر خادمي — ولا يمسّ الدفتر ───────────────────────────
def test_checkout_records_audited_interest_with_server_price(monkeypatch):
    monkeypatch.delenv("SILK_PAY_PROVIDER", raising=False)
    seed(monkeypatch)
    with client() as cl:
        before = _ledger_count()
        r = cl.post("/platform/billing/checkout",
                    json=dict(_BODY, price=1))     # سعر عميل مزوّر — يُتجاهل
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["configured"] is False and body["recorded"] is True
        assert body["error"] == "payment_not_configured"
        assert "لم يُفعَّل" in body["message_ar"]
        assert body["message_en"]

        rows = _audit_rows("checkout_requested")
        assert len(rows) == 1
        import json
        changes = json.loads(rows[0]["changes"])
        assert changes["plan"] == "gold"
        assert changes["price_sar"] == 1799        # من pricing.yaml لا العميل
        assert changes["contact"]["email"] == "owner@dates.example"
        # لا قيد دفتر ولا توسيع Operation — الدفع لم يقع.
        assert _ledger_count() == before


def test_checkout_validation_422s(monkeypatch):
    seed(monkeypatch)
    with client() as cl:
        r = cl.post("/platform/billing/checkout",
                    json=dict(_BODY, plan="diamond"))
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "unknown_plan"
        r = cl.post("/platform/billing/checkout",
                    json=dict(_BODY, billing_cycle="yearly"))
        assert r.status_code == 422        # «yearly» ليست قيمة — annual فقط
        r = cl.post("/platform/billing/checkout",
                    json=dict(_BODY, email="بلا-بريد"))
        assert r.status_code == 422
        assert _audit_rows("checkout_requested") == []


def test_checkout_accepts_annual_cycle_with_server_annual_price(monkeypatch):
    """قرار 2026-08-18: الدورة السنوية مقبولة، وسعرها خادمي من
    `*_price_annual` في pricing.yaml (10 أشهر — شهران مجاناً)."""
    monkeypatch.delenv("SILK_PAY_PROVIDER", raising=False)
    seed(monkeypatch)
    with client() as cl:
        r = cl.post("/platform/billing/checkout",
                    json=dict(_BODY, billing_cycle="annual", price=1))
        assert r.status_code == 200, r.text
        assert r.json()["recorded"] is True
        import json
        rows = _audit_rows("checkout_requested")
        assert len(rows) == 1
        changes = json.loads(rows[0]["changes"])
        assert changes["cycle"] == "annual"
        assert changes["price_sar"] == 17990       # ذهبية سنوياً — خادمي حصراً


def test_checkout_rejects_annual_when_plan_has_no_annual_price(monkeypatch):
    """اتساق العرض: باقة مدفوعة شهرياً بسعر سنوي 0 في الملف = السنوي غير
    معروض — يُرفض 422 بدل تسجيل «اهتمام سنوي بصفر ريال» لم يُعرَض أصلاً."""
    seed(monkeypatch)
    import silk_platform.pricing as pricing_mod
    base = pricing_mod.load_pricing()
    fake = dict(base, gold_price_annual=0)
    monkeypatch.setattr(pricing_mod, "load_pricing",
                        lambda path=None: dict(fake))
    with client() as cl:
        r = cl.post("/platform/billing/checkout",
                    json=dict(_BODY, billing_cycle="annual"))
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "annual_not_available"
        assert _audit_rows("checkout_requested") == []


def test_checkout_throttle_uses_its_own_named_limits(monkeypatch):
    """§58 H1: حدود checkout مستقلة عن عدّاد الدخول — متغيّراها الخاصان
    يعملان، ورفع تسامح الدخول لا يوسّعها.

    (حدّ ما يثبته TestClient معلَن: العميل دائماً بهوية واحدة، فسلوك
    «لكل IP» الحقيقي يقوم على `--proxy-headers` المضبوط في
    Dockerfile/railway.json — مقفول نصياً في اختبار النشر أدناه.)"""
    monkeypatch.setenv("SILK_PLATFORM_CHECKOUT_MAX_REQUESTS", "3")
    monkeypatch.setenv("SILK_PLATFORM_LOGIN_MAX_FAILURES", "99")  # لا أثر له هنا
    seed(monkeypatch)
    with client() as cl:
        # P3/BIZ-7: كلُّ طلبٍ ببريدٍ مختلف — الخنقُ يعدّ **بالـIP** (`checkout|{ip}`)
        # فيبقى موضوعُ الاختبار كما هو، بينما كشفُ التكرار (بريد+باقة+دورة) لا
        # يبتلع القيود فيصير العدد ٣ لسببٍ آخر. مسارُ التكرار مقفولٌ على حدة في
        # `tests/test_audit_2026_09_01_p3.py::test_a_duplicate_checkout_is_recorded_once`.
        codes = [cl.post("/platform/billing/checkout",
                         json=dict(_BODY, email=f"t{i}@dates.example")).status_code
                 for i in range(4)]
        assert codes[:3] == [200] * 3
        assert codes[3] == 429
        assert len(_audit_rows("checkout_requested")) == 3   # المخنوق لا يُسجَّل


def test_deployment_trusts_proxy_forwarding_headers():
    """§58 H1: بلا `--proxy-headers` يكون `request.client.host` عنوانَ بروكسي
    Railway الواحد لكل الزوّار — فينقفل دلو checkout عالمياً بعشرة طلبات من
    أي شخص. أمرا التشغيل في النشر يجب أن يحملا العلم.

    R0 (تدقيق 2026-09-01، CI-2): `railway.json` **يبقى** يحمل الأمر — مطابقاً
    لـ`CMD` الصورة بايتاً ببايت (قفل `tests/test_audit_2026_09_01_r0.py`) — لأن
    حقل «Custom Start Command» في لوحة Railway ما زال يحمل أمراً أضعف بلا هذه
    الأعلام (قُرئ 2026-09-02)؛ حذفُه من `railway.json` قبل تفريغ اللوحة كان
    سيُسقط `--proxy-headers` حيّاً."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    docker = (root / "Dockerfile").read_text(encoding="utf-8")
    railway = (root / "railway.json").read_text(encoding="utf-8")
    assert "--proxy-headers" in docker and "--forwarded-allow-ips" in docker
    assert "--proxy-headers" in railway and "--forwarded-allow-ips" in railway


def test_named_limits_are_independent_env_knobs(monkeypatch):
    from silk_platform import throttle
    monkeypatch.delenv("SILK_PLATFORM_CHECKOUT_MAX_REQUESTS", raising=False)
    assert throttle.named_limits("CHECKOUT", 30) == (30, throttle.WINDOW_S)
    monkeypatch.setenv("SILK_PLATFORM_CHECKOUT_MAX_REQUESTS", "5")
    monkeypatch.setenv("SILK_PLATFORM_CHECKOUT_WINDOW_S", "60")
    assert throttle.named_limits("CHECKOUT", 30) == (5, 60)
    # مستقلة عن عدّاد الدخول — لا استعارة صامتة (§58 L4).
    monkeypatch.setenv("SILK_PLATFORM_LOGIN_MAX_FAILURES", "77")
    assert throttle.named_limits("DIAG", 10)[0] == 10


# ── ٢) المزوّدات: لا نداء يُحاول حتى بمفتاح مضبوط ───────────────────────────
def test_every_provider_raises_not_configured_even_with_keys(monkeypatch):
    import pytest
    from silk_platform import payments
    keys = {"moyasar": "MOYASAR_SECRET_KEY", "tap": "TAP_SECRET_KEY",
            "stripe": "STRIPE_SECRET_KEY"}
    with _block_network():        # أي محاولة نداء فعلي = انفجار فوري
        for name, cls in payments.PROVIDERS.items():
            monkeypatch.setenv(keys[name], "sk_test_fake")
            with pytest.raises(payments.ProviderNotConfigured):
                cls().create_checkout("gold", "monthly", {"email": "a@b.c"})


def test_provider_from_env_resolution(monkeypatch):
    from silk_platform import payments
    monkeypatch.delenv("SILK_PAY_PROVIDER", raising=False)
    assert payments.provider_from_env() is None
    monkeypatch.setenv("SILK_PAY_PROVIDER", "paypal")     # مجهول = None معلَنة
    assert payments.provider_from_env() is None
    monkeypatch.setenv("SILK_PAY_PROVIDER", "moyasar")
    assert payments.provider_from_env().NAME == "moyasar"


def test_configured_provider_still_degrades_declared_through_the_endpoint(
        monkeypatch):
    """مزوّد مختار + مفتاح مضبوط ≠ تكامل مبني: النقطة تعيد الإعلان الصادق
    نفسه (لا تحويل وهمي) — والطلب مسجَّل."""
    monkeypatch.setenv("SILK_PAY_PROVIDER", "stripe")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    seed(monkeypatch)
    # **تعليقٌ تشخيصيّ (تدقيق 2026-08-30).** كان هنا `_block_network()` —
    # وهو يُرقِّع `socket.socket` عالمياً. حول `TestClient` تحديداً هذا هو الفخّ
    # الموثَّق في CLAUDE.md حرفياً («blocking sockets globally breaks the
    # TestClient transport»): بوّابةُ anyio تحتاج مقبساً حقيقياً للإيقاظ بين
    # خيط الاختبار وخيط الحلقة، فإن مُنِعت عَلِق `Future.result()` **بلا مهلة**.
    # على ويندوز (ProactorEventLoop) يتجمّد الاختبار إلى الأبد؛ فحصٌ بـ
    # faulthandler أظهر المكدّس داخل `starlette/testclient.py:345` بصفر إطارات
    # من شيفرة سِلك. الحجبُ يبقى قائماً — لكن على طبقة `requests` كما تنصّ
    # القاعدة، وهي الطبقةُ الوحيدة التي قد يخرج منها نداءٌ فعليّ أصلاً.
    with client() as cl, mock.patch(
            "requests.sessions.Session.request",
            side_effect=OSError("network disabled for offline test")):
        r = cl.post("/platform/billing/checkout", json=_BODY)
        assert r.status_code == 200
        assert r.json()["configured"] is False
        assert len(_audit_rows("checkout_requested")) == 1


def test_payments_module_has_zero_network_imports():
    """نمط `correlation.py`: الوحدة تُستورد في كل إقلاع — لا استيراد شبكي
    على مستوى الوحدة إطلاقاً (النداء يوم يُبنى يكون كسولاً داخل الدالة)."""
    tree = ast.parse((_ROOT / "silk_platform" / "payments.py")
                     .read_text(encoding="utf-8"))
    banned = {"requests", "httpx", "urllib", "urllib3", "aiohttp", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods = {(node.module or "").split(".")[0]}
        else:
            continue
        assert not (mods & banned), f"استيراد شبكي في payments.py: {mods}"


# ── ٣) حُرّاس الصفحة — لا شاشة نجاح دفعٍ لم يقع ─────────────────────────────
def test_checkout_page_never_fakes_a_payment():
    assert "تم الدفع" not in _PAGE                 # لا ادعاء دفعٍ أبداً
    assert "msg info" in _PAGE                     # النتيجة صندوق معلوماتي
    assert ".good" not in _PAGE and "success" not in _PAGE.lower()
    assert "لن يُحصَّل أي مبلغ الآن" in _PAGE       # الصدق قبل الإرسال


def test_checkout_page_reads_the_real_endpoints_and_no_hardcoded_prices():
    assert '"/platform/pricing"' in _PAGE
    assert '"/platform/billing/checkout"' in _PAGE
    for price in ("749", "1899", "1,899", "4999", "4,999",      # القديمة
                  "699", "1799", "1,799", "4499", "4,499",      # الشهرية
                  "6990", "6,990", "17990", "17,990",
                  "44990", "44,990"):                           # السنوية
        assert price not in _PAGE, f"سعر مثبّت: {price}"
    assert 'get("plan")' in _PAGE                  # ?plan= من بطاقات الهبوط
    assert 'get("cycle")' in _PAGE                 # ?cycle= يسبق اختيار المبدّل


def test_checkout_route_redirect_preserves_the_query(monkeypatch):
    seed(monkeypatch)
    with client() as cl:
        r = cl.get("/checkout?plan=gold", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/checkout.html?plan=gold"
