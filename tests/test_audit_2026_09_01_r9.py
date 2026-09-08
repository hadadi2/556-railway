"""أقفال R9 — تشغيل Railway (التدقيق الجنائي 2026-09-01، المرحلة ٩).

لماذا هذا الملف: `/health` كان دالّةً متزامنة تفحص القرصَ وتفتح قاعدةَ المنصّة
مع كلّ نداء — فمسبارُ Railway يقف في طابور مجمّع الخيوط خلف أيّ أربعين طلباً
بطيئاً وتُعاد الحاويةُ السليمة (CONC-3/CI-3)؛ ولا سقفَ لحجم الجسم قبل قراءته
(API-8)؛ وتحويلُ PDF عمليةُ LibreOffice بلا سقفِ تزامن ولا قتلٍ لمجموعة العملية
عند المهلة (API-11/EXT-14)؛ واستطلاعُ مكشطة الخرائط `time.sleep` لا يستجيب
للإغلاق (CONC-9/CONC-5)؛ ودليلُ التشغيل بلا تمييزٍ بين مسبار الحياة ومسبار
الجهوزية ولا إيقاعِ نسخٍ إنتاجيّ مسمّى (DB-10).

هرمتي: قواعد مؤقّتة، لا شبكة. Hermetic only.
"""
from __future__ import annotations

import contextlib
import inspect
import os
import pathlib
import sys
import tempfile
import threading
import time
import types
from unittest import mock
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.platform_helpers import (client, hdr, login, make_factory,  # noqa: E402
                                    make_product_study, seed)

pytest.importorskip("fastapi")

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_MIB = 1024 * 1024


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


@contextlib.contextmanager
def _root(**env):
    """تطبيقٌ جذريّ جديد تحت بيئةٍ محدَّدة — قاعدةٌ مؤقّتة، بلا مفاتيح مدفوعة.
    `None` تعني «انزع المتغيّر». الطلباتُ تُرسَل داخل السياق نفسه."""
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    base = {"SILK_DB": db, "SILK_RATE_LIMIT": "0", "SILK_ORPHAN_REAP_INTERVAL_S": "0"}
    unset = ["SILK_API_KEY", "ANTHROPIC_API_KEY", "SILK_DATA_DIR",
             "SILK_REQUIRE_PERSISTENT_DATA_DIR", "SILK_MAX_BODY_BYTES",
             "SILK_TEST_SLOW_ROUTE_S"]
    for k, v in env.items():
        if v is None:
            unset.append(k)
        else:
            base[k] = str(v)
    with patch.dict(os.environ, base):
        for k in unset:
            if k not in env or env[k] is None:
                os.environ.pop(k, None)
        import api as root_api
        from fastapi.testclient import TestClient
        app = root_api.create_app()
        yield TestClient(app), root_api, app


def _route(app, path: str):
    return next(r for r in app.routes if getattr(r, "path", "") == path)


def _pconn():
    from silk_platform import db as pdb
    return pdb.connect()


