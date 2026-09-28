"""بناء «حالة الدراسة» من نتيجة `/research` — deep_research → case dict (P2-1/P1-3).

المدخل نتيجةُ تحليلٍ مخزَّنة (`found`) تحمل `deep_research` بالبعثات، والمخرج قاموسٌ
بصيغة `evals/golden_set/malaysia_coffee_fixture.json` يستهلكه `silk_study_render`.
كل ما لا يُستخرج **بنيوياً** (قيمة رقمية بسنتها من نقطة بيانات) يبقى `None`؛ المحرك
يُسقط الفقرة ويُعلن الفجوة في «ما لم يتسنّ توثيقه» — لا رقم يُقدَّر ولا نصّ يُختلق.
لا نداء شبكي ولا نموذج هنا؛ الاعتماد على قرّاء الركائز الموجودين (`silk_deep_pillars`).
"""
from __future__ import annotations

import csv
import os
import datetime as _dt
import re

_ROOT = os.path.dirname(os.path.abspath(__file__))

_USD_PER_KG_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:دولار|USD|\$)\s*/?\s*(?:كجم|كغ|kg)", re.I)


def _findings(dr: dict, mission: str) -> list[dict]:
    m = (dr.get("missions") or {}).get(mission) or {}
    out = []
    for f in (m.get("findings") if isinstance(m, dict) else getattr(m, "findings", None)) or []:
        if isinstance(f, dict):
            out.append(f)
        else:
            out.append({"value": getattr(f, "value", None), "source": getattr(f, "source", ""),
                        "note": getattr(f, "note", ""), "data_year": getattr(f, "data_year", None),
                        "status": getattr(f, "status", ""), "confidence": getattr(f, "confidence", 0),
                        "retrieved_at": getattr(f, "retrieved_at", None)})
    return out


def _indicator(dr: dict, words: tuple[str, ...], lo: float, hi: float) -> dict | None:
    """أحدث نقطة رقمية بسنة بنيوية تحمل إحدى الكلمات في ملاحظتها."""
    best = None
    for mission in ("risk_news", "demographics_economy", "logistics", "trade_flow"):
        for f in _findings(dr, mission):
            v, note, y = f.get("value"), str(f.get("note") or ""), f.get("data_year")
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not isinstance(y, int):
                continue
            if not any(w in note for w in words) or not (lo <= float(v) <= hi):
                continue
            if best is None or y > best["year"]:
                best = {"value": float(v), "year": y, "source": str(f.get("source") or "")}
    return best


def _nisba(iso3: str) -> tuple[str | None, str | None]:
    """صفة النسبة (مؤنثة، مذكرة) من data/market_nisba_l1.csv — غيابها فجوة لا تخمين."""
    import csv
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "market_nisba_l1.csv")
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8") as f:
        rows = [ln for ln in f if not ln.startswith("#")]
    for r in csv.DictReader(rows):
        if r.get("iso3") == iso3:
            return r.get("nisba_f") or None, r.get("nisba_m") or None
    return None, None


# P3-3: الجهة القادرة على استكمال كل فجوة — حتمية، لا يخمّنها النموذج.
GAP_OWNERS = {
    "سلسلة الواردات السنوية": "UN Comtrade (سحب لاحق)",
    "حصص الموردين": "UN Comtrade (سحب لاحق)",
    "الرسم الجمركي المنطبق": "جمارك السوق المستهدفة",
    "سعر الصرف": "البنك الدولي (سحب لاحق)",
    "مؤشرات الحوكمة": "البنك الدولي (سحب لاحق)",
    "مؤشر الأداء اللوجستي": "البنك الدولي (سحب لاحق)",
    "أسعار الرف": "المنشأة (رصد ميداني)",
    "مستوردون مؤكدون بالاسم": "المبيعات (أدلة الجهات المعتمدة ومعارض القطاع)",
}


