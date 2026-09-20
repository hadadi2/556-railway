"""المدوّنة القانونية الحقيقية الشكل — عسل × هولندا (الموجة د-٢).

> **الغرض.** عيّنةُ المالك (الموجة د) تطلب سوقاً **أكبرُ مورّديه معيدُ تصدير**
> (بلجيكا/هولندا نمطياً) كي يُثبَت البند ٢: معيدُ التصدير يُستبعد من «المنافس
> المباشر» ويُقدَّم المصدرُ الفعلي خلفه؛ وبطاقةَ منتجٍ بسماتٍ (شهادة، هويةُ
> منشأ، شريحة) يُقارَن بعضُها بما يملكه المنافسون (البند ٤)؛ وثلاثةَ سطور أسعارٍ
> **مكتملة** (علامة + متجر + تاريخ + عبوة + عملة) فيُقرأ توثيقُ الأسعار
> مرصوداً لا ضعيفاً (البند ٥).
>
> **مموّهة** (كسائر المدوّنات): أرقامُها شكلٌ إنتاجيٌّ لا رصدٌ حيّ.

المكتبات: stdlib فقط (dicts خام).
"""
from __future__ import annotations


def _dp(value, source: str = "UN Comtrade", conf: float = 0.8,
        note: str = "", ra: str = "2026-09-01", data_year=None) -> dict:
    return {"value": value, "source": source, "confidence": conf,
            "note": note, "retrieved_at": ra, "data_year": data_year}


NLD_HONEY_PRODUCT = "عسل سدر"
NLD_HONEY_HS = "040900"

REPORT_TEXT = """## 1. الخلاصة التنفيذية
التوصية: مراقبة السوق. قاعدة الحكم قبل الأرقام: نوصي بالدخول حين تكتمل ثلاثة
جوانب من خمسة ويكون الهامش موجباً؛ وهنا سعر الحدود منخفض جداً مقارنة بتكلفة
المنتج. واردات هولندا المصرَّحة من العسل 96 مليون دولار لعام 2024.

## 2. منهجية البحث ونطاقه
اثنتا عشرة بعثة بحث، ثم محلّل شامل فكاتب التقرير. رُصدت ثلاثة أسعار رفّ
موثّقة بالعلامة والمتجر والتاريخ والعبوة.

## 3. نظرة عامة على السوق وحجمه
الواردات المصرَّحة 96 مليون دولار (2024)، بنمو تراكمي 2.1% سنوياً على ثلاث
سنوات. متوسط سعر الاستيراد الحدودي 2.85 دولار للكيلوغرام.

## 4. ديناميكيات السوق
الطلب مستقر ويميل إلى العسل العضوي وأحادي المصدر في قنوات التجزئة الراقية،
بينما تُهيمن العبوات الرخيصة الممزوجة على السلاسل الكبرى.

## 5. تحليل المستهلك والطلب
أسعار الرف المرصودة بين 4.99 و12.90 يورو للكيلوغرام: عسل ممزوج في السلاسل
الكبرى، وعسل عضوي أحادي المصدر في متاجر الأغذية الطبيعية.

## 6. المشهد التنافسي
المورّدون: بلجيكا 24%، أوكرانيا 19%، الأرجنتين 15%، السعودية أقل من 1%.
مؤشر التركّز 1320 على مستوى الدول — تنافسي غير مركّز.

## 7. التنظيم والوصول للسوق
يشترط الاتحاد الأوروبي منشأة معتمدة بموجب اللائحة 2017/625 وتوجيه العسل
2001/110. الرسوم الجمركية المطبَّقة 17.3% وفق WITS، وضريبة القيمة المضافة
على الأغذية 9%.

## 8. اللوجستيات وسلسلة الإمداد
شحن بحري من جدة إلى ميناء روتردام. زمن العبور غير متاح من مصدر منسَّق.

## 9. تقييم المخاطر
الخطر الأول سعر الحدود المنخفض الذي يضغط أي هامش لمنتج فاخر، والثاني
الرسوم 17.3% بلا اتفاقية تفضيلية.

## 10. التوصيات الاستراتيجية
أقوى حجة ضد هذا الحكم: شريحة العسل الفاخر أحادي المصدر تدفع ثلاثة أضعاف
سعر الحدود فعلاً. نردّ بأن هذه الشريحة تُدخَل عبر متاجر متخصّصة لا عبر
المستوردين الكبار الذين يرسمون متوسط الحدود.
### أرقام القرار
تفصيل البنود الخمسة في جدول أرقام القرار.
### خارطة طريق الدخول (٩٠ يوماً)
1. التحقق من إدراج المنشأة في قائمة الاتحاد الأوروبي. 2. عيّنات لثلاثة
متاجر أغذية طبيعية. 3. تسعير الرف لا الحدود.

## 11. الملاحق
UN Comtrade، البنك الدولي، WITS، بحث ويب."""