# ══════════════ CONC-3 / CI-3 — `/health` لقطةٌ من حلقة الحدث، و`/ready` مسبارٌ طازج ═══
def test_health_is_async_and_probes_nothing_per_request():
    """`/health` كان يفحص القرص (`persistence_status`) ويفتح قاعدةَ المنصّة مع كلّ
    نداء على خيطٍ من المجمّع — مسبارُ Railway يقف في الطابور. الآن دالّةٌ غير
    متزامنة تقرأ لقطةً حُسبت عند الإقلاع."""
    with _root() as (cl, root_api, app):
        assert inspect.iscoroutinefunction(_route(app, "/health").endpoint)
        import silk_storage
        calls = {"disk": 0, "db": 0}

        def boom_disk():
            calls["disk"] += 1
            raise AssertionError("disk probe per request")

        def boom_db():
            calls["db"] += 1
            raise AssertionError("platform DB per request")
        with patch.object(silk_storage, "persistence_status", boom_disk), \
                patch.object(root_api, "_platform_readiness", boom_db):
            r = cl.get("/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert calls == {"disk": 0, "db": 0}
        assert "is_mount" in body["storage"] and "platform_ready" in body["storage"]
        assert isinstance(body["probe_age_s"], (int, float)) and body["probe_age_s"] >= 0


def test_health_snapshot_refreshes_from_the_research_runtime_tick():
    """اللقطةُ لا تجمد: دورةُ `silk_research_runtime.tick()` (الحاصدُ الدوريّ، R2b)
    تعيد الفحصَ البطيء فتتبع `/health` حالةَ القرص الفعلية بلا فحصٍ لكلّ طلب."""
    with _root() as (cl, root_api, app):
        import silk_research_runtime
        import silk_storage
        before = cl.get("/health").json()["storage"]["is_mount"]
        fake = dict(silk_storage.persistence_status())
        fake["is_mount"] = not before
        with patch.object(silk_storage, "persistence_status", lambda: fake):
            assert cl.get("/health").json()["storage"]["is_mount"] == before   # لقطة
            silk_research_runtime.tick()
            assert cl.get("/health").json()["storage"]["is_mount"] == (not before)


def test_health_env_only_fields_stay_live_after_the_snapshot():
    """ما يُقرأ من البيئة وحدها (المفاتيح، الجهوزية) يبقى حيّاً — اللقطةُ للقرص
    والقاعدة والاستيراد فقط (عقد `test_wave7_live_incident_fixes`)."""
    with _root() as (cl, root_api, app):
        first = cl.get("/health").json()
        assert first["research_ready"] is False
        assert "غير مضبوط" in first["research_ready_reason"]
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
            second = cl.get("/health").json()
        assert second["research_ready"] is False
        assert "SILK_API_KEY" in second["research_ready_reason"]


def test_health_field_contract_is_preserved_in_dev_mode():
    """الحقولُ التي تعتمدها الاختباراتُ والأدواتُ (وضعُ التطوير، بلا مفتاح) كلُّها باقية،
    ويُضاف `probe_age_s` (عمرُ اللقطة بالثواني)."""
    with _root() as (cl, root_api, app):
        body = cl.get("/health").json()
        for k in ("status", "deps", "sources", "research_ready", "hs_classifier",
                  "storage", "version", "ai_model", "probe_age_s"):
            assert k in body, k
        for k in ("data_dir", "analyses_db", "fact_store_db", "usage_db", "cache_dir",
                  "platform_db", "platform_ready", "persist_guard", "is_mount",
                  "writable", "mountpoint"):
            assert k in body["storage"], k
        assert body["status"] == "ok"


def test_health_is_503_when_the_persist_guard_is_on_and_the_snapshot_says_ephemeral():
    """مع `SILK_REQUIRE_PERSISTENT_DATA_DIR=1` وقرصٍ لم يعد مركَّباً بعد الإقلاع —
    503 صريح (Railway يعيد الحاوية فتفشل مصيدةُ الإقلاع بصوتٍ عالٍ) لا 200 صامت."""
    tmp = tempfile.mkdtemp()
    with patch("os.path.ismount", return_value=True):
        with _root(SILK_DATA_DIR=tmp, SILK_REQUIRE_PERSISTENT_DATA_DIR="1") as (
                cl, root_api, app):
            ok = cl.get("/health")
            assert ok.status_code == 200, ok.text
            assert ok.json()["storage"]["persist_guard"] is True
            with patch("os.path.ismount", return_value=False):
                root_api.refresh_health_snapshot(app)
            r = cl.get("/health")
            assert r.status_code == 503, r.text
            body = r.json()
            assert body["status"] != "ok"
            assert body["storage"]["is_mount"] is False
            assert body["storage"]["persist_guard"] is True


def test_ready_runs_a_fresh_probe_is_rate_limited_and_503s_on_misconfig():
    """`GET /ready` مسبارُ الجهوزية العميق: يفحص القرصَ والقاعدةَ فعلاً في كلّ نداء
    (وليس مسارَ Railway)، مخنوقٌ بـ`_rate_limit`، و503 على سوء التهيئة."""
    with _root(SILK_RATE_LIMIT="2", SILK_RATE_WINDOW="60") as (cl, root_api, app):
        import silk_storage
        calls = {"n": 0}
        real = silk_storage.persistence_status

        def spy():
            calls["n"] += 1
            return real()
        # الساعةُ مُجمَّدة **لكلّ** النداءات: نافذةُ الحدّ دقيقةٌ كاملة ومفتاحُها
        # `int(time())//60`، فنداءٌ أوّلُ على النافذة الحقيقية ثم البقيةُ على نافذةٍ
        # مجمَّدة كان يعيد العدّادَ إلى الصفر في المنتصف (رُصد على الحزمة الكاملة).
        with mock.patch.object(root_api, "time",
                               types.SimpleNamespace(time=lambda: 1_000_000.0,
                                                     monotonic=time.monotonic,
                                                     sleep=time.sleep)):
            with patch.object(silk_storage, "persistence_status", spy):
                r = cl.get("/ready")
            assert r.status_code == 200, r.text
            assert calls["n"] == 1
            assert r.json()["probe_age_s"] < 1
            assert cl.get("/ready").status_code == 200
            assert cl.get("/ready").status_code == 429      # الحدُّ يسري على المسبار العميق
            assert cl.get("/health").status_code == 200     # مسبارُ Railway بلا حدّ (قرار R7)
    tmp = tempfile.mkdtemp()
    with patch("os.path.ismount", return_value=True):
        with _root(SILK_DATA_DIR=tmp, SILK_REQUIRE_PERSISTENT_DATA_DIR="1") as (
                cl, root_api, app):
            with patch("os.path.ismount", return_value=False):
                r = cl.get("/ready")
            assert r.status_code == 503, r.text
            assert r.json()["storage"]["is_mount"] is False


def test_slow_test_route_is_absent_by_default_and_refused_under_a_prod_signal():
    """مسارُ الإشباع `GET /_test/slow` لا يوجد إلا بـ`SILK_TEST_SLOW_ROUTE_S`، وهو
    متزامنٌ عمداً (يشغل خيطاً من المجمّع)، وحارسُ الإقلاع يرفضه مع أيّ إشارة إنتاج."""
    with _root() as (cl, root_api, app):
        assert cl.get("/_test/slow").status_code == 404
    with _root(SILK_TEST_SLOW_ROUTE_S="0.01") as (cl, root_api, app):
        r = cl.get("/_test/slow")
        assert r.status_code == 200, r.text
        assert r.json()["slept_s"] == 0.01
        assert not inspect.iscoroutinefunction(_route(app, "/_test/slow").endpoint)
    from silk_platform import api as papi
    with patch.dict(os.environ, {"SILK_PLATFORM_SECURE_COOKIES": "1",
                                 "SILK_PLATFORM_SECRET": "s" * 40,
                                 "SILK_PLATFORM_BCRYPT_ROUNDS": "12",
                                 "SILK_TEST_SLOW_ROUTE_S": "1"}):
        for k in ("SILK_PLATFORM_EXPOSE_RESET_TOKEN", "SILK_PLATFORM_FAKE_ENGINE"):
            os.environ.pop(k, None)
        with pytest.raises(RuntimeError, match="SILK_TEST_SLOW_ROUTE_S"):
            papi.boot_config_guard()


# ══════════════ API-8 — سقفُ حجم الجسم قبل قراءته ═══════════════════════════════
def test_body_limit_default_is_20_mib_and_env_overrides():
    import api as root_api
    with patch.dict(os.environ, {}):
        os.environ.pop("SILK_MAX_BODY_BYTES", None)
        assert root_api._body_limit_bytes() == 20 * _MIB
    with patch.dict(os.environ, {"SILK_MAX_BODY_BYTES": "1024"}):
        assert root_api._body_limit_bytes() == 1024
    with patch.dict(os.environ, {"SILK_MAX_BODY_BYTES": "junk"}):
        assert root_api._body_limit_bytes() == 20 * _MIB


def test_oversized_bodies_are_413_before_any_handler_runs():
    """`Content-Length` فوق السقف ⇒ 413 قبل قراءة بايتٍ واحد؛ جسمٌ مقطَّع (بلا حجمٍ
    معلَن) يُعَدّ عند الاستقبال ويُقطع عند السقف — على المسار الجذري والمنصّة معاً."""
    with _root(SILK_MAX_BODY_BYTES="1024") as (cl, root_api, app):
        big = b"x" * 2048
        r = cl.post("/platform/auth/login", content=big,
                    headers={"Content-Type": "application/json"})
        assert r.status_code == 413, r.text
        assert r.json()["detail"]["error"] == "body_too_large"
        assert r.json()["detail"]["max_bytes"] == 1024
        r = cl.post("/markets", content=big, headers={"Content-Type": "application/json"})
        assert r.status_code == 413, r.text

        def gen():
            for _ in range(4):
                yield b"y" * 512
        r = cl.post("/platform/auth/login", content=gen(),
                    headers={"Content-Type": "application/json"})
        assert r.status_code == 413, r.text
        assert r.json()["detail"]["error"] == "body_too_large"
        # الجسمُ الصغير يبلغ معالجَه (رفضٌ بمنطقه هو، لا 413)
        r = cl.post("/platform/auth/login", json={"email": "a@b.c", "password": "x"})
        assert r.status_code in (401, 422), r.text


# ══════════════ API-11 / EXT-14 — سقفُ تزامن LibreOffice وقتلُ مجموعة العملية ═══════
def _docx(tmp_path) -> str:
    from docx import Document
    p = os.path.join(str(tmp_path), "x.docx")
    Document().save(p)
    return p


def test_pdf_conversion_is_bounded_and_busy_is_a_named_error(monkeypatch, tmp_path):
    """فتحاتُ التحويل محدودة (`SILK_PDF_MAX_CONCURRENT`، ٢): الطلبُ الزائد لا ينتظر
    بلا سقف ولا يفرّع soffice — يرفع `PdfBusy` (صنفٌ مسمّى تحت RuntimeError)."""
    import subprocess
    import silk_reports
    assert issubclass(silk_reports.PdfBusy, RuntimeError)
    monkeypatch.setenv("SILK_PDF_MAX_CONCURRENT", "1")
    monkeypatch.setenv("SILK_PDF_WAIT_S", "0")
    monkeypatch.setattr(silk_reports, "_find_soffice", lambda: "/fake/soffice")
    popen = mock.Mock(side_effect=AssertionError("soffice must not start while busy"))
    monkeypatch.setattr(subprocess, "Popen", popen)
    docx = _docx(tmp_path)
    slots = silk_reports._pdf_slots()
    assert slots.acquire(timeout=0)
    try:
        t0 = time.monotonic()
        with pytest.raises(silk_reports.PdfBusy):
            silk_reports.docx_to_pdf(docx, os.path.join(str(tmp_path), "x.pdf"))
        assert time.monotonic() - t0 < 2
    finally:
        slots.release()
    popen.assert_not_called()
    assert silk_reports._pdf_slots() is slots          # السقفُ لم يتغيّر ⇒ الكائنُ نفسه


def test_pdf_timeout_kills_the_whole_process_group_and_frees_the_slot(monkeypatch, tmp_path):
    """`subprocess.run(timeout=)` كان يقتل soffice وحده ويترك أبناءه — الآن مجموعةُ
    عملية جديدة (`start_new_session`) تُقتل كاملةً عند المهلة، والفتحةُ تعود."""
    import subprocess
    import silk_reports
    monkeypatch.delenv("SILK_PDF_MAX_CONCURRENT", raising=False)
    monkeypatch.setattr(silk_reports, "_find_soffice", lambda: "/fake/soffice")
    fake = mock.MagicMock()
    fake.pid = 4242
    fake.returncode = None
    fake.__enter__.return_value = fake          # مراجعة R9: `with Popen(...) as proc`
    fake.__exit__.return_value = False
    fake.communicate.side_effect = [subprocess.TimeoutExpired(cmd="soffice", timeout=1),
                                    (b"", b"")]
    popen = mock.Mock(return_value=fake)
    monkeypatch.setattr(subprocess, "Popen", popen)
    killed: dict = {}
    if os.name != "nt":
        monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed.update(pgid=pgid, sig=sig))
    docx = _docx(tmp_path)
    with pytest.raises(RuntimeError) as ei:
        silk_reports.docx_to_pdf(docx, os.path.join(str(tmp_path), "x.pdf"), timeout=1)
    assert str(ei.value) == silk_reports._PDF_FAILED
    assert not isinstance(ei.value, silk_reports.PdfBusy)
    kwargs = popen.call_args.kwargs
    assert kwargs.get("start_new_session") is True
    if os.name != "nt":
        assert killed.get("pgid") == 4242
    else:
        fake.kill.assert_called()
    slots = silk_reports._pdf_slots()
    assert slots.acquire(timeout=0)                       # الفتحةُ أُعيدت بعد الفشل
    slots.release()


