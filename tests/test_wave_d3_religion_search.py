"""الموجة د-٣ — الدين بفئة المنتج، وميزةُ الحلال بثلاثة شروط، ومصطلحاتُ البحث.

بلاغُ المالك (2026-09-19، الموجة د، البندان ٣ و٨): «لا يُذكر الدين إلا حين
يؤثّر فعلاً في الفئة… التركيبة الدينية ليست طلباً… الحلال ميزة فقط بثلاثة
شروط، والثالث دليلُ طلبٍ فعليّ **من مصدر خارجي مستشهَد به فقط، لا من نثر
بعثة**، وقيمةُ Trends تُقارن نسبياً بقيمة المنتج وحدَه»؛ و«مصطلحات البحث
بلغة السوق والإنجليزية والوصف التجاري — لا ترجمة حرفية لوصف البند».

test-first: كُتب قبل التنفيذ. هرمتي: صفر شبكة، صفر مفتاح، صفر إنفاق.
Run: python3 -m pytest tests/test_wave_d3_religion_search.py -q
"""
import importlib
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import silk_ai_judge as J                                     # noqa: E402
import silk_commercial_analysis as CA                         # noqa: E402
import silk_fact_ledger as L                                  # noqa: E402
import silk_missions as M                                     # noqa: E402
import silk_render as R                                       # noqa: E402
import silk_reports as SR                                     # noqa: E402
import silk_style_contract as SC                              # noqa: E402
from gen_verdict_baseline import CANONICAL_BLOBS              # noqa: E402
from silk_market_resolver import resolve_market                # noqa: E402

#: ألفاظُ الدين في أيّ مخرَج — نفسُ عائلة حارس المسوّدة.
RELIGIOUS = re.compile(r"حلال|رمضان|العيدين|المسلمين|المسلمة|إسلامي|"
                       r"halal|ramadan|muslim", re.IGNORECASE)


def _view(key):
    mod, fn = CANONICAL_BLOBS[key]
    return R.build_view(getattr(importlib.import_module(mod), fn)())


def _dp(value, note="", source="Web Search", url=""):
    return {"value": value, "source": source, "confidence": 0.7,
            "note": note, "retrieved_at": "2026-09-01", "url": url}


def _missions(**kw):
    return {k: {"agent_name": "LLMMissionAgent", "summary": "",
                "findings": v, "failed": False} for k, v in kw.items()}


# ── ٣) الدينُ بفئة المنتج — لا لفظَ في فئةٍ لا صلةَ له بها ──────────────────

@pytest.mark.parametrize("hs,expected", [
    ("200811", "affects"),      # محضّرات فواكه — إضافاتٌ ونكهات
    ("020230", "affects"),      # لحوم
    ("080410", "inherent"),     # تمور — حلالٌ بطبيعته
    ("390210", "none"),         # بوليمرات — صناعيّ
    ("720610", "none"),         # حديد
    ("990000", None),           # فصلٌ غيرُ مصنَّف — لا حكم
])
def test_category_decides_whether_religion_is_mentioned_at_all(hs, expected):
    assert J.religion_relevance(hs) == expected


def test_the_third_condition_parameter_comes_from_the_data_file():
    assert J.halal_demand_min_ratio("200811") == 0.2      # فئةُ affects
    assert J.halal_demand_min_ratio("080410") is None     # لا شرطَ يُقاس
    assert J.halal_demand_min_ratio("390210") is None
    src = open(os.path.join(_ROOT, "data", "hs_category_l1.csv"),
               encoding="utf-8").read()
    assert "halal_demand_min_ratio" in src


def test_a_neutral_category_strips_religion_from_every_mission_prompt():
    for key in ("consumer_culture", "demographics_economy", "demand_trends",
                "opportunity_gaps", "pricing_scout"):
        gated = M.gate_religion(M.MISSIONS[key], "390210")["instructions"]
        assert not RELIGIOUS.search(gated), key


