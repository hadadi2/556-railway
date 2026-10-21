#!/usr/bin/env python3
"""خادم MCP لمراجعة تقارير Silk داخل كلود — Silk MCP server (stdio، مكتبة قياسية فقط).

قرار المالك (2026-10-20): التقرير يُنتَج في Silk كالمعتاد، ثم يراجعه المالك
وينقّحه في كلود (Desktop أو Code) على اشتراكه — لا نداء API مدفوعاً من الخادم —
ثم يعيده إلى Silk فتصدر ملفات العميل (docx/pdf/md) من النصّ المنقَّح بالقالب
الرسمي، بعد بوّابة التسليم الحتمية نفسها.

المسار كلّه من داخل كلود (توضيح المالك 2026-10-20): `start_study` (يشغّل البحث
الكامل — **مدفوع**) ← `study_status` (متابعة) ← `get_report` ← تنقيح ←
`submit_refined_report` ← `download_report` (Word/PDF إلى جهاز المالك ليرسله).
`get_evidence` يعطي كلود أدلة الدراسة بمصادرها فيراجع الدقة قبل إعادة الكتابة
(توضيح المالك: مراجعة نهائية وإعادة كتابة إنسانية، لا تعديل خفيف). `list_studies`
للجرد. `get_report` يسحب **نصّ الكاتب المخزَّن**
(`GET /analyses/{id}/report/refined`) لا المستند المعروض للعميل — وهو نفسُ ما يُعاد
في `submit_refined_report`، فالطرفان صيغةٌ واحدة (مراجعة §58). الخادم وكيلٌ رقيق فوق
HTTP API القائم — لا منطق أعمال هنا؛ كل فحصٍ وكل بوّابة ما قبل التشغيل تجري في
الخادم فلا يُلتَفّ عليها من هذا الباب.

وضعان لنفس الأدوات (توضيح المالك: «وين رابط MCP»):
  • محلّي (stdio): هذا الملف يعمل على جهاز المالك ويُضاف في إعداد Claude Desktop/Code.
  • بعيد (Streamable HTTP): `api.py` يستورد هذه الوحدة ويخدمها على `/mcp/<SILK_MCP_TOKEN>`
    فيُلصَق الرابط في Connectors؛ `REMOTE` (contextvar لكل طلب) يوجّه نداءات الأدوات إلى
    الخادم نفسه (loopback) ويجعل `download_report` يعيد رابط ملفٍ محمياً بالرمز نفسه
    بدل الحفظ على قرص الخادم.

التشغيل (على جهاز المالك):
  SILK_BASE_URL=https://<railway-domain>  SILK_API_KEY=<key>  python3 tools/silk_mcp.py
  SILK_DOWNLOAD_DIR (اختياري): مجلّد حفظ الملفات، افتراضياً ~/Downloads/silk-reports
التفصيل والإعداد في كلود: docs/MCP_OWNER_REVIEW.md
"""
from __future__ import annotations

import contextvars
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

VERSION = "0.5.0"
# إصدارات البروتوكول التي يطبّقها هذا الخادم فعلاً (الأحدث أولاً). غير المعروف
# من العميل يُجاب بأحدثها — لا ادّعاءُ دعمٍ لما لا نعرفه (مراجعة §58، الملاحظة ١٠).
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
TIMEOUT_S = 120

_REVIEW_RULES = (
    "المطلوب: مراجعة نهائية وإعادة كتابة إنسانية احترافية للدراسة بصوت مستشار تجاري "
    "خبير يخاطب صاحب قرار — جمل طبيعية مترابطة، لا قوالب ولا تكرار ولا حشو؛ راجع الدقة "
    "على الأدلة (get_evidence) وصحّح ما يخالفها. الحرّية كاملة داخل الأقسام (الصياغة، "
    "ترتيب الفقرات، العناوين الفرعية). "
    "ما يفرضه الخادم حتمياً ويرفض بلا حفظ: "
    "١) كل رقم ونسبة وسنة في النص واردٌ في الأصل أو في الأدلة — لا تخمين، ولا تركيب "
    "رقمَين في ادّعاء جديد، ولا اسم جهة أو علامة بلا سند في الأدلة؛ "
    "٢) أبقِ سطور الأقسام الأحد عشر «## N. العنوان» بأرقامها وعناوينها وترتيبها (بنية "
    "الدراسة الإلزامية عند المالك)، وأبقِ عنوان «### خارطة طريق الدخول»؛ "
    "٣) أبقِ كل عنصر «{{…}}» حرفياً — يُملأ آلياً بقيمته عند التصيير؛ "
    "٤) أعد النص كاملاً لا قسماً واحداً؛ "
    "٥) لغة عميل: لا «بعثة/وكيل/نداء/JSON/إذن ماذا» ولا وصف لآلية البناء، والحكم "
    "النهائي (التوصية ودرجة الثقة) ثابت كما هو."
)