def test_root_report_pdf_maps_pdfbusy_to_503_pdf_busy_with_retry_after(monkeypatch):
    with _root(SILK_API_KEY="secret") as (cl, root_api, app):
        import silk_render
        import silk_reports
        import silk_storage
        monkeypatch.setattr(silk_storage, "get_analysis", lambda aid, path=None: {"id": aid})
        monkeypatch.setattr(silk_render, "build_view", lambda found: {})

        def busy(view, out):
            raise silk_reports.PdfBusy("مشغول")
        monkeypatch.setattr(silk_reports, "render_research_pdf", busy)
        r = cl.get("/analyses/7/report.pdf", headers={"X-API-Key": "secret"})
        assert r.status_code == 503, r.text
        assert r.json()["detail"]["error"] == "pdf_busy"
        assert int(r.headers.get("Retry-After") or 0) > 0


def test_platform_report_pdf_maps_pdfbusy_to_503_pdf_busy_with_retry_after(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "pdfbusy@f.local")
    sid = make_product_study(f["account_id"], f["user_id"], state="completed")
    conn = _pconn()
    try:
        conn.execute("UPDATE studies SET analysis_id = ? WHERE id = ?", (777, sid))
        conn.commit()
    finally:
        conn.close()
    import silk_render
    import silk_reports
    import silk_storage
    # عرضٌ أدنى يعبر بوّابةَ التسليم (نمطُ `test_platform_pivot_bridge`) — القفلُ على
    # ترجمة `PdfBusy` لا على محتوى التقرير.
    monkeypatch.setattr(silk_storage, "get_analysis",
                        lambda i, path=None: {"id": i, "product": "تمور"})
    monkeypatch.setattr(silk_render, "build_view",
                        lambda found, lang="ar": {"brief": ["التوصية: صالح للمضي"],
                                                  "markets": []})

    def busy(view, out):
        raise silk_reports.PdfBusy("مشغول")
    monkeypatch.setattr(silk_reports, "render_research_pdf", busy)
    cl = client()
    tok = login(cl, f["email"], f["password"])
    r = cl.get(f"/platform/studies/{sid}/report.pdf", headers=hdr(tok))
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "pdf_busy"
    assert int(r.headers.get("Retry-After") or 0) > 0


