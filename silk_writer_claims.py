"""ادعاءاتُ الكاتب الرقمية المنظّمة — PR-B البند (د)، الدرس ٣٠٣.

قرار المالك: «الكاتب يُخرج ادعاءاته الرقمية بصيغة منظمة (القيمة، الوحدة، السنة، المصدر، مباشر أو مرآة)،
حتى تُفحص البيانات المنظمة بدل تحليل النثر العربي».

* الكاتب يُلحق في آخر مخرَجه سياجاً ```claims {"claims": [...]}```؛ `strip` ينزعه **فور وصول النصّ**
  (قبل الاكتمال والإكمال وقبل أن يصل أيَّ سطح) ويعيد الادعاءات وحالتها: ok | missing | invalid | truncated.
* `check(found)` — الفحص C1 الحتميّ على عقدة التقرير: كلُّ ادعاء واردات يطابق نقطةَ سنته في
  `import_series` بنوعها (مرآةٌ مُعلَنةٌ مباشراً = FAIL)، والنموُّ والمركّب يطابقان المحسوبَ من السنوات
  المصرّحة (`growth_pct`/`cagr_pct`)، ونموٌّ مرفوضٌ لأنه مرآة لا يُدّعى. أرقامُ النثر التي لا يغطّيها ادعاءٌ
  ولا رمزُ سجلّ تُعَدّ (WARN). يعمل في وضع الظلّ (`silk_study_checks_shadow`) — لا يحجب.

Structured numeric claims from the writer and their deterministic check (shadow mode).
"""
from __future__ import annotations

import contextvars
import re

# مراجعة §58: حسّاسٌ لا لحالة الحروف، والكائنُ قد يبدأ على سطر الفاتح نفسِه.
_FENCE_RE = re.compile(r"\n?```[ \t]*claims\b[ \t]*\n?(.*?)(\n?```[ \t]*\n?|\Z)", re.S | re.I)
#: كلُّ مخرَجٍ نُزع سياجُه في هذا النداء: [(النصّ النظيف، الادعاءات/الحالة)] — المسلَّمُ يُطابَق بنصّه.
_LAST: contextvars.ContextVar = contextvars.ContextVar("silk_writer_claims_last", default=None)

INDICATORS = ("imports", "imports_growth", "imports_cagr", "saudi_share", "price", "tariff",
              "other")
BASES = ("direct", "mirror", "estimate", "other")


def strip(text: "str | None") -> tuple:
    """(النصّ بلا السياج، الادعاءات أو None، الحالة). السياجُ الأخير وحده؛ المبتورُ يُنزع إلى آخر النصّ."""
    if not text:
        return text, None, "missing"
    matches = list(_FENCE_RE.finditer(text))
    if not matches:
        return text, None, "missing"
    m = matches[-1]
    body = m.group(1)
    closed = m.group(2).strip().startswith("```")
    clean = (text[:m.start()] + text[m.end():]).rstrip() + "\n"
    if not closed:
        return clean, None, "truncated"
    import silk_json
    obj = silk_json.extract(body, dict_only=True) if body else None
    claims = obj.get("claims") if isinstance(obj, dict) else None
    if not isinstance(claims, list):
        return clean, None, "invalid"
    good = [dict(c, v=_num(c.get("v"))) for c in claims
            if isinstance(c, dict) and _num(c.get("v")) is not None]
    dropped = len(claims) - len(good)
    # مراجعة §58: ادعاءٌ لا تُقرأ قيمتُه فجوةٌ معلنة لا سقوطٌ صامت (قاعدة المستخلِص المتين).
    return clean, good, ("ok" if not dropped else f"ok_dropped:{dropped}")


def take(text: "str | None") -> "str | None":
    """للكاتب: انزع السياج واحفظ ادعاءاته في سياق النداء **مقرونةً بنصّها** — المسلَّمُ يُطابَق
    لاحقاً بنصّه (مراجعة §58: لا «آخرُ نداءٍ يفوز» فتُلحق ادعاءاتُ مراجعةٍ مرفوضة)."""
    clean, claims, status = strip(text)
    if text:
        box = _LAST.get()
        if box is None:
            box = []
            _LAST.set(box)
        dropped = int(status.split(":")[1]) if status.startswith("ok_dropped:") else 0
        box.append((clean, {"claims": claims, "status": "ok" if dropped else status,
                            "dropped": dropped}))
    return clean


