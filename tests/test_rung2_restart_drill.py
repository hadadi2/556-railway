"""تمرين إعادة التشغيل (R2) — رُتبة ٢: خادم uvicorn حقيقي يُوقَف أثناء دراسة جارية
ثم يُقلَع على **نفس** البيانات، فلا تبقى الدراسة تبدو سليمةً وهي ميتة.

لماذا (تدقيق 2026-09-01، أمر المالك 2026-09-02 — RC-1): كل اختبارات المنصّة
الهرمتية تعيش في عمليةٍ واحدة لا تموت؛ فكان «إعادة النشر تترك قيد الإعداد ساعةً»
ادعاءً ساكناً بلا رُتبةٍ تُثبته أو تنفيه. هنا: إطلاقٌ حقيقي ← نبضةٌ تتقدّم ←
إيقافُ العملية (SIGTERM ثم SIGKILL في متغيّرٍ ثانٍ) ← إقلاعٌ على القاعدة نفسها
← الدراسة مسودّةٌ بسببٍ معلَن وحصّتُها مُرجَعة. والإلغاءُ عبر HTTP يوقف المقعدَ
المحاكى قبل انقضاء تأخيره.

المقعدُ المحاكى (`SILK_PLATFORM_FAKE_ENGINE=deep`) بتأخيرٍ طويل يمثّل تشغيلةً
حيّة بلا أي نداء خارجي — لا مفاتيح، لا شبكة. Evidence bucket: real server (rung 2).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.e2e

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

# بيئة الخادم: قيم conftest (`…=0`) تتسرّب إلى العملية الفرعية عبر `os.environ`،
# فتُعاد صراحةً هنا — وإلا أقلع الخادم بلا مشرفٍ ولا نبضة فمرّ التمرين زائفاً.
DRILL_ENV = {
    "SILK_PLATFORM_RUN_SUPERVISOR": "1",
    "SILK_PLATFORM_ORPHAN_SWEEP": "1",
    "SILK_PLATFORM_HEARTBEAT_S": "1",
    "SILK_PLATFORM_RUN_STALE_S": "5",
    "SILK_PLATFORM_FAKE_ENGINE_DELAY_S": "40",
}


def _json(base: str, path: str, method: str = "GET", token: str | None = None,
          body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return status, {"_raw": raw[:400].decode(errors="replace")}


def _login(base: str) -> str:
    from live_shape_server import LiveShapeServer as L
    st, out = _json(base, "/platform/auth/login", method="POST",
                    body={"email": L.PLATFORM_FACTORY_EMAIL,
                          "password": L.PLATFORM_PASSWORD})
    assert st == 200, out
    return out["token"]


def _create_and_launch(base: str, token: str) -> tuple[int, dict]:
    st, study = _json(base, "/platform/studies", method="POST", token=token,
                      body={"product": "تمور سكري", "market_pref": "ARE",
                            "hs_code": "080410"})
    assert st in (200, 201), study
    sid = int(study["id"])
    st, out = _json(base, f"/platform/studies/{sid}/launch", method="POST",
                    token=token)
    assert st == 200, out
    return sid, out


def _poll(base: str, token: str, sid: int, pred, timeout: float,
          what: str) -> dict:
    """استطلاعٌ عبر نقطة القراءة العامّة — ما يفعله المتصفّح نفسه."""
    deadline = time.monotonic() + timeout
    row: dict = {}
    while time.monotonic() < deadline:
        st, row = _json(base, f"/platform/studies/{sid}", token=token)
        assert st == 200, row
        if pred(row):
            return row
        time.sleep(0.5)
    raise AssertionError(f"{what} لم يتحقّق خلال {timeout}s — آخر صفّ: "
                         f"state={row.get('state')} run={row.get('run')} "
                         f"run_error={row.get('run_error')}")


def _running_with_heartbeat(row: dict) -> bool:
    run = row.get("run") or {}
    return run.get("state") == "running" and bool(run.get("heartbeat_at"))


def _reverted(row: dict) -> bool:
    return row.get("state") == "draft" and bool(row.get("run_error"))


@pytest.fixture()
def server():
    from live_shape_server import LiveShapeServer
    srv = LiveShapeServer(platform=True, env=DRILL_ENV)
    srv.seed()
    srv.start()
    try:
        yield srv
    finally:
        srv.__exit__(None, None, None)


def _launch_and_reach_running(server) -> tuple[str, int, str]:
    base = server.base_url
    tok = _login(base)
    sid, out = _create_and_launch(base, tok)
    assert out["state"] == "in_progress" and out["run_state"] in ("running", "queued"), out
    row = _poll(base, tok, sid, _running_with_heartbeat, 20, "تشغيلة جارية بنبضة")
    hb0 = row["run"]["heartbeat_at"]
    # النبضة تتقدّم فعلاً أثناء التشغيل (لا ختمَ بدءٍ ثابت).
    _poll(base, tok, sid, lambda r: (r.get("run") or {}).get("heartbeat_at", "") > hb0,
          10, "تقدّم النبضة")
    return tok, sid, hb0


def _assert_recovered(base: str, tok: str, sid: int, timeout: float) -> None:
    row = _poll(base, tok, sid, _reverted, timeout, "عودة الدراسة مسودّةً بعد الإقلاع")
    assert "انقطع" in (row["run_error"] or ""), row["run_error"]
    assert "run" not in row                      # لا تشغيلة نشطة تبقى معلّقة
    st, ent = _json(base, "/platform/entitlements", token=tok)
    assert st == 200, ent
    assert ent["studies_used"] == 0, ent         # الحصّة أُرجعت


def test_graceful_stop_and_restart_never_leaves_the_study_looking_alive(server):
    """SIGTERM أثناء تشغيلة جارية ثم إقلاعٌ على نفس القاعدة ⇒ الدراسة مسودّةٌ
    بسبب «انقطع» وحصّتُها مُرجَعة — بختم الإغلاق (لينكس) أو بانقطاع النبضة."""
    base = server.base_url
    tok, sid, _ = _launch_and_reach_running(server)
    server.stop()
    server.start()
    tok = _login(base)
    # على لينكس يُختَم فوراً عند الإغلاق؛ على ويندوز `terminate()` قتلٌ قسري
    # فيقع التعافي بانقطاع النبضة (٥ ث + دورة مشرف) — كلاهما داخل هذه المهلة.
    _assert_recovered(base, tok, sid, timeout=30)


def test_hard_kill_recovers_through_the_stale_heartbeat_alone(server):
    """SIGKILL (بلا حدث إغلاق) ⇒ التعافي عبر النبضة المنقطعة وحدها عند الإقلاع
    أو في أول دورات المشرف — لا ساعةَ انتظار."""
    base = server.base_url
    tok, sid, _ = _launch_and_reach_running(server)
    server.kill()
    server.start()
    tok = _login(base)
    _assert_recovered(base, tok, sid, timeout=30)


def test_cancel_over_http_stops_the_run_before_its_delay_elapses(server):
    """الإلغاء تعاونيّ فعلاً: المقعد المحاكى (٤٠ ث) يتوقّف عند نقطة تفتيشه خلال
    ثوانٍ، والدراسة تعود مسودّةً بسبب «أُلغيت» وتُرجَع حصّتها."""
    base = server.base_url
    tok, sid, _ = _launch_and_reach_running(server)
    st, out = _json(base, f"/platform/studies/{sid}/cancel", method="POST", token=tok)
    assert st == 200 and out["run_state"] == "cancelling", out
    row = _poll(base, tok, sid, _reverted, 15, "توقّف التشغيلة بعد الإلغاء")
    assert "أُلغيت" in (row["run_error"] or ""), row["run_error"]
    st, ent = _json(base, "/platform/entitlements", token=tok)
    assert st == 200 and ent["studies_used"] == 0, ent


# ── R2b — المسار الجذري على خادمٍ حقيقي · root /research runtime on a real server ──
REAPER_ENV = dict(DRILL_ENV, SILK_ORPHAN_REAP_INTERVAL_S="1",
                  SILK_ORPHAN_STALE_MINUTES="0")


@pytest.fixture()
def reaper_server():
    from live_shape_server import LiveShapeServer
    srv = LiveShapeServer(platform=True, env=REAPER_ENV)
    srv.seed()
    srv.start()
    try:
        yield srv
    finally:
        srv.__exit__(None, None, None)


def test_a_stale_root_research_row_is_reaped_by_the_tick_without_refresh_hours(reaper_server):
    """الصفُّ المبذور `running` (بلا خيطٍ يملكه) يُحصَد بالحاصد الدوريّ وحده —
    `SILK_REFRESH_HOURS` غيرُ مضبوط (المقعدُ يزيله) فكان الحاصدُ لا يدور إطلاقاً."""
    base = reaper_server.base_url
    aid = reaper_server.running_id
    deadline = time.monotonic() + 15
    status = None
    while time.monotonic() < deadline:
        code, body = _json(base, f"/research/{aid}/status")
        assert code == 200, body
        status = body.get("status")
        if status == "failed":
            break
        time.sleep(0.5)
    assert status == "failed", status
    assert "cancel_requested" in body


def test_resume_of_a_fresh_running_row_is_409_on_the_real_server(server):
    """صفٌّ جارٍ طازج النبضة ⇒ الاستئنافُ 409 `resume_still_running` لا تشغيلةً ثانية."""
    base = server.base_url
    aid = server.running_id
    code, body = _json(base, "/research", method="POST",
                       body={"product": "تمور", "market": "Spain", "resume": aid})
    assert code == 409, body
    assert body["detail"]["error"] == "resume_still_running"
    assert body["detail"]["owner"] == "other_process"
