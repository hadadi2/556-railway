"""فحوصات الدراسة الحتمية F1–F7 (+G0) — deterministic study checks (المرحلة ١، PR-A).

**لماذا وُجد هذا الملف (قرار المالك 2026-10-21).** الأخطاء نفسها عادت في أربع
دراسات مدفوعة لأن الإصلاحات كانت تُكتب في التعليمات (prompts) لا في الشيفرة،
ولا فحص يمنع عودتها. هنا تُقاس الدراسة **بعد** كتابتها بشيفرة حتمية خالصة:
stdlib فقط، صفر شبكة، صفر نموذج — المدخل نصّ التقرير + سطور الأدلة بمصادرها
(+ قيم مرجعية اختيارية يؤكدها المالك)، والمخرج لكل فحص PASS / WARN / FAIL مع
السبب والموضع. المرحلة ١ **قياس فقط**؛ الربط ببوّابة التسليم في PR-B.

الفحوصات (نصّ المالك حرفياً هو المرجع):
- **F1 الوحدات**: لكل رقم كمية، السعر الضمني = القيمة ÷ الكمية؛ خارج [10%، 10×]
  من متوسط سعر الاستيراد = مرفوض (مثال الدراسة ١: «817,876 طن» وهي كيلوغرامات).
- **F2 أسعار الرفوف**: كل سعر يحتاج رابطاً ووزناً وسعراً وعملة وتاريخ رصد؛
  يُحسب للكيلو؛ يُرفض ما دون (متوسط سعر الاستيراد × سعر الصرف × (1 + الضريبة))؛
  مصادر التواصل الاجتماعي «غير موثق» ولا تدخل أي حساب أو نطاق في النثر.
- **F3 المرآة**: رقم مباشر ورقم مرآة لنفس المؤشر بفرق > 25% يُوسَمان «تباين»؛
  رقم المرآة ممنوع في الخلاصة التنفيذية وكأول رقم في أي قسم، وممنوع رأساً
  لسجلّ الحقائق.
- **F4 الجمارك**: «رسوم 0%» أو «إعفاء» بلا شرط قاعدة المنشأ في الفقرة نفسها = مرفوض.
- **F5 الحكم**: حكم استثماري بلا سعر مصنع ولا سقف سعر محسوب = مرفوض؛ الصحيح
  «فرز سوق أولي».
- **F6 النطاق**: منتج في التوصيات خارج البند الجمركي للدراسة (من `data/hs_codes.csv`)
  = مرفوض، مع وعي بالنفي («غير منزوع الكافيين» ليس 090122).
- **F7 الاتساق**: الاشتراط الواحد لا يُصنَّف «إلزامياً» في قسم و«يطلبه المشترون»
  في قسم آخر.
- **G0 القيم المرجعية**: القيم التي أكدها المالك (`expected.json`) حاضرة في الدراسة
  ضمن 0.5%؛ المخالِفة = FAIL، الغائبة = WARN.

Deterministic, stdlib-only post-writing checks over report text + evidence lines.
Phase 1 measures; wiring into the delivery gate is PR-B.
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
_ORDER = {FAIL: 3, WARN: 2, PASS: 1, SKIP: 0}

_ROOT = os.path.dirname(os.path.abspath(__file__))
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_AR = "ء-ي"
# السوابقُ العربية الملتصقة («بـ2.50»، «و20.00») لا تحجب الرقم؛ الحرفُ اللاتيني يحجبه
# («HS090121»، «GSO9»، «dp7» ليست أرقاماً للقياس).
_NUM_RE = re.compile(r"(?<![\d.,A-Za-z])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\d)"
                     r"|(?<![\d.,A-Za-z])-?\d+(?:\.\d+)?(?!\d)")
_HEAD_RE = re.compile(r"^##\s+(\d+)\.\s*(.+?)\s*$", re.M)
_SUBHEAD_RE = re.compile(r"^###\s+(.+?)\s*$")
_YEAR_RE = re.compile(r"(?<!\d)(?:19[89]\d|20[0-4]\d)(?!\d)")
_URL_RE = re.compile(r"https?://\S+", re.I)
_CLAUSE_SPLIT = re.compile(r"[،؛;]|(?<!\d),|,(?!\d)|\s(?:ثم|بينما|مقابل|versus|vs\.?|while)\s")
_SENT_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n")
_MAG = {"مليون": 1e6, "ملايين": 1e6, "مليار": 1e9, "مليارات": 1e9,
        "ألف": 1e3, "آلاف": 1e3, "الف": 1e3, "million": 1e6, "billion": 1e9,
        "thousand": 1e3, "m": 1e6, "bn": 1e9, "k": 1e3}

# ── المرافق العامة · shared helpers ──────────────────────────────────────────


_TASHKEEL_RE = re.compile("[\u064B-\u0652\u0670\u0640]")


def norm_digits(s: object) -> str:
    """تطبيع النصّ قبل أيّ فحص: الأرقام الهندية/الفارسية → ASCII، والفاصلة العشرية العربية →
    نقطة، والحركات والشدّة والتطويل تُحذف («بإعفاءٍ جمركيّ» = «بإعفاء جمركي»)."""
    return _TASHKEEL_RE.sub("", str(s or "").translate(_DIGITS).replace("٫", ".").replace("٬", ","))


def _to_float(tok: str) -> "float | None":
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return None


def numbers_in(text: str) -> list:
    """كل الأعداد في نصّ بترتيبها: [(القيمة، البداية، النهاية، الخام)]."""
    out = []
    t = norm_digits(text)
    for m in _NUM_RE.finditer(t):
        v = _to_float(m.group(0))
        if v is not None:
            out.append((v, m.start(), m.end(), m.group(0)))
    return out


def near(a: float, b: float, tol_pct: float = 0.5) -> bool:
    """تقارب نسبي: |a − b| ≤ tol% من |b| (والصفر يساوي الصفر فقط)."""
    if b == 0:
        return a == 0
    return abs(a - b) <= abs(b) * tol_pct / 100.0


def sentences(text: str) -> list:
    return [s.strip() for s in _SENT_SPLIT.split(norm_digits(text)) if s and s.strip()]


_BLOCK_START_RE = re.compile(r"^\s*(?:#|[-*•]|\d+[.)]\s)")


def report_sentences(text: str) -> list:
    """جمل التقرير مع ضمّ الأسطر الملفوفة داخل الفقرة («تكلفة إنتاج\nالكيلوغرام (95 روبية)»
    جملةٌ واحدة)؛ العنوان وبند القائمة وصفّ الجدول بداياتٌ مستقلة."""
    out = []
    for p in paragraphs(text):
        if p.lstrip().startswith("|"):
            out.append(p.strip())
            continue
        groups: list = []
        for line in p.split("\n"):
            if not groups or _BLOCK_START_RE.match(line):
                groups.append(line.strip())
            else:
                groups[-1] += " " + line.strip()
        for g in groups:
            out += [x.strip() for x in re.split(r"(?<=[.!?؟])\s+", g) if x.strip()]
    return out


def paragraphs(text: str) -> list:
    """فقرات = كتل بين أسطر فارغة؛ وصفّ الجدول فقرةٌ بذاته."""
    out, buf = [], []
    for line in norm_digits(text).split("\n"):
        if not line.strip():
            if buf:
                out.append("\n".join(buf))
                buf = []
            continue
        if line.lstrip().startswith("|"):
            if buf:
                out.append("\n".join(buf))
                buf = []
            out.append(line)
            continue
        buf.append(line)
    if buf:
        out.append("\n".join(buf))
    return out


def _snip(s: str, n: int = 160) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


_AR_PREFIX = r"(?:[وفبكل]?ال|لل|[وفبكل])?"


def _ar_word(term: str) -> str:
    """نمطُ عبارةٍ كاملة الحدود: كل كلمةٍ عربية تقبل سابقةً (و/ف/ب/ك/ل) و«ال» اختيارية
    («للقهوة المحمصة» تطابق «قهوة محمصة»)؛ اللاتينية حرفية بلا حساسية حالة."""
    parts = []
    for w in norm_digits(term).strip().split():
        if re.match(rf"[{_AR}]", w):
            core = w[2:] if w.startswith("ال") and len(w) > 3 else w
            parts.append(_AR_PREFIX + re.escape(core))
        else:
            parts.append(re.escape(w))
    first = norm_digits(term).strip()[:1]
    left = rf"(?<![{_AR}A-Za-z])" if re.match(rf"[{_AR}]", first) else r"(?<![A-Za-z])"
    return left + r"\s+".join(parts) + rf"(?![{_AR}A-Za-z])"


# ── نموذج المدخل · the input model ─────────────────────────────────────────


@dataclass
class Finding:
    check: str
    title: str
    status: str
    note: str = ""
    items: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"check": self.check, "title": self.title, "status": self.status,
                "note": self.note, "items": list(self.items)}

    @property
    def failed(self) -> bool:
        return self.status == FAIL


@dataclass
class StudyDoc:
    """نصّ التقرير + أدلة الدراسة + بيانات وصفية + قيم مرجعية اختيارية."""
    report: str
    evidence: str = ""
    meta: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    view: "dict | None" = None
    #: نتائج المهام المنظَّمة (value/source/note/status/data_year) حين تتوفّر النتيجة كاملة.
    findings: list = field(default_factory=list)

    def __post_init__(self):
        self.report = norm_digits(self.report)
        self.evidence = norm_digits(self.evidence)

    @property
    def sections(self) -> list:
        """[(الرقم، العنوان، المتن)] للأقسام المرقّمة «## N. العنوان»."""
        heads = list(_HEAD_RE.finditer(self.report))
        out = []
        for i, m in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(self.report)
            out.append((int(m.group(1)), m.group(2).strip(), self.report[m.end():end]))
        return out

    def section(self, n: int) -> str:
        for num, _t, body in self.sections:
            if num == n:
                return body
        return ""

    def section_title(self, n: int) -> str:
        for num, t, _b in self.sections:
            if num == n:
                return t
        return str(n)

    @property
    def prose(self) -> str:
        """التقرير بلا صفوف الجداول — لفحص النثر وحده."""
        return "\n".join(l for l in self.report.split("\n") if not l.lstrip().startswith("|"))

    @property
    def evidence_lines(self) -> list:
        return [l for l in self.evidence.split("\n") if l.strip()]

    @property
    def all_text(self) -> str:
        return self.report + "\n" + self.evidence

    @classmethod
    def from_result(cls, found: dict, meta: "dict | None" = None,
                    expected: "dict | None" = None) -> "StudyDoc":
        """من نتيجة مخزَّنة (`GET /analyses/{id}` أو blob): **النصّ المسلَّم** (نصّ العرض
        بعد ملء الرموز والتطهير، وإلا نصّ الكاتب الخام) + سياق الأدلة
        (`silk_render.analysis_context` — أرضية `get_evidence`) بلا نسخة التقرير فيه."""
        dr = (found or {}).get("deep_research") or {}
        raw = ((dr.get("report") or {}).get("report")
               or (dr.get("report") or {}).get("text") or "")
        report, evidence, view = raw, "", None
        try:
            from silk_render import analysis_context, build_view
            view = found.get("view") if isinstance(found.get("view"), dict) else None
            view = view or build_view(found)
            bound = (((view.get("deep_research") or {}).get("report") or {}).get("text") or "")
            report = bound or raw
            evidence = strip_embedded_report(
                analysis_context(dict(found, view=view), max_chars=200_000), report)
        except Exception:  # noqa: BLE001 — بلا أدلة تبقى الفحوص النصية ممكنة
            evidence = ""
        fnd: list = []
        try:
            for m in (((view or {}).get("deep_research") or {}).get("missions") or {}).values():
                if isinstance(m, dict) and not m.get("failed"):
                    fnd += [f for f in (m.get("findings") or []) if isinstance(f, dict)]
        except Exception:  # noqa: BLE001
            fnd = []
        mk = (found or {}).get("market") or {}
        m = {"hs_code": str((found or {}).get("hs_code") or ""),
             "market_iso3": mk.get("iso3") or "", "market_ar": mk.get("name_ar") or "",
             "lang": (found or {}).get("lang") or "ar",
             "production_cost_per_unit": ((found or {}).get("request") or {})
             .get("production_cost_per_unit")}
        m.update(meta or {})
        return cls(report=report, evidence=evidence, meta=m, expected=expected or {},
                   view=view, findings=fnd)


