"""رابط MCP البعيد — `POST /mcp/<SILK_MCP_TOKEN>` (توضيح المالك «وين رابط MCP»، 2026-10-21).

نفس أدوات `tools/silk_mcp.py` عبر Streamable HTTP بلا جلسات: الرمز في المسار هو
المصادقة (Connectors لا تمرّر ترويسات)، نداءات الأدوات تعود إلى الخادم نفسه عبر
loopback بمفتاحه فلا يُلتَفّ على أي بوّابة، و`download_report` يعيد رابطاً محمياً
بالرمز نفسه بدل الحفظ على قرص الخادم.

هرمتي: `tools.silk_mcp._http` مُطعَّم (لا loopback حقيقي هنا — رُتبة ٢ تثبته).
Run: python3 -m pytest tests/test_mcp_remote_endpoint.py -q
"""
from __future__ import annotations

import contextlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

TOKEN = "t0ken-" + "x" * 30


@contextlib.contextmanager
def _env(**vals):
    saved = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _client():
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


def _rpc(c, token, payload, raw=None):
    return c.post(f"/mcp/{token}", content=(raw if raw is not None else json.dumps(payload)),
                  headers={"Content-Type": "application/json",
                           "Accept": "application/json, text/event-stream"})


def test_endpoint_is_off_without_token_and_hides_itself():
    with _env(SILK_MCP_TOKEN=None):
        c = _client()
        assert _rpc(c, "anything", {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 404
    with _env(SILK_MCP_TOKEN="short"):                 # أقصر من ١٦ = مُطفأ (فشل مغلق)
        c = _client()
        assert _rpc(c, "short", {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 404
    with _env(SILK_MCP_TOKEN=TOKEN):
        c = _client()
        assert _rpc(c, TOKEN + "x", {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 404
        assert c.get(f"/mcp/{TOKEN}x").status_code == 404


def test_streamable_http_transport_contract():
    with _env(SILK_MCP_TOKEN=TOKEN, SILK_API_KEY="secret"):
        c = _client()
        r = _rpc(c, TOKEN, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": "connectors", "version": "1"}}})
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
        d = r.json()
        assert d["id"] == 1 and d["result"]["protocolVersion"] == "2025-06-18"
        assert d["result"]["serverInfo"]["name"] == "silk"
        # إشعارٌ بلا ردّ ⇒ 202 بلا جسم
        r = _rpc(c, TOKEN, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert r.status_code == 202 and r.content == b""
        # قائمة الأدوات السبع
        tools = _rpc(c, TOKEN, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()["result"]["tools"]
        assert [t["name"] for t in tools] == ["start_study", "study_status", "download_report",
                                              "list_studies", "get_evidence", "get_report",
                                              "submit_refined_report"]
        # دفعة (2025-03-26) ⇒ قائمة ردود؛ الإشعار داخلها يُسقَط
        r = _rpc(c, TOKEN, [{"jsonrpc": "2.0", "id": 3, "method": "ping"},
                            {"jsonrpc": "2.0", "method": "notifications/cancelled"},
                            {"jsonrpc": "2.0", "id": 4, "method": "nope"}])
        assert r.status_code == 200 and [x.get("id") for x in r.json()] == [3, 4]
        assert r.json()[1]["error"]["code"] == -32601
        # أخطاء النقل
        r = _rpc(c, TOKEN, None, raw="not json")
        assert r.status_code == 400 and r.json()["error"]["code"] == -32700
        r = _rpc(c, TOKEN, None, raw="[]")
        assert r.status_code == 400 and r.json()["error"]["code"] == -32600
        assert c.get(f"/mcp/{TOKEN}").status_code == 405
        assert c.delete(f"/mcp/{TOKEN}").status_code == 405


def test_tools_run_against_loopback_with_server_key_and_links(monkeypatch):
    """نداءات الأدوات تعود إلى الخادم نفسه (127.0.0.1:PORT) — `_http` مُطعَّم هنا؛
    `download_report` يعيد رابط `/mcp/<token>/files/...` ولا يكتب على القرص."""
    import tools.silk_mcp as m
    seen = []

    def fake_http(method, path, body=None, *, raw=False):
        seen.append((method, path, raw))
        if path.startswith("/analyses?limit="):
            return 200, json.dumps([{"id": 7, "product": "قهوة", "market_name": "Bahrain",
                                     "created_at": "2026-10-15", "kind": "research",
                                     "status": "completed", "verdict_label": "دخول مشروط"}])
        if path == "/analyses/7/report/refined":
            return 200, json.dumps({"gate": {"verdict": "PASS-WITH-WARNINGS", "fail_drivers": []}})
        if path == "/analyses/8/report/refined":
            return 200, json.dumps({"gate": {"verdict": "FAIL", "fail_drivers": ["owner_flagged_phrase"]}})
        if path.endswith("/report.docx"):
            return 200, b"PK\x03\x04docx"
        return 500, "boom"

    monkeypatch.setattr(m, "_http", fake_http)
    with _env(SILK_MCP_TOKEN=TOKEN, SILK_API_KEY="secret", PORT="8123",
              RAILWAY_PUBLIC_DOMAIN="silk.example.up.railway.app", SILK_DOWNLOAD_DIR=None):
        c = _client()
        r = _rpc(c, TOKEN, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                            "params": {"name": "list_studies", "arguments": {"limit": 3}}})
        out = r.json()["result"]
        assert out["isError"] is False and "قهوة | Bahrain" in out["content"][0]["text"]
        # الإعداد البعيد contextvar لكل طلب: خارج الطلب يعود الوضع المحلّي (لا تسرّب).
        assert m.REMOTE.get() is None
        with pytest.raises(RuntimeError):
            with _env(SILK_BASE_URL=None):
                m._base_url()
        tok = m.REMOTE.set({"base_url": "http://127.0.0.1:8123/", "download_link_base": "x"})
        try:
            assert m._base_url() == "http://127.0.0.1:8123"
        finally:
            m.REMOTE.reset(tok)
        # download_report بعيداً: فحص البوّابة من سطح التنقيح (لا تصيير مزدوج) ثم رابط بالرمز
        r = _rpc(c, TOKEN, {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                            "params": {"name": "download_report", "arguments": {"analysis_id": 7}}})
        out = r.json()["result"]
        assert out["isError"] is False
        assert f"https://silk.example.up.railway.app/mcp/{TOKEN}/files/7/report.docx" in out["content"][0]["text"]
        assert not os.path.exists(os.path.expanduser("~/Downloads/silk-reports/silk-7.docx"))
        assert ("GET", "/analyses/7/report/refined", False) in seen
        assert all(not (p.endswith("/report.docx")) for _, p, _ in seen)   # لا تنزيلَ بايتات
        # دراسةٌ محجوبة ⇒ لا رابط
        r = _rpc(c, TOKEN, {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                            "params": {"name": "download_report", "arguments": {"analysis_id": 8}}})
        out = r.json()["result"]
        assert out["isError"] is True and "owner_flagged_phrase" in out["content"][0]["text"]
        assert "/files/8/" not in out["content"][0]["text"]


def test_file_link_streams_export_with_token_and_passes_gate_status(monkeypatch):
    import tools.silk_mcp as m

    def fake_http(method, path, body=None, *, raw=False):
        if path.endswith("/report.docx"):
            return 200, b"PK\x03\x04docx-bytes"
        if path.endswith("/report.pdf"):
            return 409, json.dumps({"detail": {"error": "quality_gate_fail",
                                               "fail_drivers": ["owner_flagged_phrase"]}})
        return 500, "boom"

    monkeypatch.setattr(m, "_http", fake_http)
    with _env(SILK_MCP_TOKEN=TOKEN, SILK_API_KEY="secret"):
        c = _client()
        r = c.get(f"/mcp/{TOKEN}/files/7/report.docx")
        assert r.status_code == 200 and r.content == b"PK\x03\x04docx-bytes"
        assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert 'filename="silk-7.docx"' in r.headers["content-disposition"]
        r = c.get(f"/mcp/{TOKEN}/files/7/report.pdf")
        assert r.status_code == 409 and r.json()["detail"]["error"] == "quality_gate_fail"
        assert c.get(f"/mcp/{TOKEN}/files/7/report.exe").status_code == 404
        assert c.get(f"/mcp/{TOKEN}x/files/7/report.docx").status_code == 404
        # الخادم نفسه غير متاح عبر loopback (مهلة/رفض اتصال) ⇒ 502 نظيف لا 500 غير مُدار.
        import urllib.error

        def down(*a, **k):
            raise urllib.error.URLError("connection refused")
        monkeypatch.setattr(m, "_http", down)
        r = c.get(f"/mcp/{TOKEN}/files/7/report.docx")
        assert r.status_code == 502 and "loopback" in r.json()["detail"]


def test_remote_mode_never_bypasses_server_gates_by_construction():
    """كل أداة تمرّ بـHTTP إلى نقاط النهاية القائمة (loopback) — لا استدعاء مباشر لدوال
    داخلية يتجاوز `_require_key`/البوّابات. قفلٌ نصّي على api.py."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent.joinpath("api.py").read_text(encoding="utf-8")
    start = src.index('@app.post("/mcp/{token}")')
    end = src.index('@app.post("/analyses/{analysis_id}/enrich-leads")', start)
    body = src[start:end]
    assert "hmac.compare_digest" in src[src.index("def _mcp_require_token"):start]
    assert "silk_storage." not in body and "silk_ai_judge" not in body
    # حدّ المعدّل قبل فحص الرمز في كل معالج (التخمين يُحاسَب)، ومجمّع مستقل للنداءات.
    for head in ('@app.post("/mcp/{token}")', '@app.delete("/mcp/{token}")',
                 '@app.get("/mcp/{token}/files/'):
        seg = body[body.index(head):]
        assert seg.index("_rate_limit(request)") < seg.index("_mcp_require_token(token)")
    assert "_mcp_run(" in body and "anyio.to_thread" not in body


def test_malformed_jsonrpc_messages_get_errors_not_500():
    import tools.silk_mcp as m
    out = m.handle_payload([{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                            {"jsonrpc": "2.0", "id": 2, "method": 5},
                            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": "x"},
                            "junk"])
    assert [o.get("id") for o in out] == [1, 2, 3, None]
    assert "result" in out[0]
    assert out[1]["error"]["code"] == -32600 and out[2]["error"]["code"] == -32600
    assert out[3]["error"]["code"] == -32600
    with _env(SILK_MCP_TOKEN=TOKEN):
        c = _client()
        r = _rpc(c, TOKEN, {"jsonrpc": "2.0", "id": 9, "method": 5})
        assert r.status_code == 200 and r.json()["error"]["code"] == -32600


def test_access_log_filter_redacts_mcp_token_in_path():
    """SEC-6 (مراجعة §58): سجلُّ وصول uvicorn يكتب المسار حرفياً — الرمز في `/mcp/<token>`
    يُنقَّح كما يُنقَّح `?token=`."""
    import logging
    import api as _api
    f = _api._QueryTokenFilter()
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                            '%s - "%s %s HTTP/1.1" %d',
                            ("1.2.3.4", "POST", f"/mcp/{TOKEN}", 200), None)
    assert f.filter(rec) is True
    assert TOKEN not in (rec.msg % rec.args)
    assert "/mcp/<redacted>" in (rec.msg % rec.args)
    rec2 = logging.LogRecord("x", logging.INFO, "", 0,
                             f'GET /mcp/{TOKEN}/files/7/report.docx 200', (), None)
    f.filter(rec2)
    assert TOKEN not in rec2.msg and "/mcp/<redacted>/files/7/report.docx" in rec2.msg
