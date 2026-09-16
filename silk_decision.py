"""محرك قرار دخول السوق — Silk market-entry decision engine (Stage 4, §8).

يستهلك حصراً حزمة وكلاء البحث المتحقَّق منها (silk_research §4b) عبر
`bundle["pillar_inputs"]` — لا نداء خارجياً واحداً هنا؛ محرك حسابي نقي قابل
للاختبار، كل عمود يطبع أساسه (المعادلة + المدخلات المستخدمة).

Score = w1·جاذبية السوق + w2·(1 − شدة المنافسة) + w3·الملاءمة التنظيمية
        + w4·هامش الربحية + w5·أمان السوق (المخاطر) — كل عمود ∈ [0,1].

توجيه المالك: تُرقّى المخاطر من بوابةٍ فقط إلى **عمودٍ خامسٍ موزون** — الاستقرار
السياسي/جودة التنظيم/الأداء اللوجستي/تقلّب الصرف ترفع أو تخفض الدرجة تناسبيًّا،
مع إبقاء بوابة الخطر الحرج (PV<−1.5) تقلب القرار NO-GO فوق العمود.

خيارا الأوزان (بوابة GATE 3 — قرار المالك يحدد الافتراضي النهائي):
  A (خطة §8):        سوق 0.25 · منافسة 0.20 · تنظيمي 0.15 · ربحية 0.25 · مخاطر 0.15
  B (تنظيمي مثقّل):   سوق 0.20 · منافسة 0.15 · تنظيمي 0.30 · ربحية 0.20 · مخاطر 0.15
كلا المجموعين يُحسبان دائماً ويظهران في المخرجات؛ SILK_DECISION_WEIGHTS يختار
المعتمد (الافتراضي A إلى حين قرار البوابة).

القواعد (§8): GO عند score ≥ 0.65 وثقة ≥ 0.6؛ NO-GO تحت 0.45 أو عند بوابة خطر
حرجة؛ وإلا CONDITIONAL-GO وشروطه = الأعمدة الضعيفة/الغائبة. عمود غائب لا
يُخمَّن: الأوزان تُعاد تسويتها والفجوة تصير شرطاً — لا اختلاق (المبدأ التأسيسي).
"""
from __future__ import annotations

import logging
import math
import os

log = logging.getLogger(__name__)

SCHEMA = "silk.decision/v1"

WEIGHT_OPTIONS: dict[str, dict[str, float]] = {
    "A": {"market": 0.25, "competition": 0.20, "regulatory": 0.15,
          "profit": 0.25, "risk": 0.15},
    "B": {"market": 0.20, "competition": 0.15, "regulatory": 0.30,
          "profit": 0.20, "risk": 0.15},
}
_N_PILLARS = len(next(iter(WEIGHT_OPTIONS.values())))   # عدد الأعمدة (٥ الآن)

# اسم عرض عربي قصير لكل خيار أوزان (قرار المالك، الطبقة ٨) — يحل محل رمز
# المفتاح الخام A/B على وجه التقرير؛ المفتاح A/B نفسه يبقى دون تغيير في
# WEIGHT_OPTIONS/SILK_DECISION_WEIGHTS (سطح API مستقر، لا تغيير بنيوي).
_WEIGHT_LABEL_AR: dict[str, str] = {"A": "الأوزان القياسية",
                                    "B": "الأوزان التنظيمية المُثقّلة"}

_GO, _NOGO = 0.65, 0.45          # عتبات §8
_MIN_CONF_GO = 0.60


def _min_scored_pillars() -> int:
    """الحدّ الأدنى من الأعمدة المحسوبة قبل أيّ درجةٍ موزونة — البند 2 من
    أمر إصلاح المحرّك (تقريرا #10/#11: «درجة موزونة 84%» بعمودٍ واحد و«26%»
    بعمودين — متوسّطٌ موزون على أوزانٍ فارغة رقمٌ بلا معنى). الافتراض 3/5؛
    `SILK_MIN_SCORED_PILLARS` للمعايرة بلا كود."""
    try:
        # سقفٌ علويّ أيضاً (مراجعة §58): قيمةٌ فوق عدد الأعمدة (خطأ إدخال)
        # كانت تُطفئ المحرّكَ كلياً للأبد بـ«الغائب: —» فارغة.
        return min(_N_PILLARS,
                   max(1, int(os.environ.get("SILK_MIN_SCORED_PILLARS", "3"))))
    except ValueError:
        return 3

_AR = {"market": "جاذبية السوق", "competition": "شدة المنافسة",
       "regulatory": "الملاءمة التنظيمية", "profit": "هامش الربحية",
       "risk": "أمان السوق (المخاطر)"}

# ── الموجة Z · البند Z-04 — لا معرّفٍ داخليٍّ في نصٍّ يقرؤه إنسان ─────────
# سطرُ الشرط كان يطبع مفاتيحَ المكوّنات الخام: «عمود أمان السوق غائب
# (political_stability, regulatory_quality, logistics, fx_stability)». القارئُ
# لا يعرف ما هي، ولا يستطيع إغلاقَ فجوةٍ لا يفهم اسمَها — والشرطُ موجودٌ
# أصلاً ليقول له **ماذا يفعل**. البنيةُ (`pillars[...]["missing"]`) تبقى
# بمفاتيحها كما هي للمستهلك الآلي؛ التعريبُ للنصّ وحدَه.
_PART_AR = {
    "tam_log": "حجم واردات السوق", "cagr": "معدّل نموّ الواردات",
    "income": "دخل الفرد", "saudi_momentum": "حصّة السعودية الحالية",
    "hhi": "تركّز الموردين", "top_share": "حصّة المورّد الأكبر",
    "named_density": "منافسون مرصودون بالاسم",
    "tariff": "التعريفة الجمركية", "legibility": "وضوح قائمة الاشتراطات",
    "margin": "هامش السعر عند الحدود", "price_position": "موقع سعرك مقابل السوق",
    "political_stability": "الاستقرار السياسي",
    "regulatory_quality": "جودة التنظيم", "logistics": "أداء اللوجستيات",
    "fx_stability": "استقرار العملة",
}


