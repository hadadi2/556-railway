"""محرك دراسة السوق — القواعد الحاكمة، الموجتان ١ و٣ (كلتاهما SHADOW):
وكيل الميثاق (silk_charter) + سجلّ الحقائق ودرجات المصادر
(silk_fact_records) + وكيل التناقض (silk_contradiction) + حقّ الحَكَم في
الامتناع (silk_judge_abstain، القاعدة ٥).

حادثة دراسة #9 (المرجع الوحيد لهاتين الموجتين): دراسةٌ عامة عن «الحليب»
حُلِّلت على HS 040110 (منزوع الدسم ≤١٪ حصراً)، وفجوةُ مرآة ٥٫٦× لم تُختبَر
كتضييق نطاقٍ أولاً، ومسارُ نقلٍ بحريٌّ افتراضيٌّ رغم حدودٍ برّية، وعلاوةُ
سعرٍ ~٥٠٪ لم تُحلَّل قط، وحكمٌ سُجِّل ١٦٪ رفضاً من عمودين غير مقاسين بدل
الامتناع.

هاتان الموجتان SHADOW فقط: تُحسَب المكوّنات وتُرفَق (`result["charter"]`،
`view["deep_research"]["charter"]`، `judge_abstain_shadow`) دون أن توقف
أيّ تشغيلة حقيقية إلا خلف صمّامٍ صريح (`SILK_CHARTER_ENFORCE=1` للميثاق؛
لا صمّام مقابل للامتناع بعد — لا مفهوم ABSTAIN رسمي في `synthesize`/
`silk_decision` اليوم). الكاتب (§6) وسقفُ الفجوات (§8) موجاتٌ لاحقة —
غير مُدَّعاتين هنا.
"""
import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from conftest import block_network

import silk_charter
import silk_contradiction
import silk_fact_records
import silk_judge_abstain


@contextlib.contextmanager
def _env(**vals):
    old = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── وكيل الميثاق — معيار القبول ١: يتوقّف عند 040110 لدراسة حليب عامة ──────
# ملاحظة: اسم المنتج "milk" (لا "حليب") عمداً — التداخل اللفظي مع وصف الرمز
# الإنجليزي («milk … not exceeding 1%») يُصادِق زوراً على 040110 (نفس حادثة
# دراسة #9 حرفياً: تداخل الكلمة الواحدة "milk" يكفي القبول التقليدي، ولا
# صفة درجة في الاسم لتحفيز تعارض `confirm_hs` الصريح القائم) — وهنا بالذات
# تضييقُ الميثاق الجديد (الصامت) هو ما يوقف الدراسة، لا فرعُ التعارض القديم.

def test_acceptance_1_charter_halts_on_generic_milk_vs_hs_040110():
    with block_network():
        charter = silk_charter.build_charter("milk", "040110", market_iso3="NLD")
    assert charter.halted is True
    assert charter.excluded_attributes
    assert "040110" in charter.halt_reason
    assert charter.charter_confidence == 0.0
    assert charter.to_dict()["halted"] is True    # مجمَّد إلى dict كما هو


def test_charter_does_not_halt_when_variant_explicitly_declared():
    with block_network():
        charter = silk_charter.build_charter(
            "milk", "040110", market_iso3="NLD",
            declared_attributes=["skimmed", "1% fat", "منزوع الدسم"])
    assert charter.halted is False
    assert charter.charter_confidence > 0.0


def test_charter_declared_attribute_recognized_even_without_literal_desc_overlap():
    """مراجعة الشيفرة (code-review): الفحص السابق كان يقارن صفات الدراسة
    **بنصّ وصف الرمز الإنجليزي حرفياً** — صفةٌ عربية («منزوع الدسم») لا
    تتقاطع لفظياً أبداً مع "fat content ... not exceeding 1%" فتُستبعَد
    زوراً رغم تصريحٍ صريح. الإصلاح: الإشارة صفةُ درجة/كمّية لغوية عامة
    (`_DEGREE_TERMS`) في اسم المنتج أو التصريح — لا تطابق نصّ الوصف."""
    with block_network():
        charter = silk_charter.build_charter(
            "milk", "040110", market_iso3="NLD",
            declared_attributes=["منزوع الدسم"])   # صفر تقاطع لفظي مع الوصف الإنجليزي
    assert charter.halted is False


def test_charter_generic_declared_attribute_without_degree_term_still_halts():
    # صفةٌ مصرَّحة لكنها لا تحمل معنى درجة/كمّية إطلاقاً (مثل ذكر السوق) —
    # لا تُعَدّ توافقاً على تضييق HS، فيبقى التضييقُ الصامت مُعلَناً.
    with block_network():
        charter = silk_charter.build_charter(
            "milk", "040110", market_iso3="NLD",
            declared_attributes=["organic", "بقري"])
    assert charter.halted is True


def test_charter_catches_explicit_negation_conflict_too():
    # full fat milk صراحةً يناقض 040110 — يكتشفه confirm_hs الموجود أصلاً،
    # ويستهلكه الميثاق كفرعه الأول (تعارضٌ لفظيٌّ صريح).
    with block_network():
        charter = silk_charter.build_charter("full fat milk", "040110")
    assert charter.halted is True


