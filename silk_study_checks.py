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
_CLAUSE_SPLIT = re.compile(r"[،,؛;]|\s(?:ثم|بينما|مقابل|versus|vs\.?|while)\s")
_SENT_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n")
_MAG = {"مليون": 1e6, "ملايين": 1e6, "مليار": 1e9, "مليارات": 1e9,
        "ألف": 1e3, "آلاف": 1e3, "الف": 1e3, "million": 1e6, "billion": 1e9,
        "thousand": 1e3, "m": 1e6, "bn": 1e9, "k": 1e3}

# ── المرافق العامة · shared helpers ──────────────────────────────────────────


def norm_digits(s: object) -> str:
    """الأرقام الهندية/الفارسية → ASCII، والفاصلة العشرية العربية → نقطة."""
    return str(s or "").translate(_DIGITS).replace("٫", ".").replace("٬", ",")


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
        report, evidence = raw, ""
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
        mk = (found or {}).get("market") or {}
        m = {"hs_code": str((found or {}).get("hs_code") or ""),
             "market_iso3": mk.get("iso3") or "", "market_ar": mk.get("name_ar") or "",
             "lang": (found or {}).get("lang") or "ar",
             "production_cost_per_unit": ((found or {}).get("request") or {})
             .get("production_cost_per_unit")}
        m.update(meta or {})
        return cls(report=report, evidence=evidence, meta=m, expected=expected or {},
                   view=(found or {}).get("view"))


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
    ev = evidence or ""
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
    for where, text in (("التقرير", doc.report), ("الأدلة", doc.evidence)):
        for s in sentences(text):
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
    if not tables:
        return Finding("F2", "فحص أسعار الرفوف", WARN,
                       "لا جدول أسعار رفوف في التقرير — لا سعر منافس موثق")
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
            link = bool(_URL_RE.search(joined)) or (
                i_link is not None and _cell(row, i_link) and not _NA_RE.search(_cell(row, i_link)))
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
    for s_ in sentences(scan):
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
    refs = doc.expected.get("reference_shelf_prices") or []
    missing_refs = [r for r in refs if not any(
        near(v, float(r.get("price") or 0), 0.5) for v, *_ in numbers_in(doc.report))]
    if missing_refs:
        items.append({"status": WARN, "why": "أسعار موثقة معروفة غائبة عن الدراسة: "
                      + "؛ ".join(f"{r.get('store')} {r.get('product')} {r.get('price')} {r.get('currency')}"
                                  for r in missing_refs)})
    fails = [i for i in items if i["status"] == FAIL]
    n_rows = sum(1 for i in items if "pack_kg" in i)
    note = (f"{documented} سعر موثق من {n_rows} صف"
            + (f"؛ الحد الأدنى {floor} {doc.meta.get('currency') or ''}/كغ" if floor is not None
               else "؛ لا حدّ أدنى (سعر الصرف أو متوسط الاستيراد غائب)"))
    if fails:
        return Finding("F2", "فحص أسعار الرفوف", FAIL, note + f"؛ {len(fails)} مخالفة", items)
    if documented < 5:
        return Finding("F2", "فحص أسعار الرفوف", WARN, note + "؛ أقل من 5 أسعار موثقة", items)
    return Finding("F2", "فحص أسعار الرفوف", PASS, note, items)


# ── F3 المرآة · mirror vs direct ───────────────────────────────────────────

_MIRROR_RE = re.compile(r"مرآة|مرآتية|مرايا|\bmirror(?:ed)?\b|بيانات\s+الدول\s+الشريكة|"
                        r"تصريحات\s+الدول\s+التي\s+تصدّ?ر|partner[- ]reported", re.I)
_DIRECT_RE = re.compile(r"مباشر|direct|صرّ?حت\s+بها|reported\s+by\s+the\s+market", re.I)
_DIVERGENCE_RE = re.compile(r"تباين|divergence")
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_LEDGER_HEAD_RE = re.compile(r"^سجلّ?\s+الحقائق\s*[—-]\s*(.+?):")
_SECTION_NUM_SKIP = re.compile(r"^\s*\d+\.\s")