def _parts_ar(keys) -> str:
    """أسماءُ المكوّنات بلغةِ قارئ — مفتاحٌ غيرُ مُعرَّب يُترك كما هو لا يُخفى."""
    return "، ".join(_PART_AR.get(str(k), str(k)) for k in (keys or []))


# ── الموجة Z · البند Z-06 — مرايا إنجليزية للأسماء نفسها ─────────────────
# أعمدةُ القرار تصل الآن **تقرير العميل** (لم تكن تصله إطلاقاً — قياسٌ في
# `docs/WAVE_Z_AUDIT.md`)، وتقريرُ العميل قد يكون إنجليزياً. النصّان مكتوبان
# أصالةً في اللغتين لا مترجَمين آلياً (البند ٤ في LAW + C9).
_EN = {"market": "Market attractiveness", "competition": "Competitive intensity",
       "regulatory": "Regulatory fit", "profit": "Margin headroom",
       "risk": "Market safety (risk)"}
_PART_EN = {
    "tam_log": "market import size", "cagr": "import growth rate",
    "income": "income per person", "saudi_momentum": "current Saudi share",
    "hhi": "supplier concentration", "top_share": "largest supplier's share",
    "named_density": "competitors observed by name",
    "tariff": "applied tariff", "legibility": "clarity of the requirements list",
    "margin": "price headroom at the border",
    "price_position": "your price against the market",
    "political_stability": "political stability",
    "regulatory_quality": "regulatory quality", "logistics": "logistics performance",
    "fx_stability": "currency stability",
}


def pillar_label(name: str, lang: str = "ar") -> str:
    """اسمُ العمود بلغةِ التقرير — مصدرٌ واحد يستهلكه كلُّ عارض."""
    src = _EN if str(lang).lower().startswith("en") else _AR
    return src.get(str(name), str(name))


def part_labels(keys, lang: str = "ar") -> str:
    """أسماءُ المكوّنات الناقصة بلغةِ التقرير، مفصولةً بفاصلةِ تلك اللغة."""
    en = str(lang).lower().startswith("en")
    src, sep = (_PART_EN, ", ") if en else (_PART_AR, "، ")
    return sep.join(src.get(str(k), str(k)) for k in (keys or []))


def pillar_strength(name: str, value: object) -> "float | None":
    """مساهمةُ العمود في الدرجة كنسبةٍ من ١ — **بنفس تحويل `_score` حرفياً**.

    عمودُ المنافسة يُستهلَك مقلوباً (شدّةٌ أقلّ = مساهمةٌ أعلى)؛ عرضُ قيمته
    الخام كـ«قوّة» كان يقلب المعنى على القارئ (نفس عائلة العطل الذي أصلحه
    `counter_case` في هذه الموجة).
    """
    if not isinstance(value, (int, float)):
        return None
    v = float(value)
    return round(1.0 - v if name == "competition" else v, 3)


def _pct(x: object) -> str:
    """كسرٌ 0–1 كنسبةٍ بشرية — الموجة Z (Z-07).

    التعليقُ فوق سطر «لماذا» يقول منذ المرحلة ٥ «لا كسرَ عشريٍّ خام على وجه
    التقرير»، والسطرُ نفسُه كان يطبع `0.31`. والقياسُ أثبت وصولَه فعلياً إلى
    غلاف تقرير العميل بعد أن صار حكمُ المحرّك هو المُقدَّم (Z-01) — فسدُّ
    التسريب لازمٌ عند المنشأ لا في العارض.
    """
    # الصنف ٣: النسبةُ من المُنسِّق الواحد — صفرُ تغييرٍ في المخرَج (كسرٌ
    # 0–1 × 100 مقرَّباً لعددٍ صحيح) بمصدرٍ واحد للقاعدة.
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return "—"
    from silk_narrative import fmt_pct
    return fmt_pct(round(float(x) * 100), dp=0)


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _conf_phrase(c: object) -> str:
    """ثقة بصيغة بشرية على وجه التقرير — silk_narrative.confidence_phrase
    (استيراد كسول: الوحدة تبقى مستوردة بلا تبعيات عرض عند فشل غير متوقع)."""
    try:
        from silk_narrative import confidence_phrase
        return confidence_phrase(c)
    except Exception:  # noqa: BLE001 — صياغة تجميلية لا شرط حساب
        return str(c)


def _mean_available(parts: dict[str, float | None]) -> tuple[float | None, list]:
    """متوسط المكوّنات المتاحة + قائمة الغائبة — never a guessed component."""
    have = {k: v for k, v in parts.items() if v is not None}
    missing = [k for k, v in parts.items() if v is None]
    return (round(sum(have.values()) / len(have), 3) if have else None, missing)


