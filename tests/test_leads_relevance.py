"""قفل الدرس ٢٦٣ — قائمة موزّعين نظيفة: لا نائبَ ولا غيرَ مرتبط.

بلاغ المالك (2026-09-19): «نظّف قائمة الموزعين: احذف غير المرتبط بالمنتج،
واحذف البيانات الافتراضية مثل mysite.com». الحالاتُ هنا **مقيسةٌ من
المدوّنات المجمّدة** لا مُختلَقة. هرمتي: صفر شبكة، صفر مفتاح، صفر إنفاق.

Run: python3 -m pytest tests/test_leads_relevance.py -q
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import silk_contact_quality as CQ                          # noqa: E402
import silk_render as R                                    # noqa: E402
import silk_reports as SR                                  # noqa: E402
import silk_style_contract as SC                           # noqa: E402
from canonical_fettuccine import fettuccine_research_blob  # noqa: E402
from canonical_libya_tahini import libya_tahini_research_blob  # noqa: E402


# ── ١) النطاقاتُ النائبة ───────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://mysite.com", "www.mysite.com/home", "http://example.com",
    "yourdomain.com", "website.com", "sitename.com", "shop.local",
    "acme",          # بلا نقطة — ليس مضيفاً عمومياً
])
def test_placeholder_sites_are_recognised(url):
    assert CQ.is_placeholder_site(url) is True


@pytest.mark.parametrize("url", [
    "https://real-company.com.tr", "http://acme.ly", "sahel-trading.ly",
    "https://www.pastificio-milano.it/contatti",
])
def test_real_sites_are_not_touched(url):
    assert CQ.is_placeholder_site(url) is False


def test_placeholder_website_is_cleared_not_the_row():
    lead = CQ.clean_contact({"name": "شركة", "website": "https://mysite.com",
                             "phone": "+218 21 000000"}, "LBY")
    assert lead["website"] == "" and lead["phone"] == "+218 21 000000"


def test_a_row_whose_only_contact_was_a_placeholder_is_dropped():
    """نائبٌ يُفرَّغ، فإن لم يبقَ اتصالٌ صار الصفُّ حشواً يُسقَط."""
    dr = {"market": {"iso3": "LBY", "name_ar": "ليبيا", "name_en": "Libya"},
          "product": "طحينة", "hs_code": "200899",
          "importer_leads": {"leads": [
              {"name": "شركة القالب", "website": "https://mysite.com"}]}}
    assert SR._clean_leads(dr["importer_leads"]["leads"], dr) == []
    assert dr["leads_dropped"][0]["why"] == "بلا أيّ وسيلة اتصال"


# ── ٢) الصلةُ بفئة المنتج — الحالةُ التي بلّغ عنها المالك ─────────────────

def test_the_auto_parts_shop_leaves_the_tahini_list():
    """direct reproduction (مدوّنة ليبيا): «مؤسسة النخبة لقطع الغيار» كانت
    تُعرَض موزّعاً لطحينة، و«شركة الساحل للتجارة» تبقى."""
    view = R.build_view(libya_tahini_research_blob())
    il = view["deep_research"]["importer_leads"]
    assert [l["name"] for l in il["leads"]] == ["شركة الساحل للتجارة"]
    assert il.get("dropped_count") == 1


def test_the_same_shop_stays_when_the_product_is_auto_parts():
    """المِصفاةُ بمحورين لا بقائمةِ منعٍ عامّة: النشاطُ نفسُه مرتبطٌ حين
    يكون المنتجُ من فئته (وإلا أسقطنا الرابطَ الصحيح لمصدّر قطع غيار)."""
    ok, why = SC.lead_relevant_to_product(
        {"name": "متجر قطع غيار", "category": "auto parts store"},
        "870899", "قطع غيار", "EGY")
    assert ok is True and why == ""


def test_a_generic_trader_is_never_dropped_for_lacking_product_words():
    ok, _ = SC.lead_relevant_to_product(
        {"name": "Al Rashid General Trading", "category": "trading company"},
        "080410", "تمور", "ARE")
    assert ok is True


def test_an_unknown_activity_passes_rather_than_being_guessed_away():
    """الجهلُ بالتسمية ليس دليلَ عدمِ صلة — سياسةُ الريبو القائمة."""
    ok, _ = SC.lead_relevant_to_product(
        {"name": "Société Générale de Négoce", "category": "négociant"},
        "080410", "تمور", "MAR")
    assert ok is True


# ── ٣) لغةُ السوق تُبقي موزّعاً لا تحذفه ──────────────────────────────────

def test_local_language_terms_keep_a_real_local_distributor():
    """«Pastificio Milano Srl» صانعُ معكرونة إيطاليّ — بلا كلمةٍ عربيةٍ ولا
    إنجليزيةٍ في اسمه. بلا مفرداتِ لغةِ السوق كان يُحذَف."""
    assert "pastificio" in SC.product_terms("منتج غذائي/زراعي", "it")
    ok, _ = SC.lead_relevant_to_product(
        {"name": "Pastificio Milano Srl"}, "190219", "معكرونة", "ITA")
    assert ok is True


def test_a_missing_language_row_is_a_declared_skip_not_a_guess():
    assert SC.product_terms("منتج غذائي/زراعي", "xx-unknown") == ()


def test_the_italian_codex_keeps_its_local_maker():
    view = R.build_view(fettuccine_research_blob())
    names = [l["name"] for l in
             view["deep_research"]["importer_leads"]["leads"]]
    assert "Pastificio Milano Srl" in names


# ── ٤) القائمةُ الفارغة تقول أيَّ فراغٍ هي ────────────────────────────────

def _filtered_only_view():
    blob = libya_tahini_research_blob()
    blob["deep_research"]["importer_leads"]["leads"] = [
        l for l in blob["deep_research"]["importer_leads"]["leads"]
        if "قطع الغيار" in l["name"]]
    return R.build_view(blob)


def test_an_emptied_by_filtering_list_says_so_not_unavailable():
    """«القائمة غير متاحة» تقول للعميل إنّ السوق بلا موزّعين مرصودين — وهو
    غيرُ صحيحٍ حين رُصدوا واستُبعدوا. الجملتان تفترقان."""
    md = SR.render_markdown(_filtered_only_view())
    assert "لم نجد موزّعاً مرتبطاً بهذا المنتج" in md
    assert "القائمة غير متاحة" not in md


def test_the_excluded_count_is_for_the_auditor_only():
    view = _filtered_only_view()
    assert "استُبعدت" not in SR.render_markdown(view)
    view["internal"] = True
    assert "استُبعدت 1 جهة" in SR.render_markdown(view)


def test_a_genuinely_empty_search_still_says_unavailable():
    dr = {"importer_leads": {"leads": []}}
    assert SR._leads_empty_line(dr, "ar").endswith("القائمة غير متاحة")


# ── ٥) حصادُ القياس قبل الشحن ─────────────────────────────────────────────

def test_customs_prose_words_do_not_mark_an_unrelated_lead_relevant():
    """وصفُ البند الجمركيّ نثرٌ عامّ: وصفُ HS200899 يحمل «parts» فطابق
    «auto parts store» وأبقى رابطاً لا صلةَ له. الكلماتُ المنسَّقة وحدَها."""
    words = SC._product_words("200899", "طحينة", "LBY")
    assert "parts" not in words and "other" not in words
    ok, _ = SC.lead_relevant_to_product(
        {"name": "X", "category": "auto parts store"}, "200899", "طحينة",
        "LBY")
    assert ok is False


def test_an_unknown_product_category_never_drops_a_lead():
    """لا حذفَ بجهلِ الطرفين: رمزٌ غائبٌ = لا محورَ مقارنة."""
    ok, why = SC.lead_relevant_to_product(
        {"name": "X", "category": "food broker"}, None, "", "")
    assert ok is True and why == ""


# ── ٦) حصادُ المراجعة الذاتية الثانية (§58) ───────────────────────────────

def _view_with_named_lead():
    """جهةٌ لا يسمح نشاطُها لكنّ **متنَ التقرير يوصي بها** بالاسم."""
    blob = libya_tahini_research_blob()
    dr = blob["deep_research"]
    dr["importer_leads"]["leads"] = [{
        "name": "مكتب الوفاء للمحاماة", "category": "law firm",
        "phone": "+218 21 111111", "address": "طرابلس، ليبيا"}]
    dr["report"]["report"] = (dr["report"]["report"]
                              + "\n\nنوصي بالتعاقد عبر مكتب الوفاء للمحاماة.")
    return R.build_view(blob)


def test_a_named_lead_is_kept_as_a_candidate_not_immune_to_a_clear_mismatch():
    """قفلٌ محدَّث معلن (تقرير ٧ §4.4، قرار المالك «أصلح كل مشاكل التقرير»):
    ذكرُ الاسم في المتن ليس دليلَ صلةٍ مستقلّاً. مكتبُ محاماةٍ ليس طرفاً
    تجارياً أيّاً كان ما يقوله المتن ⇒ يُسقَط؛ وتاجرٌ عامّ مسمّى يبقى بحالة
    «مرشّحٌ يحتاج تحققاً» لا مشترياً مؤكَّداً."""
    il = _view_with_named_lead()["deep_research"]["importer_leads"]
    assert [l["name"] for l in il["leads"]] == []
    dr = {"market": {"iso3": "LBY", "name_ar": "ليبيا", "name_en": "Libya"},
          "product": "طحينة", "hs_code": "200899",
          "report": {"text": "نوصي بالتعامل مع شركة الوفاء للتجارة."}}
    kept = SR._clean_leads([{"name": "شركة الوفاء للتجارة",
                             "category": "trading company",
                             "phone": "+218 21 111111",
                             "address": "طرابلس، ليبيا"}], dr)
    assert [k["name"] for k in kept] == ["شركة الوفاء للتجارة"]
    assert kept[0]["evidence_status"] == "named_unverified"


def test_every_drop_path_is_counted_for_the_auditor():
    """المراجعة #2: فرعُ قائمةِ السماح كان يُسقِط بلا تسجيل، فتُطبَع جملةُ
    «غير متاحة» على قائمةٍ أفرغتها المِصفاة."""
    dr = {"market": {"iso3": "LBY", "name_ar": "ليبيا", "name_en": "Libya"},
          "product": "طحينة", "hs_code": "200899",
          "importer_leads": {"leads": [
              {"name": "مكتب المحاماة", "category": "law firm",
               "phone": "+218 21 222222", "address": "طرابلس، ليبيا"}]}}
    assert SR._clean_leads(dr["importer_leads"]["leads"], dr) == []
    assert dr["leads_dropped"], "إسقاطٌ بلا تسجيل"


def test_internal_drop_reasons_never_ride_in_the_view():
    """المراجعة #4: أسماءُ الجهات المرفوضة وتعليلُها الداخليّ كانت تُسلَّم
    في JSON عرضِ العميل وتُلتزَم في المدوّنات — العددُ وحدَه يخرج."""
    import json
    view = R.build_view(libya_tahini_research_blob())
    il = view["deep_research"]["importer_leads"]
    assert il.get("dropped_count") == 1 and "dropped" not in il
    assert "يخدم فئة" not in json.dumps(view, ensure_ascii=False, default=str)


def test_the_writer_bundle_uses_the_same_two_axes():
    """المراجعة #3: حزمةُ الكاتب كانت تُنقّى بلا منتجٍ ولا رمز، فيذكر السردُ
    جهةً يحذفها الجدول."""
    import inspect
    import silk_writer_handoff
    src = inspect.getsource(silk_writer_handoff.writer_reports)
    assert '"product": product' in src and '"hs_code": hs_code' in src