# ── نسخة التقرير داخل سياق الأدلة · the report copy inside the evidence ─────

REPORT_MARKER = "التقرير المكتوب للدراسة:"
#: أشكالُ السطور التي يكتبها `analysis_context` **بعد** نصّ التقرير — أوّلُها نهايةُ النسخة.
_POST_REPORT_LINE = re.compile(
    r"^(?:شرط\s+مفتوح|حدّ\s+معلن|مورّد|فجوة\s)[^\n]*:"
    r"|^[^\n|#]{1,80}\s=\s[^\n]*\[المصدر:"
    r"|^[^\n|#:]{1,60}:\s(?:غير متاح|تعذّر الجلب[^\n]*)$")


def strip_embedded_report(evidence: str, report: str = "") -> str:
    """أزِل نسخة التقرير من سياق الأدلة كي لا تُعَدّ أرقامُه أدلةً على نفسه. النسخة في
    السياق هي نصّ العرض (بعد الملء والتطهير) لا نصّ الكاتب الخام، فالمطابقة الحرفية لا
    تكفي: يُقصّ من سطر «التقرير المكتوب للدراسة:» إلى أوّل سطرٍ من أشكال ما بعده."""
    ev = norm_digits(evidence)
    report = norm_digits(report)
    if report and report.strip() and report.strip() in ev:
        ev = ev.replace(report.strip(), "")
    lines = ev.split("\n")
    try:
        i = next(k for k, l in enumerate(lines) if l.strip() == REPORT_MARKER)
    except StopIteration:
        return ev
    j = i + 1
    while j < len(lines) and not _POST_REPORT_LINE.match(lines[j]):
        j += 1
    return "\n".join(lines[:i] + lines[j:])


# ── القيم المرجعية المشتركة · reference figures ─────────────────────────────

_UNIT_VALUE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:دولار(?:\s*أمريكي)?|USD|\$)\s*(?:/|لل|لكل\s*)?\s*"
    r"(?:كجم|كغم|كغ|كيلوغرام|كيلوجرام|كيلو\s*غرام|kg)", re.I)
_IMPORT_PRICE_CTX = re.compile(r"سعر\s+(?:ال)?استيراد|سعر\s+(?:ال)?جملة|عند\s+الحدود|"
                               r"سعر\s+الوحدة|border|unit\s+value|import\s+price", re.I)


def reference_unit_values(doc: StudyDoc) -> dict:
    """متوسط سعر الاستيراد (دولار/كغ) بالسنة: من `expected` أولاً ثم من الأدلة."""
    out: dict = {}
    for y, v in ((doc.expected.get("import_unit_value_usd_kg") or {}).items()):
        try:
            out[int(y)] = float(v)
        except (TypeError, ValueError):
            continue
    if out:
        return out
    for s in sentences(doc.evidence) + sentences(doc.report):
        if not _IMPORT_PRICE_CTX.search(s):
            continue
        years = [int(y) for y in _YEAR_RE.findall(s)]
        for m in _UNIT_VALUE_RE.finditer(s):
            v = float(m.group(1))
            # السنة الأقرب قبل الرقم؛ وإلا أول سنة في الجملة
            before = s[: m.start()]
            ys = [int(y) for y in _YEAR_RE.findall(before)] or years
            key = ys[-1] if ys else 0
            out.setdefault(key, v)
    return out


def _ref_price_for(ref: dict, year: "int | None") -> "tuple[float | None, int | None]":
    if not ref:
        return None, None
    if year is not None and year in ref:
        return ref[year], year
    y = max(ref)
    return ref[y], (y or None)


# ── F1 الوحدات · unit sanity ────────────────────────────────────────────────

_QTY_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:(مليون|ألف|آلاف)\s+)?"
    r"(طن(?:اً|ًا)?|أطنان|كجم|كغم|كغ|كيلوغرام(?:اً|ًا)?|كيلوجرام|كيلو\s*غرام|tonnes?|tons?|kg)"
    rf"(?![{_AR}A-Za-z])", re.I)
_MONEY_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(مليون|ملايين|مليار|ألف|آلاف|million|billion)?\s*"
    r"(دولار(?:\s*أمريكي)?|\$|USD|دينار(?:\s*بحريني)?|د\.ب|BHD|ريال|SAR|يورو|€|EUR|درهم|AED)",
    re.I)
_PER_UNIT_AFTER = re.compile(r"\s*(?:/|لل|لكل|per|a|an)\s*(?:كجم|كغم|كغ|كيلو\w*|طن|kg|ton\w*|tonne\w*)", re.I)
_TON = ("طن", "طنا", "طناً", "طنًا", "أطنان", "ton", "tons", "tonne", "tonnes")


def _unit_to_kg(unit: str) -> "tuple[float, str]":
    u = unit.strip().lower()
    if u.startswith("كيلو") or u in ("كجم", "كغم", "كغ", "kg"):
        return 1.0, "kg"
    return 1000.0, "ton"


def _usd_value(amount: float, mag: str, cur: str, doc: StudyDoc) -> "float | None":
    v = amount * _MAG.get((mag or "").lower(), 1.0)
    c = (cur or "").lower()
    if "دولار" in c or c in ("$", "usd"):
        return v
    # عملةُ السوق وحدها تُحوَّل بسعر صرفه المعلن؛ أيُّ عملةٍ أخرى بلا سعر = لا تحويل.
    fx = doc.meta.get("fx_local_per_usd")
    if fx and _is_local_currency(c, str(doc.meta.get("currency") or "").upper()):
        return v / float(fx)
    return None


def check_units(doc: StudyDoc) -> Finding:
    ref = reference_unit_values(doc)
    items: list = []
    seen = 0
    for where, ss in (("التقرير", report_sentences(doc.report)), ("الأدلة", sentences(doc.evidence))):
        for s in ss:
            qm = _QTY_RE.search(s)
            if not qm:
                continue
            # المبلغ الإجمالي لا سعرُ الوحدة: «6.2 دولار للكيلوغرام» ليس قيمة الكمية.
            mm = [m for m in _MONEY_RE.finditer(s)
                  if m.start() != qm.start() and not _PER_UNIT_AFTER.match(s, m.end())]
            if not mm:
                continue
            seen += 1
            qty = _to_float(qm.group(1)) * _MAG.get(qm.group(2) or "", 1.0)
            per_kg_factor, unit_kind = _unit_to_kg(qm.group(3))
            qty_kg = qty * per_kg_factor
            money = mm[0]
            val = _usd_value(_to_float(money.group(1)), money.group(2) or "",
                             money.group(3), doc)
            if val is None or qty_kg <= 0:
                continue
            years = [int(y) for y in _YEAR_RE.findall(s)]
            ref_v, ref_y = _ref_price_for(ref, years[0] if years else None)
            implied = val / qty_kg
            if ref_v is None:
                items.append({"status": SKIP, "where": where, "text": _snip(s),
                              "implied_usd_per_kg": round(implied, 4),
                              "why": "لا متوسط سعر استيراد مرجعي للمقارنة"})
                continue
            ratio = implied / ref_v if ref_v else None
            if ratio is not None and 0.1 <= ratio <= 10.0:
                continue
            alt_factor = 1.0 if unit_kind == "ton" else 1000.0
            alt_implied = val / (qty * alt_factor)
            alt_unit = "كيلوغرام" if unit_kind == "ton" else "طن"
            hint = ""
            if 0.5 <= (alt_implied / ref_v) <= 2.0:
                hint = (f" — يطابق المرجع لو كانت الوحدة {alt_unit} "
                        f"({alt_implied:.2f} دولار/كغ): خطأ وحدة على الأرجح")
            items.append({"status": FAIL, "where": where, "text": _snip(s),
                          "quantity": qm.group(0), "value": money.group(0),
                          "implied_usd_per_kg": round(implied, 4),
                          "reference_usd_per_kg": ref_v, "reference_year": ref_y,
                          "ratio": round(ratio, 5) if ratio is not None else None,
                          "why": (f"السعر الضمني {implied:.4f} دولار/كغ خارج "
                                  f"[10%، 10×] من متوسط الاستيراد {ref_v} "
                                  f"(سنة {ref_y}){hint}")})
    fails = [i for i in items if i["status"] == FAIL]
    if fails:
        return Finding("F1", "فحص الوحدات", FAIL,
                       f"{len(fails)} رقم كمية بسعر ضمني غير معقول من {seen} فُحِص",
                       items)
    if items:
        return Finding("F1", "فحص الوحدات", WARN,
                       "أرقام كمية بلا مرجع سعر استيراد للمقارنة", items)
    if not seen:
        return Finding("F1", "فحص الوحدات", PASS, "لا أرقام كمية مقرونة بقيمة في الدراسة")
    return Finding("F1", "فحص الوحدات", PASS, f"{seen} رقم كمية بسعر ضمني ضمن النطاق")


# ── F2 أسعار الرفوف · shelf prices ─────────────────────────────────────────

_PRICE_TABLE_HEAD = ("سعر التجزئة", "سعر الرف", "سعر الرفّ", "السعر لوحدة المقارنة",
                     "retail price", "shelf price", "price per")
_SOCIAL_RE = re.compile(r"إنستغرام|انستغرام|انستقرام|إنستقرام|instagram|فيسبوك|فيس بوك|"
                        r"facebook|تيك\s*توك|tiktok|سناب|snapchat|تويتر|twitter|\bx\.com|"
                        r"واتساب|whatsapp|تلغرام|telegram|يوتيوب|youtube", re.I)
_PACK_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(كيلوغرام|كيلوجرام|كيلو\s*غرام|كجم|كغم|كغ|kg|غرام|جرام|غم|جم|غ|g)"
    rf"(?![{_AR}A-Za-z])", re.I)
_PRICE_CELL_RE = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*(?:إلى|-|–|to)\s*(\d+(?:\.\d+)?))?\s*"
    r"(دينار\s*بحريني|دينار|د\.ب|BHD|ريال\s*سعودي|ريال|SAR|ر\.س|درهم|AED|دولار|\$|USD|يورو|€|EUR|"
    r"جنيه|EGP|دينار\s*كويتي|KWD|ريال\s*قطري|QAR)", re.I)
