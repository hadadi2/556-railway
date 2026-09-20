"""مولّد خطّ أساس الحكم والدرجة — أمر المالك (خطوة الإعداد ٢ لهدف الدراسة الاحترافية).

يبني لكل مدوّنة قانونية مجمّدة (`tools/canonical_*.py`) بصمةَ الحكم من المصدرين
الوحيدين اللذين يراهما العميل والمحرّك:

1. **حكم العرض** — `silk_render.build_view(blob)["deep_research"]["verdict"]`
   (verdict/confidence) + `verdict_label`.
2. **قرار المحرّك الحتمي** — `silk_deep_pillars.decide_for_deep(dr)` بلا بطاقة
   منتج وبلا حالة تنظيمية (نفس نداء `api._deep_engine_decision` مع أعطاله
   الاختيارية مُصفَّرة): verdict/score/confidence/insufficient_pillars/
   computed_pillars وقيمة كل عمود محسوب.

الاستعمال: `python3 tools/gen_verdict_baseline.py` يكتب
`tests/baselines/verdict_score_baseline.json`. الاختبار الدائم
`tests/test_verdict_score_baseline.py` يقارن ضدّه قبل كل كوميت — أي تغيّر في
حكم أو درجة أي مدوّنة = كسر معلَن يُوقف العمل، لا يُحدَّث خطُّ الأساس إلا
بقرار مالك صريح.

The frozen verdict/score fingerprint of the 10 canonical blobs; regenerated
only on an explicit owner decision, never to make a wave pass.
"""
from __future__ import annotations

import importlib
import json
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
for p in (_REPO_ROOT, _TOOLS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

BASELINE_PATH = os.path.join(_REPO_ROOT, "tests", "baselines",
                             "verdict_score_baseline.json")

# المدوّنات العشر — مفتاح ثابت → (وحدة، دالة المدوّنة)
CANONICAL_BLOBS = {
    "dza_peanut_butter": ("canonical_dza_peanut_butter", "dza_research_blob"),
    # موجة عيوب التقرير (أمر المالك بعد كلّ جولة): سوقان ومنتَجان جديدان
    # تُولَّد تقاريرُهما وتُراجَع ذاتياً لاكتشافِ عائلاتِ عيوبٍ لم تُرصَد —
    # مصرُ (عملةٌ محلّية وفئةٌ واسعة) ونيجيريا (ضعفُ تبليغٍ مُعلَن ⇒ مرآة).
    "egypt_olive_oil": ("canonical_egypt_olive_oil",
                        "egypt_olive_oil_research_blob"),
    "nigeria_dates": ("canonical_nigeria_dates", "nigeria_dates_research_blob"),
    # الجولةُ الثانية (المراجعةُ الذاتية بعدها): الهندُ (مسارُ الاقتصاد
    # مكتملاً — بطاقةُ تكلفةٍ مُدخَلةٌ وسعرُ رفٍّ مرصود، فبنودُ القرار
    # محسوبةٌ لا فجوات) والمغربُ (عملتان لا تُطرَحان). وهما معاً الطرفان
    # في مقارنةِ مفرداتِ التعرّف (الصنف ١٢).
    "india_honey": ("canonical_india_honey", "india_honey_research_blob"),
    "morocco_juice": ("canonical_morocco_juice",
                      "morocco_juice_research_blob"),
    # الجولةُ الثالثة (المراجعةُ الذاتية بعدها): ليبيا (سلطتان بحكم الواقع
    # وبوّابتا دخولٍ مسمّيتان — شكلُ حارسِ الإقليم) وكينيا (ثلاثةُ أصنافِ
    # أنظمةِ مطابقةٍ في تقريرٍ واحد: قُطريٌّ ومشتركُ الاسم ودوليّ).
    "libya_tahini": ("canonical_libya_tahini", "libya_tahini_research_blob"),
    "kenya_honey": ("canonical_kenya_honey", "kenya_honey_research_blob"),
    "fettuccine": ("canonical_fettuccine", "fettuccine_research_blob"),
    "germany_dates": ("canonical_germany_dates", "germany_dates_research_blob"),
    "japan_honey": ("canonical_japan_honey", "japan_honey_research_blob"),
    "jordan_milk": ("canonical_jordan_milk", "jordan_milk_research_blob"),
    "kuwait_peanut_butter": ("canonical_kuwait_peanut_butter",
                             "kuwait_research_blob"),
    "nadec_yemen_dairy": ("canonical_nadec_yemen_dairy",
                          "nadec_yemen_research_blob"),
    "netherlands": ("canonical_netherlands", "netherlands_research_blob"),
    "qatar_peanut_butter": ("canonical_qatar_peanut_butter",
                            "qatar_research_blob"),
    "yemen": ("canonical_yemen", "yemen_research_blob"),
    # الموجة د-٢: فئةٌ صناعية (صفرُ ذكرٍ ديني، ميزةُ تكلفةٍ من المدخلات)
    # وسوقٌ أكبرُ مورّديه معيدُ تصدير — بالاكتشافات المخزَّنة (لا شبكة).
    "turkey_polymers": ("canonical_turkey_polymers",
                        "turkey_polymers_research_blob"),
    "netherlands_honey": ("canonical_netherlands_honey",
                          "netherlands_honey_research_blob"),
}


def _round(x, nd: int = 6):
    """تدوير حتمي للأعداد العائمة كي لا يكسر ضجيجُ التمثيل المقارنة."""
    return round(float(x), nd) if isinstance(x, (int, float)) and not isinstance(
        x, bool) and x is not None else x


def load_blob(key: str) -> dict:
    mod_name, fn_name = CANONICAL_BLOBS[key]
    return getattr(importlib.import_module(mod_name), fn_name)()


def fingerprint(blob: dict) -> dict:
    """بصمة الحكم/الدرجة لمدوّنة واحدة — حقول مستقرة قياسية فقط."""
    from silk_render import build_view
    import silk_deep_pillars

    view = build_view(blob)
    dr_view = view.get("deep_research") or {}
    ver = dr_view.get("verdict") or {}
    dec = silk_deep_pillars.decide_for_deep(
        blob.get("deep_research") or {}, product_card=None, regulatory=None)
    dec = dec or {}
    pillars = {}
    for name, node in (dec.get("pillars") or {}).items():
        pillars[name] = _round((node or {}).get("value"))
    return {
        "view_verdict": ver.get("verdict"),
        "view_confidence": _round(ver.get("confidence")),
        "view_verdict_label": dr_view.get("verdict_label"),
        "engine_verdict": dec.get("verdict"),
        "engine_score": _round(dec.get("score")),
        "engine_confidence": _round(dec.get("confidence")),
        "insufficient_pillars": dec.get("insufficient_pillars"),
        "computed_pillars": dec.get("computed_pillars"),
        "pillar_values": pillars,
    }


def collect_baseline() -> dict:
    return {key: fingerprint(load_blob(key)) for key in sorted(CANONICAL_BLOBS)}


def main() -> None:
    data = collect_baseline()
    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"كُتب خط الأساس: {BASELINE_PATH} ({len(data)} مدوّنة)")


if __name__ == "__main__":
    main()