# ── الأعمدة الأربعة · the four pillars (كلٌّ يطبع أساسه) ─────────────────────

def _pillar_market(pi: dict) -> dict:
    """جاذبية السوق — حجم (لوغاريتمي) + نمو + دخل + زخم الحصة السعودية.

    مؤشر النشاط المثلَّث (§7 المرحلة ٢) يُستهلَك **فقط** عند غياب tam_log —
    بديل جزئي 0..1 غير دولاري عند فجوة TAM الرسمية، لا يُضاف فوق tam_log
    (لا ازدواج قياس السوق مرتين بمصدرين مختلفي الطبيعة).
    """
    tam, cagr = pi.get("tam_usd"), pi.get("import_cagr_pct")
    gdp, sau = pi.get("gdp_per_capita_usd"), pi.get("saudi_share_pct")
    tam_log = _clip(math.log10(tam) / 9) if tam and tam > 0 else None
    activity_idx = pi.get("market_activity_index")
    parts = {
        "tam_log": tam_log if tam_log is not None else (
            _clip(activity_idx) if activity_idx is not None else None),
        "cagr": _clip((cagr + 10) / 40) if cagr is not None else None,
        "income": _clip(gdp / 50_000) if gdp else None,
        "saudi_momentum": _clip(sau / 20) if sau is not None else None,
    }
    v, missing = _mean_available(parts)
    basis = ("متوسط المتاح من: log10(TAM)/9 (سقف 10^9$)، "
            "(CAGR+10)/40 (−10%→0، +30%→1)، دخل الفرد/50k$، "
            "الحصة السعودية/20%")
    if tam_log is None and activity_idx is not None:
        basis += ("؛ TAM الرسمي غائب — استُبدل بمؤشر النشاط المثلَّث "
                  "(Maps/Trends، مُقدَّر بثقة مسقوفة 0.5)")
    return {"value": v, "components": parts, "missing": missing, "basis": basis}


def _pillar_competition(pi: dict) -> dict:
    """شدة المنافسة — HHI + حصة المورّد الأكبر + كثافة الشركات المرشّحة."""
    hhi, top = pi.get("hhi"), pi.get("top_supplier_share_pct")
    n = pi.get("named_company_count")
    # الموجة 2ب: HHI يصل على المقياس الموحّد 0–10000 (كان 0–1) — المقام
    # المعياري = 2×عتبة التركّز القانونية (5000 ≡ 0.5 القديمة حرفياً).
    from silk_economics import HHI_HIGH_CONCENTRATION
    parts = {
        "hhi": (_clip(hhi / (2.0 * HHI_HIGH_CONCENTRATION))
                if hhi is not None else None),
        "top_share": _clip(top / 100) if top is not None else None,
        "named_density": _clip(n / 10) if n is not None else None,
    }
    v, missing = _mean_available(parts)
    # البند 1 (أمر إصلاح المحرّك): المهيمنُ سعوديّ ⇒ علمٌ مستقل يصل القرارَ
    # والكاتبَ كما هو — **لا يُعدِّل الدرجة**: الدرجة تقيس انغلاقَ السوق على
    # داخلٍ جديد، والدفاعُ عن حصةٍ قائمة منطقٌ تجاريّ مختلف يُصاغ نصاً.
    incumbent = pi.get("incumbent_is_self")
    basis = ("متوسط المتاح من: HHI مقسوماً على 5000، وحصة المورّد "
             "الأكبر مقسومةً على 100، وعدد المرشّحين بالاسم مقسوماً "
             "على 10 — الدرجة المستهلكة في المجموع هي (1 − الشدة)")
    if incumbent:
        basis += ("؛ المورّد المهيمن سعوديّ — منطق الدخول الفعلي دفاعُ حصةٍ "
                  "قائمة عبر القناة القائمة (علمٌ مستقل لا يعدّل الدرجة)")
    # PR B §B10 (بلاغ تحليل ٧): «حصة الأكبر/100» كان يُقرأ رقماً مستقلاً
    # («المؤشرات المساهمة: 100») حين يخلط الكاتب المقامَ المعياريّ بعدّاد
    # المؤشرات. الصياغة «مقسومةً على» صراحةً فلا يُلتقَط 100/0.5/10 كقيمة.
    return {"value": v, "components": parts, "missing": missing,
            "incumbent_is_self": incumbent,
            "basis": basis}


def _pillar_regulatory(pi: dict) -> dict:
    """الملاءمة التنظيمية — تعريفة منخفضة + وضوح الاشتراطات؛ بوابة الأهلية تُخفّض."""
    tariff, req = pi.get("tariff_applied_pct"), pi.get("entry_requirements_count")
    gate = pi.get("eligibility_gate")
    parts = {
        "tariff": _clip(1 - tariff / 30) if tariff is not None else None,
        "legibility": _clip(req / 8) if req is not None else None,
    }
    v, missing = _mean_available(parts)
    gated = bool(gate) and v is not None
    if gated:  # بوابة أهلية أمامية (EU 2017/625): سقف 0.3 حتى تُعبَر — قاعدة معلنة
        v = round(min(v, 0.3), 3)
    return {"value": v, "components": parts, "missing": missing,
            "eligibility_gate": bool(gate) if gate is not None else None,
            "basis": "متوسط المتاح من: (1 − تعريفة/30%)، وضوح القائمة (بنود/8)"
                     + ("؛ بوابة أهلية مفتوحة ⇒ سقف 0.3 حتى اعتماد المنشأة"
                        if gated else "")}