# ══════════════ CONC-9 / CONC-5 — استطلاعُ الخرائط يستجيب للإغلاق ═══════════════
def test_gmaps_poll_worker_exits_promptly_on_stop_all(monkeypatch):
    """`poll_leads` كان ينام `time.sleep(10)` بين الاستطلاعات — خيطُ العامل لا يرى
    الإغلاق قبل انقضاء نومه. الآن حدثٌ (`_STOP.wait`) يوقظه فوراً."""
    import silk_gmaps
    monkeypatch.setattr(silk_gmaps, "_fetch_job", lambda jid: ("running", None))
    monkeypatch.setattr(silk_gmaps, "_POLL_INTERVAL_S", 30)
    out: dict = {}

    def run():
        out["r"] = silk_gmaps.poll_leads("job-1", time.monotonic() + 120)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(0.2)
    try:
        silk_gmaps.stop_all()
        t.join(3)
        assert not t.is_alive(), "worker still sleeping after stop_all()"
        assert out.get("r") is None
    finally:
        stop = getattr(silk_gmaps, "_STOP", None)
        if stop is not None:
            stop.clear()


def test_research_runtime_shutdown_stops_gmaps_pollers(monkeypatch):
    import silk_gmaps
    import silk_research_runtime
    called: list = []
    monkeypatch.setattr(silk_gmaps, "stop_all", lambda: called.append(1), raising=False)
    silk_research_runtime.shutdown()
    assert called, "shutdown() must stop the gmaps pollers too"


