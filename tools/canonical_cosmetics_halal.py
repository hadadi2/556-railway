"""المدوّنتان القانونيتان — مستحضراتُ تجميل × ماليزيا وأمام اليابان (الموجة د-٣).

> **الغرض (عيّنةُ المالك، مصفوفةُ الحلال).** فئةُ الفصل ٣٣ `religion_relevance =
> affects`: الحلالُ **قد** يكون ميزةً — لكن بثلاثة شروطٍ لا اثنين.
>
> - **ماليزيا**: الحلالُ سائدٌ في السوق نفسِه (حصةٌ مسلمة ٦٤٪) ⇒ **شرطُ دخولٍ
>   لا ميزة**، مهما كان منشأُ المنافسين.
> - **اليابان**: لا قناةَ حلالٍ مرصودةً في مرجع السوق وحصتُها المسلمة ٠٫٢٪
>   والمنافسون من كوريا وفرنسا ⇒ الشرطان الأوّلان متحقّقان. والفارقُ هو
>   **الشرطُ الثالث** (تعديلُ المالك): بلا دليلِ طلبٍ خارجيٍّ مُستشهَدٍ به
>   ⇒ «لم نرصد طلباً على الحلال بعد + كيف يُعرَف»؛ ومع صفحةِ منتجٍ حلالٍ
>   معروضةٍ في متجرٍ محلّي (رابطُ http) ⇒ **ميزةٌ حقيقية**. الدالةُ الواحدة
>   تُنتج الحالتين بوسيطٍ واحد، فيُثبَت الشرطُ بالاتجاهين على المدوّنة نفسِها.
>
> **مموّهة** (كسائر المدوّنات): أرقامُها شكلٌ إنتاجيٌّ لا رصدٌ حيّ.

المكتبات: stdlib فقط (dicts خام).
"""
from __future__ import annotations

COSMETICS_HS = "330499"


def _dp(value, source: str = "UN Comtrade", conf: float = 0.8,
        note: str = "", ra: str = "2026-09-01", data_year=None,
        url: str = "") -> dict:
    out = {"value": value, "source": source, "confidence": conf,
           "note": note, "retrieved_at": ra, "data_year": data_year}
    if url:
        out["url"] = url
    return out


def _m(summary, findings=None, failed=False):
    return {"agent_name": "LLMMissionAgent", "summary": summary,
            "findings": findings or [], "failed": failed}


def _supplier_nature(year, topn, world_top, rows, n_re):
    return _dp({"kind": "supplier_nature", "year": year, "topn": topn,
                "world_top_exporters": world_top, "rows": rows,
                "calls_used": 0, "partial": False},
               note=f"[commercial] طبيعة المورّدين الأكبر لسنة {year}: "
                    f"{len(rows)} مُقيَّم من {len(rows)}، منهم {n_re} معيد "
                    f"تصدير مرجَّح — القاعدة: ليس من أعلى {topn} مصدّراً "
                    "عالمياً ووارداته ≥ صادراته", data_year=year)


def _row(partner, iso3, share, top, exp, imp, re_likely):
    return {"partner": partner, "iso3": iso3, "share": share,
            "world_top_exporter": top, "exports_usd": exp, "imports_usd": imp,
            "reexporter_likely": re_likely, "actual_source": None,
            "status": "X:stored M:stored"}