def _pillar_profit(pi: dict) -> dict:
    """هامش الربحية — هامش عند الحدود + موقع سعر الصادر السعودي مقابل السوق."""
    margin = pi.get("margin_at_border_pct")
    uv, sau_uv = pi.get("border_unit_value_usd_kg"), \
        pi.get("saudi_border_unit_value_usd_kg")
    ratio = (sau_uv / uv) if (uv and sau_uv) else None
    parts = {
        "margin": _clip(margin / 40) if margin is not None else None,
        # نسبة سعرك الحدودي لمتوسط السوق: 0.5→1.0 (منافس جداً)، 1.5→0.
        "price_position": _clip(1.5 - ratio) if ratio is not None else None,
    }
    v, missing = _mean_available(parts)
    return {"value": v, "components": parts, "missing": missing,
            "basis": "متوسط المتاح من: الهامش/40%، الموقع السعري "
                     "(1.5 − سعرك/متوسط السوق)"}


def _pillar_risk(pi: dict) -> dict:
    """أمان السوق — استقرار سياسي + جودة تنظيم + أداء لوجستي − تقلّب صرف.

    توجيه المالك: المخاطر عمودٌ موزون لا بوابةٌ فقط. أعلى = أأمن، ويُستهلَك مباشرةً
    في المجموع (لا معكوساً كالمنافسة). بوابة الخطر الحرج (PV<−1.5 في decide) تبقى
    منفصلةً وتقلب القرار NO-GO فوق هذا العمود — بوابةٌ وعمودٌ معًا لا أحدهما.
    مقاييس WGI في [−2.5, +2.5] ⇒ (x+2.5)/5؛ LPI في [1,5] ⇒ (LPI−1)/4.
    """
    pv, rq = pi.get("political_stability_wgi"), pi.get("regulatory_quality_wgi")
    lpi, fx = pi.get("logistics_lpi"), pi.get("fx_volatility_pct")
    parts = {
        "political_stability": _clip((pv + 2.5) / 5) if pv is not None else None,
        "regulatory_quality": _clip((rq + 2.5) / 5) if rq is not None else None,
        "logistics": _clip((lpi - 1) / 4) if lpi is not None else None,
        "fx_stability": _clip(1 - fx / 20) if fx is not None else None,
    }
    v, missing = _mean_available(parts)
    return {"value": v, "components": parts, "missing": missing,
            "basis": "متوسط المتاح من: (استقرار سياسي WGI+2.5)/5، (جودة تنظيم "
                     "WGI+2.5)/5، (LPI−1)/4، (1 − تقلّب الصرف/20%) — أعلى=أأمن"}


# ── سجل المخاطر · rule-derived risk register (كل بند بدليله) ─────────────────

def _risk_register(pi_risk: dict, coverage: float) -> list[dict]:
    R: list[dict] = []
    hhi = pi_risk.get("supplier_concentration_hhi")
    # الموجة 2ب: عتبة المقياس الموحّد ⇔ 0.25 القديمة حرفياً — من المصدر الواحد.
    from silk_economics import hhi_is_high
    if hhi_is_high(hhi):
        R.append({"risk": "تركّز مصادر التوريد", "severity": "متوسطة",
                  "evidence": f"HHI={hhi} > 2500 (كومتريد، مقياس 0–10000)"})
    fx = pi_risk.get("fx_volatility_pct")
    if fx is not None and fx > 5:
        R.append({"risk": "تقلب العملة", "severity": "متوسطة",
                  "evidence": f"معامل اختلاف الصرف {fx}% > 5% (World Bank)"})
    pv = pi_risk.get("political_stability_wgi")
    if pv is not None and pv < -0.5:
        R.append({"risk": "استقرار سياسي منخفض", "severity":
                  "عالية" if pv < -1.5 else "متوسطة",
                  "evidence": f"WGI PV.EST={pv} (World Bank)"})
    if coverage < 0.6:
        R.append({"risk": "تغطية بيانات منخفضة", "severity": "متوسطة",
                  "evidence": f"تغطية الوكلاء {round(100 * coverage)}% < 60% — "
                              "القرار مشروط باكتمالها"})
    return R


# ── القرار · decide() ────────────────────────────────────────────────────────

