"""محرك قوالب الدراسة (P0-T) — الاختبارات الثلاثة الحاكمة + قواعد العربية + الحراسة.

1. المطابقة الحرفية لحالة ماليزيا بملف معرفتها المعتمد (بعد تطبيع المسافات فقط).
2. حالة تركيبية: سلسلة هابطة + مؤشر تركّز مركّز + قرار إرجاء → تُصيَّر بالنسخ الصحيحة.
3. حالة بلا ملف معرفة → النص الحتمي ≥ 70% من الأحرف.
+ اتجاهات معكوسة (قيمة صاعدة/سعر هابط)، حدّا HHI (1,300 تُرفض)، حروف الجر، العدد
والمعدود، لا فعل اتجاه صلب خارج {dir:…}، بوابة النسخ pending، رفض العناصر النائبة.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIX = os.path.join(_ROOT, "evals", "golden_set", "malaysia_coffee_fixture.json")
_REF = os.path.join(_ROOT, "samples", "golden_malaysia_coffee_study.md")


def _case():
    with open(_FIX, encoding="utf-8") as f:
        return json.load(f)


def _norm(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s.replace("\r\n", "\n")).strip()


def _first_diff(a: str, b: str) -> str:
    la, lb = a.splitlines(), b.splitlines()
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return f"سطر {i + 1}:\n  المرجع: {x[:160]}\n  الناتج: {y[:160]}"
    return f"طول مختلف: {len(la)} مقابل {len(lb)}"


# ── ١) المطابقة الحرفية ──────────────────────────────────────────────────
def test_malaysia_renders_verbatim_from_fixture_and_approved_knowledge():
    from silk_study_render import load_knowledge, render_study
    out = render_study(_case(), load_knowledge("090121", "MY"))
    with open(_REF, encoding="utf-8") as f:
        ref = f.read()
    assert _norm(out) == _norm(ref), _first_diff(_norm(ref), _norm(out))


# ── ٢) الحالة التركيبية ─────────────────────────────────────────────────
def _synthetic_down_concentrated_defer():
    c = _case()
    c["imports"]["series"] = [
        {"year": 2019, "value_musd": 90.0, "kg": 13000000, "complete": True},
        {"year": 2020, "value_musd": 84.0, "kg": 12300000, "complete": True},
        {"year": 2021, "value_musd": 70.0, "kg": 10500000, "complete": True},
        {"year": 2022, "value_musd": 66.0, "kg": 10000000, "complete": True},
        {"year": 2023, "value_musd": 60.0, "kg": 9200000, "complete": True},
        {"year": 2024, "value_musd": 55.0, "kg": 8600000, "complete": True},
    ]
    c["imports"]["last_yoy_pct"] = -8
    c["imports"]["unit_value_first"] = 6.9
    c["imports"]["unit_value_last_reliable"] = 6.4
    c["imports"]["unit_value_year_excluded"] = None
    c["suppliers"]["top"] = [
        {"iso3": "BRA", "name_ar": "البرازيل", "share_pct": 52, "kind": "producer"},
        {"iso3": "COL", "name_ar": "كولومبيا", "share_pct": 18, "kind": "producer"},
        {"iso3": "ITA", "name_ar": "إيطاليا", "share_pct": 9, "kind": "roaster"},
        {"iso3": "DEU", "name_ar": "ألمانيا", "share_pct": 6, "kind": "roaster"},
    ]
    c["suppliers"]["hub_share_trend"] = None
    c["decision"]["type"] = "defer"
    return c


def test_synthetic_down_concentrated_defer_uses_the_right_variants():
    from silk_study_numbers import compute
    from silk_study_render import Renderer
    c = _synthetic_down_concentrated_defer()
    n = compute(c)
    assert n["shape_trend"] == "down" and n["hhi_band"] == "above_2500" and n["market_def"] == "defer"
    assert n["dec_variant"] == "decomposable_down"
    assert not n["top3_near"]                      # البرازيل/كولومبيا/إيطاليا بعيدة عن كوالالمبور
    out = Renderer(c, {}, allow_pending=True).render()
    assert "سوقاً معتبرة الحجم للقهوة المحمصة، غير أن مؤشراتها لا تكفي لقرار دخول في الوقت الراهن" in out
    assert "غير أنها ليست سوقاً سهلة الدخول" not in out          # ease تُحذف مع defer
    assert "بتراجع يقارب 39% عن عام 2019" in out
    assert "مع هيمنة واضحة للبرازيل" in out                       # top1 ≥ 40%
    assert "وتستحوذ ثلاث دول على" in out and "قريبة جغرافياً" not in out
    assert "يتجاوز العتبة التي تُصنَّف عندها السوق شديدة التركّز (2,500 نقطة)" in out
    assert "انتزاع حصة من أحدهم أو على استهداف شريحة لا يخدمونها" in out
    assert "من الموردين الرئيسيين" not in out                    # above_2500 لا يذكر origin_word
    assert "تراجعت القيمة بنسبة 39%" in out and "تفسّر نحو" in out
    assert "تراجع الطلب بلغ 8% في عام واحد" in out               # last_yoy = −8% → dir:last + قيمة مطلقة
    assert "توصي الدراسة بـ**إرجاء**" in out
    assert "واعدة" not in out


# ── ٣) بلا ملف معرفة ─────────────────────────────────────────────────────
def test_without_knowledge_deterministic_text_is_at_least_70_percent():
    from silk_study_render import LLM_MARK, Renderer
    marks = []

    def fake_llm(sid, brief):
        marks.append(sid)
        return "جملة نموذج مؤقتة للمراجعة."
    r = Renderer(_case(), {}, llm_fill=fake_llm, review_marks=True)
    out = r.render()
    assert marks and all(LLM_MARK.format(sid=s) in out for s in marks)
    llm_chars = len("جملة نموذج مؤقتة للمراجعة.") * len(marks)
    body = re.sub(r"<!-- llm:[^>]*-->", "", out)
    assert (len(body) - llm_chars) / len(body) >= 0.70


def test_llm_slot_is_retried_once_then_dropped_as_gap():
    """P1-12: نموذج يعيد نائباً دائماً → نداءان لكل فراغ ثم فجوة معلنة بلا نص."""
    from silk_study_render import Renderer
    calls = []

    def bad_llm(sid, brief):
        calls.append(sid)
        return "[يُدرج لاحقاً]"
    r = Renderer(_case(), {}, llm_fill=bad_llm)
    out = r.render()
    per_slot = {s: calls.count(s) for s in set(calls)}
    assert per_slot and all(n == 2 for n in per_slot.values()), per_slot
    assert "[يُدرج" not in out and r.gaps and "s2_survey" in r.gaps


def test_llm_slot_with_unpassed_number_is_rejected():
    from silk_study_render import Renderer
    r = Renderer(_case(), {}, llm_fill=lambda sid, brief: "تبلغ الحصة 37% وفق تقديرنا.")
    out = r.render()
    assert "37%" not in out and r.gaps


def test_missing_knowledge_without_llm_declares_gap_not_text():
    from silk_study_render import Renderer
    r = Renderer(_case(), {})
    out = r.render()
    assert r.gaps and "s2_survey" in r.gaps
    assert "الكوبي" not in out


# ── الاتجاهات المعكوسة (P1-7 / تعديل المالك أ-٢) ───────────────────────────
def test_value_up_price_down_variant_and_no_share_sentence():
    from silk_study_numbers import decomposition
    ser = [
        {"year": 2020, "value_musd": 50.0, "kg": 5000000},
        {"year": 2021, "value_musd": 55.0, "kg": 6100000},
        {"year": 2022, "value_musd": 60.0, "kg": 7200000},
        {"year": 2023, "value_musd": 65.0, "kg": 8400000},
    ]
    d = decomposition(ser)
    assert d["variant"] == "value_up_price_down" and d["dv"] > 0 and d["dp"] < 0
    c = _case()
    c["imports"]["series"] = [dict(r, complete=True) for r in ser]
    c["imports"]["unit_value_first"], c["imports"]["unit_value_last_reliable"] = 10.0, 7.7
    c["imports"]["unit_value_year_excluded"] = None
    from silk_study_render import Renderer
    out = Renderer(c, {}, allow_pending=True).render()
    assert "ارتفعت القيمة بنسبة 30% بينما تراجع متوسط سعر الكيلوغرام" in out
    assert "تفسّر نحو" not in out.split("## أولاً")[1].split("| السنة")[0]
    assert "تراجعاً في أسعار البن عالمياً" in out


def test_value_down_price_up_variant():
    from silk_study_numbers import decomposition
    d = decomposition([{"year": 2020, "value_musd": 80.0, "kg": 10000000},
                       {"year": 2021, "value_musd": 72.0, "kg": 8000000},
                       {"year": 2022, "value_musd": 64.0, "kg": 6500000}])
    assert d["variant"] == "value_down_price_up"


# ── مؤشر التركّز (P1-9) ───────────────────────────────────────────────────
def test_hhi_bounds_reference_shares_reject_1300_accept_900_1200():
    from silk_study_numbers import hhi_bounds, hhi_consistent
    lo, hi = hhi_bounds([19, 16, 14, 8])
    assert lo == 877 and hi == 1206
    assert hhi_consistent(900, [19, 16, 14, 8]) and hhi_consistent(1200, [19, 16, 14, 8])
    assert not hhi_consistent(1300, [19, 16, 14, 8])
    # حدّية: الباقي أصغر من أصغر حصة
    lo2, hi2 = hhi_bounds([60, 35])
    assert lo2 == 60 * 60 + 35 * 35 and hi2 == lo2 + 25


def test_hhi_band_boundaries():
    from silk_study_numbers import hhi_band
    assert hhi_band(900, 1200) == "below_1500"
    assert hhi_band(1400, 1600) == "straddles_1500"
    assert hhi_band(1600, 2400) == "between_1500_2500"
    assert hhi_band(2400, 2600) == "straddles_2500"
    assert hhi_band(2600, 3000) == "above_2500"


# ── قواعد العربية (§ج) ─────────────────────────────────────────────────────
def test_prep_merges_definite_article():
    from silk_study_arabic import prep
    assert prep("ل", "القهوة المحمصة") == "للقهوة المحمصة"
    assert prep("ب", "الدولار") == "بالدولار"
    assert prep("ك", "المرجع") == "كالمرجع"
    assert prep("ل", "تمور") == "لتمور"
    assert prep("ل", "Shopee") == "لـShopee"


def test_exec_summary_line_uses_prep_on_product_short():
    from silk_study_render import load_knowledge, render_study
    out = render_study(_case(), load_knowledge("090121", "MY"))
    assert "سوقاً واعدة للقهوة المحمصة" in out


@pytest.mark.parametrize("n,spec,case,expected", [
    (1, "دولة مورّدة", "nom", "دولة مورّدة واحدة"),
    (2, "دولة مورّدة", "nom", "دولتان مورّدتان"),
    (2, "دولة مورّدة", "gen", "دولتين مورّدتين"),
    (5, "دولة مورّدة", "nom", "خمس دول مورّدة"),
    (11, "دولة مورّدة", "gen", "11 دولة مورّدة"),
    (48, "دولة مورّدة", "gen", "48 دولة مورّدة"),
    (100, "دولة مورّدة", "gen", "100 دولة مورّدة"),
    (3, "مورّد", "nom", "ثلاثة موردين"),
    (2, "مورّد", "nom", "مورّدان"),
    (15, "مورّد", "nom", "15 مورّداً"),
    (4, "سنة", "gen", "أربع سنوات"),
    (6, "شهر", "gen", "ستة أشهر"),
    (4, "متطلب", "gen", "أربعة متطلبات"),
])
def test_count_number_and_counted(n, spec, case, expected):
    from silk_study_arabic import count
    assert count(n, spec, case) == expected


def test_number_formats():
    from silk_study_arabic import fmt, fraction_word
    assert fmt(89.4, "m1") == "89.4 مليون دولار" and fmt(1500, "int") == "1,500"
    assert fmt(19.4, "pct0") == "19%" and fmt(9, "month") == "سبتمبر"
    assert fraction_word(24 / 43) == "ثلاثة أخماس" and fraction_word(0.24, True) == "الربع"
    assert fraction_word(0.49) == "نصف" and fraction_word(0.16) == "سدس" and fraction_word(0.33) == "ثلث"


# ── الحراسة ────────────────────────────────────────────────────────────────
_DIR_VERBS = re.compile(r"(?<![{|:])\b(ارتفعت|تراجعت|ارتفع|تراجع|نمت|انكمشت|زادت|انخفضت)\b(?![|}])")


def test_no_hardcoded_direction_verb_outside_dir_slot_in_sign_dependent_templates():
    """الأفعال المرتبطة بإشارة رقم متغيّر تكون داخل {dir:…}. تُستثنى النسخ التي تحمل
    الإشارة في شرطها نفسه (value_up_price_down/…down/…) لأن اتجاهها ثابت بالتعريف."""
    import yaml
    with open(os.path.join(_ROOT, "data", "study_templates_ar.yaml"), encoding="utf-8") as f:
        t = yaml.safe_load(f)
    fixed_sign = {"value_up_price_down", "value_down_price_up", "decomposable_down"}
    texts = []
    for name, cl in t["clauses"].items():
        for k, v in cl["variants"].items():
            texts.append((f"{name}.{k}", v or ""))
    for b in t["blocks"]:
        if b.get("variants"):
            for k, v in b["variants"].items():
                if k not in fixed_sign:
                    texts.append((k, v or ""))
    offenders = []
    for name, txt in texts:
        stripped = re.sub(r"\{dir:[^}]*\}", "", txt)
        # الحالات الثابتة بالتعريف في المرجع (السلسلة الصاعدة المتذبذبة: «ارتفاعاً ملحوظاً…الصعود» اسمان لا فعلان)
        if _DIR_VERBS.search(stripped):
            offenders.append(name)
    assert not offenders, offenders


def test_pending_variant_is_skipped_as_a_gap_unless_explicitly_allowed(monkeypatch, tmp_path):
    """نسخة pending لا تصل العميل: الفقرة تسقط ويُعلن في الحدود أنها بانتظار الاعتماد.
    ملف مراجعة مؤقت يحمل نسخة exec_2.defer بحالة pending — لا اعتماد على حالة الملف الحقيقي."""
    import silk_study_render as SR
    import yaml
    with open(os.path.join(_ROOT, "data", "study_templates_ar.yaml"), encoding="utf-8") as f:
        t = yaml.safe_load(f)
    defer_txt = next(b["text"] for b in t["blocks"] if b.get("when") == "decision == defer")
    review = tmp_path / "review.md"
    review.write_text("| القالب | المفتاح | النص | الحالة |\n|---|---|---|---|\n"
                      f"| exec_2 | defer | {defer_txt} | pending |\n", encoding="utf-8")
    monkeypatch.setattr(SR, "REVIEW_FILE", str(review))
    c = _synthetic_down_concentrated_defer()
    out = SR.Renderer(c, {}).render()
    assert "توصي الدراسة بـ**إرجاء**" not in out
    assert "فقرة قالبها بانتظار اعتماد المالك" in out
    assert "توصي الدراسة بـ**إرجاء**" in SR.Renderer(c, {}, allow_pending=True).render()


def test_placeholder_leak_is_refused():
    from silk_study_render import Renderer, StudyRenderError
    c = _case()
    c["entities"]["rows"][0]["desc"] = "[يُدرج لاحقاً]"
    with pytest.raises(StudyRenderError):
        Renderer(c, {}).render()


def test_draft_knowledge_is_not_used():
    from silk_study_render import load_knowledge
    import yaml
    p = os.path.join(_ROOT, "data", "product_knowledge", "999999_ZZ.yaml")
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump({"status": "draft", "paragraphs": {"s2_survey": "x"}}, f, allow_unicode=True)
    try:
        assert load_knowledge("999999", "ZZ") == {}
    finally:
        os.remove(p)


def test_every_yaml_variant_text_is_reference_or_registered_in_review_file():
    """كل نسخة لم ترد حرفياً في المرجع لها صف في ملف المراجعة (approved أو pending)."""
    import yaml
    with open(os.path.join(_ROOT, "data", "study_templates_ar.yaml"), encoding="utf-8") as f:
        t = yaml.safe_load(f)
    with open(_REF, encoding="utf-8") as f:
        ref = f.read()
    with open(os.path.join(_ROOT, "docs", "plans", "STUDY_TEMPLATE_VARIANTS_REVIEW.md"), encoding="utf-8") as f:
        review = f.read().replace("\\|", "|")
    missing = []
    for name, cl in t["clauses"].items():
        for k, v in cl["variants"].items():
            if not v:
                continue
            v = v.strip()
            probe = v.split("{")[0].rsplit(" ", 1)[0] if "{" in v else v
            if len(probe.strip()) < 6:
                continue          # فراغ في أول الجملة — لا مسبار نصي كافٍ
            if v not in review and probe.strip() not in ref and probe.strip() not in review:
                missing.append(f"{name}.{k}")
    assert not missing, missing