TOOLS = [
    {
        "name": "start_study",
        "description": "ابدأ دراسة سوق كاملة جديدة في Silk (اثنتا عشرة مهمة جمع + تحليل + "
                       "تقرير). **نداء مدفوع** يستهلك اعتمادات كلود والمصادر — استأذن "
                       "المالك قبل استدعائه. يفحص الجاهزية أولاً: سوقٌ غامضة أو مفتاح غائب = "
                       "رفضٌ بأسبابه بلا إنفاق؛ تنبيهات استشارية (بلد منشأ منتِج، رمز HS "
                       "غير مؤكَّد…) تُعاد للمالك ليقرّر، ثم يُعاد الاستدعاء بـack=true. "
                       "يعود analysis_id فوراً والمعالجة تكمل في الخادم — تابعها بـstudy_status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "اسم المنتج (عربي أو إنجليزي)"},
                "market": {"type": "string",
                           "description": "السوق المستهدفة: اسم عربي/إنجليزي أو رمز ISO3"},
                "hs_code": {"type": "string",
                            "description": "رمز HS6 إن كان المالك متأكداً منه (اختياري)"},
                "production_cost_per_unit": {
                    "type": "number", "exclusiveMinimum": 0,
                    "description": "تكلفة إنتاج وحدة السوق بالدولار (اختياري؛ يفتح الهامش والتعادل)"},
                "ack": {"type": "boolean",
                        "description": "true = المالك قرأ التنبيهات الاستشارية ووافق على المتابعة"}},
            "required": ["product", "market"],
            "additionalProperties": False},
    },
    {
        "name": "study_status",
        "description": "حالة دراسة جارية أو منتهية: المرحلة، المهام المكتملة من 12، الزمن، "
                       "التكلفة المقدَّرة حتى الآن، وهل التقرير جاهز. عند الاكتمال انتقل إلى "
                       "get_report للتنقيح أو download_report للتنزيل.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "integer", "description": "معرّف الدراسة"}},
            "required": ["analysis_id"],
            "additionalProperties": False},
    },
    {
        "name": "download_report",
        "description": "نزّل ملف العميل النهائي (Word افتراضياً، أو PDF أو Markdown) إلى جهاز "
                       "المالك ليرسله هو للعميل؛ يعود مسار الملف المحفوظ. ملفٌ تحجبه بوّابة "
                       "التسليم لا يُنزَّل — يعود سبب الحجب.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "integer", "description": "معرّف الدراسة"},
                "format": {"type": "string", "enum": ["docx", "pdf", "md"],
                           "description": "صيغة الملف (افتراضياً docx)"}},
            "required": ["analysis_id"],
            "additionalProperties": False},
    },
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
        "name": "get_evidence",
        "description": "أدلة الدراسة بمصادرها (سجلّ الحقائق، نتائج المهام، المكوّنات؛ كلٌّ "
                       "بمصدره والفجوات معلَنة) — المرجع الذي تراجَع عليه دقة النصّ قبل "
                       "إعادة كتابته؛ أرقامه مسموحة في النصّ المنقَّح، وما ليس فيه ولا في "
                       "النصّ الأصلي رقمٌ مرفوض.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "integer", "description": "معرّف الدراسة"}},
            "required": ["analysis_id"],
            "additionalProperties": False},
    },
    {
        "name": "get_report",
        "description": "اسحب نصّ تقرير الدراسة المخزَّن لإعادة كتابته (Markdown بأقسامه "
                       "المرقّمة وعناصر {{…}})، مع قرار بوّابة التسليم وملاحظاتها. تعود "
                       "كتلتان: الأولى ملاحظة (البوّابة وملاحظاتها، العناصر)، والثانية النصّ "
                       "نفسه — وهو ما تعيد كتابته وتعيده كاملاً عبر submit_refined_report. "
                       + _REVIEW_RULES,
        "inputSchema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "integer", "description": "معرّف الدراسة"}},
            "required": ["analysis_id"],
            "additionalProperties": False},
    },
    {
        "name": "submit_refined_report",
        "description": "أعد الدراسة المُعاد كتابتها كاملةً إلى Silk لتحلّ مكان نصّ الكاتب "
                       "وتصدر منها ملفات العميل (Word/PDF/Markdown) بالقالب الرسمي. الخادم "
                       "يرفض (بلا حفظ) رقماً ليس في الأصل ولا الأدلة، أو قسماً مرقّماً غائباً "
                       "أو مُعاد ترتيبه، أو عنصر {{…}} غائباً أو جديداً، أو نصاً مبتوراً، أو "
                       "ما تحجبه بوّابة التسليم — ويعيد الملاحظات لتصحيحها وإعادة الإرسال. "
                       "الأصل يُحفَظ دائماً.",
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
#: الوضع البعيد (api.py) — إعدادٌ **لكل طلب** لا حالةٌ عالمية (مراجعة §58: طلبان على
#: مضيفَين مختلفَين كانا يتسابقان على متغيّر وحدة): `{"base_url": عنوان الخادم نفسه
#: (loopback)، "download_link_base": قاعدة روابط الملفات}`؛ None = الوضع المحلّي (stdio).
REMOTE: contextvars.ContextVar = contextvars.ContextVar("silk_mcp_remote", default=None)


def _remote() -> dict:
    return REMOTE.get() or {}


def _base_url() -> str:
    override = _remote().get("base_url")
    if override:
        return str(override).rstrip("/")
    url = os.environ.get("SILK_BASE_URL", "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SILK_BASE_URL غير مضبوط — عنوان خادم Silk (مثال: "
                           "https://silk.up.railway.app)")
    return url


def _http(method: str, path: str, body: dict | None = None, *,
          raw: bool = False) -> tuple:
    """نداء HTTP واحد؛ يعيد (الحالة، النصّ) — أو (الحالة، bytes) مع `raw=True`
    للملفات. أخطاء HTTP تعود حالةً لا استثناءً (409 البوّابة حمولةٌ مقصودة
    للمالك)؛ جسم الخطأ نصٌّ دائماً. تُطعَّم في الاختبارات."""
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
            data = resp.read()
            return resp.status, (data if raw else data.decode("utf-8", "replace"))
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
_STATUS_MARK = {"ok": "✓", "advisory": "⚠", "blocked": "✗"}


def _checks_lines(checks: list) -> str:
    return "\n".join(
        f"{_STATUS_MARK.get(str(c.get('status')), '•')} {c.get('label_ar') or c.get('key')}: "
        f"{c.get('detail_ar') or ''}".rstrip() for c in checks if isinstance(c, dict))


def _tool_start_study(args: dict) -> tuple:
    product = str(args.get("product") or "").strip()
    market = str(args.get("market") or "").strip()
    if not product or not market:
        raise ValueError("product و market إلزاميان")
    hs = str(args.get("hs_code") or "").strip()
    ack = bool(args.get("ack"))
    # (١) الجاهزية — قراءةٌ بلا إنفاق: محجوبٌ أو استشاريٌّ بلا موافقة يُعاد للمالك.
    q = urllib.parse.urlencode({"product": product, "market": market, "hs_code": hs})
    status, text = _http("GET", f"/research/readiness?{q}")
    if status != 200:
        return f"تعذّر فحص جاهزية الدراسة ({status}): {_detail(text)}", True
    ready = _json_body("/research/readiness", text)
    checks = ready.get("checks") or []
    if not ready.get("can_run"):
        return ("لا يمكن بدء الدراسة — عوائق حاجبة (لم يُنفَق شيء):\n"
                + _checks_lines(checks)), True
    if ready.get("needs_ack") and not ack:
        return ("الدراسة تحتاج موافقة المالك على التنبيهات الاستشارية التالية قبل البدء "
                "(لم يُنفَق شيء). إن وافق المالك أعد الاستدعاء بـack=true:\n"
                + _checks_lines(checks)), True
    # (٢) البدء — خلفيٌّ ومخزَّن؛ الموافقات تُمرَّر فقط حين أعطاها المالك صراحةً.
    body: dict = {"product": product, "market": market, "async_run": True,
                  "persist": True}
    if hs:
        body["hs_code"] = hs
    cost = args.get("production_cost_per_unit")
    if cost is not None:
        body["production_cost_per_unit"] = float(cost)
    if ack:
        body.update({"advisories_ack": True, "producer_ack": True,
                     "accept_limited": True, "hs_confirmed": bool(hs)})
    status, text = _http("POST", "/research", body)
    if status not in (200, 201, 202):
        return (f"رفض الخادم بدء الدراسة ({status}) — لم تبدأ ولم يُنفَق شيء:\n"
                f"{_detail(text)}"), True
    data = _json_body("/research", text)
    aid = data.get("analysis_id")
    if aid is None:
        return f"بدأ الطلب لكن بلا معرّف دراسة في الردّ: {text[:200]}", True
    return (f"بدأت الدراسة رقم {aid} ({product} ← {market}) في الخادم — تستغرق عادةً "
            f"دقائق عدّة وتستهلك اعتمادات. تابعها بـstudy_status({aid})؛ عند الاكتمال "
            f"استعمل get_report للتنقيح ثم download_report للتنزيل."), False


def _tool_study_status(args: dict) -> tuple:
    aid = int(args["analysis_id"])
    path = f"/research/{aid}/status"
    status, text = _http("GET", path)
    if status != 200:
        return f"تعذّر قراءة حالة الدراسة {aid} ({status}): {_detail(text)}", True
    d = _json_body(path, text)
    st = d.get("status") or "—"
    cost = d.get("cost_usd_estimate")
    lines = [f"الدراسة {aid} · {d.get('product') or ''} · الحالة: {st}",
             f"المرحلة: {d.get('stage_label') or d.get('stage') or '—'} · المهام: "
             f"{d.get('missions_completed', 0)}/{d.get('missions_total', 12)} · "
             f"الزمن: {d.get('elapsed_seconds') or 0} ث · نداءات كلود: {d.get('llm_calls') or 0}"
             + (f" · التكلفة المقدَّرة: {cost}$" if cost is not None else "")]
    if d.get("cost_unpriced_models"):
        lines.append(f"نماذج بلا سعر في الدفتر (التكلفة ناقصة): {d['cost_unpriced_models']}")
    if st == "completed" and d.get("report_present"):
        lines.append("التقرير جاهز — get_report للتنقيح، أو download_report للتنزيل.")
    elif st == "completed":
        lines.append("اكتملت بلا تقرير (متدهورة) — أعد توليد التقرير من Silk قبل التنقيح.")
    elif st == "failed":
        lines.append(f"فشلت: {d.get('skip_reason') or 'بلا سبب مسجَّل'}")
    elif d.get("cancel_requested"):
        lines.append(f"طُلب الإلغاء: {d.get('cancel_reason') or ''}")
    else:
        lines.append("ما زالت تعمل — أعد الاستدعاء بعد دقيقة.")
    return "\n".join(lines), False


#: صيغة → نوع الوسيط — المصدر الواحد لـ`download_report` ولنقطة الملفات البعيدة في api.py.
_MEDIA = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "pdf": "application/pdf", "md": "text/markdown"}


