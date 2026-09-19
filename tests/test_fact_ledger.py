"""قفل الدرس ٢٦٢ — سجلّ حقائق واحد يقرأ منه كل سطح (بلاغ المالك: التقرير 6).

test-first: كل حالة هنا تُعيد إنتاج تناقضاً مرصوداً فعلياً أو تقفل قاعدة
قرّرها المالك في 2026-09-19. هرمتي بالكامل — صفر شبكة، صفر مفتاح، صفر إنفاق.

Run: python3 -m pytest tests/test_fact_ledger.py -q
"""
import json
import os
import re
import sys
from contextlib import contextmanager

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import silk_fact_ledger as L                                  # noqa: E402
import silk_render as R                                       # noqa: E402
from canonical_morocco_juice import morocco_juice_research_blob  # noqa: E402
from canonical_netherlands import netherlands_research_blob   # noqa: E402


@contextmanager
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


def _morocco_view():
    return R.build_view(morocco_juice_research_blob())


# ── ١) العيب المؤسِّس: التعرفة مرصودة بصيغة «التعريفة المطبَّقة» ────────────

def test_tariff_written_as_applied_tariff_is_observed_not_missing():
    """direct reproduction (المغرب): البعثة تحمل «تعريفة مطبَّقة 25%» وقسم
    الاقتصاد كان يعلن «اعتُمد 0% — غير متاحة» لأن مفرداته تعرف «تعرفة» فقط."""
    led = L.build_ledger(morocco_juice_research_blob())
    e = led["entries"]["tariff_applied_pct"]
    assert e["status"] != L.MISSING, e
    assert e["value"] == pytest.approx(25.0)


def test_ledger_is_attached_to_the_canonical_view():
    view = _morocco_view()
    assert view.get("ledger"), "السجلّ لا يصل نموذج العرض القانوني"
    assert view["ledger"]["entries"]["tariff_applied_pct"]["value"] == \
        pytest.approx(25.0)


# ── ٢) الحالات الثلاث متمايزة: مرصود / ضعيف التوثيق / ناقص ─────────────────

def test_weak_is_not_missing():
    """«ناقص» و«موجود لكن ضعيف التوثيق» حالتان لا واحدة (طلب المالك)."""
    obs = L._entry("hhi", 3800, source="UN Comtrade", confidence=0.9)
    weak = L._entry("hhi", 3800, source="بحث ويب", confidence=0.4)
    gone = L._entry("hhi", None, note="لا ملخّص مورّدين")
    assert (obs["status"], weak["status"], gone["status"]) == (
        L.OBSERVED, L.WEAK, L.MISSING)
    # الموجة د-١: صيغُ الحالة لغةُ قارئ («من مصادر غير رسمية») لا أسماءُ
    # حالات — والفرقُ بين الثلاث يبقى مقروءاً.
    assert "غير رسمية" in L.render_status(weak)
    assert L.render_status(weak) != L.render_status(obs)
    assert L.render_status(gone) == "غير متاح"


# ── ٣) الشروط: عدد واحد بكل السطوح، وصيغة عربية سليمة ──────────────────────

def test_open_conditions_count_is_one_number_everywhere():
    view = _morocco_view()
    led = view["ledger"]["entries"]["open_conditions"]
    top = (view.get("markets") or [{}])[0]
    ed = top.get("entry_decision") or top.get("decision") or {}
    assert led["value"] == R.open_conditions(ed)["count"]
    for cap in (3, 4, 6, None):
        assert R.open_conditions(ed, cap)["count"] == led["value"]


@pytest.mark.parametrize("n,expected", [
    (0, "لا شروط مفتوحة."), (1, "الشروط المفتوحة شرط واحد."),
    (2, "الشروط المفتوحة شرطان."), (3, "الشروط المفتوحة ثلاثة شروط."),
    (11, "الشروط المفتوحة أحد عشر شرطاً.")])
def test_count_tokens_bind_with_arabic_agreement(n, expected):
    """الشرط ٢: الرمز يُملأ بصيغة سليمة لغوياً — لا «2 شروط»."""
    led = {"entries": {"open_conditions": L._entry(
        "open_conditions", n, source="محرك القرار", confidence=1.0)}}
    out, _ = L.bind("{{open_conditions:sentence}}", led)
    assert out == expected


