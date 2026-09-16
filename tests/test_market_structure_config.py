"""الصنف ١٠ — افتراضاتُ بنية السوق تهيئةً، اختبارٌ أوّلاً.

كلُّ **تغييرِ سلوكٍ** هنا خلف `SILK_MARKET_STRUCTURE_CONFIG` المطفأةِ
افتراضياً؛ وكلُّ **حارسٍ** تحذيريٌّ بلا راية يقرأ نصَّ التقرير أوّلاً — لأنّ
سجلَّ التهيئة يغطّي أربعةَ أسواقٍ من ٣٨، وحارسٌ يشترط التهيئة ينام في الباقي
(الدرس ٩٨: الحارسُ الذي لا يمكن أن يُطلِق).

كلُّ اختبارٍ يقيس الحالتين: مطفأةً (عقدُ عدم المساس) ومفعّلةً (الأثر).

Run: python3 -m pytest tests/test_market_structure_config.py -q
"""
from __future__ import annotations

import copy
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from conftest import block_network  # noqa: E402


class _env:
    """متغيّراتُ بيئةٍ باستعادةٍ مضمونة — الاصطلاحُ القائم في هذه الحزمة."""

    def __init__(self, **vals):
        self.vals = vals
        self.old = {}

    def __enter__(self):
        for k, v in self.vals.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def _canonical_keys() -> list:
    from tools import gen_verdict_baseline as B
    return sorted(B.CANONICAL_BLOBS)


def _blob(key: str) -> dict:
    from tools import gen_verdict_baseline as B
    mod, fn = B.CANONICAL_BLOBS[key]
    return getattr(importlib.import_module(mod), fn)()


def _view(key: str) -> dict:
    import silk_render
    return silk_render.build_view(_blob(key))


def _repo(name: str) -> str:
    return open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), name), encoding="utf-8").read()


# ════════════════ الوحدةُ القارئة — بياناتٌ لا تفريعُ سوق ════════════════

def test_the_module_carries_no_country_or_hs_literal():
    """مبدأُ الصنف ١٠: كلُّ واقعةٍ قُطريةٍ أو منتجيةٍ **بيانات**، وكلُّ سلوكٍ
    قاعدةٌ تقرؤها. لِنتُ مصدرٍ كنظيره على `silk_profiles`
    (`tests/test_profiles_g1_g2.py`) — اسمُ دولةٍ أو رمزُ بندٍ في الوحدة
    يعني أنّ الصنفَ انتُقِض من داخله."""
    import re
    src = _repo("silk_market_structure.py")
    for tok in ("QAT", "NLD", "NGA", "IND", "YEM", "SAU", "SONCAP", "CIQ",
                "NAFDAC", "FSSAI", "ONSSA"):
        assert tok not in src, tok
    assert not re.search(r"\b\d{6}\b", src), "رمزُ بندٍ سداسيٌّ في الوحدة"


def test_currency_comes_from_the_existing_reference_for_all_markets():
    """عملةُ السوق **مُهيَّأةٌ أصلاً** لثمانيةٍ وثلاثين سوقاً في
    `market_locale.csv`؛ الناقصُ كان وصلَها. وهذا موطنُ الخطر المتبقّي من
    الصنف ١٢: «ريال» تسعُ عدّةَ دول، فسوقٌ خليجيٌّ غيرُ السعودية يأخذ رمزَه
    هو لا رمزَ الأشهر."""
    import silk_market_structure as M
    assert M.market_currency("QAT") == "QAR"
    assert M.market_currency("KWT") == "KWD"
    assert M.market_currency("YEM") == "YER"
    assert M.market_currency("EGY") == "EGP"
    # وسوقُ المنشأ (السعودية) **ليس** في جدول الأسواق المستهدفة ولا له
    # ملامح — فيُعاد فراغاً معلَناً لا رمزاً مخمَّناً. قيدٌ مقيسٌ مُعلَن،
    # ولا يمسّ الغرضَ (الاستعمالُ لعملةِ سوقِ الهدف).
    assert M.market_currency("SAU") == ""
    assert M.market_currency("") == ""
    assert M.market_currency("ZZZ") == ""
    # قارئاتُ الوحدة **لا تسأل الراية**: الرايةُ تحكم تغييرَ السلوك لا
    # القراءةَ (وإلّا صار الاختبارُ نفسُه هو ما يُشغّلها).
    with _env(SILK_MARKET_STRUCTURE_CONFIG=None):
        assert M.market_currency("QAT") == "QAR"


