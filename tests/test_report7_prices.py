"""تقرير سِلك ٧ — موجة الأسعار المهيكلة (§3.3–3.4، الدرسان ٢٧٢ و٢٧٣).

structured-prices wave: the shelf anchor is chosen AFTER per-kg normalisation
and inside one currency (never a raw min across currencies); currencies are
compared by ISO code; FX applies only to the currency it quotes and carries
its pair/year/type; an import unit value above the shelf price per kg is
isolated from price comparisons; a price row without a currency says so.

كلُّ الحالات مصطنعةٌ لاختبارٍ هرمتيّ — لا تُقدَّم حالاتٍ ذهبيةً حقيقية.
"""
import silk_economics as E


def _dr(*rows, fx=None, ref=None) -> dict:
    missions = {"pricing_scout": {"findings": [
        {"value": v, "note": n} for v, n in rows]}}
    if fx is not None:
        missions["risk_news"] = {"findings": [
            {"value": fx, "data_year": 2024,
             "note": f"[risk] سعر الصرف الرسمي {fx} (وحدة محلية لكل دولار) "
                     "— PA.NUS.FCRF سنة 2024"}]}
    if ref is not None:
        missions["trade_flow"] = {"findings": [
            {"value": ref, "note": "متوسط سعر استيراد USD/kg"}]}
    return {"missions": missions}


# ── (١) المرساةُ بعد التطبيع لا قبله ─────────────────────────────────────

def test_the_anchor_is_the_lowest_per_kg_not_the_lowest_pack_price():
    """أدنى سعر عبوة ≠ أدنى سعر للكيلوغرام: 12 رينجيت لـ250 غ = 48/كغ،
    و30 رينجيت لـ1 كغ = 30/كغ — المرجعُ الثاني."""
    out = E.economics_view(_dr(
        ("سعر رف 12 MYR", "سعر رف لعبوة 250 غ"),
        ("سعر رف 30 MYR", "سعر رف لعبوة 1 كجم")), market_iso3="MYS")
    a = out["anchor_price"]
    assert a["raw_value"] == 30.0 and a["per_kg"] == 30.0


def test_the_anchor_never_takes_a_raw_min_across_currencies():
    """«$4» لا يغلب «20 رينجيت» لأن رقمه أصغر — لا مقارنة بلا صرف. عملةُ
    السوق المحلية أولاً، والمستبعَد يُعلَن."""
    out = E.economics_view(_dr(
        ("سعر رف 20 MYR", "سعر رف لعبوة 1 كجم"),
        ("سعر رف 4 USD", "سعر رف لعبوة 1 كجم")), market_iso3="MYS")
    a = out["anchor_price"]
    assert a["raw_value"] == 20.0
    assert E._iso(a["currency"]) == "MYR"
    assert any("بعملة أخرى" in g for g in out["gaps"]), out["gaps"]


def test_without_a_local_row_the_largest_currency_group_is_used():
    out = E.economics_view(_dr(
        ("سعر رف 9 EUR", "سعر رف لعبوة 1 كجم"),
        ("سعر رف 7 EUR", "سعر رف لعبوة 1 كجم"),
        ("سعر رف 3 USD", "سعر رف لعبوة 1 كجم")), market_iso3="MYS")
    assert out["anchor_price"]["raw_value"] == 7.0


def test_the_existing_single_currency_lowest_retail_rule_holds():
    """القاعدةُ القائمة داخل عملةٍ واحدة بلا أوزان: أدنى سعر رف."""
    out = E.economics_view(_dr((30.0, "سعر الرف"), (25.0, "shelf price")))
    assert out["anchor_price"]["raw_value"] == 25.0


# ── (٢) العملاتُ تُقارَن برمزها ISO ──────────────────────────────────────

def test_currency_names_and_codes_compare_by_iso():
    assert E._iso("رينجيت") == E._iso("MYR") == "MYR"
    assert E._iso("$") == E._iso("دولار") == E._iso("USD") == "USD"
    assert E._iso("") == ""


