"""رُتبة ٢ — خادم حقيقي بشكل الإنتاج (rung 2 — the real-server lane).

> **القاعدة الجديدة (تأكيد المالك آخِراً لا أوّلاً).** «مدموج ≠ يعمل؛ أخضر
> محلياً ≠ تمّ» (البند ١، `docs/LESSONS.md`). الحزمة الهرمتية تُثبِت العقود
> على TestClient/نماذج؛ **لا تُقلِع الخادم الفعلي**. هذه الرُتبة تُقلِع
> `uvicorn api:app` على ملف SQLite حقيقي مبذور بالمدوّنة القانونية، وتضرب كل
> نقطة نهاية للقراءة/التصدير بـHTTP حقيقي. هذا التدفّق بالضبط كان سيلتقط
> عائلة 501 التصدير والشريط الجانبي الميت **قبل** أن يراها المالك.

المفاتيح المدفوعة غائبة عمداً — نقاط القراءة/التصدير المبذورة تُقرَأ من
المخزن ولا تلمس أيّ API خارجي (لا محاكاة لازمة على مسار الإسناد؛ التغييرات
قرب مسار المال تُشغّل رُتبة ٤ بمزودين محاكَين). راجع `tools/live_shape_server.py`.

يُتخطّى في `pytest tests/ -q` الافتراضية (هرمتية سريعة)؛ يعمل في وظيفة
`e2e-live-shape` حين `SILK_RUN_E2E=1`.

Run locally:  SILK_RUN_E2E=1 python3 -m pytest tests/test_rung2_real_server.py -q
"""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

pytestmark = pytest.mark.e2e


def _get(base: str, path: str):
    req = urllib.request.Request(base + path)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})


@pytest.fixture(scope="module")
def server():
    from live_shape_server import LiveShapeServer
    with LiveShapeServer() as srv:
        yield srv


# ── الواجهة تُخدَم فعلياً (الشريط الجانبي/أزرار التصدير موجودة) ──────────────

def test_dashboard_html_is_served_with_the_touched_ui_hooks(server):
    """`GET /index.html` يخدم اللوحة الفعلية بمرابط الواجهة التي تختبرها رُتبة ٣:
    الشريط الجانبي (#histList)، وزرّا التصدير (Word=#pdfBtn، Markdown=#mdBtn).
    تغييرٌ معلن (طلب المالك 2026-09-24): الجذرُ يحوّل إلى `/platform`، واللوحةُ
    ملفُّها الثابت نفسُه على `/index.html`."""
    st, body, _ = _get(server.base_url, "/index.html")
    assert st == 200
    html = body.decode("utf-8", "replace")
    assert 'id="histList"' in html          # الشريط الجانبي
    assert 'id="pdfBtn"' in html            # تصدير Word/PDF
    assert 'id="mdBtn"' in html             # تصدير Markdown
    assert 'id="boardBody"' in html         # لوحة العرض


def test_root_opens_the_platform_on_the_real_server(server):
    st, body, _ = _get(server.base_url, "/")      # urllib يتبع التحويل
    assert st == 200
    # صفحةُ هبوط المنصّة نفسُها، لا اللوحة.
    assert "<title>سِلك للدراسات</title>".encode() in body
    assert b'id="histList"' not in body


def test_health_is_200_on_the_real_server(server):
    st, body, _ = _get(server.base_url, "/health")
    assert st == 200
    assert isinstance(json.loads(body), dict)   # صيد ٣: توكيد فعلي لا توتولوجيا


# ── الشريط الجانبي: الصفوف الحقيقية تُسرَد، والصفّ الجارٍ يحمل حالته ──────────

def test_analyses_list_returns_both_seeded_rows(server):
    st, body, _ = _get(server.base_url, "/analyses")
    assert st == 200
    rows = json.loads(body)
    ids = {r.get("id") for r in rows}
    assert server.completed_id in ids and server.running_id in ids
    running = [r for r in rows if r.get("id") == server.running_id][0]
    # صفّ التقدّم — الشريط الجانبي يعرض «جارٍ التشغيل…» + زرّ استئناف عليه.
    assert running.get("status") == "running"