def test_a_food_category_prompt_is_byte_identical():
    """لا انحرافَ eval لفئةٍ للدين صلةٌ بها — ولا لفصلٍ غيرِ مصنَّف."""
    for key in M.MISSIONS:
        for hs in ("080410", "200811", "990000", ""):
            assert (M.gate_religion(M.MISSIONS[key], hs)["instructions"]
                    == M.MISSIONS[key]["instructions"]), (key, hs)


def test_the_writer_prompt_is_gated_by_the_same_one_table():
    src = open(os.path.join(_ROOT, "silk_ai_judge.py"), encoding="utf-8").read()
    assert "gate_religion_text(\"\\n\\n\".join(parts), hs_code)" in src
    sample = ("طبقات: (حلال، عضوي، تجارة عادلة).** ثم موزّع أغذية "
              "متخصص يخدم القناة الحلال بدل محاولة اختراق التجزئة العامة ")
    assert not RELIGIOUS.search(J.gate_religion_text(sample, "390210"))
    assert J.gate_religion_text(sample, "080410") == sample


def test_the_analyst_no_longer_teaches_religion_as_demand_in_any_category():
    src = open(os.path.join(_ROOT, "silk_market_analyst.py"),
               encoding="utf-8").read()
    assert "نسبة السكان المسلمين × واردات المنتج" not in src
    assert "السكان ونسبة المسلمين عند" not in src
    # والقاعدةُ المضادّة تبقى حيّة
    assert "نسبة دينية لا يثبتان وجود مشترين" in src


def test_religious_composition_is_never_a_demand_segment_or_an_opportunity():
    src = open(os.path.join(_ROOT, "silk_render.py"), encoding="utf-8").read()
    assert "شريحة الحلال/رمضان" not in src
    assert "موسمية رمضان/العيدين فرصة ذروة طلب" not in src


def test_a_draft_that_mentions_religion_in_a_neutral_category_is_returned():
    led = {"hs_code": "390210", "entries": {}}
    issues = L.draft_issues("السوق يطلب شهادة حلال للحبيبات. النمو 3%.", led)
    assert any("لفظٌ دينيّ" in i for i in issues)
    assert L.draft_issues("السوق يطلب شهادة حلال.",
                          {"hs_code": "040900", "entries": {}}) == []
    # سجلٌّ بلا رمز = لا حكم (لا كتمَ ذكرٍ بناءً على جهل بالفئة)
    assert L.draft_issues("شهادة حلال.", {"entries": {}}) == []


def test_the_ledger_carries_the_code_the_guard_needs():
    assert _view("turkey_polymers")["ledger"]["hs_code"] == "390210"


# ── ميزةُ الحلال: ثلاثةُ شروطٍ لا اثنان ─────────────────────────────────────

def _supplier_rows(*iso3):
    return [{"iso3": c, "partner": c, "share": 10.0} for c in iso3]


def test_an_industrial_category_says_nothing_about_religion():
    hp = CA.halal_positioning("390210", "TUR", {}, _supplier_rows("DEU"))
    assert hp["status"] == "not_applicable" and hp["evidence"] == []


def test_an_inherently_halal_product_is_an_entry_condition_not_an_advantage():
    hp = CA.halal_positioning("080410", "DEU", {}, _supplier_rows("TUN"))
    assert hp["status"] == "entry_condition"
    assert "شرطُ دخولٍ" in " ".join(hp["evidence"])


def test_a_market_where_halal_is_prevalent_gives_no_advantage():
    hp = CA.halal_positioning("200811", "MYS", {}, _supplier_rows("DEU", "NLD"))
    assert hp["status"] == "entry_condition"
    assert hp["conditions"]["no_local_halal_channel"] is False
    assert "سائدٌ في السوق" in " ".join(hp["evidence"])


def test_an_observed_local_halal_channel_gives_no_advantage():
    hp = CA.halal_positioning("200811", "NLD", {}, _supplier_rows("DEU", "BEL"))
    assert hp["status"] == "entry_condition"
    assert CA.local_halal_channel("NLD") and not CA.local_halal_channel("TUR")


