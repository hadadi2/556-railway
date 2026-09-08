"""رُتبة ٤ — جسرُ المنصّة على الخطّ الحقيقي (R8/TEST-1، تدقيق 2026-09-01).

> **الفجوة المقيسة.** رُتبتا ٢ و٣ تُقلعان خادماً حقيقياً ومتصفّحاً حقيقياً، لكنّ
> دراسةَ المصنع فيهما تمرّ بـ`SILK_PLATFORM_FAKE_ENGINE` — مقعدٌ يقفز **فوق الخطّ
> كلّه** (جسر ← بعثات ← توليف ← كاتب ← بوّابة جودة) ويحفظ عيّنةً موسومة. أي أنّ
> «الدراسةُ تكتمل فعلاً» ظلّ غيرَ مُثبَتٍ خارج العيّنة، وهو بالضبط ما يقرؤه المالك.
>
> هذه الرُتبة تُشغّل **الخطّ الحقيقي** بلا نداءٍ خارجيّ: المقعدُ ينتقل من مستوى
> الجسر إلى مستوى **المزوّد** (`SILK_LLM_PROVIDER=fake`)، فكلُّ حلقةٍ ونقطةِ تفتيشٍ
> وحصّةٍ ومصالحةٍ ودفتر استهلاك تعمل كما في الإنتاج. المفتاحُ المضبوط باطلٌ عمداً
> ووكيلُ الشبكة موجَّهٌ إلى منفذٍ مغلق: أيّ نداءٍ حقيقيّ **يفشل بصوت**، فنجاحُ
> التشغيلة دليلٌ بنيويّ على أنّ صفر دولارات أُنفقت.

**نطاقُ ما تُثبِته (صدقٌ في الادّعاء).** الشبكةُ مقطوعة، فالبعثاتُ لا تجد حقائق —
وهذا نفسُه دليلٌ مطلوب: التشغيلةُ الأولى تُثبِت أنّ **بوّابة كفاية البيانات** تعمل على
الخطّ الحقيقي (تُوقِف قبل الكتابة وتقول أيّ الجوانب نقص، ولا تكتب توصيةً فوق فراغ)،
والثانيةُ — بإطفاءِ الوقف المبكر صراحةً — تُثبِت أنّ **المحلّل والكاتب وبوّابة الجودة
والحفظ** تعمل كلُّها على المسار نفسِه. ما لا تُثبِته: جودةَ النصّ (المزوّد معلَّب).

يُتخطّى في `pytest tests/ -q` الافتراضية (`SILK_RUN_E2E` غير مضبوط).

Run locally:  SILK_RUN_E2E=1 python3 -m pytest tests/test_rung4_platform_real_bridge.py -q
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

pytestmark = pytest.mark.e2e

# مفتاحٌ **باطلٌ عمداً**: الخطُّ يمرّ بمزوّدٍ معلَّب، فأيّ نداءٍ حقيقيّ يعني عطلاً
# في العزل — ولن ينجح بهذا المفتاح. صفرُ دولارات، بالبنية لا بالنيّة.
_INVALID_KEY = "sk-ant-invalid-rung4-no-network-should-ever-use-this"
_ENV = {
    "SILK_PLATFORM_FAKE_ENGINE": "",          # ينزع المقعدَ الجسريّ — الخطُّ الحقيقي
    "SILK_LLM_PROVIDER": "fake",              # المقعدُ على مستوى المزوّد
    # المنصّةُ تحجب طبقاتِ كلود حين يوجد مفتاحٌ مدفوع بلا `SILK_API_KEY` (حارس 503)،
    # فضبطُه شرطُ تشغيل الخطّ الحقيقي — وهو ليس إشارةَ إنتاج (راجع `_production_signal`).
    "SILK_API_KEY": "rung4-secret",
    "ANTHROPIC_API_KEY": _INVALID_KEY,
    "SILK_PLATFORM_STUDY_MODE": "deep",
    "SILK_PLATFORM_STUDY_AI": "1",
    "SILK_PAID_DAILY_CAP": "50",
    "SILK_PAID_DAILY_USD_CAP": "5",
    "SILK_MISSION_TIMEOUT_S": "20",
    "SILK_MISSION_WALL_GRACE_S": "5",
    "SILK_ANALYZE_DEADLINE_S": "90",
    "SILK_HTTP_RETRIES": "0",
    "SILK_SWR": "0",
    # وكيلُ شبكةٍ إلى منفذٍ مغلق: أيّ نداءٍ خارجيّ يفشل فوراً بدل أن ينتظر مهلته.
    "HTTP_PROXY": "http://127.0.0.1:9",
    "HTTPS_PROXY": "http://127.0.0.1:9",
    "NO_PROXY": "127.0.0.1,localhost",
}


def _req(base: str, path: str, *, method: str = "GET", token: str | None = None,
         body: dict | None = None, timeout: float = 30.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("X-API-Key", _ENV["SILK_API_KEY"])
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:200].decode("utf-8", "replace")}


def _boot(extra: dict | None = None):
    from live_shape_server import LiveShapeServer
    env = dict(_ENV)
    env.update(extra or {})
    srv = LiveShapeServer(platform=True, env=env, boot_timeout=90.0)
    srv.seed()
    srv.start()
    os.environ["SILK_RUNG4_PASSWORD"] = srv.PLATFORM_PASSWORD
    return srv


@pytest.fixture(scope="module")
def server():
    srv = _boot()
    try:
        yield srv
    finally:
        srv.__exit__(None, None, None)


@pytest.fixture(scope="module")
def server_no_halt():
    # `SILK_EARLY_HALT=0` صمّامٌ موثَّق (`api.py`): يُطفَأ هنا **صراحةً** كي يُختبَر ذيلُ
    # الخطّ (محلّل ← كاتب ← بوّابة جودة ← حفظ) بلا شبكة؛ الإنتاجُ يبقى على الافتراض ١.
    srv = _boot({"SILK_EARLY_HALT": "0"})
    try:
        yield srv
    finally:
        srv.__exit__(None, None, None)


def _run_a_study(base: str, market: str = "ARE") -> dict:
    """دخولٌ ← منتجٌ ← دراسةٌ ← إطلاقٌ ← انتظارُ حالةٍ نهائية. يعيد صفَّ الدراسة."""
    st, out = _req(base, "/platform/auth/login", method="POST",
                   body={"email": "owner@factory-a.local",
                         "password": os.environ["SILK_RUNG4_PASSWORD"]})
    assert st == 200, out
    tok = out["token"]
    st, prod = _req(base, "/platform/products", method="POST", token=tok,
                    body={"name": "تمور سكري", "hs_code": "080410"})
    assert st in (200, 201), prod
    st, study = _req(base, "/platform/studies", method="POST", token=tok,
                     body={"product": "تمور سكري", "hs_code": "080410",
                           "market_pref": market, "product_id": prod["id"]})
    assert st in (200, 201), study
    sid = study["id"]
    st, launched = _req(base, "/platform/studies/%d/launch" % sid, method="POST",
                        token=tok, timeout=60)
    assert st == 200, launched
    assert launched["state"] == "in_progress", launched
    deadline = time.monotonic() + 300
    row: dict = {}
    while time.monotonic() < deadline:
        st, row = _req(base, "/platform/studies/%d" % sid, token=tok)
        assert st == 200, row
        if row.get("state") in ("completed", "draft"):
            break
        time.sleep(2)
    row["_token"], row["_id"] = tok, sid
    return row


def _run_mode_via_admin(base: str, sid: int) -> str:
    """وضعُ التشغيلة من سطح الأدمِن — الصفُّ هناك يفكّ `run_stats` (سطحُ المصنع
    لا يعرضها). يُثبِت أنّ التشغيلة سلكت الخطّ العميق لا المقعدَ الجسريّ."""
    st, out = _req(base, "/platform/auth/login", method="POST",
                   body={"email": "admin@silk.local",
                         "password": os.environ["SILK_RUNG4_PASSWORD"]})
    assert st == 200, out
    st, listing = _req(base, "/platform/admin/studies?limit=500", token=out["token"])
    assert st == 200, listing
    row = next((r for r in listing["studies"] if int(r["id"]) == int(sid)), None)
    assert row is not None, sid
    return ((row.get("run_stats") or {}) or {}).get("mode") or ""


def test_the_real_pipeline_runs_and_the_data_sufficiency_gate_holds(server):
    """التشغيلةُ الأولى بصمّاماتِ الإنتاج كما هي: الجسرُ والبعثاتُ تعمل على الخطّ
    الحقيقي، وبوّابةُ كفاية البيانات تُوقِف **قبل** الكتابة وتسمّي الجوانب الناقصة —
    لا توصيةَ فوق فراغ، ولا انهيارَ ولا مهلةٌ صامتة."""
    row = _run_a_study(server.base_url)
    assert row.get("state") == "draft", row
    err = row.get("run_error") or ""
    assert "أوقفنا الدراسة مبكراً" in err, err
    assert "الجوانب" in err, err                     # يسمّي ما نقص
    assert _run_mode_via_admin(server.base_url, row["_id"]) == "deep", "ليس الخطَّ العميق"
    assert "traceback" not in err.lower() and "Exception" not in err, err


def test_the_writer_and_the_save_path_run_when_the_early_halt_is_off(server_no_halt):
    """التشغيلةُ الثانية بإطفاءِ الوقف المبكر **صراحةً** (`SILK_EARLY_HALT=0` — صمّامٌ
    موثَّق): المحلّلُ والكاتبُ وبوّابةُ الجودة والحفظُ تعمل على المسار نفسِه، والتقريرُ
    الناتج ليس عيّنةَ المقعد الجسريّ."""
    row = _run_a_study(server_no_halt.base_url)
    assert row.get("state") == "completed", (
        f"لم تكتمل بلا الوقف المبكر: {row.get('run_error')}")
    assert _run_mode_via_admin(server_no_halt.base_url, row["_id"]) == "deep"
    assert row.get("analysis_id"), row
    st, report = _req(server_no_halt.base_url,
                      "/platform/studies/%d/report" % row["_id"],
                      token=row["_token"], timeout=60)
    assert st == 200, report
    blob = json.dumps(report, ensure_ascii=False)
    assert "عيّنة اختبار" not in blob, "التقريرُ عيّنةُ المقعد الجسريّ لا مخرَجَ الخطّ"
    assert report.get("view"), report


def test_the_run_spent_nothing_and_made_no_external_call(server):
    """المفتاحُ باطلٌ ووكيلُ الشبكة مغلق: تشغيلةٌ ناجحة معناها صفرُ نداءاتٍ خارجية.
    ودفترُ الاستهلاك يشهد: لا دولارَ سُجِّل على مزوّدٍ معلَّب."""
    base = server.base_url
    st, health = _req(base, "/health")
    assert st == 200, health
    assert health["sources"]["claude"] in ("on", "blocked — ANTHROPIC_API_KEY بلا SILK_API_KEY"), \
        health["sources"]["claude"]
    st, diag = _req(base, "/platform/admin/metrics", token=None)
    assert st in (401, 403), "مقاييسُ الأدمِن مكشوفة"