# ══════════════ DB-10 / CI-2 — الوثائق والصمّامات ════════════════════════════════
def test_ops_docs_name_the_probe_split_the_backup_cadence_and_the_r9_valves():
    deploy = _read("docs/DEPLOY_RAILWAY.md")
    assert "/ready" in deploy and "probe_age_s" in deploy
    assert "verify_backup.py" in deploy and "platform_files" in deploy
    env = _read(".env.example")
    assert "SILK_BACKUP_HOURS=24" in env
    for k in ("SILK_MAX_BODY_BYTES", "SILK_PDF_MAX_CONCURRENT", "SILK_PDF_WAIT_S",
              "SILK_TEST_SLOW_ROUTE_S"):
        assert k in env, k
    owner = _read("docs/OWNER_NEXT_STEPS.md")
    assert "SILK_BACKUP_HOURS=24" in owner and "/ready" in owner
    decisions = _read("docs/DEEP_RESEARCH_DECISIONS.md")
    assert "CI-2/SEC-5" in decisions and "Custom Start Command" in decisions


# ══════════════ مراجعة R9 (/code-review high) — اكتشافاتٌ أُقفلت أحمر أوّلاً ════════════
def test_boot_snapshot_is_taken_after_the_platform_mount_so_seeding_is_visible(monkeypatch):
    """اللقطةُ الأولى كانت تُحسَب قبل تركيب المنصّة وبذرها — `/health` يقول «بلا
    مستخدمين» بعد كلّ نشرةٍ طازجة حتى أوّل دورة حاصد، فيظنّ المالكُ أنّ البذرَ فشل."""
    from tests.platform_helpers import setup_env
    setup_env(monkeypatch)
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "Seed-Admin-Pass-2026!")
    monkeypatch.setenv("SILK_ORPHAN_REAP_INTERVAL_S", "0")
    for k in ("SILK_API_KEY", "ANTHROPIC_API_KEY", "SILK_REQUIRE_PERSISTENT_DATA_DIR",
              "SILK_TEST_SLOW_ROUTE_S"):
        monkeypatch.delenv(k, raising=False)
    import api as root_api
    from fastapi.testclient import TestClient
    cl = TestClient(root_api.create_app())
    ready = cl.get("/health").json()["storage"]["platform_ready"]
    assert ready and int(ready.get("users") or 0) >= 1, ready


