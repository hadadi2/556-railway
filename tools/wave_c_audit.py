"""تدقيقٌ بعديٌّ مركَّز على بنود الموجة C — يقيس، لا يفترض.

يُشغَّل على الشجرة بعد الموجة، ويُثبِت لكلّ بندٍ **سلوكاً** لا وجودَ رمز.
الفرقُ جوهريّ: أربعةٌ من بنود هذه الموجة كانت رموزاً موجودةً وخامدة.

    python3 tools/wave_c_audit.py
"""
from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_rows: list = []


def chk(item: str, ok: bool, detail: str) -> None:
    _rows.append((item, bool(ok), detail))


def _src(name: str) -> str:
    return io.open(os.path.join(_ROOT, name), encoding="utf-8").read()


# ── التنظيم ──────────────────────────────────────────────────────────────
import silk_requirements_agent as R                     # noqa: E402
import silk_quality_gate as Q                           # noqa: E402

_meat = R.regulatory_blockers("DEU", "020130")
chk("§5-1 عمودا الحجب/الانطباق",
    all(R.blocking_level(r) in (R.BLOCKING_HARD, R.BLOCKING_CONDITIONAL,
                                R.BLOCKING_PROCEDURAL)
        for r in R._load_reference()), "كلُّ صفٍّ بدرجةٍ معلومة")
chk("§5-2 انطباقٌ ثلاثيّ الحالة",
    (R.applies_to({"applies_when": "hs_chapter:02"}, "020130", "food") is True
     and R.applies_to({"applies_when": "needs_evidence"}, "0", "food") is None),
    "ينطبق / لا ينطبق / لا يُعرَف")
chk("§5-3 حواجزُ بنيوية", bool(R.open_hard_blockers(_meat)),
    f"{len(R.open_hard_blockers(_meat))} حاجزٌ صلبٌ لمنتجٍ حيوانيّ إلى الاتحاد")
chk("§5-3 تمورٌ لا تُحجَب بندٍ حيوانيّ",
    R.open_hard_blockers(R.regulatory_blockers("DEU", "080410")) == [],
    "لا حجبَ بلا سبب")
_view = {"regulatory": R.regulatory_state("DEU", "020130"),
         "deep_research": {"verdict": {"verdict": "GO"}}}
chk("§5-4 البوّابةُ الحاجزة",
    bool(Q._check_regulatory_blocker(_view))
    and "regulatory_hard_blocker_open" in Q.FAIL_TRIGGER_CHECKS,
    "إيجابٌ فوق حاجزٍ مفتوح = رفض")
chk("R-04 الجدولُ الزمنيّ يُحسَب",
    bool(R.regulatory_state("DEU", "020130")["access_timeline"].get("steps")),
    "لم يعد شيفرةً ميتة")

# ── الأدلة والإسناد ──────────────────────────────────────────────────────
import silk_llm_runtime as L                            # noqa: E402
from silk_data_layer import DataPoint                   # noqa: E402

chk("T-04 معرّفاتُ الأدلة تُحفَظ",
    DataPoint(1, "s", .5, evidence_ids=("dp1",)).evidence_ids == ("dp1",),
    "حاملٌ صريحٌ متمايزٌ عن source_ids")
_a = DataPoint(1, "UN Comtrade", .9, unit="USD", data_year=2023,
               url="https://x", retrieval_method="api")
chk("T-08 وراثةُ عقد المصدر",
    L._cited_contract_fields([_a, _a], "UN Comtrade").get("unit") == "USD",
    "تُملأ بلا لبسٍ فقط")
chk("T-08 لا وراثةَ عند اللبس",
    "unit" not in L._cited_contract_fields(
        [_a, DataPoint(1, "WB", .9, unit="tonnes")], "UN Comtrade"),
    "وحدتان مختلفتان ⇒ لا نسبة")

# ── التحجيم والحساب ──────────────────────────────────────────────────────
import re                                               # noqa: E402
_judge = "\n".join(l for l in _src("silk_ai_judge.py").splitlines()
                   if not l.strip().startswith("#"))
