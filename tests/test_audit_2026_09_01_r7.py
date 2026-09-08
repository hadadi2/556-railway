"""أقفال R7 — الأمن (التدقيق الجنائي 2026-09-01، المرحلة ٧).

لماذا هذا الملف: خنقُ دخولٍ يُتجاوَز بتدوير IP، وحدُّ معدّلٍ يمنح كلَّ مفتاحٍ مزوَّر
دلوَه، ومفتاحُ Comtrade في الرابط والسجلّ، ورمزُ إعادة التعيين في الرابط وسجلّ
الوصول، وCSP بلا `form-action`/`object-src`، ولا HSTS، وحاويةٌ تعمل جذراً
بخطوطٍ من فرعٍ متحرّك، ونصٌّ خارجيّ قد يبلغ كلود بلا عزل، وبريدُ إعادة التعيين
متزامنٌ (قناةُ توقيت)، وكوكي بلا Secure على https، وGET ذاتُ أثرٍ تُستدعى عبر
المواقع، وجلسةٌ بلا عمرٍ مطلق، وتنظيفٌ رهينُ المجدول الاختياري، وscrypt ضعيف،
وصورةٌ تُقبَل بامتدادها لا بمحتواها، و`/health` يكشف المسارات والإصدار للعموم،
وسقفُ شراءٍ بلا عدّاد بريد ولا احتفاظ، وتصفيرُ حصّة الخزنة، وأسماءُ منتجات
المصانع للمحلّل، ونصُّ الاستثناء الخام في أجسام 500، وبوّابةُ مراجعةٍ تقبل
القالبَ الفارغ، وتثبيتٌ مصاب لـpython-multipart.

هرمتي: قواعد مؤقّتة، لا شبكة. Hermetic only.
"""
from __future__ import annotations

import ast
import datetime
import json
import logging
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import time
import types
from unittest import mock
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.platform_helpers import (client, hdr, login, make_factory,  # noqa: E402
                                    make_product_study, seed, setup_env)

pytest.importorskip("fastapi")

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_HDR = {"X-API-Key": "secret"}
_ENV = {"ANTHROPIC_API_KEY": "test", "SILK_RATE_LIMIT": "0", "SILK_API_KEY": "secret",
        "SILK_ORPHAN_REAP_INTERVAL_S": "0"}
_SMTP_CFG = {"host": "smtp.test", "port": 25, "use_tls": False, "username": "",
             "password": "", "from_email": "noreply@silk.test", "from_name": "Silk"}


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _root_client(**env):
    from fastapi.testclient import TestClient
    import api as root_api
    return TestClient(root_api.create_app()), root_api


def _pconn():
    from silk_platform import db as pdb
    return pdb.connect()


# ══════════════ AUTH-1(a) / API-7 — عدّادُ بريدٍ للدخول، ودلوُ المضيف للمفاتيح المزوّرة ═══
def test_login_email_counter_holds_under_ip_rotation(monkeypatch):
    """٣٠ فشلاً على بريدٍ واحد من عناوين مختلفة كانت تعبر (عدّادُ (بريد،IP) يتصفّر
    بتدوير IP، وعدّادُ IP لا يجمع) — عدّادٌ ثالث بالبريد وحده."""
    info = seed(monkeypatch)
    from silk_platform import throttle
    ident = throttle.login_email_identity(info["admin"]["email"])
    assert ident.startswith("login-email|")
    assert "LOGINEMAIL" in throttle.NAMED_WINDOW_DEFAULTS
    limits = throttle.named_limits("LOGINEMAIL", 30, 900)
    conn = _pconn()
    try:
        for _ in range(30):
            throttle.record_failure(conn, ident, limits)
        conn.commit()
    finally:
        conn.close()
    from silk_platform import api as papi
    monkeypatch.setattr(papi, "_client_ip", lambda request: "9.9.9.9")   # IP جديد
    cl = client()
    r = cl.post("/platform/auth/login", json={"email": info["admin"]["email"],
                                              "password": info["admin"]["password"]})
    assert r.status_code == 429, r.text


def test_root_rate_limit_shares_the_host_bucket_for_unvalidated_keys():
    """كلُّ قيمةِ `X-API-Key` مزوَّرة كانت تنال دلوَها الخاص — التدوير يلغي الحدّ."""
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with patch.dict(os.environ, {"SILK_API_KEY": "secret", "SILK_DB": db,
                                 "SILK_RATE_LIMIT": "3", "SILK_RATE_WINDOW": "60"}):
        cl, root_api = _root_client()
        with mock.patch.object(root_api, "time",
                               types.SimpleNamespace(time=lambda: 1_000_000.0)):
            codes = [cl.get("/markets", headers={"X-API-Key": f"bogus-{i}"}).status_code
                     for i in range(5)]
    assert codes[:3] == [200, 200, 200], codes
    assert codes[3] == 429 and codes[4] == 429, codes


# ══════════════ SEC-4 / EXT-18 / API-10 — مفتاحُ Comtrade ترويسةً، بلا أثرٍ في السجلّ ═══
def test_comtrade_key_travels_as_a_header_read_per_call(monkeypatch):
    import silk_data_layer as d
    monkeypatch.setenv("COMTRADE_API_KEY", "sek-123")
    monkeypatch.delenv("SILK_COMTRADE_KEY_IN_QUERY", raising=False)
    seen: dict = {}

    def spy(url, params, ttl_seconds=86400, headers=None, **kw):   # EXT: cacheable/short_lived
        seen.update(url=url, params=dict(params), headers=dict(headers or {}))
        return {"data": []}
    monkeypatch.setattr(d, "_cached_get", spy)
    assert d.comtrade_trade("080410", "784", 2024) == []
    assert seen["headers"].get("Ocp-Apim-Subscription-Key") == "sek-123"
    assert "subscription-key" not in seen["params"]
    assert seen["url"].endswith("/data/v1/get/C/A/HS")       # المفتاحُ يُقرأ عند النداء