def decide(bundle: dict, weights_option: str | None = None) -> dict:
    """قرار موزون من حزمة البحث — deterministic, explainable, never fabricates.

    bundle: مخرجات ResearchOrchestrator.run_market (§4b). يعيد قاموس قرار كامل:
    verdict/score/confidence + الأعمدة بأساسها + كلا خياري الأوزان + الشروط
    والمخاطر والخطوات الأولى. عمود غائب => إعادة تسوية + شرط، لا تخمين.
    """
    opt = (weights_option or os.environ.get("SILK_DECISION_WEIGHTS", "A")
           ).strip().upper()
    if opt not in WEIGHT_OPTIONS:
        opt = "A"
    pi = bundle.get("pillar_inputs") or {}
    coverage = float(bundle.get("coverage") or 0.0)

    pillars = {"market": _pillar_market(pi.get("market_attractiveness") or {}),
               "competition": _pillar_competition(
                   pi.get("competition_intensity") or {}),
               "regulatory": _pillar_regulatory(pi.get("regulatory_fit") or {}),
               "profit": _pillar_profit(pi.get("profitability") or {}),
               "risk": _pillar_risk(pi.get("risk") or {})}

    def _score(weights: dict[str, float]) -> tuple[float | None, list[str]]:
        """المجموع الموزون على الأعمدة المتاحة — إعادة تسوية معلنة للأوزان."""
        contrib, wsum, missing = 0.0, 0.0, []
        for name, w in weights.items():
            v = pillars[name]["value"]
            if v is None:
                missing.append(name)
                continue
            if name == "competition":
                v = 1.0 - v  # الدرجة = عكس الشدة (§8)
            contrib += w * v
            wsum += w
        if wsum == 0:
            return None, missing
        return round(contrib / wsum, 3), missing

    scores = {name: _score(w)[0] for name, w in WEIGHT_OPTIONS.items()}
    score, missing_pillars = _score(WEIGHT_OPTIONS[opt])

    # الثقة = تغطية الوكلاء × نسبة الأعمدة المحسوبة (معلنة الأساس، لا رقم حدسي).
    pillar_frac = (_N_PILLARS - len(missing_pillars)) / _N_PILLARS
    # الموجة Z (Z-08، حارسٌ لا تغييرُ سلوك): `coverage` نسبةٌ في كلّ مُنادٍ
    # مشحون (`silk_deep_pillars.coverage_of` و`silk_research`)، فالتقييدُ هنا
    # لا يمسّ أيّ مخرجٍ قائم — لكنّ مُنادياً مستقبلياً بقيمةٍ خارج المدى كان
    # سيُنتِج «ثقة 300%» على وجه تقرير عميل. القيدُ عند المستهلك لا عند كلّ
    # مُنادٍ: مصدرٌ واحد للصيغة، حارسٌ واحد لها.
    confidence = round(_clip(coverage) * pillar_frac, 2)

    risk_pi = pi.get("risk") or {}
    critical = bool(risk_pi.get("critical_risk"))
    risks = _risk_register(risk_pi, _clip(coverage))

    conditions: list[str] = []
    for name in missing_pillars:
        # D4 (البند 16): مفردات الغياب القانونية على سطح الشروط أيضاً.
        conditions.append(f"جانب {_AR[name]} غائب (غير متاح: "
                          f"{_parts_ar(pillars[name]['missing'])}) "
                          "— أكمل مصادره قبل قرار نهائي")
    for name, p in pillars.items():
        v = p["value"]
        if v is None:
            continue
        eff = 1.0 - v if name == "competition" else v
        if eff < 0.5:
            # سدّ تسريب (الطبقة ٨): كسر عشري خام على وجه التقرير ("ضعيف
            # (0.37)") — نسبة مئوية بشرية بدله، شقيقة إصلاح سطر «لماذا»
            # أعلاه لنفس السبب (لا رقم آلي خام يصل العميل).
            conditions.append(f"جانب {_AR[name]} ضعيف ({round(eff * 100)}%) "
                              f"— {p['basis']}")
    if pillars["regulatory"].get("eligibility_gate"):
        conditions.insert(0, "بوابة أهلية أمامية مفتوحة (منشأة معتمدة EU 2017/625) "
                             "— لا تقدّم قبل عبورها")

    # ── البند 2 (أمر إصلاح المحرّك): لا درجةَ ولا حكمَ آلياً بأقل من الحد
    # الأدنى من الأعمدة. `verdict=""` **بالتصميم**: `promote_engine_verdict`
    # لا يُرقّي حكماً فارغاً، و`build_view` (silk_render.py:2360) يرتدّ لقراءة
    # التغطية («الحالة: …» لا «التوصية: …») — فلا رقم ولا توصية على أي سطح،
    # والغائب مُسمّى. الفرع القديم (كل الأعمدة غائبة ⇒ NO-GO) كان يُصدر حكماً
    # من لا-بيانات — يُلغى بنفس القاعدة.
    computed_n = _N_PILLARS - len(missing_pillars)
    if computed_n < _min_scored_pillars():
        missing_ar = [_AR[n] for n in missing_pillars]
        # بوابةُ الخطر الحرج (PV<−1.5) **قياسٌ صلبٌ مرصود** لا درجةٌ مختلَقة —
        # تبقى فوق قاعدة الحد الأدنى (مراجعة §58: كتمُها هنا كان يحوّل خطراً
        # مقيساً إلى «بيانات غير كافية» محايدة). الدرجة تبقى None بصدق.
        _crit_verdict = "NO-GO" if critical else ""
        return {
            "decision_rule": decision_rule_text(),
            "schema": SCHEMA, "verdict": _crit_verdict, "score": None,
            "confidence": None,
            "confidence_basis": "لم تُحسب ثقة — الأعمدة المحسوبة دون الحد "
                                "الأدنى للتقييم",
            "insufficient_pillars": True,
            "computed_pillars": computed_n,
            "min_scored_pillars": _min_scored_pillars(),
            "weights_option": opt, "weights": WEIGHT_OPTIONS[opt],
            "scores_by_option": {k: None for k in WEIGHT_OPTIONS},
            "weights_label": _WEIGHT_LABEL_AR.get(opt, opt),
            "weights_note": "لم تُحسب درجة موزونة — الأعمدة المحسوبة دون "
                            "الحد الأدنى",
            "pillars": pillars, "missing_pillars": missing_pillars,
            "incumbent_is_self": pillars["competition"].get("incumbent_is_self"),
            "critical_risk": critical, "risks": risks,
            "conditions": conditions,
            "first_steps": [f"أكمل مصادر عمود {n} قبل طلب درجةٍ وحكم"
                            for n in missing_ar],
            "why": (("خطر حرج مرصود (الاستقرار السياسي دون العتبة) يقلب "
                     "القرار عدمَ دخولٍ بصرف النظر عن اكتمال الأعمدة؛ و"
                     if critical else "")
                    + f"بيانات غير كافية للتقييم — أعمدة محسوبة {computed_n} "
                    f"من {_N_PILLARS} والحد الأدنى {_min_scored_pillars()}؛ "
                    "الغائب: " + ("، ".join(missing_ar) or "—")),
            # شكلُ المخرَج مستقرّ لكل مستهلك: الحقل حاضر دوماً، وامتناعُه معلن.
            "counter_case": {"skipped": "insufficient_pillars",
                             "note": "لا حجة مضادة — لم يصدر حكم آلي بأقل من "
                                     "الحد الأدنى من الأعمدة"},
            "note": "لا حكم آلي بأقل من الحد الأدنى من الأعمدة — الغائب "
                    "مُعلَن بالاسم، لا تخمين ولا درجة على أوزان فارغة",
        }

    # (البند 2): `score is None` صار مستحيلاً هنا — صفرُ أعمدةٍ يعترضه فرعُ
    # الحدّ الأدنى أعلاه (≥1 دوماً)؛ الفرعُ القديم «NO-GO من لا-بيانات» حُذف
    # لا عُلّق (مراجعة §58: بقاؤه كان بابَ عودةٍ صامتة للحكم المختلَق).
    if critical:
        verdict = "NO-GO"
        why = ("بوابة خطر حرجة: مؤشر الاستقرار السياسي دون العتبة الحرجة "
               "(قاعدة الحكم المعلنة)")
    elif score >= _GO and confidence >= _MIN_CONF_GO and not conditions:
        verdict = "GO"
        why = (f"الدرجة الموزونة {_pct(score)} بلغت عتبة المضي "
               f"({_pct(_GO)}) والثقة {_conf_phrase(confidence)} فوق "
               f"الحد الأدنى ({_pct(_MIN_CONF_GO)})")
    elif score < _NOGO:
        verdict = "NO-GO"
        why = (f"الدرجة الموزونة {_pct(score)} دون عتبة الرفض "
               f"({_pct(_NOGO)})")
    else:
        verdict = "CONDITIONAL-GO"
        # أسباب فعلية فقط (إصلاح P0-1): القالب القديم "X أو Y أو Z" كان يطبع
        # الأسباب الثلاثة دوماً — فظهر «الثقة 0.91 دون 0.6» وهي ليست دونها،
        # وقرأه المالك تناقضاً في أرقام الثقة بين المشتقات. الآن تُسرد
        # الأسباب المتحقّقة حصراً.
        # سطر «لماذا» يظهر حرفياً على وجه التقرير (docx/markdown) — عربية
        # بشرية بلا رطانة كود: "score 0.64" الإنجليزية الخام كانت تصل
        # العميل، والثقة العشرية الخامة تصاغ عبر confidence_phrase
        # (نفس قاعدة إصلاح المرحلة ٥: لا كسر عشري خام على وجه التقرير).
        reasons = []
        if score < _GO:
            reasons.append(f"الدرجة الموزونة {_pct(score)} في النطاق الشرطي")
        if confidence < _MIN_CONF_GO:
            reasons.append(f"الثقة {_conf_phrase(confidence)} دون الحد "
                           f"الأدنى ({_pct(_MIN_CONF_GO)})")
        if conditions:
            reasons.append(f"شروط مفتوحة ({len(conditions)})")
        why = " و".join(reasons)

    first_steps = _first_steps(verdict, pillars, conditions, risks)
    out = {
        # الموجة ٥ (الجزء ٦-١): قاعدة القرار تسبق الحكم في بنية المخرج —
        # كل مُصدِّر يعرضها قبل سطر الحكم فيرى القارئ أنها لم تُفصَّل عليه.
        "decision_rule": decision_rule_text(),
        "schema": SCHEMA, "verdict": verdict, "score": score,
        "confidence": confidence,
        # سدّ تسريب (الطبقة ٨): كسر تغطية عشري خام ("التغطية 0.65 × ...")
        # — نسبة مئوية بشرية بدله (شقيقة إصلاح سطر «لماذا» في المرحلة ٥).
        "confidence_basis": f"التغطية {_pct(_clip(coverage))} × الأعمدة "
                            f"المحسوبة {_N_PILLARS - len(missing_pillars)}"
                            f"/{_N_PILLARS}",
        "weights_option": opt, "weights": WEIGHT_OPTIONS[opt],
        "scores_by_option": scores,
        # سدّ تسريب (الطبقة ٨، قرار المالك): "بوابة GATE 3" مصطلح مسار عمل
        # داخلي — والحرف الخام A/B رمز مفتاح داخلي (يبقى weights_option/
        # SILK_DECISION_WEIGHTS كما هما لسطح الـAPI؛ العرض فقط يتغيّر).
        "weights_label": _WEIGHT_LABEL_AR.get(opt, opt),
        "weights_note": (f"تُحسب الدرجة بمجموعتي أوزان معاً للمقارنة؛ "
                         f"المعتمد لهذا القرار: {_WEIGHT_LABEL_AR.get(opt, opt)}"),
        "pillars": pillars, "missing_pillars": missing_pillars,
        # البند 1: علمُ «المهيمن سعوديّ» يصل مستهلكي القرار كما هو — منطقُ
        # الدخول دفاعيٌّ لا توسّعيّ؛ لا يُطوى في الدرجة (الدرجة تقيس انغلاق
        # السوق على داخلٍ جديد أياً كان).
        "incumbent_is_self": pillars["competition"].get("incumbent_is_self"),
        "critical_risk": critical, "risks": risks, "conditions": conditions,
        "first_steps": first_steps, "why": why,
        "note": "قرار حتمي قابل للتفسير من الحزمة البحثية المتحقَّق منها — "
                "الأعمدة الغائبة شروط معلنة، لا تخمين",
    }
    # الموجة ٥ (الجزء ٦-٥): الحجة المضادة في أقوى صورها + سبب عدم اعتمادها.
    out["counter_case"] = counter_case(out)
    return out