def test_slow_route_is_refused_under_root_production_signals_and_bad_values():
    """حارسُ المنصّة وحده لا يغطّي بيئةَ Railway الموثَّقة (مفتاحُ API + مصيدةُ القرص بلا
    إشارتَي المنصّة) — الرفضُ عند التعريف على إشارات الجذر، والقيمةُ تُفحَص عند الإقلاع."""
    for env in ({"SILK_API_KEY": "secret"}, {"SILK_REQUIRE_PERSISTENT_DATA_DIR": "1"},
                {"SILK_PLATFORM_SECURE_COOKIES": "1", "SILK_PLATFORM_SECRET": "s" * 40,
                 "SILK_PLATFORM_BCRYPT_ROUNDS": "12"}):
        with pytest.raises(RuntimeError, match="SILK_TEST_SLOW_ROUTE_S"):
            with patch("os.path.ismount", return_value=True), \
                    _root(SILK_TEST_SLOW_ROUTE_S="1", SILK_DATA_DIR=tempfile.mkdtemp(), **env):
                pass
    with pytest.raises(RuntimeError, match="SILK_TEST_SLOW_ROUTE_S"):
        with _root(SILK_TEST_SLOW_ROUTE_S="4s"):
            pass


def test_stale_health_snapshot_refreshes_on_read_without_the_reaper():
    """`SILK_ORPHAN_REAP_INTERVAL_S=0` (موثَّق «مطفأ») كان يجمّد اللقطةَ إلى الأبد — الآن
    قراءةٌ تجد اللقطةَ أقدمَ من عمرها الأقصى تطلق تجديداً خلفياً على خيطٍ مستقلّ."""
    with _root() as (cl, root_api, app):
        import silk_storage
        before = cl.get("/health").json()["storage"]["is_mount"]
        fake = dict(silk_storage.persistence_status())
        fake["is_mount"] = not before
        with patch.object(silk_storage, "persistence_status", lambda: fake):
            app.state.health_snapshot["at"] -= 10_000          # لقطةٌ عتيقة
            first = cl.get("/health")
            assert first.status_code == 200                     # لا انتظارَ على القرص
            for _ in range(200):
                if getattr(app.state, "health_refresh_started", None) is None \
                        and cl.get("/health").json()["storage"]["is_mount"] == (not before):
                    break
                time.sleep(0.02)
            assert cl.get("/health").json()["storage"]["is_mount"] == (not before)


