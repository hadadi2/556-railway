"""Regression locks for the owner's report/image/dialog incident (2026-09-09)."""
import pytest


def test_writer_receives_the_same_missing_components_as_the_decision_panel():
    import silk_ai_judge as writer
    import silk_deep_pillars as pillars
    decision = {"verdict": "wait", "confidence": 0.5, "score": 0.4,
                "why": "لا تتوفر قياسات كافية",
                "pillars": {"risk": {"missing": ["fx_stability"]}}}
    verdict = pillars.promote_engine_verdict({"verdict": "wait"}, decision)
    summary = writer._summarize_verdict(verdict, [])
    assert "استقرار العملة" in summary
    assert decision["why"] in summary


def test_pillar_refusal_has_a_specific_recovery_message():
    import silk_export_gate as gate
    for lang in ("ar", "en"):
        assert gate.client_reason("pillar_narrative_sync", lang) != gate._GENERIC_REASON[lang]


@pytest.mark.parametrize("text", [
    "## حجم الواردات",
    "المعطى الناقص: إجمالي قيمة أو كمية واردات الأردن.",
    "لا يمكن حساب حجم الواردات لعدم رصد الكمية الإجمالية.",
    "الشرط الحاجب: لا يُعتمد أي التزام مالي أوسع قبل رصد حجم الواردات الفعلي.",
])
def test_missing_data_or_heading_is_not_an_observed_pillar(text):
    import silk_quality_gate as q
    assert not q._narrated_outside_gap_sentences(
        text, q._PILLAR_BODY_NEEDLES["tam_log"])


def test_gap_does_not_hide_a_separate_observed_claim():
    import silk_quality_gate as q
    assert q._narrated_outside_gap_sentences(
        "حجم الواردات غير محسوب. بلغ حجم الواردات 51.1 مليون دولار.",
        q._PILLAR_BODY_NEEDLES["tam_log"])


def test_label_attributes_reach_the_classifier(monkeypatch):
    import silk_hs_classifier as hsc
    import silk_hs_from_image as image
    seen = {}
    def classify(product, **kwargs):
        seen.update(kwargs)
        return {"tier": "auto", "hs6": "040120", "source": "image_attribute"}
    monkeypatch.setattr(hsc, "classify_general", classify)
    attrs = [{"name": "نسبة الدهن", "value": 3.5, "unit": "%"}]
    out = image.classify_extraction({"ok": True, "product_name": "حليب",
                                    "extraction": {"attributes": attrs}})
    assert out["hs6"] == "040120"
    assert seen["label_attributes"] == attrs
    assert not set(image.FORBIDDEN_CLIENT_KEYS) & out.keys()


def test_numeric_attributes_reject_nonfinite_values():
    import silk_product_intake as intake
    attrs = [{"name": "نسبة الدهن", "value": v, "unit": "%"}
             for v in ["NaN", "Infinity", "-Infinity", True, "٣٫٥"]]
    assert intake._sanitize_attributes(attrs) == [
        {"name": "نسبة الدهن", "value": 3.5, "unit": "%"}]


@pytest.mark.parametrize("enabled,expected", [(True, "040120"), (False, None)])
def test_real_numeric_resolver_is_used_for_ambiguous_image(monkeypatch, enabled, expected):
    import silk_hs_classifier as hsc
    monkeypatch.setenv("SILK_HS_ATTRIBUTE_RESOLVE", "1" if enabled else "0")
    monkeypatch.setattr(hsc, "_deterministic_validated_candidates", lambda *a: [
        {"hs6": code, "overlap": 0.8, "verified": True, "source": "deterministic"}
        for code in ["040110", "040120", "040140"]])
    out = hsc.classify_general("حليب", allow_claude=False,
        label_attributes=[{"name": "نسبة الدهن", "value": 3.5, "unit": "%"}])
    assert out["hs6"] == expected
    assert out["tier"] == ("auto" if enabled else "candidates")


def test_lexical_match_cannot_override_a_conflicting_label_measurement(monkeypatch):
    import silk_hs_classifier as hsc
    monkeypatch.setenv("SILK_HS_ATTRIBUTE_RESOLVE", "1")
    monkeypatch.setattr(hsc, "_deterministic_validated_candidates", lambda *a: [
        {"hs6": "040110", "overlap": 1.0, "verified": True, "source": "deterministic"}])
    out = hsc.classify_general("حليب", allow_claude=False,
        label_attributes=[{"name": "نسبة الدهن", "value": 3.5, "unit": "%"}])
    # The measured value belongs to a displayed sibling, not an eligible code.
    assert out["hs6"] is None and out["tier"] != "auto"