def test_port_and_standards_bodies_read_the_existing_layers():
    """المرفأُ من `ports_l1.csv` (٢٣٥ سوقاً)، وجهةُ التقييس من ملامح السوق
    مع كتلتِه — ولا شيءَ منها يُبنى من جديد."""
    import silk_market_structure as M
    assert M.main_port("QAT")
    assert M.main_port("YEM")            # سوقٌ بلا ملامحَ ومع ذلك له مرفأ
    assert M.main_port("ZZZ") == ""
    bodies = M.standards_bodies("QAT")
    assert "GSO" in bodies and "GCC" in bodies
    assert M.standards_bodies("ZZZ") == ()


def test_region_keys_are_a_shipped_contract_with_no_rows_yet():
    """قرارُ مالكٍ مسجَّل: المخطَّطُ والمُدقِّقُ والحارسُ تُشحَن، والصفوفُ
    إدخالٌ لاحق. فالإعلانُ صريح: صفرُ أقاليمَ اليوم — لا صمت."""
    import silk_market_structure as M
    for iso3 in ("QAT", "NLD", "NGA", "IND"):
        assert M.regions(iso3) == (), iso3
        assert M.multi_authority(iso3) is False, iso3
        assert M.target_region(iso3) == "", iso3


# ════════════════ سجلُّ أنظمة المطابقة — مفتاحُه النظامُ لا السوق ════════════

def test_scheme_registry_is_cited_row_by_row():
    """كلُّ صفٍّ باستشهاده — عقدُ عدم الاختلاق ممتدٌّ لجداول L1."""
    import silk_market_structure as M
    rows = M.schemes()
    assert len(rows) >= 20
    for r in rows:
        assert r["scheme"] and r["source_url"].startswith("http"), r
        assert bool(r["owner_iso3"]) != bool(r["owner_bloc"]), r


def test_a_scheme_of_another_country_does_not_belong():
    """العيبُ المرصود حرفياً: حدودُ تقريرِ اليمن استشهدت بـSONCAP (نيجيريا)
    وCIQ (الصين)."""
    import silk_market_structure as M
    assert M.scheme_belongs_to("SONCAP", "NGA") is True
    assert M.scheme_belongs_to("SONCAP", "YEM") is False
    assert M.scheme_belongs_to("CIQ", "YEM") is False
    assert M.scheme_belongs_to("FSSAI", "IND") is True


def test_bloc_membership_and_origin_are_both_legitimate():
    """نظامُ كتلةٍ يخصّ أعضاءها (بجدول أسماءٍ لا تفريع: «EU» ⇄ `EU27`)،
    و**نظامُ دولةِ المنشأ مشروعٌ دائماً** — اشتراطاتُ الخروج جزءٌ قانونيٌّ من
    كلّ تقرير (`silk_requirements_agent` يثبّت صفوفَ الخروج على المنشأ).
    إسقاطُ هذا الاستثناء كان سيُطلِق على كلّ تقريرٍ يذكر جهةَ بلدِ المصدّر."""
    import silk_market_structure as M
    assert M.scheme_belongs_to("CE", "NLD") is True
    assert M.scheme_belongs_to("CE", "YEM") is False
    assert M.scheme_belongs_to("SFDA", "YEM", "SAU") is True
    assert M.scheme_belongs_to("SFDA", "YEM", "") is False
    assert M.scheme_belongs_to("GSO", "YEM", "SAU") is True   # المنشأ خليجيّ


def test_an_international_or_shared_name_is_never_a_mismatch():
    """معيارٌ دوليٌّ أو اسمٌ تتقاسمه برامجُ عدّة دول لا مالكَ قُطريَّ له —
    احتسابُه مخالفةً كان سيُطلِق على HACCP في كلّ تقرير."""
    import silk_market_structure as M
    for name in ("HACCP", "ISO 22000", "BRCGS", "PVoC", "COC"):
        assert M.scheme_belongs_to(name, "YEM") is True, name
    # واسمٌ غيرُ مُسجَّل لا يُحكَم عليه — لا نحكم على ما لا نعرف.
    assert M.scheme_belongs_to("SCHEME-X", "YEM") is True
    assert M.scheme_owner("SCHEME-X") == {}


# ════════════════ المخطَّطُ المُدقَّق — العقدُ يُنفَّذ لا يُوصَف ════════════

def test_real_profiles_still_validate_after_the_new_schema():
    import silk_profiles as P
    assert P.validate_all() == []


def test_multi_authority_now_requires_a_target_region():
    """قاعدةُ تقابلٍ جديدة: سلطتان بلا إقليمِ هدفٍ تعني أنّ القارئَ لا يعرف
    أيَّ سلطةٍ تحكم شحنتَه — والقائمةُ لا تصلح للتنفيذ."""
    import silk_profiles as P
    good = copy.deepcopy(P.market_profile("QAT"))
    cite = {"source_url": "https://example.gov", "review_date": "2026-09-16"}
    good["multi_authority"] = {"value": True, **cite}
    good["authorities"] = [{"value": "جهة أ", **cite},
                           {"value": "جهة ب", **cite}]
    errs = P.validate_market("QAT", good)
    assert any("target_region" in e for e in errs), errs
    good["target_region"] = {"value": "إقليم الجنوب", **cite}
    assert P.validate_market("QAT", good) == []


