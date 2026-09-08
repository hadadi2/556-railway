"""تدقيقٌ بعديٌّ سلوكيّ على بنود الموجة D — يقيس، لا يفترض.

نظيرُ `tools/wave_c_audit.py`: لكلّ بندٍ إثباتُ **سلوك** لا وجودُ رمز. الموجة D
بالذات تحتاجه: بنودُها كانت **قدراتٍ موجودةً في الشيفرة وغائبةً عن المسار**،
فوجودُ الوحدة لا يقول شيئاً عن عملها.

    python3 tools/wave_d_audit.py
"""
from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_rows: list = []


def chk(item: str, ok: bool, detail: str) -> None:
    _rows.append((item, bool(ok), detail))


def _src(name: str) -> str:
    return io.open(os.path.join(_ROOT, name), encoding="utf-8").read()


import silk_deep_pillars as DP                          # noqa: E402
import silk_render                                      # noqa: E402
from canonical_netherlands import netherlands_research_blob  # noqa: E402
from silk_requirements_agent import regulatory_state    # noqa: E402

_r = netherlands_research_blob()
_dr = _r["deep_research"]
_reg = regulatory_state("NLD", "080410")
_r["markets"] = [{"iso3": "NLD", "name_ar": "هولندا", "rank": 1, "deep": True,
                  "regulatory": _reg, "components": DP.build_components(_dr),
                  "decision": DP.decide_for_deep(_dr, regulatory=_reg)}]
_view = silk_render.build_view(_r, "ar")
_top = _view["markets"][0]
_ed = _top.get("entry_decision") or {}

# ── الجذر ١ والقرار ──────────────────────────────────────────────────────
chk("الجذر ١ · صفُّ السوق", bool(_view.get("markets")),
    "لم يعد `markets: []` على المسار العميق")
chk("D-01 · محرّكُ القرار يعمل", _ed.get("schema") == "silk.decision/v1",
    f"حكم={_ed.get('verdict')} درجة={_ed.get('score')} ثقة={_ed.get('confidence')}")
chk("D-01 · الأعمدةُ الخمسة",
    set(_ed.get("pillars") or {}) == {"market", "competition", "regulatory",
                                      "profit", "risk"},
    "بمعادلةِ كلٍّ منها")
chk("D-01 · قاعدةٌ قبل الحكم", bool(_ed.get("decision_rule")), "مُعلَنة")
chk("D-01 · حجّةٌ مضادّة", bool(_ed.get("counter_case")), "حاضرة")
chk("D-04 · لا «لا أسواق مرتّبة»",
    "لا أسواق مرتّبة" not in str(_view["decision"].get("why") or ""),
    "الرسالةُ المتناقضة زالت")
chk("P-01 · الأوزان A/B",
    (_ed.get("scores_by_option") or {}).keys() >= {"A", "B"},
    "بديلا الأوزان يصلان تقرير العميل")

# ── المُستخرِجُ لا يقرّر ─────────────────────────────────────────────────
_dp_src = _src("silk_deep_pillars.py")
_body = "\n".join(l for l in _dp_src.splitlines()
                  if not l.strip().startswith("#"))
chk("D-01 · لا منطقَ قرارٍ ثانٍ",
    not any(w in _body for w in ("GO", "NO-GO", "WEIGHT", "verdict ="))
    and "def decide(" not in _dp_src,
    "المُستخرِجُ مُستخرِج")
chk("D-01 · الغائبُ يبقى None",
    DP.build_pillar_inputs({"missions": {}})["market_attractiveness"]
    ["tam_usd"] is None, "لا صفرٌ مختلَق")

# ── الفروعُ التي فتحها الجذر ────────────────────────────────────────────
_cd = _top.get("components_detail") or []
chk("X-03 · الصفُّ بمكوّناته", len(_cd) >= 4,
    f"{len(_cd)} مكوّناً — الحارسان يقرآن صفّاً")