def test_charter_no_hs_code_never_halts_and_is_low_confidence():
    with block_network():
        charter = silk_charter.build_charter("منتج غير محسوم", None)
    assert charter.halted is False
    assert charter.charter_confidence == 0.0     # لا حكم بلا رمز — لا اختلاق


# ── وكيل الميثاق — معيار القبول ٣: يحلّل المعبر البرّي، لا ميناء العقبة ─────

def test_acceptance_3_land_neighbor_analyzed_via_land_crossing_not_port():
    out = silk_charter.determine_transport_mode("JOR")
    assert out["mode"] == "land"
    assert "برّية" in out["reason"]


def test_transport_mode_defaults_to_sea_for_non_adjacent_market():
    out = silk_charter.determine_transport_mode("NLD")
    assert out["mode"] == "sea"


def test_transport_mode_causeway_linked_bahrain_is_land():
    assert silk_charter.determine_transport_mode("BHR")["mode"] == "land"


def test_transport_mode_none_iso3_is_declared_gap_not_a_guess():
    out = silk_charter.determine_transport_mode(None)
    assert out["mode"] is None


# ── سجلّ الحقائق ودرجات المصادر ──────────────────────────────────────────

def test_acceptance_6_interest_bearing_association_is_tier_x_not_b():
    # جمعيةٌ تنشر "تقريراً قطاعياً" (ظاهرياً B) تبقى X — موقفٌ ترويجيّ لا دليل.
    tier = silk_fact_records.classify_tier(
        "اتحاد منتجي الألبان — تقرير قطاعي", "الجمعية تدعم موقف أعضائها")
    assert tier == "X"
    assert silk_fact_records.TIER_WEIGHTS[tier] == 0.0
    assert tier not in silk_fact_records.VERDICT_ELIGIBLE_TIERS


def test_source_tier_classification_a_b_c():
    assert silk_fact_records.classify_tier("UN Comtrade") == "A"
    assert silk_fact_records.classify_tier("Central Bank of Jordan") == "A"
    assert silk_fact_records.classify_tier("Trade press report") == "B"
    assert silk_fact_records.classify_tier("web search result") == "C"
    assert silk_fact_records.classify_tier("مصدرٌ غير معروف") == "C"   # لا A/B افتراضية


def test_effective_confidence_formula_literal():
    # effective = agent_conf × charter_conf × tier_weight × (0.5 إن متحيّز)
    assert silk_fact_records.effective_confidence(0.9, 1.0, "A") == pytest.approx(0.9)
    assert silk_fact_records.effective_confidence(0.9, 1.0, "B") == pytest.approx(0.72)
    assert silk_fact_records.effective_confidence(0.9, 1.0, "X") == 0.0
    assert silk_fact_records.effective_confidence(0.9, 1.0, "A", biased=True) == pytest.approx(0.45)
    # ثقة ميثاق ضعيفة (رمز HS مهزوز) تُسقِط كل ما بعده تلقائياً.
    assert silk_fact_records.effective_confidence(0.9, 0.0, "A") == 0.0


def test_report_confidence_is_weighted_minimum_not_average():
    assert silk_fact_records.report_confidence(
        {"trade": 0.9, "competition": 0.2, "regulatory": 0.8}) == pytest.approx(0.2)
    assert silk_fact_records.report_confidence({}) is None       # فجوة معلنة لا صفر مختلَق
    assert silk_fact_records.report_confidence({"a": None}) is None


def test_fact_record_schema_and_computed_fields_not_self_declared():
    rec = silk_fact_records.FactRecord(
        claim="نمو الاستيراد ١٥٪", value=15, unit="%",
        source_name="UN Comtrade", source_date="2024",
        scope_hs_code="080410", agent_confidence=0.9,
        charter_hs_code="080410", charter_confidence=1.0)
    d = rec.to_dict()
    for key in ("claim", "value", "unit", "source", "scope", "bias_flag",
               "agent_confidence", "effective_confidence", "verdict_eligible",
               "depends_on"):
        assert key in d, key
    assert d["source"]["tier"] == "A"
    assert d["scope"]["matches_charter"] is True
    assert d["verdict_eligible"] is True
    assert d["effective_confidence"] == pytest.approx(0.9)


def test_fact_record_scope_mismatch_zeroes_effective_confidence():
    # سجلّ برمز HS مختلف عن ميثاق التشغيلة المجمَّد — لا يطابق، فثقتُه الفعلية صفر.
    rec = silk_fact_records.FactRecord(
        claim="x", value=1, unit=None, source_name="UN Comtrade",
        source_date="2024", scope_hs_code="040110", agent_confidence=0.9,
        charter_hs_code="080410", charter_confidence=1.0)
    d = rec.to_dict()
    assert d["scope"]["matches_charter"] is False
    assert d["effective_confidence"] == 0.0
    # مراجعة الشيفرة (code-review): درجةٌ A لا تكفي وحدها للأهلية — سجلٌّ
    # خارج نطاق الميثاق المجمَّد غيرُ مؤهَّل للحكم مهما كانت درجةُ مصدره
    # (نفس عائلة «منهجيةٌ تتبرّأ من رقمٍ ثم يستخدمه الملخّص نفسُه»).
    assert d["verdict_eligible"] is False