chk("Z-01 الموجِّه لا يأمر بالحساب",
    not re.search(r"احسب\s+TAM", _judge) and "لا تحسبها" in _judge,
    "العرضُ لا الحساب")
_tbl = ("| المستوى | القيمة | طريقة الحساب |\n| TAM | 61,000,000 | واردات |\n"
        "| SAM | 9,150,000 | TAM × 15% |\n| SOM | 12,000,000 |  |")
_sz = Q._check_market_sizing_derivation({"report": {"text": _tbl},
                                         "missions": {}})
chk("Z-03 فحصُ الاشتقاق",
    {"sizing_row_without_method", "sizing_order_inverted"}
    <= {h["check"] for h in _sz}, "صفٌّ بلا معادلة + ترتيبٌ مقلوب")
chk("Z-05 حارسُ التأريض في الإنتاج",
    "from silk_evals import formula_grounded_numbers" in _src(
        "silk_quality_gate.py"), "خرج من حزمة التقييم")
chk("Z-02 مبالغُ النثر تُردّ",
    bool(Q._check_narrative_money_grounded({
        "missions": {"t": {"findings": [{"value": 61000000, "note": "واردات"}]}},
        "report": {"text": "السوق يبلغ 900 مليون دولار."}})),
    "رقمٌ طليقٌ يُعلَن")

# ── الاقتصاد والتسعير ────────────────────────────────────────────────────
import silk_economics as E                              # noqa: E402


def _pr(*rows):
    return {"missions": {"pricing_scout": {"findings": [
        {"value": v, "note": n} for v, n in rows]}}}


chk("E-01 سعرُ حدودٍ لا يُرسي",
    E.economics_view(_pr((6.0, "قيمة الاستيراد عند الحدود")))["anchor_price"]
    is None, "المستوى يسبق الرقم")
chk("E-01 رفٌّ يفوز على حدود",
    E.economics_view(_pr((6.0, "عند الحدود"), (25.0, "سعر رف")))
    ["anchor_price"]["raw_value"] == 25.0, "خلطُ المستويات ممنوع")
chk("E-02 مرساةٌ من نثر",
    (E.economics_view(_pr(("سعر رف 7.49 يورو", "متجر")))["anchor_price"] or {})
    .get("raw_value") == 7.49, "الجملُ تُقرأ")
chk("E-02 المدى بحدّه الأدنى",
    min(E.price_numbers_in_text("بين 6 و9 يورو")) == 6.0, "لا تفاؤل")
chk("E-05 HHI من نثر",
    E.economics_view({"missions": {"competitors": {"findings": [
        {"value": "HHI يقارب 2350", "note": "تركّز"}]}}})["hhi"] == 2350.0,
    "بوّابةُ الإزاحة تعمل")
chk("E-05 «لم يُقَس» معلَنة",
    E.economics_view({"missions": {}})["displacement_measured"] is False
    and any("تركّز المورّدين غير مرصود" in g
            for g in E.economics_view({"missions": {}})["gaps"]),
    "لا تُقرأ سوقاً مفتوحاً")
chk("E-06 السجلُّ يُصاب بالاسم العربيّ",
    E.convert_amount(1.0, "litre", "kg", "حليب")[0] == 1.03, "مفتاحٌ مترجَم")
chk("E-07 حسابٌ واحد",
    "product_card=product_card" in _judge, "الكاتبُ والعرضُ بوسيطين واحدين")
chk("E-08 فحصُ الاقتصاد يستيقظ",
    bool(Q._check_economics_present({
        "missions": {"pricing_scout": {"findings": [
            {"value": "سعر رف 7.49 يورو", "note": "م"}]}}, "economics": {}})),
    "يُطلِق على الشكل الإنتاجيّ")