def _fig_tokens(text: str) -> list:
    """[(القيمة، اللاحقة)] — اللاحقة: % أو مليون/مليار/نقطة أو ''؛ السنوات تُستبعد."""
    out = []
    t = norm_digits(text)
    for v, _s, e, raw in numbers_in(t):
        if _YEAR_RE.fullmatch(raw) or re.fullmatch(r"\d{6}", raw):
            continue
        tail = t[e:e + 12]
        suf = ""
        if re.match(r"\s*%", tail):
            suf = "%"
        elif re.match(r"\s*(?:مليون|ملايين|مليار|million|billion)", tail):
            suf = "مليون"
        elif re.match(r"\s*نقطة", tail):
            suf = "نقطة"
        out.append((v, suf))
    return out


def _direct_mirror_pairs(expected: dict) -> list:
    """أزواج (المؤشر، المباشر، مفتاحه، المرآة، مفتاحها، اللاحقة) من `expected`:
    كل قاموس مؤشر يحمل مفاتيح `direct_*` و`mirror_*` — صريحٌ لا استدلال."""
    out = []
    for key, suf in (("saudi_share_pct", "%"), ("imports_musd", "مليون"),
                     ("hhi", "نقطة"), ("supplier_count", "")):
        block = expected.get(key) or {}
        d = [(k, v) for k, v in block.items() if str(k).startswith("direct")]
        m = [(k, v) for k, v in block.items() if str(k).startswith("mirror")]
        for dk, dv in d:
            for mk, mv in m:
                try:
                    out.append((key, float(dv), str(dk), float(mv), str(mk), suf))
                except (TypeError, ValueError):
                    continue
    return out


def mirror_figures(doc: StudyDoc) -> list:
    """الأرقام الموسومة مرآةً: [(القيمة، اللاحقة أو None)].

    من جملٍ تحمل علامة المرآة — وإن حملت الجملةُ علامةَ «مباشر» أيضاً فالأرقام
    **بعد** علامة المرآة وحدها (جملةُ مقارنةٍ تذكر الرقمين معاً) — ومن قيم `mirror_*`
    و`mirror_values` في `expected`."""
    figs: list = []
    for s in sentences(doc.all_text):
        mm = _MIRROR_RE.search(s)
        if not mm:
            continue
        dm = _DIRECT_RE.search(s)
        if dm and dm.start() < mm.start():
            figs.extend(_fig_tokens(s[mm.start():]))
        else:
            figs.extend(_fig_tokens(s))
    for _k, _dv, _dk, mv, _mk, suf in _direct_mirror_pairs(doc.expected):
        figs.append((mv, suf))
    for v in doc.expected.get("mirror_values") or []:
        try:
            figs.append((float(v), None))
        except (TypeError, ValueError):
            continue
    return figs


def _is_mirror(v: float, suf: str, figs: list) -> bool:
    for mv, msuf in figs:
        if not near(v, mv, 0.5):
            continue
        if msuf is None:
            # قيمة مرجعية بلا لاحقة: عددٌ صحيح صغير يحتاج لاحقةً كي لا يلتبس بعدّاد
            if mv < 100 and float(mv).is_integer() and suf == "":
                continue
            return True
        if _suffix_ok(suf, msuf):
            return True
    return False


def _suffix_ok(found: str, wanted: str) -> bool:
    """رقمٌ بلاحقةٍ معلنة («مليون»، «%»، «نقطة») يطابق اللاحقة نفسها فقط — «15.15 دولار/كغ»
    ليس «15.12 مليون دولار». المرجع بلا لاحقة يطابق أيّ لاحقة."""
    return wanted == "" or found == wanted


_IMPORT_LEDGER_KEY_RE = re.compile(r"واردات|الواردات|النمو|نمو|المركّب|المركب|imports|growth|CAGR", re.I)
_IMPORT_SENT_RE = re.compile(r"(?:استيراد|واردات|imports?)[^.\n]{0,120}?(\d+(?:\.\d+)?)\s*(?:مليون|million)", re.I)