def test_fact_record_verdict_eligible_requires_tier_a_and_charter_match():
    tier_a_out_of_scope = silk_fact_records.FactRecord(
        claim="x", value=1, unit=None, source_name="UN Comtrade",
        source_date="2024", scope_hs_code="999999", agent_confidence=0.9,
        charter_hs_code="080410", charter_confidence=1.0)
    assert tier_a_out_of_scope.to_dict()["verdict_eligible"] is False

    tier_b_in_scope = silk_fact_records.FactRecord(
        claim="x", value=1, unit=None, source_name="Trade press report",
        source_date="2024", scope_hs_code="080410", agent_confidence=0.9,
        charter_hs_code="080410", charter_confidence=1.0)
    assert tier_b_in_scope.to_dict()["verdict_eligible"] is False   # B مساندة لا مؤهَّلة

    tier_a_in_scope = silk_fact_records.FactRecord(
        claim="x", value=1, unit=None, source_name="UN Comtrade",
        source_date="2024", scope_hs_code="080410", agent_confidence=0.9,
        charter_hs_code="080410", charter_confidence=1.0)
    assert tier_a_in_scope.to_dict()["verdict_eligible"] is True


def test_flags_growth_without_base_regulation_and_partner_rules():
    assert silk_fact_records.flags_growth_without_base(
        "نمو الاستيراد ١٥٪", has_base_volume=False) == "UNVERIFIED_GROWTH_NO_BASE"
    assert silk_fact_records.flags_growth_without_base(
        "نمو الاستيراد ١٥٪ من ١٠٠ طن", has_base_volume=True) is None
    assert silk_fact_records.flags_regulation_without_number(
        "يلزم معيار مطابقة", has_regulation_number=False) == "UNVERIFIED"
    assert silk_fact_records.flags_regulation_without_number(
        "المعيار GSO 9/2019", has_regulation_number=True) is None
    assert silk_fact_records.flags_named_partner_without_registry(
        has_partner_name=True, has_registry_source=False) == "UNVERIFIED_LEADS"
    assert silk_fact_records.flags_named_partner_without_registry(
        has_partner_name=True, has_registry_source=True) is None


# ── وكيل التناقض — معيار القبول ٢: فجوة مرآة > ٢× ⇒ عدم تطابق HS أولاً ─────

def test_acceptance_2_mirror_gap_challenges_hs_scope_first():
    gap = silk_contradiction.detect_mirror_gap(export_value=100, import_value=560)
    assert gap["conflict"] is True
    assert gap["hypothesis"] == "hs_scope_mismatch"
    assert gap["ratio"] == pytest.approx(5.6, abs=0.01)
    assert "جمرك" not in gap["note"] or "عدم تطابق" in gap["note"]


def test_mirror_gap_below_threshold_is_not_a_conflict():
    assert silk_contradiction.detect_mirror_gap(100, 150) is None


def test_mirror_gap_challenge_cycle_cap_at_three():
    gap = silk_contradiction.detect_mirror_gap(100, 560, cycle=3)
    assert gap["challenge_exhausted"] is True
    gap2 = silk_contradiction.detect_mirror_gap(100, 560, cycle=2)
    assert gap2["challenge_exhausted"] is False


def test_mirror_gap_missing_values_is_a_declared_gap_not_a_verdict():
    assert silk_contradiction.detect_mirror_gap(None, 100) is None
    assert silk_contradiction.detect_mirror_gap(100, None) is None


# ── وكيل التناقض — معيار القبول ٤: علاوة السعر = تمايز لا إغلاق ────────────

def test_acceptance_4_import_premium_reads_as_differentiated_not_closed():
    synth = silk_contradiction.import_premium_synthesis(
        imported_price=0.85, local_price=0.55, imported_brand="علامة مستوردة")
    assert synth["signal"] == "differentiated_not_closed"
    assert synth["premium_pct"] == pytest.approx(54.5, abs=0.5)


def test_import_premium_below_threshold_is_not_a_signal():
    assert silk_contradiction.import_premium_synthesis(1.0, 0.95) is None


# ── وكيل التناقض — معيار القبول ٥: اتجاهٌ واعٍ بالمنشأ = فرصة ─────────────

def test_acceptance_5_origin_aware_rising_trend_is_an_opportunity_signal():
    findings = [
        {"query": "علامة تصدير", "rising": True, "brand_origin_iso3": "SAU"},
        {"query": "علامة محلية", "rising": True, "brand_origin_iso3": "NLD"},
        {"query": "علامة ثالثة", "rising": False, "brand_origin_iso3": "SAU"},
    ]
    signals = silk_contradiction.origin_aware_trend_synthesis(findings, "SAU")
    assert len(signals) == 1
    assert signals[0]["signal"] == "opportunity"
    assert signals[0]["brand_origin_iso3"] == "SAU"


def test_origin_aware_trend_synthesis_no_hardcoded_brand_or_product():
    # القاعدة (عائلة hardcoded-product-rule): صفر اسم علامة/منتج مكتوب صلباً
    # في منطق الوكيل نفسه — إشاراتٌ من بيانات المُدخَل حصراً.
    import inspect
    src = inspect.getsource(silk_contradiction.origin_aware_trend_synthesis)
    for forbidden in ("Almarai", "المراعي", "milk", "حليب"):
        assert forbidden not in src