def test_hung_health_probe_degrades_liveness():
    """فحصٌ معلَّق (قرصٌ متجمّد) كان يترك اللقطةَ «سليمة» إلى الأبد — تجديدٌ لا ينتهي في
    مهلته يُنزل الحالةَ إلى degraded/503 فتعيد Railway الحاويةَ."""
    with _root() as (cl, root_api, app):
        import silk_storage
        gate = threading.Event()

        def blocking():
            gate.wait(30)
            return {"configured": False, "is_mount": False, "writable": False,
                    "mountpoint": None, "path": None}
        try:
            with patch.object(silk_storage, "persistence_status", blocking):
                app.state.health_snapshot["at"] -= 10_000
                assert cl.get("/health").status_code == 200        # أطلق التجديد المعلَّق
                for _ in range(100):
                    if getattr(app.state, "health_refresh_started", None) is not None:
                        break
                    time.sleep(0.01)
                assert getattr(app.state, "health_refresh_started", None) is not None
                app.state.health_refresh_started -= 10_000         # «معلَّقٌ» منذ زمن
                r = cl.get("/health")
                assert r.status_code == 503, r.text
                assert r.json()["status"] == "degraded"
        finally:
            gate.set()
            time.sleep(0.05)


def test_storage_alarm_reason_is_gated_on_the_verbose_key():
    """سببُ الإنذار تشخيصٌ للمشغّل (R7/AUTH-18): 503 يبقى عامّاً لـRailway، والنصُّ
    للمفتاح الصالح وحده."""
    tmp = tempfile.mkdtemp()
    with patch("os.path.ismount", return_value=True):
        with _root(SILK_DATA_DIR=tmp, SILK_REQUIRE_PERSISTENT_DATA_DIR="1",
                   SILK_API_KEY="secret") as (cl, root_api, app):
            with patch("os.path.ismount", return_value=False):
                root_api.refresh_health_snapshot(app)
            anon = cl.get("/health")
            assert anon.status_code == 503
            assert anon.json()["status"] == "degraded"
            assert "storage_alarm" not in anon.json() and "storage" not in anon.json()
            keyed = cl.get("/health", headers={"X-API-Key": "secret"})
            assert keyed.status_code == 503 and "storage_alarm" in keyed.json()


def test_health_apps_are_tracked_without_a_closure_cycle():
    """`app.state.health_refresh` كان إغلاقاً يحمل `app` (دورةُ مراجع) فتبقى تطبيقاتُ
    الاختبارات في المجموعة حتى GC الدوري ويجدّدها الحاصدُ تحت بيئةٍ غريبة."""
    import gc
    import api as root_api
    with _root() as (cl, root_api, app):
        assert not hasattr(app.state, "health_refresh")
        assert app in root_api._HEALTH_APPS
        n_with = len(root_api._HEALTH_APPS)
    del cl, app
    gc.collect()
    assert len(root_api._HEALTH_APPS) <= n_with - 1


def test_body_limit_is_outermost_and_rejects_before_auth_touches_the_db(monkeypatch):
    """`add_middleware` يدرج في المقدّمة: وسيطُ الحدّ كان داخل `_load_auth` فيُقرأ الكوكي
    وتُفتح القاعدةُ لكلّ طلبٍ زائد قبل 413."""
    with _root(SILK_MAX_BODY_BYTES="1024") as (cl, root_api, app):
        from silk_platform import api as papi
        opened: list = []
        real_open = papi._open

        def spy():
            opened.append(1)
            return real_open()
        monkeypatch.setattr(papi, "_open", spy)
        r = cl.post("/platform/auth/login", content=b"x" * 2048,
                    headers={"Content-Type": "application/json",
                             "Cookie": f"{papi.COOKIE_NAME}=not-a-real-session"})
        assert r.status_code == 413, r.text
        assert not opened, "قاعدةُ الجلسات فُتحت قبل رفض الحجم"
        stack = []
        m = app.middleware_stack if hasattr(app, "middleware_stack") else None
        _ = cl.get("/health")                     # يبني المكدّس
        m = app.middleware_stack
        while m is not None and hasattr(m, "app"):
            stack.append(type(m).__name__)
            m = m.app
        assert stack.index("_BodyLimitMiddleware") == stack.index("ServerErrorMiddleware") + 1, stack


