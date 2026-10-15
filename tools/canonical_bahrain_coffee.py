"""نتيجةُ بحثٍ عميقٍ مموّهة (البحرين × HS 090121، قهوة محمّصة) بشكل الدراسة التي
قيّمها المالك 7/10 (الدرسان ٢٩٦–٢٩٧) — **بعد** الإصلاح: نصُّ كاتبٍ سليم يسمّي
جسر الملك فهد، وسلسلةٌ مباشرة 2019–2024 مع سنةِ مرآةٍ أقدم، وتعرفةُ الاتحاد
الجمركي الخليجي 0% من الأمانة العامة، ونموُّ ناتجٍ من IMF بسنته، وقائمةُ روابط
تخلط مقهىً ومحمصةً بموزّعٍ يسمّيه المتن (Ashraf FMCG).

مموّهةٌ موسومة (نمط §10.6) — تمرّ عبر مسار العرض الإنتاجيّ الحقيقيّ، فتثبت أنّ
مستند العميل الفعليّ لدراسةٍ بهذا الشكل يُسلَّم بلا حاجبٍ وبلا عبارةٍ رفضها المالك.
`BAHRAIN_OWNER_PHRASES` هي عباراتُ البلاغ حرفياً — حقنُها في النصّ يجب أن يُحجَب.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_agents import AgentReport
from silk_data_layer import DataPoint
from silk_market_resolver import resolve_market

ref, _ = resolve_market("Bahrain")

REPORT_TEXT = """## 1. الخلاصة التنفيذية

التوصية دخول مشروط. بلغت واردات البحرين من القهوة المحمّصة نحو 9.17 مليون دولار
عام 2024 وفق UN Comtrade، وتتوزّع على عددٍ معتدل من المورّدين، فتبقى مساحةٌ لمورّدٍ
سعوديّ يدخل عبر موزّعٍ للسلع الاستهلاكية.

## 2. منهجية البحث ونطاقه

اعتمد هذا التقرير على UN Comtrade وIMF WEO والبنك الدولي وأمانة مجلس التعاون.
سنة البيانات الأساسية 2024.

## 3. نظرة عامة على السوق وحجمه

نمت واردات البحرين من القهوة المحمّصة بين 2019 و2024، والحصة السعودية صغيرة.

## 8. اللوجستيات وسلسلة الإمداد

المسار الأول برّي بالشاحنات عبر جسر الملك فهد من المنطقة الشرقية، والميناء مسارٌ
بديل. لم تُرصد مدة العبور ولا تكلفته بمصدر، وتُطلب ثلاثة عروض من شركات النقل البري.

## 10. التوصيات الاستراتيجية

أول باب دخول مرشّح هو Ashraf FMCG، ويلزم التحقق من تعامله في القهوة قبل التعاقد.
"""

#: عباراتُ بلاغ المالك (2026-10-15) حرفياً — كلٌّ منها يجب أن يُحجَب إن عاد.
BAHRAIN_OWNER_PHRASES = (
    "ميناء خليفة هو نقطة الدخول الوحيدة للبضائع.",
    "يسجل مستنتج من أرقام مرصودة خلال الفترة.",
    "المصدر reach_agent.",
    "عدد المؤشرات المرصودة المساهمة 97.",
    "استكمال بيانات الحصة السعودية و1 مكونات أخرى.",
    "يتراوح العبور بين 10 و14 يوماً قياساً على شحنات من إثيوبيا.",
)


def _f(value, source, confidence, note, year=None, status=""):
    return DataPoint(value, source, confidence, note, "2026-10-15",
                     status=status, data_year=year)


def _rep(name, findings, summary):
    return AgentReport(f"LLMAgent:{name}", findings, False, summary)


_series = [
    _f(2_930_000.0, "UN Comtrade (مرآة)", 0.6,
       "إجمالي واردات السوق HS090121 2018 (مرآة)", 2018, status="mirrored"),
    _f(4_810_000.0, "UN Comtrade", 0.9, "إجمالي واردات السوق HS090121 2019", 2019),
    _f(6_200_000.0, "UN Comtrade", 0.9, "إجمالي واردات السوق HS090121 2021", 2021),
    _f(9_170_000.0, "UN Comtrade", 0.9, "إجمالي واردات السوق HS090121 2024", 2024),
]

missions = {
    "trade_flow": _rep("trade_flow", list(_series), "تدفقات تجارية مؤكَّدة"),
    "demographics_economy": _rep("demographics_economy", [
        _f(2.8, "IMF WEO", 0.85,
           "نمو الناتج المحلي الإجمالي الحقيقي (% سنوي، IMF WEO) — BHR سنة 2024",
           2024),
        _f(0.9, "IMF WEO", 0.85,
           "التضخم — متوسط أسعار المستهلك (% سنوي، IMF WEO) — BHR سنة 2024", 2024)],
        "مؤشرات مستقرة"),
    "tariffs_agreements": _rep("tariffs_agreements", [
        _f(0.0, "GCC Secretariat", 0.9,
           "التعرفة الجمركية المطبَّقة 0% — الاتحاد الجمركي الخليجي، منشأ سعودي")],
        "إعفاءٌ جمركيٌّ خليجيّ"),
    "channels_importers": _rep("channels_importers", [
        _f("Ashraf FMCG", "بحث ويب", 0.5, "[entry_door] موزّع سلع استهلاكية")],
        "موزّع مرشّح"),
}

analyst_report = AgentReport(
    "LLMAgent:market_analyst", [_series[-1]], False, "تحليل التقاطعات مكتمل")

result = {
    "product": "قهوة محمصة", "hs_code": "090121", "year": 2024,
    "market": {"iso3": ref.iso3, "m49": ref.m49, "iso2": ref.iso2,
               "name_en": ref.name_en, "name_ar": ref.name_ar},
    "markets": [],
    "deep_research": {
        "trace_id": "sample-client-bhr-coffee",
        "missions": missions,
        "analyst": {"report": analyst_report,
                    "by_category": {"demand": [_series[-1]]},
                    "missing_categories": []},
        "verdict": {"verdict": "CONDITIONAL-GO",
                    "ai": {"verdict": "CONDITIONAL-GO", "confidence": 0.6,
                           "reasoning": "دخولٌ مشروط بتأكيد موزّع."}},
        "report": {"report": REPORT_TEXT, "review_cycles": 1,
                   "unresolved_notes": []},
        "importer_leads": {"path": "scraper", "note": "عيّنة توضيحية", "leads": [
            {"name": "Moments Café", "category": "Cafe", "address": "المنامة (نموذج)",
             "phone": "+973 1700 0001", "email": "—", "website": "—"},
            {"name": "Hub Coffee Roasters", "category": "", "address": "المنامة (نموذج)",
             "phone": "+973 1700 0002", "email": "—", "website": "—"},
            {"name": "Ashraf FMCG", "address": "", "phone": "", "email": "",
             "website": "", "maps_link": "", "source": "web_search"}]},
    },
}


def bahrain_coffee_research_blob() -> dict:
    """نسخةٌ طازجةٌ من النتيجة (لا حالةٌ مشتركةٌ بين الاختبارات)."""
    import copy
    return copy.deepcopy(result)
