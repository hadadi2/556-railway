"""اختبار المجموعة الذهبية — golden set locks (المرحلة 0.5، توجيه المنصّة).

هرمتي بالكامل: المدوّنات القانونية المجمَّدة + build_view، بلا شبكة.
يثبت: (١) خط الأساس الملتزَم مطابق للتوليد الحالي، (٢) تغيّر الحكم يُلتقط
حاجباً، (٣) رقم غير مسنود جديد في التقرير يُلتقط حاجباً، (٤) البصمة تحمل
المؤشرات **الستة** كاملة، (٥) **كل مؤشر** له اختبار عبثٍ مقصود يثبت أنه
يكشف التغيّر لا أنه صامتٌ فحسب (طلب المالك 2026-08-19).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import golden_set as G  # noqa: E402

_INDICATORS = ("verdict", "confidence", "key_figures", "section_count",
               "unsupported_report_numbers", "verification_items")


def test_every_indicator_has_a_deliberate_mutation_test():
    """طلب المالك (٤): كل مؤشر يُثبَت أنه **يكشف** التغيّر — لا مؤشر بلا
    عبثٍ مقصود. غياب اختبار لمؤشر = إنذار كاذب بالسلامة."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "test_golden_set.py"), encoding="utf-8").read()
    for ind in _INDICATORS:
        assert f"# mutates:{ind}" in src, (
            f"المؤشر {ind} بلا اختبار عبثٍ مقصود — لا يُعرَف أنه يكشف شيئاً")


def test_confidence_mutation_is_detected():
    # mutates:confidence
    key = "netherlands_dates"
    base = G.snapshot(key)
    mutated = json.loads(json.dumps(base))
    mutated["confidence"] = (base["confidence"] or 0) + 0.25
    diffs = G.compare_case(key, base, mutated)
    assert any("confidence changed" in d for d in diffs)


def test_every_key_figure_mutation_is_detected():
    # mutates:key_figures
    key = "netherlands_dates"
    base = G.snapshot(key)
    figs = base.get("key_figures") or {}
    assert figs, "لا أرقام مفتاحية في البصمة — المؤشر أجوف"
    for name in figs:
        mutated = json.loads(json.dumps(base))
        cur = mutated["key_figures"][name]
        mutated["key_figures"][name] = (
            (cur + 1) if isinstance(cur, (int, float)) and not isinstance(cur, bool)
            else f"{cur}-mutated")
        diffs = G.compare_case(key, base, mutated)
        assert any(f"key_figure {name}" in d for d in diffs), (
            f"تغيّر {name} لم يُكتشَف")


def test_verification_items_regression_is_blocking():
    # mutates:verification_items
    key = "kuwait_peanut_butter"
    base = G.snapshot(key)
    assert (base["verification_items"]["count"] or 0) > 0
    # (أ) اختفاء البنود كلياً = انحدار قناة الفجوات
    dropped = json.loads(json.dumps(base))
    dropped["verification_items"]["count"] = 0
    assert any(d.startswith("BLOCKING") and "dropped" in d
               for d in G.compare_case(key, base, dropped))
    # (ب) ادّعاء «لا شيء» مع وجود بنود = حادثة الحليب–الأردن نفسها
    lying = json.loads(json.dumps(base))
    lying["verification_items"]["claims_none"] = True
    assert any(d.startswith("BLOCKING") and "لا شيء" in d
               for d in G.compare_case(key, base, lying))


def test_all_five_baselines_exist_and_carry_every_indicator():
    assert len(G.GOLDEN_CASES) == 5
    for key in G.GOLDEN_CASES:
        path = os.path.join(G.BASELINE_DIR, f"{key}.json")
        assert os.path.exists(path), f"خط أساس مفقود: {key} — شغّل tools/golden_set.py archive"
        with open(path, encoding="utf-8") as f:
            snap = json.load(f)
        for ind in _INDICATORS:
            assert ind in snap, f"{key}: مؤشر {ind} مفقود من خط الأساس"


def test_current_generation_matches_committed_baselines():
    """المقارنة الكاملة خضراء — أي فرق حاجب هنا يعني أن تغييراً حرّك حكماً
    أو أدخل رقماً غير مسنود، ويجب تفسيره قبل المتابعة (تعديل مالك ١)."""
    assert G.compare() == 0


def test_verdict_change_is_blocking():
    # mutates:verdict
    key = "netherlands_dates"
    base = G.snapshot(key)
    mutated = json.loads(json.dumps(base))
    mutated["verdict"] = "GO — مغاير"
    diffs = G.compare_case(key, base, mutated)
    assert any(d.startswith("BLOCKING") and "verdict" in d for d in diffs)


def test_new_unsupported_number_is_blocking():
    # mutates:unsupported_report_numbers
    key = "netherlands_dates"
    base = G.snapshot(key)
    mutated = json.loads(json.dumps(base))
    mutated["unsupported_report_numbers"] = list(base["unsupported_report_numbers"]) + [98765.0]
    diffs = G.compare_case(key, base, mutated)
    assert any(d.startswith("BLOCKING") and "unsupported" in d for d in diffs)


def test_non_blocking_drift_does_not_block():
    # mutates:section_count
    key = "netherlands_dates"
    base = G.snapshot(key)
    mutated = json.loads(json.dumps(base))
    mutated["section_count"] = base["section_count"] + 1
    diffs = G.compare_case(key, base, mutated)
    assert diffs and not any(d.startswith("BLOCKING") for d in diffs)