def _first_steps(verdict: str, pillars: dict, conditions: list[str],
                 risks: list[dict]) -> list[str]:
    """خطوات أولى قاعدية — مشتقة من أضعف الأعمدة والمخاطر، لا نصائح عامة."""
    steps: list[str] = []
    if verdict == "NO-GO":
        return ["عالج سبب NO-GO المذكور أولاً ثم أعد التحليل — لا خطوات دخول "
                "قبل ذلك"]
    if pillars["regulatory"].get("eligibility_gate"):
        steps.append("ابدأ بمسار اعتماد المنشأة (القائمة الأوروبية EU 2017/625) "
                     "— كل ما بعده محجوب عليه")
    # سدّ تسريب (الطبقة ٩): كانت الخطوات تشير لاسم وكيل داخلي خام إنجليزي
    # بين قوسين ("وكيل regulatory"/"وكيل supplier") — لا قيمة للقارئ في
    # معرفة أي وكيل داخلي غذّى الخطوة؛ عربية صرفة بلا إسناد داخلي الآن.
    if pillars["regulatory"]["value"] is not None and \
            pillars["regulatory"]["value"] < 0.5:
        steps.append("أغلق بنود قائمة الاشتراطات بنداً بنداً بمرجعها الرسمي")
    comp = pillars["competition"]["value"]
    if comp is not None and comp > 0.5:
        steps.append("سوق مركّز: ادخل عبر موزّع قائم من مرشّحي التوريد "
                     "المرصودين بدل البناء المباشر")
    prof = pillars["profit"]["value"]
    if prof is None:
        # #13: لغة الزائر لا لغة المدخلات — المعطيان نفساهما بالاسم.
        steps.append("أدخل سعر المصنع للكيلوغرام وطاقتك الإنتاجية الشهرية "
                     "ليُحسب الهامش والحصة الواقعية قبل الالتزام")
    for r in risks:
        if r["risk"] == "تقلب العملة":
            steps.append("سعّر بعقود قصيرة أو تحوّط عملة — " + r["evidence"])
    if not steps:
        steps.append("تحقّق من مرشّحي التوزيع والتوريد بالاسم — المرشّحون "
                     "غير موثَّقين حتى تأكيدهم")
    return steps[:5]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo = {"coverage": 0.8, "pillar_inputs": {
        "market_attractiveness": {"tam_usd": 2.9e8, "import_cagr_pct": 6.0,
                                  "gdp_per_capita_usd": 48_000,
                                  "saudi_share_pct": 2.0},
        "competition_intensity": {"hhi": 1200, "top_supplier_share_pct": 21.0,  # مقياس 0–10000
                                  "named_company_count": 7},
        "regulatory_fit": {"tariff_applied_pct": 0.0,
                           "entry_requirements_count": 9,
                           "eligibility_gate": True},
        "profitability": {"border_unit_value_usd_kg": 3.4,
                          "saudi_border_unit_value_usd_kg": 3.1,
                          "margin_at_border_pct": 18.0},
        "risk": {"political_stability_wgi": 0.8, "fx_volatility_pct": 0.9,
                 "supplier_concentration_hhi": 1200, "critical_risk": False}}}  # مقياس 0–10000
    d = decide(demo)
    print(f"verdict={d['verdict']} score={d['score']} (A/B: "
          f"{d['scores_by_option']}) conf={d['confidence']}")
    for c in d["conditions"]:
        print("  شرط:", c)
    for s in d["first_steps"]:
        print("  خطوة:", s)