def test_pdf_slot_is_held_only_around_the_soffice_process(monkeypatch, tmp_path):
    """الفتحةُ كانت محجوزةً عبر الجسم كلّه (نسخةٌ بلا حركات، تطبيعُ طبقة النصّ، فحصُ
    الأقواس) فيُرفَض ثالثٌ `pdf_busy` بلا عمليةِ soffice واحدة حيّة."""
    import silk_reports
    import silk_pdf_textlayer
    monkeypatch.setenv("SILK_PDF_MAX_CONCURRENT", "1")
    monkeypatch.setattr(silk_reports, "_find_soffice", lambda: "/fake/soffice")
    seen: dict = {}

    def fake_run(cmd, **kw):
        out_dir = cmd[cmd.index("--outdir") + 1]
        pathlib.Path(out_dir, pathlib.Path(cmd[-1]).stem + ".pdf").write_bytes(b"%PDF-1.4")
        seen["slot_during_soffice"] = silk_reports._pdf_slots()._value
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    def spy_normalize(path):
        seen["slot_during_normalize"] = silk_reports._pdf_slots()._value
        return False
    monkeypatch.setattr(silk_reports, "_run_soffice", fake_run)
    monkeypatch.setattr(silk_pdf_textlayer, "normalize_arabic_text_layer", spy_normalize)
    silk_reports.docx_to_pdf(_docx(tmp_path), os.path.join(str(tmp_path), "x.pdf"))
    assert seen["slot_during_soffice"] == 0            # محجوزة حول العملية
    assert seen["slot_during_normalize"] == 1          # حرّة أثناء المعالجة اللاحقة


def test_run_soffice_kills_the_group_on_any_failure(monkeypatch, tmp_path):
    """`subprocess.run` كان يقتل الطفلَ على أيّ استثناء؛ `_run_soffice` كان يقتل على
    المهلة وحدها — OSError أثناء القراءة كان يترك soffice وأنابيبَه أحياءً."""
    import subprocess
    import silk_reports
    monkeypatch.setattr(silk_reports, "_find_soffice", lambda: "/fake/soffice")
    fake = mock.MagicMock()
    fake.pid = 4343
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    fake.communicate.side_effect = OSError("pipe broke")
    monkeypatch.setattr(subprocess, "Popen", mock.Mock(return_value=fake))
    killed: dict = {}
    if os.name != "nt":
        monkeypatch.setattr(os, "killpg", lambda pgid, sig: killed.update(pgid=pgid))
    with pytest.raises(RuntimeError) as ei:
        silk_reports.docx_to_pdf(_docx(tmp_path), os.path.join(str(tmp_path), "x.pdf"))
    assert str(ei.value) == silk_reports._PDF_FAILED
    if os.name != "nt":
        assert killed.get("pgid") == 4343
    else:
        fake.kill.assert_called()
    fake.wait.assert_called()


def test_persistence_rule_and_pdf_busy_detail_have_one_home_each():
    """قاعدةُ مصيدة القرص كانت مكرّرةً (حارسُ الإقلاع و`_storage_alarm`) وتحليلُ البيئة
    الصادق أربعَ مرّات؛ وجسمُ `pdf_busy` مكرّرٌ بثلاث صياغات."""
    storage = _read("silk_storage.py")
    assert "def persistence_violation" in storage
    api_src = _read("api.py")
    assert api_src.count("silk_storage.persistence_violation(") >= 2
    assert api_src.count('"SILK_REQUIRE_PERSISTENT_DATA_DIR", "").strip().lower()') <= 1
    assert "def _truthy_env" in api_src and "def _persist_guard_on" in api_src
    assert "pdf_busy_detail()" in api_src
    assert "pdf_busy_detail()" in _read("silk_platform/api.py")
    assert _read("silk_reports.py").count('"error": "pdf_busy"') == 1
    assert '"error": "pdf_busy"' not in api_src
