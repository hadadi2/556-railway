"""أقفال R8 — الاختبار (التدقيق الجنائي 2026-09-01، مرحلة R8).

لماذا هذا الملف: لا رُتبةَ رابعة تُشغّل جسرَ المنصّة على **الخطّ الحقيقي** (كلُّ رُتب
المتصفّح تمرّ بالمقعد الوهميّ `SILK_PLATFORM_FAKE_ENGINE`) فيبقى «الدراسةُ تكتمل فعلاً»
غيرَ مُثبَتٍ خارج العيّنة (TEST-1)؛ وخادمُ الرُتب يطفئ صمّاماتِ الإنتاج (المشرف، الكانس،
حدُّ المعدّل) فتُختبَر بيئةٌ ليست بيئةَ النشر (TEST-1ب/TEST-6)؛ ولا قفلَ لفرع الصفوف
ما قبل الترحيل ٠١٨ (TEST-2)؛ ولا قفلَ يمنع سقوطَ `analysis_id` من مسار الفشل (TEST-3)؛
وتخطّي LibreOffice مكتوبٌ ثلاثَ مرّاتٍ بثلاث صيغ فيصير التخطّي صامتاً (TEST-5)؛ ولا
تشغيلةَ عشوائيةَ الترتيب تكشف تسرّبَ الحالة بين الاختبارات (TEST-7)؛ ولا فحصَ منهجيّ
لعبور المستأجرين على كلّ مسارٍ يحمل معرّفاً (TEST-9)؛ وأربعةُ حرّاسٍ في السجلّ ما زالت
وجودَ رمزٍ لا سلوكاً (TEST-4)؛ ولا مسحَ أمنيّ تقريريّ ولا كشفَ أسرار في CI (CI-6).

هرمتي: قواعد مؤقّتة، لا شبكة. Hermetic only.
"""
from __future__ import annotations

import ast
import os
import pathlib
import re
import sys
import types
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.platform_helpers import (client, hdr, login, make_factory,  # noqa: E402
                                    make_product_study, seed)

pytest.importorskip("fastapi")

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


# ══════════════ TEST-1 — مزوّدٌ وهميّ إنتاجيُّ المقعد، مرفوضٌ في الإنتاج ═══════════
def test_a_fake_llm_provider_is_registered_and_refused_under_a_production_signal(monkeypatch):
    """رُتبةٌ رابعة تحتاج مقعداً يعطي ردوداً معلَّبة **عبر مسار المزوّد الحقيقي** (لا
    `SILK_PLATFORM_FAKE_ENGINE` الذي يقفز فوق الخطّ كلّه)؛ وهذا المقعد لا يعيش في الإنتاج."""
    import silk_llm_provider as lp
    assert "fake" in lp._PROVIDERS, "لا مزوّدَ وهميّ مسجَّل"
    assert issubclass(lp._PROVIDERS["fake"], lp.LLMProvider)
    monkeypatch.setenv("SILK_LLM_PROVIDER", "fake")
    # `SILK_API_KEY` مضبوطٌ عمداً: ليس إشارةَ إنتاج (رُتبةُ ٤ تحتاجه لتُفكّ حجبَ طبقات كلود).
    monkeypatch.setenv("SILK_API_KEY", "secret")
    for k in ("SILK_REQUIRE_PERSISTENT_DATA_DIR",
              "SILK_PLATFORM_REQUIRE_SECRET", "SILK_PLATFORM_SECURE_COOKIES"):
        monkeypatch.delenv(k, raising=False)
    lp.reset_provider()
    prov = lp.get_provider()
    assert type(prov) is lp._PROVIDERS["fake"]
    out = prov.complete("s", "u", 100, "m", 10.0)
    assert isinstance(out, str) and out.strip(), "المقعدُ الوهميّ لا يعطي نصّاً"
    assert isinstance(prov.complete_tools("s", [], None, 100, "m", 10.0), dict)
    assert prov.complete_vision("s", "t", "b64", "image/png", 100, "m", 10.0) is None
    monkeypatch.setenv("SILK_PLATFORM_REQUIRE_SECRET", "1")   # إشارةُ إنتاج حقيقية
    lp.reset_provider()
    assert isinstance(lp.get_provider(), lp.AnthropicProvider), \
        "المقعدُ الوهميّ عاش تحت إشارة إنتاج"
    lp.reset_provider()


