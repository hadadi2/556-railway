"""التقرير المنقَّح بيد المالك عبر MCP — أقفال المسار (قرار المالك 2026-10-20).

المسار: `tools/silk_mcp.py` (خادم MCP stdio بالمكتبة القياسية) يسحب تقرير العميل
إلى كلود، والمالك ينقّحه هناك على اشتراكه، ثم `POST /analyses/{id}/report/refined`
يخزّنه بعد فحوص حتمية (`silk_refined_report`) وبوّابة التسليم نفسها — **صفر
نداء كلود من الخادم** في هذا المسار كلّه.

هرمتي بالكامل: لا شبكة (requests.get مقطوع)، لا مفاتيح، قاعدة مؤقّتة.
Run: python3 -m pytest tests/test_mcp_refined_report.py -q
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_refined_report as RR  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parent.parent


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


# ── (١) الفحوص الحتمية — وحدة silk_refined_report ──────────────────────────
def test_figures_normalize_arabic_indic_digits_and_separators():
    """«٩» و«9» عددٌ واحد؛ فواصل الآلاف تُسقَط؛ «٫» فاصلة عشرية."""
    assert RR.extract_figures("واردات ٩ ملايين و2,900 نقطة و٢٫٥%") == {"9", "2900", "2.5"}
    assert RR.new_figures("بلغت ٩ ملايين", "واردات 9 ملايين") == []


def test_new_figure_detected_even_when_fewer_figures_overall():
    """حذف أرقامٍ مقبول؛ رقمٌ واحد غير وارد يُلتقَط."""
    assert RR.new_figures("نمو 7% في 2019", "نمو 7% (2023) و38 مليون") == ["2019"]


def test_structure_requires_numbered_skeleton_and_roadmap_only():
    """إعادة كتابة إنسانية: ما يثبت هو «## N. العنوان» بترتيبه وعنوان خارطة الدخول؛
    العناوين الفرعية والفقرات حرّة (مرساة القالب `_CLIENT_SECTION_BY_ORDINAL`)."""
    orig = ("## 1. الخلاصة التنفيذية\nنص\n## 2. المنهجية\nنص\n### أرقام القرار\nنص\n"
            "## 10. التوصيات\nنص\n### خارطة طريق الدخول (٩٠ يوماً)\nخطوات")
    assert RR.section_heads(orig) == ["1. الخلاصة التنفيذية", "2. المنهجية", "10. التوصيات"]
    free = orig.replace("### أرقام القرار\nنص", "ما يعنيه هذا لقرارك: فقرة طبيعية") \
               .replace("##   1.", "## 1.")
    assert RR.structure_issues(orig, free) == []
    dropped = orig.replace("## 2. المنهجية\nنص\n", "")
    assert [i["check"] for i in RR.structure_issues(orig, dropped)] == ["missing_sections"]
    assert RR.structure_issues(orig, dropped)[0]["items"] == ["2. المنهجية"]
    reordered = orig.replace("## 1. الخلاصة التنفيذية\nنص\n## 2. المنهجية\nنص\n",
                             "## 2. المنهجية\nنص\n## 1. الخلاصة التنفيذية\nنص\n")
    assert [i["check"] for i in RR.structure_issues(orig, reordered)] == ["section_order"]
    no_map = orig.replace("### خارطة طريق الدخول (٩٠ يوماً)", "### الخطوات")
    assert [i["check"] for i in RR.structure_issues(orig, no_map)] == ["missing_roadmap_subhead"]
    retitled_sub = orig.replace("### خارطة طريق الدخول (٩٠ يوماً)", "### Entry roadmap (90 days)")
    assert RR.structure_issues(orig, retitled_sub) == []


def test_figures_from_evidence_are_allowed_but_unsourced_are_not():
    """زيادة الدقة: رقمٌ من الأدلة المسنَدة يصحّح النصّ؛ رقمٌ لا في الأصل ولا الأدلة مرفوض."""
    orig = "## 1. الخلاصة التنفيذية\n" + "واردات 38 مليون دولار بحسب كومتريد. " * 8
    evidence = "سجلّ الحقائق — نمو الواردات: 7% [المصدر: UN Comtrade 2023]"
    fixed = orig.replace("واردات 38 مليون دولار", "واردات 38 مليون دولار بنمو 7% (2023)")
    assert RR.verify(fixed, orig, evidence) == []
    assert [f["check"] for f in RR.verify(fixed, orig)] == ["new_figures"]
    invented = orig.replace("38 مليون", "41 مليون")
    assert RR.verify(invented, orig, evidence)[0]["items"] == ["41"]


def test_ledger_placeholders_must_survive_verbatim_and_none_added():
    """`{{…}}` يملؤها silk_fact_ledger عند التصيير (الدرس ٢٦٢) — ضياعُها رقمٌ يتجمّد بلا رصد."""
    orig = "## 1. الخلاصة التنفيذية\n" + "واردات {{imports_value}} ({{status:imports_value}}). " * 6
    assert RR.placeholders(orig) == ["{{imports_value}}", "{{status:imports_value}}"]
    lost = RR.verify(orig.replace("{{status:imports_value}}", "مرصودة"), orig)
    assert [f["check"] for f in lost] == ["missing_placeholders"]
    assert lost[0]["items"] == ["{{status:imports_value}}"]
    added = RR.verify(orig + "\nو{{share_pct}}", orig)
    assert [f["check"] for f in added] == ["new_placeholders"]
    assert RR.verify(orig.replace("واردات", "الواردات المرصودة"), orig) == []


def test_verify_rejects_empty_truncated_and_new_figures_together():
    orig = "## 1. الخلاصة التنفيذية\n" + "جملة طويلة بما يكفي للمقارنة. " * 10 + "\n## 2. المنهجية\nنص"
    assert [f["check"] for f in RR.verify("", orig)] == ["empty"]
    checks = [f["check"] for f in RR.verify("## 1. الخلاصة التنفيذية\nنمو 12%", orig)]
    assert checks == ["truncated", "missing_sections", "new_figures"]
    assert RR.verify(orig.replace("جملة طويلة", "عبارة مطوَّلة"), orig) == []


def test_apply_keeps_first_original_and_counts_refinements():
    node = {"report": "أصل", "review_cycles": 1, "unresolved_notes": []}
    n1 = RR.apply(node, "تنقيح ١", now="2026-10-20T00:00:00+00:00")
    assert node["report"] == "أصل"                       # العقدة الأصلية لم تُمَسّ
    assert (n1["report"], n1["report_original"], n1["refined_count"],
            n1["refined_via"], n1["refined_at"]) == (
        "تنقيح ١", "أصل", 1, "mcp", "2026-10-20T00:00:00+00:00")
    n2 = RR.apply(n1, "تنقيح ٢")
    assert n2["report_original"] == "أصل" and n2["refined_count"] == 2


# ── (٢) نقطة النهاية POST /analyses/{id}/report/refined ────────────────────
pytest.importorskip("fastapi")
pytest.importorskip("httpx")


def _seed():
    from tools.gen_academic_sample import academic_sample_blob
    import silk_storage
    blob = academic_sample_blob()
    return silk_storage.save_analysis(blob), blob["deep_research"]["report"]["report"]


def _client():
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


_H = {"X-API-Key": "secret"}
_REPHRASED = ("ولا تتوافر بذلك أرضية يقين كافية", "ولا تكفي الأرضية الراهنة من اليقين")


def test_get_refinable_report_returns_stored_writer_text_not_client_document():
    """سطح التنقيح هو النصّ المخزَّن نفسه — لا المستند المعروض (مراجعة §58 ١)."""
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _env(SILK_API_KEY="secret", SILK_DB=db, SILK_HERMETIC="1"), \
            patch("requests.get", side_effect=OSError("no network")):
        aid, original = _seed()
        c = _client()
        assert c.get(f"/analyses/{aid}/report/refined").status_code == 401
        r = c.get(f"/analyses/{aid}/report/refined", headers=_H)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["markdown"] == original and d["refined_count"] == 0
        assert d["has_original"] is False and d["sections"][0] == "1. الخلاصة التنفيذية"
        assert d["gate"]["verdict"] and isinstance(d["gate"]["fail_drivers"], list)
        assert isinstance(d["gate"]["notes"], list)
        # الأدلة بمصادرها — أرضية المراجعة النهائية.
        ev = c.get(f"/analyses/{aid}/evidence", headers=_H)
        assert ev.status_code == 200 and ev.json()["chars"] == len(ev.json()["context"])
        assert "المصدر" in ev.json()["context"] or "سجلّ الحقائق" in ev.json()["context"]
        assert c.get(f"/analyses/{aid}/evidence").status_code == 401
        # الجولة الكاملة بلا تغيير: ما سُحب يُعاد ويُقبَل — صيغةٌ واحدة في الاتجاهين.
        md_before = c.get(f"/analyses/{aid}/report.md", headers=_H).text
        r = c.post(f"/analyses/{aid}/report/refined", json={"markdown": d["markdown"]},
                   headers=_H)
        assert r.status_code == 200, r.text
        md_after = c.get(f"/analyses/{aid}/report.md", headers=_H).text
        # لا قالبٌ داخل قالب: عنوان الخلاصة مرّةً واحدة قبلَ وبعد.
        assert md_after.count("الخلاصة التنفيذية") == md_before.count("الخلاصة التنفيذية")
        assert c.get(f"/analyses/{aid}/report/refined", headers=_H).json()["refined_count"] == 1


def test_refined_report_is_stored_original_kept_and_exports_follow():
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _env(SILK_API_KEY="secret", SILK_DB=db, SILK_HERMETIC="1"), \
            patch("requests.get", side_effect=OSError("no network")):
        import silk_storage
        aid, original = _seed()
        assert _REPHRASED[0] in original
        refined = original.replace(*_REPHRASED)
        c = _client()
        r = c.post(f"/analyses/{aid}/report/refined", json={"markdown": refined},
                   headers=_H)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["saved"] is True and body["refined_count"] == 1
        assert body["export"]["docx"] == f"/analyses/{aid}/report.docx"
        node = silk_storage.get_analysis(aid)["deep_research"]["report"]
        assert node["report"] == refined.strip()
        assert node["report_original"] == original and node["refined_via"] == "mcp"
        # التصدير يتبع النصّ المنقَّح — القالب والبوّابة نفسهما.
        md = c.get(f"/analyses/{aid}/report.md", headers=_H)
        assert md.status_code == 200 and _REPHRASED[1] in md.text


def test_refined_report_with_new_figure_is_rejected_without_saving():
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _env(SILK_API_KEY="secret", SILK_DB=db, SILK_HERMETIC="1"), \
            patch("requests.get", side_effect=OSError("no network")):
        import silk_storage
        aid, original = _seed()
        c = _client()
        # رقمان لا في النصّ ولا في أدلة الدراسة (الأرقام المسنَدة وحدها تمرّ).
        r = c.post(f"/analyses/{aid}/report/refined",
                   json={"markdown": original + "\nوبلغت الحصة 73.91% عام 1987."},
                   headers=_H)
        assert r.status_code == 409
        d = r.json()["detail"]
        assert d["error"] == "refined_report_rejected"
        new = [f for f in d["findings"] if f["check"] == "new_figures"]
        assert new and set(new[0]["items"]) == {"73.91", "1987"}
        node = silk_storage.get_analysis(aid)["deep_research"]["report"]
        assert node["report"] == original and "report_original" not in node


def test_human_rewrite_inside_sections_is_accepted_and_exported():
    """إعادة كتابة فعلية: فقرة الخلاصة تُستبدل كاملةً بصياغة إنسانية (أرقامها من الأصل)،
    والهيكل المرقّم ثابت ⇒ تُقبَل وتصدر في Markdown العميل."""
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _env(SILK_API_KEY="secret", SILK_DB=db, SILK_HERMETIC="1"), \
            patch("requests.get", side_effect=OSError("no network")):
        aid, original = _seed()
        head, rest = original.split("\n## 2.", 1)
        human = ("## 1. الخلاصة التنفيذية\n"
                 "نقول للقارئ بوضوح: السوق موجود لكنه ليس ناضجاً لقرار استثماري بعد. "
                 "تُظهر بيانات UN Comtrade واردات تقارب 9 ملايين دولار في 2023 تحت الرمز "
                 "040510، في سوق مرتفع التركّز (HHI 2900)، ونوصي بمراقبته بثقة منخفضة (50%) "
                 "حتى تُغلَق فجوة التصنيف الجمركي وتُوثَّق قناة التوزيع.\n"
                 "ماذا يعني هذا لقرارك: لا تلتزم استثمارياً الآن؛ ابدأ بملف التصنيف والقناة.")
        refined = human + "\n## 2." + rest
        assert RR.extract_figures(human) <= RR.extract_figures(head)
        c = _client()
        r = c.post(f"/analyses/{aid}/report/refined", json={"markdown": refined}, headers=_H)
        assert r.status_code == 200, r.text
        md = c.get(f"/analyses/{aid}/report.md", headers=_H)
        assert md.status_code == 200 and "ليس ناضجاً لقرار استثماري بعد" in md.text


def test_refined_report_missing_section_head_or_truncated_is_rejected():
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _env(SILK_API_KEY="secret", SILK_DB=db, SILK_HERMETIC="1"), \
            patch("requests.get", side_effect=OSError("no network")):
        aid, original = _seed()
        c = _client()
        r = c.post(f"/analyses/{aid}/report/refined",
                   json={"markdown": original.replace("## 2. منهجية البحث ونطاقه", "منهجية")},
                   headers=_H)
        assert r.status_code == 409
        assert [f["check"] for f in r.json()["detail"]["findings"]] == ["missing_sections"]
        r = c.post(f"/analyses/{aid}/report/refined",
                   json={"markdown": "## 1. الخلاصة التنفيذية\nقصير"}, headers=_H)
        assert r.status_code == 409
        assert "truncated" in [f["check"] for f in r.json()["detail"]["findings"]]
        r = c.post(f"/analyses/{aid}/report/refined",
                   json={"markdown": original + "\n{{status:share_pct}}"}, headers=_H)
        assert r.status_code == 409
        assert [f["check"] for f in r.json()["detail"]["findings"]] == ["new_placeholders"]


def test_refined_report_blocked_by_delivery_gate_is_not_saved():
    """عبارةٌ رفضها المالك (الدرس ٢٩٦) في النصّ المنقَّح ⇒ بوّابة التسليم FAIL ⇒
    409 `quality_gate_fail` والتقرير المخزَّن كما هو — لا يُلتَفّ على البوّابة من MCP."""
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _env(SILK_API_KEY="secret", SILK_DB=db, SILK_HERMETIC="1"), \
            patch("requests.get", side_effect=OSError("no network")):
        import silk_storage
        aid, original = _seed()
        c = _client()
        bad = original.replace("اعتمدت الدراسة منهجاً",
                               "يسجل مستنتج من أرقام مرصودة. اعتمدت الدراسة منهجاً")
        assert bad != original
        r = c.post(f"/analyses/{aid}/report/refined", json={"markdown": bad}, headers=_H)
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["error"] == "quality_gate_fail"
        assert "owner_flagged_phrase" in d.get("fail_drivers", [])
        node = silk_storage.get_analysis(aid)["deep_research"]["report"]
        assert node["report"] == original and "refined_at" not in node


def test_refined_report_endpoint_contracts_auth_missing_nonresearch_body():
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with _env(SILK_API_KEY="secret", SILK_DB=db, SILK_HERMETIC="1"), \
            patch("requests.get", side_effect=OSError("no network")):
        import silk_storage
        aid, original = _seed()
        c = _client()
        assert c.post(f"/analyses/{aid}/report/refined",
                      json={"markdown": original}).status_code == 401
        assert c.post("/analyses/999999/report/refined",
                      json={"markdown": original}, headers=_H).status_code == 404
        assert c.post(f"/analyses/{aid}/report/refined", json={}, headers=_H).status_code == 422
        plain = silk_storage.save_analysis(
            {"product": "تمور", "hs_code": "080410", "year": 2023, "markets": []})
        assert c.post(f"/analyses/{plain}/report/refined",
                      json={"markdown": original}, headers=_H).status_code == 400


def test_refined_endpoint_makes_no_claude_call():
    """المسار كلّه حتمي — لا استيراد لطبقة كلود داخل نقطة النهاية ولا في الوحدة."""
    tree = ast.parse((_ROOT / "silk_refined_report.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "re", "datetime"}, imported   # حتمي: لا كلود ولا شبكة
    api_src = (_ROOT / "api.py").read_text(encoding="utf-8")
    start = api_src.index("    def _refined_gate(found: dict) -> dict:")
    end = api_src.index('@app.post("/analyses/{analysis_id}/enrich-leads")', start)
    body = api_src[start:end]
    assert "silk_ai_judge" not in body and "_free_ai_extras_allowed" not in body
    # لا نداءَ تحضيرِ نثرٍ (يستدعي كلود مدفوعاً) — يُذكَر في الوثائق فقط، لا يُنادى.
    assert "prepare_fallback_prose(" not in body
    assert "silk_export_gate" in body and body.count("_require_key(request)") == 3  # GET refined + GET evidence + POST


# ── (٣) خادم MCP — tools/silk_mcp.py ────────────────────────────────────────
def _mcp():
    import importlib
    return importlib.import_module("tools.silk_mcp")


def test_mcp_server_imports_stdlib_only():
    """المالك يشغّله على جهازه بـpython3 عارٍ — لا pip install."""
    tree = ast.parse((_ROOT / "tools" / "silk_mcp.py").read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods <= {"json", "os", "sys", "urllib", "__future__"}, mods


def test_mcp_handshake_tools_list_and_unknown_method():
    m = _mcp()
    init = m.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                "clientInfo": {"name": "t", "version": "1"}}})
    assert init["id"] == 1 and init["result"]["protocolVersion"] == "2025-03-26"
    future = m.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2031-01-01"}})
    assert future["result"]["protocolVersion"] == m.SUPPORTED_PROTOCOLS[0]
    assert "tools" in init["result"]["capabilities"]
    assert m.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert m.handle({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}
    tools = m.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})["result"]["tools"]
    assert [t["name"] for t in tools] == ["start_study", "study_status", "download_report",
                                          "list_studies", "get_evidence", "get_report",
                                          "submit_refined_report"]
    assert "إعادة كتابة إنسانية" in next(t for t in tools if t["name"] == "get_report")["description"]
    assert "مدفوع" in next(t for t in tools if t["name"] == "start_study")["description"]
    for t in tools:
        assert t["inputSchema"]["type"] == "object" and t["description"]
    err = m.handle({"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
    assert err["error"]["code"] == -32601


def test_mcp_tools_proxy_to_silk_api_with_key_header(monkeypatch):
    """كل أداة نداءٌ واحد على نقطة النهاية الصحيحة بمفتاح X-API-Key؛ 409 يعود
    isError بنصّ الملاحظات لا انهياراً."""
    m = _mcp()
    seen = []

    def fake_http(method, path, body=None):
        seen.append((method, path, body))
        if path.startswith("/analyses?limit="):
            return 200, json.dumps([{"id": 7, "product": "قهوة", "market_name": "Bahrain",
                                     "created_at": "2026-10-15", "kind": "research",
                                     "status": "completed", "verdict_label": "دخول مشروط"}])
        if method == "GET" and path.endswith("/report/refined"):
            return 200, json.dumps({"analysis_id": 7, "markdown": "## 1. الخلاصة التنفيذية\nنص الكاتب",
                                    "refined_count": 2, "placeholders": ["{{x}}"],
                                    "gate": {"verdict": "FAIL", "fail_drivers": ["owner_flagged_phrase"],
                                             "notes": ["عبارةٌ رفضها المالك: «يسجل مستنتج»"]}})
        if method == "GET" and path.endswith("/evidence"):
            return 200, json.dumps({"analysis_id": 7, "context": "سجلّ الحقائق — الواردات: 38 مليون [المصدر: Comtrade]", "chars": 55})
        if method == "POST" and path.endswith("/report/refined"):
            return 409, json.dumps({"detail": {"error": "refined_report_rejected",
                                               "findings": [{"check": "new_figures",
                                                             "items": ["17"]}]}})
        return 500, "boom"

    monkeypatch.setattr(m, "_http", fake_http)
    monkeypatch.setenv("SILK_BASE_URL", "https://silk.test")

    def call(name, args):
        return m.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                         "params": {"name": name, "arguments": args}})["result"]

    out = call("list_studies", {"limit": 5})
    assert out["isError"] is False and "قهوة | Bahrain" in out["content"][0]["text"]
    out = call("get_report", {"analysis_id": 7})
    assert out["isError"] is False and len(out["content"]) == 2
    note, text = out["content"][0]["text"], out["content"][1]["text"]
    assert "FAIL" in note and "owner_flagged_phrase" in note and "2" in note
    assert "يسجل مستنتج" in note                      # ملاحظات البوّابة تصل المنقِّح
    assert text == "## 1. الخلاصة التنفيذية\nنص الكاتب"      # النصّ المخزَّن نفسه، بلا ترويسة
    out = call("get_evidence", {"analysis_id": 7})
    assert out["isError"] is False and "Comtrade" in out["content"][1]["text"]
    out = call("submit_refined_report", {"analysis_id": 7, "markdown": "x"})
    assert out["isError"] is True and "17" in out["content"][0]["text"]
    assert seen == [("GET", "/analyses?limit=5", None),
                    ("GET", "/analyses/7/report/refined", None),
                    ("GET", "/analyses/7/evidence", None),
                    ("POST", "/analyses/7/report/refined", {"markdown": "x"})]
    out = call("nope", {})
    assert out["isError"] is True
    # 200 ليس JSON (صفحة وسيط) ⇒ خطأُ عنوانٍ صريح، لا «وسائط غير صالحة».
    monkeypatch.setattr(m, "_http", lambda *a, **k: (200, "<html>maintenance</html>"))
    out = call("list_studies", {})
    assert out["isError"] is True
    assert "SILK_BASE_URL" in out["content"][0]["text"] and "وسائط" not in out["content"][0]["text"]


def test_mcp_http_layer_sends_api_key_and_json_body(monkeypatch):
    """طبقة HTTP الحقيقية (urllib) — بلا شبكة: نلتقط الطلب المُجهَّز."""
    m = _mcp()
    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = req.data
        return _Resp()

    monkeypatch.setenv("SILK_BASE_URL", "https://silk.test/")
    monkeypatch.setenv("SILK_API_KEY", "k-123")
    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    assert m._http("POST", "/analyses/3/report/refined", {"markdown": "نص"}) == (200, "ok")
    assert captured["url"] == "https://silk.test/analyses/3/report/refined"
    assert captured["method"] == "POST" and captured["headers"]["x-api-key"] == "k-123"
    assert json.loads(captured["body"].decode("utf-8")) == {"markdown": "نص"}


def test_mcp_serve_loop_is_line_delimited_and_survives_bad_input(monkeypatch):
    m = _mcp()
    monkeypatch.setattr(m, "_http", lambda *a, **k: (
        200, json.dumps({"markdown": "## 1. x", "gate": {}, "placeholders": []})))
    monkeypatch.setenv("SILK_BASE_URL", "https://silk.test")
    lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
             "not json",
             json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
             json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": "get_report", "arguments": {"analysis_id": 1}}})]
    out = io.BytesIO()
    m.serve(io.BytesIO(("\n".join(lines) + "\n").encode("utf-8")), out)
    replies = [json.loads(l) for l in out.getvalue().decode("utf-8").splitlines()]
    assert [r.get("id") for r in replies] == [1, None, 2]
    assert replies[1]["error"]["code"] == -32700
    assert replies[2]["result"]["content"][1]["text"] == "## 1. x"
    assert replies[0]["result"]["protocolVersion"] == m.SUPPORTED_PROTOCOLS[0]


# ── (٤) المسار الكامل من كلود: بدء الدراسة، المتابعة، التنزيل ──────────────
def _fake_start_http(readiness: dict, research_status=200, research_body=None):
    seen = []

    def fake(method, path, body=None, raw=False):
        seen.append((method, path, body))
        if path.startswith("/research/readiness?"):
            return 200, json.dumps(readiness, ensure_ascii=False)
        if path == "/research":
            return research_status, json.dumps(
                research_body if research_body is not None else {"analysis_id": 42, "status": "running"})
        return 500, "boom"
    return fake, seen


def _call(m, name, args):
    return m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})["result"]


def test_start_study_blocked_readiness_spends_nothing(monkeypatch):
    m = _mcp()
    fake, seen = _fake_start_http({"checks": [{"key": "market", "label_ar": "السوق المستهدفة",
                                               "status": "blocked", "detail_ar": "سوق غامضة",
                                               "blocking": True}],
                                   "can_run": False, "needs_ack": False})
    monkeypatch.setattr(m, "_http", fake)
    out = _call(m, "start_study", {"product": "تمور", "market": "هولاندا؟"})
    assert out["isError"] is True and "سوق غامضة" in out["content"][0]["text"]
    assert [p for _, p, _ in seen if p == "/research"] == []       # لا POST ⇒ لا إنفاق


def test_start_study_advisory_requires_owner_ack_then_starts(monkeypatch):
    m = _mcp()
    readiness = {"checks": [{"key": "producer", "label_ar": "بلد منشأ منتِج",
                             "status": "advisory", "detail_ar": "السوق من كبار المصدّرين",
                             "blocking": False}],
                 "can_run": True, "needs_ack": True}
    fake, seen = _fake_start_http(readiness)
    monkeypatch.setattr(m, "_http", fake)
    out = _call(m, "start_study", {"product": "تمور", "market": "مصر"})
    assert out["isError"] is True and "ack=true" in out["content"][0]["text"]
    assert all(p != "/research" for _, p, _ in seen)
    out = _call(m, "start_study", {"product": "تمور", "market": "مصر", "hs_code": "080410",
                                   "production_cost_per_unit": 2.5, "ack": True})
    assert out["isError"] is False and "42" in out["content"][0]["text"]
    post = [b for mth, p, b in seen if p == "/research"][0]
    assert post["async_run"] is True and post["persist"] is True
    assert post["hs_code"] == "080410" and post["production_cost_per_unit"] == 2.5
    assert post["advisories_ack"] and post["producer_ack"] and post["hs_confirmed"] is True


def test_start_study_without_ack_sends_no_acknowledgements(monkeypatch):
    """الموافقات لا تُمرَّر إلا حين أعطاها المالك صراحةً — لا تجاوز صامت لاستشاري."""
    m = _mcp()
    fake, seen = _fake_start_http({"checks": [], "can_run": True, "needs_ack": False})
    monkeypatch.setattr(m, "_http", fake)
    out = _call(m, "start_study", {"product": "عسل", "market": "اليابان"})
    assert out["isError"] is False
    post = [b for _, p, b in seen if p == "/research"][0]
    assert "advisories_ack" not in post and "producer_ack" not in post and "hs_code" not in post


def test_start_study_server_refusal_is_reported_not_swallowed(monkeypatch):
    m = _mcp()
    fake, _ = _fake_start_http({"checks": [], "can_run": True, "needs_ack": False},
                               research_status=422,
                               research_body={"detail": {"error": "hs_unconfirmed", "reason": "أكّد الرمز"}})
    monkeypatch.setattr(m, "_http", fake)
    out = _call(m, "start_study", {"product": "عسل", "market": "اليابان"})
    assert out["isError"] is True and "hs_unconfirmed" in out["content"][0]["text"]


def test_study_status_summarizes_progress_and_next_step(monkeypatch):
    m = _mcp()
    payload = {"analysis_id": 5, "status": "running", "product": "قهوة", "stage": "writer",
               "stage_label": "كاتب التقرير", "elapsed_seconds": 310, "llm_calls": 14,
               "cost_usd_estimate": 0.42, "cost_unpriced_models": [],
               "missions_completed": 12, "missions_total": 12, "report_present": False}
    monkeypatch.setattr(m, "_http", lambda *a, **k: (200, json.dumps(payload, ensure_ascii=False)))
    txt = _call(m, "study_status", {"analysis_id": 5})["content"][0]["text"]
    assert "12/12" in txt and "0.42$" in txt and "كاتب التقرير" in txt and "ما زالت تعمل" in txt
    payload.update(status="completed", report_present=True)
    txt = _call(m, "study_status", {"analysis_id": 5})["content"][0]["text"]
    assert "get_report" in txt and "download_report" in txt
    payload.update(status="failed", skip_reason="نفاد الاعتمادات")
    assert "نفاد الاعتمادات" in _call(m, "study_status", {"analysis_id": 5})["content"][0]["text"]


def test_download_report_writes_file_to_owner_dir_and_respects_gate(monkeypatch, tmp_path):
    m = _mcp()
    monkeypatch.setenv("SILK_DOWNLOAD_DIR", str(tmp_path / "out"))
    seen = []

    def fake(method, path, body=None, raw=False):
        seen.append((path, raw))
        if path.endswith("report.docx"):
            return 200, b"PK\x03\x04docx-bytes"
        if path.endswith("report.pdf"):
            return 409, json.dumps({"detail": {"error": "quality_gate_fail",
                                               "fail_drivers": ["owner_flagged_phrase"]}})
        return 500, "boom"
    monkeypatch.setattr(m, "_http", fake)
    out = _call(m, "download_report", {"analysis_id": 3})
    assert out["isError"] is False
    saved = str(tmp_path / "out" / "silk-3.docx")
    assert saved in out["content"][0]["text"]
    assert open(saved, "rb").read() == b"PK\x03\x04docx-bytes"
    assert seen == [("/analyses/3/report.docx", True)]
    out = _call(m, "download_report", {"analysis_id": 3, "format": "pdf"})
    assert out["isError"] is True and "owner_flagged_phrase" in out["content"][0]["text"]
    assert not (tmp_path / "out" / "silk-3.pdf").exists()
    out = _call(m, "download_report", {"analysis_id": 3, "format": "exe"})
    assert out["isError"] is True and "format" in out["content"][0]["text"]