def reset() -> None:
    _LAST.set(None)


def for_text(final: str) -> "dict | None":
    """ادعاءاتُ المخرَج الأقرب نصّاً إلى النصّ المسلَّم — وإلا `unmatched` بلا ادعاءات."""
    box = _LAST.get() or []
    if not box or not final:
        return None
    for clean, rec in reversed(box):
        if clean.strip() == final.strip():
            return rec
    import difflib
    best, ratio = None, 0.0
    for clean, rec in box:
        r = difflib.SequenceMatcher(None, clean[:6000], final[:6000]).quick_ratio()
        if r > ratio:
            best, ratio = rec, r
    return best if ratio >= 0.85 else {"claims": None, "status": "unmatched", "dropped": 0}


def _num(v) -> "float | None":
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:      # «٩٫١٧» و«1,234» — تطبيعُ الأرقام كما تفعل الفحوص
        from silk_study_checks import norm_digits
        return float(norm_digits(str(v)).replace(",", "").replace("٬", "").strip())
    except (TypeError, ValueError):
        return None


def scaled(claim: dict) -> "float | None":
    v = _num(claim.get("v"))
    if v is None:
        return None
    from silk_study_checks import _MAG
    unit = str(claim.get("unit") or "").lower()
    for word in sorted(_MAG, key=len, reverse=True):
        if len(word) > 2 and word in unit:
            return v * _MAG[word]
    return v


_IND_CTX_RE = re.compile(r"واردات|الواردات|استيراد|نمو|نمت|نما|مركّ?ب|حصة|نصيب|imports|growth|CAGR|share",
                         re.I)


def _window_ref(s: dict, by_year: dict, ind: str, c: dict, year) -> tuple:
    """(المرجع المحسوب، سبب) لادعاء نموٍّ/مركّب. السببُ «!…» = FAIL، و«…» = WARN، والفارغ = قارن.
    النافذةُ من `from_year`→`year`: نافذةُ السلسلة نفسُها تُقارَن بـ`growth_pct`/`cagr_pct`،
    وغيرُها تُحسب من نقطتَي المباشر؛ طرفٌ مرآةٌ = نموٌّ من المرآة (مراجعة §58)."""
    if s.get("growth_refused") == "mirror_only":
        return None, "!{L} لا يُحسب من بيانات المرآة (السوق لم تصرّح بسنتين)"
    try:
        y0 = int(c.get("from_year")) if c.get("from_year") is not None else None
    except (TypeError, ValueError):
        y0 = None
    by = s.get("basis_years") or []
    key = "growth_pct" if ind == "imports_growth" else "cagr_pct"
    if y0 is None:
        if by and year == by[-1] and s.get(key) is not None:
            return s[key], ""        # بلا بداية: يُفترض أنه نموُّ نافذة السلسلة المعلنة
        return None, "{L} بلا سنة بداية — لا يُتحقق منه"
    if by and [y0, year] == by:
        return s.get(key), ""
    a, b = by_year.get(y0), by_year.get(year)
    if not (a and b):
        return None, f"{{L}} {y0}–{year}: سنةٌ بلا رقم في السلسلة — لا يُتحقق منه"
    if a.get("mirrored") or b.get("mirrored"):
        return None, f"!{{L}} {y0}–{year} محسوبٌ على سنة مرآة — لا نموَّ من بيانات الشركاء"
    v0, v1 = float(a["value"]), float(b["value"])
    if v0 <= 0 or year <= y0:
        return None, "{L}: نافذةٌ غير صالحة"
    if ind == "imports_growth":
        return round((v1 / v0 - 1) * 100, 1), ""
    return round(((v1 / v0) ** (1 / (year - y0)) - 1) * 100, 1), ""


def _finding(status: str, note: str, items: list):
    from silk_study_checks import Finding
    return Finding("C1", "فحص الادعاءات المنظّمة", status, note, items)