def test_contradiction_report_zero_external_calls_structurally_and_behaviorally():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(silk_contradiction))
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree)
               if isinstance(n, ast.Import)}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom)}
    assert imported.isdisjoint({"requests", "urllib", "http", "socket",
                                "httpx", "anthropic", "silk_ai_judge"})
    with block_network():
        report = silk_contradiction.build_contradiction_report(
            export_value=100, import_value=560, imported_price=0.85,
            local_price=0.55, imported_brand="b",
            trend_findings=[{"query": "q", "rising": True,
                             "brand_origin_iso3": "SAU"}],
            exporting_country_iso3="SAU")
    assert report.conflicts and report.synthesis_records
    assert report.strongest_counter_argument


# ── الترابط مع خط الأنابيب — SHADOW فقط، لا كسر لسلوكٍ قائم ────────────────

def test_deep_research_attaches_charter_shadow_mode_without_halting(monkeypatch):
    """صمّام SILK_CHARTER_ENFORCE مُطفأ افتراضياً: الميثاق يُرفَق (`result
    ["charter"]`) لكن `run_all_missions` يُستدعى دوماً — لا كسرَ لسلوكٍ
    قائم (قاعدة الطرح، البند ١٠: SHADOW لا يوقف شيئاً)."""
    import silk_missions
    from silk_market_resolver import MarketRef

    called = {}

    def _fake_run_all_missions(market, **kw):
        called["ran"] = True
        return {}

    monkeypatch.setattr(silk_missions, "run_all_missions", _fake_run_all_missions)
    market = MarketRef(iso3="NLD", m49="528", name_en="Netherlands", name_ar="هولندا")
    with _env(SILK_CHARTER_ENFORCE=None):
        with block_network():
            out = silk_missions.deep_research(market, product="milk", hs_code="040110")
    assert called.get("ran") is True
    assert out["mode"] == "full"
    assert out["charter"]["halted"] is True     # يُحسَب ويُرفَق ولو كان سيوقف


def test_deep_research_enforce_flag_halts_before_running_missions(monkeypatch):
    """صمّامٌ صريح `SILK_CHARTER_ENFORCE=1` — الميثاقُ المتوقِّف يمنع
    `run_all_missions` من التشغيل إطلاقاً (لا نداءات مهدرة على تشغيلةٍ
    محكومٍ عليها بالفشل من نطاق HS)."""
    import silk_missions
    from silk_market_resolver import MarketRef

    def _must_not_run(market, **kw):
        raise AssertionError("run_all_missions لا يجب أن يُستدعى بعد توقّف الميثاق")

    monkeypatch.setattr(silk_missions, "run_all_missions", _must_not_run)
    market = MarketRef(iso3="NLD", m49="528", name_en="Netherlands", name_ar="هولندا")
    with _env(SILK_CHARTER_ENFORCE="1"):
        with block_network():
            out = silk_missions.deep_research(market, product="milk", hs_code="040110")
    assert out["mode"] == "halted"
    assert out["charter"]["halted"] is True
    assert out["reports"] == {}


def test_deep_research_enforce_flag_does_not_halt_a_healthy_charter(monkeypatch):
    import silk_missions
    from silk_market_resolver import MarketRef

    called = {}

    def _fake_run_all_missions(market, **kw):
        called["ran"] = True
        return {}

    monkeypatch.setattr(silk_missions, "run_all_missions", _fake_run_all_missions)
    market = MarketRef(iso3="NLD", m49="528", name_en="Netherlands", name_ar="هولندا")
    with _env(SILK_CHARTER_ENFORCE="1"):
        with block_network():
            out = silk_missions.deep_research(market, product="تمور", hs_code="080410")
    assert called.get("ran") is True
    assert out["mode"] == "full"
    assert out["charter"]["halted"] is False


def test_build_view_passes_charter_through_additively():
    """`view["deep_research"]["charter"]` إضافيٌّ بحت — مدوّنة قانونية بلا
    مفتاح charter تحصل على {} بدل KeyError؛ مدوّنة تحمله تحصل عليه كما هو."""
    import silk_render
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    from canonical_netherlands import netherlands_research_blob

    blob = netherlands_research_blob()
    view = silk_render.build_view(blob)
    assert view["deep_research"]["charter"] == {}     # عدم الوجود = {} لا كسر

    blob2 = netherlands_research_blob()
    blob2["deep_research"]["charter"] = {"halted": True, "halt_reason": "x"}
    view2 = silk_render.build_view(blob2)
    assert view2["deep_research"]["charter"]["halted"] is True


# ── المُطعِّم ضدّ مدوّناتٍ حقيقية الشكل — تصحيح المسار (ملاحظة المُشرِف) ─────
# لا يكفي أن يعمل الميثاق/المُطعِّم على سيناريوهات اصطناعية مصمَّمة؛ الاختبارات
# هنا تشغّلهما ضدّ tools/canonical_*.py — إعادات بناءٍ موثّقة لحوادث إنتاجية
# حقيقية (كل ملف يوثّق بلاغه في رأسه) — ثلاثةٌ منها حوادث سوء تصنيف HS
# **موثّقة مسبقاً**: «زبدة الفول السوداني» على HS 040510 (زبدة ألبان لا
# فول سوداني) في DZA/KWT/YEM، مقابل نسختها المصحَّحة على 200811 في QAT.