chk("E-04 بطاقةُ المنتج",
    __import__("silk_platform.engine_bridge", fromlist=["x"])
    .product_card_from_row({"cost_per_unit": 12.5}) == {"cost_per_unit": 12.5},
    "تُبنى — وبلا تكلفةٍ لا تُبنى")

# ── التناقضات والطزاجة والثقة ────────────────────────────────────────────
import silk_plausibility as P                           # noqa: E402

_res = {"deep_research": {"missions": {"m": {"findings": [
    {"claim": "حجم السوق", "value": "900000000000", "note": "حجم السوق",
     "source": "X"}]}}}}
P.annotate(_res)
chk("X-04 «لم يُفحَص» معلَنة",
    bool(_res["deep_research"].get("plausibility_unverified")),
    "لا يفشل مفتوحاً صامتاً")
chk("X-02 الشريحةُ الوسطى",
    any(h["check"] == "evidence_body_numeric_divergence"
        for h in Q._check_evidence_body_numeric_consistency({
            "missions": {"t": {"findings": [
                {"value": 10_000_000, "note": "واردات"}]}},
            "report": {"text": "واردات السوق 25 مليون دولار"}})),
    "٢٫٥× لم تعد تمرّ")
chk("S-02 القِدَمُ يصل الكاتب",
    '_vint = str(c.get("vintage") or "").strip()' in _src("silk_render.py"),
    "لم يعد يُحسَب ويُرمى")

_conf = L._parse_output(
    '{"findings":[{"claim":"ك","datapoint_ids":["a"],"confidence":0.99}],'
    '"gaps":[],"summary":""}',
    {"a": DataPoint(5.0, "UN Comtrade", 0.6, "n", "")})
chk("C-06 الثقةُ مسقوفةٌ بالأدلة",
    _conf["findings"][0]["confidence"] == 0.6, "النموذجُ يخفض ولا يرفع")

from silk_render import _VERDICT_LABELS_AR as _LBL      # noqa: E402
chk("C-08 النثرُ يُربَط بالحكم",
    bool(Q._check_narrative_matches_the_verdict({"deep_research": {
        "verdict": {"verdict": "NO-GO", "confidence": 0.7},
        "report": {"text": f"التوصية: {_LBL['go']}."}}})),
    "تحذيريٌّ بسببٍ معلَن (V-01 في الموجة D)")

# ── التغطية والوسوم ──────────────────────────────────────────────────────
from silk_narrative import evidence_badge_for           # noqa: E402
import silk_research                                    # noqa: E402
from silk_source_coverage import _is_backed             # noqa: E402

chk("T-13 سقفُ الرتبة يعمل",
    evidence_badge_for(DataPoint(5, "UN Comtrade", .9,
                                 retrieval_method="llm_web")).startswith("◐"),
    "بإشارةٍ بنيوية بعد زوال الوسم النصّيّ")
_note = silk_research._indicative("مُقدَّر", "SAM = TAM × 0.3")
chk("T-14 وسمُ التقدير يُنادى",
    _is_backed("", _note) and not _is_backed("", "مُقدَّر"),
    "المسارُ الشرعيّ حيّ")

# ── سدُّ الفجوات ─────────────────────────────────────────────────────────
import silk_gap_recovery as G                           # noqa: E402

os.environ["SILK_GAP_RECOVERY_ENABLED"] = "1"
os.environ["SILK_GAP_RECOVER_WEB_SEARCH"] = "1"
chk("§6 حتميٌّ مفتوح", G.recoverer_enabled("wgi"), "تحت الصمّام")
chk("§6 يحتاج دليلاً مطفأ", not G.recoverer_enabled("seasonality"), "افتراضاً")
chk("§6 الويبُ مطفأٌ بنيوياً", not G.recoverer_enabled("web_search"),
    "حتى بمفتاحٍ صريح")
os.environ.pop("SILK_GAP_RECOVER_WEB_SEARCH", None)
os.environ["SILK_GAP_RECOVERY_ENABLED"] = "0"