# ── الموجة ٥ (توجيه المنصّة، الجزء ٦): قاعدة القرار تُعلن قبل تطبيقها + ────
# الحجة المضادة في أقوى صورها — حتميان بالكامل من مكونات النقاط القائمة.

def decision_rule_text() -> str:
    """نصّ قاعدة القرار — يُعرض **قبل** الحكم كي يرى القارئ أن القاعدة لم
    تُفصَّل على النتيجة (الجزء ٦-١ من التوجيه)."""
    # الموجة Z (Z-07): لا كسرَ عشريٍّ خام على وجه التقرير — العتباتُ نِسَبٌ
    # مئوية كـ`why`/`confidence_basis`، فلا جملةٌ بوحدتين («0.65 … 60%»).
    return ("قاعدة القرار (معلنة قبل تطبيقها): مضيّ حين تبلغ الدرجة الموزونة "
            f"{_pct(_GO)} فأعلى مع ثقة {_pct(_MIN_CONF_GO)} فأعلى وبلا "
            f"شروط مفتوحة؛ رفض حين تنخفض الدرجة دون {_pct(_NOGO)} أو عند إطلاق "
            "بوابة الخطر الحرجة (الاستقرار السياسي دون العتبة)؛ وما بينهما "
            "دخول مشروط بشروط مسماة. الثقة = التغطية × نسبة الأعمدة "
            "المحسوبة — لا نسبة مجرّدة.")