_MONTH_RE = re.compile(r"(?:يناير|فبراير|مارس|أبريل|إبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|"
                       r"أكتوبر|نوفمبر|ديسمبر|كانون|شباط|آذار|نيسان|أيار|حزيران|تموز|آب|أيلول|"
                       r"تشرين|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+20\d\d"
                       r"|20\d\d-\d\d(?:-\d\d)?", re.I)
_NA_RE = re.compile(r"غير\s+متاح|غير\s+محسوب|^\s*(?:—|-|n/?a)\s*$", re.I)
_PACK_TO_KG = {"كيلوغرام": 1.0, "كيلوجرام": 1.0, "كجم": 1.0, "كغم": 1.0, "كغ": 1.0, "kg": 1.0,
               "غرام": .001, "جرام": .001, "غم": .001, "جم": .001, "غ": .001, "g": .001}
_LOCAL_CUR = {"BHD": ("دينار", "د.ب", "bhd"), "SAR": ("ريال", "sar", "ر.س"),
              "AED": ("درهم", "aed"), "KWD": ("دينار", "kwd"), "QAR": ("ريال", "qar")}


def _table_rows(text: str) -> list:
    """جداول Markdown: [(رأس، [صفوف])] — كل صف قائمة خلايا."""
    tables, cur = [], None
    for line in text.split("\n"):
        if line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            if cur is None:
                cur = (cells, [])
                tables.append(cur)
            else:
                cur[1].append(cells)
        else:
            cur = None
    return tables


def _col(header: list, *needles: str) -> "int | None":
    for i, h in enumerate(header):
        hl = h.lower()
        if any(n.lower() in hl for n in needles):
            return i
    return None


def _cell(row: list, idx: "int | None") -> str:
    return row[idx] if idx is not None and idx < len(row) else ""


def _pack_kg(cell: str) -> "float | None":
    m = _PACK_RE.search(cell or "")
    if not m:
        return None
    unit = re.sub(r"\s+", "", m.group(2).lower())
    unit = "كيلوغرام" if unit.startswith("كيلو") else unit
    return float(m.group(1)) * _PACK_TO_KG.get(unit, 0.0) or None


_PROSE_PRICE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(دينار(?:\s*(?:بحريني|كويتي|أردني|جزائري|ليبي))?|د\.ب|د\.ك|ريال(?:\s*(?:سعودي|قطري|عماني))?|"
    r"درهم|يورو|€|جنيه|ين|روبية|ليرة|شلن|نايرا|رينغيت|BHD|KWD|JOD|SAR|QAR|AED|OMR|EUR|EGP|JPY|INR|"
    r"TRY|KES|NGN|MAD|DZD|MYR|YER|LYD|دولار|\$|USD)(?![ء-يA-Za-z])"
    r"(\s*(?:/\s*(?:كجم|كغم|كغ|كيلو\w*|لتر|عبوة|علبة|kg)|لل(?:كيلو\w*|لتر|عبوة|علبة)))?", re.I)
_SHELF_CTX_RE = re.compile(r"سعر\s+(?:ال)?(?:تجزئة|رف)|على\s+(?:ال)?رفوف|(?:ي|ت)باع|علامة|عبوة|"
                           r"retail|shelf|sells?\s+(?:at|for)", re.I)
_RETAIL_STRICT_RE = re.compile(r"سعر\s+(?:ال)?(?:تجزئة|رف)|على\s+(?:ال)?رفوف|retail|shelf", re.I)
_COST_CTX_BEFORE_RE = re.compile(r"تكلفة|كلفة|سعر\s+(?:ال)?مصنع|\bEXW\b|\bex-?works\b|\bcosts?\b", re.I)
_FEE_CTX_RE = re.compile(r"(?<![ء-ي])(?:رسوم|رسم|بيان\s+جمركي|فحص\s+بالأشعة|غرامة|رواتب|إيجار)(?![ء-ي])|"
                         r"\b(?:fees?|duty|duties|rent)\b", re.I)


_CUR_WORDS = (r"دينار|د\.ب|د\.ك|ريال|درهم|يورو|€|جنيه|روبية|ليرة|شلن|نايرا|رينغيت|دولار|\$|"
              r"BHD|KWD|JOD|SAR|QAR|AED|OMR|EUR|EGP|JPY|INR|TRY|KES|NGN|MAD|DZD|MYR|YER|LYD|USD")


def _evidence_link(doc: "StudyDoc", product: str, price: str) -> bool:
    """رابطٌ في سجلّ الأدلة لنفس المنتج أو السعر — السجلّ الموثَّق قد يكون في الأدلة لا في النصّ."""
    tokens = [t for t in re.findall(rf"[{_AR}A-Za-z]{{3,}}", product or "")][:3]
    price = (price or "").strip()
    rows = list(doc.evidence_lines)
    for f in doc.findings or []:
        if isinstance(f, dict):
            rows.append(" ".join(str(f.get(k) or "") for k in ("value", "note", "source", "url")))
    for line in rows:
        if not _URL_RE.search(line):
            continue
        body = norm_digits(_URL_RE.sub(" ", line))
        has_price = bool(price) and bool(re.search(
            rf"(?<![\d.]){re.escape(price)}(?!\d|\.\d)\s*[^\d\s]{{0,3}}\s*(?:{_CUR_WORDS})", body, re.I))
        has_tokens = bool(tokens) and all(t.lower() in body.lower() for t in tokens)
        if (has_price and (has_tokens or not tokens)) or (has_tokens and not price):
            return True
    return False


def _is_local_currency(cur: str, iso: str) -> bool:
    c = (cur or "").lower()
    return any(k in c for k in _LOCAL_CUR.get(iso, ()))


def shelf_floor_local_per_kg(doc: StudyDoc) -> "tuple[float | None, dict]":
    """الحد الأدنى لسعر الرف بالعملة المحلية/كغ = أدنى متوسط سعر استيراد (آخر ثلاث
    سنوات) × سعر الصرف × (1 + الضريبة). أدنى السنوات لا أحدثها كي لا يُرفَض إلا ما
    يستحيل تحت أيّ سنة."""
    ref = reference_unit_values(doc)
    fx = doc.meta.get("fx_local_per_usd")
    vat = doc.meta.get("vat_pct")
    basis = {"import_unit_values": ref, "fx_local_per_usd": fx, "vat_pct": vat}
    if not ref or not fx:
        return None, basis
    recent = sorted(ref.items())[-3:]
    lo_year, lo = min(recent, key=lambda kv: kv[1])
    v = float(vat) if vat is not None else 0.0
    basis.update({"basis_year": lo_year, "basis_usd_per_kg": lo,
                  "vat_assumed_zero": vat is None})
    return round(lo * float(fx) * (1 + v / 100.0), 4), basis


def check_shelf_prices(doc: StudyDoc) -> Finding:
    tables = [(h, rows) for h, rows in _table_rows(doc.report)
              if any(n in " ".join(h).lower() for n in (x.lower() for x in _PRICE_TABLE_HEAD))]
    floor, basis = shelf_floor_local_per_kg(doc)
    cur_code = str(doc.meta.get("currency") or "").upper()
    items: list = []
    documented = 0
    rejected_figures: list = []
    for header, rows in tables:
        i_prod = _col(header, "المنتج", "العلامة", "product", "brand")
        i_pack = _col(header, "العبوة", "الوزن", "الحجم", "pack", "size", "weight")
        i_price = _col(header, "سعر التجزئة", "سعر الرف", "retail", "shelf")
        i_unit = _col(header, "لوحدة المقارنة", "/كجم", "per kg", "للكيلو")
        i_link = _col(header, "الرابط", "رابط", "url", "link")
        for row in rows:
            joined = " | ".join(row)
            prod = _cell(row, i_prod)
            if re.search(r"محل\s+الدراسة|سعر\s+مصنع|EXW", joined):
                continue  # صفّ المنتج محل الدراسة لا سعر رفّ
            price_cell = _cell(row, i_price)
            pm = _PRICE_CELL_RE.search(price_cell)
            if not pm and _NA_RE.search(price_cell or "—"):
                continue  # بلا سعر — فجوة معلنة لا سعر
            reasons: list = []
            link = bool(_URL_RE.search(joined)) or bool(
                i_link is not None and _cell(row, i_link) and not _NA_RE.search(_cell(row, i_link))) \
                or _evidence_link(doc, prod, pm.group(1) if pm else "")
            if not link:
                reasons.append("بلا رابط منتج")
            kg = _pack_kg(_cell(row, i_pack))
            if kg is None:
                reasons.append("بلا وزن عبوة")
            if not pm:
                reasons.append("بلا سعر/عملة")
            if not _MONTH_RE.search(joined):
                reasons.append("بلا تاريخ رصد")
            social = bool(_SOCIAL_RE.search(joined))
            if social:
                reasons.append("مصدر تواصل اجتماعي — «غير موثق» ولا يدخل أي حساب")
            per_kg = None
            cur = pm.group(3) if pm else ""
            price = float(pm.group(1)) if pm else None
            if pm and pm.group(2):
                reasons.append("نطاق سعري لا سعر منتج واحد")
            if price is not None and kg:
                per_kg = round(price / kg, 3)
                stated = _PRICE_CELL_RE.search(_cell(row, i_unit) or "")
                if stated and not near(float(stated.group(1)), per_kg, 1.0):
                    reasons.append(f"السعر للكيلو المعلن {stated.group(1)} ≠ المحسوب {per_kg}")
            below = None
            if per_kg is not None and floor is not None and _is_local_currency(cur, cur_code):
                below = per_kg < floor
                if below:
                    reasons.append(f"{per_kg} {cur}/كغ دون الحد الأدنى {floor} "
                                   f"(= {basis.get('basis_usd_per_kg')} $/كغ × "
                                   f"{basis.get('fx_local_per_usd')} × (1+{basis.get('vat_pct') or 0}%))")
            item = {"status": FAIL if reasons else PASS, "product": prod, "row": _snip(joined, 200),
                    "price": price, "currency": cur, "pack_kg": kg, "per_kg": per_kg,
                    "has_link": link, "social": social, "below_floor": below,
                    "why": "؛ ".join(reasons) if reasons else "موثق"}
            items.append(item)
            if reasons:
                for fig in {x for x in (price, per_kg) if x is not None}:
                    rejected_figures.append((prod, fig))
            else:
                documented += 1
    # أرقام مرفوضة/غير موثقة دخلت النثر (نطاق، مقارنة، حساب)
    seen_pairs: set = set()
    price_rows = {"|".join(r) for _h, rows in tables for r in rows} | \
        {"|".join(h) for h, _r in tables}
    scan = "\n".join(l for l in doc.report.split("\n")
                     if "|".join(c.strip() for c in l.strip().strip("|").split("|")) not in price_rows)
    for s_ in report_sentences(scan):
        for v, _st, en, _raw in numbers_in(s_):
            tail = s_[en:en + 25]
            if not re.match(r"\s*(?:(?:و|إلى|-|–)\s*\d+(?:\.\d+)?\s*)?"
                            r"(?:دينار|د\.ب|ريال|درهم|/\s*ك|للكيلو|BHD|SAR|AED)", tail):
                continue
            for prod, fig in rejected_figures:
                if near(v, fig, 0.5) and (prod, s_) not in seen_pairs:
                    seen_pairs.add((prod, s_))
                    items.append({"status": FAIL, "product": prod, "row": _snip(s_),
                                  "why": f"رقم غير موثق ({fig}) دخل النثر/الحساب"})
    # أسعار رفوف مذكورة في النصّ: كلٌّ منها يجب أن يقابله سجلٌّ موثَّق (صفٌّ موثق في الجدول
    # أو سطرُ دليلٍ برابط)؛ وإلا فهو سعرٌ بلا رابط/وزن/تاريخ.
    good = [x for i in items if i.get("status") == PASS and "pack_kg" in i
            for x in (i.get("price"), i.get("per_kg")) if x is not None]
    flagged = {(it.get("row"), it.get("product")) for it in items if "pack_kg" not in it}
    bad_vals = {fig for _p, fig in rejected_figures}
    for s_ in report_sentences(scan):
        if _FEE_CTX_RE.search(s_):
            continue
        for m in _PROSE_PRICE_RE.finditer(s_):
            v = float(m.group(1))
            if _COST_CTX_BEFORE_RE.search(s_[max(0, m.start() - 45): m.start()]):
                continue  # تكلفة إنتاج/سعر مصنع لا سعر رف
            if re.match(r"دولار|\$|USD", m.group(2), re.I):
                # الدولار عملةُ أسعار الحدود غالباً: يُقرأ سعرَ رفٍّ فقط بقرينة تجزئةٍ صريحة،
                # وبلا قرينة استيراد/حدود/جملة قبله.
                if not _RETAIL_STRICT_RE.search(s_) or \
                        _IMPORT_PRICE_CTX.search(s_[max(0, m.start() - 60): m.start()]):
                    continue
            shelf_ctx = bool(m.group(3)) or bool(_SHELF_CTX_RE.search(s_))
            if not shelf_ctx or any(near(v, g, 0.5) for g in good) \
                    or any(near(v, b, 0.5) for b in bad_vals):
                continue
            if _evidence_link(doc, "", m.group(1)):
                continue
            key = (_snip(s_), None)
            if key in flagged:
                continue
            flagged.add(key)
            items.append({"status": FAIL, "row": _snip(s_), "price": v, "currency": m.group(2),
                          "why": f"سعر رف في النصّ ({m.group(0).strip()}) بلا سجلٍّ موثَّق "
                                 "(رابط المنتج والوزن وتاريخ الرصد)"})
    refs = doc.expected.get("reference_shelf_prices") or []
    missing_refs = [r for r in refs if not any(
        near(v, float(r.get("price") or 0), 0.5) for v, *_ in numbers_in(doc.report))]
    if missing_refs:
        items.append({"status": WARN, "why": "أسعار موثقة معروفة غائبة عن الدراسة: "
                      + "؛ ".join(f"{r.get('store')} {r.get('product')} {r.get('price')} {r.get('currency')}"
                                  for r in missing_refs)})
    fails = [i for i in items if i["status"] == FAIL]
    n_rows = sum(1 for i in items if "pack_kg" in i)
    if not tables and not fails:
        return Finding("F2", "فحص أسعار الرفوف", WARN,
                       "لا جدول أسعار رفوف في التقرير — لا سعر منافس موثق", items)
    note = (f"{documented} سعر موثق من {n_rows} صف"
            + (f"؛ الحد الأدنى {floor} {doc.meta.get('currency') or ''}/كغ" if floor is not None
               else "؛ لا حدّ أدنى (سعر الصرف أو متوسط الاستيراد غائب)"))
    if fails:
        return Finding("F2", "فحص أسعار الرفوف", FAIL, note + f"؛ {len(fails)} مخالفة", items)
    if documented < 5:
        return Finding("F2", "فحص أسعار الرفوف", WARN, note + "؛ أقل من 5 أسعار موثقة", items)
    return Finding("F2", "فحص أسعار الرفوف", PASS, note, items)