MYS_REPORT = """## 1. الخلاصة التنفيذية
التوصية: مراقبة السوق. واردات ماليزيا المصرَّحة من مستحضرات العناية 410 مليون
دولار لعام 2024، والمنافسة مفتوحة على مستوى الدول.

## 2. منهجية البحث ونطاقه
اثنتا عشرة بعثة بحث، ثم محلّل شامل فكاتب التقرير.

## 3. نظرة عامة على السوق وحجمه
الواردات المصرَّحة 410 مليون دولار (2024) بنمو تراكمي 5.1% سنوياً.

## 4. ديناميكيات السوق
نمو قنوات التجزئة الحديثة والتجارة الإلكترونية يقود الطلب على العناية اليومية.

## 5. تحليل المستهلك والطلب
المشتري الأساسي حضري بين 20 و40 سنة، ويقرأ قائمة المكوّنات قبل الشراء.

## 6. المشهد التنافسي
المورّدون: كوريا الجنوبية 26%، فرنسا 14%، تايلاند 11%. مؤشر التركّز 1180.

## 7. التنظيم والوصول للسوق
تسجيل المنتج لدى هيئة الرقابة الوطنية قبل الطرح، وشهادة المطابقة للمكوّنات
المقيَّدة. وشهادة الحلال شرط دخول تجاري في هذا السوق لا عامل تمايز.

## 8. اللوجستيات وسلسلة الإمداد
شحن بحري إلى ميناء كلانغ. زمن العبور غير متاح من مصدر منسَّق.

## 9. تقييم المخاطر
تقلّب تكلفة المكوّنات الفعّالة هو الخطر الأول، والتسجيل التنظيمي الثاني.

## 10. التوصيات الاستراتيجية
أقوى حجة ضد هذا الحكم: حجم السوق كبير والنمو مستقر. نردّ بأن الشهادة التي
يعدّها المصدّر ميزة هي هنا الحد الأدنى للدخول، فالتمايز يجب أن يأتي من غيرها.
### أرقام القرار
تفصيل البنود الخمسة في جدول أرقام القرار.
### خارطة طريق الدخول (٩٠ يوماً)
1. التسجيل التنظيمي. 2. عيّنات لموزّعين اثنين. 3. تسعير الرف لا الحدود.

## 11. الملاحق
UN Comtrade، البنك الدولي، WITS، بحث ويب."""

JPN_REPORT = """## 1. الخلاصة التنفيذية
التوصية: مراقبة السوق. واردات اليابان المصرَّحة من مستحضرات العناية 1.9 مليار
دولار لعام 2024، وسعر الرف المرصود مرتفع.

## 2. منهجية البحث ونطاقه
اثنتا عشرة بعثة بحث، ثم محلّل شامل فكاتب التقرير.

## 3. نظرة عامة على السوق وحجمه
الواردات المصرَّحة 1.9 مليار دولار (2024) بنمو تراكمي 2.6% سنوياً.

## 4. ديناميكيات السوق
سوق ناضج تقوده الصيدليات وسلاسل التجميل المتخصصة، والتجديد سريع في التركيبات.

## 5. تحليل المستهلك والطلب
المشتري يقرأ المكوّنات ويفضّل التركيبات اللطيفة، والولاء للعلامة مرتفع.

## 6. المشهد التنافسي
المورّدون: كوريا الجنوبية 31%، فرنسا 19%، الولايات المتحدة 12%. مؤشر التركّز
1420 — تنافسي غير مركّز.

## 7. التنظيم والوصول للسوق
يخضع المنتج لقانون المستحضرات الطبية والأجهزة، ويشترط مستورداً مرخَّصاً ووسماً
بالمكوّنات باللغة اليابانية.

## 8. اللوجستيات وسلسلة الإمداد
شحن بحري إلى ميناء يوكوهاما. زمن العبور غير متاح من مصدر منسَّق.

## 9. تقييم المخاطر
حاجز التسجيل التنظيمي هو الخطر الأول، وارتفاع تكلفة الدخول إلى الرف الثاني.

## 10. التوصيات الاستراتيجية
أقوى حجة ضد هذا الحكم: السوق كبير ويدفع أسعاراً مرتفعة. نردّ بأن الدخول يحتاج
مستورداً مرخَّصاً وميزة تمايز واضحة لا سعراً أدنى.
### أرقام القرار
تفصيل البنود الخمسة في جدول أرقام القرار.
### خارطة طريق الدخول (٩٠ يوماً)
1. مستورد مرخَّص. 2. ملف تسجيل كامل. 3. عيّنات لثلاث سلاسل متخصصة.

## 11. الملاحق
UN Comtrade، البنك الدولي، WITS، بحث ويب."""