def test_region_rows_are_cited_and_their_keys_controlled():
    import silk_profiles as P
    cite = {"source_url": "https://example.gov", "review_date": "2026-09-16"}
    prof = copy.deepcopy(P.market_profile("NLD"))
    prof["regions"] = [{"name": {"value": "الشمال", **cite},
                        "port": {"value": "مرفأ الشمال", **cite}}]
    assert P.validate_market("NLD", prof) == []
    prof["regions"] = [{"name": {"value": "الشمال", **cite},
                        "fx": {"value": 3.75}}]          # بلا استشهاد
    assert any("regions[0].fx" in e for e in P.validate_market("NLD", prof))
    prof["regions"] = [{"name": {"value": "الشمال", **cite},
                        "warehouses": {"value": 3, **cite}}]   # مفتاحٌ مجهول
    assert any("غيرُ معروفة" in e for e in P.validate_market("NLD", prof))


def test_hs_scope_and_price_range_are_validated_when_present():
    import silk_profiles as P
    cite = {"source_url": "https://example.org", "review_date": "2026-09-16"}
    prod = copy.deepcopy(P.product_profile("080410"))
    prod["hs_scope"] = {"value": "wide", **cite}          # خارج enum
    assert any("hs_scope" in e and "خارج المسموح" in e
               for e in P.validate_product("p", prod))
    prod["hs_scope"] = {"value": "broad", **cite}
    prod["price_range"] = {"border_usd_per_kg_min": {"value": 9.0, **cite},
                           "border_usd_per_kg_max": {"value": 2.0, **cite}}
    assert any("price_range" in e and "الحدُّ الأدنى" in e
               for e in P.validate_product("p", prod))


def test_an_unknown_top_level_section_no_longer_passes_silently():
    """ثقبٌ مرصود: المُدقِّقُ كان يقرأ الأقسامَ المسمّاة ويُقبَل ما عداها
    بصمت، فقسمٌ مكتوبٌ بخطأٍ إملائيّ يمرّ ولا يقرؤه أحد — وهو أسوأُ من
    الرفض لأنه يُطمئن."""
    import silk_profiles as P
    prof = copy.deepcopy(P.market_profile("IND"))
    prof["regualtory_regime"] = prof["regulatory_regime"]   # خطأٌ إملائيّ
    assert any("أقسامٌ غيرُ معروفة" in e for e in P.validate_market("IND",
                                                                    prof))
    prod = copy.deepcopy(P.product_profile("200811"))
    prod["shelf_life"] = prod["shelf_life_days"]
    assert any("مفاتيحُ غيرُ معروفة" in e for e in P.validate_product("p",
                                                                      prod))


def test_hs_scope_is_configured_from_the_official_nomenclature():
    """الاتّساعُ **واقعةٌ مُستشهَدة** لا استنتاجَ محرّك: بندُ زبدةِ الفول
    السوداني يضمّ المنتجَ بين غيره، وبندُ التمور يطابق فئتَه."""
    import silk_market_structure as M
    assert M.hs_scope("200811") == "broad"
    assert M.hs_scope("080410") == "exact"
    assert M.hs_scope("170490") == ""        # غيرُ مُهيَّأ ⇒ لا حكم
    assert M.price_range("200811") is None   # المفتاحُ عقدٌ بلا صفوفٍ بعد


# ════════════════ الحرّاس الستّة — تقرأ النصَّ أوّلاً ════════════════

_NEW_CHECKS = ("zero_fx_volatility",
               "target_region_missing_in_multi_authority",
               "broad_hs_scope_undisclosed", "border_price_out_of_range",
               "lead_outside_activity_allowlist",
               "regime_not_belonging_to_country")


def test_none_of_the_six_guards_is_blocking_in_any_flag_state():
    """قرارُ المالك «لا حجب جديداً» — الصنفُ ١٠ تحذيريٌّ بالكامل."""
    import silk_quality_gate as G
    for name in _NEW_CHECKS:
        assert name not in G.FAIL_TRIGGER_CHECKS, name
    with _env(SILK_MARKET_STRUCTURE_CONFIG="1"):
        eff = G.effective_fail_triggers()
    for name in _NEW_CHECKS:
        assert name not in eff, name