def provisional_threshold(shelf: list, landed_high_pct: int = 45) -> int | None:
    """P3-8: عتبة مؤقتة = أعلى سعر رف مرصود (دولار/كغ) × الحد الأعلى للتكلفة الواصلة،
    مقرّبةً للأدنى. بلا رف مرصود = فجوة (None)."""
    # الصفوف المكافئة وحدها — نفسها التي يقرؤها القالب «أعلى سعر مرصود».
    vals = [r["usd_kg"] for r in shelf or [] if isinstance(r.get("usd_kg"), (int, float))
            and r.get("equivalent", True)]
    return int(max(vals) * landed_high_pct // 100) if vals else None


REVIEW_LIMIT_OWNER = "فريق الدراسة (إصدار محدَّث)"   # P5-6: حدود أعلنها المراجع
MIN_ENTITIES = 2      # P4-4: أقل من جهتين مؤكدتين ⇒ فجوة بجهة استكمال محددة


def market_directories(iso3: str) -> list[dict]:
    """جهات البحث الرسمية عن مستوردين في السوق (data/market_directories_l1.csv)."""
    p = os.path.join(_ROOT, "data", "market_directories_l1.csv")
    try:
        with open(p, encoding="utf-8") as f:
            rows = list(csv.DictReader(ln for ln in f if not ln.startswith("#")))
    except OSError:
        return []
    return [r for r in rows if r.get("iso3") == iso3]


def threshold_from(shelf: list, landed_high_pct: int = 45) -> tuple[int | None, bool]:
    """(العتبة، هل هي مؤقتة). سعرُ رفٍ من الشريحة المستهدفة مرصود ⇒ العتبة منه (أدناه،
    تحفّظاً) وغير مؤقتة؛ وإلا المؤقتة من أعلى الصفوف المكافئة؛ وإلا فجوة."""
    tgt = [r["usd_kg"] for r in shelf or [] if r.get("segment_target")
           and isinstance(r.get("usd_kg"), (int, float))]
    if tgt:
        return int(min(tgt) * landed_high_pct // 100), False
    v = provisional_threshold(shelf, landed_high_pct)
    return v, v is not None


def _gap(label: str, iso3: str = "") -> dict:
    owner = GAP_OWNERS.get(label) or REVIEW_LIMIT_OWNER
    if label == "مستوردون مؤكدون بالاسم":
        dirs = [d["name_ar"] for d in market_directories(iso3)]
        owner = ("المبيعات عبر " + " و".join(dirs)) if dirs else \
            "المبيعات عبر غرفة التجارة في السوق المستهدفة"
    return {"label": label, "owner": owner}


def _merge_claims(*groups) -> list[dict]:
    seen, out = set(), []
    for g in groups:
        for c in g or []:
            if c.get("id") not in seen:
                seen.add(c.get("id"))
                out.append(c)
    return out


def _seg_cfg() -> dict:
    try:
        import yaml
        with open(os.path.join(_ROOT, "data", "shelf_segment_keywords.yaml"), encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, ImportError):
        return {}


def shelf_segment(text: str, hs: str = "0901") -> str:
    """P4-2: شريحة صف الرف بأول مطابقة (كلمة كاملة) من كلمات فصل HS؛ وإلا «غير محدد»."""
    cfg = ((_seg_cfg().get("by_hs") or {}).get(str(hs or "")[:4]) or {})
    t = str(text or "").lower()
    for seg in cfg.get("order") or []:
        for w in (cfg.get("segments") or {}).get(seg) or []:
            if re.search(rf"(?<![\w\u0600-\u06FF]){re.escape(w.lower())}(?![\w\u0600-\u06FF])", t):
                return seg
    return "غير محدد"


def segment_target(product_segment: str | None) -> str | None:
    return (_seg_cfg().get("target") or {}).get(str(product_segment or ""))


def _requirements_from_gaps(gaps: list, shelf: list, candidates: int) -> list[dict]:
    """متطلبات القرار المرقّمة تُشتق حتمياً من الفجوات (P1-5): تكلفة الوحدة أولاً
    دائماً (رقم المنشأة)، ثم سعر رف الشريحة، ثم مسار الاعتماد، ثم الجهات."""
    reqs = [{"id": 1, "text": "تحديد تكلفة إنتاج الكيلوغرام لدى المنشأة", "owner": "المنشأة"}]
    if not shelf or "أسعار الرف" in [g["label"] if isinstance(g, dict) else g for g in gaps]:
        reqs.append({"id": len(reqs) + 1, "text": "رصد سعر رف فعلي لمنافس واحد على الأقل من الشريحة المستهدفة", "owner": "المبيعات"})
    if candidates < MIN_ENTITIES:
        reqs.append({"id": len(reqs) + 1, "text": "تحديد جهتين أو ثلاث من المستوردين المؤكدين قبل بدء التفاوض", "owner": "المبيعات"})
    return reqs


def _knowledge_claims(hs: str, iso2: str) -> list[dict]:
    """P3-1: ادعاءات «يُفاد» المهيكلة من ملف المعرفة المعتمد (إن وُجد)."""
    try:
        from silk_study_render import load_knowledge
        return list(load_knowledge(hs, iso2).get("claims") or [])
    except Exception:  # noqa: BLE001 — المعرفة إضافة لا شرط
        return []


# P3-4: ملف المصدّر — يحدد أي نفع يجوز نسبته إليه.
EXPORTER_TYPES = ("agri_producer", "processor_of_imported_input", "manufacturer")


def build_case(found: dict, *, product_short: str | None = None,
               exporter_type: str | None = None,
               segment: str = "specialty") -> dict:
    dr = found.get("deep_research") or {}
    missions = dr.get("missions") or {}
    exporter_type = (exporter_type or dr.get("exporter_type") or found.get("exporter_type")
                     or "processor_of_imported_input")
    from silk_deep_pillars import import_series, top_supplier_shares
    from silk_market_resolver import resolve_market
    mk = found.get("market") or ""
    market_name = (mk.get("name_en") or mk.get("iso3") or "") if isinstance(mk, dict) else str(mk)
    ref, _ = resolve_market(market_name)
    iso3 = getattr(ref, "iso3", "") or ""
    iso2 = getattr(ref, "iso2", "") or ""
    name_ar = getattr(ref, "name_ar", None) or market_name
    hs = str(found.get("hs_code") or "")
    product = str(found.get("product") or "")
    today = _dt.date.today()

    # ── الواردات ─────────────────────────────────────────────────────────
    imp = import_series(missions)
    series = [{"year": p["year"], "value_musd": round(p["value"] / 1e6, 1), "kg": None,
               "complete": not (p.get("partial") or p.get("provisional"))} for p in imp.get("series") or []]
    # الوزن (إن وُجد) من نقاط «صافي الوزن» بسنة بنيوية
    for f in _findings(dr, "trade_flow"):
        v, note, y = f.get("value"), str(f.get("note") or ""), f.get("data_year")
        if isinstance(v, (int, float)) and isinstance(y, int) and ("وزن" in note or "netWgt" in note or "كجم" in note):
            for p in series:
                if p["year"] == y:
                    p["kg"] = float(v)
    for p in series:
        if p["kg"] and p["kg"] > 0:
            p["unit_value"] = p["value_musd"] * 1e6 / p["kg"]
    uvs = [p for p in series if p.get("unit_value")]
    if len(uvs) >= 2:
        med = sorted(p["unit_value"] for p in uvs)[len(uvs) // 2]
        for p in uvs:
            if abs(p["unit_value"] - med) > 0.6 * med:
                p["weight_anomaly"] = True
    reliable = [p for p in uvs if not p.get("weight_anomaly")]
    excluded = [p["year"] for p in uvs if p.get("weight_anomaly")]

    # ── الموردون ─────────────────────────────────────────────────────────
    rows, _sup_src = top_supplier_shares(missions)
    sup_year = (_sup_src or {}).get("year") if isinstance(_sup_src, dict) else None
    top = []
    for r in rows[:4]:
        pref, _ = resolve_market(r["partner"])
        top.append({"iso3": getattr(pref, "iso3", "") or "", "name_ar": getattr(pref, "name_ar", None) or r["partner"],
                    "share_pct": r["share"], "kind": None})
    saudi = next((r["share"] for r in rows if r.get("saudi")), 0.0)
    sup_count = None
    for f in _findings(dr, "competitors"):
        v = f.get("value")
        if isinstance(v, dict) and v.get("supplier_count"):
            sup_count = int(v["supplier_count"])
            break

    # ── التعرفة ──────────────────────────────────────────────────────────
    tariff = {"status": "gap", "rate_pct": None}
    for f in _findings(dr, "tariffs_agreements"):
        v = f.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= float(v) <= 100:
            tariff = {"status": "exempt" if float(v) == 0 else "rate", "rate_pct": float(v)}
            break

    # ── المؤشرات العامة ──────────────────────────────────────────────────
    fx = _indicator(dr, ("سعر الصرف", "PA.NUS.FCRF", "صرف"), 0.01, 100000)
    gdp = _indicator(dr, ("نمو الناتج", "GDP growth", "النمو"), -30, 30)
    inf = _indicator(dr, ("التضخم", "inflation"), -10, 200)
    lpi = _indicator(dr, ("LPI", "الأداء اللوجستي"), 1, 5)
    wgi = _indicator(dr, ("PV.EST", "الاستقرار السياسي"), -3, 3)

    # ── المتطلبات (المرجع الثابت) ──────────────────────────────────────────
    req_rows, sst_rule, halal_mandatory = [], None, None
    try:
        from silk_requirements_agent import _checklist_rows, hs_category, is_animal_origin
        entry_rows, _elig, _exit = _checklist_rows(iso3, hs_category(hs).lower(), is_animal_origin(hs), hs)
        for r in entry_rows:
            item = str(r.get("item_ar") or "")
            status = str(r.get("requirement_status") or "")
            if "ضريبة" in item:
                m = re.search(r"بمعدّل\s+(.+?)\s+—", item)
                sst_rule = m.group(1) if m else None
                continue
            if "حلال" in item:
                halal_mandatory = status == "legal_mandatory"
                continue
            party = "المستورد" if "المستورد" in item else "المصدّر"
            req_rows.append({"item": item, "authority": str(r.get("authority") or "").split(" — ")[0],
                             "party": party, "verified_at": r.get("verified_at") or None})
    except Exception:  # noqa: BLE001 — غياب المرجع = فجوة معلنة لا انهيار
        pass

    # ── الجهات وأسعار الرف ────────────────────────────────────────────────
    # P4-1: جهات مهيكلة مؤكَّدة بالمنتج + سطر استبعاد معلَّل (silk_study_entities).
    from silk_study_entities import classify, outlet_claims
    _leads = (dr.get("importer_leads") or {}).get("leads") or []
    _chan = _findings(dr, "channels_importers")
    entities, excluded_text = classify(_leads, _chan, hs, product, iso3)
    shelf = []
    for f in _findings(dr, "pricing_scout"):
        v, note = f.get("value"), str(f.get("note") or "")
        txt = f"{v} {note}"
        m = _USD_PER_KG_RE.search(txt)
        if m and "استيراد" not in note and "Comtrade" not in str(f.get("source") or ""):
            seg = shelf_segment(f"{note} {f.get('source') or ''}", hs)      # P4-2
            date = str(f.get("retrieved_at") or "")[:10]
            src = str(f.get("source") or "") + (f"، {date}" if date else "")
            shelf.append({"product": note[:60] or "منتج مرصود", "segment": seg, "price": m.group(0),
                          "source": src, "usd_kg": float(m.group(1).replace(",", ".")),
                          "segment_target": False, "equivalent": seg != "غير مكافئ"})
    target_seg = segment_target(segment)
    for r in shelf:
        # صفوف الشريحة المستهدفة ليست من «نطاق أسعار الرف للمنتجات غير المختصة» — تُعزل
        # فيُبنى عليها المرجع مباشرة (العتبة غير مؤقتة)، ولا تدخل النطاق.
        if target_seg and r["segment"] == target_seg:
            r["segment_target"], r["equivalent"] = True, False

    from silk_synthesis import study_decision
    decision = study_decision(dr.get("verdict") or {})
    gaps = []
    if not series:
        gaps.append("سلسلة الواردات السنوية")
    if not rows:
        gaps.append("حصص الموردين")
    if tariff["status"] == "gap":
        gaps.append("الرسم الجمركي المنطبق")
    for label, ind in (("سعر الصرف", fx), ("مؤشرات الحوكمة", wgi), ("مؤشر الأداء اللوجستي", lpi)):
        if ind is None:
            gaps.append(label)
    if not shelf:
        gaps.append("أسعار الرف")
    # P4-4: العدّ واحد في كل مكان — المرشحون لطلب عرض أسعار وحدهم (لا المنافسون ولا المنافذ).
    candidates = sum(e["role"] == "مرشح لطلب عرض أسعار" for e in entities)
    # P5-6: ملاحظات المراجع المتوسطة لإصدارٍ درجته 8–9 تُعلن حدوداً للدراسة.
    for lim in ((dr.get("study_review") or {}).get("delivery") or {}).get("limits") or []:
        gaps.append(lim)
    if candidates < MIN_ENTITIES:
        gaps.append("مستوردون مؤكدون بالاسم")
    return {
        "case": f"{hs}_{iso3}", "live": True,
        "product": {"name_full": product, "short": product_short or product, "hs": hs, "commodity": product,
                    "origin_iso3": "SAU", "origin_ar": "المملكة العربية السعودية", "exporter_type": exporter_type,
                    "segment": segment, "halal_relevant": None, "base_word": product_short or product,
                    "raw_input_word": None},
        "market": {"iso3": iso3, "iso2": iso2, "name_ar": name_ar, "nisba_f": _nisba(iso3)[0],
                   "nisba_m": _nisba(iso3)[1], "capital_port": None},
        "prepared": {"year": today.year, "month": today.month, "collected_on": today.isoformat()},
        "imports": {"source": "UN Comtrade", "source_line": f"تصريحات الاستيراد لدى {name_ar}، قاعدة بيانات UN Comtrade.",
                    "series": series, "unit_value_first": reliable[0]["unit_value"] if reliable else None,
                    "unit_value_last_reliable": reliable[-1]["unit_value"] if reliable else None,
                    "unit_value_year_excluded": excluded[-1] if excluded else None,
                    "last_yoy_pct": None, "gdp_growth_pct": gdp["value"] if gdp else None,
                    "gdp_source": "صندوق النقد الدولي" if gdp and "IMF" in gdp["source"] else (gdp["source"] if gdp else None),
                    "local_producers_word": None},
        "suppliers": {"year": sup_year, "count": sup_count, "saudi_share_pct": saudi, "top": top, "hub_share_trend": None},
        "tariff": {**tariff, "sst_rule": sst_rule, "sst_authority": None, "preferential_note": None, "preferential_status": None},
        "fx": {"currency_ar": None, "currency_short": None, "avg_year": fx["year"] if fx else None,
               "avg_rate": fx["value"] if fx else None, "range_years": None, "range_pct": None,
               "source": "البنك الدولي"},
        "macro": {"year": gdp["year"] if gdp else None, "gdp_growth_pct": gdp["value"] if gdp else None,
                  "inflation_pct": inf["value"] if inf else None},
        "governance": {"available": wgi is not None, "pv_est": wgi["value"] if wgi else None},
        "logistics": {"lpi": lpi["value"] if lpi else None, "lpi_year": lpi["year"] if lpi else None, "sea_days_word": None},
        "demographics": {"muslim_share_pct": None, "census_authority": None, "census_year": None},
        "shelf_prices": {"fx_rate": fx["value"] if fx else None, "fx_year": fx["year"] if fx else None, "rows": shelf,
                         "segment_price_observed": any(r["segment"] == target_seg for r in shelf), "target_segment_word": None, "target_competitor_word": None},
        "requirements": {"rows": req_rows, "exit_text": None,
                         "halal": {"mandatory": halal_mandatory, "authority_short": None, "authority_long": None,
                                   "list_site": None, "official_durations_published": False},
                         "durations_published": False, "quarantine_agent_word": None},
        "entities": {"rows": entities, "excluded_text": excluded_text,
                     "directories": [d["name_ar"] for d in market_directories(iso3)] or None,
                     "importer_candidates": candidates},
        "decision": {"type": decision,
                     "requirements": _requirements_from_gaps(gaps, shelf, candidates),
                     "unit_cost_provided": False,
                     # P3-8: بلا سعر رف من الشريحة — عتبةٌ **مؤقتة** = أعلى سعر مرصود ×
                     # الحد الأعلى لقاعدة التكلفة الواصلة (45%)، مقرّبةً للأدنى؛ قاعدة
                     # تقديرية موسومة، ولا يُبنى عليها إرجاء (القرار من التوليف وحده).
                     "provisional_threshold_usd": threshold_from(shelf)[0],
                     "threshold_provisional": threshold_from(shelf)[1],
                     "rule_low_pct": 50, "rule_high_pct": 60,
                     "landed_low_pct": 40, "landed_high_pct": 45},
        "claims_reported": _merge_claims(
            _knowledge_claims(hs, iso2),
            outlet_claims(_chan, [e["name"] for e in entities])),   # P4-3: جهات اجتازت الحارس فقط
        "gaps": [_gap(g, iso3) for g in gaps],
        "sources": sorted({str(f.get("source")) for m in missions.values() if isinstance(m, dict)
                           for f in (m.get("findings") or []) if isinstance(f, dict) and f.get("source")
                           and f.get("value") is not None}),
    }