def test_comtrade_key_in_query_rollback_valve(monkeypatch):
    import silk_data_layer as d
    monkeypatch.setenv("COMTRADE_API_KEY", "sek-123")
    monkeypatch.setenv("SILK_COMTRADE_KEY_IN_QUERY", "1")
    seen: dict = {}

    def spy(url, params, ttl_seconds=86400, headers=None, **kw):   # EXT: cacheable/short_lived
        seen.update(params=dict(params), headers=dict(headers or {}))
        return {"data": []}
    monkeypatch.setattr(d, "_cached_get", spy)
    d.comtrade_trade("080410", "784", 2024)
    assert seen["params"].get("subscription-key") == "sek-123"
    assert "Ocp-Apim-Subscription-Key" not in seen["headers"]


def test_fetch_failure_logs_never_carry_the_comtrade_key(monkeypatch, caplog):
    import requests
    import silk_data_layer as d
    monkeypatch.setenv("COMTRADE_API_KEY", "sek-123")
    monkeypatch.setattr(d, "_cached_get", lambda *a, **k: None)

    def boom(*a, **k):
        raise requests.HTTPError(
            "429 Client Error: Too Many Requests for url: "
            "https://comtradeapi.un.org/data/v1/get/C/A/HS?subscription-key=sek-123&x=1")
    monkeypatch.setattr(d, "_http_get", boom)
    with caplog.at_level(logging.WARNING, logger="silk_data_layer"):
        assert d.comtrade_trade("080410", "784", 2024) is None
    assert "sek-123" not in caplog.text
    assert "COMTRADE_API_KEY" in caplog.text or "query-redacted" in caplog.text


def test_cached_get_failure_log_is_redacted(monkeypatch, caplog):
    import silk_cache
    monkeypatch.setenv("COMTRADE_API_KEY", "sek-123")
    monkeypatch.setenv("SILK_CACHE_DIR", tempfile.mkdtemp())

    def boom(url, params, headers=None):
        raise RuntimeError("boom https://x.test/a?subscription-key=sek-123")
    with caplog.at_level(logging.WARNING, logger="silk_cache"):
        out = silk_cache.cached_get("https://x.test/a", {"q": 1}, ttl_seconds=1,
                                    fetcher=boom)
    assert out is None
    assert "sek-123" not in caplog.text


def test_soffice_child_env_carries_no_secrets(monkeypatch, tmp_path):
    """بيئةُ عملية LibreOffice كانت نسخةَ بيئة الخادم كاملةً (مفاتيحُ المزوّدين)."""
    import silk_reports
    from docx import Document
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-leak-123")
    monkeypatch.setattr(silk_reports, "_find_soffice", lambda: "soffice-fake")
    captured: dict = {}

    def fake_run(cmd, **kw):
        captured["env"] = dict(kw.get("env") or {})
        out_dir = cmd[cmd.index("--outdir") + 1]
        src = cmd[-1]
        pathlib.Path(out_dir, pathlib.Path(src).stem + ".pdf").write_bytes(b"%PDF-1.4")
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    # R9 (API-11/EXT-14): التحويلُ صار عبر `_run_soffice` (Popen في مجموعة عملية جديدة)
    # — المقعدُ نفسُه يحمل `env=` نفسَه، فالقفلُ يتبع المقعدَ لا الدالّةَ المكتبية.
    monkeypatch.setattr(silk_reports, "_run_soffice", fake_run)
    docx = tmp_path / "r.docx"
    Document().save(str(docx))
    silk_reports.docx_to_pdf(str(docx), str(tmp_path / "r.pdf"))
    env = captured["env"]
    assert "ANTHROPIC_API_KEY" not in env
    assert not any(k.endswith("_API_KEY") or k.startswith("SILK_") for k in env)
    assert "HOME" in env and "PATH" in env


# ══════════════ SEC-6 — رمزُ إعادة التعيين لا يبقى في الرابط ولا في سجلّ الوصول ═══
def test_reset_page_strips_the_token_from_the_url():
    page = _read("web/reset-password.html")
    assert "history.replaceState" in page
    assert page.index('get("token")') < page.index("history.replaceState")


def test_uvicorn_access_log_filter_redacts_query_tokens():
    import api as root_api
    root_api.create_app()
    lg = logging.getLogger("uvicorn.access")
    flt = [f for f in lg.filters if isinstance(f, root_api._QueryTokenFilter)]
    assert flt, "مرشّحُ سجلّ الوصول غير مركَّب"
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                            '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:1", "GET", "/reset-password?token=abc123&x=1",
                             "1.1", 200), None)
    assert flt[0].filter(rec) is True
    assert "abc123" not in rec.getMessage()
    assert "token=<redacted>" in rec.getMessage() and "x=1" in rec.getMessage()


# ══════════════ SEC-9 / SEC-1 — CSP أكمل، وHSTS بصمّام ═══════════════════════
def test_csp_has_form_action_and_object_src():
    cl, _ = _root_client()
    csp = cl.get("/health").headers.get("Content-Security-Policy") or ""
    assert "form-action 'self'" in csp and "object-src 'none'" in csp
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp


