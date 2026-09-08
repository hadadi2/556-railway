"""تحقّق مُطعِّم الموجة ١ — Wave 1 charter/fact-records adapter validation.

يُشغِّل وكيل الميثاق (`silk_charter`) ومُطعِّم سجلّ الحقائق (`silk_fact_
records.build_fact_records_from_missions`) ضد كل المدوّنات القانونية
الحقيقية الشكل المتاحة في `tools/canonical_*.py` — كل واحدة إعادةُ بناءٍ
موثّقة لحادثة إنتاجية حقيقية (راجع رأس كل ملف: بلاغ حيّ + LESSONS رقمه).
يطبع رقمين هما بيت القصيد (الشيفرة أداة قياسهما فقط):

  (١) **معدّل تحويل المُطعِّم (parse rate)** — عبر كل نتائج البعثات في كل
      المدوّنات: هل يعمل `build_fact_records_from_missions` فعلياً على شكل
      بيانات حقيقي، أم يُسقِط نسبةً معتبرة صامتاً؟
  (٢) **معدّل توقّف الميثاق (عدم تطابق HS)** — لكل دراسة: هل يكتشف `build_
      charter` فعلياً حالات سوء التصنيف **الموثّقة سلفاً** في هذه المدوّنات
      (مثال: «زبدة الفول السوداني» على HS 040510 — «زبدة» ألبان لا فولٌ
      سوداني، DZA/KWT/YEM)، ولا يُطلِق زوراً على الحالات الصحيحة (QAT
      الصحيحة على 200811، NLD/DEU/JPN/ITA)؟

**حدودٌ معلنة صريحة — لا تعمية على ما يثبته هذا الرقمان فعلاً (ملاحظة
مُشرِف بعد أول تشغيلة):**

1. **حجم العيّنة**: هذه **١٠** مدوّنات حقيقية الشكل (إعادات بناء موثّقة
   لحوادث فعلية + حادثة #9 المرجعية الاصطناعية — راجع `canonical_jordan_
   milk.py`)، **لا ٢٠-٣٠ دراسة حيّة مستقلّة** — هذا كل ما هو متاح بلا شبكة/
   مفاتيح Anthropic في بيئة التطوير الحالية.
2. **معدّل توقّف الميثاق ليس تقدير معدّل توقّفٍ عام.** مجموعة `canonical_*`
   **مُثراةٌ بالحوادث عمداً** (أُنشئت أغلبُ ملفّاتها خصيصاً لأنها توثّق
   حوادث سوء تصنيف HS أو عيوباً مشابهة) — ليست عيّنةً عشوائية من دراسات
   حقيقية. فرقمٌ مثل ٤٠٪/٥٠٪ هنا **لا يعني** أن ٤٠-٥٠٪ من الدراسات الحقيقية
   ستتوقّف عند الميثاق؛ إنه معدّل اكتشافٍ **على عيّنة مصمَّمة لاختبار
   الاكتشاف**، لا معدّل حدوثٍ في الطبيعة. **لا يُستخدَم هذا الرقم لتبرير
   ترقية الموجة ١ من SHADOW إلى WARN** — ذلك يحتاج عيّنة تمثيلية من دراساتٍ
   حيّة غير مُنتقاة بحادثة.
3. **معدّل تحويل المُطعِّم ليس معدّل صمودٍ أمام مخرَجات مُلتقَطة حيّاً.**
   كل ملفّات `canonical_*` **مبنيّةٌ يدوياً على شكل القاموس** الذي يتوقّعه
   `_dp()`/المُطعِّم بالضبط (`value/source/confidence/note/retrieved_at`) —
   لم تُلتقَط من استجابة خادمٍ حيّ بكل ما فيها من تفاوتٍ محتمل (حقولٌ
   إضافية، تنسيقاتٌ غير متوقَّعة، قيمٌ حدّية). فرقم ١٠٠٪ هنا يثبت أن المُطعِّم
   **لا يتعطّل على الشكل المتوقَّع بنيوياً**، لا أنه صامدٌ أمام تنوّع
   مخرَجات إنتاجية حقيقية لم تُختبَر بعد — ذلك يحتاج التقاطاً فعلياً من
   تشغيلةٍ حيّة (`SILK_RUN_E2E=1` أو تشغيلة `/research` مدفوعة حقيقية).
4. `scope_hs_code` لكل سجلّ حقيقة يُشتَقّ من ميثاق التشغيلة الواحد لا من كل
   نتيجة بعثة على حدة (`DataPoint` لا يحمل حقل HS لكل سجلّ اليوم) — فمعدّل
   «عدم تطابق HS» المُقاس هنا هو **معدّل توقّف الميثاق على مستوى الدراسة**،
   لا معدّلاً لكل نتيجةٍ بعثة (التفصيل الكامل في توثيق `silk_fact_records.
   fact_record_from_finding`).

تشغيل: `python3 tools/wave1_charter_adapter_validation.py`
"""
from __future__ import annotations

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_charter import build_charter
from silk_fact_records import build_fact_records_from_missions

