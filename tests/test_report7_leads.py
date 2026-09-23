"""تقرير سِلك ٧ — تأهيل الجهات بمستوى المنتج (§4.4، الدرس ٢٧٥).

product-level lead qualification: a seafood wholesaler or a greengrocer is not
a coffee buyer; category words match whole words only («food» ≠ «seafood»);
a specialised activity is kept only for its own HS chapters (the butcher stays
for a meat exporter); naming a company in the narrative is not evidence of
relevance — a clear mismatch is dropped and the rest is shown as a candidate.

كلُّ الحالات مصطنعةٌ لاختبارٍ هرمتيّ.
"""
import silk_reports as SR
import silk_style_contract as SC

_COFFEE = ("090121", "قهوة محمصة", "MYS")


def _fit(name, category, hs=_COFFEE):
    return SC.lead_product_fit({"name": name, "category": category}, *hs)


def test_seafood_and_greengrocer_are_not_coffee_buyers():
    for name, cat in (("Ocean Seafood Trading", "Seafood wholesaler"),
                      ("Pasar Segar Buah", "Greengrocer"),
                      ("Kedai Daging Halal", "Butcher shop")):
        ok, why, _ = _fit(name, cat)
        assert not ok and "متخصّصٌ بمنتجٍ آخر" in why, (name, why)


def test_a_specialised_activity_stays_for_its_own_chapter():
    """لا منعٌ عامّ: الملحمةُ لمصدّر اللحوم، وبائعُ الخضار لمصدّر الفواكه."""
    assert _fit("Kedai Daging", "Butcher shop",
                ("020130", "لحم بقري", "MYS"))[0]
    assert _fit("Pasar Segar", "Greengrocer", ("080410", "تمور", "MYS"))[0]
    ok, _, status = _fit("Kopi Hub", "Coffee wholesaler")
    assert ok and status == SC.EVIDENCE_SPECIALIST


def test_category_words_match_whole_words_only():
    assert not SC._word_in("ocean seafood trading", "food")
    assert SC._word_in("mega food supplies", "food")
    assert not SC._word_in("لبنان للتجارة", "بن")
    assert SC._word_in("مؤسسة البن الذهبي", "بن")


def test_a_general_trader_is_kept_as_a_candidate_to_verify():
    ok, _, status = _fit("ABC Trading", "Trading company")
    assert ok and status == SC.EVIDENCE_GENERAL


def test_empty_keyword_codes_inherit_their_heading_words_only_as_last_resort():
    """090112 بلا كلمات ولا اسم ⇒ يرث «قهوة/coffee» من 0901؛ أمّا 200899
    «طحينة» فاسمُه يكفي ولا يرث «peanut butter» من شقيقه 200811."""
    words = SC._product_specific_words("090112", "")
    assert "coffee" in words or "قهوة" in words
    tahini = SC._product_specific_words("200899", "طحينة")
    assert "peanut butter" not in tahini and "طحينة" in tahini
    # ولا يرث شقيقٌ ذو كلماتٍ كلماتِ غيره: التمرُ ليس المانجو.
    assert "mango" not in SC._product_specific_words("080410", "تمور")
    # والأوصافُ العامّة في الاسم لا تُثبت تخصّصاً.
    assert "محمصة" not in SC._product_specific_words("090121", "قهوة محمصة")


def test_a_clear_mismatch_is_dropped_before_any_word_can_rescue_it():
    for lead, hs, prod in (
            ({"name": "Fresh Seafood Trading", "category": "Seafood wholesaler"},
             "080410", "Fresh Dates"),
            ({"name": "Palm Oil Consultants", "category": "Consultant"},
             "150910", "olive oil"),
            ({"name": "Motor Oil Co", "category": "Auto parts store"},
             "150910", "زيت زيتون"),
            ({"name": "Honey Dairy", "category": "Dairy store"},
             "040900", "عسل")):
        assert not SC.lead_product_fit(lead, hs, prod, "MYS")[0], lead


def test_naming_in_the_narrative_does_not_rescue_a_clear_mismatch():
    dr = {"market": {"iso3": "MYS", "name_en": "Malaysia",
                     "name_ar": "ماليزيا"},
          "product": "قهوة محمصة", "hs_code": "090121",
          "report": {"text": "يمكن التعاون مع Ocean Seafood Trading وKopi Hub."}}
    leads = [{"name": "Ocean Seafood Trading", "category": "Seafood wholesaler",
              "phone": "+60 3 1111 1111", "address": "Kuala Lumpur, Malaysia"},
             {"name": "Kopi Hub", "category": "Coffee wholesaler",
              "phone": "+60 3 2222 2222", "address": "Kuala Lumpur, Malaysia"}]
    kept = SR._clean_leads(leads, dr)
    assert [k["name"] for k in kept] == ["Kopi Hub"]
    assert kept[0]["evidence_status"] == SC.EVIDENCE_SPECIALIST
    assert any("متخصّصٌ بمنتجٍ آخر" in d["why"] for d in dr["leads_dropped"])


def test_reason_and_candidate_mark_follow_the_evidence_status():
    import silk_reports as R
    named = {"name": "شركة الوفاء", "evidence_status": "named_unverified"}
    cells = R._lead_cells(named, "ar")
    assert len(cells) == 6 and "مرشّحةٌ تحتاج تحققاً" in cells[0]
    spec = {"name": "Golden Coffee Beans", "evidence_status": "specialist"}
    assert R._lead_reason(spec, "ar") == "صلتُها بالمنتج ظاهرةٌ في اسمها"
    gen_spec = {"name": "Golden Coffee Trading", "category": "شركة تجارية",
                "category_raw": "Trading company",
                "evidence_status": "specialist"}
    assert "شركة تجارية" not in R._lead_reason(gen_spec, "ar")
    gen = {"name": "ABC", "category": "شركة تجارية",
           "category_raw": "Trading company", "evidence_status": "general_trader"}
    assert "Trading company" in R._lead_reason(gen, "en")
    assert "شركة" not in R._lead_reason(gen, "en")


def test_the_anchor_never_compares_a_kilo_with_a_litre():
    import silk_economics as E
    out = E.economics_view({"missions": {"pricing_scout": {"findings": [
        {"value": "سعر رف 30 MYR", "note": "سعر رف لعبوة 1 كجم"},
        {"value": "سعر رف 25 MYR", "note": "سعر رف لعبوة 1 لتر"}]}}},
        market_iso3="MYS")
    assert out["anchor_price"]["raw_value"] == 30.0
    assert any("بوحدة قياسٍ أخرى" in g for g in out["gaps"])
