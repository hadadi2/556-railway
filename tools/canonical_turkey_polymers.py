"""المدوّنة القانونية الحقيقية الشكل — بوليمرات بروبيلين × تركيا (الموجة د-٢).

> **الغرض.** المدوّناتُ الستّ عشرة كلُّها أغذية؛ عيّنةُ المالك (الموجة د)
> تطلب **فئةً صناعيةً** (فصل ٣٩ ⇒ `religion_relevance = none`: صفرُ ذكرٍ
> دينيّ) يظهر فيها **البند ١ (ميزة التكلفة)** من صافي تجارة المدخلات الخام
> (٢٩٠١/٢٧١١/٢٩٠٢) بالشكل المخزَّن الذي تكتبه `silk_commercial_analysis`
> في اكتشافات البعثة — فلا شبكةَ في الاختبار ولا تُترك الاستنتاجاتُ ناقصةً على
> كلّ العيّنة.
>
> **مموّهة** (كسائر المدوّنات): أرقامُها شكلٌ إنتاجيٌّ لا رصدٌ حيّ، ولا تُقدَّم
> قياساً لسوقٍ حقيقي.

المكتبات: stdlib فقط (dicts خام).
"""
from __future__ import annotations


def _dp(value, source: str = "UN Comtrade", conf: float = 0.8,
        note: str = "", ra: str = "2026-09-01", data_year=None) -> dict:
    return {"value": value, "source": source, "confidence": conf,
            "note": note, "retrieved_at": ra, "data_year": data_year}


TURKEY_PRODUCT = "بولي بروبيلين"
TURKEY_HS = "390210"

REPORT_TEXT = """## 1. الخلاصة التنفيذية
التوصية: دخول مشروط. قاعدة الحكم قبل الأرقام: نوصي بالدخول حين تكتمل ثلاثة
جوانب من خمسة ويكون الهامش موجباً. واردات تركيا المصرَّحة من البولي بروبيلين
2.1 مليار دولار لعام 2024، والمنافسة على مستوى الدول مفتوحة.

## 2. منهجية البحث ونطاقه
اثنتا عشرة بعثة بحث، ثم محلّل شامل فكاتب التقرير. رُصد سعر مصنع محلي واحد
بلا تاريخ نشر، فبقي توثيق الأسعار أدنى من المطلوب.

## 3. نظرة عامة على السوق وحجمه
الواردات المصرَّحة 2.1 مليار دولار (2024)، بنمو تراكمي 3.2% سنوياً على ثلاث
سنوات. متوسط سعر الاستيراد الحدودي 1.18 دولار للكيلوغرام.

## 4. ديناميكيات السوق
الطلب مدفوع بصناعات التغليف والسيارات والمنسوجات غير المنسوجة، ويتبع دورة
البناء والتصدير الصناعي التركي.

## 5. تحليل المستهلك والطلب
المشتري صناعي لا مستهلك نهائي: مصانع التغليف والخيوط تشتري بعقود ربع سنوية
وتطلب شهادة تحليل لكل دفعة.

## 6. المشهد التنافسي
المورّدون: السعودية 31%، كوريا الجنوبية 14%، بلجيكا 9%، اليونان 6%. مؤشر
التركّز 1560 على مستوى الدول — تنافسي معتدل.

## 7. التنظيم والوصول للسوق
تشترط تركيا مطابقة سلامة المنتج عبر معهد المواصفات التركي للفئات الخاضعة،
وتُطبَّق ضريبة القيمة المضافة 20% على الاستيراد. الرسوم الجمركية المطبَّقة
6.5% وفق WITS.

## 8. اللوجستيات وسلسلة الإمداد
شحن بحري من الجبيل إلى ميناء مرسين أو أمبارلي. زمن العبور غير متاح من مصدر
منسَّق.

## 9. تقييم المخاطر
سعر الصرف الخطر الأول: الليرة تفقد قيمتها فتُسعَّر العقود بالدولار. والثاني
تقلّب سعر البروبيلين العالمي الذي ينتقل إلى سعر الحبيبات مباشرة. وحين تُحسب
سلسلة التكلفة كاملةً بالرسوم والضريبة، يقع أقصى سعر مصنع قابل للمنافسة دون
متوسط سعر الاستيراد المرصود — ولا يصلح هذا الرقم أساساً للتفاوض.

## 10. التوصيات الاستراتيجية
أقوى حجة ضد هذا الحكم: المورّد السعودي حاضر أصلاً بحصة كبيرة، فالدخول لمصدّر
جديد يزاحم مواطنه لا المنافس الأجنبي. نردّ بأن الحصة على مستوى الدولة لا
تقول شيئاً عن الدرجات (grades) الفارغة في السوق.
### أرقام القرار
تفصيل البنود الخمسة في جدول أرقام القرار.
### خارطة طريق الدخول (٩٠ يوماً)
1. عرض شحن رسمي لممر الجبيل–مرسين. 2. عيّنات مع شهادة تحليل لثلاثة مصانع
تغليف. 3. عقد ربع سنوي بالدولار.

## 11. الملاحق
UN Comtrade، البنك الدولي، WITS، بحث ويب."""