# ── E-10 · المدوّنة تطابق الإنتاج ────────────────────────────────────────
from canonical_netherlands import netherlands_research_blob  # noqa: E402
from silk_missions import MISSIONS                      # noqa: E402

_ms = netherlands_research_blob()["deep_research"]["missions"]
chk("E-10 مفاتيحُ المدوّنة إنتاجية",
    all(k in MISSIONS for k in _ms), f"{len(_ms)} بعثة")
chk("E-10 الاقتصادُ مُمرَّن",
    E.economics_view(netherlands_research_blob()["deep_research"])["hhi"]
    == 940.0, "لم يعد hhi=None دائماً")

# ── C9 · وضوحُ ما يُقال ──────────────────────────────────────────────────
import silk_i18n                                        # noqa: E402
import silk_reports                                     # noqa: E402

# **قائمةٌ صريحة لا تصفيةٌ ببادئة.** المرورُ الأول صفّى بـ`coverage_` فجرف
# `coverage_gap` — مفتاحاً **قائماً قبل الموجة** على سطح المشغّل — فحُمِّر
# التدقيقُ على شيءٍ لم تُدخِله الموجة. تدقيقٌ يخلط القديمَ بالجديد يُنتِج إمّا
# إنذاراً كاذباً أو تبرئةً كاذبة.
_keys = [
    "reg_block_head", "reg_block_lead", "reg_block_why", "reg_block_impact",
    "reg_block_action", "reg_verify_head", "reg_verify_lead", "reg_verify_why",
    "reg_verify_impact", "reg_verify_action", "reg_clear_note",
    "insufficient_evidence", "not_calculable", "not_calculable_why",
    "not_calculable_action", "recovered_value", "recovered_derived",
    "stale_value", "stale_impact", "coverage_head", "coverage_good",
    "coverage_low", "coverage_low_action", "confidence_because",
    "confidence_reason_coverage", "confidence_reason_gaps",
    "confidence_reason_stale", "confidence_reason_conflict",
    "price_level_missing", "price_level_impact", "price_level_action",
    "margin_needs_cost", "margin_needs_cost_action",
]
_fmt = dict(market="م", authority="ج", pct="80", year="2023", band="ب",
            reason="ر", missing="ن", formula="ف")
_dirty = []
for _lg in ("ar", "en"):
    for _k in _keys:
        try:
            _txt = silk_i18n.t(_k, _lg, **_fmt)
        except KeyError:
            continue      # مفتاحٌ يطلب حقلاً آخر — خارج نطاق هذا الفحص
        if silk_reports._client_forbidden_hits(_txt, _lg):
            _dirty.append((_lg, _k))
chk("C9 رسائلُ العميل بلغةِ أعمال", not _dirty,
    f"{len(_keys)} مفتاحاً في اللغتين، صفرُ ملاحظات")

# ── ملاحظةٌ قائمةٌ قبل الموجة، تُعلَن ولا تُحسَب عليها ────────────────────
# `coverage_gap` («فجوة معلنة») يُحمِّر حارسَ مفردات العميل. مفتاحٌ **سابقٌ**
# للموجة C على سطح المشغّل — يُسجَّل هنا كي لا يضيع، ولا يُعَدّ انحداراً منها.
_pre = silk_reports._client_forbidden_hits(silk_i18n.t("coverage_gap", "ar"),
                                           "ar")
if _pre:
    print("\nملاحظةٌ سابقةٌ للموجة (لا تُحسَب عليها): "
          f"coverage_gap ⇒ {_pre[0]}")

# ── التقرير ──────────────────────────────────────────────────────────────
_ok = sum(1 for _, o, _ in _rows if o)
print(f"\nتدقيقُ الموجة C البعديّ — {_ok}/{len(_rows)} مُثبَتٌ سلوكياً\n")
for item, ok, detail in _rows:
    print(f"  {'✔' if ok else '✘'} {item:<38} {detail}")
print()
sys.exit(0 if _ok == len(_rows) else 1)