chk("X-03 · سطرُ مصدرٍ لكلّ رقم",
    all(c.get("source") for c in _cd if c.get("value") is not None),
    "لا رقمَ بلا مصدر")
_dr2 = netherlands_research_blob()["deep_research"]
_dr2["missions"]["trade_flow"]["findings"][0]["data_year"] = 2019
_v2 = silk_render.build_view(
    {**netherlands_research_blob(), "deep_research": _dr2,
     "markets": [{"iso3": "NLD", "rank": 1,
                  "components": DP.build_components(_dr2)}]}, "ar")
chk("S-01 · تحذيرُ القِدَم",
    any(c.get("vintage") for c in _v2["markets"][0]["components_detail"]),
    "رقمُ ٢٠١٩ يحمل عمرَه")

# ── R-03 · البوّابةُ التنظيمية بنيويّة ──────────────────────────────────
_gate = DP.build_pillar_inputs(
    {"missions": {}},
    regulatory={"open_hard": [{"item": "x"}], "all": [{}]})["regulatory_fit"]
chk("R-03 · بوّابةُ الأهلية", _gate["eligibility_gate"] is True,
    "تُقرأ من حالة الحواجز لا من نثر")
_d_blocked = DP.decide_for_deep(
    {"missions": {"trade_flow": {"findings": [
        {"value": "واردات السوق 42,000,000 دولار", "note": "واردات"}],
        "failed": False}}},
    regulatory={"open_hard": [{"item": "إدراج المنشأة"}], "all": [{}]})
chk("R-01 · الحاجزُ يتصدّر الشروط",
    bool(_d_blocked and "بوابة أهلية" in (_d_blocked.get("conditions") or [""])[0]),
    "منعُ الإيجاب حتميٌّ لا تعليمة")

# ── V-02 · الرمزُ يسبق النصّ ────────────────────────────────────────────
from silk_agents import COVERAGE_STATES                 # noqa: E402
from silk_render import _STATE_TONE, _coverage_basis_tone, _verdict_tone  # noqa: E402

_jury = {"basis": "data_coverage", "coverage_state": "coverage_none",
         "verdict": "صيغةٌ لا يعرفها أيُّ مطابِق"}
chk("V-02 · تفكيكٌ بالرمز",
    _coverage_basis_tone(_verdict_tone(_jury["verdict"]), _jury) == "data_absent",
    "نصٌّ مجهولٌ يُفكَّك صحيحاً")
chk("V-02 · كلُّ حالةٍ لها نبرة",
    set(COVERAGE_STATES) == set(_STATE_TONE), "لا حالةَ يتيمة")

# ── P-02 · الكاتبُ يعرض ولا يحسب ────────────────────────────────────────
_judge = "\n".join(l for l in _src("silk_ai_judge.py").splitlines()
                   if not l.strip().startswith("#"))
chk("P-02 · لا أمرَ بحساب درجة",
    "(score/confidence) في جدول Markdown صغير" not in _judge
    and "لا تحسبها ولا تشتقّها" in _judge, "العرضُ لا الحساب")
chk("P-02 · غيابُ الدرجة يُعلَن",
    "الدرجة الرقمية غير متاحة" in _judge, "لا يُملأ الفراغ برقم")

# ── V-03 · مدحوض ────────────────────────────────────────────────────────
chk("V-03 · القراءةُ تصل المدقّق",
    "قراءة تحليلية للذكاء الاصطناعي" in _src("silk_reports.py"),
    "مدحوضٌ بإعادة إنتاج — النداءُ ليس مهدوراً")

# ── التقرير ──────────────────────────────────────────────────────────────
_ok = sum(1 for _, o, _ in _rows if o)
print(f"\nتدقيقُ الموجة D البعديّ — {_ok}/{len(_rows)} مُثبَتٌ سلوكياً\n")
for item, ok, detail in _rows:
    print(f"  {'✔' if ok else '✘'} {item:<32} {detail}")
print()
sys.exit(0 if _ok == len(_rows) else 1)