def test_hsts_follows_the_valve_and_the_prod_signal():
    def _hsts(**env):
        with patch.dict(os.environ, env):
            cl, _ = _root_client()
            return cl.get("/health").headers.get("Strict-Transport-Security")
    assert _hsts(SILK_HSTS="", SILK_PLATFORM_SECURE_COOKIES="",
                 SILK_PLATFORM_REQUIRE_SECRET="") is None
    assert _hsts(SILK_HSTS="1") == "max-age=31536000; includeSubDomains"
    # إشارةُ الإنتاج تُشغّل حارسَ الإقلاع — عاملُ bcrypt الإنتاجي لازمٌ له (لا بذر هنا).
    assert _hsts(SILK_HSTS="", SILK_PLATFORM_SECURE_COOKIES="1", SILK_PLATFORM_BCRYPT_ROUNDS="12",
                 SILK_PLATFORM_SECRET="x" * 32) == "max-age=31536000; includeSubDomains"
    assert _hsts(SILK_HSTS="0", SILK_PLATFORM_SECURE_COOKIES="1", SILK_PLATFORM_BCRYPT_ROUNDS="12",
                 SILK_PLATFORM_SECRET="x" * 32) is None


# ══════════════ SEC-8 / EXT-15 — حاويةٌ بلا جذر، وخطوطٌ مثبَّتةٌ بالبصمة ═══════
def test_dockerfile_drops_root_and_pins_fonts_by_digest():
    docker = _read("Dockerfile")
    assert "useradd" in docker and "silk" in docker
    assert "setpriv --reuid=silk" in _read("docker/entrypoint.sh")
    assert "SILK_RUN_AS_ROOT" in _read("docker/entrypoint.sh")
    assert "docker/entrypoint.sh" in docker
    assert "/google/fonts/main/" not in docker, "خطوطٌ من فرعٍ متحرّك"
    assert "sha256sum -c" in docker
    digests = [ln for ln in _read("docker/fonts.sha256").splitlines() if ln.strip()]
    assert len(digests) == 3
    for ln in digests:
        assert re.fullmatch(r"[0-9a-f]{64} [ *]IBMPlexSansArabic-\w+\.ttf", ln), ln
    assert re.search(r"GOOGLE_FONTS_COMMIT=[0-9a-f]{40}", docker)


def test_docker_health_job_asserts_the_unprivileged_user():
    wf = _read(".github/workflows/e2e-live-shape.yml")
    assert "/proc/1/status" in wf and '"10001"' in wf


# ══════════════ SEC-3 — عزلُ النصّ الخارجيّ قبل كلود (قفلٌ بنيويّ + سقّاطة) ═══
_LLM_CALLS = {"_call", "_call_tools", "complete", "complete_tools", "complete_vision"}
_ISOLATION_EXEMPT = {
    ("silk_ai_judge.py", "_call"), ("silk_ai_judge.py", "_call_tools"),   # البدائيّات
    ("silk_ai_judge.py", "_continue_truncated_report"),   # يُكمل مسودّةً كتبها النموذج
    ("silk_evals.py", "evaluate_report"),                 # يقيّم مخرجَ النموذج نفسه
}
_ISOLATE_MIN = {"silk_ai_judge.py": 28, "silk_llm_runtime.py": 9,
                "silk_hs_classifier.py": 7, "silk_synthesis.py": 4, "silk_evals.py": 2,
                "silk_research.py": 2, "silk_product_intake.py": 2}