# ── ٤) الرموز الستة الإلزامية ومنعُ كتابة قيمتها ───────────────────────────

def test_writer_writing_a_mandatory_value_is_rejected_before_storage():
    led = L.build_ledger(morocco_juice_research_blob())
    bad = "الرسوم الجمركية المطبَّقة 25% وفق المصدر الرسمي."
    issues = L.draft_issues(bad, led)
    assert any("رمزٌ إلزامي" in i for i in issues), issues
    good = "الرسوم الجمركية المطبَّقة {{tariff_applied_pct}}."
    assert not L.draft_issues(good, led)


def test_invented_token_is_rejected():
    led = L.build_ledger(morocco_juice_research_blob())
    assert any("غير مسرود" in i
               for i in L.draft_issues("قيمة {{made_up_key}} هنا", led))


# ── ٥) الأرقام الطبيعية: التسامح يمرّ، والمخالفة تُرفض بجملتها ─────────────

def _ledger_with(key, value, **kw):
    kw.setdefault("source", "UN Comtrade")
    kw.setdefault("confidence", 0.9)
    return {"entries": {key: L._entry(key, value, **kw)},
            "order": [key], "gaps": []}


def test_rounded_number_inside_tolerance_passes():
    led = _ledger_with("market_imports_usd", 18_700_000.0)
    assert not L.draft_issues("واردات السوق نحو 18.7 مليون دولار.", led)


def test_verbal_comparison_is_not_number_checked():
    led = _ledger_with("market_imports_usd", 18_700_000.0)
    assert not L.draft_issues("واردات السوق تضاعفت تقريباً خلال الفترة.", led)


def test_number_outside_tolerance_is_rejected_naming_its_sentence():
    led = _ledger_with("market_imports_usd", 18_700_000.0)
    issues = L.draft_issues("واردات السوق نحو 60 مليون دولار سنوياً.", led)
    assert issues and "60" in issues[0] and "أعد صياغة الجملة" in issues[0]


def test_number_for_a_missing_fact_is_rejected():
    led = _ledger_with("saudi_share_pct", None, note="غير ظاهرة")
    issues = L.draft_issues("الحصة السعودية 12% من الواردات.", led)
    assert issues and "غير متاح في السجلّ" in issues[0]


def test_declaring_an_observed_fact_unavailable_is_rejected():
    led = _ledger_with("saudi_share_pct", 30.0)
    issues = L.draft_issues("الحصة السعودية غير متاحة في هذا التشغيل.", led)
    assert issues and "مرصود في السجلّ" in issues[0]


def test_allowed_derived_number_is_not_flagged():
    """الشرط ٤: رقمٌ في سياق مسموح صراحةً (أرقام القرار) لا يُعَدّ مخالفة."""
    led = _ledger_with("market_imports_usd", 18_700_000.0)
    text = "واردات السوق تدعم كلفة الدخول الكلية البالغة 66493 ريالاً."
    assert not L.draft_issues(text, led)


# ── ٦) الملء: لا «غير متاح» وسط جملة كُتبت لرقم ────────────────────────────

def test_missing_fact_replaces_the_whole_line_not_the_slot():
    led = _ledger_with("tariff_applied_pct", None, note="لا تعرفة")
    out, _ = L.bind("- بلغت الرسوم الجمركية {{tariff_applied_pct}} هذا العام.",
                    led)
    assert out == "- الرسوم الجمركية المطبَّقة غير متاح."
    assert "هذا العام" not in out


def test_status_token_renders_a_word_not_a_number():
    led = _ledger_with("hhi", 3800.0)
    out, _ = L.bind("حالة التركّز: {{status:hhi}}.", led)
    assert out == "حالة التركّز: متاح من مصدر موثّق."


# ── ٧) اللقطة: رمز قديم يُعلَّم ولا يُملأ بصمت (الشرط ١) ────────────────────