def netherlands_honey_research_blob() -> dict:
    """المدوّنةُ كما تُخزَّن وتُقرَأ — dict جديدةٌ في كلّ نداء."""
    def _m(summary, findings=None, failed=False):
        return {"agent_name": "LLMMissionAgent", "summary": summary,
                "findings": findings or [], "failed": failed}

    # البند ١ بالشكل المخزَّن: السعودية مستوردٌ صافٍ لمدخلات الفصل ٤ (أبقار
    # حية وأعلاف) — فالميزةُ لا تُدَّعى.
    raw_input_trade = _dp(
        {"kind": "raw_input_trade", "year": 2024,
         "codes": ["0102", "1214", "2309"], "label": "أبقار حية وأعلاف",
         "rows": [{"code": "0102", "exports_usd": 12_000_000.0,
                   "imports_usd": 310_000_000.0, "status": "X:stored M:stored"},
                  {"code": "1214", "exports_usd": 3_000_000.0,
                   "imports_usd": 420_000_000.0, "status": "X:stored M:stored"},
                  {"code": "2309", "exports_usd": 95_000_000.0,
                   "imports_usd": 640_000_000.0, "status": "X:stored M:stored"}],
         "exports_usd": 110_000_000.0, "imports_usd": 1_370_000_000.0,
         "net_usd": -1_260_000_000.0, "observed_codes": 3, "calls_used": 0},
        note="[commercial] صافي تجارة السعودية في المدخلات الخام (أبقار حية "
             "وأعلاف) سنة 2024: واردات ≥ صادرات على 3 من 3 رموز",
        data_year=2024)
    # البند ٢: أكبرُ مورّد (بلجيكا) ليس من كبار المصدّرين ووارداتُه ≥ صادراتِه
    # ⇒ معيدُ تصديرٍ مرجَّح والمصدرُ الفعلي خلفه أوكرانيا؛ أوكرانيا والأرجنتين
    # منتجان عالميان.
    supplier_nature = _dp(
        {"kind": "supplier_nature", "year": 2024, "topn": 5,
         "world_top_exporters": ["CHN", "NZL", "ARG", "UKR", "IND"],
         "rows": [
             {"partner": "Belgium", "share": 24.0, "iso3": "BEL",
              "world_top_exporter": False, "exports_usd": 31_000_000.0,
              "imports_usd": 46_000_000.0, "reexporter_likely": True,
              "actual_source": {"partner": "Ukraine", "iso3": "UKR",
                                "share": 41.0},
              "status": "X:stored M:stored"},
             {"partner": "Ukraine", "share": 19.0, "iso3": "UKR",
              "world_top_exporter": True, "exports_usd": 140_000_000.0,
              "imports_usd": 2_000_000.0, "reexporter_likely": False,
              "actual_source": None, "status": "X:stored M:stored"},
             {"partner": "Argentina", "share": 15.0, "iso3": "ARG",
              "world_top_exporter": True, "exports_usd": 210_000_000.0,
              "imports_usd": 500_000.0, "reexporter_likely": False,
              "actual_source": None, "status": "X:stored M:stored"}],
         "calls_used": 0, "partial": False},
        note="[commercial] طبيعة المورّدين الأكبر لسنة 2024: 3 مُقيَّم من 3، "
             "منهم 1 معيد تصدير مرجَّح — القاعدة: ليس من أعلى 5 مصدّراً "
             "عالمياً ووارداته ≥ صادراته", data_year=2024)
    missions = {
        "trade_flow": _m("واردات 96 مليون وسعر حدود 2.85 دولار/كجم (70/70)",
                         [_dp(96_000_000, note="واردات مصرَّحة 2024",
                              data_year=2024),
                          _dp(2.1, note="نمو تراكمي سنوي % على ثلاث سنوات",
                              data_year=2024),
                          _dp(2.85, note="متوسط سعر استيراد دولار/كجم 2024",
                              data_year=2024),
                          raw_input_trade]),
        # ثلاثةُ سطورٍ **مكتملة** (علامة + متجر + تاريخ + عبوة + عملة) ⇒
        # توثيقٌ مرصود؛ «bio/عضوي» تحملها علامةٌ منافسة فلا تُعلَن ميزة.
        "pricing_scout": _m("ثلاثة أسعار رف موثّقة 4.99–12.90 يورو/كجم (15/15)",
                            [_dp(4.99, "بحث ويب", 0.7,
                                 note="Albert Heijn سعر رف عبوة 450 g علامة "
                                      "AH Honing bloemen 2026-08-14 بسعر "
                                      "€4.99 للكيلوغرام"),
                             _dp(8.49, "بحث ويب", 0.7,
                                 note="Jumbo سعر رف عبوة 350 g علامة De "
                                      "Traay bio honing 2026-08-14 بسعر "
                                      "€8.49 للكيلوغرام"),
                             _dp(12.90, "بحث ويب", 0.7,
                                 note="متجر Ekoplaza سعر رف عبوة 250 g علامة "
                                      "Nature's Nectar organic honey "
                                      "2026-08-15 بسعر €12.90 للكيلوغرام")]),
        "competitors": _m("مؤشر تركّز 1320 — بلجيكا أكبر مورّد",
                          [_dp({"year": 2024, "hhi": 1320, "supplier_count": 38,
                                "top_suppliers": [
                                    {"partner": "Belgium", "share": 24.0},
                                    {"partner": "Ukraine", "share": 19.0},
                                    {"partner": "Argentina", "share": 15.0}]},
                               conf=0.9,
                               note="HS040900 مورّدو Netherlands 2024: 38 دولة "
                                    "مرصودة، مؤشر تركّز HHI=1320",
                               data_year=2024),
                           _dp(24.0, note="حصة أكبر مورد % 2024",
                               data_year=2024),
                           supplier_nature]),
        "customs_requirements": _m("منشأة معتمدة EU 2017/625 وتوجيه العسل "
                                   "2001/110", []),
        "tariffs_agreements": _m("تعريفة مطبَّقة 17.3% وضريبة أغذية 9%",
                                 [_dp(17.3, "WITS", note="تعريفة مطبَّقة %"),
                                  _dp(9.0, "Belastingdienst", 0.9,
                                      note="ضريبة القيمة المضافة على الأغذية %")]),
        "risk_news": _m("لا مخاطر حادة", []),
    }
    analyst = {
        "report": {"agent_name": "market_analyst",
                   "summary": "هولندا مراقبة — سعر حدود منخفض وشريحة فاخرة ضيقة.",
                   "findings": [], "failed": False},
        "missing_categories": [],
        "by_category": {
            "demand": [_dp(96_000_000, note="واردات 2024", data_year=2024)],
            "price_competitiveness": [_dp(12.90, "بحث ويب", 0.7,
                                          note="سعر رف عضوي يورو/كجم")],
            "entry_cost": [_dp(17.3, "WITS", note="تعريفة مطبَّقة")],
        },
    }
    verdict = {"verdict": "WATCH", "confidence": 0.55,
               "ai": {"verdict": "WATCH",
                      "reasoning": "سعر الحدود منخفض والشريحة الفاخرة ضيقة."}}
    report_out = {"report": REPORT_TEXT, "review_cycles": 2,
                  "unresolved_notes": [], "failure_reason": ""}
    return {
        "product": NLD_HONEY_PRODUCT, "hs_code": NLD_HONEY_HS, "year": None,
        "preliminary": True,
        "hs_confirmation": {"confirmed": True, "hs_code": NLD_HONEY_HS,
                            "code_desc": "عسل طبيعي", "reason": ""},
        # سماتُ التمايز (البند ٤): «organic» يملكها منافسٌ رئيسي (سطرا الأسعار
        # bio/organic) فلا تُعلَن ميزة؛ هويةُ المنشأ «سدر» والشريحةُ premium
        # لم تظهر في سطور المنافسين ⇒ مصدرُ تمايزٍ ممكن.
        "product_card": {"cost_per_unit": 6.50, "cost_currency": "USD",
                         "monthly_capacity": 8_000.0, "tier": "premium",
                         "certifications": ["organic"],
                         "origin_claim": "عسل سدر أحادي المصدر"},
        "market": {"iso3": "NLD", "m49": 528, "iso2": "NL",
                   "name_en": "Netherlands", "name_ar": "هولندا"},
        "markets": [],
        "deep_research": {"missions": missions, "analyst": analyst,
                          "verdict": verdict, "report": report_out,
                          "trace_id": "nld-honey-shape",
                          "budget_status": {"tail_degraded": False}},
        "data_economics": {"llm_calls": 34, "note": "34 نداء كلود"},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(sorted(netherlands_honey_research_blob()),
                     ensure_ascii=False))