def check(found: dict):
    """C1 — ادعاءاتُ الكاتب المنظّمة مقابل السلسلة والسجلّ."""
    from silk_study_checks import FAIL, PASS, SKIP, WARN, _report_figures
    dr = (found or {}).get("deep_research") or {}
    node = dr.get("report") if isinstance(dr.get("report"), dict) else {}
    text = node.get("report") or node.get("text") or ""
    if not text:
        return _finding(SKIP, "لا تقرير كاتب", [])
    if node.get("refined_at"):
        return _finding(SKIP, "نصٌّ مُنقَّح — ادعاءاتُ الكاتب تصف مسوّدته لا النصَّ المسلَّم", [])
    status = node.get("claims_status")
    claims = node.get("claims")
    if status is None:
        # مراجعة §58: دراسةٌ سبقت الدرس ٣٠٣ لم يُطلب من كاتبها سياج — لا إنذارَ كاذب.
        return _finding(SKIP, "دراسةٌ قبل الادعاءات المنظّمة", [])
    if not isinstance(claims, list):
        why = {"invalid": "سياج الادعاءات غير صالح", "truncated": "سياج الادعاءات مبتور",
               "unmatched": "ادعاءاتُ الكاتب لا تطابق النصَّ المسلَّم"}.get(
            status, "الكاتب لم يُخرج ادعاءاته المنظّمة")
        return _finding(WARN, why, [{"status": WARN, "why": why}])
    import silk_deep_pillars as P
    s = P.import_series(dr.get("missions") or {})
    by_year = {int(p["year"]): p for p in (s.get("series") or [])}
    items: list = []
    if node.get("claims_dropped"):
        items.append({"status": WARN, "why": f"{node['claims_dropped']} ادعاءً بقيمةٍ لا تُقرأ"})

    def bad(c, why):
        items.append({"status": FAIL, "claim": c, "why": why})

    def warn(c, why):
        items.append({"status": WARN, "claim": c, "why": why})

    for c in claims:
        ind = str(c.get("indicator") or "other")
        basis = str(c.get("basis") or "other")
        try:
            year = int(c.get("year")) if c.get("year") is not None else None
        except (TypeError, ValueError):
            year = None
        val = scaled(c)
        if ind == "imports" and year is not None and year not in by_year:
            warn(c, f"لا رقم لسنة {year} في سلسلة الواردات — الادعاء غير قابل للتحقق")
        elif ind == "imports" and year in by_year:
            p = by_year[year]
            if p.get("mirrored") and basis == "direct":
                bad(c, f"رقم {year} من بيانات الشركاء (مرآة) أُعلِن تصريحاً مباشراً")
            elif not p.get("mirrored") and basis == "mirror":
                bad(c, f"رقم {year} تصريحٌ مباشر من السوق ووُسم مرآة")
            if val is not None and abs(val - float(p["value"])) > 0.02 * float(p["value"]):
                bad(c, f"قيمة {year} في الادعاء {val:,.0f} وفي السلسلة {float(p['value']):,.0f}")
        elif ind in ("imports_growth", "imports_cagr"):
            label = "النمو" if ind == "imports_growth" else "المعدل المركّب"
            ref, why = _window_ref(s, by_year, ind, c, year)
            if why:
                (bad if why.startswith("!") else warn)(c, why.lstrip("!").replace("{L}", label))
            elif ref is not None and val is not None and abs(val - float(ref)) > 0.6:
                bad(c, f"{label} في الادعاء {val:g}% والمحسوب من السنوات المصرّحة {float(ref):g}%")
    # التغطية: أرقامُ النثر (عدا السنوات ورموز السجلّ) التي لا يطابقها ادعاء.
    vals = [v for v in (scaled(c) for c in claims) if v is not None]
    plain = re.sub(r"\{\{[^}]*\}\}", " ", text)
    uncovered = []
    for v, unit, pos in _report_figures(plain):
        if unit not in ("money", "pct") or v == 0:
            continue
        # مراجعة §58: التغطيةُ لمؤشرات السياج وحدها (لا كلِّ رقمٍ في الدراسة).
        if not _IND_CTX_RE.search(plain[max(0, pos - 80):pos]):
            continue
        if not any(abs(v - x) <= 0.01 * max(abs(x), 1e-9) for x in vals):
            uncovered.append(round(v, 4))
    if uncovered:
        items.append({"status": WARN, "why": f"{len(uncovered)} رقماً في النصّ بلا ادعاء منظّم",
                      "values": uncovered[:10]})
    if any(i["status"] == FAIL for i in items):
        return _finding(FAIL, f"{sum(i['status'] == FAIL for i in items)} ادعاءً يخالف السلسلة/السجلّ",
                        items)
    if items:
        return _finding(WARN, items[-1]["why"], items)
    return _finding(PASS, f"{len(claims)} ادعاءً منظّماً يطابق السلسلة والسجلّ", [])