def test_snapshot_records_only_tokens_the_writer_used():
    led = L.build_ledger(morocco_juice_research_blob())
    snap = L.snapshot_for("التعرفة {{tariff_applied_pct}} والشروط "
                          "{{open_conditions}}.", led)
    assert set(snap) == {"tariff_applied_pct", "open_conditions"}
    assert "leads" not in snap and "hhi" not in snap


def test_changed_fact_since_writing_is_marked_stale():
    led = L.build_ledger(morocco_juice_research_blob())
    snap = L.snapshot_for("{{tariff_applied_pct}}", led)
    snap["tariff_applied_pct"]["value"] = 10.0
    stale = L.stale_keys(snap, led)
    assert [s["key"] for s in stale] == ["tariff_applied_pct"]
    assert stale[0]["was"]["value"] == 10.0
    assert stale[0]["now"]["value"] == pytest.approx(25.0)


def test_unchanged_fact_is_not_stale():
    led = L.build_ledger(morocco_juice_research_blob())
    snap = L.snapshot_for("{{tariff_applied_pct}} {{open_conditions}}", led)
    assert L.stale_keys(snap, led) == []


# ── ٨) لا رمز داخلي يصل أي مخرج (قيد المالك) ───────────────────────────────

@pytest.mark.parametrize("blob_fn", [morocco_juice_research_blob,
                                     netherlands_research_blob])
def test_no_internal_token_survives_into_any_rendered_output(blob_fn):
    import silk_reports
    view = R.build_view(blob_fn())
    md = silk_reports.render_markdown(view)
    assert "{{" not in md
    assert "{{" not in json.dumps(view.get("deep_research") or {},
                                  ensure_ascii=False, default=str)


def test_unbound_token_is_blocking_even_in_measurement_mode():
    view = _morocco_view()
    with _env(**{L.ENFORCE_FLAG: None}):
        out = L.check(view, "التعرفة {{tariff_applied_pct}} باقية.")
    names = [f["check"] for f in out]
    assert "ledger_token_unbound" in names
    unbound = next(f for f in out if f["check"] == "ledger_token_unbound")
    assert unbound["repairable"] is False


# ── ٩) الحجب باتجاهين (التعديل ٧) ──────────────────────────────────────────

_MISMATCH = "بلغت الرسوم الجمركية المطبَّقة 60% وفق المصدر."


def test_measurement_mode_reports_but_does_not_block():
    view = _morocco_view()
    with _env(**{L.ENFORCE_FLAG: None}):
        out = L.check(view, _MISMATCH)
    hit = [f for f in out if f["check"] == "ledger_value_mismatch"]
    assert hit, out
    assert all(f["repairable"] for f in hit)


def test_enforcement_mode_blocks_the_same_text():
    view = _morocco_view()
    with _env(**{L.ENFORCE_FLAG: "1"}):
        out = L.check(view, _MISMATCH)
    hit = [f for f in out if f["check"] == "ledger_value_mismatch"]
    assert hit and all(not f["repairable"] for f in hit)


# ── ١٠) الإصلاح: الجملة كاملة لا الرقم وحده (التعديل ٨) ────────────────────

def test_repair_rewrites_the_whole_sentence_with_agreement():
    view = _morocco_view()
    led = view["ledger"]
    n = led["entries"]["open_conditions"]["value"]
    text = "يبقى في التقرير شرطان مفتوحان قبل القرار."
    fixed, repairs = L.repair(text, led)
    if n != 2:
        assert repairs and repairs[0]["kind"] == "open_conditions_count"
        assert re.search(r"\d\s*شروط", fixed) is None, fixed
        assert L.render_sentence(led["entries"]["open_conditions"]) in fixed


def test_repair_replaces_a_false_absence_with_the_ledger_sentence():
    led = _ledger_with("tariff_applied_pct", 25.0, source="WITS")
    fixed, repairs = L.repair("الرسوم الجمركية غير متاحة لهذا السوق.", led)
    assert repairs and repairs[0]["kind"] == "status"
    assert "غير متاح" not in fixed and "25%" in fixed


# ── ١١) سقف التنقيح معلن وسلوكه واضح (الشرط ٣) ─────────────────────────────

