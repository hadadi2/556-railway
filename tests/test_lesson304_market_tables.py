"""الدرس ٣٠٤ (PR-C، قرار المالك): جداولُ الضريبة وسعر الصرف وقواعد المنشأ — حتمية، لكلّ صفٍّ مصدرٌ
رسميّ، والغائبُ فجوةٌ معلنة لا رقمٌ مخمَّن. تُغذّي F2 (أرضية سعر الرف) وF4 (شرط المنشأ ونسبته) بدل
`meta.json` اليدويّ؛ ما يمرّره المستدعي صراحةً يعلو الجدول.

Lesson 304 locks: deterministic VAT / FX-peg / rules-of-origin tables. Written test-first.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools"), os.path.join(_ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def test_fiscal_rows_carry_an_official_source_and_gaps_stay_none():
    import silk_market_tables as T
    bhr = T.fiscal("BHR")
    assert bhr["currency"] == "BHD" and bhr["fx_local_per_usd"] == 0.376 and bhr["vat_pct"] == 10.0
    assert bhr["source_url"].startswith("https://") and bhr["fx_regime"] == "peg"
    assert T.fiscal("SAU")["vat_pct"] == 15.0 and T.fiscal("ARE")["fx_local_per_usd"] == 3.6725
    assert T.fiscal("QAT")["vat_pct"] == 0.0                 # لا ضريبة قيمة مضافة مطبَّقة
    kwt = T.fiscal("KWT")
    assert kwt["fx_regime"] == "basket" and kwt["fx_local_per_usd"] is None   # لا ربطَ ثابت = لا رقم
    assert T.fiscal("DEU") is None and T.fiscal("") is None   # خارج الجدول = فجوة لا تخمين


def test_every_table_row_cites_a_source():
    import csv
    for name in ("market_fiscal_l1.csv", "origin_rules_l1.csv"):
        rows = list(csv.DictReader(l for l in open(os.path.join(_ROOT, "data", name), encoding="utf-8")
                                   if not l.startswith("#")))
        assert rows and all(r["source_url"].startswith("https://") and r["source"] for r in rows), name


def test_origin_rule_for_a_saudi_exporter_follows_the_market_agreement():
    import silk_market_tables as T
    gcc = T.origin_rule("BHR")
    assert gcc["agreement"] == "GCC" and gcc["min_value_added_pct"] == 40.0
    assert "51" in gcc["other_conditions"]
    assert T.origin_rule("EGY")["agreement"] == "GAFTA" and T.origin_rule("EGY")["min_value_added_pct"] == 40.0
    assert T.origin_rule("DEU") is None


def test_study_meta_is_filled_from_the_tables_and_explicit_meta_wins():
    from test_lesson300_series_head import _bahrain_blob
    import silk_study_checks as C
    b = _bahrain_blob()
    b["deep_research"]["report"] = {"report": "## 1. الخلاصة\n\nنص.\n", "review_cycles": 1,
                                    "unresolved_notes": []}
    doc = C.StudyDoc.from_result(b)
    assert doc.meta["fx_local_per_usd"] == 0.376 and doc.meta["vat_pct"] == 10.0
    assert doc.meta["currency"] == "BHD" and doc.meta.get("fiscal_source")
    doc2 = C.StudyDoc.from_result(b, meta={"vat_pct": 5})
    assert doc2.meta["vat_pct"] == 5


def test_f4_fails_a_wrong_value_added_threshold_and_names_the_rule():
    import silk_study_checks as C
    text = ("## 7. التنظيم والوصول للسوق\n\nالرسوم الجمركية 0% على القهوة السعودية بشرط قاعدة "
            "المنشأ: قيمة مضافة محلية لا تقل عن 35%.\n")
    f = C.check_tariff_claims(C.StudyDoc(report=text, meta={"market_iso3": "BHR"}))
    assert f.status == C.FAIL and "40" in f.items[0]["why"] and "GCC" in f.items[0]["why"]
    ok = text.replace("35%", "40% وملكية خليجية لا تقل عن 51%")
    assert C.check_tariff_claims(C.StudyDoc(report=ok, meta={"market_iso3": "BHR"})).status == C.PASS
    missing = "## 7. التنظيم\n\nالرسوم الجمركية 0% على القهوة.\n"
    f2 = C.check_tariff_claims(C.StudyDoc(report=missing, meta={"market_iso3": "BHR"}))
    assert f2.status == C.FAIL and "40%" in f2.items[0]["why"]       # السببُ يسمّي القاعدة


def test_f2_floor_uses_the_table_without_manual_meta():
    import silk_study_checks as C
    from test_lesson300_series_head import _bahrain_blob
    b = _bahrain_blob()
    b["deep_research"]["report"] = {"report": "## 4. الأسعار\n\nنص.\n", "review_cycles": 1,
                                    "unresolved_notes": []}
    doc = C.StudyDoc.from_result(b)
    assert doc.meta["fx_local_per_usd"] and doc.meta["vat_pct"] is not None


# ── أقفال المراجعة الذاتية (§58) · self-review locks ──────────────────────────

def test_review_vat_percentage_is_not_read_as_value_added_threshold():
    import silk_study_checks as C
    p = "الرسوم الجمركية 0% بشرط قاعدة المنشأ وضريبة القيمة المضافة 10%."
    assert C._value_added_pct(p) is None


def test_review_zero_tariff_is_not_captured_as_threshold():
    import silk_study_checks as C
    p = "الرسوم الجمركية 0% بشرط قاعدة المنشأ."
    assert C._value_added_pct(p) is None


def test_review_definite_value_added_form_is_compared():
    import silk_study_checks as C
    text = ("## 7. التنظيم\n\nالرسوم الجمركية 0% بشرط قاعدة المنشأ: القيمة المضافة 35% "
            "وملكية خليجية 51%.\n")
    f = C.check_tariff_claims(C.StudyDoc(report=text, meta={"market_iso3": "BHR"}))
    assert f.status == C.FAIL and f.items[0]["kind"] == "threshold"


def test_review_omani_and_jordanian_currencies_are_local():
    import silk_study_checks as C
    assert C._is_local_currency("ريال عماني", "OMR") and C._is_local_currency("OMR", "OMR")
    assert C._is_local_currency("دينار أردني", "JOD")


def test_review_saudi_riyal_is_not_local_in_qatar():
    import silk_study_checks as C
    assert not C._is_local_currency("ريال سعودي", "QAR")
    assert C._is_local_currency("ريال قطري", "QAR")


def test_review_run_all_fills_fiscal_for_a_direct_studydoc():
    import silk_study_checks as C
    doc = C.StudyDoc(report="## 1. الخلاصة\n\nنص.\n", meta={"market_iso3": "BHR"})
    C.run_all(doc)
    assert doc.meta["vat_pct"] == 10.0 and doc.meta["fx_local_per_usd"] == 0.376


def test_review_gcc_exemption_without_ownership_warns_not_fails():
    import silk_study_checks as C
    text = "## 7. التنظيم\n\nالرسوم الجمركية 0% بشرط قاعدة المنشأ وقيمة مضافة لا تقل عن 40%.\n"
    f = C.check_tariff_claims(C.StudyDoc(report=text, meta={"market_iso3": "BHR"}))
    assert f.status == C.WARN and f.items[0]["kind"] == "ownership"


def test_review_rule_without_threshold_does_not_crash(monkeypatch):
    import silk_study_checks as C
    import silk_market_tables as T
    monkeypatch.setattr(T, "origin_rule", lambda iso: {"agreement": "X", "min_value_added_pct": None,
                                                       "other_conditions": "", "source": "s"})
    text = "## 7. التنظيم\n\nالرسوم الجمركية 0% على القهوة.\n"
    f = C.check_tariff_claims(C.StudyDoc(report=text, meta={"market_iso3": "BHR"}))
    assert f.status == C.FAIL and "قاعدة منشأ X" in f.items[0]["why"]
