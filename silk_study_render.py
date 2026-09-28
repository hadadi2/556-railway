"""محرك القوالب اللغوية لنمط «دراسة السوق» — deterministic template engine (P0-T).

> النص الثابت من `data/study_templates_ar.yaml` حرفياً؛ الأرقام من
> `silk_study_numbers`؛ نصوص المنتج×السوق من `data/product_knowledge/<hs>_<market>.yaml`
> إن كانت `status: approved`؛ وإلا يُستدعى `llm_fill(slot_id, brief)` (حقن — لا نداء
> شبكي هنا) ويُوسم الناتج للمراجعة. لا فعل اتجاه ولا رقم مكتوبَين في هذه الوحدة.

صيغة الفراغات داخل القوالب:
  {name}            قيمة من السياق كما هي        {name:fmt}   صيغة عرض (silk_study_arabic.fmt)
  {dir:key:أ|ب}      أ إذا كانت إشارة key موجبة وإلا ب   {n:count(معدود صفة, حالة)}
  لـ{x} / بـ{x} / كـ{x}   حرف جر يُدمج بالكلمة (prep)     {k:para_id}   فقرة/شظية من ملف المعرفة
  {c:clause}        جملة فرعية مختارة من `clauses` بحسب مفتاح اختيار
"""
from __future__ import annotations

import functools
import os
import re
from typing import Callable

import yaml

from silk_study_arabic import count, direction, fmt, ordinal_m, prep
from silk_study_numbers import compute

ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(ROOT, "data", "study_templates_ar.yaml")
KNOWLEDGE_DIR = os.path.join(ROOT, "data", "product_knowledge")
EXEMPLARS = os.path.join(ROOT, "data", "study_style_exemplars.json")
LLM_MARK = "<!-- llm:{sid} -->"

_SLOT = re.compile(r"\{([^{}]+)\}")
_PREP = re.compile(r"([لبك])ـ\{([^{}]+)\}")


class StudyRenderError(ValueError):
    pass


def _masc_nisba(nisba_f: str) -> str:
    """«الماليزية» → «الماليزي» (صفة النسبة المذكرة من المؤنثة)."""
    return nisba_f[:-1] if nisba_f.endswith("ة") else nisba_f


@functools.lru_cache(maxsize=8)
def _templates_cached(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_templates(path: str = TEMPLATES) -> dict:
    """نسخة مستقلة من قوالب مكاشة — مستدعٍ يعدّلها لا يسمّم غيره."""
    import copy
    return copy.deepcopy(_templates_cached(path))


def load_knowledge(hs: str, market_code: str) -> dict:
    """ملف المعرفة `<hs>_<market>.yaml` (رمز السوق ISO2 كما سمّاه المالك، أو ISO3)
    إن كان `status: approved`؛ غير ذلك = لا معرفة (النموذج يملأ ويُوسم)."""
    p = os.path.join(KNOWLEDGE_DIR, f"{hs}_{market_code}.yaml")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    return d if d.get("status") == "approved" else {}


REVIEW_FILE = os.path.join(ROOT, "docs", "plans", "STUDY_TEMPLATE_VARIANTS_REVIEW.md")
PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]|TODO|placeholder|يُدرج|<[^>]*>", re.I)


def load_exemplars(path: str = EXEMPLARS) -> dict:
    import copy
    return copy.deepcopy(_exemplars_cached(path))