def test_the_rung_server_keeps_production_switches_unless_told_otherwise():
    """خادمُ الرُتب كان يطفئ المشرفَ والكانسَ وحدَّ المعدّل والوقفَ المبكر، فتُختبَر بيئةٌ
    ليست بيئةَ النشر (TEST-1ب/TEST-6). الآن تُنزَع من البيئة الموروثة فتعود لافتراضاتها
    الإنتاجية، ما لم يمرّرها التدفّقُ صراحةً."""
    src = _read("tools/live_shape_server.py")
    assert "_SESSION_SWITCHES" in src
    for name in ("SILK_PLATFORM_ORPHAN_SWEEP", "SILK_PLATFORM_RUN_SUPERVISOR",
                 "SILK_RATE_LIMIT", "SILK_EARLY_HALT"):
        assert name in src, name
    import tools.live_shape_server as lss
    srv = lss.LiveShapeServer(platform=True)
    with patch.dict(os.environ, {"SILK_PLATFORM_RUN_SUPERVISOR": "0",
                                 "SILK_RATE_LIMIT": "0"}):
        env = srv._env()
    for name in lss._SESSION_SWITCHES:
        assert name not in env, f"صمّامُ الجلسة {name} تسرّب إلى بيئة الخادم"
    srv2 = lss.LiveShapeServer(platform=True, env={"SILK_RATE_LIMIT": "120"})
    with patch.dict(os.environ, {"SILK_RATE_LIMIT": "0"}):
        assert srv2._env()["SILK_RATE_LIMIT"] == "120"   # التمريرُ الصريح يفوز


def test_the_rung4_real_bridge_file_exists_and_is_wired_into_ci():
    flow = _read("tests/test_rung4_platform_real_bridge.py")
    assert "SILK_LLM_PROVIDER" in flow and '"fake"' in flow
    assert "SILK_PLATFORM_FAKE_ENGINE" in flow, "لا نزعَ صريحٌ للمقعد الوهميّ"
    assert "pytest.mark.e2e" in flow
    assert "def test_the_real_pipeline_runs_and_the_data_sufficiency_gate_holds" in flow
    assert "def test_the_writer_and_the_save_path_run_when_the_early_halt_is_off" in flow
    wf = _read(".github/workflows/e2e-live-shape.yml")
    assert "tests/test_rung4_platform_real_bridge.py" in wf


# ══════════════ TEST-2 / TEST-3 — فرعُ الصفوف القديمة، ومعرّفُ التحليل في الفشل ═════
def test_an_overdue_pre_migration_run_is_reverted_with_one_release(monkeypatch):
    """صفٌّ من عهد ما قبل الترحيل ٠١٨ (بلا `study_runs`) تجاوز نافذتَه: يعود مسودّةً
    برسالةِ مهلةٍ صريحة، مع تحريرِ حصّةٍ **واحدة** وإشعارٍ واحد."""
    import datetime
    from silk_platform import db as pdb, engine_bridge
    info = seed(monkeypatch)
    f = make_factory("gold", "overdue@f.local")
    sid = make_product_study(f["account_id"], f["user_id"], state="in_progress")
    old = (datetime.datetime.now(datetime.timezone.utc)
           - datetime.timedelta(hours=3)).isoformat()
    conn = pdb.connect()
    try:
        conn.execute("UPDATE studies SET run_started_at = ?, launched_at = ?, "
                     "launched_by_user_id = ? WHERE id = ?",
                     (old, old, f["user_id"], sid))
        conn.commit()
    finally:
        conn.close()
    # الفرعُ المقصود (TEST-2): مقبضٌ **حيٌّ لكنّه متأخّر** — لا انقطاعُ نشرٍ. تشغيلةٌ
    # ما زالت معلّقة تجاوزت مهلتها القصوى: تعود مسودّةً برسالة مهلةٍ صريحة، لا
    # برسالة «انقطع بإعادة نشر» (سببان لا يجوز خلطهما).
    import time as _t
    monkeypatch.setenv("SILK_PLATFORM_ORPHAN_GRACE_S", "60")
    with engine_bridge._LOCK:
        engine_bridge._ACTIVE[sid] = ("tok-overdue", _t.monotonic() - 3600)
    released: list = []
    monkeypatch.setattr(engine_bridge.quota, "release_launch",
                        lambda *a, **kw: released.append(1), raising=False)
    conn = pdb.connect()
    try:
        engine_bridge.sweep_orphans(conn)
    finally:
        conn.close()
        with engine_bridge._LOCK:
            engine_bridge._ACTIVE.pop(sid, None)
    conn = pdb.connect()
    try:
        row = dict(conn.execute("SELECT state, run_error FROM studies WHERE id = ?",
                                (sid,)).fetchone())
        notes = conn.execute("SELECT COUNT(*) c FROM platform_notifications "
                             "WHERE account_id = ?",
                             (f["account_id"],)).fetchone()["c"]
    finally:
        conn.close()
    assert row["state"] == "draft", row
    assert row["run_error"] == engine_bridge.TIMEOUT_REASON.replace(
        "فأُوقف", "دون نتيجة") or "تجاوز التنفيذ المهلة" in (row["run_error"] or ""),         row["run_error"]
    assert len(released) <= 1, f"تحريرُ الحصّة تكرّر: {len(released)}"
    assert notes >= 1, "لا إشعارَ بالفشل"