def test_revision_cap_is_bounded_and_declared():
    with _env(**{L.MAX_REVISIONS_FLAG: None}):
        assert L.max_revisions() == 1
    with _env(**{L.MAX_REVISIONS_FLAG: "5"}):
        assert L.max_revisions() == 2
    with _env(**{L.MAX_REVISIONS_FLAG: "0"}):
        assert L.max_revisions() == 0


# ── ١٢) السجلّ يعمل على مسار /analyze أيضاً (لا إصلاح على مسار واحد) ───────

def test_ledger_is_built_for_analyze_results_too():
    sample = os.path.join(_ROOT, "samples", "analysis_latest.json")
    if not os.path.exists(sample):
        pytest.skip("العيّنة غير موجودة")
    with open(sample, encoding="utf-8") as fh:
        view = json.load(fh)["view"]
    led = L.build_ledger({"markets": view.get("markets") or []})
    assert led["entries"]["open_conditions"]["value"] is not None
    assert led["entries"]["import_cagr_pct"]["status"] != L.MISSING


# ── ١٣) الحارسُ لا يُطلِق على الصحيح (عائلة الدرس ٢٣٩) ─────────────────────

def _canonical_keys():
    from tools import gen_verdict_baseline as B
    return sorted(B.CANONICAL_BLOBS)


def _canonical_view(key):
    import importlib
    from tools import gen_verdict_baseline as B
    mod, fn = B.CANONICAL_BLOBS[key]
    return R.build_view(getattr(importlib.import_module(mod), fn)())


@pytest.mark.parametrize("key", _canonical_keys())
def test_no_false_alarm_on_any_frozen_codex(key):
    """المدوّناتُ الستّ عشرة تقاريرُ **صحيحة**؛ فحصُ السجلّ يصمت عليها.

    قِيست ثلاثُ عائلاتِ إنذارٍ كاذبٍ وأُسقطت قبل الشحن: عتبةُ مسردٍ
    («فوق 2500 يعني سوقاً مركّزاً») تُقرأ تركّزَ السوق، ورقمُ مفهومٍ مجاورٍ
    («حصة السعودية … مقابل نمو السوق 9.3%») يُنسَب للحصة، وسنةُ رصدٍ
    («دخل الفرد لليمن (2018)») تُقرأ قيمةً.
    """
    import silk_reports
    view = _canonical_view(key)
    assert L.check(view, silk_reports.render_markdown(view)) == []


def test_glossary_threshold_is_not_read_as_a_reading():
    led = _ledger_with("hhi", 940.0)
    text = "HHI (مؤشر يقيس تركّز السوق — فوق 2500 يعني سوقاً مركّزاً)."
    assert L.check({"ledger": led}, text) == []


def test_a_neighbouring_metric_number_is_not_attributed_to_the_label():
    led = _ledger_with("saudi_share_pct", 1.5)
    text = "حصة السعودية المنخفضة مقابل نمو السوق 9.3% تدعو للحذر."
    assert L.check({"ledger": led}, text) == []


def test_an_observation_year_is_not_read_as_a_value():
    led = _ledger_with("per_capita_income_usd", 1200.0, source="World Bank")
    assert L.check({"ledger": led}, "دخل الفرد لليمن (2018)") == []


def test_a_real_value_contradiction_still_fires():
    """التضييقُ لم يُخمِد الحارس: مخالفةٌ حقيقيةٌ بجوار التسمية تُلتقَط."""
    led = _ledger_with("hhi", 940.0)
    out = L.check({"ledger": led}, "مؤشر التركّز 3800 في هذا السوق.")
    assert [f["check"] for f in out] == ["ledger_value_mismatch"]


# ── ١٤) حصادُ المراجعة الذاتية (§58) — سبعُ ملاحظاتٍ مقفولة ────────────────

