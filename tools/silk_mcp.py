#!/usr/bin/env python3
"""خادم MCP لمراجعة تقارير Silk داخل كلود — Silk MCP server (stdio، مكتبة قياسية فقط).

قرار المالك (2026-10-20): التقرير يُنتَج في Silk كالمعتاد، ثم يراجعه المالك
وينقّحه في كلود (Desktop أو Code) على اشتراكه — لا نداء API مدفوعاً من الخادم —
ثم يعيده إلى Silk فتصدر ملفات العميل (docx/pdf/md) من النصّ المنقَّح بالقالب
الرسمي، بعد بوّابة التسليم الحتمية نفسها.

ثلاث أدوات فقط (YAGNI): `list_studies` · `get_report` · `submit_refined_report`.
`get_report` يسحب **نصّ الكاتب المخزَّن** (`GET /analyses/{id}/report/refined`) لا
المستند المعروض للعميل — وهو نفسُ ما يُعاد في `submit_refined_report`، فالطرفان
صيغةٌ واحدة (مراجعة §58). الخادم وكيلٌ رقيق فوق HTTP API القائم — لا منطق أعمال
هنا؛ كل فحصٍ يجري في الخادم فلا يُلتَفّ على البوّابات من هذا الباب.

التشغيل (على جهاز المالك):
  SILK_BASE_URL=https://<railway-domain>  SILK_API_KEY=<key>  python3 tools/silk_mcp.py
التفصيل والإعداد في كلود: docs/MCP_OWNER_REVIEW.md
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

VERSION = "0.2.0"
# إصدارات البروتوكول التي يطبّقها هذا الخادم فعلاً (الأحدث أولاً). غير المعروف
# من العميل يُجاب بأحدثها — لا ادّعاءُ دعمٍ لما لا نعرفه (مراجعة §58، الملاحظة ١٠).
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
TIMEOUT_S = 120

_REVIEW_RULES = (
    "قواعد التنقيح (يفرضها الخادم حتمياً عند الإرجاع ويرفض بلا حفظ): "
    "١) لا رقم ولا نسبة ولا سنة غير واردة في النص — انسخ الأرقام كما هي؛ "
    "٢) أبقِ كل سطر عنوان (#/##/###) حرفياً وبترتيبه؛ "
    "٣) أبقِ كل عنصر «{{…}}» حرفياً في مكانه — يُملأ آلياً بقيمته عند التصيير؛ "
    "٤) أعد النص كاملاً لا قسماً واحداً؛ "
    "٥) لا اسم جهة أو علامة أو ادّعاء سببي غير وارد في النص، ولا تركيب رقمَين في ادّعاء جديد؛ "
    "٦) لغة عميل تجاري: لا «بعثة/وكيل/نداء/JSON/إذن ماذا»، ولا وصف لآلية البناء؛ "
    "٧) حسّن الوضوح والترابط والإيجاز فقط — المعنى والحكم والأرقام ثابتة."
)

TOOLS = [
    {
        "name": "list_studies",
        "description": "اسرد دراسات السوق المخزَّنة في Silk (الأحدث أولاً): المعرّف، "
                       "المنتج، السوق، التاريخ، النوع، الحالة والحكم. استعمله لاختيار "
                       "analysis_id قبل get_report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200,
                          "description": "عدد الصفوف (افتراضياً 20)"}},
            "additionalProperties": False},
    },
    {
        "name": "get_report",
        "description": "اسحب نصّ تقرير الدراسة المخزَّن القابل للتنقيح (Markdown بعناوين "
                       "وعناصر {{…}})، مع قرار بوّابة التسليم الحالي. تعود كتلتان: "
                       "الأولى ملاحظة قصيرة (البوّابة، العناصر)، والثانية النصّ نفسه — "
                       "وهو ما تنقّحه وتعيده كاملاً عبر submit_refined_report. " + _REVIEW_RULES,
        "inputSchema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "integer", "description": "معرّف الدراسة"}},
            "required": ["analysis_id"],
            "additionalProperties": False},
    },
    {
        "name": "submit_refined_report",
        "description": "أعد النصّ المنقَّح كاملاً إلى Silk ليحلّ مكان نصّ الكاتب وتصدر "
                       "منه ملفات العميل (Word/PDF/Markdown) بالقالب الرسمي. الخادم "
                       "يرفض (بلا حفظ) أي رقم جديد، أو عنوان أو عنصر {{…}} غائب أو "
                       "جديد، أو نصاً مبتوراً، أو ما تحجبه بوّابة التسليم — ويعيد "
                       "الملاحظات لتصحيحها وإعادة الإرسال. الأصل يُحفَظ دائماً.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "integer", "description": "معرّف الدراسة"},
                "markdown": {"type": "string",
                             "description": "النصّ المنقَّح كاملاً كما سُحب من get_report "
                                            "(الكتلة الثانية) بعد التنقيح"}},
            "required": ["analysis_id", "markdown"],
            "additionalProperties": False},
    },
]


# ── HTTP نحو Silk ────────────────────────────────────────────────────────────
def _base_url() -> str:
    url = os.environ.get("SILK_BASE_URL", "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SILK_BASE_URL غير مضبوط — عنوان خادم Silk (مثال: "
                           "https://silk.up.railway.app)")
    return url


def _http(method: str, path: str, body: dict | None = None) -> tuple[int, str]:
    """نداء HTTP واحد؛ يعيد (الحالة، النصّ). أخطاء HTTP تعود حالةً لا استثناءً
    (409 البوّابة حمولةٌ مقصودة للمالك). تُطعَّم في الاختبارات."""
    headers = {"Accept": "application/json, text/markdown;q=0.9, */*;q=0.1"}
    key = os.environ.get("SILK_API_KEY", "").strip()
    if key:
        headers["X-API-Key"] = key
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(_base_url() + path, data=data, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


class _NotJSON(Exception):
    """ردّ 200 ليس JSON (صفحة صيانة/بوّابة وسيطة) — خطأ عنوانٍ لا خطأ وسائط."""


def _json_body(path: str, text: str):
    try:
        return json.loads(text)
    except ValueError:
        raise _NotJSON(f"ردّ الخادم على {path} ليس JSON (أول ١٢٠ حرفاً: "
                       f"{text.strip()[:120]!r}) — تحقّق من SILK_BASE_URL") from None


def _detail(text: str) -> str:
    """نصٌّ مقروء من حمولة خطأ FastAPI (`{"detail": ...}`) أو النصّ كما هو."""
    try:
        data = json.loads(text)
    except ValueError:
        return text.strip()
    d = data.get("detail", data) if isinstance(data, dict) else data
    if isinstance(d, str):
        return d
    return json.dumps(d, ensure_ascii=False, indent=1)


# ── الأدوات — كلٌّ يعيد (كتلة نصّ أو قائمة كتل، is_error) ────────────────────
def _tool_list_studies(args: dict) -> tuple:
    limit = int(args.get("limit") or 20)
    path = f"/analyses?limit={max(1, min(limit, 200))}"
    status, text = _http("GET", path)
    if status != 200:
        return f"فشل جرد الدراسات ({status}): {_detail(text)}", True
    rows = _json_body(path, text)
    if not rows:
        return "لا دراسات مخزَّنة.", False
    lines = ["id | المنتج | السوق | التاريخ | النوع | الحالة | الحكم"]
    for r in rows:
        lines.append(" | ".join(str(r.get(k) or "—") for k in (
            "id", "product", "market_name", "created_at", "kind", "status",
            "verdict_label")))
    return "\n".join(lines), False


def _tool_get_report(args: dict) -> tuple:
    aid = int(args["analysis_id"])
    path = f"/analyses/{aid}/report/refined"
    status, text = _http("GET", path)
    if status != 200:
        return f"تعذّر سحب نصّ التقرير {aid} ({status}): {_detail(text)}", True
    data = _json_body(path, text)
    gate = data.get("gate") or {}
    drivers = gate.get("fail_drivers") or []
    note = (f"الدراسة {aid} · بوّابة التسليم الآن: {gate.get('verdict') or '—'}"
            + (f" (أسباب الحجب: {', '.join(drivers)})" if drivers else "")
            + f" · تنقيحات سابقة: {data.get('refined_count', 0)}"
            + f" · عناصر {{{{…}}}} تُبقى حرفياً: {len(data.get('placeholders') or [])}"
            + " — النصّ القابل للتنقيح في الكتلة التالية؛ أعده كاملاً إلى submit_refined_report.")
    return [note, data.get("markdown") or ""], False


def _tool_submit_refined(args: dict) -> tuple:
    aid = int(args["analysis_id"])
    md = str(args.get("markdown") or "")
    path = f"/analyses/{aid}/report/refined"
    status, text = _http("POST", path, {"markdown": md})
    if status == 200:
        data = _json_body(path, text)
        ex = data.get("export") or {}
        base = _base_url()
        return ("حُفظ التقرير المنقَّح للدراسة {aid} (تنقيح رقم {n}، بوّابة التسليم: {g}).\n"
                "ملفات العميل الآن من النصّ المنقَّح:\n- Word: {b}{d}\n- PDF: {b}{p}\n- Markdown: {b}{m}"
                ).format(aid=aid, n=data.get("refined_count"), g=data.get("gate"),
                         b=base, d=ex.get("docx", ""), p=ex.get("pdf", ""),
                         m=ex.get("md", "")), False
    if status == 409:
        return (f"رُفض التقرير المنقَّح للدراسة {aid} — لم يُحفَظ شيء. صحّح ثم أعد "
                f"الإرسال:\n{_detail(text)}"), True
    return f"تعذّر حفظ التقرير المنقَّح {aid} ({status}): {_detail(text)}", True


_HANDLERS = {
    "list_studies": _tool_list_studies,
    "get_report": _tool_get_report,
    "submit_refined_report": _tool_submit_refined,
}


def call_tool(name: str, args: dict) -> tuple[list[str], bool]:
    """تنفيذ أداة → (كتل نصّ، is_error). فشل الأداة نصٌّ للمالك لا انهيارٌ للخادم."""
    fn = _HANDLERS.get(name)
    if fn is None:
        return [f"أداة غير معروفة: {name}"], True
    try:
        out, is_error = fn(args or {})
    except _NotJSON as e:
        return [str(e)], True
    except (KeyError, TypeError, ValueError) as e:
        return [f"وسائط غير صالحة لـ{name}: {e}"], True
    except Exception as e:  # noqa: BLE001 — فشل الأداة يعود نصاً لا انهياراً للخادم
        return [f"فشل {name}: {type(e).__name__}: {e}"], True
    return (list(out) if isinstance(out, (list, tuple)) else [str(out)]), bool(is_error)


# ── JSON-RPC (MCP) ───────────────────────────────────────────────────────────
def _ok(mid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def negotiate_protocol(requested) -> str:
    """إصدار العميل إن كنّا نطبّقه، وإلا أحدث ما نطبّقه (نصّ المواصفة)."""
    return requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]


def handle(msg: dict) -> dict | None:
    """رسالة JSON-RPC واحدة → ردّ (أو None للإشعارات التي لا ردّ لها)."""
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}
    if method is None:
        return None            # ردٌّ من العميل (لا طلب) — يُتجاهَل
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": negotiate_protocol(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "silk", "version": VERSION},
            "instructions": ("Silk: دراسات سوق للمصدّر السعودي. المسار: list_studies ← "
                             "get_report ← تنقيح ← submit_refined_report. " + _REVIEW_RULES),
        })
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        blocks, is_error = call_tool(str(params.get("name") or ""),
                                     params.get("arguments") or {})
        return _ok(mid, {"content": [{"type": "text", "text": b} for b in blocks],
                         "isError": is_error})
    if mid is None:
        return None
    return _err(mid, -32601, f"Method not found: {method}")


def serve(stdin=None, stdout=None) -> None:
    """حلقة stdio: سطرٌ = رسالة. stdout للبروتوكول حصراً؛ السجلّ إلى stderr."""
    inp = stdin or sys.stdin.buffer
    out = stdout or sys.stdout.buffer
    for raw in inp:
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp = _err(None, -32700, "Parse error")
        else:
            try:
                resp = handle(msg) if isinstance(msg, dict) else _err(None, -32600, "Invalid Request")
            except Exception as e:  # noqa: BLE001 — لا يسقط الخادم برسالة واحدة
                print(f"silk_mcp: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                resp = _err(msg.get("id") if isinstance(msg, dict) else None,
                            -32603, f"Internal error: {type(e).__name__}")
        if resp is not None:
            out.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            out.flush()


if __name__ == "__main__":
    serve()
