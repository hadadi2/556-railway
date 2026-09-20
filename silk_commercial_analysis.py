"""طبقةُ التحليل التجاري — commercial analysis layer (الموجة د-٢).

أسئلةُ المصدّر الحقيقية لا وصفُ السوق: هل لي ميزةُ تكلفة؟ مَن منافسي الفعلي
(منتجٌ أم معيدُ تصدير)؟ بمَ أتمايز؟ أأسعارُ المنافسين موثّقةٌ بما يكفي؟ وأيُّ
شهادةٍ إلزاميةٌ بمصدرٍ رسمي؟ — كلُّها قواعدُ **عامّةٌ مدفوعةٌ بالبيانات وفئةِ
المنتج من فصل HS**، بلا أيّ منطقٍ خاصٍّ بمنتجٍ أو سوقٍ بعينه (قيدُ المالك).

بنيتان منفصلتان عمداً:
- **إشارات** (`augment_*`): شبكةٌ — تُشغَّل في خطوة augment بعد البعثات
  (`silk_missions`، مهلةٌ ٣٠ ث) وتُخزَّن **اكتشافاتِ بعثةٍ** بشكلٍ مُهيكَل
  (قيمةٌ dict + إبرةُ `[commercial]`) فيقرؤها السجلُّ لاحقاً بلا شبكة.
- **استنتاجات** (`fill_insights`): نقيّةٌ — تُحسَب في `build_ledger` من
  الاكتشافات المخزَّنة وتدخل السجلَّ بدرجتها (`ESTIMATE`/`INFERENCE`/فجوةٍ
  معلنة). لا تدخل `build_pillar_inputs` فلا تحرّك حكماً.

الميزانية: كومتريد بلا مفتاح ٤ نداءاتٍ يومياً فقط (`silk_collectors`)، فالطبقةُ
تستشير المتبقّي قبل كلّ نداء، وتُعلِن فجوةً بلا نداءٍ حين ينفد؛ المخزنُ
(`silk_store.trade_flows`) يخدم ما بعد أوّل تشغيل. لا اختلاق: تعذُّرُ الجلب
`None` ≠ سجلٌّ فارغٌ `[]`، وكلاهما يُقال باسمه.
"""
from __future__ import annotations

import csv
import functools
import logging
import os
import re

log = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
RAW_INPUTS_PATH = os.path.join(_HERE, "data", "raw_inputs_l1.csv")
CERTS_PATH = os.path.join(_HERE, "data", "certifications_l1.csv")
#: إبرةُ الملاحظة التي تُميّز اكتشافاتِ هذه الطبقة في نتائج البعثات.
MARK = "[commercial]"
MAX_CALLS_ENV = "SILK_COMMERCIAL_MAX_CALLS"
TOP_SUPPLIERS = 3
_SAU = ("SAU", "682")


def max_calls() -> int:
    """سقفُ نداءات كومتريد لهذه الطبقة في التشغيلة — افتراضه ١٢ (≤ ١٥ بقرار
    المالك)، ولا يتجاوز الميزانيةَ اليومية المتبقّية."""
    try:
        n = int(os.environ.get(MAX_CALLS_ENV, "12"))
    except ValueError:
        n = 12
    return max(0, min(n, 15))


# ── ملفاتُ البيانات · reference files ───────────────────────────────────────