# (اسم الوحدة، اسم الدالّة) — كل صفّ ملف tools/canonical_*.py موجود فعلياً.
_FIXTURES = [
    ("canonical_dza_peanut_butter", "dza_research_blob"),
    ("canonical_fettuccine", "fettuccine_research_blob"),
    ("canonical_germany_dates", "germany_dates_research_blob"),
    ("canonical_japan_honey", "japan_honey_research_blob"),
    ("canonical_jordan_milk", "jordan_milk_research_blob"),
    ("canonical_kuwait_peanut_butter", "kuwait_research_blob"),
    ("canonical_nadec_yemen_dairy", "nadec_yemen_research_blob"),
    ("canonical_netherlands", "netherlands_research_blob"),
    ("canonical_qatar_peanut_butter", "qatar_research_blob"),
    ("canonical_yemen", "yemen_research_blob"),
]


def run() -> dict:
    rows = []
    agg_total = 0
    agg_parsed = 0
    agg_skipped_reasons: dict = {}

    for mod_name, fn_name in _FIXTURES:
        mod = importlib.import_module(mod_name)
        blob = getattr(mod, fn_name)()
        product = blob.get("product")
        hs_code = blob.get("hs_code")
        market = (blob.get("market") or {}).get("iso3")
        missions = (blob.get("deep_research") or {}).get("missions") or {}

        charter = build_charter(product, hs_code, market_iso3=market)
        fr = build_fact_records_from_missions(missions, charter)
        stats = fr["stats"]

        agg_total += stats["total_findings"]
        agg_parsed += stats["parsed"]
        for s in stats["skipped_reasons"]:
            agg_skipped_reasons[s["reason"]] = agg_skipped_reasons.get(s["reason"], 0) + 1

        rows.append({
            "study": mod_name, "product": product, "hs_code": hs_code,
            "market": market, "charter_halted": charter.halted,
            "halt_reason": charter.halt_reason,
            "findings": stats["total_findings"], "parsed": stats["parsed"],
            "parse_rate": stats["parse_rate"],
        })

    return {"rows": rows, "agg_total": agg_total, "agg_parsed": agg_parsed,
           "agg_skipped_reasons": agg_skipped_reasons}


def main():
    result = run()
    rows = result["rows"]

    print(f"{'study':32s} {'product':26s} {'hs':8s} {'mkt':5s} "
         f"{'halted':7s} {'findings':9s} {'parsed':7s} {'rate':6s}")
    for r in rows:
        rate = f"{r['parse_rate']:.0%}" if r["parse_rate"] is not None else "—"
        print(f"{r['study']:32s} {str(r['product'])[:26]:26s} "
             f"{str(r['hs_code']):8s} {str(r['market']):5s} "
             f"{str(r['charter_halted']):7s} {r['findings']:<9d} "
             f"{r['parsed']:<7d} {rate:6s}")
        if r["charter_halted"]:
            print(f"    ⤷ سبب التوقّف: {r['halt_reason']}")

    total_studies = len(rows)
    halted = sum(1 for r in rows if r["charter_halted"])
    agg_total = result["agg_total"]
    agg_parsed = result["agg_parsed"]

    print()
    print("── الرقمان المطلوبان ────────────────────────────────────────")
    print(f"عدد الدراسات: {total_studies} (مدوّنات حقيقية الشكل — إعادات بناء "
         "موثّقة، ليست ٢٠-٣٠ دراسة حيّة مستقلّة)")
    print(f"معدّل توقّف الميثاق (عدم تطابق HS على مستوى الدراسة): "
         f"{halted}/{total_studies} = {halted / total_studies:.0%}")
    print(f"معدّل تحويل المُطعِّم (parse rate) عبر {agg_total} نتيجة بعثة: "
         f"{agg_parsed}/{agg_total} = "
         f"{(agg_parsed / agg_total if agg_total else 0):.1%}")
    if result["agg_skipped_reasons"]:
        print("أسباب التخطّي (نتائج لم تتحوّل لسجلّ حقيقة):")
        for reason, count in sorted(result["agg_skipped_reasons"].items(),
                                    key=lambda x: -x[1]):
            print(f"  {count:4d}× {reason}")

    print()
    print("── تذكيرٌ بحدود الرقمين (اقرأ رأس هذا الملف للتفصيل) ─────────")
    print("• العيّنة مُثراةٌ بالحوادث عمداً — هذا معدّل اكتشافٍ على عيّنةٍ "
         "مصمَّمة للاختبار، لا معدّل توقّفٍ متوقَّع على دراساتٍ حقيقية عشوائية.")
    print("• كل المدوّنات مبنيّةٌ يدوياً على الشكل المتوقَّع — ١٠٠٪ يثبت "
         "غياب تعطّلٍ بنيويّ، لا صموداً أمام تنوّع مخرَجات حيّة مُلتقَطة فعلاً.")
    print("• لا تُستخدَم هذه الأرقام لتبرير ترقية الموجة ١ من SHADOW إلى WARN.")


if __name__ == "__main__":
    main()