def _import_tools_module(mod_name: str):
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import importlib
    return importlib.import_module(mod_name)


def test_charter_catches_the_three_documented_peanut_butter_misclassifications():
    """DZA/KWT/YEM: «زبدة الفول السوداني» على HS 040510 حادثةٌ موثّقة (سوء
    تصنيف حقيقي — الرمز «زبدة» ألبان، لا يشمل «فول»/«سوداني»). الميثاق
    يتوقّف على الثلاثة بلا استثناء — لا يعتمد على تركيبةٍ اصطناعية له."""
    for mod_name, fn_name, iso3 in [
        ("canonical_dza_peanut_butter", "dza_research_blob", "DZA"),
        ("canonical_kuwait_peanut_butter", "kuwait_research_blob", "KWT"),
        ("canonical_yemen", "yemen_research_blob", "YEM"),
    ]:
        mod = _import_tools_module(mod_name)
        blob = getattr(mod, fn_name)()
        charter = silk_charter.build_charter(
            blob["product"], blob["hs_code"],
            market_iso3=(blob.get("market") or {}).get("iso3"))
        assert charter.halted is True, f"{mod_name}: لم يُكتشَف سوء التصنيف الموثّق"
        assert charter.hs_code == "040510"


def test_study9_reference_fixture_exercises_all_five_wave1_mechanisms():
    """`canonical_jordan_milk.py` — إعادةُ بناءٍ **اصطناعية معلَنة** لحادثة
    دراسة #9، الحالة المرجعية الوحيدة التي يستند إليها أمرُ المُشرِف كاملاً
    (خلافاً لبقية `canonical_*.py` وهي حوادثُ حقيقيةٌ وقعت فعلاً — راجع
    تصريح رأس الملف). تُمارِس خمس آليات الموجة ١ معاً على مدوّنةٍ واحدة."""
    mod = _import_tools_module("canonical_jordan_milk")
    blob = mod.jordan_milk_research_blob()
    market_iso3 = blob["market"]["iso3"]

    # (١) تضييقٌ صامت + (٢) نقلٌ برّي.
    charter = silk_charter.build_charter(
        blob["product"], blob["hs_code"], market_iso3=market_iso3)
    assert charter.halted is True
    assert silk_charter.determine_transport_mode(market_iso3)["mode"] == "land"

    missions = blob["deep_research"]["missions"]

    # (٣) فجوة مرآة 5.6× من نتائج البعثات الفعلية (لا أرقام مُلفَّقة للاختبار).
    jordan_declared_import = missions["trade_flow"]["findings"][0]["value"]
    saudi_mirror_export = missions["competitors"]["findings"][0]["value"]
    gap = silk_contradiction.detect_mirror_gap(saudi_mirror_export, jordan_declared_import)
    assert gap["hypothesis"] == "hs_scope_mismatch"
    assert gap["ratio"] == pytest.approx(5.6, abs=0.01)

    # (٤) علاوة سعر ~50% من نتائج البعثات الفعلية.
    price_findings = missions["pricing_scout"]["findings"]
    imported_price = price_findings[0]["value"]
    local_price = price_findings[1]["value"]
    premium = silk_contradiction.import_premium_synthesis(imported_price, local_price)
    assert premium["signal"] == "differentiated_not_closed"
    assert premium["premium_pct"] > 45

    # (٥) بيانُ جمعيةٍ ذات مصلحة = Tier X، لا B رغم شكله «تقريراً قطاعياً».
    assoc = missions["consumer_culture"]["findings"][0]
    assert silk_fact_records.classify_tier(assoc["source"], assoc["note"]) == "X"

    # المُطعِّم يعمل على المدوّنة كاملةً بلا إسقاطٍ صامت.
    fr = silk_fact_records.build_fact_records_from_missions(missions, charter)
    assert fr["stats"]["parse_rate"] == 1.0, fr["stats"]["skipped_reasons"]


def test_charter_does_not_falsely_flag_five_correctly_classified_real_studies():
    """صفرُ إنذاراتٍ كاذبة على خمس مدوّناتٍ حقيقية الشكل مصنَّفة بصحة موثّقة —
    منها QAT (نسخةُ زبدة الفول السوداني **المصحَّحة** على 200811، بجوار
    نظيراتها الفاسدة في الاختبار أعلاه)."""
    for mod_name, fn_name in [
        ("canonical_fettuccine", "fettuccine_research_blob"),
        ("canonical_germany_dates", "germany_dates_research_blob"),
        ("canonical_japan_honey", "japan_honey_research_blob"),
        ("canonical_netherlands", "netherlands_research_blob"),
        ("canonical_qatar_peanut_butter", "qatar_research_blob"),
    ]:
        mod = _import_tools_module(mod_name)
        blob = getattr(mod, fn_name)()
        charter = silk_charter.build_charter(
            blob["product"], blob["hs_code"],
            market_iso3=(blob.get("market") or {}).get("iso3"))
        assert charter.halted is False, (
            f"{mod_name}: إنذارٌ كاذب على دراسةٍ مصنَّفة بصحة موثّقة")