def counter_case(decision: dict) -> dict:
    """الحجة المضادة في أقوى صورها + سبب عدم اعتمادها (الجزء ٦-٥) —
    تُبنى حتمياً من أعمدة القرار نفسه؛ لا نموذج، لا اختلاق."""
    pillars = decision.get("pillars") or {}
    verdict = str(decision.get("verdict") or "")
    # ── الموجة Z · البند Z-05 — قطبُ عمود المنافسة كان مقلوباً هنا ────────
    # `_score` يستهلك عمودَ المنافسة **مقلوباً** (`eff = 1 − v`): شدّةٌ أقلّ =
    # مساهمةٌ أعلى. وكانت هذه الدالةُ ترتّب الأعمدةَ على `value` الخام، فتقرأ
    # سوقاً مُفتَّتةً (شدّة 0.33، وهي أقوى ما يدعم الدخول) على أنّها «أضعف
    # الأعمدة … يدعم رفضاً» — أي أنّ أقوى حجّةٍ **مع** الدخول تُقدَّم للمصنع
    # أقوى حجّةٍ **ضدّه**. مُثبَتٌ بإعادة إنتاج على HHI=200 مقابل HHI=4800.
    #
    # الترتيبُ الآن على **المساهمة الفعلية** بنفس تحويل `_score` حرفياً، وهي
    # أيضاً الرقمُ المطبوع (طباعةُ الشدّة الخام كانت تناقض الجملة حولها).
    def _eff(name: str, v: float) -> float:
        return 1.0 - v if name == "competition" else v

    scored = [(k, _eff(k, float((v or {}).get("value"))))
              for k, v in pillars.items()
              if isinstance((v or {}).get("value"), (int, float))]
    if not scored:
        return {"case": "لا جوانب محسوبة تُبنى منها حجة مضادة — البيانات "
                        "غير كافية أصلاً.",
                "rebuttal": ""}
    # البند 8 (أمر إصلاح المحرّك): «أقوى الأعمدة X وأضعفها X» بعمودٍ واحد
    # جملةٌ تناقض نفسها (تقرير #11 طبعها حرفياً) — القالب يشترط عمودين
    # مختلفين، ودونهما يُمتنَع معلَناً (skipped صادقة) فيُسقِط العرضُ القسمَ
    # بدل استبداله (نفس عقد فرع insufficient_pillars).
    if len({k for k, _ in scored}) < 2:
        return {"skipped": "single_pillar", "case": "", "rebuttal": "",
                "note": "عمود واحد محسوب — لا حجة مضادة من عمود يقارن نفسه"}
    weakest = min(scored, key=lambda t: t[1])
    strongest = max(scored, key=lambda t: t[1])
    conds = decision.get("conditions") or []
    if verdict == "GO":
        case = (f"أقوى حجة ضد المضيّ: أضعف الجوانب «{_AR.get(weakest[0], weakest[0])}» "
                f"عند {round(weakest[1] * 100)}%"
                + (f"، مع {len(conds)} شرطاً مفتوحاً" if conds else "")
                + " — لو كان هذا العمود هو الحاكم وحده لتغيّر القرار.")
        rebuttal = (f"لماذا لم تُعتمد: الدرجة الموزونة "
                    f"{_pct(decision.get('score'))} تجاوزت عتبة المضيّ "
                    f"({_pct(_GO)}) عبر الأعمدة مجتمعة بأوزانها المعلنة، "
                    f"والثقة {_pct(decision.get('confidence'))} فوق الحد "
                    "الأدنى — جانب ضعيف واحد لا يعكس القرار ما لم يبلغ "
                    "بوابة الخطر الحرجة.")
    elif verdict == "NO-GO":
        case = (f"أقوى حجة ضد الرفض: أقوى الجوانب "
                f"«{_AR.get(strongest[0], strongest[0])}» عند "
                f"{round(strongest[1] * 100)}% يشير إلى فرصة قائمة.")
        rebuttal = (f"لماذا لم تُعتمد: الدرجة الموزونة "
                    f"{_pct(decision.get('score'))} دون عتبة الرفض "
                    f"({_pct(_NOGO)}) أو أطلقت بوابة الخطر الحرجة — جانب "
                    "قوي واحد لا يعوّض بنية القرار الكاملة.")
    else:
        case = (f"أقوى حجة ضد الدخول المشروط: من جهةٍ أقوى الجوانب "
                f"«{_AR.get(strongest[0], strongest[0])}» "
                f"({round(strongest[1] * 100)}%) يدعم مضيّاً كاملاً، ومن جهةٍ "
                f"أضعفها «{_AR.get(weakest[0], weakest[0])}» "
                f"({round(weakest[1] * 100)}%) يدعم رفضاً.")
        rebuttal = ("لماذا لم تُعتمد أيٌّ منهما: الدرجة في النطاق الشرطي "
                    "والشروط المفتوحة مسماة — الحسم قبل إغلاقها التزام "
                    "بلا أساس.")
    return {"case": case, "rebuttal": rebuttal}