def test_germany_has_an_observed_halal_channel_so_no_advantage_there():
    """المدوّنةُ المتوقَّعة في الخطة كانت «الشرطان الأوّلان متحقّقان في ألمانيا» —
    والمرجعُ يقول غيرَ ذلك: `ethnic_retail` لألمانيا «Turkish/Arab grocers».
    القاعدةُ تتبع البيانات لا التوقّع."""
    hp = CA.halal_positioning("200811", "DEU", {}, _supplier_rows("CHN", "USA"))
    assert hp["status"] == "entry_condition"
    assert hp["conditions"]["no_local_halal_channel"] is False


def test_two_conditions_without_demand_evidence_is_not_an_advantage():
    """تعديلُ المالك: الشرطُ الثالث إلزاميّ — غيابُه يُقال ويُسمّى سبيلُ إغلاقه.

    اليابانُ سوقُ الاختبار: لا قناةَ حلالٍ مرصودةً في المرجع وحصتُها المسلمة
    0.2% — فالشرطان الأوّلان متحقّقان بالبيانات لا بالتوقّع.
    """
    hp = CA.halal_positioning("200811", "JPN", {}, _supplier_rows("CHN", "USA"))
    assert hp["status"] == "no_demand_evidence"
    assert hp["conditions"] == {"rivals_not_halal_origin": True,
                                "no_local_halal_channel": True,
                                "demand_evidence": False}
    assert "لم نرصد طلباً" in hp["how_to_close"]


def test_an_official_requirement_row_is_not_demand_evidence():
    """مراجعةٌ ذاتية §58: صفُّ شهادة الحلال الرسميّ (بل واشتراطُ الخروج
    السعوديّ) يحمل الكلمةَ ورابطاً رسمياً في **كلّ** سوق — فكان يُسقِط الشرطَ
    الثالث كلَّه. الدليلُ من **أداةِ سوقٍ في بعثةٍ سوقية** حصراً."""
    req = _missions(customs_requirements=[
        _dp("شهادة حلال إلزامية", source="Silk L1 requirements reference",
            note="https://sfda.gov.sa حلال")])
    hp = CA.halal_positioning("200811", "JPN", req, _supplier_rows("CHN"))
    assert hp["status"] == "no_demand_evidence"


def test_an_unlisted_market_is_unknown_not_channel_free():
    hp = CA.halal_positioning("200811", "XXX", {}, _supplier_rows("CHN"))
    assert hp["conditions"]["no_local_halal_channel"] is None
    assert hp["status"] == "entry_condition"
    assert "لم يُقَس" in " ".join(hp["evidence"])


def test_an_unmeasured_first_condition_is_written_weak_not_observed():
    log = {}
    CA.fill_insights({"missions": {}}, lambda e: log.__setitem__(e["key"], e),
                     hs_code="200811", market_iso3="JPN")
    e = log["halal_positioning"]
    assert e["status"] == L.WEAK and "لم تُرصد بعد" in e["note"]


def test_the_draft_guard_does_not_fire_on_a_delivered_shipment_or_a_bank():
    led = {"hs_code": "390210", "entries": {}}
    assert L.draft_issues("وصلت الشحنة المسلمة عبر البنك الإسلامي للتنمية.",
                          led) == []


def test_a_neutral_category_is_not_marked_incomplete_for_an_unasked_metric():
    """مراجعةٌ ذاتية §58: إسقاطُ المعطيين الدينيين كان يخفض تغطيةَ وكيل الطلب
    إلى 0.67 بلا فجوةٍ معلنة — «ناقصٌ» ما لا يُسأل عنه أصلاً."""
    import silk_research as RS
    agent = RS.ConsumerDemandAgent()
    assert len(agent.expected_for({"hs6": "390210"})) == 4
    assert len(agent.expected_for({"hs6": "080410"})) == 6
    assert len(agent.expected_for({})) == 6