def test_every_llm_calling_function_isolates_external_text():
    problems = []
    for mod, floor in _ISOLATE_MIN.items():
        src = _read(mod)
        assert src.count("_isolate(") >= floor, f"{mod}: عزلٌ أقلّ من السقّاطة {floor}"
        for fn in [n for n in ast.walk(ast.parse(src))
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            calls = set()
            for c in ast.walk(fn):
                if isinstance(c, ast.Call):
                    f = c.func
                    calls.add(f.id if isinstance(f, ast.Name)
                              else f.attr if isinstance(f, ast.Attribute) else "")
            if calls & _LLM_CALLS and (mod, fn.name) not in _ISOLATION_EXEMPT \
                    and not any(x.startswith("_isolate") for x in calls):
                problems.append(f"{mod}:{fn.name}")
    assert not problems, f"دوالٌ تنادي كلود بلا عزلٍ للنصّ الخارجيّ: {problems}"


# ══════════════ SEC-13 — مفتاحُ كلود لا يُخزَّن من الواجهة ═══════════════════
def test_set_keys_refuses_the_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch.dict(os.environ, {"SILK_API_KEY": "secret", "SILK_RATE_LIMIT": "0",
                                 "SILK_STORE_DB": os.path.join(tempfile.mkdtemp(), "s.db")}):
        cl, _ = _root_client()
        r = cl.post("/settings/keys", headers=_HDR,
                    json={"keys": {"ANTHROPIC_API_KEY": "sk-ant-x", "COMTRADE_API_KEY": "c1"}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "ANTHROPIC_API_KEY" not in body["saved"]
        assert body.get("owner_env_only") == ["ANTHROPIC_API_KEY"]
    assert os.environ.get("ANTHROPIC_API_KEY") is None


# ══════════════ AUTH-3 / AUTH-7 — بريدٌ غيرُ متزامن، وإصدارُ الأدمِن بالبريد ═══
def test_reset_request_latency_is_independent_of_email_existence(monkeypatch):
    info = seed(monkeypatch)
    from silk_platform import smtp_transport as st
    sent: list = []

    def slow_send(**kw):
        time.sleep(0.6)
        sent.append(kw)
    monkeypatch.setattr(st, "operator_config_from_env", lambda: dict(_SMTP_CFG))
    monkeypatch.setattr(st, "send", slow_send)
    cl = client()
    t0 = time.monotonic()
    assert cl.post("/platform/auth/password-reset/request",
                   json={"email": info["admin"]["email"]}).status_code == 200
    t_known = time.monotonic() - t0
    t0 = time.monotonic()
    assert cl.post("/platform/auth/password-reset/request",
                   json={"email": "nobody@nowhere.local"}).status_code == 200
    t_unknown = time.monotonic() - t0
    assert t_known < 0.5 and t_unknown < 0.5, (t_known, t_unknown)
    st.wait_pending(timeout=5)
    assert len(sent) == 1 and "reset-password?token=" in sent[0]["body"]
    conn = _pconn()
    try:
        n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = "
                         "'password_reset_email_sent'").fetchone()[0]
    finally:
        conn.close()
    assert n == 1


def test_admin_issue_reset_emails_when_smtp_is_configured(monkeypatch):
    info = seed(monkeypatch)
    from silk_platform import smtp_transport as st
    sent: list = []
    monkeypatch.setattr(st, "send", lambda **kw: sent.append(kw))
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    uid = info["factory_a"]["user_id"]
    monkeypatch.setattr(st, "operator_config_from_env", lambda: None)
    r = cl.post(f"/platform/admin/users/{uid}/reset", headers=hdr(tok))
    assert r.status_code == 200, r.text
    assert r.json()["delivered"] == "response" and r.json().get("reset_token")
    monkeypatch.setattr(st, "operator_config_from_env", lambda: dict(_SMTP_CFG))
    r = cl.post(f"/platform/admin/users/{uid}/reset", headers=hdr(tok))
    assert r.status_code == 200, r.text
    assert r.json()["delivered"] == "email" and "reset_token" not in r.json()
    st.wait_pending(timeout=5)
    assert len(sent) == 1 and sent[0]["to_email"] == info["factory_a"]["email"]


# ══════════════ AUTH-6 — Secure على https دائماً ══════════════════════════════
def test_session_cookie_is_secure_over_https(monkeypatch):
    info = seed(monkeypatch)
    from fastapi.testclient import TestClient
    from silk_platform.api import create_platform_app
    body = {"email": info["admin"]["email"], "password": info["admin"]["password"]}
    https = TestClient(create_platform_app(), base_url="https://testserver")
    r = https.post("/platform/auth/login", json=body)
    assert r.status_code == 200 and "secure" in r.headers.get("set-cookie", "").lower()
    http = TestClient(create_platform_app(), base_url="http://testserver")
    r = http.post("/platform/auth/login", json=body)
    assert r.status_code == 200 and "secure" not in r.headers.get("set-cookie", "").lower()


# ══════════════ AUTH-8 — GET ذاتُ أثرٍ لا تُستدعى بالكوكي عبر المواقع ═════════
def test_cross_site_cookie_get_is_refused_on_side_effecting_routes(monkeypatch):
    info = seed(monkeypatch)
    monkeypatch.setenv("SILK_DIAG_EXEMPT", "1")
    import silk_diagnostics
    monkeypatch.setattr(silk_diagnostics, "run_diagnostics",
                        lambda: {"overall": "ok", "sources": []})
    cl = client()
    r = cl.post("/platform/auth/login", json={"email": info["admin"]["email"],
                                              "password": info["admin"]["password"]})
    assert r.status_code == 200
    token = r.json()["token"]
    r = cl.get("/platform/admin/diagnostics", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403, r.text                    # كوكي + عبر المواقع
    assert r.json()["detail"]["error"] == "cross_site_get_refused"
    cl.cookies.clear()
    r = cl.get("/platform/admin/diagnostics",
               headers={"Sec-Fetch-Site": "cross-site", **hdr(token)})
    assert r.status_code == 200, r.text                    # حاملُ الرمز لا يُحجَب


def test_admin_diagnostics_accepts_post_and_the_page_uses_it(monkeypatch):
    info = seed(monkeypatch)
    monkeypatch.setenv("SILK_DIAG_EXEMPT", "1")
    import silk_diagnostics
    monkeypatch.setattr(silk_diagnostics, "run_diagnostics",
                        lambda: {"overall": "ok", "sources": []})
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    assert cl.post("/platform/admin/diagnostics", headers=hdr(tok)).status_code == 200
    page = _read("web/platform.html")
    assert re.search(r'api\("/admin/diagnostics",\s*\{method:\s*"POST"', page)


# ══════════════ AUTH-11 / AUTH-12 — عمرٌ مطلق للجلسة، وتنظيفٌ ساعيّ بلا مجدول ═══
def test_sessions_expire_absolutely_after_thirty_days(monkeypatch):
    info = seed(monkeypatch)
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    assert cl.get("/platform/me", headers=hdr(tok)).status_code == 200

    def _age(days: int):
        conn = _pconn()
        try:
            old = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute("UPDATE sessions SET created_at = ?", (old,))
            conn.commit()
        finally:
            conn.close()
    _age(29)
    assert cl.get("/platform/me", headers=hdr(tok)).status_code == 200
    _age(31)
    assert cl.get("/platform/me", headers=hdr(tok)).status_code == 401


def test_sweep_pass_runs_session_cleanup_once_per_hour(monkeypatch):
    setup_env(monkeypatch)
    from silk_platform import engine_bridge, scheduler, study_runtime
    monkeypatch.setattr(engine_bridge, "sweep_orphans", lambda conn: None)
    monkeypatch.setattr(study_runtime, "supervisor_enabled", lambda: True)
    ran: list = []
    monkeypatch.setattr(scheduler, "run_job", lambda name: ran.append(name))
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(scheduler, "time", types.SimpleNamespace(time=lambda: clock["t"],
                                                                  sleep=lambda s: None))
    scheduler.reset_cleanup_slot_for_tests()
    scheduler.sweep_pass()
    scheduler.sweep_pass()
    assert ran == ["session_cleanup"]
    clock["t"] += 3600
    scheduler.sweep_pass()
    assert ran == ["session_cleanup", "session_cleanup"]


# ══════════════ AUTH-14 — scrypt أقوى، ولا إنتاجَ بلا bcrypt ═══════════════════
def test_scrypt_cost_is_2_15_and_prod_refuses_missing_bcrypt(monkeypatch):
    from silk_platform import api as papi, passwords
    monkeypatch.delenv("SILK_PLATFORM_SCRYPT_N", raising=False)
    assert passwords.scrypt_n() == 2 ** 15
    monkeypatch.setenv("SILK_PLATFORM_REQUIRE_SECRET", "1")
    monkeypatch.setenv("SILK_PLATFORM_SECRET", "x" * 32)
    monkeypatch.delenv("SILK_PLATFORM_BCRYPT_ROUNDS", raising=False)
    monkeypatch.setattr(passwords, "_bcrypt", None)
    with pytest.raises(RuntimeError, match="bcrypt"):
        papi.boot_config_guard()


# ══════════════ AUTH-15 — كلمةٌ ضعيفة لا تحرق الرمز ═══════════════════════════
def test_weak_password_does_not_burn_the_reset_token(monkeypatch):
    info = seed(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_EXPOSE_RESET_TOKEN", "1")
    cl = client()
    r = cl.post("/platform/auth/password-reset/request",
                json={"email": info["admin"]["email"]})
    tok = r.json()["reset_token"]
    r = cl.post("/platform/auth/password-reset/confirm",
                json={"token": tok, "new_password": "weak"})
    assert r.status_code == 422, r.text
    r = cl.post("/platform/auth/password-reset/confirm",
                json={"token": tok, "new_password": "Strong-Pass-2026!"})
    assert r.status_code == 200, r.text


# ══════════════ AUTH-17 / BIZ-9 — الصورةُ بمحتواها لا بامتدادها ═════════════════
def test_upload_refuses_bytes_that_do_not_match_the_extension(monkeypatch):
    seed(monkeypatch)
    f = make_factory("basic", "r7@factory.local")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\0" * 64
    r = cl.post("/platform/images", headers=hdr(tok),
                files={"file": ("x.png", jpeg_bytes, "image/png")})
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "image_content_mismatch"
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
    r = cl.post("/platform/images", headers=hdr(tok),
                files={"file": ("x.png", png_bytes, "image/png")})
    assert r.status_code in (200, 201), r.text


# ══════════════ AUTH-18 / API-20 — `/health` لا يكشف المسارات والإصدار للعموم ═══
def test_health_hides_operational_fields_without_a_valid_key():
    private = ("storage", "version", "ai_model")
    public = ("status", "deps", "sources", "research_ready")
    with patch.dict(os.environ, {"SILK_API_KEY": "secret", "SILK_HEALTH_VERBOSE": ""}):
        cl, _ = _root_client()
        anon = cl.get("/health").json()
        keyed = cl.get("/health", headers=_HDR).json()
    assert all(k not in anon for k in private), sorted(anon)
    assert all(k in anon for k in public), sorted(anon)
    assert all(k in keyed for k in private), sorted(keyed)
    with patch.dict(os.environ, {"SILK_API_KEY": "secret", "SILK_HEALTH_VERBOSE": "1"}):
        cl, _ = _root_client()
        assert all(k in cl.get("/health").json() for k in private)
    with patch.dict(os.environ, {"SILK_API_KEY": "", "SILK_HEALTH_VERBOSE": ""}):
        cl, _ = _root_client()
        assert all(k in cl.get("/health").json() for k in private)   # وضعُ التطوير


# ══════════════ AUTH-20 — عدّادُ بريدٍ للشراء، واحتفاظٌ محدود ════════════════
def test_checkout_email_counter_and_retention_prune(monkeypatch):
    seed(monkeypatch)
    from silk_platform import api as papi, audit, throttle
    assert "CHECKOUTEMAIL" in throttle.NAMED_WINDOW_DEFAULTS
    ips = iter(f"10.0.0.{i}" for i in range(1, 50))
    monkeypatch.setattr(papi, "_client_ip", lambda request: next(ips))
    cl = client()
    # P3 (BIZ-7): كشفُ التكرار (بريد+باقة+دورة) يقمع **قيدَ التدقيق** للطلب المعاد،
    # وهذا الاختبار يحتاج ستّةَ قيودٍ ببريدٍ واحد ليقيس عدّادَ البريد والتقليم. يُعطَّل
    # هنا صراحةً؛ مسارُه مقفولٌ وحده في
    # `tests/test_audit_2026_09_01_p3.py::test_a_duplicate_checkout_is_recorded_once`.
    monkeypatch.setenv("SILK_PLATFORM_CHECKOUT_DEDUPE_MIN", "0")
    body = {"plan": "basic", "email": "buyer@factory.local", "name": "x"}
    codes = [cl.post("/platform/billing/checkout", json=body).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429, codes
    conn = _pconn()
    try:
        old = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute("UPDATE audit_log SET created_at = ? WHERE action = "
                     "'checkout_requested' AND id = (SELECT MIN(id) FROM audit_log "
                     "WHERE action = 'checkout_requested')", (old,))
        conn.commit()
        removed = audit.prune_checkout(conn, days=365)
        conn.commit()
        left = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = "
                            "'checkout_requested'").fetchone()[0]
    finally:
        conn.close()
    assert removed == 1 and left == 4
    assert "prune_checkout" in _read("silk_platform/scheduler.py")


# ══════════════ AUTH-21 / AUTH-22 — الخزنةُ لا تُصفَّر، والمحلّلُ يرى فصولاً لا أسماء ═══
def test_admin_quota_reset_refuses_the_vault(monkeypatch):
    info = seed(monkeypatch)
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    r = cl.post(f"/platform/admin/accounts/{info['vault_account_id']}/reset-quota", headers=hdr(tok))
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["error"] == "vault_quota_reset_refused"
    r = cl.post(f"/platform/admin/accounts/{info['factory_a']['account_id']}/reset-quota",
                headers=hdr(tok))
    assert r.status_code == 200, r.text


def test_analyst_aggregates_expose_hs_chapters_not_product_names(monkeypatch):
    info = seed(monkeypatch)
    fa = info["factory_a"]
    sid = make_product_study(fa["account_id"], fa["user_id"], product="تمور سكري خاصّة")
    conn = _pconn()
    try:
        conn.execute("UPDATE studies SET hs_code = '080410' WHERE id = ?", (sid,))
        conn.commit()
    finally:
        conn.close()
    cl = client()
    tok = login(cl, info["analyst"]["email"], info["analyst"]["password"])
    out = cl.get("/platform/analyst/aggregates", headers=hdr(tok)).json()
    assert "top_products" not in out
    assert out["top_hs_chapters"] and out["top_hs_chapters"][0]["chapter"] == "08"
    assert "تمور سكري خاصّة" not in json.dumps(out, ensure_ascii=False)
    page = _read("web/platform.html")
    assert "top_hs_chapters" in page and "agg.top_products" not in page


# ══════════════ API-9 / SEC-10 — جسمُ 500 يسمّي الصنفَ لا نصَّ الاستثناء ════════
def test_research_failure_body_names_the_type_not_the_message():
    from tests.test_wave13_resilience import _fake_call, _fake_call_tools_factory
    import silk_storage as st
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    env = dict(_ENV, ANTHROPIC_API_KEY="sk-ant-secret-x", SILK_DB=db)
    with patch.dict(os.environ, env), \
            patch("silk_llm_runtime._call_tools", side_effect=_fake_call_tools_factory([])), \
            patch("silk_synthesis._call", side_effect=_fake_call), \
            patch("silk_ai_judge._call", side_effect=_fake_call), \
            patch("silk_storage.save_analysis",
                  side_effect=KeyError("token sk-ant-secret-x rejected")):
        cl, _ = _root_client()
        r = cl.post("/research", headers=_HDR,
                    json={"product": "تمور", "market": "Nigeria", "hs_code": "080410",
                          "persist": True})
        assert r.status_code == 500, r.text
        detail = r.json()["detail"]
        assert detail["error"] == "research_run_failed"
        assert detail["error_type"] == "KeyError"
        assert "sk-ant-secret-x" not in r.text and "rejected" not in r.text
        aid = detail["analysis_id"]
        row = sqlite3.connect(st._db_path()).execute(
            "SELECT * FROM analyses WHERE id = ?", (aid,)).fetchone()
    blob = " ".join(str(v) for v in row)
    assert "sk-ant-secret-x" not in blob and "KeyError" in blob


# ══════════════ CI-7 / CI-8 / CI-9 / python-multipart ═══════════════════════════
def test_live_smoke_installs_the_ci_requirements():
    assert "-r requirements-ci.txt" in _read(".github/workflows/live-smoke.yml")


def test_stop_hook_has_an_opt_in_subset():
    hook = _read(".claude/hooks/suite-green-stop.sh")
    assert "SILK_STOP_HOOK_SUBSET" in hook
    assert "tests/test_audit_2026_09_01_" in hook


def test_python_multipart_is_upgraded_and_the_ignore_list_is_gone():
    reqs = _read("requirements.txt")
    pin = re.search(r"^python-multipart==([\d.]+)", reqs, re.M)
    assert pin and tuple(int(x) for x in pin.group(1).split(".")) >= (0, 0, 31), pin
    ci = _read(".github/workflows/ci.yml")
    assert "--ignore-vuln" not in ci
    assert "pip-audit -r requirements.txt --strict" in ci


# ══════════════ توثيقُ الصمّامات والدليل ══════════════════════════════════════
def test_r7_env_vars_and_runbook_are_documented():
    example = _read(".env.example")
    for name in ("SILK_COMTRADE_KEY_IN_QUERY", "SILK_HSTS", "SILK_RUN_AS_ROOT",
                 "SILK_PLATFORM_SESSION_ABSOLUTE_HOURS", "SILK_PLATFORM_LOGINEMAIL_MAX_REQUESTS",
                 "SILK_PLATFORM_CHECKOUTEMAIL_MAX_REQUESTS",
                 "SILK_PLATFORM_CHECKOUT_RETENTION_DAYS", "SILK_HEALTH_VERBOSE",
                 "SILK_STOP_HOOK_SUBSET"):
        assert name in example, name
    deploy = _read("docs/DEPLOY_RAILWAY.md")
    assert "SILK_FORWARDED_ALLOW_IPS" in deploy and "SILK_TRACE_RETENTION_DAYS=30" in deploy
    assert "Ocp-Apim-Subscription-Key" in deploy or "COMTRADE_API_KEY" in deploy


# ══════════════ مراجعة R7 (/code-review high) — قفلٌ لكلّ اكتشاف ═══════════
_STORE_VARS = ("SILK_DB", "SILK_STORE_DB", "SILK_USAGE_DB", "SILK_OPS_LOG_DB",
               "SILK_WATCHDOG_DB", "SILK_PLATFORM_DB", "SILK_CACHE_DIR",
               "SILK_PLATFORM_STORAGE_DIR", "SILK_TRACE_DIR")


def test_entrypoint_owns_every_explicit_store_path():
    """`chown` على `SILK_DATA_DIR` وحده يترك المخازنَ الموجَّهة بمتغيّراتها الصريحة
    (`SILK_DB=/data/silk.db` بلا `SILK_DATA_DIR` شكلٌ موثَّق) مملوكةً للجذر ⇒ uid 10001
    لا يكتب ⇒ حلقةُ إعادة تشغيل."""
    sh = _read("docker/entrypoint.sh")
    for v in _STORE_VARS:
        assert v in sh, v
    assert "dirname" in sh


def test_non_ascii_api_key_header_never_500s():
    """`hmac.compare_digest` يرفع TypeError على نصٍّ غير ASCII — ترويسةٌ مشوَّهة كانت
    500 على `/health` وكلّ مسارٍ مخنوق."""
    import api as root_api
    assert root_api._key_matches("\u00e9", "secret") is False       # لا TypeError
    with patch.dict(os.environ, {"SILK_API_KEY": "secret", "SILK_RATE_LIMIT": "0"}):
        cl, _ = _root_client()
        bad = {"X-API-Key": "\u00e9".encode("latin-1")}   # httpx يمرّر البايتات كما هي
        assert cl.get("/health", headers=bad).status_code == 200
        assert cl.get("/markets", headers=bad).status_code != 500
        assert cl.get("/analyses", headers=bad).status_code == 401


def test_admin_reset_dialog_branches_on_delivery():
    page = _read("web/platform.html")
    assert "out.delivered" in page


def test_admin_issue_reset_falls_back_to_the_response_when_smtp_fails(monkeypatch):
    """مع SMTP مضبوطٍ ومعطَّل كان الأدمِن يُخبَر `delivered: email` والرمزُ يضيع."""
    info = seed(monkeypatch)
    from silk_platform import smtp_transport as st

    def boom(**kw):
        raise RuntimeError("relay down")
    monkeypatch.setattr(st, "send", boom)
    monkeypatch.setattr(st, "operator_config_from_env", lambda: dict(_SMTP_CFG))
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    r = cl.post(f"/platform/admin/users/{info['factory_a']['user_id']}/reset", headers=hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delivered"] == "response" and body.get("reset_token")
    assert body.get("email_error")
    conn = _pconn()
    try:
        n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = "
                         "'password_reset_email_failed'").fetchone()[0]
    finally:
        conn.close()
    assert n == 1


def test_anthropic_key_is_refused_by_the_store_and_never_loaded_into_env(monkeypatch):
    """SEC-13 كان منعاً عند الكتابة فقط: صفٌّ قديم (أو كتابةٌ مباشرة) كان يُحقَن في بيئة
    العملية عند كلّ إقلاع عبر `load_settings_into_env`."""
    import silk_store
    monkeypatch.setenv("SILK_STORE_DB", os.path.join(tempfile.mkdtemp(), "s.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    silk_store.migrate()
    assert silk_store.set_setting("ANTHROPIC_API_KEY", "sk-ant-x") is False
    assert "ANTHROPIC_API_KEY" not in silk_store._ALLOWED_KEY_SETTINGS
    with silk_store._open() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                     ("ANTHROPIC_API_KEY", "sk-ant-legacy", "2026-01-01T00:00:00Z"))
    silk_store.load_settings_into_env(overwrite=True)
    assert os.environ.get("ANTHROPIC_API_KEY") is None


def test_collectors_budget_follows_the_per_call_comtrade_key(monkeypatch):
    import silk_collectors
    import silk_store
    monkeypatch.setenv("SILK_STORE_DB", os.path.join(tempfile.mkdtemp(), "s.db"))
    monkeypatch.delenv("COMTRADE_DAILY_BUDGET", raising=False)
    silk_store.migrate()
    monkeypatch.delenv("COMTRADE_API_KEY", raising=False)
    assert silk_collectors.comtrade_budget_left() == 4
    monkeypatch.setenv("COMTRADE_API_KEY", "sek-late")      # مفتاحٌ ضُبط بعد الاستيراد
    assert silk_collectors.comtrade_budget_left() == 450


def test_diagnostics_probe_uses_the_header_path(monkeypatch):
    import silk_data_layer as dl
    import silk_diagnostics
    monkeypatch.setenv("COMTRADE_API_KEY", "sek-123")
    monkeypatch.delenv("SILK_COMTRADE_KEY_IN_QUERY", raising=False)
    seen: dict = {}

    def spy(url, params=None, headers=None, **kw):
        seen.update(url=url, params=dict(params or {}), headers=dict(headers or {}))
        return types.SimpleNamespace(raise_for_status=lambda: None,
                                     json=lambda: {"data": [{"x": 1}]})
    monkeypatch.setattr(dl, "_http_get", spy)
    out = silk_diagnostics._probe_comtrade(2024)
    assert out["state"] == silk_diagnostics.OK, out
    assert seen["headers"].get("Ocp-Apim-Subscription-Key") == "sek-123"
    assert "subscription-key" not in seen["params"]


def test_cross_site_cookie_get_is_refused_everywhere_under_the_platform_prefix(monkeypatch):
    """الحارسُ كان اختياريّاً لكلّ مسار (٣ مسارات) ومعتمداً على `Sec-Fetch-Site` وحده —
    `report.docx` و`signed-url` بقيا مكشوفَين، ومتصفّحٌ بلا الترويسة يمرّ."""
    info = seed(monkeypatch)
    fa = info["factory_a"]
    sid = make_product_study(fa["account_id"], fa["user_id"])
    cl = client()
    r = cl.post("/platform/auth/login", json={"email": fa["email"], "password": fa["password"]})
    assert r.status_code == 200
    xs = {"Sec-Fetch-Site": "cross-site"}
    assert cl.get(f"/platform/studies/{sid}/report.docx", headers=xs).status_code == 403
    assert cl.get("/platform/images/1/signed-url", headers=xs).status_code == 403
    r = cl.get("/platform/me", headers={"Origin": "https://evil.test"})   # بلا Sec-Fetch-Site
    assert r.status_code == 403, r.text
    assert cl.get("/platform/me", headers={"Origin": "http://testserver"}).status_code == 200
    assert cl.get("/platform/me").status_code == 200


def test_email_lockout_is_recoverable_by_reset_or_admin_unlock(monkeypatch):
    """٣٠ فشلاً من أيّ مكان تقفل الحسابَ (مقصود) — لكنّ صاحبَه يستعيده بإعادة تعيينٍ
    ناجحة، والأدمِن يفكّه صراحةً؛ بلا ذلك كان القفلُ أبدياً ما دام المهاجم يعيده."""
    info = seed(monkeypatch)
    from silk_platform import throttle
    fa = info["factory_a"]
    ident = throttle.login_email_identity(fa["email"])
    limits = throttle.named_limits("LOGINEMAIL", 30, 900)

    def _lock():
        conn = _pconn()
        try:
            for _ in range(30):
                throttle.record_failure(conn, ident, limits)
            conn.commit()
        finally:
            conn.close()
    cl = client()
    body = {"email": fa["email"], "password": fa["password"]}
    _lock()
    assert cl.post("/platform/auth/login", json=body).status_code == 429
    monkeypatch.setenv("SILK_PLATFORM_EXPOSE_RESET_TOKEN", "1")
    tok = cl.post("/platform/auth/password-reset/request",
                  json={"email": fa["email"]}).json()["reset_token"]
    r = cl.post("/platform/auth/password-reset/confirm",
                json={"token": tok, "new_password": "Fresh-Pass-2026!"})
    assert r.status_code == 200, r.text
    body = {"email": fa["email"], "password": "Fresh-Pass-2026!"}
    assert cl.post("/platform/auth/login", json=body).status_code == 200   # القفلُ زال
    _lock()
    assert cl.post("/platform/auth/login", json=body).status_code == 429
    atok = login(cl, info["admin"]["email"], info["admin"]["password"])
    r = cl.post(f"/platform/admin/users/{fa['user_id']}/unlock-login", headers=hdr(atok))
    assert r.status_code == 200, r.text
    assert cl.post("/platform/auth/login", json=body).status_code == 200


def test_access_log_filter_also_redacts_signed_url_signatures():
    import api as root_api
    flt = root_api._QueryTokenFilter()
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s "%s %s"',
                            ("c", "GET", "/platform/files/1?sig=abc.def&exp=9"), None)
    flt.filter(rec)
    assert "abc.def" not in rec.getMessage() and "sig=<redacted>" in rec.getMessage()


def test_failed_hourly_cleanup_is_retried_on_the_next_sweep(monkeypatch):
    setup_env(monkeypatch)
    from silk_platform import engine_bridge, scheduler, study_runtime
    monkeypatch.setattr(engine_bridge, "sweep_orphans", lambda conn: None)
    monkeypatch.setattr(study_runtime, "supervisor_enabled", lambda: True)
    calls: list = []

    def flaky(name):
        calls.append(name)
        if len(calls) == 1:
            raise RuntimeError("db locked")
    monkeypatch.setattr(scheduler, "run_job", flaky)
    monkeypatch.setattr(scheduler, "time", types.SimpleNamespace(time=lambda: 5_000_000.0,
                                                                  sleep=lambda s: None))
    scheduler.reset_cleanup_slot_for_tests()
    scheduler.sweep_pass()
    scheduler.sweep_pass()
    scheduler.sweep_pass()
    assert calls == ["session_cleanup", "session_cleanup"]   # فشلٌ ثم نجاح، ثم لا تكرار


def test_smoke_tool_treats_hidden_health_fields_as_hidden_not_missing():
    src = _read("tools/post_deploy_smoke.py")
    assert "hidden" in src and '"storage" not in health' in src