def test_fact_records_adapter_parses_real_mission_findings_without_dropping():
    """المُطعِّم يعمل على شكل نتائج البعثات الحقيقي (كما يُخزَّن فعلياً) —
    ليس فقط على FactRecord مبنيٍّ يدوياً في اختبارات أعلاه."""
    mod = _import_tools_module("canonical_netherlands")
    blob = mod.netherlands_research_blob()
    missions = blob["deep_research"]["missions"]
    charter = silk_charter.build_charter(
        blob["product"], blob["hs_code"],
        market_iso3=(blob.get("market") or {}).get("iso3"))
    result = silk_fact_records.build_fact_records_from_missions(missions, charter)
    stats = result["stats"]
    assert stats["total_findings"] > 0
    assert stats["parse_rate"] == 1.0, stats["skipped_reasons"]
    assert all("effective_confidence" in r for r in result["records"])


def test_fact_records_adapter_never_raises_on_malformed_real_shaped_input():
    """حصنٌ سلوكيّ: نتيجةٌ حقيقية الشكل لكن ناقصة (بلا مصدر، أو بلا قيمة
    ونصّ معاً) تُخطَّى معلنةً — لا استثناء يوقف تشغيلةً حقيقية."""
    missions = {
        "m1": {"findings": [
            {"value": None, "source": "", "confidence": 0.0, "note": ""},
            {"value": 5, "source": "UN Comtrade", "confidence": 0.9, "note": "x"},
        ]},
        "m2": {"findings": [object()]},   # كائنٌ عشوائيٌّ بلا أيّ حقل متوقَّع
    }
    charter = silk_charter.build_charter("تمور", "080410", market_iso3="NLD")
    result = silk_fact_records.build_fact_records_from_missions(missions, charter)
    stats = result["stats"]
    assert stats["total_findings"] == 3
    assert stats["parsed"] == 1                # السجلّ الصالح الوحيد
    assert stats["skipped"] == 2
    assert stats["parse_rate"] == pytest.approx(1 / 3, abs=1e-3)


def test_fact_records_adapter_never_treats_a_failed_missions_error_note_as_a_claim():
    """مراجعة الشيفرة (code-review): بعثةٌ فاشلة تضع نصّ الفشل (استثناء/مهلة)
    داخل DataPoint وحيدة (`BaseAgent.run`) — يجب ألّا يتحوّل هذا النصّ إلى
    «حقيقة» بمصدرٍ ودرجةٍ محسوبَين، ويجب ألّا يُحتسَب في معدّل التحويل
    كنجاحٍ (بعثةٌ فاشلة تبدو نجاحاً في القياس نفسه الذي يثبت أن المُطعِّم
    لا يُسقِط شيئاً صامتاً)."""
    missions = {
        "trade_flow": {"failed": True, "findings": [
            {"value": None, "source": "UN Comtrade", "confidence": 0.0,
             "note": "LLMMissionAgent:trade_flow error: TimeoutError: "
                     "upstream call timed out after 90s",
             "retrieved_at": "2026-08-23"}]},
        "demand_trends": {"failed": False, "findings": [
            {"value": 8, "source": "Google Trends", "confidence": 0.7,
             "note": "نمو اهتمام 8%", "retrieved_at": "2026-08-23"}]},
    }
    charter = silk_charter.build_charter("تمور", "080410", market_iso3="NLD")
    result = silk_fact_records.build_fact_records_from_missions(missions, charter)
    stats = result["stats"]
    assert stats["total_findings"] == 2
    assert stats["parsed"] == 1                      # بعثة demand_trends فقط
    assert stats["parse_rate"] == pytest.approx(0.5)
    assert not any("TimeoutError" in r["claim"] for r in result["records"]), (
        "نصّ خطأ داخليّ تسرّب كـ«ادّعاء» في سجلّ حقائق")
    assert any("بعثةٌ فاشلة" in s["reason"] for s in stats["skipped_reasons"])