def test_zero_fx_volatility_fires_and_a_declared_peg_spares_it():
    """الصفرُ يرفع عمودَ أمانِ العملة إلى ١.٠٠ في الدرجة — فالمطلوبُ إعلانُ
    أيِّهما: ربطٌ رسميٌّ أم سلسلةٌ ثابتة. القيمةُ لا تُمَسّ."""
    import silk_quality_gate as G
    dr = {"report": {"text": "سعر الصرف مستقر عبر ثلاث سنوات."},
          "missions": {"risk_news": {"summary": "x", "findings": [
              {"value": 0.0, "note": "[risk] تقلب سعر الصرف 0.0% — مستنتَج",
               "source": "World Bank", "confidence": 0.85}]}}}
    out = G._check_zero_fx_volatility({"deep_research": dr})
    assert len(out) == 1 and out[0]["check"] == "zero_fx_volatility"
    assert out[0]["repairable"] is True
    ok = copy.deepcopy(dr)
    ok["report"]["text"] += " العملة مربوطة رسمياً بالدولار."
    assert G._check_zero_fx_volatility({"deep_research": ok}) == []
    # وتقلّبٌ غيرُ صفريٍّ ليس شأنَ هذا الفحص.
    nz = copy.deepcopy(dr)
    nz["missions"]["risk_news"]["findings"][0]["value"] = 18.4
    assert G._check_zero_fx_volatility({"deep_research": nz}) == []


def test_target_region_guard_needs_two_authorities_and_two_named_gateways():
    """**قِياسٌ ضيَّق القاعدة قبل الشحن**: إبرةُ منفذٍ واحدةٍ أطلقت على تقرير
    مصر — جهتان مشروعتان («القومية»/«المصرية») ومنفذٌ واحد. والعيبُ المرصود
    **بوّابتان**: قيودُ سلطةٍ ومرفأُ أخرى. بالبوّابتين المسمّيتين: صفرُ
    إطلاقةٍ على المدوّنات الأربعَ عشرة."""
    import silk_quality_gate as G
    view = {"market": {"iso3": "YEM"}}
    two = ("تشترط الهيئة الشمالية تسجيلاً مسبقاً، بينما تديـر الهيئة "
           "الجنوبية الجمارك. الشحن عبر ميناء عدن أو معبر الوديعة.")
    dr = {"report": {"text": two}}
    out = G._check_target_region_missing(view, dr, "ar")
    assert len(out) == 1
    assert out[0]["check"] == "target_region_missing_in_multi_authority"
    # بوّابةٌ واحدة ⇒ صمت (وهو ما حمى تقريرَ مصر).
    one = {"report": {"text": two.replace(" أو معبر الوديعة", "")}}
    assert G._check_target_region_missing(view, one, "ar") == []
    # وإعلانُ الإقليم يُعفي.
    told = {"report": {"text": two + " الإقليم المستهدف: الجنوب."}}
    assert G._check_target_region_missing(view, told, "ar") == []


def test_broad_hs_guard_fires_on_a_real_view_when_disclosure_is_removed():
    """يُقاس على مدوّنةٍ حقيقيةٍ لا على مثالٍ مصنوع: المدوّنةُ الوحيدةُ التي
    بندُها مُعلَنٌ واسعاً (200811) **تُفصِح فعلاً**، فالفحصُ يصمت عليها —
    صمتٌ مقيسٌ لا غياب. وحذفُ جملةِ الإفصاح وحدَها يُطلِقه."""
    import silk_quality_gate as G
    with block_network():
        v = _view("qatar_peanut_butter")
    assert v.get("hs_code") == "200811"
    assert G._check_broad_hs_scope_undisclosed(v) == []
    stripped = copy.deepcopy(v)
    txt = stripped["deep_research"]["report"]["text"]
    for needle in G._HS_BREADTH_DISCLOSURE:
        txt = txt.replace(needle, "—")
    stripped["deep_research"]["report"]["text"] = txt
    out = G._check_broad_hs_scope_undisclosed(stripped)
    assert len(out) == 1 and out[0]["check"] == "broad_hs_scope_undisclosed"
    assert "200811" in out[0]["note"]


def test_broad_hs_guard_is_silent_for_an_exact_code():
    import silk_quality_gate as G
    with block_network():
        v = _view("germany_dates")
    assert v.get("hs_code") == "080410"
    assert G._check_broad_hs_scope_undisclosed(v) == []


def test_lead_activity_guard_drops_only_a_listed_and_excluded_activity():
    """المجهولُ يمرّ بالتصميم: الجهلُ بالتسمية ليس دليلَ عدمِ الصلة."""
    import silk_quality_gate as G
    view = {"deep_research": {"importer_leads": {"leads": [
        {"name": "متجر الوفاء", "category": "متجر قطع غيار"},
        {"name": "مؤسسة البركة", "category": "مستورد"},
        {"name": "جهة ج", "category": "نشاطٌ لم يُسجَّل بعد"},
        {"name": "جهة د", "category": ""}]}}}
    out = G._check_lead_outside_activity_allowlist(view)
    assert len(out) == 1
    assert out[0]["check"] == "lead_outside_activity_allowlist"
    assert "متجر الوفاء" in out[0]["note"]
    assert "مؤسسة البركة" not in out[0]["note"]
    assert "جهة ج" not in out[0]["note"]