def _rows(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as fh:
            return list(csv.DictReader(l for l in fh if not l.startswith("#")))
    except OSError as e:
        log.warning("reference file unreadable: %s (%s)", path, e)
        return []


@functools.lru_cache(maxsize=1)
def raw_input_rows() -> dict:
    """فصلٌ → صفُّ مدخلاته من `data/raw_inputs_l1.csv`."""
    out = {}
    for r in _rows(RAW_INPUTS_PATH):
        ch = (r.get("chapter") or "").strip().zfill(2)
        codes = [c.strip() for c in (r.get("input_codes") or "").split(";")
                 if c.strip()][:3]
        if ch and codes:
            out[ch] = {"codes": codes, "label": (r.get("input_label_ar") or "").strip(),
                       "source": (r.get("source") or "").strip()}
    return out


def raw_input_codes(hs_code: object) -> "dict | None":
    """مدخلاتُ فصل هذا الرمز — None = لم تُحدَّد بعد (فجوةٌ معلنة، لا تخمين)."""
    digits = "".join(ch for ch in str(hs_code or "") if ch.isdigit())
    if len(digits) < 2:
        return None
    return raw_input_rows().get(digits[:2])


@functools.lru_cache(maxsize=1)
def certification_rows() -> tuple:
    """صفوفُ `data/certifications_l1.csv` — صفُّ `official` بلا رابطٍ رسمي
    **يُتخطّى** (قاعدةُ المالك: «إلزامية» تحتاج مصدراً رسمياً)."""
    out = []
    for r in _rows(CERTS_PATH):
        basis = (r.get("basis") or "").strip().lower()
        url = (r.get("source_url") or "").strip()
        if basis == "official" and not url.startswith("http"):
            log.warning("certifications_l1: official row without source_url "
                        "skipped: %s", r.get("scheme"))
            continue
        out.append({k: v.strip() for k, v in r.items()
                    if isinstance(k, str) and isinstance(v, str)})
    return tuple(out)


def _market_matches(row_market: str, iso3: str) -> bool:
    if not iso3:
        return False
    if row_market == iso3:
        return True
    try:
        import silk_blocs
        if row_market == "GCC":
            return iso3 in silk_blocs.GCC
        if row_market == "EU":
            return iso3 in silk_blocs.EU27
    except Exception:  # noqa: BLE001
        return False
    return False


def certifications_for(market_iso3: str, hs_code: object,
                       kind: str = "certification") -> list:
    """الصفوفُ المنطبقة على (السوق × الرمز) لنوعٍ معيّن — بانطباق `applies_when`
    الحتميّ نفسِه الذي يستعمله مرجعُ الاشتراطات (بما فيه `processing:`)."""
    try:
        from silk_requirements_agent import applies_to, hs_category, is_animal_origin
    except Exception:  # noqa: BLE001
        return []
    cat = hs_category(hs_code)
    animal = is_animal_origin(hs_code)
    out = []
    for r in certification_rows():
        if r.get("kind") != kind or not _market_matches(r.get("market", ""),
                                                       (market_iso3 or "").upper()):
            continue
        rc = r.get("category") or "all"
        if rc not in ("all", cat) and not (rc == "animal" and animal):
            continue
        if applies_to(r, hs_code, cat) is False:
            continue
        out.append(r)
    return out


def official_vat(market_iso3: str, hs_code: object) -> tuple:
    """(نسبةُ الضريبة، الصفّ) من صفٍّ **رسمي** — لا صفَّ = (None, None) فيُكتب
    «تحتاج تحققاً» لا صفرٌ صامت.

    القاعدةُ المعلنة (رأسُ الملف): صفُّ `all` معدّلٌ قياسيٌّ للأصناف غير
    الغذائية فقط؛ الصنفُ الغذائي يحتاج صفَّ `food` (مخفّض/إعفاء) لأنّ معدّلاتِ
    الأغذية تختلف بالبند — تطبيقُ القياسي عليه اختلاقُ رقمٍ في مسار المال."""
    try:
        from silk_requirements_agent import hs_category
        food = hs_category(hs_code) == "food"
    except Exception:  # noqa: BLE001
        food = True                      # عند الشكّ لا يُطبَّق القياسي
    rows = [r for r in certifications_for(market_iso3, hs_code, kind="vat")
            if r.get("basis") == "official" and r.get("rate_pct") not in ("", None)
            and (not food or r.get("category") == "food")]
    if not rows:
        return None, None
    rows.sort(key=lambda r: 0 if r.get("category") not in ("all", "") else 1)
    try:
        return float(rows[0]["rate_pct"]), rows[0]
    except (TypeError, ValueError):
        return None, None


# ── الإشارات · signals (network, bounded, budget-gated) ─────────────────────

class _Budget:
    """سقفُ التشغيلة (`max_calls()` ناقصَ ما أنفقته إشارةٌ سابقة في التشغيلة
    نفسِها — `spent`) والميزانيةُ اليومية معاً؛ وما يُنفَق يُسجَّل في
    `collection_runs` عند الإغلاق كي تراه `comtrade_budget_left()` في
    التشغيلة التالية."""

    def __init__(self, spent: int = 0):
        left = max_calls() - max(0, int(spent or 0))
        try:
            from silk_collectors import comtrade_budget_left
            left = min(left, int(comtrade_budget_left()))
        except Exception:  # noqa: BLE001 — الميزانيةُ تحسينٌ لا شرط
            pass
        self.left = max(0, left)
        self.used = 0

    def has(self) -> bool:
        return self.left > 0

    def spend(self) -> None:
        self.left -= 1
        self.used += 1

    def close(self) -> None:
        if self.used <= 0:
            return
        try:
            from silk_collectors import _run_finish, _run_start, comtrade_budget_left
            run_id = _run_start("comtrade", self.used)
            _run_finish(run_id, self.used, 0, None, f"{MARK} signals")
            _run_finish(run_id, self.used, 0, comtrade_budget_left(), f"{MARK} signals")
        except Exception:  # noqa: BLE001 — التسجيلُ تحسينٌ لا شرط
            pass


def _has_signal(findings, kind: str, gap_needle: str = "") -> bool:
    """هل شُغِّلت الإشارةُ في هذا التقرير — إشارةٌ مُهيكَلة **أو** فجوتُها المعلنة
    (ملاحظةٌ بإبرة الطبقة)؛ وإلا أُلحِقت الفجوةُ في كلّ استئنافٍ فتغيّرت بصمةُ
    البعثة وأُعيد دفعُ المحلل (مراجعةٌ ذاتية §58)."""
    for dp in findings or []:
        v = dp.get("value") if isinstance(dp, dict) else getattr(dp, "value", None)
        if isinstance(v, dict) and v.get("kind") == kind:
            return True
        note = str(dp.get("note") if isinstance(dp, dict) else getattr(dp, "note", "") or "")
        if gap_needle and MARK in note and gap_needle in note:
            return True
    return False


def _dp(value, note: str, conf: float, year=None, stored_dates=()):
    """اكتشافُ الطبقة. قيمٌ من المخزن تحتفظ بتاريخ جلبها **الأصلي** وتحمل «من
    المخزن» في الملاحظة — لا تُقدَّم حيّةً (قاعدةُ التخزين في CLAUDE.md)."""
    from silk_data_layer import DataPoint
    import datetime as _dt
    ra = _dt.date.today().isoformat()
    if stored_dates:
        lo, hi = min(stored_dates), max(stored_dates)
        ra = lo
        note = f"{note} — من المخزن (جُلب: {lo if lo == hi else lo + '…' + hi})"
    return DataPoint(value, "UN Comtrade", conf, f"{MARK} {note}", ra, data_year=year)


def _iso3_of(name: str, code: object = None) -> "tuple | None":
    """(iso3, m49) لمورّدٍ من كومتريد — رمزُ M49 من الملخّص أوّلاً (يحمله
    `_competitor_dp`)، ثمّ مُحلّلُ الأسواق على الاسم؛ None = مجهولٌ يُتخطّى."""
    try:
        from silk_data_layer import _country_m49_index, _normalize_m49
        norm = _normalize_m49(code) if code not in (None, "") else ""
        row = _country_m49_index().get(norm) if norm.isdigit() else None
        if row and row.get("iso3"):
            return str(row["iso3"]).upper(), norm
    except Exception:  # noqa: BLE001
        pass
    try:
        from silk_market_resolver import resolve_market
        ref, _ = resolve_market(str(name or "").replace("Rep. of", "Republic of"))
        if ref is not None and ref.iso3 and ref.m49:
            return ref.iso3.upper(), str(ref.m49)
    except Exception:  # noqa: BLE001
        pass
    return None


def _flow_total(hs6: str, iso3: str, m49: str, year: int, flow: str,
                budget: _Budget, dates: "list | None" = None) -> tuple:
    """(القيمة، الحالة) لإجمالي تدفّقٍ نحو العالم — المخزنُ أوّلاً ثمّ كومتريد
    ضمن الميزانية. الحالة: stored / live / fetch_failed / no_record / no_budget.
    قيمةٌ من المخزن تُلحِق تاريخَ جلبها الأصلي بـ`dates` (لا تُقدَّم حيّةً)."""
    try:
        import silk_store
        row = silk_store.get_trade_flow(hs6, iso3, "WLD", year, flow)
        if row and row.get("value_usd") is not None:
            if dates is not None and row.get("retrieved_at"):
                dates.append(str(row["retrieved_at"])[:10])
            return float(row["value_usd"]), "stored"
    except Exception:  # noqa: BLE001
        pass
    if not budget.has():
        return None, "no_budget"
    from silk_data_layer import comtrade_trade, primary_qty, primary_value
    budget.spend()
    recs = comtrade_trade(hs6, m49, year, flow=flow, partner=0)
    if recs is None:
        return None, "fetch_failed"
    vals = [v for v in (primary_value(r) for r in recs) if v is not None]
    if not vals:
        return None, "no_record"
    total = float(sum(vals))
    try:
        import silk_store
        qty = sum(q for q in (primary_qty(r) for r in recs) if q is not None) or None
        silk_store.upsert_trade_flows([{"hs6": hs6, "reporter_iso3": iso3,
                                        "partner_iso3": "WLD", "year": year,
                                        "flow": flow, "value_usd": total,
                                        "qty_kg": qty}])
    except Exception:  # noqa: BLE001 — المخزنُ تحسين
        pass
    return total, "live"


def _default_year() -> int:
    import datetime as _dt
    return _dt.date.today().year - 1


def augment_supplier_nature(report, hs_code: str, market, year=None,
                            spent: int = 0) -> None:
    """البند ٢: لكلّ مورّدٍ من الثلاثة الأكبر — منتجٌ عالميٌّ أم معيدُ تصدير؟

    القاعدةُ المعلنة: ليس من أعلى N مصدّرٍ عالمي **و**وارداتُه من الصنف ≥
    صادراتِه ⇒ معيدُ تصديرٍ مرجَّح، ويُطلَب المصدرُ الفعلي خلفه (أكبرُ مورّدٍ
    له). idempotent على `kind == supplier_nature`؛ الفشلُ فجوةٌ معلنة.
    """
    findings = getattr(report, "findings", None)
    if findings is None or _has_signal(findings, "supplier_nature", "طبيعة المورّدين"):
        return
    hs6 = "".join(ch for ch in str(hs_code or "") if ch.isdigit())[:6]
    summary = None
    for dp in findings:
        v = getattr(dp, "value", None)
        if isinstance(v, dict) and v.get("top_suppliers"):
            summary = v
            break
    if not summary or not hs6:
        findings.append(_dp(None, "طبيعة المورّدين غير محسوبة — لا ملخّص "
                                  "مورّدين مهيكل في هذه البعثة", 0.0))
        return
    y = int(summary.get("year") or year or _default_year())
    budget = _Budget(spent)
    if not budget.has():
        findings.append(_dp(None, "طبيعة المورّدين غير محسوبة — ميزانية "
                                  "كومتريد اليومية مستنفدة أو بلا مفتاح", 0.0, y))
        return
    from silk_data_layer import comtrade_trade, partner_name, primary_value
    from silk_market_ranker import _producer_advisory_topn, world_export_totals
    topn = _producer_advisory_topn()
    # ترتيبُ مصدّري العالم من الدالة القانونية نفسِها (المُرتِّب) — نداءٌ واحد؛
    # تعذُّرُه يُعلَن فجوةً **قبل** إنفاق نداءات المورّدين التي لا تُقيَّم بدونه.
    budget.spend()
    top = world_export_totals(hs6, y, on_fetch_failure=None)
    if top is None:
        budget.close()
        findings.append(_dp(None, "طبيعة المورّدين غير محسوبة — تعذّر جلب "
                                  "قائمة كبار مصدّري العالم من كومتريد", 0.0, y))
        return
    world_top = [t["iso3"] for t in top[:topn]]
    rows = []
    partial = False
    dates: list = []
    for s in (summary.get("top_suppliers") or [])[:TOP_SUPPLIERS]:
        name = str(s.get("partner") or "")
        if "سعود" in name or "saudi" in name.lower():
            continue
        row = {"partner": name, "share": s.get("share"), "iso3": None,
               "world_top_exporter": None, "exports_usd": None,
               "imports_usd": None, "reexporter_likely": None,
               "actual_source": None, "status": ""}
        code = _iso3_of(name, s.get("code"))
        if code is None:
            row["status"] = "unknown_country"
            rows.append(row)
            continue
        iso3, m49 = code
        row["iso3"] = iso3
        row["world_top_exporter"] = (iso3 in world_top) if world_top is not None else None
        exp, st_x = _flow_total(hs6, iso3, m49, y, "X", budget, dates)
        imp, st_m = _flow_total(hs6, iso3, m49, y, "M", budget, dates)
        row["exports_usd"], row["imports_usd"] = exp, imp
        row["status"] = f"X:{st_x} M:{st_m}"
        partial = partial or "no_budget" in (st_x, st_m)
        if row["world_top_exporter"] is False and exp is not None and imp is not None:
            row["reexporter_likely"] = imp >= exp
        elif row["world_top_exporter"] is True:
            row["reexporter_likely"] = False
        if row["reexporter_likely"] and budget.has():
            budget.spend()
            recs2 = comtrade_trade(hs6, m49, y, flow="M", partner="all")
            best = None
            for r in recs2 or []:
                pc = str(r.get("partnerCode") or "")
                val = primary_value(r)
                if pc in ("0", "") or val is None:
                    continue
                if best is None or val > best[0]:
                    best = (val, pc)
            if best is not None:
                src = _iso3_of("", best[1])
                # الحصةُ من إجمالي وارداته المرصود فقط — صفرٌ أو غيابٌ = لا حصة.
                share = (round(100 * min(best[0], imp) / imp, 1)
                         if imp else None)
                row["actual_source"] = {
                    "partner": partner_name(best[1]),
                    "iso3": src[0] if src else "", "share": share}
        rows.append(row)
    budget.close()
    known = [r for r in rows if r["reexporter_likely"] is not None]
    n_re = sum(1 for r in known if r["reexporter_likely"])
    findings.append(_dp(
        {"kind": "supplier_nature", "year": y, "topn": topn,
         "world_top_exporters": world_top, "rows": rows,
         "calls_used": budget.used, "partial": partial},
        f"طبيعة المورّدين الأكبر لسنة {y}: {len(known)} مُقيَّم من {len(rows)}، "
        f"منهم {n_re} معيد تصدير مرجَّح — القاعدة: ليس من أعلى {topn} مصدّراً "
        "عالمياً ووارداته ≥ صادراته",
        0.8 if known else 0.0, y, stored_dates=tuple(dates)))


def augment_raw_input_trade(report, hs_code: str, year=None) -> None:
    """البند ١: صافي تجارة السعودية في المدخلات الخام لفصل المنتج (≤ ٣ رموز
    HS4 × تدفّقان) — مؤشّرٌ للإنتاج لا قياسٌ له. idempotent على
    `kind == raw_input_trade`."""
    findings = getattr(report, "findings", None)
    if findings is None or _has_signal(findings, "raw_input_trade", "المدخلات الخام"):
        return
    spec = raw_input_codes(hs_code)
    if not spec:
        findings.append(_dp(None, "صافي تجارة المدخلات الخام غير محسوب — لم "
                                  "تُحدَّد مدخلاتُ هذا الفصل في data/raw_inputs_l1.csv",
                            0.0))
        return
    y = int(year or _default_year())
    budget = _Budget()
    if not budget.has():
        findings.append(_dp(None, "صافي تجارة المدخلات الخام غير محسوب — ميزانية "
                                  "كومتريد اليومية مستنفدة أو بلا مفتاح", 0.0, y))
        return
    iso3, m49 = _SAU
    rows = []
    dates: list = []
    for code in spec["codes"]:
        exp, st_x = _flow_total(code, iso3, m49, y, "X", budget, dates)
        imp, st_m = _flow_total(code, iso3, m49, y, "M", budget, dates)
        rows.append({"code": code, "exports_usd": exp, "imports_usd": imp,
                     "status": f"X:{st_x} M:{st_m}"})
    budget.close()
    observed = [r for r in rows if r["exports_usd"] is not None
                and r["imports_usd"] is not None]
    exports = sum(r["exports_usd"] for r in observed) if observed else None
    imports = sum(r["imports_usd"] for r in observed) if observed else None
    net = (exports - imports) if observed else None
    findings.append(_dp(
        {"kind": "raw_input_trade", "year": y, "codes": spec["codes"],
         "label": spec["label"], "rows": rows, "exports_usd": exports,
         "imports_usd": imports, "net_usd": net,
         "observed_codes": len(observed), "calls_used": budget.used},
        (f"صافي تجارة السعودية في المدخلات الخام ({spec['label']}) سنة {y}: "
         f"{'صادرات > واردات' if (net or 0) > 0 else 'واردات ≥ صادرات'} على "
         f"{len(observed)} من {len(rows)} رموز" if observed else
         f"صافي تجارة السعودية في المدخلات الخام ({spec['label']}) غير مرصود — "
         f"لا تدفّق مكتمل لأيّ رمز ({'; '.join(r['status'] for r in rows)})"),
        0.8 if observed else 0.0, y, stored_dates=tuple(dates)))


# ── الاستنتاجات · insights (pure, from stored findings) ─────────────────────

def _signal(missions: dict, mission: str, kind: str) -> "dict | None":
    rep = (missions or {}).get(mission) or {}
    findings = rep.get("findings") if isinstance(rep, dict) else getattr(rep, "findings", None)
    for dp in findings or []:
        v = dp.get("value") if isinstance(dp, dict) else getattr(dp, "value", None)
        if isinstance(v, dict) and v.get("kind") == kind:
            return v
    return None


def _signal_gap_note(missions: dict, mission: str, needle: str) -> str:
    rep = (missions or {}).get(mission) or {}
    findings = rep.get("findings") if isinstance(rep, dict) else getattr(rep, "findings", None)
    for dp in findings or []:
        note = dp.get("note") if isinstance(dp, dict) else getattr(dp, "note", "")
        if MARK in str(note or "") and needle in str(note or ""):
            return str(note).replace(MARK, "").strip()
    return "لم تُشغَّل إشارات التحليل التجاري لهذه التشغيلة"


def _mission_text(missions: dict, *keys) -> str:
    parts = []
    for k in keys:
        rep = (missions or {}).get(k) or {}
        findings = rep.get("findings") if isinstance(rep, dict) else getattr(rep, "findings", None)
        for dp in findings or []:
            v = dp.get("value") if isinstance(dp, dict) else getattr(dp, "value", None)
            note = dp.get("note") if isinstance(dp, dict) else getattr(dp, "note", "")
            parts.append(str(note or ""))
            if isinstance(v, str):
                parts.append(v)
    return " ".join(parts).lower()


_CUR_RE = re.compile(r"[€$£]|\b(?:usd|eur|gbp|sar|aed|try|inr|jpy|egp|mad|jod|kes|ngn|dzd|lyd)\b"
                     r"|ريال|دولار|يورو|درهم|ليرة|روبية|جنيه|دينار", re.IGNORECASE)
_PACK_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:كجم|كغم|كغ|جم|غم|غ|مل|لتر|ل|kg|g|gr|ml|l|lb|oz)\b",
                      re.IGNORECASE)