def _download_dir() -> str:
    d = os.environ.get("SILK_DOWNLOAD_DIR", "").strip() or os.path.join(
        os.path.expanduser("~"), "Downloads", "silk-reports")
    os.makedirs(d, exist_ok=True)
    return d


def _tool_download_report(args: dict) -> tuple:
    aid = int(args["analysis_id"])
    fmt = str(args.get("format") or "docx").lower()
    if fmt not in _MEDIA:
        raise ValueError("format يجب أن يكون docx أو pdf أو md")
    link_base = _remote().get("download_link_base")
    if link_base:
        # الوضع البعيد: لا قرصَ مالكٍ هنا، ولا نصيّر الملف مرّتين (مراجعة §58) — نقرأ قرار
        # بوّابة التسليم من سطح التنقيح (بناءُ عرضٍ واحد) ثم نعيد رابطاً محمياً بالرمز نفسه
        # يصيّر الملف عند فتحه؛ نقطةُ الملف تعيد 409 البوّابة كما هو إن تغيّر الحال.
        status, text = _http("GET", f"/analyses/{aid}/report/refined")
        if status == 200:
            gate = (_json_body(f"/analyses/{aid}/report/refined", text).get("gate") or {})
            if str(gate.get("verdict") or "").upper() == "FAIL":
                return (f"تسليم الدراسة {aid} محجوب بالبوّابة — لا رابطَ لملفٍ محجوب "
                        f"(أسباب الحجب: {', '.join(gate.get('fail_drivers') or []) or '—'})؛ "
                        f"عالج الأسباب عبر get_report ثم submit_refined_report."), True
        elif status not in (400,):      # 400 = تحليل /analyze لا بحث — بوّابته عند التنزيل
            return f"تعذّر فحص جاهزية الملف للدراسة {aid} ({status}): {_detail(text)}", True
        link = f"{str(link_base).rstrip('/')}/{aid}/report.{fmt}"
        return (f"ملف العميل للدراسة {aid} جاهز — افتح الرابط لتنزيله ثم أرسله للعميل بعد "
                f"مراجعتك النهائية:\n{link}"), False
    path = f"/analyses/{aid}/report.{fmt}"
    status, data = _http("GET", path, raw=True)
    if status == 409:
        return (f"تسليم الدراسة {aid} محجوب بالبوّابة — لا يُنزَّل ملفٌ محجوب:\n"
                f"{_detail(data if isinstance(data, str) else data.decode('utf-8', 'replace'))}"), True
    if status != 200:
        return (f"تعذّر تنزيل {fmt} للدراسة {aid} ({status}): "
                f"{_detail(data if isinstance(data, str) else data.decode('utf-8', 'replace'))}"), True
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not data:
        return f"الخادم أعاد ملفاً فارغاً للدراسة {aid} — لم يُحفَظ", True
    out = os.path.join(_download_dir(), f"silk-{aid}.{fmt}")
    with open(out, "wb") as fh:
        fh.write(data)
    return (f"حُفظ ملف العميل: {out} ({len(data)} بايت). أرسله للعميل بعد مراجعتك "
            f"النهائية."), False


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