def turkey_polymers_research_blob() -> dict:
    """المدوّنةُ كما تُخزَّن وتُقرَأ — dict جديدةٌ في كلّ نداء."""
    def _m(summary, findings=None, failed=False):
        return {"agent_name": "LLMMissionAgent", "summary": summary,
                "findings": findings or [], "failed": failed}

    # اكتشافُ البند ١ بالشكل الذي تكتبه `augment_raw_input_trade` حرفياً:
    # قيمةٌ dict بـ`kind` + إبرةُ `[commercial]` في الملاحظة.
    raw_input_trade = _dp(
        {"kind": "raw_input_trade", "year": 2024,
         "codes": ["2901", "2711", "2902"], "label": "هيدروكربونات وغازات نفطية",
         "rows": [{"code": "2901", "exports_usd": 3_900_000_000.0,
                   "imports_usd": 120_000_000.0, "status": "X:stored M:stored"},
                  {"code": "2711", "exports_usd": 9_800_000_000.0,
                   "imports_usd": 210_000_000.0, "status": "X:stored M:stored"},
                  {"code": "2902", "exports_usd": 2_600_000_000.0,
                   "imports_usd": 340_000_000.0, "status": "X:stored M:stored"}],
         "exports_usd": 16_300_000_000.0, "imports_usd": 670_000_000.0,
         "net_usd": 15_630_000_000.0, "observed_codes": 3, "calls_used": 0},
        note="[commercial] صافي تجارة السعودية في المدخلات الخام (هيدروكربونات "
             "وغازات نفطية) سنة 2024: صادرات > واردات على 3 من 3 رموز",
        data_year=2024)
    # اكتشافُ البند ٢ بالشكل الذي تكتبه `augment_supplier_nature`: كوريا منتجٌ
    # عالمي؛ بلجيكا واليونان ليستا من كبار المصدّرين ووارداتُهما ≥ صادراتِهما
    # ⇒ معيدا تصديرٍ مرجَّحان، والمصدرُ الفعلي خلف بلجيكا ألمانيا.
    supplier_nature = _dp(
        {"kind": "supplier_nature", "year": 2024, "topn": 5,
         "world_top_exporters": ["SAU", "KOR", "USA", "DEU", "SGP"],
         "rows": [
             {"partner": "Rep. of Korea", "share": 14.0, "iso3": "KOR",
              "world_top_exporter": True, "exports_usd": 5_100_000_000.0,
              "imports_usd": 380_000_000.0, "reexporter_likely": False,
              "actual_source": None, "status": "X:stored M:stored"},
             {"partner": "Belgium", "share": 9.0, "iso3": "BEL",
              "world_top_exporter": False, "exports_usd": 210_000_000.0,
              "imports_usd": 260_000_000.0, "reexporter_likely": True,
              "actual_source": {"partner": "Germany", "iso3": "DEU",
                                "share": 34.0},
              "status": "X:stored M:stored"},
             {"partner": "Greece", "share": 6.0, "iso3": "GRC",
              "world_top_exporter": False, "exports_usd": 40_000_000.0,
              "imports_usd": 95_000_000.0, "reexporter_likely": True,
              "actual_source": {"partner": "Italy", "iso3": "ITA",
                                "share": 29.0},
              "status": "X:stored M:stored"}],
         "calls_used": 0, "partial": False},
        note="[commercial] طبيعة المورّدين الأكبر لسنة 2024: 3 مُقيَّم من 3، "
             "منهم 2 معيد تصدير مرجَّح — القاعدة: ليس من أعلى 5 مصدّراً "
             "عالمياً ووارداته ≥ صادراته", data_year=2024)
    missions = {
        "trade_flow": _m("واردات 2.1 مليار وسعر حدود 1.18 دولار/كجم (70/70)",
                         [_dp(2_100_000_000, note="واردات مصرَّحة 2024",
                              data_year=2024),
                          _dp(3.2, note="نمو تراكمي سنوي % على ثلاث سنوات",
                              data_year=2024),
                          _dp(1.18, note="متوسط سعر استيراد دولار/كجم 2024",
                              data_year=2024),
                          raw_input_trade]),
        # سطرُ سعرٍ واحدٌ بلا تاريخ ⇒ توثيقٌ ضعيف (البند ٥) — عمداً.
        "pricing_scout": _m("سعر مصنع محلي 1.35 دولار/كجم (8/8)",
                            [_dp(1.35, "بحث ويب", 0.6,
                                 note="سعر رف صناعي محلي عبوة 25 kg بسعر "
                                      "1.35 دولار للكيلوغرام (مصنع تغليف "
                                      "في بورصة، بلا تاريخ نشر)")]),
        "competitors": _m("مؤشر تركّز 1560 — السعودية أكبر مورّد",
                          [_dp({"year": 2024, "hhi": 1560, "supplier_count": 41,
                                "top_suppliers": [
                                    {"partner": "Saudi Arabia", "share": 31.0},
                                    {"partner": "Rep. of Korea", "share": 14.0},
                                    {"partner": "Belgium", "share": 9.0},
                                    {"partner": "Greece", "share": 6.0}]},
                               conf=0.9,
                               note="HS390210 مورّدو Türkiye 2024: 41 دولة "
                                    "مرصودة، مؤشر تركّز HHI=1560",
                               data_year=2024),
                           _dp(31.0, note="حصة أكبر مورد % 2024",
                               data_year=2024),
                           supplier_nature]),
        "customs_requirements": _m("مطابقة TSE للفئات الخاضعة", []),
        "tariffs_agreements": _m("تعريفة مطبَّقة 6.5% وضريبة 20%",
                                 [_dp(6.5, "WITS", note="تعريفة مطبَّقة %"),
                                  _dp(20.0, "Gelir İdaresi Başkanlığı", 0.9,
                                      note="ضريبة القيمة المضافة %")]),
        "risk_news": _m("تقلّب الليرة", []),
    }
    analyst = {
        "report": {"agent_name": "market_analyst",
                   "summary": "تركيا دخول مشروط — مدخل خام محلي ومنافسة معتدلة.",
                   "findings": [], "failed": False},
        "missing_categories": [],
        "by_category": {
            "demand": [_dp(2_100_000_000, note="واردات 2024", data_year=2024)],
            "price_competitiveness": [_dp(1.35, "بحث ويب", 0.6,
                                          note="سعر مصنع محلي دولار/كجم")],
            "entry_cost": [_dp(6.5, "WITS", note="تعريفة مطبَّقة")],
        },
    }
    verdict = {"verdict": "CONDITIONAL-GO", "confidence": 0.62,
               "ai": {"verdict": "CONDITIONAL-GO",
                      "reasoning": "المدخل الخام محلي والمنافسة معتدلة، "
                                   "والشرط عقد بالدولار."}}
    report_out = {"report": REPORT_TEXT, "review_cycles": 1,
                  "unresolved_notes": [], "failure_reason": ""}
    return {
        "product": TURKEY_PRODUCT, "hs_code": TURKEY_HS, "year": None,
        "preliminary": True,
        "hs_confirmation": {"confirmed": True, "hs_code": TURKEY_HS,
                            "code_desc": "بولي بروبيلين بأشكاله الأولية",
                            "reason": ""},
        # بطاقةٌ بلا سماتِ تمايز (لا شهادات ولا هوية منشأ) ⇒ «التمايز» فجوةٌ
        # معلنةٌ تُغلَق بإدخالها — لا تخمين.
        "product_card": {"cost_per_unit": 0.95, "cost_currency": "USD",
                         "monthly_capacity": 4_000_000.0},
        "market": {"iso3": "TUR", "m49": 792, "iso2": "TR",
                   "name_en": "Türkiye", "name_ar": "تركيا"},
        "markets": [],
        "deep_research": {"missions": missions, "analyst": analyst,
                          "verdict": verdict, "report": report_out,
                          "trace_id": "tur-shape",
                          "budget_status": {"tail_degraded": False}},
        "data_economics": {"llm_calls": 31, "note": "31 نداء كلود"},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(sorted(turkey_polymers_research_blob()), ensure_ascii=False))