_DATE_RE = re.compile(r"20\d\d-\d\d(?:-\d\d)?")
_STORE_RE = re.compile(r"https?://|www\.|\.com|\.net|\.org|متجر|سوبرماركت|هايبر|"
                       r"supermarket|store|shop|market|carrefour|lulu|panda|"
                       r"albert heijn|jumbo|edeka|rewe|migros|coop|tesco|amazon",
                       re.IGNORECASE)


def price_evidence(missions: dict) -> tuple:
    """(عددُ سطور الأسعار المكتملة، العددُ الكلي) — مكتملٌ = علامة/متجر أو موقع
    محدّد + تاريخ + عبوة + عملة (البند ٥). الأقلُّ من ٣ = ضعيفُ التوثيق."""
    rep = (missions or {}).get("pricing_scout") or {}
    findings = rep.get("findings") if isinstance(rep, dict) else getattr(rep, "findings", None)
    total = complete = 0
    for dp in findings or []:
        v = dp.get("value") if isinstance(dp, dict) else getattr(dp, "value", None)
        note = str(dp.get("note") if isinstance(dp, dict) else getattr(dp, "note", "") or "")
        blob = f"{note} {v if isinstance(v, str) else ''}"
        num = None
        try:
            num = float(v) if not isinstance(v, (dict, list, str)) and v is not None else None
        except (TypeError, ValueError):
            num = None
        if num is None and not re.search(r"\d", blob):
            continue
        if MARK in note:
            continue
        total += 1
        if (_CUR_RE.search(blob) and _PACK_RE.search(blob) and _DATE_RE.search(blob)
                and _STORE_RE.search(blob)):
            complete += 1
    return complete, total