def test_regime_guard_fires_on_a_foreign_scheme_and_spares_origin():
    import silk_quality_gate as G
    base = {"market": {"iso3": "YEM"}, "header": {"origin": "SAU"},
            "deep_research": {"report": {"text": ""}}}
    bad = copy.deepcopy(base)
    bad["deep_research"]["report"]["text"] = (
        "تشترط الجهات شهادة SONCAP قبل الشحن، وفحص CIQ عند الوصول.")
    out = G._check_regime_not_belonging_to_country(bad)
    assert len(out) == 1
    assert out[0]["check"] == "regime_not_belonging_to_country"
    assert "SONCAP" in out[0]["note"] and "CIQ" in out[0]["note"]
    ok = copy.deepcopy(base)
    ok["deep_research"]["report"]["text"] = (
        "اشتراطات الخروج من السعودية عبر SFDA وSABER، ومواصفات GSO، "
        "ونظام HACCP معيارٌ دوليّ.")
    assert G._check_regime_not_belonging_to_country(ok) == []


def test_border_price_guard_is_dormant_until_a_range_is_configured():
    """إعلانٌ صريحٌ لا صمت: المفتاحُ عقدٌ مُدقَّقٌ بلا صفوفٍ بعد، فالفحصُ
    يصمت — ويُطلِق على مدىً مُهيَّأً حين يُدخَل."""
    import silk_market_structure as M
    import silk_quality_gate as G
    with block_network():
        v = _view("india_honey")
    assert M.price_range(v.get("hs_code")) is None
    assert G._check_border_price_out_of_range(v) == []


def test_the_guards_fire_only_where_the_defect_is_real_and_verbatim():
    """الإطلاقاتُ **محصورةٌ حرفياً** على المدوّنات الستّ عشرة: مدوّنةُ ليبيا
    (المراجعةُ الذاتية للجولة الثالثة) تحمل العيوبَ الثلاثة بقصد — سلطتان
    وبوّابتان بلا إقليم، وبندٌ واسعٌ غيرُ مُعلَن، ونشاطٌ لا صلةَ له —
    وخمسَ عشرةَ مدوّنةً **صفرٌ**. والقاعدةُ التي تُطلِق على الصحيح لا
    تُشحَن (الصنف ١١)، والصمتُ وحدَه لا يُثبِت أنّ القاعدةَ حيّة."""
    import silk_quality_gate as G
    expected_off = {
        "libya_tahini": {"target_region_missing_in_multi_authority",
                         "broad_hs_scope_undisclosed",
                         "lead_outside_activity_allowlist"}}
    # مفعّلةً: مِصفاةُ النشاط **تُسقِط** الجهةَ فعلاً، فيصمت حارسُها —
    # صمتُه هنا هو الفكسُ يعمل، لا قاعدةٌ نائمة.
    expected_on = {
        "libya_tahini": {"target_region_missing_in_multi_authority",
                         "broad_hs_scope_undisclosed"}}
    off: dict = {}
    on: dict = {}
    with block_network():
        for key in _canonical_keys():
            with _env(SILK_MARKET_STRUCTURE_CONFIG=None):
                g_off = G.run_quality_gate(_view(key))
            with _env(SILK_MARKET_STRUCTURE_CONFIG="1"):
                g_on = G.run_quality_gate(_view(key))
            h_off = {f["check"] for f in g_off["findings"]
                     if f["check"] in _NEW_CHECKS}
            h_on = {f["check"] for f in g_on["findings"]
                    if f["check"] in _NEW_CHECKS}
            if h_off:
                off[key] = h_off
            if h_on:
                on[key] = h_on
            assert g_off["verdict"] == g_on["verdict"], key
    assert off == expected_off, off
    assert on == expected_on, on


# ════════════════ تغييراتُ السلوك — كلُّها خلف الراية ════════════════

def test_the_mission_prompt_names_no_country_scheme_with_the_flag_on():
    """الجذرُ كان في الشيفرة لا في التهيئة: تعليمةُ بعثة الاشتراطات تحقن
    أسماءَ أنظمةٍ بعينها في موجّه **كلّ سوق**. مفعّلةً: تعليمةٌ مقيَّدةٌ
    بسوق الهدف. مطفأةً: النصُّ السابق حرفياً (فلا ينحرف eval)."""
    import silk_missions as MS
    mission = MS.MISSIONS["customs_requirements"]
    with _env(SILK_MARKET_STRUCTURE_CONFIG="1"):
        on = MS.scope_instructions(mission)["instructions"]
    with _env(SILK_MARKET_STRUCTURE_CONFIG=None):
        off = MS.scope_instructions(mission)["instructions"]
    for tok in ("SONCAP", "CIQ", "SFDA"):
        assert tok not in on, tok
        assert tok in off, tok
    assert "لا تذكر نظام دولة أخرى" in on
    assert MS._LEGACY_SCHEME_HINT in off
    # والمبدِّلُ موصولٌ في مسارِ البعثة الحقيقيّ لا في الاختبار وحدَه.
    assert "scope_instructions" in _repo("silk_llm_runtime.py")


