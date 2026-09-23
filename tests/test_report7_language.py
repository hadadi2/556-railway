"""تقرير سِلك ٧ — موجة لغة العميل (§5، الدرس ٢٧٤).

client-language wave: code-generated templates that reach the client speak
the reader's language — no generation-method headings («محسوبة حتمياً» on
rows that may be uncomputed), no personal «we don't know yet», no internal
terms («سبيل الإغلاق»، «الشرط الحاجب»), and no claim of a verification that
did not happen («تحقّقنا منه مباشرة»).
"""
import pathlib

import silk_i18n as I

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_BANNED_CLIENT = ("محسوبة حتمياً", "لا نعرفه بعد", "سبيل الإغلاق",
                  "الشرط الحاجب", "تحقّقنا منه مباشرة", "تحقّقنا مباشرة")


def _src(name: str) -> str:
    return (_ROOT / name).read_text(encoding="utf-8")


def test_the_financial_table_heading_describes_content_not_method():
    src = _src("silk_reports.py")
    assert "المؤشرات المالية ومدخلاتها" in src
    assert "محسوبة حتمياً" not in src


def test_uncomputed_rows_say_what_the_calculation_requires():
    src = _src("silk_reports.py")
    assert "يتطلب الحساب: " in src and "الإجراء المطلوب: " in src
    assert "لا نعرفه بعد — يلزم" not in src and "سبيل الإغلاق" not in src


def test_i18n_client_keys_carry_no_internal_or_personal_terms():
    for key in ("pillar_not_computed", "pillar_measured",
                "decision_weighted_line", "cond_pillar_missing"):
        txt = I.t(key, "ar", score="70", conf="60", pillar="الطلب",
                  parts="السعر")
        assert not any(b in txt for b in _BANNED_CLIENT), (key, txt)
    en = I.t("pillar_measured", "en")
    assert "verified" not in en.lower(), "لا ادّعاءَ تحقّقٍ لم يجرِ"


def test_the_prerequisite_label_replaces_the_internal_term_everywhere():
    import silk_fact_ledger as FL
    row = next(r for r in FL.KEYS if r.key == "blocking_condition")
    assert row.label_ar == "المتطلب السابق للتعاقد أو الشحن"
    # المصطلحُ القديم يبقى كلمةَ تعرّف — النصوصُ المحفوظة قبل التغيير.
    assert "الشرط الحاجب" in row.words
    for name in ("silk_ai_judge.py", "silk_style_contract.py"):
        assert "ثم الشرط الحاجب" not in _src(name), name


def test_the_drift_check_reads_both_labels_and_ignores_label_words():
    """كلماتُ التسمية نفسِها («الشحن») لا تُرضي الإبرة — المقارنةُ بعد التسمية."""
    import silk_fact_ledger as FL
    view = {"ledger": {"entries": {"blocking_condition": {
        "key": "blocking_condition", "status": "observed",
        "value": "جانب مسار الشحن غائب (غير متاح: تكلفة الشحن)"}}}}
    for label in ("المتطلب السابق للتعاقد أو الشحن", "الشرط الحاجب"):
        hits = FL.check(view, f"{label}: شهادة حلال من الهيئة.")
        assert any(h.get("check") == "blocking_condition_drift"
                   for h in hits), (label, hits)
        ok = FL.check(view, f"{label}: جانب مسار الشحن غائب.")
        assert not any(h.get("check") == "blocking_condition_drift"
                       for h in ok), label


def test_no_internal_term_survives_in_any_client_rendering():
    import silk_fact_ledger as FL
    empty = {"key": "blocking_condition", "value": None, "status": "missing"}
    for lang in ("ar", "en"):
        v = FL.render_value(empty, lang)
        assert "حاجب" not in v and "blocking" not in v.lower(), v
    for key in ("decision_rule_lead", "decision_rule_lead_empty",
                "coverage_intro", "coverage_primary"):
        for lang in ("ar", "en"):
            txt = I.t(key, lang, go="70", nogo="40", conf="60", total="10",
                      pct="50")
            assert "تحقّق" not in txt and "verified" not in txt.lower(), \
                (key, lang, txt)
    assert "blocking condition" not in _src("silk_style_contract.py")