def test_single_analysis_carries_analysis_id_and_prebuilt_view(server):
    """نقر الشريط الجانبي يفتح `GET /analyses/{id}` ويعتمد على analysis_id
    (لأزرار التصدير) وعلى view (لعرض اللوحة) — كلاهما يجب أن يصل."""
    st, body, _ = _get(server.base_url, f"/analyses/{server.completed_id}")
    assert st == 200
    j = json.loads(body)
    assert j.get("analysis_id") == server.completed_id
    assert j.get("view")                    # عرض مُبنى مسبقاً


# ── التصدير: نفس عائلة الأخطاء الثلاث (501/قالب فارغ) على HTTP حقيقي ─────────

def test_report_md_serves_real_narrative_not_the_empty_analyze_template(server):
    """البند ٢: report.md لنتيجة بحث يُصيَّر من deep_research (سرد غنيّ)، لا
    قالب /analyze الفارغ («with_research غير مفعّلة»/«0 أسواق»/«None»)."""
    st, body, _ = _get(server.base_url,
                       f"/analyses/{server.completed_id}/report.md")
    assert st == 200, body[:300]
    md = body.decode("utf-8", "replace")
    assert md.strip()                                   # غير فارغ
    assert "HHI" in md and "EU 2017/625" in md          # السرد الحقيقي
    assert "with_research" not in md                    # لا قالب /analyze
    assert "None" not in md                             # لا سنة/ثقة "None"


def test_report_docx_downloads_a_real_openable_document_no_501(server):
    """البنود ٢/٣/١١/١٣: report.docx لا يفشل 501، وهو ملف ZIP/docx صالح
    يُفتَح فعلياً عبر python-docx بمحتوى غير فارغ (لا مجرد 200 على الحالة)."""
    st, body, headers = _get(server.base_url,
                             f"/analyses/{server.completed_id}/report.docx")
    assert st == 200, body[:300]
    assert body[:2] == b"PK"                            # توقيع ZIP (docx)
    from docx import Document
    doc = Document(io.BytesIO(body))
    text = "\n".join(p.text for p in doc.paragraphs)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                text += "\n" + c.text
    assert text.strip()                                 # مستند غير فارغ فعلاً


def test_bahrain_coffee_codex_exports_clean_over_real_http(server):
    """الدرس ٢٩٨: مدوّنةُ بلاغ المالك (قهوة البحرين) تُصدَّر عبر الخادم الحقيقيّ
    — Word وMarkdown بلا حجبٍ وبلا أيّ عبارةٍ رفضها المالك، وجسرُ الملك فهد
    مذكور. الهرمتيّ وحدَه كان يثبتها (تدقيق الفجوات)."""
    import silk_quality_gate as Q
    assert server.bahrain_id
    st, body, _ = _get(server.base_url, f"/analyses/{server.bahrain_id}/report.md")
    assert st == 200, body[:400]
    md = body.decode("utf-8", "replace")
    assert "جسر الملك فهد" in md
    assert not Q.owner_flag_hits(md, "BHR")
    st, body, _ = _get(server.base_url, f"/analyses/{server.bahrain_id}/report.docx")
    assert st == 200, body[:400]
    from docx import Document
    doc = Document(io.BytesIO(body))
    text = "\n".join([p.text for p in doc.paragraphs]
                     + [c.text for t in doc.tables for r in t.rows for c in r.cells])
    assert text.strip() and not Q.owner_flag_hits(text, "BHR")


def test_missing_analysis_export_is_404_not_a_fabricated_success(server):
    """المبدأ المؤسِّس على مستوى HTTP: تحليل غير موجود = 404 صريح، لا مستند
    فارغ مُختلَق."""
    st, _, _ = _get(server.base_url, "/analyses/999999/report.md")
    assert st == 404


# ── R9 (CONC-3/CI-3): مسبارُ الحياة لا يقف خلف مجمّع الخيوط المشبَع ─────────────