def _mirror_only_years(doc: StudyDoc) -> set:
    """سنواتٌ رقمُ وارداتها مرآةٌ فقط: من مفاتيح `mirror_*` في المرجع ومن سطور السجلّ
    الموسومة مرآة، ناقصاً السنوات ذات تصريحٍ مباشر (المرجع + جمل الواردات غير الموسومة)."""
    mirror: set = set()
    for blk in ("imports_musd", "saudi_share_pct", "hhi", "supplier_count"):
        for k in (doc.expected.get(blk) or {}):
            m = re.search(r"mirror_(\d{4})", str(k))
            if m:
                mirror.add(int(m.group(1)))
    for line in doc.evidence_lines:
        if _LEDGER_HEAD_RE.match(line) and _MIRROR_RE.search(line):
            mirror |= {int(y) for y in _YEAR_RE.findall(line)}
    direct = {int(y) for y in (doc.expected.get("imports_usd_musd_direct") or {})}
    for s_ in sentences(doc.evidence):
        if _MIRROR_RE.search(s_) or _LEDGER_HEAD_RE.match(s_):
            continue
        if _IMPORT_SENT_RE.search(s_):
            direct |= {int(y) for y in _YEAR_RE.findall(s_)}
    return mirror - direct


_INDICATOR_AR = {"saudi_share_pct": "الحصة السعودية", "imports_musd": "واردات السوق",
                 "hhi": "مؤشر التركّز", "supplier_count": "عدد الدول المورّدة"}