def _tool_get_evidence(args: dict) -> tuple:
    aid = int(args["analysis_id"])
    path = f"/analyses/{aid}/evidence"
    status, text = _http("GET", path)
    if status != 200:
        return f"تعذّر سحب أدلة الدراسة {aid} ({status}): {_detail(text)}", True
    data = _json_body(path, text)
    ctx = data.get("context") or ""
    if not ctx.strip():
        return f"لا أدلة مخزَّنة للدراسة {aid}", True
    return [f"أدلة الدراسة {aid} بمصادرها ({data.get('chars', len(ctx))} حرفاً) — كل رقم هنا "
            "مسموح في النصّ المنقَّح؛ ما ليس هنا ولا في النصّ الأصلي مرفوض:", ctx], False


def _tool_get_report(args: dict) -> tuple:
    aid = int(args["analysis_id"])
    path = f"/analyses/{aid}/report/refined"
    status, text = _http("GET", path)
    if status != 200:
        return f"تعذّر سحب نصّ التقرير {aid} ({status}): {_detail(text)}", True
    data = _json_body(path, text)
    gate = data.get("gate") or {}
    drivers = gate.get("fail_drivers") or []
    notes = gate.get("notes") or []
    note = (f"الدراسة {aid} · بوّابة التسليم الآن: {gate.get('verdict') or '—'}"
            + (f" (أسباب الحجب: {', '.join(drivers)})" if drivers else "")
            + f" · تنقيحات سابقة: {data.get('refined_count', 0)}"
            + f" · عناصر {{{{…}}}} تُبقى حرفياً: {len(data.get('placeholders') or [])}"
            + (("\nملاحظات البوّابة لتعالجها في إعادة الكتابة:\n- " + "\n- ".join(notes))
               if notes else "")
            + "\nالنصّ في الكتلة التالية؛ راجع دقته على get_evidence ثم أعده كاملاً إلى "
              "submit_refined_report.")
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
    "start_study": _tool_start_study,
    "study_status": _tool_study_status,
    "download_report": _tool_download_report,
    "list_studies": _tool_list_studies,
    "get_evidence": _tool_get_evidence,
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
    if not isinstance(method, str) or not isinstance(params, dict):
        return _err(mid, -32600, "Invalid Request")
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": negotiate_protocol(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "silk", "version": VERSION},
            "instructions": ("Silk: دراسات سوق للمصدّر السعودي. المسار: start_study (مدفوع — "
                             "استأذن المالك) ← study_status ← get_report + get_evidence ← "
                             "مراجعة وإعادة كتابة ← submit_refined_report ← download_report. "
                             "list_studies للجرد. " + _REVIEW_RULES),
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


def handle_payload(payload):
    """حمولة HTTP واحدة (رسالة أو دفعة قائمة — بروتوكول 2025-03-26 يسمح بالدفعات) →
    قائمة الردود (بلا الإشعارات). قائمة فارغة = لا ردّ (202 عند النقل عبر HTTP)."""
    items = payload if isinstance(payload, list) else [payload]
    out = []
    for msg in items:
        if not isinstance(msg, dict):
            out.append(_err(None, -32600, "Invalid Request"))
            continue
        try:
            resp = handle(msg)
        except Exception as e:  # noqa: BLE001 — رسالةٌ مشوَّهة لا تُسقِط الدفعة ولا تعطي 500
            print(f"silk_mcp: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            resp = _err(msg.get("id"), -32603, f"Internal error: {type(e).__name__}")
        if resp is not None:
            out.append(resp)
    return out


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