# ── F3 المرآة · mirror vs direct ───────────────────────────────────────────
#
# الحقائق تُستخرج من **بيانات الدراسة نفسها**، لا من قيمٍ مرجعية: نتائج المهام المنظَّمة
# (`status="mirrored"`، مصدر «(مرآة)»، `data_year`) حين تتوفّر النتيجة كاملة، وإلا سطورُ
# سياق الأدلة بعلامات «مباشر/مرآة» ومصادرها. الحقيقة «مباشرة» حين مصدرها إحصاءُ تجارةٍ رسمي
# (UN Comtrade) بلا علامة مرآة، و«مرآة» بعلامتها؛ وما سواهما (بحث ويب) لا يدخل F3.

_MIRROR_RE = re.compile(r"مرآة|مرآتية|مرايا|\bmirror(?:ed)?\b|بيانات\s+الدول\s+الشريكة|"
                        r"تصريحات\s+الدول\s+التي\s+تصدّ?ر|صادرات\s+الشركاء|partner[- ]reported", re.I)
_DIRECT_RE = re.compile(r"مباشر|direct|صرّ?حت\s+بها|مصرَّ?حة|reported\s+by\s+the\s+market", re.I)
_OFFICIAL_TRADE_RE = re.compile(r"comtrade|كومتريد|الأمم\s+المتحدة\s+للتجارة", re.I)
_DIVERGENCE_RE = re.compile(r"تباين|divergence")
_LABELLED_MIRROR_RE = re.compile(_MIRROR_RE.pattern + r"|تقدير\s+من|بيانات\s+الشركاء|"
                                 r"من\s+(?:تصريحات|بيانات)\s+(?:الدول|الشركاء)", re.I)
_LEDGER_HEAD_RE = re.compile(r"^سجلّ?\s+الحقائق\s*[—-]\s*(.+?):")
_SRC_TAG_RE = re.compile(r"\[المصدر:\s*([^\]]*)\]")
_LEDGER_SRC_RE = re.compile(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$")

#: المؤشرات ووحداتها: money بالدولار، pct نسبة، index مؤشر تركّز، count عدد.
INDICATORS = {"imports_usd": "money", "saudi_flow_usd": "money", "saudi_share_pct": "pct",
              "hhi": "index", "supplier_count": "count"}
_INDICATOR_AR = {"imports_usd": "واردات السوق", "saudi_flow_usd": "الواردات من السعودية",
                 "saudi_share_pct": "الحصة السعودية", "hhi": "مؤشر التركّز",
                 "supplier_count": "عدد الدول المورّدة"}

# «المملكة» وحدها تعني السعودية في تقاريرنا، و«المملكة المتحدة» ليست هي.
_SAUDI = r"(?:ال)?سعودي(?:ة)?|المملكة(?!\s+المتحدة)|Saudi(?:\s+Arabia)?|KSA"
_SHARE_RE = re.compile(rf"(?:{_SAUDI})[^\d%\n]{{0,40}}?(\d+(?:\.\d+)?)\s*%", re.I)
_SHARE_CTX_RE = re.compile(r"حصة|بحصة|نصيب|share|الدول\s+(?:ال)?\w*\s*(?:ال)?أعلى|مورّ?د", re.I)
_PCT_ONLY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[%٪]")
_SAUDI_SHARE_CTX_RE = re.compile(r"(?:ال)?حصة\s+(?:ال)?سعودي(?:ة)?|حصة\s+(?:ال)?مملكة|Saudi\s+share", re.I)
_HHI_RE = re.compile(r"(?:HHI|مؤشر\s+(?:ال)?تركّ?ز(?:\s+(?:ال)?مورّ?دين)?|درجة\s+تركّ?ز)"
                     r"[^\d\n]{0,25}?(\d[\d,]*(?:\.\d+)?)", re.I)
_COUNT_RE = re.compile(r"(\d{1,3})\s+(?:دولة|دول)(?!\w)")
_COUNT_CTX_RE = re.compile(r"مورّ?د|HHI|تركّ?ز|supplier", re.I)
_MONEY_AMT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(مليون|ملايين|مليار|مليارات|million|billion|bn)?\s*"
                           r"(?:دولار(?:\s*أمريكي)?|USD|\$)", re.I)
_IMPORTS_TOTAL_RE = re.compile(
    r"إجمالي\s+(?:ال)?(?:واردات|استيراد)|واردات\s+(?:ال)?سوق|حجم\s+(?:ال)?واردات|من\s+العالم|"
    r"واردات\s+مصرَّ?حة|واردات\s+\d{4}\s+تحت|مرآة\s+صادرات\s+الشركاء|صادرات\s+الشركاء|"
    r"total\s+imports|market\s+imports", re.I)
_SAUDI_FLOW_RE = re.compile(rf"صادرات\s+(?:ال)?سعودية|(?:واردات|استيراد)\s+\S+\s+من\s+(?:ال)?سعودية|"
                            rf"Saudi\s+exports", re.I)
_NOT_TOTAL_PHRASE_RE = re.compile(r"ليست?\s+إجمالي\s+(?:ال)?واردات(?:\s+(?:ال)?سوق)?|not\s+(?:the\s+)?total\s+imports", re.I)
_SUPPLIER_LINE_RE = re.compile(r"^\s*مورّ?د\s*:|صادرات\s+هذا\s+المورّ?د|المورّ?د\s+وحده", re.I)
_NOT_TOTAL_RE = re.compile(r"حصة|سعر|للكيلو|/\s*ك|كجم|كغ|طن|الوزن|كمي|price|share|kg", re.I)


@dataclass
class Fact:
    """حقيقةٌ رقمية من أدلة الدراسة: المؤشر، القيمة، السنة، مباشر/مرآة، المصدر، النص."""
    indicator: str
    value: float
    year: "int | None"
    kind: str
    source: str = ""
    text: str = ""

    @property
    def unit(self) -> str:
        return INDICATORS[self.indicator]


def _finding_lines(findings: list) -> list:
    """نتائج المهام المنظَّمة → (نص، مصدر، علم مرآة، سنة) — يُقرأ منها ما لا يقرؤه النص."""
    out = []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        v = f.get("value")
        src = norm_digits(f.get("source") or "")
        note = norm_digits(f.get("note") or "")
        if isinstance(v, str):
            v = norm_digits(v)
        mirrored = str(f.get("status") or "") == "mirrored" or bool(_MIRROR_RE.search(src + " " + note))
        yr = f.get("data_year")
        if isinstance(v, dict):
            out.append(("dict", v, src, mirrored, yr, note))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(("num", float(v), src, mirrored, yr, note))
        elif isinstance(v, str) and v.strip():
            out.append(("text", f"{note} {v}" if note and note not in v else v, src, mirrored, yr, note))
    return out


def _clause_kinds(sentence: str, source_kind: "str | None") -> list:
    """[(عبارة، نوع)] — العبارةُ تأخذ أوّل علامةٍ فيها، والبلا علامة ترث ما قبلها، والأولى
    بلا علامة تأخذ نوعَ المصدر («مرآة»/«مباشر»/لا شيء)."""
    out, kind = [], source_kind
    for clause in _CLAUSE_SPLIT.split(sentence):
        marks = sorted([(m.start(), "mirror") for m in _MIRROR_RE.finditer(clause)]
                       + [(m.start(), "direct") for m in _DIRECT_RE.finditer(clause)])
        if marks:
            kind = marks[0][1]
        elif kind is None and _OFFICIAL_TRADE_RE.search(clause):
            kind = "direct"
        out.append((clause, kind))
    return out


def _year_of(*texts: str) -> "int | None":
    for t in texts:
        ys = {int(y) for y in _YEAR_RE.findall(t or "")}
        if len(ys) == 1:
            return ys.pop()
    return None