def _card_attributes(card: dict) -> list:
    """سماتُ المنتج القابلةُ للمقارنة من بطاقته: شهادات، هويةُ منشأ، شريحة."""
    attrs = []
    for c in (card or {}).get("certifications") or []:
        c = str(c).strip()
        if c:
            attrs.append(("شهادة", c))
    oc = str((card or {}).get("origin_claim") or "").strip()
    if oc:
        attrs.append(("هوية المنشأ", oc))
    tier = str((card or {}).get("tier") or "").strip().lower()
    if tier == "premium":
        attrs.append(("الشريحة", "premium"))
    return attrs


_ATTR_SYNONYMS = {
    "halal": ("halal", "حلال"), "حلال": ("halal", "حلال"),
    "organic": ("organic", "عضوي", "bio"), "عضوي": ("organic", "عضوي", "bio"),
    "premium": ("premium", "فاخر", "gourmet", "بريميوم"),
    "iso22000": ("iso 22000", "iso22000"), "haccp": ("haccp",),
    "brc": ("brc",), "ifs": ("ifs",), "fssc": ("fssc",),
}


def _attr_words(value: str) -> tuple:
    key = value.strip().lower()
    return _ATTR_SYNONYMS.get(key, (key,))


def fill_insights(dr: dict, put, *, hs_code=None, market_iso3: str = "",
                  product_card: "dict | None" = None) -> None:
    """اكتب استنتاجاتِ الطبقة في السجلّ — نقيّةٌ، من الاكتشافات المخزَّنة فقط."""
    import silk_fact_ledger as L
    missions = (dr or {}).get("missions") or {}

    # ١) ميزةُ التكلفة — صافي تجارة المدخلات الخام × طبيعةُ المنافسين.
    rit = _signal(missions, "trade_flow", "raw_input_trade")
    sn = _signal(missions, "competitors", "supplier_nature")
    if rit and rit.get("net_usd") is not None:
        put(L._entry("saudi_raw_input_balance", rit["net_usd"], source="UN Comtrade",
                     confidence=0.8, year=rit.get("year"), origin="trade_flow",
                     note=f"صادرات السعودية − وارداتها من المدخلات الخام "
                          f"({rit.get('label', '')}) سنة {rit.get('year')} على "
                          f"{rit.get('observed_codes')} رموز"))
        saudi_produces = float(rit["net_usd"]) > 0
        producers = [r for r in (sn or {}).get("rows") or []
                     if r.get("world_top_exporter") is True]
        known = [r for r in (sn or {}).get("rows") or []
                 if r.get("world_top_exporter") is not None]
        rivals_produce = bool(known) and len(producers) / len(known) >= 0.5
        saudi_side = ("السعودية مصدّرٌ صافٍ للمدخل الخام" if saudi_produces
                      else "السعودية مستوردٌ صافٍ للمدخل الخام")
        if not known:
            # لا إشارةَ مورّدين ⇒ لا يُقال شيءٌ عن المنافسين (لا اختلاق).
            verdict, why = "محايد", (saudi_side + "، وطبيعةُ كبار مورّدي السوق "
                                    "لم تُقيَّم بعد فلا يُحسم الاتجاه")
        elif saudi_produces and not rivals_produce:
            verdict, why = "ميزة", (saudi_side + " بينما كبارُ مورّدي السوق ليسوا "
                                   "من كبار منتجيه")
        elif not saudi_produces and rivals_produce:
            verdict, why = "عيب", (saudi_side + " بينما كبارُ مورّدي السوق من "
                                  "كبار منتجيه")
        else:
            verdict, why = "محايد", ("لا يميل صافي تجارة المدخل وطبيعةُ المنافسين "
                                    "إلى طرف")
        put(L.insight_entry(
            "cost_advantage", verdict, grade=L.INFERENCE,
            basis=("saudi_raw_input_balance",) + (("top_supplier_share_pct",) if known else ()),
            assumption="صافي التجارة مؤشّرٌ للإنتاج لا قياسٌ له",
            flip_if=("لو ثبت أن السعودية تستورد المدخلَ الخام صافياً تنقلب الميزة"
                     if verdict == "ميزة" else
                     "لو ثبت إنتاجٌ محليٌّ للمدخل الخام يفوق وارداته ينقلب الحكم"),
            note=why))
    else:
        gap = _signal_gap_note(missions, "trade_flow", "المدخلات الخام")
        put(L._entry("saudi_raw_input_balance", None, origin="trade_flow", note=gap))
        put(L._entry("cost_advantage", None, origin="trade_flow",
                     note="لا يُستنتَج بلا صافي تجارة المدخلات الخام — " + gap))

    # ٢) طبيعةُ المنافسين وحصةُ المنافسين المباشرين.
    if sn and sn.get("rows"):
        rows = sn["rows"]
        n_re = sum(1 for r in rows if r.get("reexporter_likely"))
        n_prod = sum(1 for r in rows if r.get("reexporter_likely") is False)
        n_unknown = len(rows) - n_re - n_prod
        summary = (f"{n_prod} منتج و{n_re} معيد تصدير مرجَّح"
                   + (f" و{n_unknown} لم يُقيَّم" if n_unknown else ""))
        put(L.insight_entry(
            "supplier_nature", summary, grade=L.INFERENCE,
            basis=("top_supplier_share_pct",), items=[dict(r) for r in rows],
            assumption=(f"مورّدٌ ليس من أعلى {sn.get('topn')} مصدّراً عالمياً "
                        "ووارداتُه من الصنف ≥ صادراتِه ⇒ معيدُ تصديرٍ مرجَّح"),
            flip_if="لو تبيّن إنتاجٌ محليٌّ لدى مورّدٍ عُدّ معيدَ تصدير",
            source="UN Comtrade", year=sn.get("year")))
        direct = [r for r in rows if r.get("reexporter_likely") is not True
                  and r.get("share") is not None]
        if direct:
            put(L.insight_entry(
                "direct_competitor_share_pct",
                round(sum(float(r["share"]) for r in direct), 1),
                grade=L.INFERENCE, basis=("top_supplier_share_pct", "hhi"),
                assumption="معيدُ التصدير لا يُعدّ منافساً مباشراً؛ حصصُ الباقين تُجمَع",
                note="مؤشّرُ التركّز على مستوى الدول لا يُقدَّم وحده مقياساً لشدّة "
                     "المنافسة", source="UN Comtrade", year=sn.get("year")))
        else:
            put(L._entry("direct_competitor_share_pct", None, origin="competitors",
                         note="كلُّ المورّدين الأكبر معيدو تصدير أو بلا حصة"))
    else:
        gap = _signal_gap_note(missions, "competitors", "طبيعة المورّدين")
        put(L._entry("supplier_nature", None, origin="competitors", note=gap))
        put(L._entry("direct_competitor_share_pct", None, origin="competitors",
                     note="لا يُستنتَج بلا طبيعة المورّدين — " + gap))

    # ٤) التمايزُ الحقيقي — سماتُ البطاقة مقابل ما يملكه المنافسون.
    attrs = _card_attributes(product_card or {})
    if not attrs:
        put(L._entry("differentiation", None, origin="pricing_scout",
                     note="لم تُدخَل سماتُ المنتج (الشهادات، هويةُ المنشأ، الشريحة) "
                          "في بطاقة المنتج — يُعرَف بإدخالها"))
    else:
        text = _mission_text(missions, "pricing_scout", "competitors")
        owned, free = [], []
        for kind, val in attrs:
            (owned if any(w in text for w in _attr_words(val)) else free).append(f"{kind}: {val}")
        if free:
            value = "ممكن عبر " + "؛ ".join(free)
            note = ("لم تظهر هذه السمات في سطور المنافسين المرصودة" +
                    (f"؛ أمّا {'؛ '.join(owned)} فيملكها منافسٌ رئيسي فلا تُعلَن ميزة"
                     if owned else ""))
        else:
            value = "غير واضح بعد"
            note = "كلُّ السمات المُدخَلة يملكها منافسٌ رئيسي: " + "؛ ".join(owned)
        put(L.insight_entry(
            "differentiation", value, grade=L.INFERENCE, basis=("competitor_prices",),
            assumption="سماتُ المنافسين مقروءةٌ من سطور الأسعار المرصودة فقط",
            flip_if="لو رُصد منافسٌ رئيسي يحمل السمةَ نفسَها يسقط التمايز",
            note=note, source="بعثة الأسعار والمنافسين"))

    # ٥) جودةُ توثيق أسعار المنافسين.
    complete, total = price_evidence(missions)
    if total == 0:
        put(L._entry("price_evidence_quality", None, origin="pricing_scout",
                     note="لا سطر سعرٍ مرصوداً"))
    else:
        put(L.graded_entry(
            "price_evidence_quality", f"{complete} من {total}",
            L.WEAK if complete < 3 else L.OBSERVED, source="بعثة الأسعار",
            origin="pricing_scout",
            note=f"{complete} سطر سعر مكتمل (متجر/موقع محدّد + تاريخ + عبوة + "
                 f"عملة) من {total} — أقلّ من 3 = ضعيف التوثيق"))

    # ٣/٦) الشهاداتُ الإلزامية بمصدرٍ رسمي.
    certs = certifications_for(market_iso3, hs_code, kind="certification")
    if certs:
        put(L.graded_entry(
            "mandatory_certifications", "؛ ".join(c.get("scheme", "") for c in certs),
            L.OBSERVED,
            source="؛ ".join(sorted({c.get("authority", "") for c in certs if c.get("authority")})),
            origin="customs_requirements",
            note="شهاداتُ مطابقةٍ بمصدرٍ رسمي لهذا السوق والفئة",
            items=[{"scheme": c.get("scheme"), "authority": c.get("authority"),
                    "source_url": c.get("source_url")} for c in certs]))
    else:
        put(L._entry("mandatory_certifications", None, origin="customs_requirements",
                     note="لا صفَّ رسمياً لهذا السوق والفئة في data/certifications_l1.csv "
                          "— تُكتب الشهاداتُ «مطلوبة تجارياً» لا «إلزامية»"))