def check_mirror(doc: StudyDoc) -> Finding:
    items: list = []
    figs = mirror_figures(doc)
    # ١) أزواج مباشر/مرآة صريحة من القيم المرجعية
    pairs: list = list(_direct_mirror_pairs(doc.expected))
    # ٢) أزواج من جملة واحدة تحمل العلامتين ونسبتين (دراسة بلا قيم مرجعية)
    for s in sentences(doc.all_text):
        if not (_MIRROR_RE.search(s) and _DIRECT_RE.search(s)):
            continue
        # كل عبارةٍ تأخذ علامتها (الأولى فيها إن حملت العلامتين)، والعبارةُ بلا علامة
        # ترث علامة ما قبلها: «حصة المرآة 12.02% مقابل 1.43% في البيانات المباشرة».
        groups: dict = {"mirror": [], "direct": []}
        kind = None
        for clause in _CLAUSE_SPLIT.split(s):
            marks = sorted([(m.start(), "mirror") for m in _MIRROR_RE.finditer(clause)]
                           + [(m.start(), "direct") for m in _DIRECT_RE.finditer(clause)])
            if marks:
                kind = marks[0][1]
            if kind:
                groups[kind] += [float(x) for x in _PCT_RE.findall(clause)]
        if groups["direct"] and groups["mirror"]:
            dv, mv = groups["direct"][0], groups["mirror"][0]
            if not any(near(dv, p[1], 0.5) and near(mv, p[3], 0.5) for p in pairs):
                pairs.append(("جملة مقارنة", dv, "direct", mv, "mirror", "%"))
    for label, dv, dk, mv, mk, suf in pairs:
        if dv == 0:
            continue
        gap = abs(mv - dv) / abs(dv) * 100.0
        if gap <= 25.0:
            continue
        holders = [p for p in paragraphs(doc.report)
                   if any(near(v, mv, 0.5) and _suffix_ok(sf, suf) for v, sf in _fig_tokens(p))]
        if holders and all(_DIVERGENCE_RE.search(p) for p in holders):
            continue
        ctx = next((p for p in holders if not _DIVERGENCE_RE.search(p)), "")
        where = "الأدلة فقط" if not holders else "التقرير"
        items.append({"status": FAIL, "indicator": _INDICATOR_AR.get(label, label),
                      "direct": dv, "direct_key": dk, "mirror": mv, "mirror_key": mk,
                      "gap_pct": round(gap, 1), "where": where, "text": _snip(ctx),
                      "why": f"فرق {gap:.0f}% بين المباشر {dv:g} والمرآة {mv:g} بلا وسم «تباين»"
                             + (" في فقرة الرقم" if holders else " — والتقرير لا يعرض التباين")})
    # ٣) رقم مرآة في الخلاصة التنفيذية
    exec_text = doc.section(1)
    for v, suf in _fig_tokens(exec_text):
        if _is_mirror(v, suf, figs):
            items.append({"status": FAIL, "where": "القسم 1", "figure": v,
                          "why": "رقم مرآة في الخلاصة التنفيذية"})
            break
    # ٤) أول رقم في كل قسم
    for num, title, body in doc.sections:
        if num == 1:
            continue
        toks = _fig_tokens(body)
        if toks and _is_mirror(toks[0][0], toks[0][1], figs):
            items.append({"status": FAIL, "where": f"القسم {num} ({title})", "figure": toks[0][0],
                          "why": "أول رقم في القسم رقم مرآة"})
    # ٥) رأس سجلّ الحقائق: رقم مرآة صريح، أو مؤشرُ وارداتٍ سنتُه سنةُ مرآةٍ فقط
    #    (أحدث سنة/نمو/مركّب محسوبة من سنةٍ لا تصريح مباشر لها).
    mirror_years = _mirror_only_years(doc)
    for line in doc.evidence_lines:
        m = _LEDGER_HEAD_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip()
        if _MIRROR_RE.search(line):
            items.append({"status": FAIL, "where": "سجلّ الحقائق", "key": key, "text": _snip(line),
                          "why": "رأس السجلّ لهذا المؤشر رقم مرآة لا تصريح مباشر"})
            continue
        if _IMPORT_LEDGER_KEY_RE.search(key):
            yrs = {int(y) for y in _YEAR_RE.findall(line[m.end():])}
            bad = sorted(yrs & mirror_years)
            if bad:
                items.append({"status": FAIL, "where": "سجلّ الحقائق", "key": key, "text": _snip(line),
                              "why": f"مؤشر واردات مبنيّ على سنة {bad[-1]} ولا تصريح مباشر لها "
                                     "(سنة مرآة فقط) — رأس السلسلة يجب أن يكون آخر سنة مباشرة"})
    if items:
        return Finding("F3", "فحص المرآة", FAIL, f"{len(items)} مخالفة مرآة/تباين", items)
    if not figs:
        return Finding("F3", "فحص المرآة", PASS, "لا أرقام مرآة في الدراسة")
    return Finding("F3", "فحص المرآة", PASS, "أرقام المرآة موسومة ولا تتصدر قسماً")


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
                   "أجّل الدخول", "أجل الدخول", "لا ننصح بالدخول", "فرز سوق أولي",
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
    vline = _VERDICT_LINE_RE.search(doc.section(1) or doc.report[:1500])
    basis.update({"status": FAIL, "required_label": SCREENING_LABEL, "where": "الخلاصة التنفيذية",
                  "text": vline.group(0) if vline else verdict,
                  "why": f"حكم استثماري «{verdict}» بلا سعر مصنع ولا سقف سعر محسوب — "
                         f"يُكتب «{SCREENING_LABEL}»"})
    return Finding("F5", "فحص الحكم", FAIL, basis["why"], [basis])


# ── F6 النطاق · recommendations stay inside the HS line ─────────────────────

_NEG_BEFORE_RE = re.compile(rf"(?:غير|ليس|ليست|لا|بدون|بلا|not|non|un)\s*-?\s*$", re.I)
_HS6_RE = re.compile(r"(?<![\d.])(\d{4})\.?(\d{2})(?!\d)(?!\.\d)")


def _hs_rows() -> list:
    path = os.path.join(_ROOT, "data", "hs_codes.csv")
    try:
        with open(path, encoding="utf-8") as fh:
            return [r for r in csv.DictReader(fh) if (r.get("hs_code") or "").strip()]
    except OSError:
        return []


def _curated_scope_terms() -> dict:
    """{hs6: {مصطلح}} من `data/hs_scope_terms_l1.csv`."""
    path = os.path.join(_ROOT, "data", "hs_scope_terms_l1.csv")
    out: dict = {}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = csv.DictReader(l for l in fh if not l.startswith("#"))
            for r in rows:
                c, t = (r.get("hs6") or "").strip(), (r.get("term") or "").strip().lower()
                if len(c) == 6 and t:
                    out.setdefault(c, set()).add(t)
    except OSError:
        return {}
    return out