def malaysia_cosmetics_research_blob() -> dict:
    """الحلالُ سائدٌ في السوق ⇒ شرطُ دخولٍ لا ميزة — dict جديدةٌ في كلّ نداء."""
    missions = {
        "trade_flow": _m("واردات 410 مليون (66/66)",
                         [_dp(410_000_000, note="واردات مصرَّحة 2024",
                              data_year=2024),
                          _dp(5.1, note="نمو تراكمي سنوي % على ثلاث سنوات",
                              data_year=2024)]),
        "pricing_scout": _m("سعر رف مرصود 39 رينغيت (9/9)",
                            [_dp(39.0, "بحث ويب", 0.7,
                                 note="Watsons سعر رف عبوة 200 ml علامة "
                                      "Nurish 2026-08-11 بسعر 39 رينغيت")]),
        "competitors": _m("مؤشر تركّز 1180",
                          [_dp({"year": 2024, "hhi": 1180, "supplier_count": 34,
                                "top_suppliers": [
                                    {"partner": "Rep. of Korea", "share": 26.0},
                                    {"partner": "France", "share": 14.0},
                                    {"partner": "Thailand", "share": 11.0}]},
                               conf=0.9, note="HS330499 مورّدو Malaysia 2024: 34 دولة مرصودة، "
                                    "مؤشر تركّز HHI=1180 (<1500 مجزَّأ)",
                               data_year=2024),
                           _dp(26.0, note="حصة أكبر مورد % 2024", data_year=2024),
                           _supplier_nature(
                               2024, 5, ["KOR", "FRA", "USA", "DEU", "CHN"],
                               [_row("Rep. of Korea", "KOR", 26.0, True,
                                     4.1e9, 3.0e8, False),
                                _row("France", "FRA", 14.0, True, 6.2e9,
                                     9.0e8, False),
                                _row("Thailand", "THA", 11.0, False, 8.0e8,
                                     4.0e8, False)], 0)]),
        "customs_requirements": _m("تسجيل المنتج قبل الطرح", []),
        "tariffs_agreements": _m("تعريفة مطبَّقة 5%",
                                 [_dp(5.0, "WITS", note="تعريفة مطبَّقة %")]),
        "risk_news": _m("لا مخاطر حادة", []),
    }
    analyst = {"report": _m("ماليزيا مراقبة — الحلال حدّ أدنى لا تمايز"),
               "missing_categories": [],
               "by_category": {"demand": [_dp(410_000_000,
                                              note="واردات 2024", data_year=2024)],
                               "price_competitiveness": [
                                   _dp(39.0, "بحث ويب", 0.7,
                                       note="سعر رف رينغيت")]}}
    return {
        "product": "مستحضرات عناية بالبشرة", "hs_code": COSMETICS_HS,
        "year": None, "preliminary": True,
        "market": {"iso3": "MYS", "m49": 458, "iso2": "MY",
                   "name_en": "Malaysia", "name_ar": "ماليزيا"},
        "markets": [],
        "deep_research": {"missions": missions, "analyst": analyst,
                          "verdict": {"verdict": "WATCH", "confidence": 0.5,
                                      "ai": {"verdict": "WATCH",
                                             "reasoning": "الحلال حدّ أدنى."}},
                          "report": {"report": MYS_REPORT, "review_cycles": 1,
                                     "unresolved_notes": [],
                                     "failure_reason": ""},
                          "trace_id": "mys-cosm",
                          "budget_status": {"tail_degraded": False}},
        "data_economics": {"llm_calls": 29, "note": "29 نداء كلود"},
    }