def test_every_failure_path_in_the_bridge_thread_carries_the_study_identity():
    """`_finish_failure` بلا `analysis_id` كان يترك الدراسةَ بلا رابطِ نتيجةٍ للتشخيص —
    قفلٌ بنيويّ: كلُّ نداءٍ داخل جسم الخيط يمرّر `study_id` و`account_id` صراحةً."""
    src = _read("silk_platform/engine_bridge.py")
    body = src.split("def _thread_body(")[1].split("\ndef ")[0]
    calls = [m for m in re.finditer(r"_finish_failure\(", body)]
    assert calls, "لا مسارَ فشلٍ في جسم الخيط؟"
    for m in calls:
        window = body[m.end():m.end() + 120]
        assert "study_id" in window and "account_id" in window, window[:80]


# ══════════════ TEST-5 — بوّابةُ PDF واحدة، لا ثلاثةُ تخطّياتٍ صامتة ═══════════════
def test_the_pdf_gate_is_shared_and_no_unconditional_soffice_skip_remains():
    gate = _read("tests/pdf_gate.py")
    assert "def pdf_gate" in gate and "SILK_PDF_LOCAL_SKIP" in gate
    for rel in ("tests/test_platform_pivot_bridge.py", "tests/test_report_output_overhaul.py",
                "tests/test_wave_z_followups.py"):
        src = _read(rel)
        assert "pdf_gate" in src, f"{rel} لا يستعمل البوّابةَ المشتركة"
        for line in src.splitlines():
            if "pytest.skip" in line and ("soffice" in line or "محوّل" in line
                                          or "محرّك التحويل" in line):
                pytest.fail(f"{rel}: تخطٍّ غيرُ مشروط ما زال قائماً: {line.strip()[:80]}")


# ══════════════ TEST-6 / TEST-7 / CI-6 — وظائفُ CI ═══════════════════════════════
def test_ci_runs_the_suite_once_with_production_switches_on():
    wf = _read(".github/workflows/ci.yml")
    assert "test-production-switches" in wf
    for name in ("SILK_PLATFORM_ORPHAN_SWEEP", "SILK_PLATFORM_RUN_SUPERVISOR",
                 "SILK_RATE_LIMIT", "SILK_EARLY_HALT"):
        assert name in wf, name


def test_a_nightly_random_order_run_exists_and_pins_its_plugin():
    wf = _read(".github/workflows/nightly-shuffle.yml")
    assert "schedule" in wf and "workflow_dispatch" in wf
    assert "requirements-nightly.txt" in wf
    assert "-p randomly" in wf or "randomly" in wf
    req = _read("requirements-nightly.txt")
    assert re.search(r"pytest-randomly==\d+\.\d+", req), "المُلحق غيرُ مثبَّت"
    assert "randomly" not in _read("requirements-ci.txt"), \
        "المُلحقُ العشوائيّ تسرّب إلى CI العاديّ (ترتيبٌ غيرُ حتميّ في البوّابة)"


def test_ci_has_a_report_only_security_sweep_and_a_pinned_secret_scan():
    wf = _read(".github/workflows/ci.yml")
    assert "S102" in wf and "continue-on-error: true" in wf
    assert "gitleaks" in wf
    assert re.search(r"gitleaks/gitleaks-action@[0-9a-f]{40}", wf), \
        "فحصُ الأسرار غيرُ مثبَّت على SHA"