def test_health_answers_within_a_second_while_the_threadpool_is_saturated():
    """٤٥ طلباً بطيئاً متزامناً (`/_test/slow`، ٤ ث لكلٍّ) يشغل مجمّعَ الخيوط (٤٠
    افتراضياً) — `/health` غيرُ المتزامن يُجاب من حلقة الحدث بلقطةٍ جاهزة في أقلّ
    من ثانية، لا من الطابور. قبل R9 كان الطلبُ الحادي والأربعون ينتظر انتهاء أحد
    الأربعين — ومسبارُ Railway معه (إعادةُ تشغيلٍ لحاويةٍ سليمة)."""
    import threading
    import time
    from live_shape_server import LiveShapeServer
    with LiveShapeServer(env={"SILK_TEST_SLOW_ROUTE_S": "4"}) as srv:
        codes: list = []

        def slow():
            try:
                st, _, _ = _get(srv.base_url, "/_test/slow")
                codes.append(st)
            except Exception as exc:  # noqa: BLE001
                codes.append(repr(exc))
        threads = [threading.Thread(target=slow, daemon=True) for _ in range(45)]
        for t in threads:
            t.start()
        time.sleep(1.0)                      # الطلباتُ البطيئة استقرّت في المجمّع
        t0 = time.monotonic()
        st, body, _ = _get(srv.base_url, "/health")
        elapsed = time.monotonic() - t0
        for t in threads:
            t.join(20)
    assert st == 200 and json.loads(body)["status"] == "ok"
    assert elapsed < 1.0, f"/health أجاب بعد {elapsed:.2f}s تحت الإشباع"
    assert codes.count(200) == 45, codes


def test_remote_mcp_link_runs_tools_via_loopback_and_serves_file_link():
    """رابط MCP البعيد (توضيح المالك 2026-10-21): `POST /mcp/<token>` على خادم حقيقي —
    الأدوات تنادي الخادمَ **نفسه** عبر loopback بمفتاحه (لا يُلتَفّ على البوّابات)،
    و`download_report` يعيد رابطاً بالرمز نفسه يُنزِّل Word فعلياً. هذا ما لا تستطيع
    الحزمة الهرمتية إثباته (كل اختباراتها تُطعِّم `_http`)."""
    import socket
    from live_shape_server import LiveShapeServer
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    token = "rung2-remote-mcp-token-0123456789"
    with LiveShapeServer(port=port, env={"SILK_MCP_TOKEN": token, "PORT": str(port)}) as srv:
        def rpc(payload, tok=token):
            req = urllib.request.Request(
                f"{srv.base_url}/mcp/{tok}", method="POST",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json, text/event-stream"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.status, r.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8")
        assert rpc({"jsonrpc": "2.0", "id": 0, "method": "ping"}, tok="wrong-token-wrong-token")[0] == 404
        st, body = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18"}})
        assert st == 200 and json.loads(body)["result"]["serverInfo"]["name"] == "silk"
        assert rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})[0] == 202

        def call(mid, name, args):
            st, body = rpc({"jsonrpc": "2.0", "id": mid, "method": "tools/call",
                            "params": {"name": name, "arguments": args}})
            assert st == 200, body
            res = json.loads(body)["result"]
            return res["isError"], [c["text"] for c in res["content"]]
        err, txt = call(2, "list_studies", {"limit": 20})         # loopback حقيقي بمفتاح الخادم
        assert err is False and "|" in txt[0], txt
        # بعض الصفوف المبذورة /analyze أو بلا نصّ كاتب — نأخذ أول دراسة يعيد الخادم نصَّها
        # (نفس ما يفعله المالك في كلود: يجرّب، والأداة تقول لماذا لا).
        rows = [[c.strip() for c in ln.split("|")] for ln in txt[0].splitlines()[1:]]
        first_id, got = None, None
        for r in rows:
            err, got = call(3, "get_report", {"analysis_id": int(r[0])})
            if err is False and got[1].startswith("## 1."):
                first_id = int(r[0])
                break
        assert first_id is not None, (rows, got)
        err, txt = call(4, "download_report", {"analysis_id": first_id})
        assert err is False, txt
        link = [ln for ln in txt[0].splitlines() if "/mcp/" in ln][-1].strip()
        assert f"/mcp/{token}/files/{first_id}/report.docx" in link
        with urllib.request.urlopen(link, timeout=120) as r:
            data, ctype = r.read(), r.headers.get("Content-Type", "")
        assert data[:2] == b"PK" and len(data) > 10_000 and "wordprocessingml" in ctype
        with pytest.raises(urllib.error.HTTPError) as ex:
            urllib.request.urlopen(link.replace(token, "x" * len(token)), timeout=30)
        assert ex.value.code == 404