def test_lead_activity_filter_and_reason_column_follow_the_flag():
    """وجهَا العيب: نشاطٌ لا صلةَ له **دخل**، وموزّعٌ يوصي به المتن **غاب**.
    فالنشاطُ صار مِصفاةً، والجهةُ التي يسمّيها المتنُ لا تُسقِطها مِصفاةٌ
    أبداً — بلا اختلاقِ جهةٍ ولا اتصال."""
    import silk_reports as R
    dr = {"market": {"iso3": "NGA", "name_en": "Nigeria",
                     "name_ar": "نيجيريا"},
          "report": {"text": "نوصي بالتعامل مع شركة النيل للتوزيع."}}
    leads = [{"name": "شركة النيل للتوزيع", "category": "auto parts store",
              "phone": "1"},
             {"name": "متجر الوفاء لقطع الغيار",
              "category": "auto parts store", "phone": "2"},
             {"name": "مؤسسة البركة", "category": "importer", "phone": "3"}]
    with _env(SILK_MARKET_STRUCTURE_CONFIG=None):
        off = R._clean_leads(leads, dr)
        assert len(off) == 3
        assert R._leads_header("ar") == list(R._LEADS_HEADER)
        assert len(R._lead_cells(leads[0], "ar")) == len(R._LEADS_HEADER)
    with _env(SILK_MARKET_STRUCTURE_CONFIG="1"):
        on = R._clean_leads(leads, dr)
        names = [x["name"] for x in on]
        assert "متجر الوفاء لقطع الغيار" not in names
        assert "شركة النيل للتوزيع" in names      # يسمّيها المتن ⇒ حصانة
        assert "مؤسسة البركة" in names
        head = R._leads_header("ar")
        assert head[-1] == "سبب الإدراج"
        assert R._lead_cells(on[0], "ar")[-1] == "مذكورةٌ في متن التقرير"


def test_broad_hs_disclosure_and_confidence_cap_reuse_the_flagged_machinery():
    """الإفصاحُ عن الاتّساع يمرّ بآلة `hs_flagged` نفسِها — لا مسارَ عرضٍ
    ثانٍ (قاعدةُ «وسِّع `build_view`»)."""
    import silk_render
    with block_network():
        with _env(SILK_MARKET_STRUCTURE_CONFIG=None):
            off = silk_render.build_view(_blob("qatar_peanut_butter"))
        with _env(SILK_MARKET_STRUCTURE_CONFIG="1"):
            on = silk_render.build_view(_blob("qatar_peanut_butter"))
    d_off = off.get("deep_research") or {}
    d_on = on.get("deep_research") or {}
    assert d_off.get("concentration_context_only") is False
    assert d_on.get("concentration_context_only") is True
    added = [ln for ln in (d_on.get("limits") or [])
             if ln not in (d_off.get("limits") or [])]
    assert len(added) == 1 and "أوسع من المنتج المدروس" in added[0]
    from silk_hs_confirm import CONTEXTUAL_TAG
    assert added[0].startswith(CONTEXTUAL_TAG)


def test_zero_fx_note_gains_its_meaning_and_keeps_value_and_needle():
    """القيمةُ لا تُمَسّ (تثبيتةُ المالك على `0.0`)، والإبرةُ «تقلب سعر
    الصرف» تبقى حرفيةً كي لا يُكسَر مستخلِصُ الأعمدة."""
    import silk_missions as MS
    src = _repo("silk_missions.py")
    assert "تقلب سعر الصرف {vol}%" in src
    assert "تقلّبٌ مرصودٌ صفراً" in src
    assert "silk_market_structure" in src
    # المستخلِصُ يقرأ الإبرةَ نفسَها — لا تُغيَّر.
    assert "تقلب سعر الصرف" in _repo("silk_deep_pillars.py")
    assert hasattr(MS, "_augment_risk_news_fx")