def _facts_from_text(text: str, src: str, src_kind: "str | None",
                     year_hint: "int | None" = None) -> list:
    facts = []
    for sent in sentences(text):
        # جملةُ مقارنةٍ للحصة السعودية بنسبتين («… 12.02% مقابل 1.43% …»): كل نسبة بنوع عبارتها.
        pcts = _PCT_ONLY_RE.findall(sent)
        compare_share = len(pcts) == 2 and bool(_SAUDI_SHARE_CTX_RE.search(sent))
        for clause, kind in _clause_kinds(sent, src_kind):
            if kind not in ("direct", "mirror"):
                continue
            yr = _year_of(clause, src) or year_hint or _year_of(sent)
            if compare_share:
                for p in _PCT_ONLY_RE.findall(clause):
                    facts.append(Fact("saudi_share_pct", float(p), yr, kind, src, clause))
            else:
                for m in _SHARE_RE.finditer(clause):
                    if _SHARE_CTX_RE.search(sent):
                        facts.append(Fact("saudi_share_pct", float(m.group(1)), yr, kind, src, clause))
            for m in _HHI_RE.finditer(clause):
                v = _to_float(m.group(1))
                if v is not None and 100 <= v <= 10000:
                    facts.append(Fact("hhi", v, yr, kind, src, clause))
            for m in _COUNT_RE.finditer(clause):
                if _COUNT_CTX_RE.search(sent):
                    facts.append(Fact("supplier_count", float(m.group(1)), yr, kind, src, clause))
            # «ليست إجمالي واردات السوق» نفيٌ لا إثبات، وسطرُ المورّد قيمةُ مورّدٍ لا إجمالي.
            sent_pos = _NOT_TOTAL_PHRASE_RE.sub(" ", sent)
            ind = ("saudi_flow_usd" if _SAUDI_FLOW_RE.search(clause)
                   else "imports_usd" if _IMPORTS_TOTAL_RE.search(sent_pos)
                   and not _NOT_TOTAL_RE.search(clause) and not _SUPPLIER_LINE_RE.search(sent)
                   else None)
            if ind:
                for m in _MONEY_AMT_RE.finditer(clause):
                    v = _to_float(m.group(1))
                    if v is not None:
                        facts.append(Fact(ind, v * _MAG.get((m.group(2) or "").lower(), 1.0), yr,
                                          kind, src, clause))
    return facts


def _line_source(line: str) -> str:
    m = _SRC_TAG_RE.search(line)
    if m:
        return m.group(1)
    if _LEDGER_HEAD_RE.match(line):
        m = _LEDGER_SRC_RE.search(line)
        return m.group(1) if m else ""
    return ""


def study_facts(doc: "StudyDoc") -> list:
    """كل حقائق المؤشرات الخمسة من بيانات الدراسة (منظَّمة أولاً ثم نصّ الأدلة)، بلا تكرار."""
    facts: list = []
    for kind_, v, src, mirrored, yr, note in _finding_lines(doc.findings):
        sk = "mirror" if mirrored else ("direct" if _OFFICIAL_TRADE_RE.search(src) else None)
        if kind_ == "dict":
            if sk is None:
                continue
            y = yr or _year_of(note)
            if isinstance(v.get("hhi"), (int, float)):
                facts.append(Fact("hhi", float(v["hhi"]), y, sk, src, note))
            if isinstance(v.get("supplier_count"), (int, float)):
                facts.append(Fact("supplier_count", float(v["supplier_count"]), y, sk, src, note))
            for row in v.get("top_suppliers") or []:
                if isinstance(row, dict) and re.search(r"saudi|سعود", str(row.get("partner") or ""), re.I) \
                        and isinstance(row.get("share"), (int, float)):
                    facts.append(Fact("saudi_share_pct", float(row["share"]), y, sk, src, note))
        elif kind_ == "num":
            if sk is None:
                continue
            y = yr or _year_of(note)
            if _SAUDI_FLOW_RE.search(note):
                facts.append(Fact("saudi_flow_usd", v, y, sk, src, note))
            elif _IMPORTS_TOTAL_RE.search(note) and not _NOT_TOTAL_RE.search(note) and v >= 1000:
                facts.append(Fact("imports_usd", v, y, sk, src, note))
            elif _HHI_RE.search(note + " 0") and 100 <= v <= 10000 and "حصة" not in note:
                facts.append(Fact("hhi", v, y, sk, src, note))
            elif re.search(r"حصة\s+(?:ال)?(?:سعودية|السعودية|المملكة)|Saudi\s+share", note, re.I):
                facts.append(Fact("saudi_share_pct", v, y, sk, src, note))
        else:
            facts += _facts_from_text(v, src, sk, yr)
    for line in doc.evidence_lines:
        src = _line_source(line)
        sk = "mirror" if _MIRROR_RE.search(src) else ("direct" if _OFFICIAL_TRADE_RE.search(src) else None)
        body = _SRC_TAG_RE.sub(" ", line)
        if " = " in body and not _LEDGER_HEAD_RE.match(line):
            name, _, val = body.partition(" = ")
            v = _to_float(val.strip().split()[0]) if val.strip() else None
            if v is not None and sk and _IMPORTS_TOTAL_RE.search(name):
                facts.append(Fact("imports_usd", v, _year_of(src), sk, src, line))
                continue
        facts += _facts_from_text(body, src, sk)
    seen, out = set(), []
    for f in facts:
        k = (f.indicator, round(f.value, 2), f.year, f.kind)
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def _report_figures(text: str) -> list:
    """[(القيمة المطلقة، الوحدة، الموضع)] لأرقام النص؛ السنوات ورموز HS تُستبعد."""
    out = []
    t = norm_digits(text)
    for v, s, e, raw in numbers_in(t):
        if _YEAR_RE.fullmatch(raw) or re.fullmatch(r"\d{6}", raw):
            continue
        tail, head = t[e:e + 20], t[max(0, s - 20):s]
        mm = re.match(r"\s*(مليون|ملايين|مليار|مليارات|million|billion)", tail)
        if mm:
            out.append((v * _MAG[mm.group(1).lower()], "money", s))
        elif re.match(r"\s*(?:دولار|\$|USD)", tail):
            out.append((v, "money", s))
        elif re.match(r"\s*[%٪]", tail):
            out.append((v, "pct", s))
        elif re.match(r"\s*(?:دولة|دول)(?!\w)", tail):
            out.append((v, "count", s))
        elif re.match(r"\s*نقطة", tail) or re.search(r"HHI|تركّ?ز", head):
            out.append((v, "index", s))
        else:
            out.append((v, "", s))
    return out


def _matches(fig: tuple, fact: "Fact") -> bool:
    v, unit, _ = fig
    if unit == fact.unit or (unit == "" and fact.unit == "index" and v >= 100):
        return near(v, fact.value, 0.5)
    return False


def _mirror_only_years(facts: list) -> set:
    """سنواتٌ رقمُ وارداتها مرآةٌ فقط (لا حقيقةَ واردات مباشرة لها)."""
    imp = [f for f in facts if f.indicator == "imports_usd"]
    return {f.year for f in imp if f.kind == "mirror" and f.year} - \
        {f.year for f in imp if f.kind == "direct" and f.year}


_IMPORT_LEDGER_KEY_RE = re.compile(r"واردات|الواردات|النمو|نمو|المركّب|المركب|imports|growth|CAGR", re.I)
_SAUDI_KEY_RE = re.compile(_SAUDI, re.I)
_SHARE_KEY_RE = re.compile(r"حصة|نصيب|share", re.I)
_HHI_KEY_RE = re.compile(r"HHI|تركّ?ز|هيرفندال", re.I)
_COUNT_KEY_RE = re.compile(r"عدد\s+(?:ال)?(?:دول|مورّ?د)|supplier\s+count", re.I)


def _ledger_indicator(key: str) -> "str | None":
    """مؤشرُ F3 لبند سجلّ الحقائق من تسميته — None حين لا يقابل مؤشراً من الخمسة."""
    if _HHI_KEY_RE.search(key):
        return "hhi"
    if _SAUDI_KEY_RE.search(key):
        return "saudi_share_pct" if _SHARE_KEY_RE.search(key) else "saudi_flow_usd"
    if _COUNT_KEY_RE.search(key):
        return "supplier_count"
    if _SHARE_KEY_RE.search(key):
        return None                                  # حصةُ أكبر مورّد ليست مؤشراً هنا
    return "imports_usd" if _IMPORT_LEDGER_KEY_RE.search(key) else None
#: سياقُ كل مؤشر حول رقمه في النصّ — «12%» نموٌّ ليست الحصة السعودية 12.02%.
_IND_CTX = {"imports_usd": re.compile(r"واردات|استيراد|حجم|سوق|imports|market", re.I),
            "saudi_flow_usd": re.compile(r"سعودي|المملكة|Saudi", re.I),
            "saudi_share_pct": re.compile(r"حصة|نصيب|share", re.I),
            "hhi": re.compile(r"HHI|تركّ?ز|نقطة", re.I),
            "supplier_count": re.compile(r"دولة|دول|مورّ?د|supplier", re.I)}


