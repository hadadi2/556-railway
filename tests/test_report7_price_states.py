"""تقرير سِلك ٧ — حالاتُ صفّ السعر والمنتجُ المكافئ ونوعُ الصرف (§3.3، §3.4، الدرس ٢٨١).

An instant or 3-in-1 coffee price is not a reference for roasted beans; a
weak search result is shown as needing a check and is not an anchor; every
row carries its state, its ISO currency, pack weight, link and observation
date when they are readable; and the exchange rate says it is an annual
average, not the rate on the observation day.

كلُّ الحالات مصطنعةٌ لاختبارٍ هرمتيّ.
"""
from docx import Document

import silk_economics as E
import silk_render as R
import silk_reports as SR


def _dr(*rows):
    return {"market": {"iso3": "MYS"}, "missions": {"pricing_scout": {
        "findings": [dict(value=v, note="سعر رف في متجر", source="shopee",
                          confidence=c) for v, c in rows]}}}


def test_instant_and_premix_are_not_equivalent_to_roasted_beans():
    assert E.non_equivalent_basis("Nescafe instant 200g RM 25", "090121")
    assert E.non_equivalent_basis("Kopi 3in1 30 sachets RM 12", "090121")
    assert E.non_equivalent_basis("قهوة بيضاء مع السكر", "090121")
    assert not E.non_equivalent_basis("بن محمص 250 غ 30 رينجيت", "090121")
    # البادئةُ تحدّ القاعدة: «instant» لا تمسّ صنفاً آخر.
    assert not E.non_equivalent_basis("instant noodles", "190230")


def test_a_non_equivalent_price_never_becomes_the_anchor():
    v = E.economics_view(_dr(("Nescafe instant 200g RM 20 سعر رف", 0.8),
                             ("Roasted beans 250g RM 30 سعر رف", 0.8)),
                         market_iso3="MYS", hs_code="090121")
    gaps = " ".join(v.get("gaps") or [])
    assert "لمنتج غير مكافئ" in gaps
    anchor = (v.get("reverse_solve") or {}).get("shelf_anchor") or {}
    assert "instant" not in str(anchor)


def test_only_non_equivalent_prices_leave_no_anchor_and_say_so():
    v = E.economics_view(_dr(("Nescafe instant 200g RM 20 سعر رف", 0.8)),
                         market_iso3="MYS", hs_code="090121")
    gaps = " ".join(v["gaps"])
    assert "لا سعر رف لمنتج مكافئ ومثبت مرصود بعد" in gaps
    # مراجعة §58: لا «لا سعر رف منافس مرصود» يناقض الاستبعادَ المعلن.
    assert "لا سعر رف منافس مرصود" not in gaps
    assert (v.get("reverse_solve") or {}).get("max_exw") is None


def test_a_weak_search_result_is_not_an_anchor():
    v = E.economics_view(_dr(("Roasted beans 250g RM 30 سعر رف", 0.5)),
                         market_iso3="MYS", hs_code="090121")
    assert "من نتائج بحث تحتاج تحققاً" in " ".join(v["gaps"])
    assert (v.get("reverse_solve") or {}).get("max_exw") is None


def test_each_row_carries_its_state_and_readable_fields():
    rows = [
        R._price_observation({"value": "Nescafe instant 200g RM 25",
                              "note": "سعر رف", "confidence": 0.8}, "090121", "MYR"),
        R._price_observation({"value": "Roasted beans 250g RM 30",
                              "note": "https://shopee.com.my/p/1",
                              "confidence": 0.3}, "090121", "MYR"),
        R._price_observation({"value": "30", "note": "سعر رف",
                              "confidence": 0.9}, "090121", "MYR"),
        R._price_observation({"value": "Roasted beans 250g RM 30",
                              "note": "سعر رف", "confidence": 0.9,
                              "retrieved_at": "2026-09-10T08:00:00"},
                             "090121", "MYR")]
    assert [r["status"] for r in rows] == [
        R.PRICE_STATUS_NON_EQUIVALENT, R.PRICE_STATUS_NEEDS_CHECK,
        R.PRICE_STATUS_INCOMPLETE, R.PRICE_STATUS_COMPARABLE]
    assert len({r["reason"] for r in rows}) == 4, "لا تُقال الحالاتُ بجملةٍ واحدة"
    ok = rows[3]
    assert ok["currency"] == "MYR" and ok["pack_kg"] == 0.25
    assert ok["observed_at"] == "2026-09-10"
    assert rows[1]["url"] == "https://shopee.com.my/p/1"