def test_flag_off_changes_no_surface_on_any_canonical_blob():
    """عقدُ عدم المساس على كلّ سطح: Markdown وحكمُ البوابة والدرجةُ والثقة."""
    import silk_quality_gate as G
    import silk_reports
    problems: dict = {}
    with block_network():
        for key in _canonical_keys():
            with _env(SILK_MARKET_STRUCTURE_CONFIG=None):
                v0 = _view(key)
                md0 = silk_reports.render_markdown(v0)
                g0 = G.run_quality_gate(v0)
            with _env(SILK_MARKET_STRUCTURE_CONFIG="1"):
                v1 = _view(key)
                g1 = G.run_quality_gate(v1)
            issues = []
            if g0["verdict"] != g1["verdict"]:
                issues.append("verdict")
            d0 = (v0.get("decision") or {})
            d1 = (v1.get("decision") or {})
            for k in ("verdict", "score", "confidence"):
                if d0.get(k) != d1.get(k):
                    issues.append(f"decision.{k}")
            with _env(SILK_MARKET_STRUCTURE_CONFIG=None):
                if silk_reports.render_markdown(_view(key)) != md0:
                    issues.append("md not deterministic")
            if issues:
                problems[key] = issues
    assert problems == {}, problems


# ═══ الصنفان ١٤ و١٥ — مراجعةُ الجولة الثالثة الذاتية ═══

def test_c14_a_generic_word_is_not_a_named_gateway():
    """**العيبُ المرصود في حارسي أنا**: «منفذ الدخول» قُرِئت بوّابةً اسمُها
    «الدخول»، فصار لتقريرٍ ذي مرفأٍ واحدٍ ثلاثُ بوّابات — وحارسٌ يُضخِّم
    عدَّه بنفسه يُطلِق على الصحيح (عائلةُ الصنف ١١).

    القياسُ على مدوّنةٍ حقيقية: تقريرُ ليبيا كان يُبلِّغ «الدخول»، «بنغازي»،
    «طرابلس» — وصار يُبلِّغ الاسمين العلَمين وحدَهما."""
    import silk_quality_gate as G
    assert G._named_gateways(
        "الشحن عبر ميناء طرابلس أو ميناء بنغازي، ومنفذ الدخول يُحسم لاحقاً."
    ) == ["بنغازي", "طرابلس"]
    # مرفأٌ واحدٌ + وصفٌ عامّ ⇒ بوّابةٌ واحدة (فلا يُطلِق الحارس).
    assert G._named_gateways(
        "الشحن عبر ميناء العقبة ومنفذ الدخول البري.") == ["العقبة"]
    with block_network():
        v = _view("libya_tahini")
    dr = v.get("deep_research") or {}
    out = G._check_target_region_missing(v, dr, "ar")
    assert len(out) == 1
    assert "الدخول»" not in out[0]["note"], out[0]["note"]
    assert "طرابلس" in out[0]["note"] and "بنغازي" in out[0]["note"]


def test_c15_a_generic_head_before_two_proper_names_is_not_an_echo():
    """**العيبُ المرصود**: «ميناء طرابلس أو ميناء بنغازي» عربيةٌ سليمة، وفحصُ
    صدى الكيان (الصنف ٢) أطلق عليها — وكذلك «الهيئة الغربية… الهيئة
    الشرقية». الرأسُ العامُّ قبل اسمٍ علَمٍ **يتكرّر بالضرورة** حين يُعَدّ
    كيانان.

    والمعالجةُ بقائمةِ رؤوسٍ مقيسةٍ لا بقاعدةِ «تابعٌ مختلف» — تلك جُرِّبت
    في الصنف ٢ فأسكتت العيبَ المرصود نفسَه («ثم السعودية بالحصة السعودية»)."""
    import silk_quality_gate as G
    ok = ("## 8. اللوجستيات\nالشحن البحري يدخل عبر ميناء طرابلس أو ميناء "
          "بنغازي، ولكل منهما إجراءات تخليص مستقلة.")
    hits = [f for f in G._check_template_interpolation(ok, "ar")
            if "صدى" in f.get("note", "")]
    assert hits == [], hits
    # والعيبُ الحقيقيُّ من عائلة الصنف ٢ ما زال يُرصَد — لا إسكاتَ عامّ.
    bad = "## 3. السوق\nثم السعودية بالحصة السعودية المرصودة."
    assert any("صدى" in f.get("note", "")
               for f in G._check_template_interpolation(bad, "ar"))
    # وعلى المدوّنة الحقيقية: صفرُ إطلاقةِ صدىً بعد التضييق.
    with block_network():
        v = _view("libya_tahini")
    text = ((v.get("deep_research") or {}).get("report") or {}).get("text")
    assert not [f for f in G._check_template_interpolation(text, "ar")
                if "صدى" in f.get("note", "")]


def test_c10_breadth_note_says_which_level_supplied_the_evidence():
    """مرجعُ الوصف يتدرّج ٦→٤ داخلياً، فبندٌ غيرُ مسجَّلٍ سداسياً يُحكَم
    بوصف بنده الرباعيّ — **تقريبٌ يُقال** لا استنتاجٌ صامت. مقيسٌ: 200819
    ليس في المرجع السداسيّ و200811 فيه."""
    import silk_quality_gate as G
    assert G._hs6_registered("200811") is True
    assert G._hs6_registered("200819") is False
    with block_network():
        out = G._check_broad_hs_scope_undisclosed(_view("libya_tahini"))
    assert len(out) == 1 and "الرباعيّ" in out[0]["note"], out