def test_mission_prose_mentioning_halal_is_not_evidence_only_a_cited_source_is():
    """الاستشهادُ بنثر بعثةٍ دائريّ — موجّهُها يدفعها إلى ذكر الحلال."""
    prose = _missions(consumer_culture=[
        _dp("السوق يطلب منتجات حلال بقوة", note="انطباع البعثة", source="تحليل")])
    hp = CA.halal_positioning("200811", "JPN", prose, _supplier_rows("CHN"))
    assert hp["status"] == "no_demand_evidence"
    cited = _missions(consumer_culture=[
        _dp({"title": "halal dates at Aeon", "link": "https://aeon.jp/halal"},
            note="صفحة منتج", source="Web Search (Serper)")])
    hp2 = CA.halal_positioning("200811", "JPN", cited, _supplier_rows("CHN"))
    assert hp2["status"] == "advantage"
    assert hp2["conditions"]["demand_evidence"] is True


def test_the_trends_signal_is_relative_to_the_product_alone_not_above_zero():
    weak = _missions(demand_trends=[
        _dp(40.0, note="اهتمام البحث Google Trends — تمور"),
        _dp(4.0, note="اهتمام البحث Google Trends — حلال تمور")])
    hp = CA.halal_positioning("200811", "JPN", weak, _supplier_rows("CHN"))
    assert hp["status"] == "no_demand_evidence"          # 0.1 < 0.2
    assert "دون المعلمة المعلنة" in " ".join(hp["evidence"])
    strong = _missions(demand_trends=[
        _dp(40.0, note="اهتمام البحث Google Trends — تمور"),
        _dp(12.0, note="اهتمام البحث Google Trends — حلال تمور")])
    hp2 = CA.halal_positioning("200811", "JPN", strong, _supplier_rows("CHN"))
    assert hp2["status"] == "advantage"                  # 0.3 ≥ 0.2
    assert "بلغت المعلمةَ المعلنة" in " ".join(hp2["evidence"])


def test_unknown_supplier_origins_never_assume_the_first_condition():
    hp = CA.halal_positioning("200811", "JPN", {}, [{"partner": "X"}])
    assert hp["conditions"]["rivals_not_halal_origin"] is None
    assert hp["status"] == "entry_condition"


def test_an_unclassified_chapter_says_nothing_at_all():
    assert CA.halal_positioning("990000", "DEU", {}, []) is None


def test_the_halal_position_enters_the_ledger_with_its_grade_and_flip():
    e = _view("netherlands_honey")["ledger"]["entries"]["halal_positioning"]
    assert e["status"] == L.INFERENCE and "شرط دخول" in e["value"]
    assert e["assumption"] and e["flip_if"]
    assert e["basis"] == ["top_supplier_share_pct"]
    e2 = _view("turkey_polymers")["ledger"]["entries"]["halal_positioning"]
    assert e2["status"] == L.MISSING and e2["value"] is None


# ── ٨) مصطلحاتُ البحث الحتمية ───────────────────────────────────────────────

def _market(name):
    ref, _ = resolve_market(name)
    return ref


def test_search_terms_are_built_from_references_not_by_the_model():
    t = SC.build_search_terms("تمور", "080410", _market("Netherlands"))
    assert "تمور" in t["ar"] and "تمر" in t["ar"]
    assert t["en"] == ["Dates fresh or dried"]
    assert t["local"]["lang"] == "nl" and t["local"]["terms"]
    assert "ليست ترجمةَ اسم المنتج" in t["local"]["note"]


def test_two_markets_get_their_own_language_terms():
    it = SC.build_search_terms("فيتوتشيني", "190219", _market("Italy"))
    jp = SC.build_search_terms("عسل", "040900", _market("Japan"))
    assert it["local"]["lang"] == "it" and jp["local"]["lang"] == "ja"
    assert it["local"]["terms"] != jp["local"]["terms"]


def test_a_market_without_a_terms_row_declares_the_gap_not_a_translation():
    t = SC.build_search_terms("بولي بروبيلين", "390210", _market("Libya"))
    assert t["local"]["terms"] == [] or t["local"]["lang"]
    if not t["local"]["terms"]:
        assert "فجوةٌ معلنة" in t["local"]["note"]