def test_the_client_list_shows_the_reason_and_the_observation_date():
    doc = Document()
    SR._client_price_observations(doc, {"price_rows": [
        {"value": "Roasted beans 250g RM 30", "note": "Roasted beans 250g RM 30",
         "reason": "", "observed_at": "2026-09-10"},
        {"value": "Nescafe instant 200g RM 25", "note": "Nescafe instant 200g RM 25",
         "reason": R.PRICE_REASON_NON_EQUIVALENT}]}, "ar")
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "رُصد 2026-09-10" in text and "منتج غير مكافئ" in text


def test_the_exchange_rate_is_named_an_annual_average():
    dr = _dr(("Roasted beans 1kg RM 60 سعر رف", 0.8))
    dr["missions"]["risk_news"] = {"findings": [
        {"value": 4.5, "source": "World Bank", "confidence": 0.9,
         "data_year": 2024, "note": "سعر الصرف الرسمي 2024 (MYR/USD)"}]}
    dr["missions"]["trade_flow"] = {"findings": [
        {"value": 6.0, "source": "UN Comtrade", "confidence": 0.9,
         "data_year": 2024, "note": "متوسط سعر استيراد 2024 USD/kg"}]}
    v = E.economics_view(dr, market_iso3="MYS", hs_code="090121")
    rs = v.get("reverse_solve") or {}
    assert rs.get("fx", {}).get("type") == "annual_average"
    assert any("متوسط سنوي 2024" in p and "لا سعر يوم الرصد" in p
               for p in rs.get("parameters") or [])


# ── مراجعة §58 ──────────────────────────────────────────────────────────────

def test_arabic_forms_with_clitics_and_suffixes_are_caught():
    for t in ("قهوة فورية 200 غ", "القهوة الفورية", "قهوة 3 في 1", "بالسكر"):
        assert E.non_equivalent_basis(t, "090121"), t


def test_negation_and_the_search_query_do_not_mark_real_beans():
    assert not E.non_equivalent_basis("بن محمص غير فوري", "090121")
    assert not E.non_equivalent_basis("roasted beans, not instant", "090121")
    assert not E.non_equivalent_basis(
        "Roasted beans 250g RM 30 مبني على: organic result for "
        "'kopi 3in1 vs roasted beans'", "090121")


def test_a_weak_wholesale_row_is_not_counted_as_a_shelf_exclusion():
    dr = {"market": {"iso3": "MYS"}, "missions": {"pricing_scout": {"findings": [
        {"value": "سعر جملة 20 رينجيت للكيلو", "note": "سعر جملة",
         "confidence": 0.4}]}}}
    gaps = " ".join(E.economics_view(dr, market_iso3="MYS",
                                     hs_code="090121")["gaps"])
    assert "من نتائج بحث تحتاج تحققاً" not in gaps


def test_the_display_and_the_anchor_share_one_state():
    dp = {"value": "Nescafe instant 200g RM 20 سعر رف", "note": "سعر رف",
          "confidence": 0.3}
    assert R._price_observation(dp, "090121", "MYR")["status"] == \
        R.PRICE_STATUS_NON_EQUIVALENT
    gaps = " ".join(E.economics_view(_dr((dp["value"], 0.3)), market_iso3="MYS",
                                     hs_code="090121")["gaps"])
    assert "لمنتج غير مكافئ" in gaps and "من نتائج بحث" not in gaps


def test_the_structured_url_wins_and_an_unresolved_currency_is_incomplete():
    row = R._price_observation({"value": "Roasted 250g RM 30", "note": "x",
                                "confidence": 0.8, "url": "https://shop.my/p/9"},
                               "090121", "MYR")
    assert row["url"] == "https://shop.my/p/9"
    row = R._price_observation({"value": "بن 250 غ 45 ريال", "note": "سعر رف",
                                "confidence": 0.8}, "090121", "MYR")
    assert row["status"] == R.PRICE_STATUS_INCOMPLETE
    assert row["reason"] == R.PRICE_REASON_CURRENCY_UNRESOLVED
