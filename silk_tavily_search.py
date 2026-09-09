"""Opt-in basic Tavily search; original pages only, no generated answer."""
import os
from urllib.parse import urlsplit
from silk_data_layer import DataPoint, _today

SOURCE = "Web Search (Tavily)"


def search(query, num=5, gl=None, hl=None):
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return [DataPoint(None, SOURCE, 0.0, "يتطلب البحث الاحتياطي TAVILY_API_KEY", _today())]
    try:
        from silk_data_layer import throttled_request
        limit = max(1, min(20, int(num)))
        body = {"query": query, "search_depth": "basic", "max_results": limit,
                "topic": "general", "include_answer": False, "include_raw_content": False,
                "include_images": False, "auto_parameters": False}
        if hl:
            body["language"] = str(hl).strip().lower()
        response = throttled_request("POST", "https://api.tavily.com/search",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            json_body=body, timeout=30)
        response.raise_for_status()
        rows = (response.json() or {}).get("results") or []
        findings, seen = [], set()
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname \
                    or parsed.username or parsed.password or url in seen:
                continue
            title, snippet = str(row.get("title") or ""), str(row.get("content") or "")
            if not title and not snippet:
                continue
            seen.add(url)
            findings.append(DataPoint({"title": title, "snippet": snippet, "link": url},
                SOURCE, .5, "نتيجة بحث ويب؛ يلزم التحقق من الصفحة الأصلية.", _today(),
                url=url, retrieval_method="llm_web"))
        return findings or [DataPoint(None, SOURCE, 0.0,
            "لم يرجع البحث الاحتياطي نتائج قابلة للإسناد.", _today(), status="no_record")]
    except Exception:
        return [DataPoint(None, SOURCE, 0.0,
            "تعذر بحث Tavily؛ تحقق من اتصال الخدمة وصلاحية المفتاح والرصيد المتاح.",
            _today(), status="fetch_failed")]
