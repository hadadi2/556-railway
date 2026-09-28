"""مسار التصدير `?style=study` (P2-1/P2-5): نتيجة /research مخزَّنة — ولو بلا بيانات —
تُسلَّم Markdown وWord بالعناوين الأحد عشر، والفجوات معلنة، بلا نداء نموذج."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HEADINGS = ["## الملخص التنفيذي", "## أولاً: حجم السوق واتجاهاته", "## ثانياً: خصائص الطلب وسلوك المستهلك",
             "## ثالثاً: البيئة التنافسية والتسعير", "## رابعاً: المتطلبات التنظيمية ومسار الدخول",
             "## خامساً: قنوات التوزيع والجهات المستهدفة", "## سادساً: المؤشرات المالية", "## سابعاً: المخاطر",
             "## ثامناً: الاعتبارات المضادة للتوصية", "## تاسعاً: خطة التنفيذ (90 يوماً)", "## المصادر وحدود الدراسة"]


def _fake_tools(system, messages, tools=None, max_tokens=None, model=None, timeout=None):
    return {"text": json.dumps({"findings": []}), "tool_calls": [], "stop_reason": "end_turn",
            "usage": {"input_tokens": 50, "output_tokens": 20}}


def _fake_call(system, user, max_tokens=1600, model=None, timeout=None):
    return json.dumps({"verdict": "WATCH", "confidence": 0.5, "reasoning": "ok"})


def _fake_writer(system, user, max_tokens=1600, model=None, timeout=None):
    return "## 1. الخلاصة التنفيذية\nتقرير تجريبي."


def test_study_style_exports_md_and_docx_even_with_all_data_gaps():
    from fastapi.testclient import TestClient
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "t", "SILK_API_KEY": "s", "SILK_RATE_LIMIT": "100000",
                                 "SILK_DATA_DIR": tempfile.mkdtemp()}), \
            patch("silk_llm_runtime._call_tools", side_effect=_fake_tools), \
            patch("silk_synthesis._call", side_effect=_fake_call), \
            patch("silk_ai_judge._call", side_effect=_fake_writer), \
            patch("silk_data_layer._cached_get", return_value=None), \
            patch("silk_data_layer._http_get", side_effect=OSError("no net")), \
            patch("silk_storage._db_path", return_value=db):
        import api
        client = TestClient(api.create_app())
        hdr = {"X-API-Key": "s"}
        r = client.post("/research", headers=hdr, json={
            "product": "قهوة محمصة", "market": "Malaysia", "hs_code": "090121",
            "persist": True, "async_run": True, "hs_confirmed": True})
        assert r.status_code == 202, r.text
        aid = r.json()["analysis_id"]
        for _ in range(3000):
            st = client.get(f"/research/{aid}/status", headers=hdr).json()
            if st.get("status") and st["status"] != "running":
                break
            time.sleep(0.01)
        md = client.get(f"/analyses/{aid}/report.md", headers=hdr, params={"style": "study"})
        assert md.status_code == 200, md.text[:300]
        text = md.text
        for h in _HEADINGS:
            assert h in text, h
        assert "ما لم يتسنّ توثيقه" in text and "سلسلة الواردات السنوية" in text
        assert "[" not in text.replace("[", "", 0) or "]" not in text  # لا نائب
        dx = client.get(f"/analyses/{aid}/report.docx", headers=hdr, params={"style": "study"})
        assert dx.status_code == 200, dx.text[:300]
        from docx import Document
        doc = Document(io.BytesIO(dx.content))
        heads = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
        for h in _HEADINGS:
            assert h[3:] in heads, h