def check_mirror(doc: StudyDoc) -> Finding:
    facts = study_facts(doc)
    items: list = []
    direct = {i: [f for f in facts if f.indicator == i and f.kind == "direct"] for i in INDICATORS}
    mirror = {i: [f for f in facts if f.indicator == i and f.kind == "mirror"] for i in INDICATORS}
    paras = paragraphs(doc.report)

    all_direct = [f for fs in direct.values() for f in fs]

    def mirror_hit(fig: tuple, fact: "Fact", text: str) -> bool:
        """الرقم رقمُ مرآةٍ لهذا المؤشر: يطابق قيمتها، ولا يطابق رقماً مباشراً، وفي سياق مؤشره."""
        if not _matches(fig, fact) or any(_matches(fig, d) for d in all_direct):
            return False
        win = text[max(0, fig[2] - 100): fig[2] + 40]  # العربية تسمّي المؤشر قبل رقمه بجملة
        return bool(_IND_CTX[fact.indicator].search(win))

    def holders(fact: "Fact") -> list:
        return [p for p in paras if any(mirror_hit(fg, fact, p) for fg in _report_figures(p))]

    def latest(fs: list) -> "Fact":
        return max(fs, key=lambda f: (f.year or 0))

    # ١) مباشر ومرآة لنفس المؤشر بفرق > 25%: كل فقرة تعرض رقم المرآة تسمّيه «تباين».
    for ind in INDICATORS:
        if not (direct[ind] and mirror[ind]):
            continue
        d, m = latest(direct[ind]), latest(mirror[ind])
        if d.value == 0:
            continue
        gap = abs(m.value - d.value) / abs(d.value) * 100.0
        if gap <= 25.0:
            continue
        untagged = [p for p in holders(m) if not _DIVERGENCE_RE.search(p)]
        if untagged:
            items.append({"status": FAIL, "indicator": _INDICATOR_AR[ind], "where": "التقرير",
                          "direct": d.value, "direct_year": d.year, "mirror": m.value,
                          "mirror_year": m.year, "gap_pct": round(gap, 1), "text": _snip(untagged[0]),
                          "why": f"فرق {gap:.0f}% بين المباشر {d.value:g} ({d.year or '—'}) والمرآة "
                                 f"{m.value:g} ({m.year or '—'}) بلا وسم «تباين» في فقرة الرقم"})
    # ٢) موضع رقم المرآة: ممنوع في الخلاصة وكأول رقم في قسم حين يوجد مباشرٌ لمؤشره؛ وحين
    #    لا مباشرَ له (سوقٌ لا تصرّح) يُسمح به موسوماً «مرآة/تقدير من بيانات الشركاء».
    seen_where: set = set()
    for ind in INDICATORS:
        for m in mirror[ind]:
            for num, title, body in doc.sections:
                figs = _report_figures(body)
                hit = [fg for fg in figs if mirror_hit(fg, m, norm_digits(body))]
                if not hit:
                    continue
                first = figs[0] if figs else None
                key = (num, ind)
                if direct[ind]:
                    if num == 1 and key not in seen_where:
                        seen_where.add(key)
                        items.append({"status": FAIL, "where": "القسم 1", "indicator": _INDICATOR_AR[ind],
                                      "figure": m.value, "text": _snip(body),
                                      "why": "رقم مرآة في الخلاصة التنفيذية وللمؤشر رقمٌ مباشر"})
                    elif first is not None and mirror_hit(first, m, norm_digits(body)) and key not in seen_where:
                        seen_where.add(key)
                        items.append({"status": FAIL, "where": f"القسم {num} ({title})",
                                      "indicator": _INDICATOR_AR[ind], "figure": m.value,
                                      "text": _snip(body),
                                      "why": "أول رقم في القسم رقم مرآة وللمؤشر رقمٌ مباشر"})
                else:
                    for p in paragraphs(body):
                        if any(mirror_hit(fg, m, p) for fg in _report_figures(p)) \
                                and not _LABELLED_MIRROR_RE.search(p) and key not in seen_where:
                            seen_where.add(key)
                            items.append({"status": FAIL, "where": f"القسم {num} ({title})",
                                          "indicator": _INDICATOR_AR[ind], "figure": m.value,
                                          "text": _snip(p),
                                          "why": "رقم مرآة بلا وسم «مرآة/تقدير من بيانات الشركاء»"})
    # ٣) رأس سجلّ الحقائق: مرآةٌ صريحة، أو مؤشرُ وارداتٍ سنتُه سنةُ مرآةٍ فقط — ممنوعان
    #    حين للمؤشر رقمٌ مباشر. الدرس ٣٠٠ (قراءة المالك ٢): سوقٌ لا تصرّح أصلاً رأسُها مرآةٌ
    #    موسومة (السجلّ يكتب «بيانات مرآة» بجوار رقمها) — مسموح.
    mirror_years = _mirror_only_years(facts)
    for line in doc.evidence_lines:
        m = _LEDGER_HEAD_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip()
        ind = _ledger_indicator(key)
        has_direct = bool(direct[ind]) if ind else bool(all_direct)
        if _MIRROR_RE.search(line):
            if has_direct:
                items.append({"status": FAIL, "where": "سجلّ الحقائق", "key": key,
                              "text": _snip(line),
                              "why": "رأس السجلّ لهذا المؤشر رقم مرآة وله تصريح مباشر"})
            continue
        if _IMPORT_LEDGER_KEY_RE.search(key) and direct["imports_usd"]:
            bad = sorted({int(y) for y in _YEAR_RE.findall(line[m.end():])} & mirror_years)
            if bad:
                items.append({"status": FAIL, "where": "سجلّ الحقائق", "key": key, "text": _snip(line),
                              "why": f"مؤشر واردات مبنيّ على سنة {bad[-1]} ولا تصريح مباشر لها "
                                     "(سنة مرآة فقط) — رأس السلسلة يجب أن يكون آخر سنة مباشرة"})
    n_m = sum(len(v) for v in mirror.values())
    if items:
        return Finding("F3", "فحص المرآة", FAIL, f"{len(items)} مخالفة مرآة/تباين", items)
    if not n_m:
        return Finding("F3", "فحص المرآة", PASS, "لا أرقام مرآة في أدلة الدراسة")
    return Finding("F3", "فحص المرآة", PASS, f"{n_m} رقم مرآة موسوم ولا يحلّ محلّ رقمٍ مباشر")


# ── F4 الجمارك · tariff claims need the origin rule ─────────────────────────

_EXEMPT_RE = re.compile(
    r"(?:رسوم|الرسوم|رسم|تعرفة|التعرفة|تعريفة|التعريفة|جمارك|الجمارك|جمركي\w*)[^.\n|]{0,40}?"
    r"(?:(?<![\d.])0(?:\.0+)?\s*[%٪]|صفر(?:\s*(?:بالمئة|في\s*المئة|%|٪))?)"
    r"|(?:(?<![\d.])0(?:\.0+)?\s*[%٪]|صفر\s*(?:بالمئة|في\s*المئة))[^.\n|]{0,30}(?:رسوم|تعرفة|جمرك)"
    r"|إعفاء\w*(?:\s+\w+){0,2}\s+(?:جمركي\w*|كامل\w*|من\s+الرسوم)|معفا?ة?\s+من\s+الرسوم"
    r"|لا\s+رسوم\s+جمركية|بلا\s+رسوم(?:\s+جمركية)?|لا\s+جمارك|بلا\s+جمارك"
    r"|لا\s+(?:ت|ي)دفع\s+رسوم(?:اً|ًا)?\s+جمركية|الإعفاء\s+الجمركي"
    r"|zero\s+tariff|duty[- ]free|(?<![\d.])0%\s+(?:tariff|duty)|tariff[- ]free"
    r"|exempt(?:ion)?\s+from\s+(?:customs\s+)?dut",
    re.I)
_ORIGIN_RULE_RE = re.compile(
    r"قاعدة\s+(?:ال)?منشأ|قواعد\s+(?:ال)?منشأ|شرط\s+(?:ال)?منشأ|شروط\s+(?:ال)?منشأ"
    r"|قيمة\s+مضافة(?:\s+محلية)?\s*(?:لا\s+تقل|≥|لا\s+تقلّ|بنسبة|من\s+\d|\d)"
    r"|(?:40|٤٠)\s*%[^.\n|]{0,60}(?:قيمة|مصنع|منشأ)|ملكية\s+خليجية"
    r"|rules?\s+of\s+origin|origin\s+(?:rule|criteri)|value[- ]added\s+(?:≥|of\s+at\s+least|not\s+less|threshold)",
    re.I)


def check_tariff_claims(doc: StudyDoc) -> Finding:
    items: list = []
    for num, title, body in doc.sections or [(None, "", doc.report)]:
        for p in paragraphs(body):
            m = _EXEMPT_RE.search(p)
            if not m:
                continue
            if _ORIGIN_RULE_RE.search(p):
                continue
            items.append({"status": FAIL, "where": f"القسم {num} ({title})" if num else "التقرير",
                          "phrase": m.group(0), "text": _snip(p),
                          "why": "إعفاء/رسوم 0% بلا شرط قاعدة المنشأ للاتفاقية في الفقرة نفسها"})
    if items:
        return Finding("F4", "فحص الجمارك", FAIL, f"{len(items)} فقرة إعفاء بلا شرط منشأ", items)
    if _EXEMPT_RE.search(doc.report):
        return Finding("F4", "فحص الجمارك", PASS, "كل إعفاء مقرون بشرط المنشأ")
    return Finding("F4", "فحص الجمارك", PASS, "لا ادّعاء إعفاء في التقرير")


# ── F5 الحكم · investment verdict needs a cost or a ceiling ─────────────────

SCREENING_LABEL = "فرز سوق أولي"
_VERDICT_LINE_RE = re.compile(r"(?:التوصية|الحكم|القرار|Recommendation|Verdict)\s*[:：]\s*([^\n.،]+)")
_VERDICT_LABELS = ("دخول مشروط", "ادخل الآن", "ادخل فوراً", "دخول قوي", "دخول", "لا تدخل",
                   "أجل الدخول", "لا ننصح بالدخول", "فرز سوق أولي", "مراقبة السوق",
                   "راقب السوق", "WATCH",
                   "STRONG GO", "PRELIMINARY GO", "CONDITIONAL-GO", "CONDITIONAL GO",
                   "NO-GO", "GO")
_COST_RE = re.compile(
    r"(?:سعر\s+(?:ال)?مصنع|تكلفة\s+(?:ال)?(?:إنتاج|وحدة|مصنع)(?:\s+(?:ال)?(?:وحدة|كيلو\w*))?|"
    r"تكلفة\s+إنتاج\s+(?:ال)?(?:وحدة|كيلو\w*)|EXW|ex-?works|production\s+cost|unit\s+cost)"
    r"[^.\n|،,؛]{0,40}?(\d[\d,]*(?:\.\d+)?)\s*(?:دولار|ريال|\$|USD|SAR|دينار|د\.ب|BHD|درهم)", re.I)
_CEILING_RE = re.compile(
    r"(?:أقصى\s+سعر\s+مصنع|سقف\s+(?:ال)?سعر(?:\s+(?:ال)?مصنع)?|أعلى\s+سعر\s+مصنع\s+قابل|"
    r"maximum\s+(?:competitive\s+)?ex-?works|max(?:imum)?\s+EXW)"
    r"[^.\n|]{0,60}?(\d[\d,]*(?:\.\d+)?)", re.I)
_NA_NEAR_RE = re.compile(r"غير\s+(?:متاح|محسوب|معروف)|لم\s+(?:نحسب|يُحسب|يحسب)")


def detect_verdict(doc: StudyDoc) -> "str | None":
    v = ((doc.view or {}).get("deep_research") or {}).get("verdict_label") if doc.view else None
    if v:
        return str(v)
    head = doc.section(1) or doc.report[:1500]
    m = _VERDICT_LINE_RE.search(head)
    if m:
        txt = m.group(1).strip()
        return _find_label(txt) or txt
    return _find_label(head)


def _find_label(text: str) -> "str | None":
    """أطولُ تسميةِ حكمٍ تقع كلمةً كاملة؛ اللاتينية بحالة أحرفها («GO» لا «good»)."""
    for lab in sorted(_VERDICT_LABELS, key=len, reverse=True):
        if re.match(rf"[{_AR}]", lab):
            pat = rf"(?<![{_AR}]){re.escape(lab)}(?![{_AR}])"
            if re.search(pat, text):
                return lab
        elif re.search(rf"(?<![A-Za-z-]){re.escape(lab)}(?![A-Za-z-])", text):
            return lab
    return None


#: أحكامٌ لا تلتزم بمال (انتظار/رفض) — «الحكم الاستثماري» في قاعدة المالك هو حكم الدخول.
_NON_ENTRY_RE = re.compile(r"(?<![ء-ي])(?:مراقبة\s+السوق|راقب\s+السوق|لا\s+تدخل|لا\s+ننصح\s+بالدخول|"
                           r"أجل\s+الدخول|فرز\s+سوق)(?![ء-ي])|(?<![A-Za-z-])(?:NO-GO|WATCH)(?![A-Za-z-])")