def test_wave1_adapter_validation_script_runs_end_to_end():
    """قفلُ عدم الانحدار لأداة `tools/wave1_charter_adapter_validation.py` —
    تعمل فعلياً وتُنتج الرقمين المطلوبين على المدوّنات الحقيقية الشكل كلّها."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import wave1_charter_adapter_validation as v

    result = v.run()
    assert len(result["rows"]) == 10
    halted = sum(1 for r in result["rows"] if r["charter_halted"])
    # DZA/KWT/YEM (موثّقة) + nadec_yemen (غير محسومة) + jordan_milk (حادثة #9
    # المرجعية الاصطناعية). لا تُقرأ هذه النسبة كمعدّل توقّفٍ متوقَّع على
    # دراساتٍ حقيقية عشوائية — العيّنة مُثراةٌ بالحوادث عمداً (راجع رأس الأداة).
    assert halted == 5
    assert result["agg_total"] > 0
    # 100% هنا يثبت غياب تعطّلٍ بنيويّ على الشكل المتوقَّع، لا صموداً أمام
    # تنوّع مخرَجات حيّة مُلتقَطة فعلاً (المدوّنات مبنيّةٌ يدوياً على الشكل
    # المتوقَّع — راجع رأس الأداة).
    assert result["agg_parsed"] == result["agg_total"]


# ═══════════════════ الموجة ٣ — حقّ الحَكَم في الامتناع ═══════════════════

def test_would_abstain_on_scope_mismatch_alone():
    """ميثاقٌ متوقِّف (عدم تطابق نطاق) يكفي وحده للامتناع، حتى لو كانت كل
    الأعمدة الخمسة مؤهَّلة بالكامل."""
    charter = silk_charter.build_charter("حليب", "040110", market_iso3="JOR")
    assert charter.halted, "الاختبار يفترض ميثاقاً متوقِّفاً فعلياً"
    by_category = {cat: [{"value": 1, "source": "UN Comtrade", "confidence": 0.9,
                          "note": "x", "retrieved_at": "2026-08-23"}]
                  for cat in ("demand", "entry_cost", "price_competitiveness",
                              "entry_door", "swot")}
    result = silk_judge_abstain.would_abstain(charter=charter, by_category=by_category)
    assert result["scope_mismatch"] is True
    assert result["would_abstain"] is True
    assert result["reasons"]  # سببٌ واحد على الأقل مُسجَّل


def test_would_abstain_on_zero_eligible_pillar_with_matching_charter():
    """ميثاقٌ غير متوقِّف لكن عمود واحد بلا أيّ سجلّ مؤهَّل (Tier A + مطابقة
    نطاق) يكفي وحده للامتناع — لا حاجة لتوقّف الميثاق."""
    charter = silk_charter.build_charter("تمور", "080410", market_iso3="NLD")
    assert not charter.halted
    by_category = {
        "demand": [{"value": 1, "source": "UN Comtrade", "confidence": 0.9,
                    "note": "x", "retrieved_at": "2026-08-23"}],
        "entry_cost": [{"value": 1, "source": "UN Comtrade", "confidence": 0.9,
                        "note": "x", "retrieved_at": "2026-08-23"}],
        "price_competitiveness": [{"value": 1, "source": "UN Comtrade",
                                   "confidence": 0.9, "note": "x",
                                   "retrieved_at": "2026-08-23"}],
        "entry_door": [{"value": 1, "source": "UN Comtrade", "confidence": 0.9,
                        "note": "x", "retrieved_at": "2026-08-23"}],
        "swot": [],   # عمودٌ فارغٌ تماماً — الحالة الوحيدة قيد الاختبار
    }
    result = silk_judge_abstain.would_abstain(charter=charter, by_category=by_category)
    assert result["scope_mismatch"] is False
    assert result["zero_eligible_pillars"] == ["swot"]
    assert result["would_abstain"] is True


def test_would_not_abstain_when_all_five_pillars_eligible_and_charter_matches():
    """كل الأعمدة الخمسة مؤهَّلة + ميثاقٌ مطابق ⇒ لا امتناع (المسار الإيجابي
    الوحيد — يثبت أن الدالّة لا تمتنع افتراضياً بلا سبب)."""
    charter = silk_charter.build_charter("تمور", "080410", market_iso3="NLD")
    assert not charter.halted
    finding = {"value": 1, "source": "UN Comtrade", "confidence": 0.9,
              "note": "x", "retrieved_at": "2026-08-23"}
    by_category = {cat: [finding] for cat in
                  ("demand", "entry_cost", "price_competitiveness",
                   "entry_door", "swot")}
    result = silk_judge_abstain.would_abstain(charter=charter, by_category=by_category)
    assert result["would_abstain"] is False
    assert result["zero_eligible_pillars"] == []
    assert result["reasons"] == []


def test_check_pillar_eligibility_flags_a_pillar_entirely_absent_from_by_category():
    """عمودٌ غائبٌ كلياً من by_category (لا `demand` مثلاً) يُعامَل كـ«صفر
    مؤهَّل»، لا يُتخطَّى بصمت — الحالة الأسوأ يجب أن تُكتشَف، لا أن تختفي."""
    result = silk_judge_abstain.check_pillar_eligibility(
        {"entry_cost": [{"value": 1, "source": "UN Comtrade", "confidence": 0.9,
                         "note": "x", "retrieved_at": "2026-08-23"}]})
    assert "demand" in result["zero_eligible_pillars"]
    assert result["detail"]["demand"] == {"total_records": 0, "eligible_records": 0}


def test_would_abstain_accepts_charter_as_dict_or_object_identically():
    """`charter` يصل إمّا ككائن `Charter` حيّ أو dict (`Charter.to_dict()`
    عبر `research_run.get("charter")` في api.py) — يجب أن يُنتج الشكلان
    نفس الإشارة تماماً (Wave 3 يستهلك الشكل dict فعلياً في الإنتاج)."""
    charter_obj = silk_charter.build_charter("حليب", "040110", market_iso3="JOR")
    charter_dict = charter_obj.to_dict()
    r_obj = silk_judge_abstain.would_abstain(charter=charter_obj, by_category={})
    r_dict = silk_judge_abstain.would_abstain(charter=charter_dict, by_category={})
    assert r_obj["scope_mismatch"] == r_dict["scope_mismatch"] is True
    assert r_obj["would_abstain"] == r_dict["would_abstain"] is True


def test_would_abstain_declares_the_unresolved_critical_conflict_gap_explicitly():
    """الشرط الثالث (تعارضٌ حرجٌ غير محسوم) غير مربوطٍ بعد — يجب أن يُعلَن
    `False` صراحةً باسم فجوة، لا أن يُخلَط بـ«فُحص ولم يُوجَد شيء»."""
    result = silk_judge_abstain.would_abstain(charter=None, by_category={})
    assert result["unresolved_critical_conflict_checked"] is False


def test_would_abstain_on_all_ten_canonical_fixtures_is_dominated_by_fixture_gap():
    """قفلُ عدم الانحدار + توثيق الحدّ الصادق: تشغيل `would_abstain` على
    المدوّنات العشر كلّها يُظهر 10/10 امتناعاً — لكن هذا **ليس** إشارة عن
    معدّل امتناعٍ متوقَّع على دراساتٍ حقيقية. السبب: `entry_door`/`swot`
    غائبان كلياً من كل مدوّنةٍ من العشر بلا استثناء، و`entry_cost` حاضرٌ في
    واحدةٍ فقط (قطر) — فجوةُ بناء مدوّناتٍ (بُنيت لغرض الموجة ١ الأضيق:
    اختبار محوِّل الميثاق/سجلّ الحقائق على عمودي demand/price_competitiveness
    أساساً)، لا سلوك دراساتٍ حقيقية. الاستثناءات ذات الدلالة الحقيقية:
    `price_competitiveness` يُقصى في أغلب المدوّنات لأن مصدره «بحث ويب» غير
    Tier A (يلتقط بالضبط فشل حادثة #9 — علاوة سعرٍ غير محلَّلة من مصدرٍ
    ضعيف)، وحتى `entry_cost` القطري (مصدره «GCC secretariat») يُقصى أيضاً —
    درجة تصنيفه/مطابقته للميثاق تستحق تدقيقاً منفصلاً لا هذا الاختبار. لا رقم
    امتناعٍ حقيقيّ لدراساتٍ فعلية متاحٌ بلا بيانات مُلتقَطة من الإنتاج — نفس
    بوّابة الموجة ١ المفتوحة.

    ملاحظة دقيقة: `entry_cost` حاضرٌ فعلياً في مدوّنة قطر وحدها من العشر —
    الاختبار أدناه يتحقّق من هذه الحقيقة بدقّة (لا يعمّم غياباً كاملاً على
    عمودٍ حاضرٍ في حالة واحدة)."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import importlib

    fixtures = [
        ("canonical_dza_peanut_butter", "dza_research_blob"),
        ("canonical_fettuccine", "fettuccine_research_blob"),
        ("canonical_germany_dates", "germany_dates_research_blob"),
        ("canonical_japan_honey", "japan_honey_research_blob"),
        ("canonical_jordan_milk", "jordan_milk_research_blob"),
        ("canonical_kuwait_peanut_butter", "kuwait_research_blob"),
        ("canonical_nadec_yemen_dairy", "nadec_yemen_research_blob"),
        ("canonical_netherlands", "netherlands_research_blob"),
        ("canonical_qatar_peanut_butter", "qatar_research_blob"),
        ("canonical_yemen", "yemen_research_blob"),
    ]
    abstain_count = 0
    zero_pillar_driven = 0
    for mod_name, fn_name in fixtures:
        mod = importlib.import_module(mod_name)
        blob = getattr(mod, fn_name)()
        market = (blob.get("market") or {}).get("iso3")
        charter = silk_charter.build_charter(
            blob.get("product"), blob.get("hs_code"), market_iso3=market)
        by_category = ((blob.get("deep_research") or {}).get("analyst") or {}
                      ).get("by_category") or {}
        r = silk_judge_abstain.would_abstain(charter=charter, by_category=by_category)
        if r["would_abstain"]:
            abstain_count += 1
        if r["zero_eligible_pillars"]:
            zero_pillar_driven += 1
    assert abstain_count == 10
    assert zero_pillar_driven == 10
    # entry_door/swot غائبان من كل مدوّنةٍ من العشر بلا استثناء — القفل الذي
    # يثبت أن هذا فجوةٌ بنيوية في المدوّنات، لا تباينٌ بينها. entry_cost
    # حاضرٌ في مدوّنة قطر وحدها (استثناءٌ واحد موثَّق أعلاه في التوثيق).
    populated_entry_cost = []
    for mod_name, fn_name in fixtures:
        mod = importlib.import_module(mod_name)
        blob = getattr(mod, fn_name)()
        by_category = ((blob.get("deep_research") or {}).get("analyst") or {}
                      ).get("by_category") or {}
        for absent in ("entry_door", "swot"):
            assert not by_category.get(absent), (
                f"{mod_name}: عمود {absent} يحمل بيانات — إن صار هذا صحيحاً "
                "لكل المدوّنات فحدِّث تعليق هذا الاختبار (لم يعد فجوة بناء)")
        if by_category.get("entry_cost"):
            populated_entry_cost.append(mod_name)
    assert populated_entry_cost == ["canonical_qatar_peanut_butter"], (
        "توزيع entry_cost تغيَّر — حدِّث التوثيق أعلاه ليطابق الواقع الجديد")