def test_a_query_that_is_the_customs_description_is_refused_with_the_alternative():
    import silk_llm_runtime as RT
    terms = SC.build_search_terms("تمور", "080410", _market("Netherlands"))
    ctx = {"search_terms": terms}
    long_desc = terms["customs_descriptions"][0]
    out = RT._tool_web_search({"query": long_desc}, ctx)
    assert out[0].value is None and out[0].confidence == 0.0
    assert "وصفُ البند الجمركيّ" in out[0].note and "تمور" in out[0].note
    out2 = RT._tool_trends_interest({"term": long_desc}, ctx)
    assert out2[0].value is None
    assert RT._customs_description_query("dadels Albert Heijn", ctx) is None


def test_the_guard_never_refuses_the_term_it_recommends():
    """مراجعةٌ ذاتية §58: رفضُ `terms["en"]` — وهو ما تعرضه كتلةُ المصطلحات —
    كان يضمن حلقةَ إعادةِ بحثٍ عقيمة بصفر نتيجة."""
    import silk_llm_runtime as RT
    terms = SC.build_search_terms("تمور", "080410", _market("Netherlands"))
    ctx = {"search_terms": terms}
    for t in terms["en"] + terms["ar"] + terms["local"]["terms"]:
        assert RT._customs_description_query(t, ctx) is None, t
    assert "Dates fresh or dried" in SC.search_terms_block(terms)


def test_a_language_code_with_a_region_suffix_still_finds_its_row():
    """`zh-CN` في المرجع و`zh-cn` من مُطبِّع اللغة — لا فجوةَ كاذبة."""
    t = SC.build_search_terms("عسل", "040900", _market("China"))
    assert t["local"]["terms"] and "فجوةٌ معلنة" not in t["local"]["note"]


def test_the_terms_block_reaches_only_the_searching_missions():
    src = open(os.path.join(_ROOT, "silk_llm_runtime.py"), encoding="utf-8").read()
    assert 'ctx["search_terms"] = build_search_terms(product, hs_code, market)' in src
    assert "search_terms_block" in src
    block = SC.search_terms_block(SC.build_search_terms(
        "تمور", "080410", _market("Netherlands")))
    assert "بالعربية" in block and "بلغة السوق" in block
    assert SC.search_terms_block({}) == ""


# ── مصفوفةُ الحلال على مدوّناتٍ حقيقيةِ الشكل ───────────────────────────────

def test_the_owner_matrix_holds_in_all_three_directions():
    from canonical_cosmetics_halal import (japan_cosmetics_research_blob,
                                           malaysia_cosmetics_research_blob)
    mys = R.build_view(malaysia_cosmetics_research_blob())
    assert (mys["ledger"]["entries"]["halal_positioning"]["value"]
            == "شرط دخول تجاري لا ميزة")
    no_ev = R.build_view(japan_cosmetics_research_blob())
    e = no_ev["ledger"]["entries"]["halal_positioning"]
    assert e["value"] == "لم نرصد طلباً على الحلال بعد" and e["how_to_close"]
    with_ev = R.build_view(japan_cosmetics_research_blob(True))
    assert (with_ev["ledger"]["entries"]["halal_positioning"]["value"]
            == "ميزة تنافسية")
    # الفارقُ **اكتشافٌ واحدٌ برابط** لا تغييرُ قاعدة.
    assert "aeon.co.jp" in " ".join(
        with_ev["ledger"]["entries"]["halal_positioning"]["note"].split())


# ── العيّنة: المدوّنات المجمّدة كلُّها ───────────────────────────────────────

@pytest.mark.parametrize("key", sorted(CANONICAL_BLOBS))
def test_no_false_alarm_and_no_religion_in_a_neutral_category(key):
    view = _view(key)
    md = SR.render_markdown(view)
    assert L.check(view, md) == []
    if J.religion_relevance(view.get("hs_code")) == "none":
        assert not RELIGIOUS.search(md), key