def check_verdict_basis(doc: StudyDoc) -> Finding:
    verdict = detect_verdict(doc)
    cost = doc.meta.get("production_cost_per_unit")
    cost_in_text = None
    for m in _COST_RE.finditer(doc.report):
        if _NA_NEAR_RE.search(m.group(0)):
            continue  # «سعر المصنع غير متاح» إعلانُ غياب لا تكلفة
        cost_in_text = m.group(0)
        break
    cost_present = cost is not None or cost_in_text is not None
    ceiling = None
    for m in _CEILING_RE.finditer(doc.report):
        if not _NA_NEAR_RE.search(doc.report[m.start(): m.end() + 30]):
            ceiling = m.group(0)
            break
    basis = {"verdict": verdict, "production_cost": cost if cost is not None else cost_in_text,
             "price_ceiling": ceiling}
    if verdict is None:
        return Finding("F5", "فحص الحكم", WARN, "لم يُرصد حكم في الخلاصة التنفيذية", [basis])
    if cost_present or ceiling:
        return Finding("F5", "فحص الحكم", PASS,
                       "الحكم مسنود بسعر مصنع أو سقف سعر محسوب", [basis])
    if SCREENING_LABEL in verdict or "screening" in verdict.lower():
        return Finding("F5", "فحص الحكم", PASS, f"بلا تكلفة ولا سقف — الحكم «{SCREENING_LABEL}» كما يجب", [basis])
    if _NON_ENTRY_RE.search(norm_digits(verdict)):
        return Finding("F5", "فحص الحكم", PASS,
                       f"«{verdict}» حكم انتظارٍ أو رفض لا يلتزم بمال — لا يحتاج تكلفة مصنع", [basis])
    vline = _VERDICT_LINE_RE.search(doc.section(1) or doc.report[:1500])
    basis.update({"status": FAIL, "required_label": SCREENING_LABEL, "where": "الخلاصة التنفيذية",
                  "text": vline.group(0) if vline else verdict,
                  "why": f"حكم استثماري «{verdict}» بلا سعر مصنع ولا سقف سعر محسوب — "
                         f"يُكتب «{SCREENING_LABEL}»"})
    return Finding("F5", "فحص الحكم", FAIL, basis["why"], [basis])


# ── F6 النطاق · recommendations stay inside the HS line ─────────────────────
#
# عامٌّ لكل بند: وصفُ البند الرسمي (`data/hs_reference.csv`) يُقرأ صفاتٍ بقطبيتها عبر معجمٍ
# عامّ (`data/hs_descriptor_terms_l1.csv`)، ثم كل صفةٍ في التوصيات تعاكس قطبيةً **أعلنها**
# وصفُ بند الدراسة = منتجٌ من بندٍ آخر. صفةٌ لم يعلنها البند لا تُحكَم (فحصٌ محافظ)، وفروقُ
# النوع (تمر/تين) خارج هذا الفحص — حدٌّ معلن. ويُرفض أيضاً ذكرُ رمز HS سداسيّ آخر صراحةً.

_NEG_BEFORE_RE = re.compile(r"(?:^|(?<=[\s،,(]))(?:غير|ليس|ليست|لا|بدون|بلا|not|non|un)\s*-?\s*$", re.I)
_HS6_RE = re.compile(r"(?<![\d.])(\d{4})\.?(\d{2})(?!\d)(?!\.\d)")
_EN_NEG_BEFORE_RE = re.compile(r"\b(?:not|non-?|excluding|other\s+than|without)\b[^,;]{0,30}$")
_WHETHER_RE = re.compile(r"whether\s+or\s+not\b[^,;]{0,40}$")


def _hs_rows() -> list:
    path = os.path.join(_ROOT, "data", "hs_codes.csv")
    try:
        with open(path, encoding="utf-8") as fh:
            return [r for r in csv.DictReader(fh) if (r.get("hs_code") or "").strip()]
    except OSError:
        return []


def _hs_reference() -> dict:
    """{رمز: الوصف الرسمي الإنجليزي} من `data/hs_reference.csv`."""
    path = os.path.join(_ROOT, "data", "hs_reference.csv")
    try:
        with open(path, encoding="utf-8") as fh:
            return {r["hscode"].strip(): r.get("description") or "" for r in csv.DictReader(fh)}
    except (OSError, KeyError):
        return {}


def descriptor_lexicon() -> list:
    """صفوف المعجم العامّ: {descriptor, en_neg, ar_forms, en_forms, polarity, hs4, head}."""
    path = os.path.join(_ROOT, "data", "hs_descriptor_terms_l1.csv")
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(l for l in fh if not l.startswith("#")):
                out.append({"descriptor": (r.get("descriptor") or "").strip().lower(),
                            "en_neg": [x for x in (r.get("en_neg") or "").lower().split("|") if x],
                            "forms": [x for x in (r.get("ar_forms") or "").split("|") + (r.get("en_forms") or "").split("|") if x],
                            "polarity": (r.get("polarity") or "+").strip(),
                            "hs4": (r.get("hs4") or "").strip(),
                            "head": [x for x in (r.get("head_ar") or "").split("|") if x]})
    except OSError:
        return []
    return out


def descriptor_spec(hs_code: str, reference: "dict | None" = None) -> dict:
    """{صفة: '+' أو '-'} مما **أعلنه** وصفُ البند؛ «whether or not X» لا تُعلن شيئاً.

    «Coffee; not roasted or decaffeinated» ⇒ roasted−، decaffeinated− (النفي يسري على «or»)؛
    «pasta (excluding stuffed), cooked» ⇒ stuffed−، cooked+."""
    ref = reference if reference is not None else _hs_reference()
    desc = (ref.get(norm_digits(hs_code).strip()) or "").lower()
    if not desc:
        return {}
    spec_txt = desc.split(";", 1)[1] if ";" in desc else desc
    spec_txt = spec_txt.replace("(", " ").replace(")", " ")
    spec: dict = {}
    for row in descriptor_lexicon():
        d = row["descriptor"]
        if not d or row["hs4"]:
            continue
        for seg in re.split(r"[,;]", spec_txt):
            for m in re.finditer(rf"(?<![\w-]){re.escape(d)}(?![\w-])", seg):
                before, after = seg[:m.start()], seg[m.end():]
                pol = None if _WHETHER_RE.search(before) else ("-" if _EN_NEG_BEFORE_RE.search(before) else "+")
                # «fresh or dried»: بديلٌ لا شرط — الصفة الموجبة في «X or Y» لا تُعلَن.
                if pol == "+" and (re.search(r"\bor\s+$", before) or re.match(r"\s+or\b", after)):
                    pol = None
                if pol:
                    spec[d] = pol if spec.get(d, pol) == pol else None
            for neg in row["en_neg"]:
                if re.search(rf"(?<![\w-]){re.escape(neg)}(?![\w-])", seg) and not _WHETHER_RE.search(seg):
                    spec[d] = "-" if spec.get(d, "-") == "-" else None
    return {k: v for k, v in spec.items() if v}


def _mentions(text: str, hs4: str) -> list:
    """[(صفة، قطبية، العبارة، الصيغة)] لكل ذكرٍ لصفةٍ في النص؛ النفيُ قبل الصيغة يعكسها،
    والمرادفُ التجاريّ الخاصّ بترويسةٍ لا يُقرأ إلا بجوار اسم المنتج في العبارة نفسها."""
    out = []
    for sent in sentences(text):
        for clause in _CLAUSE_SPLIT.split(sent):
            low = clause.lower()
            for row in descriptor_lexicon():
                if row["hs4"] and row["hs4"] != hs4:
                    continue
                if row["head"] and not any(re.search(_ar_word(h), low, re.I) for h in row["head"]):
                    continue
                for form in sorted(row["forms"], key=len, reverse=True):
                    m = re.search(_ar_word(form), low, re.I)
                    if not m:
                        continue
                    pol = row["polarity"]
                    if _NEG_BEFORE_RE.search(low[max(0, m.start() - 10): m.start()]):
                        pol = "-" if pol == "+" else "+"
                    out.append((row["descriptor"], pol, clause.strip(), form))
                    break
    return out


def check_scope(doc: StudyDoc) -> Finding:
    code = norm_digits(doc.meta.get("hs_code") or "").strip()
    if len(code) != 6:
        return Finding("F6", "فحص النطاق", SKIP, "رمز HS السداسي غير معروف")
    ref = _hs_reference()
    if not ref:
        return Finding("F6", "فحص النطاق", SKIP, "data/hs_reference.csv غير متاح")
    scope = doc.section(10) or ""
    if not scope:
        return Finding("F6", "فحص النطاق", WARN, "لا قسم توصيات (10) في التقرير")
    own = descriptor_spec(code, ref)
    sibs = {c: descriptor_spec(c, ref) for c in ref if len(c) == 6 and c[:4] == code[:4] and c != code}
    items: list = []
    seen: set = set()
    mentions = _mentions(scope, code[:4])
    for d, pol, clause, form in mentions:
        want = own.get(d)
        if not want or want == pol or (d, pol) in seen:
            continue
        seen.add((d, pol))
        # البند الشقيق الأقرب: يوافق صفات العبارة كلها، وما لم تذكره العبارة يوافق بندَنا.
        said = {dd: pp for dd, pp, cl, _f in mentions if cl == clause}
        cands = [c for c, sp in sibs.items() if sp.get(d) == pol]

        match = max(cands, key=lambda c, said=said: (
            sum(sibs[c].get(k) == v for k, v in said.items()),
            sum(sibs[c].get(k) == v for k, v in own.items() if k not in said),
            -int(c))) if cands else None
        items.append({"status": FAIL, "hs_code": match or "—", "term": form, "text": _snip(clause),
                      "why": f"«{form}» في التوصيات يعاكس وصف البند {code} "
                             f"({d}{want}) — منتجٌ من بندٍ آخر{f' ({match})' if match else ''}"})
    for m in _HS6_RE.finditer(norm_digits(scope)):
        other = m.group(1) + m.group(2)
        if other != code and other in ref:
            items.append({"status": FAIL, "hs_code": other, "term": m.group(0),
                          "text": _snip(scope[max(0, m.start() - 60): m.end() + 60]),
                          "why": f"رمز HS آخر ({other}) في التوصيات — خارج نطاق {code}"})
    if items:
        return Finding("F6", "فحص النطاق", FAIL, f"{len(items)} توصية خارج البند {code}", items)
    note = (f"التوصيات داخل البند {code}" if own
            else f"التوصيات بلا رمز آخر؛ وصف البند {code} لا يعلن صفاتٍ يقيسها المعجم")
    return Finding("F6", "فحص النطاق", PASS, note)


# ── F7 الاتساق · one requirement, one classification ────────────────────────

REQUIREMENT_FAMILIES = (
    ("الحلال", re.compile(r"حلال|halal", re.I)),
    ("شهادة المطابقة الخليجية", re.compile(r"شهادة\s+(?:ال)?مطابقة|مطابقة\s+(?:ال)?معيار|GSO\s*\d|conformity", re.I)),
    ("البطاقة الغذائية", re.compile(r"بطاقة\s+(?:غذائية|البيانات|عربية)|labell?ing", re.I)),
    ("الشهادة الصحية", re.compile(r"شهادة\s+صحية|health\s+certificate", re.I)),
    ("شهادة المنشأ", re.compile(r"شهادة\s+(?:ال)?منشأ|certificate\s+of\s+origin", re.I)),
    ("ترخيص المنشأة", re.compile(r"ترخيص\s+(?:ال)?منشأة|establishment\s+licen[cs]e", re.I)),
)
_MANDATORY_RE = re.compile(
    r"إلزامي\w*|الإلزامية|إجباري\w*|لا\s*بدّ?|يُ?شترط|شرط\s+(?:دخول|نظامي|قانوني|إلزامي)|واجب\w*|"
    r"بموجب\s+(?:قرار|قانون|لائحة|مرسوم|نظام)|يشمل\s+المستورد|بدونها\s+لن\s+تعبر|"
    r"mandatory|compulsory|required\s+by\s+law|legally\s+required", re.I)