def test_cost_and_shelf_currencies_are_matched_by_iso():
    """تكلفةٌ بـ«MYR» وسعرُ رفٍّ بـ«رينجيت»: عملةٌ واحدة — كانت المقارنةُ نصّيةً
    فتُعلَن «لا طرح بين عملتين» زوراً وتسقط نقطةُ التعادل."""
    assert E._same_currency("MYR", "رينجيت")
    assert E._same_currency("$", "USD") and E._same_currency("دولار", "usd")
    assert not E._same_currency("EUR", "MYR")
    # الكلمةُ نفسُها بلا حسمٍ ممكن تبقى مطابقةً نصّية (السلوكُ القائم)،
    # ولا يُخمَّن رمزٌ لاسمٍ واسع.
    assert E._same_currency("دينار", "دينار")
    assert not E._same_currency("درهم", "AED")
    # «ريال» المُصدِّر السعوديّ SAR — يطابق SAR ولا يطابق ريالَ قطر.
    assert E._same_currency("ريال", "SAR")
    assert not E._same_currency("ريال", "ريال", "QAR")
    import inspect
    src = inspect.getsource(E.build_decision_numbers)
    assert "market_ccy or market_currency(market_iso3)" in src
    assert "market_ccy=local_ccy" in inspect.getsource(E.economics_view), \
        "عملةُ السوق تصل مقارنةَ العملتين في الإنتاج لا في الاختبار وحده"


def test_generic_currency_names_resolve_to_the_market_not_a_guess():
    """«ريال» في قطر QAR لا SAR، وفي ماليزيا بلا رمز؛ «$» في سنغافورة SGD
    (قفل c19: الاتجاهُ العكسيّ لا يُخمِّن دولةً لاسمٍ عامّ)."""
    assert E._iso("ريال", "QAR") == "QAR"
    assert E._iso("ريال", "MYR") == "" and E._iso("ريال") == ""
    assert E._iso("$", "SGD") == "SGD" and E._iso("$", "MYR") == "USD"
    assert E._iso("دينار", "KWD") == "KWD"
    # صفوفُ «ريال» في قطر هي عملةُ السوق — لا تُستبعَد «بعملةٍ أخرى».
    out = E.economics_view(_dr(("سعر رف 30 ريال", "سعر رف لعبوة 1 كجم"),
                               ("سعر رف 5 USD", "سعر رف لعبوة 1 كجم")),
                           market_iso3="QAT")
    assert out["anchor_price"]["raw_value"] == 30.0


# ── (٣) الصرفُ لعملته وحدَها، بزوجه وسنته ونوعه ─────────────────────────

def test_fx_is_applied_only_to_the_market_currency_and_carries_its_meta():
    out = E.economics_view(_dr(("سعر رف 60 MYR", "سعر رف لعبوة 1 كجم"),
                               fx=4.5, ref=2.0), market_iso3="MYS")
    rs = out["reverse_solve"]
    assert rs["fx"] == {"pair": "MYR/USD", "rate": 4.5, "year": 2024,
                        "type": "annual_average",
                        "source": "World Bank PA.NUS.FCRF"}


def test_a_market_fx_rate_never_converts_a_price_in_another_currency():
    """صرفُ الرينجيت لا يُطبَّق على سعرٍ باليورو — كان يُقسَم عليه أيّاً كانت
    عملةُ السعر فيُنتج «دولاراً» زائفاً."""
    out = E.economics_view(_dr(("سعر رف 9 EUR", "سعر رف لعبوة 1 كجم"),
                               fx=4.5, ref=2.0), market_iso3="MYS")
    rs = out["reverse_solve"]
    assert rs.get("fx_rate") is None and rs.get("max_exw_usd") is None
    assert any("سعر الصرف المتاح لعملة السوق" in g for g in out["gaps"])


# ── (٤) سعرُ استيرادٍ أعلى من سعر الرف للكيلو يُعزَل ────────────────────

def test_an_import_unit_value_above_the_shelf_price_per_kg_is_isolated():
    """130.68 دولار/كغ عند الحدود وسعرُ الرف 13.3 دولار/كغ: الأول شاذٌّ حتى
    يُفسَّر — لا يبني «تناقضاً سعرياً» ولا يُسقط بقيّة الحساب."""
    out = E.economics_view(_dr(("سعر رف 60 MYR", "سعر رف لعبوة 1 كجم"),
                               fx=4.5, ref=130.68), market_iso3="MYS")
    assert out["pricing_contradiction"] is None
    assert out["reverse_solve"] is not None, "الشذوذُ لا يُعطِّل الحساب كلَّه"
    assert out["import_price_anomaly"]["value_usd_kg"] == 130.68
    assert any("130.68" in g and "استُبعد" in g for g in out["gaps"])


def test_a_plausible_import_price_still_feeds_the_contradiction_check():
    out = E.economics_view(_dr(("سعر رف 60 MYR", "سعر رف لعبوة 1 كجم"),
                               fx=4.5, ref=12.0), market_iso3="MYS")
    assert out["import_price_anomaly"] is None
    # 12 دولار/كغ مقابل رفٍّ 13.3: معقول — وأقصى EXW (~7.9) أدنى من 80% منه،
    # فالتحذيرُ القائم يبقى حيّاً (العزلُ للأضعاف لا لكلّ تجاوز).
    assert out["pricing_contradiction"] is not None


