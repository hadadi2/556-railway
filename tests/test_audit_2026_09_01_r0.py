"""أقفال R0 — الخطّ الأساس وصمّامات الأمان (التدقيق الجنائي 2026-09-01، المرحلة ٠).

لماذا هذا الملف: التدقيق وجد أن CI لا يمارس ما يمارسه النشر — لا فحص للأسماء
غير المعرَّفة ولا تدقيق للاعتماديات (CI-1)، ولا بناء للصورة ولا ضربة `/health`
داخل الحاوية (CI-4)، وفحص الدخان بعد النشر لا يدخل بوّابة المصانع أصلاً (CI-6)،
و`railway.json` يكرّر أمر التشغيل فيغلب `CMD` الصورة صامتاً — ومعه يُتجاهَل
`SILK_FORWARDED_ALLOW_IPS` الذي تقرؤه الصورة (CI-2). كل قفل هنا نصّي/هيكلي
عمداً: R0 أدواتٌ لا شيفرة تطبيق، فحارسُه يقرأ الملفات التي يقرؤها النشر.

Locks for roadmap phase R0: CI runs the undefined-name + dependency-audit
gates, the e2e job builds the real image and hits /health inside it, the
post-deploy smoke has an opt-in read-only platform lane, and the image CMD is
the single start command. Hermetic: file reads + one `--help` subprocess.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SMOKE = _ROOT / "tools" / "post_deploy_smoke.py"


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _smoke_module():
    """حمّل السكربت وحدةً (لا `main`) — argparse + الفحوص قابلة للنداء المباشر."""
    spec = importlib.util.spec_from_file_location("_post_deploy_smoke", _SMOKE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── CI-1: بوّابة الأسماء غير المعرَّفة + تدقيق الاعتماديات ────────────────────
def test_ci_runs_the_undefined_name_and_dependency_audit_gates():
    """`ci.yml` يشغّل `ruff` (E9,F63,F7,F82 حصراً — لا أسلوب) و`pip-audit` **قبل**
    الحزمة الهرمتية، والأداتان مثبّتتان في `requirements-ci.txt` وحده — لا تصلان
    الإنتاج (`requirements.txt`/`Dockerfile`) ولا ملفَّ ضبطٍ لمدقّق أسلوب."""
    ci = _read(".github/workflows/ci.yml")
    assert "ruff check --select E9,F63,F7,F82" in ci, "بوّابة ruff غائبة عن ci.yml"
    assert "pip-audit" in ci, "تدقيق الاعتماديات غائب عن ci.yml"
    assert ci.index("ruff check") < ci.index("python -m pytest tests/ -q"), (
        "البوّابة السريعة يجب أن تسبق الحزمة الهرمتية (فشلٌ مبكّر)")
    reqs = _read("requirements-ci.txt")
    assert re.search(r"^ruff==\d", reqs, re.M), "ruff غير مثبَّت الإصدار في requirements-ci.txt"
    assert re.search(r"^pip-audit==\d", reqs, re.M), "pip-audit غير مثبَّت الإصدار"
    for rel in ("requirements.txt", "Dockerfile"):
        src = _read(rel)
        assert not re.search(r"\bruff\b", src) and "pip-audit" not in src, (
            f"{rel}: أداة CI تسرّبت إلى الإنتاج")
    for cfg in ("ruff.toml", ".ruff.toml"):
        assert not (_ROOT / cfg).exists(), f"{cfg}: لا مدقّق أسلوب في هذا الريبو (CLAUDE.md)"


# ── CI-4: الصورة تُبنى وتُقلِع و/health يُضرَب داخلها ─────────────────────────
def test_e2e_workflow_builds_the_deploy_image_and_hits_health_inside_it():
    """وظيفة `e2e-live-shape` تبني الصورة كما يبنيها Railway، تشغّلها، وتضرب
    `/health` داخل الحاوية — بلا أسرار (لا يجوز أن يحتاج البناء مفتاحاً)."""
    e2e = _read(".github/workflows/e2e-live-shape.yml")
    assert "docker build" in e2e and "docker run" in e2e, "لا خطوة بناء/تشغيل للصورة"
    assert "/health" in e2e, "الحاوية لا تُضرَب على /health"
    m = re.search(r"^  docker-health:\n(.*?)(?=^  \S|\Z)", e2e, re.M | re.S)
    assert m, "وظيفة docker-health المستقلة غائبة"
    assert "secrets." not in m.group(1), "خطوة الصورة يجب ألا تحتاج أسراراً"
    assert "docker logs" in m.group(1), "عند الفشل تُطبَع سجلّات الحاوية لا الصمت"


# ── CI-2: أمر تشغيلٍ واحد — CMD الصورة، وrailway.json مرآته ────────────────────
def test_railway_start_command_matches_the_image_cmd_byte_for_byte():
    """`railway.json.startCommand` مرآةُ `CMD` الصورة **بايتاً ببايت** — كان يثبّت
    `--forwarded-allow-ips=*` حرفياً فيتجاهل `SILK_FORWARDED_ALLOW_IPS` الذي تقرؤه
    الصورة. لم يُحذَف (هدف التدقيق الأصلي) لأن حقل Custom Start Command في لوحة
    Railway — الإنتاج والتجهيز معاً — ما زال يحمل أمراً بلا أعلامٍ يغلب `CMD` فور
    غياب الملفّ (قُرئ 2026-09-02): تفريغُه قرار مالك، وبعده يُحذَف الحقل هنا ويُقلب
    هذا القفل إلى «بلا startCommand». الأعلام الثلاثة تعيش في الصورة."""
    cmd_lines = [ln for ln in _read("Dockerfile").splitlines() if ln.startswith("CMD ")]
    assert len(cmd_lines) == 1, "سطر CMD واحد بالضبط في Dockerfile"
    parts = json.loads(cmd_lines[0][len("CMD "):])
    assert parts[:2] == ["sh", "-c"], parts
    data = json.loads(_read("railway.json"))
    deploy = data.get("deploy") or {}
    assert deploy.get("healthcheckPath") == "/health"
    m = re.fullmatch(r"sh -c '(.*)'", deploy.get("startCommand") or "")
    assert m, "railway.json.startCommand ليس بصيغة `sh -c '…'` — لا يُقارَن"
    assert m.group(1) == parts[2], (
        "أمر railway.json انحرف عن CMD الصورة:\n"
        f"  railway : {m.group(1)}\n  docker  : {parts[2]}")
    for flag in ("uvicorn api:app", "--proxy-headers", "--forwarded-allow-ips",
                 "--timeout-graceful-shutdown 15", "SILK_FORWARDED_ALLOW_IPS"):
        assert flag in parts[2], f"CMD الصورة بلا {flag}"


def test_pip_audit_ignore_list_is_tethered_to_the_multipart_pin():
    """R7 (قرار المالك 2026-09-05): رُفع `python-multipart` إلى ≥ 0.0.31 فزالت قائمةُ
    `--ignore-vuln` كلّها — عودتُها (أو تراجعُ التثبيت) تُحمِّر هذا القفل؛ لا تُستثنى
    ثغراتٌ بعد الرفع (R0 كان يربط القائمة بالتثبيت المصاب 0.0.20)."""
    ci = _read(".github/workflows/ci.yml")
    reqs = _read("requirements.txt")
    pin = re.search(r"^python-multipart==([\d.]+)", reqs, re.M)
    assert pin, "python-multipart غير مثبَّت الإصدار في requirements.txt"
    assert tuple(int(x) for x in pin.group(1).split(".")) >= (0, 0, 31), pin.group(1)
    assert "--ignore-vuln" not in ci, "قائمةُ الاستثناءات عادت — لا تُستثنى ثغراتٌ بعد الرفع"
    assert "pip-audit -r requirements.txt --strict" in ci


# ── CI-6: فحص الدخان يدخل بوّابة المصانع (اختياري، للقراءة فقط) ───────────────
def test_post_deploy_smoke_exposes_an_opt_in_platform_lane(monkeypatch):
    """`--platform-email/--platform-password` (افتراضهما من `SILK_SMOKE_EMAIL/
    PASSWORD`)، و`--key` يقرأ `SILK_LIVE_API_KEY` — فلا مفتاح يعبر argv."""
    mod = _smoke_module()
    monkeypatch.setenv("SILK_SMOKE_EMAIL", "f@x.invalid")
    monkeypatch.setenv("SILK_SMOKE_PASSWORD", "pw-from-env")
    monkeypatch.setenv("SILK_LIVE_API_KEY", "key-from-env")
    args = mod._build_parser().parse_args(["http://h.invalid"])
    assert args.platform_email == "f@x.invalid"
    assert args.platform_password == "pw-from-env"
    assert args.key == "key-from-env"
    monkeypatch.delenv("SILK_SMOKE_EMAIL")
    monkeypatch.delenv("SILK_SMOKE_PASSWORD")
    monkeypatch.delenv("SILK_LIVE_API_KEY")
    args = mod._build_parser().parse_args(["http://h.invalid"])
    assert args.platform_email == "" and args.platform_password == ""
    assert args.key is None
    src = _read("tools/post_deploy_smoke.py")
    for needle in ("/platform/auth/login", "/platform/me", "/platform/studies",
                   "/report", "def _check_platform(", "def _finish("):
        assert needle in src, f"مسار بوّابة المصانع غائب عن الدخان: {needle}"
    assert "--platform-email" in mod._build_parser().format_help()
    # مراجعة §58: نصّ المساعدة عربيّ — بلا UTF-8 صريح يموت الابن على ويندوز
    # (cp1252) بـUnicodeEncodeError؛ الاختبار يضبط ما يضبطه CI.
    r = subprocess.run([sys.executable, str(_SMOKE), "--help"],
                       capture_output=True, cwd=str(_ROOT), timeout=60,
                       env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "--platform-email" in r.stdout.decode("utf-8", "replace")


def _fake_platform(calls: list, *, login_status: int = 200,
                   me_email: str = "f@x.invalid", me_body=None,
                   report_status: int = 200):
    """بوّابة مصانع مزيّفة — تسجّل كل نداء وتردّ بأشكال الردود الحقيقية.

    HEAD ⇒ 405 كما الحيّ (FastAPI لا يضيف HEAD لمسار `@app.get`) — قفلٌ ضدّ
    عودة رأس HEAD الذي كان يمرّ زوراً في مزيّفٍ يجيب عليه.
    """
    def req(base, path, token=None, method="GET", payload=None, timeout=60):
        calls.append((method, path, token))
        if method == "HEAD":
            return 405, b"", {}
        if path == "/platform/auth/login":
            req.login_payloads.append(payload)
            body = {"token": "T0K"} if login_status == 200 else {"detail": "no"}
            return login_status, json.dumps(body).encode(), {}
        if path == "/platform/me":
            body = me_body if me_body is not None else {"email": me_email,
                                                        "role": "factory"}
            return 200, json.dumps(body).encode(), {}
        if path == "/platform/studies":
            rows = [{"id": 3, "state": "draft"},
                    {"id": 7, "state": "completed", "analysis_id": 9},
                    {"id": 5, "state": "completed", "analysis_id": 4}]
            return 200, json.dumps({"studies": rows}).encode(), {}
        if path == "/platform/studies/7/report" and method == "GET":
            if report_status == 409:
                return 409, json.dumps({"detail": {
                    "error": "quality_gate_fail",
                    "message": "بوّابة التسليم حجبت النسخة"}}).encode(), {}
            return 200, json.dumps({"study": {"id": 7, "state": "completed"},
                                    "quality": {}, "view": {"brief": "x"}}).encode(), {}
        return 404, b"{}", {}
    req.login_payloads = []
    return req


def test_platform_lane_is_read_only_and_skips_loudly_without_credentials(monkeypatch):
    """بلا اعتماد ⇒ «متخطّاة» معلَنة بلا أي نداء؛ مع اعتماد ⇒ دخول → `/me` →
    `/studies` → `GET …/report` لأحدث دراسة مكتملة — قراءة فقط: لا إطلاق ولا
    حذف، ولا HEAD (405 حيّاً)، ولا تشغيل لمحرّك PDF."""
    mod = _smoke_module()
    calls: list = []
    monkeypatch.setattr(mod, "_platform_req", _fake_platform(calls))
    fails: list[str] = []
    assert mod._check_platform("http://h.invalid", "", "", fails) == "skipped"
    assert fails == [] and calls == [], "لا نداء بلا اعتماد"

    assert mod._check_platform("http://h.invalid", "f@x.invalid", "pw", fails) == "ok"
    assert fails == [], fails
    methods = {m for m, _p, _t in calls}
    assert methods <= {"GET", "POST"}, methods
    posts = [p for m, p, _t in calls if m == "POST"]
    assert posts == ["/platform/auth/login"], "الكتابة الوحيدة المسموحة هي الدخول"
    assert ("GET", "/platform/studies/7/report", "T0K") in calls, (
        "تقرير أحدث دراسة مكتملة (أعلى معرّف) يُفحَص بعرض JSON بالرمز")
    assert not any(p.endswith("report.pdf") for _m, p, _t in calls), (
        "لا تشغيل لمحرّك PDF ولا استهلاك لخانق pdf| في الدخان")
    assert all(t == "T0K" for m, p, t in calls if p != "/platform/auth/login"), (
        "كل نداء بعد الدخول يحمل رمز الجلسة")
    for m, p, _t in calls:
        assert not re.search(r"launch|cancel|delete|archive|complete", p), p


def test_platform_lane_declares_login_and_identity_failures(monkeypatch):
    """دخولٌ مرفوض أو هويّةٌ لا تطابق البريد = فشل صريح بسبب، لا نجاح صامت."""
    mod = _smoke_module()
    calls: list = []
    monkeypatch.setattr(mod, "_platform_req", _fake_platform(calls, login_status=401))
    fails: list[str] = []
    assert mod._check_platform("http://h.invalid", "f@x.invalid", "pw", fails) == "failed"
    assert fails and "login" in fails[0]
    assert [p for _m, p, _t in calls] == ["/platform/auth/login"], "يتوقّف عند الدخول"

    calls.clear()
    fails.clear()
    monkeypatch.setattr(mod, "_platform_req",
                        _fake_platform(calls, me_email="other@x.invalid"))
    assert mod._check_platform("http://h.invalid", "f@x.invalid", "pw", fails) == "failed"
    assert any("/platform/me" in f for f in fails)


def test_platform_lane_rejects_half_credentials_and_odd_bodies_by_name(monkeypatch):
    """نصفُ اعتماد = خطأ ضبط صريح (لا تخطٍّ صامت يبقي الوظيفة خضراء بلا فحص)؛
    جسمٌ JSON غير قاموسيّ = فشل مسمّى لا تتبّع استثناء."""
    mod = _smoke_module()
    calls: list = []
    monkeypatch.setattr(mod, "_platform_req", _fake_platform(calls))
    fails: list[str] = []
    assert mod._check_platform("http://h.invalid", "f@x.invalid", "", fails) == "failed"
    assert fails and "SILK_SMOKE" in fails[0] and calls == []
    fails.clear()
    assert mod._check_platform("http://h.invalid", "", "pw", fails) == "failed"
    assert fails and calls == []

    calls.clear()
    fails.clear()
    monkeypatch.setattr(mod, "_platform_req",
                        _fake_platform(calls, me_body=["not", "a", "dict"]))
    assert mod._check_platform("http://h.invalid", "f@x.invalid", "pw", fails) == "failed"
    assert any("/platform/me" in f for f in fails), fails


def test_platform_lane_treats_gate_409_and_padded_email_as_intended(monkeypatch):
    """409 من بوّابة التسليم = سلوك مقصود (كما `_check_exports`) لا عطل نشر؛
    بريدٌ بمسافات/حروف كبيرة (سرٌّ مُلصَق) يُطبَّع قبل الدخول والمقارنة معاً."""
    mod = _smoke_module()
    calls: list = []
    fake = _fake_platform(calls, report_status=409)
    monkeypatch.setattr(mod, "_platform_req", fake)
    fails: list[str] = []
    assert mod._check_platform("http://h.invalid", "  F@X.invalid\n", "pw", fails) == "ok"
    assert fails == [], fails
    assert fake.login_payloads == [{"email": "f@x.invalid", "password": "pw"}]
    assert ("GET", "/platform/studies/7/report", "T0K") in calls


def test_main_prints_platform_failures_even_when_the_engine_lane_exits_early(
        monkeypatch, capsys):
    """نشرٌ جديد بلا تحليل مكتمل + دخولٌ مرفوض ⇒ الخروج 1 **مع** سبب بوّابة
    المصانع مطبوعاً — كان المخرج المبكّر يبتلع الأسباب فيحمرّ بلا كلمة."""
    mod = _smoke_module()

    def fake_get(base, path, key, raw=False):
        if path == "/health":
            return 200, json.dumps({"storage": {"data_dir": "/data"},
                                    "research_ready": True,
                                    "hs_classifier": {"enabled": True}}).encode()
        if path == "/analyses":
            return 200, b"[]"
        return 404, b"{}"
    monkeypatch.setattr(mod, "_get", fake_get)
    calls: list = []
    monkeypatch.setattr(mod, "_platform_req", _fake_platform(calls, login_status=401))
    monkeypatch.setattr(sys, "argv", ["post_deploy_smoke.py", "http://h.invalid",
                                      "--platform-email", "f@x.invalid",
                                      "--platform-password", "pw", "--skip-analyze"])
    rc = mod.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "platform login" in out, out


def test_post_deploy_workflow_passes_credentials_through_env_not_argv():
    """الأسرار تصل السكربت بالبيئة: بريد/كلمة الدخان اختياريان، ومفتاح الـAPI
    لم يعد يُحقَن في `$ARGS` غير المقتبَس (كان يعبر argv ويتكسّر على مسافة)."""
    wf = _read(".github/workflows/post-deploy-smoke.yml")
    assert "SILK_SMOKE_EMAIL: ${{ secrets.SILK_SMOKE_EMAIL }}" in wf
    assert "SILK_SMOKE_PASSWORD: ${{ secrets.SILK_SMOKE_PASSWORD }}" in wf
    assert "SILK_LIVE_API_KEY: ${{ secrets.SILK_LIVE_API_KEY }}" in wf
    assert "--key $SILK_LIVE_API_KEY" not in wf, "المفتاح لا يعبر argv"
    assert re.search(r"^on:\s*\n\s*workflow_dispatch:", wf, re.M), (
        "يبقى يدوياً حصراً — قرار المالك")


def test_deploy_doc_names_the_image_cmd_as_the_only_start_command():
    """الوثيقة تقول ما يقوله النشر: CMD الصورة هو أمر التشغيل الوحيد، بأعلامه،
    ومسار الدخان يذكر بوّابة المصانع وسرَّيها."""
    doc = _read("docs/DEPLOY_RAILWAY.md")
    assert "startCommand" in doc, "الوثيقة لا تشرح حال startCommand"
    assert "Custom Start Command" in doc, (
        "الوثيقة لا تحذّر من حقل اللوحة الذي يغلب CMD فور غياب railway.json")
    assert "--timeout-graceful-shutdown" in doc and "--proxy-headers" in doc
    assert "SILK_SMOKE_EMAIL" in doc and "SILK_SMOKE_PASSWORD" in doc
    assert "docker-health" in doc, "الوثيقة لا تذكر وظيفة بناء الصورة في CI"