_OPTIONAL_RE = re.compile(
    r"يطلبها?\s+المشترون|يطلبه\s+المشترون|اختياري\w*|طوعي\w*|ميزة\s+(?:تسويقية|تنافسية)|"
    r"إضافي\w*\s+من\s+المشترين|مفضّ?ل\w*|غير\s+إلزامي\w*|ليست?\s+إلزامي\w*|شرط\s+عملي|"
    r"voluntary|optional|buyer[- ]requested|nice[- ]to[- ]have|commercial\s+preference", re.I)
_OPT_NEGATED_RE = re.compile(r"لا\s+تنظر\s+إل\w*|ليست?\s+(?:مجرد\s+)?ميزة|لا\s+(?:ك)?ميزة|بل\s+(?:ك)?ورقة", re.I)


_NOT_MANDATORY_RE = re.compile(r"(?:غير|ليس|ليست|لا\s+(?:ي|ت)عدّ?)\s+(?:إلزامي\w*|إجباري\w*|شرطاً)"
                               r"|not\s+(?:mandatory|compulsory|required)|non[- ]mandatory", re.I)


def _classify(text: str, subhead: str) -> "str | None":
    sh = subhead or ""
    if _NOT_MANDATORY_RE.search(sh):
        return "optional"
    if re.search(r"الإلزامية|إلزامي|mandatory", sh, re.I):
        return "mandatory"
    if re.search(r"يطلبها\s+المشترون|اختيارية|طوعية|إضافية|buyer|voluntary|optional", sh, re.I):
        return "optional"
    if re.search(r"المتخصصة|niche", sh, re.I):
        return "niche"
    # «غير إلزامي» نفيٌ للإلزام لا إلزام: يُقرأ اختيارياً ويُزال قبل البحث عن الإلزام.
    neg = bool(_NOT_MANDATORY_RE.search(text))
    rest = _NOT_MANDATORY_RE.sub(" ", text)
    man = bool(_MANDATORY_RE.search(rest))
    opt = neg or bool(_OPTIONAL_RE.search(rest))
    if man and opt:
        # «لا تنظر إليها كميزة … بل ورقةٌ لا بدّ منها» ⇒ إلزام؛ غير ذلك ملتبسٌ لا يُصنَّف.
        return "mandatory" if _OPT_NEGATED_RE.search(rest) else None
    if man:
        return "mandatory"
    if opt:
        return "optional"
    return None


def check_consistency(doc: StudyDoc) -> Finding:
    occ: dict = {}
    for num, title, body in doc.sections or [(None, "", doc.report)]:
        subhead = ""
        for p in paragraphs(body):
            first = p.strip().split("\n", 1)[0]
            sm = _SUBHEAD_RE.match(first)
            if sm:
                subhead = sm.group(1)
                continue
            units = [p] if p.lstrip().startswith("|") else sentences(p)
            for u in units:
                for label, rex in REQUIREMENT_FAMILIES:
                    if not rex.search(u):
                        continue
                    cls = _classify(u, subhead if not p.lstrip().startswith("|") or subhead else "")
                    if cls in ("mandatory", "optional"):
                        occ.setdefault(label, {}).setdefault(cls, []).append(
                            {"section": f"{num}. {title}" if num else "—", "subhead": subhead,
                             "text": _snip(u)})
    items: list = []
    for label, by in occ.items():
        if "mandatory" in by and "optional" in by:
            m0, o0 = by["mandatory"][0], by["optional"][0]
            items.append({"status": FAIL, "requirement": label,
                          "mandatory": by["mandatory"][:3], "optional": by["optional"][:3],
                          "text": f"إلزامي في {m0['section']}: {m0['text']} ‖ "
                                  f"اختياري في {o0['section']}: {o0['text']}",
                          "why": f"«{label}» مصنَّف إلزامياً في موضع ويطلبه المشترون/اختياري في آخر"})
    if items:
        return Finding("F7", "فحص الاتساق", FAIL, f"{len(items)} اشتراط بتصنيفين", items)
    return Finding("F7", "فحص الاتساق", PASS, f"{len(occ)} اشتراط مصنَّف بلا تعارض")


# ── G0 القيم المرجعية · owner-verified values ──────────────────────────────

_MUSD_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:مليون|ملايين)\s*(?:دولار|\$|USD)", re.I)
_VAT_RE = re.compile(r"ضريبة(?:\s+القيمة\s+المضافة)?[^.\n]{0,30}?(\d+(?:\.\d+)?)\s*%|VAT[^.\n]{0,20}?(\d+(?:\.\d+)?)\s*%", re.I)
_FX_CTX_RE = re.compile(r"مربوط|ربط|سعر\s+(?:ال)?صرف|مقابل\s+(?:ال)?دولار|للدولار|peg|exchange\s+rate|per\s+(?:US\s*)?dollar", re.I)


def check_reference_values(doc: StudyDoc) -> Finding:
    exp = doc.expected or {}
    if not exp:
        return Finding("G0", "القيم المرجعية", SKIP, "لا قيم مرجعية (expected.json)")
    tol = float(exp.get("tolerance_pct") or 0.5)
    items: list = []
    all_nums = [v for v, *_ in numbers_in(doc.all_text)]
    sents = sentences(doc.all_text)

    def present(v: float) -> bool:
        return any(near(x, v, tol) for x in all_nums)

    direct = {int(y): float(v) for y, v in (exp.get("imports_usd_musd_direct") or {}).items()}
    known = set(direct.values()) | {float(v) for blk in ("imports_musd",)
                                    for v in (exp.get(blk) or {}).values()}
    for y, v in sorted(direct.items()):
        wrong = []
        for s_ in sents:
            # الجملة تُقسَم عبارات؛ عبارةٌ بسنةٍ واحدة تملك مبالغها («ثم 9.17 مليون في 2024»)،
            # وعبارةٌ بسنتين أو بلا سنة لا تُنسَب لسنة (لا تخمين).
            for clause in _CLAUSE_SPLIT.split(s_):
                years = {int(m.group(0)) for m in _YEAR_RE.finditer(clause)}
                if years != {y}:
                    continue
                for mm in _MUSD_RE.finditer(clause):
                    got = float(mm.group(1))
                    if not near(got, v, tol) and not any(near(got, k, tol) for k in known):
                        wrong.append((got, _snip(clause)))
        if wrong:
            items.append({"status": FAIL, "key": f"imports_{y}", "expected": v,
                          "found": wrong[0][0], "text": wrong[0][1],
                          "why": "قيمة سنةٍ مخالفة للمرجع"})
        elif not present(v):
            items.append({"status": WARN, "key": f"imports_{y}", "expected": v, "why": "غير مذكورة"})
        else:
            items.append({"status": PASS, "key": f"imports_{y}", "expected": v})
    for y, v in (exp.get("import_unit_value_usd_kg") or {}).items():
        v = float(v)
        items.append({"status": PASS if present(v) else WARN, "key": f"unit_value_{y}",
                      "expected": v, **({} if present(v) else {"why": "غير مذكورة"})})
    for k, v in (exp.get("saudi_share_pct") or {}).items():
        v = float(v)
        items.append({"status": PASS if present(v) else WARN, "key": f"saudi_share_{k}",
                      "expected": v, **({} if present(v) else {"why": "غير مذكورة"})})
    if exp.get("vat_pct") is not None:
        v = float(exp["vat_pct"])
        found = [float(a or b) for a, b in _VAT_RE.findall(doc.report)]
        if any(not near(f, v, tol) for f in found):
            items.append({"status": FAIL, "key": "vat_pct", "expected": v, "found": found,
                          "why": "ضريبة مخالفة للمرجع"})
        elif found:
            items.append({"status": PASS, "key": "vat_pct", "expected": v})
        else:
            items.append({"status": WARN, "key": "vat_pct", "expected": v, "why": "الضريبة غير مذكورة"})
    if exp.get("fx_local_per_usd") is not None:
        v = float(exp["fx_local_per_usd"])
        found = [x for s_ in sentences(doc.report) if _FX_CTX_RE.search(s_)
                 for x, *_ in numbers_in(s_)
                 if not _YEAR_RE.fullmatch(f"{x:g}") and v / 10 <= x <= v * 10]
        if any(not near(f, v, tol) for f in found):
            items.append({"status": FAIL, "key": "fx_local_per_usd", "expected": v, "found": found,
                          "why": "سعر الربط مخالف للمرجع"})
        elif found:
            items.append({"status": PASS, "key": "fx_local_per_usd", "expected": v})
        else:
            items.append({"status": WARN, "key": "fx_local_per_usd", "expected": v,
                          "why": "سعر الربط غير مذكور رقماً"})
    worst = max((i["status"] for i in items), key=lambda s: _ORDER[s], default=PASS)
    n_fail = sum(1 for i in items if i["status"] == FAIL)
    n_warn = sum(1 for i in items if i["status"] == WARN)
    n_ok = sum(1 for i in items if i["status"] == PASS)
    return Finding("G0", "القيم المرجعية", worst,
                   f"{n_ok} مطابقة، {n_warn} غير مذكورة، {n_fail} مخالفة", items)


# ── التشغيل · run everything ────────────────────────────────────────────────

CHECKS = (
    ("G0", check_reference_values),
    ("F1", check_units),
    ("F2", check_shelf_prices),
    ("F3", check_mirror),
    ("F4", check_tariff_claims),
    ("F5", check_verdict_basis),
    ("F6", check_scope),
    ("F7", check_consistency),
)


def _strip_pattern_tashkeel() -> None:
    """الأنماط تُطبَّع مثل النصّ: حركةٌ إلزامية في نمطٍ («حدّ معلن»، «مصرَّحة») لا تطابق نصاً
    حُذفت حركاته. «X?» حيث X حركةٌ تُحذف معها علامة الاختيار."""
    strip = re.compile("[\u064B-\u0652\u0670\u0640]\\??")
    g = globals()
    for name, val in list(g.items()):
        if name == "_TASHKEEL_RE":
            continue  # فئةُ الحركات نفسُها — تُترك كما هي
        if isinstance(val, re.Pattern) and isinstance(val.pattern, str) \
                and _TASHKEEL_RE.search(val.pattern):
            g[name] = re.compile(strip.sub("", val.pattern), val.flags)


_strip_pattern_tashkeel()


def run_all(doc: StudyDoc) -> list:
    out = []
    for key, fn in CHECKS:
        try:
            out.append(fn(doc))
        except Exception as e:  # noqa: BLE001 — فحصٌ يتعطّل يُعلَن لا يُخفى
            out.append(Finding(key, fn.__doc__ or key, FAIL, f"تعطّل الفحص: {type(e).__name__}: {e}"))
    return out


def overall(findings: list) -> str:
    return max((f.status for f in findings), key=lambda s: _ORDER[s], default=PASS)


def summarize(findings: list) -> dict:
    return {"overall": overall(findings),
            "checks": {f.check: f.status for f in findings},
            "findings": [f.to_dict() for f in findings]}