# ── (٥) صفُّ سعرٍ بلا عملة يقول ذلك ─────────────────────────────────────

def test_a_price_row_without_a_currency_says_currency_not_available():
    import silk_render as R
    assert R._price_row_reason("12.5 للعبوة") == "العملة غير متاحة"
    assert R._price_row_reason("علبة 5 دولار") == "الوزن غير متاح"
    assert R._price_row_reason("عبوة كبيرة") == "وحدة غامضة"
    assert R._price_row_reason("سعر 25.80 MYR لعبوة 250 غ") == ""


# ── (٦) أقفالُ المراجعة الذاتية (§58) ─────────────────────────────────────

def test_a_certainly_foreign_currency_never_gets_the_market_fx():
    """«درهم» في ماليزيا ليست الرينجيت يقيناً وإن تعذّر رمزُها."""
    out = E.economics_view(_dr(("سعر رف 30 درهم", "سعر رف لعبوة 1 كجم"),
                               fx=4.5, ref=2.0), market_iso3="MYS")
    rs = out["reverse_solve"]
    assert rs.get("fx") is None and rs.get("max_exw_usd") is None
    assert any("سعر الصرف المتاح لعملة السوق" in g for g in out["gaps"])


def test_local_generic_names_beat_a_foreign_row():
    """ليرةُ تركيا ويوانُ الصين عملةُ السوق — لا يغلبها صفٌّ بالدولار."""
    for iso3, row in (("TUR", "سعر رف 200 ليرة"), ("CHN", "سعر رف 20 يوان")):
        out = E.economics_view(_dr((row, "سعر رف لعبوة 1 كجم"),
                                   ("سعر رف 5 USD", "سعر رف لعبوة 1 كجم")),
                               market_iso3=iso3)
        assert out["anchor_price"]["raw_value"] != 5.0, iso3


def test_every_row_left_out_of_the_choice_is_declared():
    out = E.economics_view(_dr((10.0, "سعر رف لعبوة 1 كجم"),
                               ("سعر رف 30 MYR", "سعر رف لعبوة 1 كجم"),
                               ("سعر رف 50 MYR", "سعر رف")),
                           market_iso3="MYS")
    gap = next(g for g in out["gaps"] if "استُبعد من اختيار" in g)
    assert "بلا عملة مسمّاة" in gap and "بلا وزن عبوة" in gap


def test_a_per_kg_quote_competes_with_pack_prices():
    """«20 MYR للكيلو» أساسُه كيلوغرامٌ واحد — لا يُقصى أمام عبوة 250 غ."""
    out = E.economics_view(_dr(("سعر رف 20 MYR للكيلو", "سعر رف"),
                               ("سعر رف 12 MYR", "سعر رف لعبوة 250 غ")),
                           market_iso3="MYS")
    assert out["anchor_price"]["raw_value"] == 20.0


def test_an_unknown_market_labels_the_fx_pair_as_lcu():
    out = E.economics_view(_dr(("سعر رف 60 رينجيت", "سعر رف لعبوة 1 كجم"),
                               fx=4.5, ref=2.0))
    assert out["reverse_solve"]["fx"]["pair"] == "LCU/USD"


def test_the_gate_never_converts_a_foreign_shelf_price_with_market_fx():
    """الحارسُ الحدوديّ كان يقسم سعرَ رفٍّ باليورو على صرف الرينجيت فيُطلِق
    «سلسلة قيمة مستحيلة» زوراً — الحسمُ الآن من المصدر الواحد نفسِه."""
    import silk_quality_gate as Q
    dr = _dr(("سعر رف 9 يورو", "سعر رف لعبوة 1 كجم"), fx=4.5, ref=5.0)
    dr["market"] = {"iso3": "MYS"}
    assert Q._check_border_price_out_of_range({"deep_research": dr}) == []
    # وسعرُ رفٍّ بعملة السوق يبقى يُحوَّل ويُفحَص كما كان.
    local = _dr(("سعر رف 9 رينجيت", "سعر رف لعبوة 1 كجم"), fx=4.5, ref=5.0)
    local["market"] = {"iso3": "MYS"}
    hits = Q._check_border_price_out_of_range({"deep_research": local})
    assert hits and hits[0]["check"] == "border_price_out_of_range"