def japan_cosmetics_research_blob(with_halal_demand: bool = False) -> dict:
    """الشرطان الأوّلان متحقّقان؛ الثالثُ هو الفارق.

    `with_halal_demand=False` (المدوّنةُ المجمّدة): لا دليلَ طلبٍ خارجيّ ⇒ «لم
    نرصد طلباً على الحلال بعد». `True`: صفحةُ منتجٍ حلالٍ معروضةٍ في متجرٍ
    محلّي برابطٍ http ⇒ ميزةٌ حقيقية. المدوّنةُ نفسُها بالاتجاهين.
    """
    culture = [_dp("المشتري يقرأ قائمة المكوّنات قبل الشراء",
                   "تحليل البعثة", 0.5, note="ثقافة استهلاك")]
    if with_halal_demand:
        culture.append(_dp(
            {"title": "halal certified skincare at Aeon",
             "link": "https://www.aeon.co.jp/halal-skincare"},
            "Web Search", 0.7,
            note="صفحة فئة «halal skincare» معروضة في سلسلة تجزئة يابانية",
            url="https://www.aeon.co.jp/halal-skincare"))
    missions = {
        "trade_flow": _m("واردات 1.9 مليار (71/71)",
                         [_dp(1_900_000_000, note="واردات مصرَّحة 2024",
                              data_year=2024),
                          _dp(2.6, note="نمو تراكمي سنوي % على ثلاث سنوات",
                              data_year=2024)]),
        "pricing_scout": _m("سعر رف مرصود 2,480 ين (11/11)",
                            [_dp(2480.0, "بحث ويب", 0.7,
                                 note="Matsumoto Kiyoshi سعر رف عبوة 150 ml "
                                      "علامة Curel 2026-08-12 بسعر 2480 ين")]),
        "consumer_culture": _m("ثقافة استهلاك موثّقة", culture),
        "competitors": _m("مؤشر تركّز 1420",
                          [_dp({"year": 2024, "hhi": 1420, "supplier_count": 29,
                                "top_suppliers": [
                                    {"partner": "Rep. of Korea", "share": 31.0},
                                    {"partner": "France", "share": 19.0},
                                    {"partner": "USA", "share": 12.0}]},
                               conf=0.9, note="HS330499 مورّدو Japan 2024: 29 دولة مرصودة، "
                                    "مؤشر تركّز HHI=1420 (<1500 مجزَّأ)",
                               data_year=2024),
                           _dp(31.0, note="حصة أكبر مورد % 2024", data_year=2024),
                           _supplier_nature(
                               2024, 5, ["KOR", "FRA", "USA", "DEU", "CHN"],
                               [_row("Rep. of Korea", "KOR", 31.0, True,
                                     4.1e9, 3.0e8, False),
                                _row("France", "FRA", 19.0, True, 6.2e9,
                                     9.0e8, False),
                                _row("USA", "USA", 12.0, True, 3.4e9,
                                     2.1e9, False)], 0)]),
        "customs_requirements": _m("مستورد مرخَّص ووسم بالمكوّنات", []),
        "tariffs_agreements": _m("تعريفة مطبَّقة 0%",
                                 [_dp(0.0, "WITS", note="تعريفة مطبَّقة %")]),
        "risk_news": _m("لا مخاطر حادة", []),
    }
    analyst = {"report": _m("اليابان مراقبة — حاجز تسجيل وتمايز مطلوب"),
               "missing_categories": [],
               "by_category": {"demand": [_dp(1_900_000_000,
                                              note="واردات 2024", data_year=2024)],
                               "price_competitiveness": [
                                   _dp(2480.0, "بحث ويب", 0.7,
                                       note="سعر رف ين")]}}
    return {
        "product": "مستحضرات عناية بالبشرة", "hs_code": COSMETICS_HS,
        "year": None, "preliminary": True,
        "market": {"iso3": "JPN", "m49": 392, "iso2": "JP",
                   "name_en": "Japan", "name_ar": "اليابان"},
        "markets": [],
        "deep_research": {"missions": missions, "analyst": analyst,
                          "verdict": {"verdict": "WATCH", "confidence": 0.48,
                                      "ai": {"verdict": "WATCH",
                                             "reasoning": "حاجز تسجيل."}},
                          "report": {"report": JPN_REPORT, "review_cycles": 1,
                                     "unresolved_notes": [],
                                     "failure_reason": ""},
                          "trace_id": "jpn-cosm",
                          "budget_status": {"tail_degraded": False}},
        "data_economics": {"llm_calls": 30, "note": "30 نداء كلود"},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(sorted(malaysia_cosmetics_research_blob()),
                     ensure_ascii=False))
