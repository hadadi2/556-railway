"""Agent Reach's Exa web-search backend, using its public read-only MCP tool.

No browser credentials, generated answer, subprocess, or automatic paid fallback.
This adapter does not claim authenticated LinkedIn access or video transcription.
"""
import json
import re
from urllib.parse import urlsplit

from silk_data_layer import DataPoint, _today

ENDPOINT = "https://mcp.exa.ai/mcp"
SOURCE = "Web Search (Exa via Agent Reach)"


def _message(response):
    response.encoding = "utf-8"
    text = response.text
    if len(text) > 2_000_000:
        raise ValueError("Search response too large")
    if text.lstrip().startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        if line.startswith("data:"):
            data = json.loads(line[5:].strip())
            if "result" in data or "error" in data:
                return data
    raise ValueError("Missing MCP result")


def _results(payload, limit):
    if payload.get("error") or (payload.get("result") or {}).get("isError"):
        raise ValueError("Search provider rejected request")
    result = payload.get("result") or {}
    findings = []
    seen = set()
    for block in result.get("content") or []:
        if block.get("type") != "text":
            continue
        # Exa supplies titled source records, each with its original URL.
        for record in re.split(r"(?m)(?=^Title: )", block.get("text") or ""):
            match = re.match(r"Title: ([^\n]+)\nURL: (https?://[^\s]+)\n([\s\S]*)", record)
            if not match:
                continue
            title, url, excerpt = match.groups()
            parsed = urlsplit(url)
            if not parsed.hostname or parsed.username or parsed.password or url in seen:
                continue
            seen.add(url)
            findings.append(DataPoint({"title": title.strip(), "snippet": excerpt.strip(), "link": url},
                SOURCE, .5, "نتيجة بحث من صفحة عامة؛ لا تثبت وحدها استيراد المنتج أو صحة كل ادعاء.",
                _today(), url=url, retrieval_method="llm_web"))
            if len(findings) >= limit:
                return findings
    return findings


def search(query, num=5, gl=None, hl=None):
    from silk_data_layer import throttled_request
    try:
        limit = max(1, min(int(num), 10))
        response = throttled_request("POST", ENDPOINT,
            headers={"Accept": "application/json, text/event-stream"},
            json_body={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "web_search_exa", "arguments": {"query": query, "numResults": limit}}},
            timeout=30)
        response.raise_for_status()
        findings = _results(_message(response), limit)
        return findings or [DataPoint(None, SOURCE, 0.0,
            "لم يرجع البحث نتائج قابلة للإسناد إلى صفحات عامة.", _today(), status="no_record")]
    except Exception:
        return [DataPoint(None, SOURCE, 0.0,
            "تعذر بحث Exa عبر Agent Reach؛ قد يكون حد الاستخدام أو اتصال المصدر. لم تُنشأ نتائج بديلة.",
            _today(), status="fetch_failed")]