def scope_terms(hs_code: str) -> "tuple[set, dict]":
    """(مصطلحات بند الدراسة، {بند شقيق: مصطلحاته المميِّزة}) تحت البند الرباعي نفسه.

    المصدر الأول الجدول المنسّق؛ والبند الغائب عنه يُمثَّل باسمه العربي الكامل من
    `hs_codes.csv` (عبارة لا كلمات مفتاحية — «coffee beans» تصف المحمّص أيضاً)."""
    code = norm_digits(hs_code).strip()
    curated = _curated_scope_terms()
    names = {r["hs_code"].strip(): (r.get("name_ar") or "").strip().lower()
             for r in _hs_rows()}
    codes = {c for c in set(curated) | set(names) if len(c) == 6 and c[:4] == code[:4]}

    def terms_of(c: str) -> set:
        if c in curated:
            return set(curated[c])
        n = names.get(c) or ""
        return {n} if len(n) >= 5 else set()

    mine = terms_of(code)
    sibs = {c: {t for t in terms_of(c) if t not in mine}
            for c in codes if c != code}
    return mine, {c: ts for c, ts in sibs.items() if ts}


def check_scope(doc: StudyDoc) -> Finding:
    code = norm_digits(doc.meta.get("hs_code") or "").strip()
    if len(code) != 6:
        return Finding("F6", "فحص النطاق", SKIP, "رمز HS السداسي غير معروف")
    mine, sibs = scope_terms(code)
    if not sibs and not _hs_rows():
        return Finding("F6", "فحص النطاق", SKIP, "data/hs_codes.csv غير متاح")
    scope = doc.section(10) or ""
    if not scope:
        return Finding("F6", "فحص النطاق", WARN, "لا قسم توصيات (10) في التقرير")
    items: list = []
    low = scope.lower()
    # مواضعُ مصطلحات بند الدراسة نفسه: مطابقةُ شقيقٍ داخلها جزءٌ من اسم منتجنا
    # («قهوة محمصة» داخل «قهوة محمصة منزوعة الكافيين» في دراسة 090122).
    own_spans = [(m.start(), m.end()) for t in mine
                 for m in re.finditer(_ar_word(t), low, re.I)]
    for c, terms in sorted(sibs.items()):
        hit = None
        for t in sorted(terms, key=len, reverse=True):
            for m in re.finditer(_ar_word(t), low, re.I):
                # داخل عبارةٍ من بندنا فهو جزءٌ من اسم منتجنا («قهوة محمصة» داخل
                # «قهوة محمصة منزوعة الكافيين» في دراسة 090122). الملاصقةُ وحدها لا
                # تكفي: «قهوة محمصة منزوعة الكافيين» في دراسة 090121 خارج النطاق.
                if any(a <= m.start() and m.end() <= b for a, b in own_spans):
                    continue
                if _NEG_BEFORE_RE.search(low[max(0, m.start() - 10): m.start()]):
                    continue
                hit = (t, m)
                break
            if hit:
                break
        if hit:
            t, m = hit
            sent = next((x for x in sentences(scope) if t in x.lower()), scope[m.start(): m.end() + 80])
            items.append({"status": FAIL, "hs_code": c, "term": t, "text": _snip(sent),
                          "why": f"منتج من بند شقيق ({c}) في التوصيات — خارج نطاق {code}"})
    valid = {r["hs_code"].strip() for r in _hs_rows()}
    for m in _HS6_RE.finditer(norm_digits(scope)):
        other = m.group(1) + m.group(2)
        if other != code and other in valid:
            items.append({"status": FAIL, "hs_code": other, "term": m.group(0),
                          "text": _snip(scope[max(0, m.start() - 60): m.end() + 60]),
                          "why": f"رمز HS آخر ({other}) في التوصيات — خارج نطاق {code}"})
    if items:
        return Finding("F6", "فحص النطاق", FAIL, f"{len(items)} توصية خارج البند {code}", items)
    return Finding("F6", "فحص النطاق", PASS, f"التوصيات داخل البند {code}")


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