def test_the_lead_filter_removes_what_the_guard_warned_about():
    """المسارُ كاملاً على مدوّنةٍ حقيقية: مطفأةً يُحذَّر من النشاط، ومفعّلةً
    **يُسقَط** من الجدول — فصمتُ الحارس هو الفكسُ لا نومُه."""
    import silk_quality_gate as G
    with block_network():
        with _env(SILK_MARKET_STRUCTURE_CONFIG=None):
            v_off = _view("libya_tahini")
            names_off = [x.get("name") for x in
                         ((v_off["deep_research"].get("importer_leads")
                           or {}).get("leads") or [])]
            hit_off = [f["check"] for f in G.run_quality_gate(v_off)["findings"]
                       if f["check"] == "lead_outside_activity_allowlist"]
        with _env(SILK_MARKET_STRUCTURE_CONFIG="1"):
            v_on = _view("libya_tahini")
            names_on = [x.get("name") for x in
                        ((v_on["deep_research"].get("importer_leads")
                          or {}).get("leads") or [])]
            hit_on = [f["check"] for f in G.run_quality_gate(v_on)["findings"]
                      if f["check"] == "lead_outside_activity_allowlist"]
    assert "مؤسسة النخبة لقطع الغيار" in names_off and hit_off
    assert "مؤسسة النخبة لقطع الغيار" not in names_on and not hit_on
    assert "شركة الساحل للتجارة" in names_on      # نشاطٌ ذو صلة يبقى


def test_c16_a_mandatory_warning_survives_a_line_wrap():
    """**العيبُ المرصود — والأخطرُ في هذه المراجعة**: تقريرُ كينيا يحمل
    التحذيرَ الإلزاميّ «…ولا يصلح هذا الرقم أساساً\\nللتفاوض»، والفحصُ
    الحاجبُ يُبلِّغ **غيابَه** فيُحجَب تقريرٌ أفصحَ كما يجب — لأنّ
    `_norm_ar` يطوي المسافةَ والجدولةَ لا السطرَ الجديد.

    في الإنتاج يكتب الكاتبُ نثراً ملفوفاً، فأيُّ لفٍّ للعبارة عند حدّ السطر
    كان يقلب الإفصاحَ إلى حجب — معاقبةُ الإفصاح (سابقةُ الدرس 239)."""
    import silk_quality_gate as G
    dr = {"economics": {"pricing_contradiction": {
        "shortfall_pct": 25.3, "max_exw_usd": 2.54,
        "reference_import_price_usd_kg": 3.4, "note": "تحذير"}},
        "report": {"text": ""}}
    wrapped = ("يقع أقصى سعر مصنع قابل للمنافسة دون متوسط سعر الاستيراد "
               "المرصود — ولا يصلح هذا الرقم أساساً\nللتفاوض.")
    dr["report"]["text"] = wrapped
    assert G._check_pricing_contradiction_flagged(
        {"deep_research": dr}) == []
    # وغيابُه الحقيقيُّ ما زال يُرصَد — لا إسكاتَ عامّ.
    dr["report"]["text"] = "أقصى سعر مصنع قابل للمنافسة 2.54 دولار/كجم."
    out = G._check_pricing_contradiction_flagged({"deep_research": dr})
    assert any(f["check"] == "pricing_contradiction_flagged" for f in out)
    # والمطوِّي لا يُستعمَل حيث السطرُ حدٌّ دلاليّ — دالّةٌ منفصلة بالاسم.
    # المطوِّي يطبّع الألفَ كنظيره ويطوي السطر؛ والأصليُّ يُبقي السطر.
    assert G._flat_ar("أ\nب  ج") == "ا ب ج"
    assert G._norm_ar("أ\nب") == "ا\nب"


def test_c16_the_kenya_corpus_is_not_blocked_by_that_false_negative():
    """حارسُ انحدارٍ على مدوّنةٍ حقيقية: كينيا مع رايةِ الصنف ١٢ مفعّلةً
    (فيُحسَب التناقضُ التسعيريُّ فعلاً) تبقى `PASS-WITH-WARNINGS`."""
    import silk_quality_gate as G
    with block_network(), _env(SILK_RECOGNITION_VOCABULARY="1"):
        out = G.run_quality_gate(_view("kenya_honey"))
    assert out["verdict"] == "PASS-WITH-WARNINGS", [
        f["check"] for f in out["findings"]]
    assert not [f for f in out["findings"]
                if f["check"] == "pricing_contradiction_flagged"]