def test_a_missing_value_replaces_its_sentence_not_the_paragraph():
    """المراجعة #1: كان السطرُ كلُّه يُستبدَل فتُبتَر فقرةٌ كاملة."""
    led = _ledger_with("tariff_applied_pct", None, note="لا تعرفة")
    line = ("السوق واعد. الرسوم الجمركية {{tariff_applied_pct}}. "
            "والخطوة التالية اعتماد المصنع.")
    out, _ = L.bind(line, led)
    assert out.startswith("السوق واعد.")
    assert "والخطوة التالية اعتماد المصنع." in out
    assert "الرسوم الجمركية المطبَّقة غير متاح." in out


def test_a_table_row_keeps_its_columns():
    """المراجعة #1ب: صفُّ جدولٍ كان يُستبدَل بجملةٍ فينكسر الجدول."""
    led = _ledger_with("tariff_applied_pct", None, note="لا تعرفة")
    out, _ = L.bind("| التعرفة | {{tariff_applied_pct}} | WITS |", led)
    assert out.count("|") == 4 and out.startswith("| التعرفة |")


def test_mandatory_branch_does_not_reject_a_year_or_a_neighbour_number():
    """المراجعة #2: الفرعُ الإلزاميّ كان يرفض أيّ رقمٍ قريب فيحرق نداءً."""
    led = L.build_ledger(morocco_juice_research_blob())
    good = ("الرسوم الجمركية المطبَّقة {{tariff_applied_pct}} وفق مسحٍ "
            "منشورٍ عام 2024.")
    assert L.draft_issues(good, led) == []


def test_repair_fixes_the_offending_sentence_only():
    """المراجعة #3: المواضعُ المُطبَّعة كانت تحذف الجملةَ الخطأ."""
    view = _morocco_view()
    led = view["ledger"]
    text = ("مقدّمةٌ فيها تشكيلٌ مُطبَّعٌ كالتعريفة المطبَّقة. "
            "تبقى ثلاثة شروط مفتوحة قبل القرار.")
    fixed, repairs = L.repair(text, led)
    assert fixed.startswith("مقدّمةٌ فيها تشكيلٌ")
    assert repairs and repairs[0]["kind"] == "open_conditions_count"


def test_no_blocking_condition_is_stated_as_a_decision_not_a_gap():
    """المراجعة #4: «لا شرط حاجب» قرارٌ محسوب لا فجوةٌ غيرُ مقيسة."""
    led = _ledger_with("blocking_condition", None, note="لا شرط حاجب")
    out, _ = L.bind("{{blocking_condition}}", led)
    assert out == "لا شرط حاجب"


def test_analyze_path_can_actually_block(tmp_path):
    """المراجعة #5: المسارُ بلا بحثٍ عميق كان يُثبِّت PASS فلا يحجب أبداً."""
    import silk_quality_gate as QG
    import silk_reports
    view = {"ledger": {"entries": {}, "gaps": []}, "markets": [],
            "product": "تمور", "report_language": "ar"}
    orig = silk_reports.render_markdown
    silk_reports.render_markdown = lambda v: "متنٌ فيه {{tariff_applied_pct}}"
    try:
        out = QG.run_quality_gate(view)
    finally:
        silk_reports.render_markdown = orig
    assert out["verdict"] == QG.FAIL
    assert "ledger_token_unbound" in [f["check"] for f in out["findings"]]


def test_unbound_token_is_caught_even_when_the_ledger_is_empty():
    """المراجعة #6: تعذّرُ بناء السجلّ هو نفسُه حالةُ تخطّي الملء."""
    assert [f["check"] for f in L.check({"ledger": {}}, "بقي {{hhi}} هنا")] \
        == ["ledger_token_unbound"]


def test_the_ledger_gate_is_re_read_after_the_review_loop():
    """المراجعة #7: كانت `ledger_unresolved` تصف مسوّدةً لم تُسلَّم — تنقيحُ
    المراجع يُعيد كتابة النصّ **بعدها**. القفلُ بنيويّ على ترتيب الشيفرة."""
    import inspect
    import silk_ai_judge
    body = inspect.getsource(silk_ai_judge.write_reviewed_report)
    loop = body.index("for cycles in range(")
    reread = body.index("_ledger_unresolved = _ledger_draft_issues(draft, ledger)",
                        loop)
    assert reread > loop, "قراءةُ بوّابة السجلّ تسبق حلقةَ المراجع"