@functools.lru_cache(maxsize=8)
def _exemplars_cached(path: str) -> dict:
    """نماذج الأسلوب لفراغات (ب)/(ج) — P2-3. غياب الملف = بلا نماذج (لا فشل)."""
    import json
    try:
        with open(path, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def pending_variants(path: str | None = None) -> set[str]:
    """نصوص النسخ التي ما زالت `pending` في ملف المراجعة — لا تُحمَّل بلا إذن صريح."""
    path = path or REVIEW_FILE
    out: set[str] = set()
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("| ") and "| pending" in ln:
                cells = [c.strip() for c in ln.strip().strip("|").split(" | ")]
                if len(cells) >= 3:
                    out.add(cells[2].replace("\\|", "|"))
    return out


# تسميات الفجوات عند سقوط فقرة لغياب فراغها (P1-3 أ: فجوة بيانات → بند في الحدود).
GAP_LABELS = {
    "imports_series": "سلسلة الواردات السنوية", "shelf_prices": "أسعار الرف", "requirements": "المتطلبات الإلزامية في السوق", "entities": "الجهات المرصودة", "plan": "خطة التنفيذ",
    "shape_v_last": "سلسلة الواردات السنوية", "shape_v_first": "سلسلة الواردات السنوية",
    "dec_y_a": "بيانات الكميات المستوردة (الوزن)", "q_share_frac": "بيانات الكميات المستوردة (الوزن)",
    "supplier_count": "عدد الدول المورّدة", "top3_frac": "حصص الموردين", "sup1_name": "حصص الموردين",
    "hhi_lo_100": "مؤشر تركّز الموردين", "tariff": "الرسم الجمركي المنطبق",
    "gdp_growth": "نمو الناتج المحلي الإجمالي", "gdp_source": "نمو الناتج المحلي الإجمالي",
    "uv_first": "متوسط سعر الاستيراد عند الحدود", "uv_last": "متوسط سعر الاستيراد عند الحدود",
    "fx_avg": "سعر الصرف", "fx_cur": "سعر الصرف", "fx_range_pct": "تقلب سعر الصرف", "fx_range_years": "تقلب سعر الصرف",
    "macro_gdp": "مؤشرات الاقتصاد الكلي", "macro_inf": "معدل التضخم", "macro_year": "مؤشرات الاقتصاد الكلي",
    "lpi": "مؤشر الأداء اللوجستي", "port": "ميناء الدخول", "sea_days": "مدة الشحن البحري",
    "muslim_share": "التركيبة الدينية", "census_auth": "التركيبة الدينية",
    "shelf_min": "أسعار الرف", "shelf_max": "أسعار الرف", "shelf_fx": "سعر الصرف", "fx_cur_short": "سعر الصرف",
    "segment_word": "الشريحة المستهدفة", "competitor_word": "الشريحة المستهدفة", "threshold": "عتبة التكلفة الواصلة",
    "sst_rule": "ضريبة المبيعات", "sst_authority": "ضريبة المبيعات", "pref_note": "المعاملة التفضيلية",
    "exit_text": "متطلبات التصدير في المملكة", "halal_long": "جهة اعتماد الحلال", "halal_short": "جهة اعتماد الحلال",
    "quarantine_agent": "مدد التصاريح", "excluded_text": "الجهات المستبعدة",
    "entity_req_ordinal": "متطلب الجهات", "directories_phrase": "أدلة الجهات في السوق", "requirements_inline": "متطلبات القرار",
    "hub_trend_name": "اتجاه حصة مركز إعادة التصدير", "producer1": "المنتجون الإقليميون", "commodity_raw_word": "المادة الخام",
    "market_nisba": "صفة النسبة للسوق (data/market_nisba_l1.csv)", "local_producers_word": "الإنتاج المحلي",
    "نسخة قالب بانتظار اعتماد المالك": "فقرة قالبها بانتظار اعتماد المالك",
    "last_complete_year": "أحدث سنة بيانات مكتملة", "shape_g_first_last": "سلسلة الواردات السنوية",
    "market_nisba_m": "صفة النسبة للسوق (data/market_nisba_l1.csv)", "sources_inline": "قائمة المصادر",
    "shape_y_first": "سلسلة الواردات السنوية", "last_yoy_abs": "نمو الواردات السنوي", "sup_year": "حصص الموردين",
    "hub_frac": "حصة مركز إعادة التصدير", "producers_two_frac": "حصص المنتجين الإقليميين",
}
_ = {
}


_K_GAP_LABEL = "معلومات خاصة بالمنتج في هذه السوق"
_K_GAP_OWNER = "ملف معرفة معتمد للمنتج والسوق"
_DATA_GAP_OWNER = "فريق البحث (سحب لاحق من المصدر)"


def gap_text(g) -> str:
    """P3-3: الفجوة بجهة استكمالها «الفجوة (يستكملها: الجهة)»؛ النص الخام كما هو."""
    if isinstance(g, dict):
        return f"{g['label']} (يستكملها: {g['owner']})" if g.get("owner") else g["label"]
    return str(g)


def _gap_label(g) -> str:
    return g["label"] if isinstance(g, dict) else str(g)


class Renderer:
    def __init__(self, case: dict, knowledge: dict | None = None,
                 llm_fill: Callable[[str, str], str | None] | None = None,
                 templates: dict | None = None, allow_pending: bool = False,
                 review_marks: bool = False, recheck: bool = True):
        self.recheck = recheck
        # وسم `<!-- llm:… -->` للمراجعة الداخلية فقط وبطلب صريح؛ الافتراضي نصٌّ
        # نظيف يصلح للعميل (الدرس 285: الوسم لا يُنزع لاحقاً، لا يُضاف أصلاً).
        self.review_marks = review_marks
        self.allow_pending = allow_pending
        self._pending = set() if allow_pending else pending_variants()
        self.case = case
        self.k = (knowledge or {}).get("paragraphs", {})
        self.llm_fill = llm_fill
        self.t = templates or load_templates()
        self.ctx = self._context()
        self.llm_slots: list[str] = []
        self.gaps: list[str] = []
        self._llm_cache: dict[str, str] = {}   # المرور الثاني لا يعيد نداء الفراغ نفسه

    # ── السياق ─────────────────────────────────────────────────────────────
    def _context(self) -> dict:
        c = self.case
        n = compute(c)
        ctx = dict(n)
        ctx.update({
            "exporter_type": c["product"].get("exporter_type") or "processor_of_imported_input",
            "product_full": c["product"]["name_full"], "product_short": c["product"]["short"],
            "hs": c["product"]["hs"], "origin_ar": c["product"]["origin_ar"], "commodity": c["product"]["commodity"],
            "market": c["market"]["name_ar"], "market_nisba": c["market"]["nisba_f"],
            "prep_year": c["prepared"]["year"], "prep_month": c["prepared"]["month"],
            "last_complete_year": max((r["year"] for r in (c["imports"].get("series") or []) if r.get("complete")), default=None),
            "gdp_growth": c["imports"].get("gdp_growth_pct"), "gdp_source": c["imports"].get("gdp_source"),
            "local_producers_word": c["imports"].get("local_producers_word"),
            "uv_first": c["imports"].get("unit_value_first"), "uv_last": c["imports"].get("unit_value_last_reliable"),
            "uv_excl_year": c["imports"].get("unit_value_year_excluded"),
            "sup_year": (c.get("suppliers") or {}).get("year"),
            "tariff_status": c["tariff"]["status"], "tariff": c["tariff"].get("rate_pct"),
            "sst_rule": c["tariff"].get("sst_rule"), "sst_authority": c["tariff"].get("sst_authority"),
            "pref_note": c["tariff"].get("preferential_note"), "pref_status": c["tariff"].get("preferential_status"),
            "fx_cur": c["fx"]["currency_ar"], "fx_avg": c["fx"]["avg_rate"], "fx_year": c["fx"]["avg_year"],
            "fx_range_years": c["fx"]["range_years"], "fx_range_pct": c["fx"]["range_pct"], "fx_source": c["fx"]["source"],
            "macro_year": c["macro"]["year"], "macro_gdp": c["macro"]["gdp_growth_pct"], "macro_inf": c["macro"]["inflation_pct"],
            "gov_available": c["governance"]["available"],
            "lpi": c["logistics"]["lpi"], "lpi_year": c["logistics"]["lpi_year"], "sea_days": c["logistics"]["sea_days_word"],
            "port": c["market"]["capital_port"],
            "muslim_share": c["demographics"]["muslim_share_pct"], "census_auth": c["demographics"]["census_authority"],
            "census_year": c["demographics"]["census_year"], "halal_relevant": c["product"].get("halal_relevant"),
            "shelf_fx": c["shelf_prices"]["fx_rate"], "shelf_fx_year": c["shelf_prices"]["fx_year"],
            "segment_word": c["shelf_prices"]["target_segment_word"], "competitor_word": c["shelf_prices"]["target_competitor_word"],
            "segment_price_observed": c["shelf_prices"]["segment_price_observed"],
            "halal_mandatory": c["requirements"]["halal"]["mandatory"], "halal_short": c["requirements"]["halal"]["authority_short"],
            "halal_long": c["requirements"]["halal"]["authority_long"], "halal_site": c["requirements"]["halal"]["list_site"],
            "durations_published": c["requirements"]["durations_published"], "quarantine_agent": c["requirements"]["quarantine_agent_word"],
            "exit_text": c["requirements"]["exit_text"],
            "excluded_text": c["entities"]["excluded_text"], "importer_candidates": c["entities"]["importer_candidates"],
            # P4-4: ترتيب متطلب الجهات من قائمة المتطلبات الفعلية لا رقمٌ مكتوب صلباً.
            "entity_req_ordinal": next((ordinal_m(r["id"]) for r in (c.get("decision") or {}).get("requirements") or []
                                        if "جهتين أو ثلاث" in str(r.get("text"))), None),
            "entity_para": ("none" if (c["entities"].get("importer_candidates") or 0) >= 2
                            else "with_excluded" if c["entities"].get("excluded_text") else "no_excluded"),
            "directories_phrase": ("عبر " + " و".join(c["entities"]["directories"])
                                   if c["entities"].get("directories") else None),
            "unit_cost_provided": c["decision"]["unit_cost_provided"], "threshold": c["decision"]["provisional_threshold_usd"],
            "rule_low": c["decision"]["rule_low_pct"], "rule_high": c["decision"]["rule_high_pct"],
            "landed_low": c["decision"]["landed_low_pct"], "landed_high": c["decision"]["landed_high_pct"],
            "hub_name": (n["hub"] or {}).get("name_ar"), "hub_share": (n["hub"] or {}).get("share_pct"),
            "hub_trend": c["suppliers"].get("hub_share_trend"),
            "collected_on": c["prepared"]["collected_on"],
        })
        sh = ctx
        sh["shape_g_abs"] = abs(n["shape_g_first_last"]) if n.get("shape_g_first_last") is not None else None
        ser = c["imports"]["series"]
        if ser:
            mn = min(ser, key=lambda r: r["value_musd"]); mx = max(ser, key=lambda r: r["value_musd"])
            sh["shape_min_year"], sh["shape_min_value"] = mn["year"], mn["value_musd"]
            sh["shape_max_value"] = mx["value_musd"]
        else:
            sh["shape_min_year"] = sh["shape_min_value"] = sh["shape_max_value"] = None
        sh["decision_word_gen"] = {"defer": "الإرجاء", "no_entry": "عدم الدخول", "entry": "الدخول", "conditional": "الدخول المشروط"}[n["decision"]]
        sh["shape_dip_sign"] = (n["shape_dip_value"] - n["shape_v_first"]) if n.get("shape_dip_value") is not None else None
        yrs = [r["year"] for r in c["imports"]["series"]]
        sh["shape_y_prev"] = yrs[-2] if len(yrs) > 1 else None
        sh["last_yoy_abs"] = abs(sh["last_yoy"]) if sh.get("last_yoy") is not None else None
        for key in ("dv", "dp", "dq"):
            v = n.get(f"dec_{key}")
            sh[f"dec_{key}_abs"] = abs(v) if v is not None else None
        sh["dec_reason"] = n.get("dec_reason")
        if n.get("dec_dq") is not None:
            dq = n["dec_dq"]
            sh["q_change_clause"] = ("لم تتغير تقريباً" if abs(dq) < 1 else
                                     (f"ارتفعت بنحو {int(round(abs(dq)))}% فقط" if dq > 0 else f"تراجعت بنحو {int(round(abs(dq)))}%"))
        sh["imports_source_line"] = c["imports"].get("source_line")
        sh["imports_source"] = c["imports"].get("source")
        for i, t in enumerate(c["suppliers"]["top"][:4], 1):
            sh[f"sup{i}_name"], sh[f"sup{i}_share"] = t["name_ar"], t["share_pct"]
        producers = [t for t in c["suppliers"]["top"] if t.get("kind") == "producer"]
        sh["producer1"] = producers[0]["name_ar"] if producers else None
        sh["producer2"] = producers[1]["name_ar"] if len(producers) > 1 else None
        ht = c["suppliers"].get("hub_share_trend") or {}
        for kk, vv in ht.items():
            sh[f"hub_trend_{kk}"] = vv
        sh["hub_trend_name"] = ht.get("name_ar")
        sh["uv_dir"] = ((c["imports"]["unit_value_last_reliable"] - c["imports"]["unit_value_first"])
                        if c["imports"].get("unit_value_first") and c["imports"].get("unit_value_last_reliable") else None)
        sh["fx_cur_short"] = c["fx"].get("currency_short")
        sh["market_nisba_m"] = c["market"].get("nisba_m") or (_masc_nisba(c["market"]["nisba_f"]) if c["market"].get("nisba_f") else None)
        sh["market_nisba_gdp"] = sh["market_nisba_m"]
        sh["product_short_bare"] = c["product"].get("base_word") or c["product"]["short"]
        sh["commodity_raw_word"] = c["product"].get("raw_input_word") or c["product"]["commodity"]
        sh["macro_gdp_abs"] = abs(sh["macro_gdp"]) if sh.get("macro_gdp") is not None else None
        sh["has_k_world_price"] = "s1_decomp.world_price_note" in self.k
        sh["has_k_gov_stability"] = "s7_gov.stability" in self.k
        g, inf = sh.get("macro_gdp"), sh.get("macro_inf")
        sh["inflation_band"] = ("low" if (g is not None and inf is not None and g > 0 and inf <= 3.5)
                                else "high")
        reqs = [q["text"] for q in c["decision"]["requirements"]]
        sh["requirements_inline"] = "؛ ".join([reqs[0]] + ["و" + q for q in reqs[1:]]) if reqs else ""
        sh["sources_inline"] = "؛ ".join(c.get("sources") or []) or "لم يُسنَد رقم إلى مصدر في هذه النسخة"
        sh["gaps_inline"] = "؛ ".join(gap_text(g) for g in c.get("gaps") or []) or "لا فجوات معلنة"
        eq = [r for r in c["shelf_prices"]["rows"] if r.get("equivalent") and r.get("usd_kg")]
        ctx["shelf_min"] = min(r["usd_kg"] for r in eq) if eq else None
        ctx["shelf_max"] = max(r["usd_kg"] for r in eq) if eq else None
        ctx["has_nonequivalent"] = any(not r.get("equivalent") for r in c["shelf_prices"]["rows"])
        ctx["has_shelf_rows"] = bool(c["shelf_prices"]["rows"])
        ctx["has_requirement_rows"] = bool((c.get("requirements") or {}).get("rows"))
        ctx["has_entity_rows"] = bool((c.get("entities") or {}).get("rows"))
        ht = ctx["hub_trend"]
        if ht:
            ctx["hub_trend_dir"] = ht["share_b"] - ht["share_a"]
            ctx["hub_trend_dir_c"] = ht["share_c"] - ht["share_b"] if ht.get("share_c") is not None else None
            ctx["hub_trend_sig"] = abs(ctx["hub_trend_dir"]) >= 5
        return ctx

    # ── التعبئة ────────────────────────────────────────────────────────────
    def _val(self, key: str):
        if key not in self.ctx:
            raise StudyRenderError(f"فراغ غير معروف: {key}")
        v = self.ctx[key]
        if v is None:
            raise StudyRenderError(f"قيمة غائبة للفراغ: {key}")
        return v

    def _slot(self, expr: str) -> str:
        if expr.startswith("dir:"):
            _, key, alts = expr.split(":", 2)
            up, down = alts.split("|", 1)
            return direction(float(self._val(key)), up, down)
        if expr.startswith("k:"):
            sid = expr[2:]
            if sid in self.k:
                return str(self.k[sid])
            return self._llm(sid)
        if expr.startswith("c:"):
            return self._clause(expr[2:])
        m = re.match(r"^(\w+):count\(([^,]+),\s*(\w+)\)$", expr)
        if m:
            return count(int(self._val(m.group(1))), m.group(2).strip(), m.group(3))
        if ":" in expr:
            key, spec = expr.split(":", 1)
            return fmt(self._val(key), spec)
        return str(self._val(expr))

    def _slot_ok(self, txt: str, sid: str | None = None) -> str | None:
        """فحص حتمي لنص فراغ النموذج (P1-12، P5-1): نائب، رقم لم يُمرَّر، ثم قواعد linter
        الجُمَلية (محظور، مصطلح مغاير/عارٍ، تعارض ادعاء، نفع المصدّر، سعر الحدود، الميزة)."""
        if PLACEHOLDER_RE.search(txt):
            return "عنصر نائب"
        allowed = {str(v) for v in self.ctx.values() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        for num in re.findall(r"\d+(?:[.,]\d+)?", txt):
            if num not in allowed and num.replace(",", "") not in allowed and not any(num == f"{v:g}" for v in
                    (x for x in self.ctx.values() if isinstance(x, (int, float)) and not isinstance(x, bool))):
                return f"رقم لم يُمرَّر: {num}"
        # P5-1: فحوص الأسلوب والاتساق نفسها التي يطبّقها linter على الدراسة كاملة.
        if not self.recheck:
            return None        # نص مخزَّن اجتاز الفحوص عند ملئه — التصدير لا يُسقطه بقواعد أحدث
        try:
            from silk_study_claims import build_claims
            from silk_study_linter import slot_violations
            v = slot_violations(txt, build_claims(self.case),
                                self.case["product"].get("exporter_type"), sid)
        except Exception as e:  # noqa: BLE001 — عطل الفحص الإضافي لا يُسقط التصيير
            import logging
            logging.getLogger(__name__).warning("slot_violations skipped: %s", e)
            v = []
        return f"{v[0]['rule']}: {v[0]['detail']}" if v else None

    def _llm(self, sid: str) -> str:
        """فراغ (ب)/(ج) بلا معرفة معتمدة: نداء واحد، فإن فشل الفحص يُعاد **مرة واحدة**
        بالملاحظة، ثم يُحذف الادعاء ويُعلن فجوةً (لا يُوقف التقرير)."""
        briefs = self.t.get("llm_briefs") or {}
        if sid not in briefs:
            # شظية كلمة/عبارة داخل جملة (بلا موجز): لا تُرسل للنموذج، ولا تُترك
            # فارغة فتنكسر الجملة — الفقرة كلها تسقط وتُعلن فجوةً بتسمية مقروءة.
            raise StudyRenderError(f"قيمة غائبة للفراغ: k:{sid}")
        if not self.llm_fill:
            self.gaps.append(sid)
            return ""
        if sid not in self._llm_cache:
            from silk_style_contract import study_slot_prompt
            brief = study_slot_prompt(briefs[sid], load_exemplars().get(sid))
            self._llm_cache[sid] = ""
            note = ""
            for _attempt in range(2):
                txt = self.llm_fill(sid, brief + note)
                if not txt:
                    break
                problem = self._slot_ok(txt, sid)
                if problem is None:
                    self._llm_cache[sid] = txt
                    break
                note = f" — أعد الصياغة: {problem}"
        txt = self._llm_cache[sid]
        if not txt:
            self.gaps.append(sid)
            return ""
        self.llm_slots.append(sid)
        return f"{LLM_MARK.format(sid=sid)}{txt}" if self.review_marks else txt

    def _gate(self, raw: str) -> None:
        if raw and raw.strip() in self._pending:
            raise StudyRenderError(f"نسخة غير معتمدة (pending في ملف المراجعة): {raw[:40]}…")

    def fill(self, text: str) -> str:
        self._gate(text)
        text = _PREP.sub(lambda m: prep(m.group(1), self._slot(m.group(2))), text)
        return _SLOT.sub(lambda m: self._slot(m.group(1)), text)

    def _clause(self, name: str) -> str:
        spec = self.t["clauses"][name]
        key = self._select(spec)
        variants = spec["variants"]
        if key not in variants:
            raise StudyRenderError(f"لا نسخة {key!r} للجملة {name}")
        return self.fill(variants[key] or "")

    def _select(self, spec: dict) -> str:
        sel = spec["select"]
        if isinstance(sel, str):
            v = self.ctx.get(sel)
            if isinstance(v, bool):
                return "yes" if v else "no"
            return str(v)
        # قاعدة مركبة: قائمة [شرط → مفتاح] بالترتيب؛ الشرط تعبير بسيط على السياق
        for rule in sel:
            if self._cond(rule["when"]):
                return rule["use"]
        raise StudyRenderError("لا شرط منطبق")

    def _cond(self, expr: str) -> bool:
        if expr == "else":
            return True
        m = re.match(r"^(\w+)\s*(==|!=|>=|<=|>|<)\s*(.+)$", expr)
        if not m:
            return bool(self.ctx.get(expr))
        k, op, raw = m.groups()
        v = self.ctx.get(k)
        rhs: object = raw.strip()
        if rhs in ("true", "false"):
            rhs = rhs == "true"
        elif rhs == "none":
            rhs = None
        else:
            try:
                rhs = float(rhs)
            except ValueError:
                rhs = str(rhs).strip("'\"")
        if op == "==":
            return v == rhs
        if op == "!=":
            return v != rhs
        if v is None:
            return False
        return {">": v > rhs, "<": v < rhs, ">=": v >= rhs, "<=": v <= rhs}[op]

    # ── الجداول ────────────────────────────────────────────────────────────
    def _table(self, spec: dict) -> str:
        cols = spec["columns"]
        rows = self._rows(spec["rows"])
        out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for r in rows:
            out.append("| " + " | ".join(str(x) for x in r) + " |")
        return "\n".join(out)

    def _rows(self, source: str) -> list[list[str]]:
        c = self.case
        if source == "imports_series":
            return [[str(r["year"]), f"{r['value_musd']:.1f}" + ("" if r.get("complete", True) else " (أولي)")]
                    for r in c["imports"]["series"]]
        if source == "shelf_prices":
            return [[r["product"], r["segment"], r["price"], r["source"]] for r in c["shelf_prices"]["rows"]]
        if source == "requirements":
            return [[r["item"], r["authority"], r["party"], r["verified_at"] or "يُستوضح"] for r in c["requirements"]["rows"]]
        if source == "entities":
            return [[r["name"], r["desc"], r["role"]] for r in c["entities"]["rows"]]
        if source == "plan":
            return self._plan_rows()
        raise StudyRenderError(f"مصدر جدول غير معروف: {source}")

    def _plan_rows(self) -> list[list[str]]:
        rows = []
        if not self.case["decision"]["unit_cost_provided"]:
            rows.append(["الأسبوع 1", "إدخال تكلفة إنتاج الكيلوغرام ووزن العبوة", "المتطلب الأول", "المنشأة"])
        krows = self.k.get("s9_plan_rows") or []
        early = [r for r in krows if r[0].startswith("الأسبوع")]
        late = [r for r in krows if not r[0].startswith("الأسبوع")]
        rows += early
        rows.append(["الأسابيع 3–4", "إعادة تقييم التوصية على ضوء الأرقام الفعلية", "—", "—"])
        rows += late
        rows.append(["الأسابيع 9–12", "متابعة المبيعات الشهرية والتحقق من الموسمية قبل الشحنة الثانية", "—", "المبيعات"])
        return rows

    # ── التجميع ────────────────────────────────────────────────────────────
    def render(self) -> str:
        """تعبئة مزدوجة: مرورٌ أول يجمع الفجوات، ثم مرور ثانٍ بقائمة الحدود المكتملة."""
        self.missing: list[str] = []
        self._render_once()
        known = {_gap_label(g) for g in self.case.get("gaps") or []}
        extra = []
        for k in dict.fromkeys(self.missing):
            if k.startswith("k:"):
                extra.append({"label": _K_GAP_LABEL, "owner": _K_GAP_OWNER})
            else:
                extra.append({"label": GAP_LABELS.get(k, k), "owner": _DATA_GAP_OWNER})
        briefs = self.t.get("llm_briefs") or {}
        extra += [{"label": briefs.get(sid, _K_GAP_LABEL), "owner": _K_GAP_OWNER}
                  for sid in dict.fromkeys(self.gaps)]
        seen: set = set()
        extra = [g for g in extra if g["label"] not in known
                 and not (g["label"] in seen or seen.add(g["label"]))]
        if extra:
            base = list(self.case.get("gaps") or []) + extra
            self.ctx["gaps_inline"] = "؛ ".join(gap_text(g) for g in base)
        self.missing, self.gaps, self.llm_slots = [], [], []
        return self._render_once()

    def _render_once(self) -> str:
        out: list[str] = []
        for block in self.t["blocks"]:
            try:
                piece = self._block(block)
            except StudyRenderError as e:
                msg = str(e)
                if msg.startswith("قيمة غائبة للفراغ: ") or msg.startswith("فراغ غير معروف: "):
                    self.missing.append(msg.split(": ", 1)[1])
                    continue                       # الفقرة تسقط والفجوة تُعلن
                if msg.startswith("نسخة غير معتمدة"):
                    self.missing.append("نسخة قالب بانتظار اعتماد المالك")
                    continue                       # لا نص غير معتمد يصل العميل
                raise
            if piece:
                out.append(piece)
        md = "\n\n".join(out) + "\n"
        leak = PLACEHOLDER_RE.search(re.sub(r"<!-- llm:[^>]*-->", "", md))
        if leak:
            raise StudyRenderError(f"عنصر نائب في المخرج: {leak.group(0)!r}")
        return md

    def _block(self, block: dict) -> str | None:
        if True:
            kind = block.get("type", "para")
            if "when" in block and not self._cond(block["when"]):
                return None
            if kind == "heading":
                return self.fill(block["text"])
            if kind == "rule":
                return "---"
            if kind == "table":
                rows = self._rows(block["rows"])
                if not rows:
                    self.missing.append(block["rows"])
                    return None
                return self._table(block)
            if kind == "para":
                txt = block.get("text")
                if txt is None:
                    key = self._select(block)
                    txt = block["variants"][key]
                if txt is None:
                    return None
                return self.fill(txt).strip() or None
            if kind == "list":
                return self.fill(block["text"])
            raise StudyRenderError(f"نوع كتلة غير معروف: {kind}")


def render_study(case: dict, knowledge: dict | None = None, llm_fill=None,
                 review_marks: bool = False) -> str:
    return Renderer(case, knowledge, llm_fill, review_marks=review_marks).render()