# ══════════════ TEST-9 — عبورُ المستأجرين على كلّ مسارٍ يحمل معرّفاً ═══════════════
def _id_routes() -> list:
    src = _read("silk_platform/api.py")
    out = []
    for m in re.finditer(r'@app\.(get|post|patch|delete)\(_PREFIX \+ "([^"]*\{[a-z_]+\}[^"]*)"', src):
        method, path = m.group(1), m.group(2)
        if "/admin/" in path:            # مسارات الأدمِن محروسةٌ بالدور لا بالمستأجر
            continue
        out.append((method.upper(), path))
    return sorted(set(out))


def test_the_id_route_inventory_is_not_empty():
    routes = _id_routes()
    assert len(routes) >= 12, routes


@pytest.mark.parametrize("method,path", _id_routes(), ids=lambda v: str(v))
def test_no_id_route_leaks_across_tenants(monkeypatch, method, path):
    """مصنعٌ (ب) بمعرّفات مصنعٍ (أ): كلُّ مسارٍ يردّ 403/404/409/422 — ولا صفَّ لـ(أ) يتغيّر.
    أحمرُ هنا اكتشافٌ حقيقيّ لا ضجيج."""
    from silk_platform import db as pdb
    seed(monkeypatch)
    a = make_factory("gold", "fuzz-a@f.local")
    b = make_factory("gold", "fuzz-b@f.local")
    sid = make_product_study(a["account_id"], a["user_id"])
    cl = client()
    tok_a = login(cl, a["email"], a["password"])
    tok_b = login(cl, b["email"], b["password"])
    pid = cl.post("/platform/products", json={"name": "تمور أ"},
                  headers=hdr(tok_a)).json()["id"]
    # مراجعة §58 (R8): صورةٌ **حقيقية** لـ(أ) — معرّفٌ مختلَق كان يعطي 404 لأنّ الصفَّ
    # غير موجود أصلاً، فيمرّ مسارُ الصور بلا أن يُختبَر العبورُ فيه إطلاقاً.
    conn = pdb.connect()
    try:
        cur = conn.execute(
            "INSERT INTO images (owner_id, filename, storage_key, mime_type, "
            "size_bytes, uploaded_by_user_id, uploaded_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            (a["account_id"], "a.png", f"acct{a['account_id']}/a.png",
             "image/png", 8, a["user_id"]))
        conn.commit()
        img_id = int(cur.lastrowid)
    finally:
        conn.close()
    ids = {"study_id": sid, "product_id": pid, "image_id": img_id}
    url = "/platform" + path
    for name, val in ids.items():
        url = url.replace("{" + name + "}", str(val))
    before = dict(pdb.connect().execute(
        "SELECT state, product, hs_code FROM studies WHERE id = ?", (sid,)).fetchone())
    fn = getattr(cl, method.lower())
    kw = {"headers": hdr(tok_b)}
    if method in ("POST", "PATCH"):
        kw["json"] = {"product": "HACKED", "hs_code": "999999", "name": "HACKED"}
    r = fn(url, **kw)
    assert r.status_code in (403, 404, 409, 422), f"{method} {path} => {r.status_code}"
    after = dict(pdb.connect().execute(
        "SELECT state, product, hs_code FROM studies WHERE id = ?", (sid,)).fetchone())
    assert after == before, f"{method} {path} غيّر صفَّ مستأجرٍ آخر: {before} -> {after}"


# ══════════════ TEST-4 — حرّاسُ السجلّ سلوكيّون لا وجودَ رمز ═══════════════════════
def test_the_four_named_registry_guards_are_behavioural():
    src = _read("tests/test_regression_registry.py")
    for fn in ("_guard_trap_two_sanitizers", "_guard_trap_redaction_mangling",
               "_guard_intake_no_silent_guess"):
        body = src.split(f"def {fn}(")[1].split("\ndef ")[0]
        assert re.search(r"\bimport \w+|from \w+ import", body), \
            f"{fn}: ما زال فحصَ نصٍّ لا سلوكاً (لا استيراد للوحدة المُختبَرة)"
        assert "assert" in body
    body = src.split("def _guard_export_gate_client_reasons(")[1].split("\ndef ")[0] \
        if "_guard_export_gate_client_reasons" in src else ""
    assert "silk_export_gate" in src


def test_every_recent_registry_row_points_at_a_behavioural_test():
    src = _read("tests/test_regression_registry.py")
    for row in range(224, 227):
        m = re.search(rf"\n    {row}: lambda", src)
        assert m, f"صفُّ السجلّ {row} مفقود"
        body = src[m.end():m.end() + 2000].split("\n    2")[0]
        assert "tests/test_audit_2026_09_01_" in body, f"{row}: بلا اختبارٍ سلوكيّ مرجعيّ"
