"""A label's brand must not compete with its evidenced tariff characteristics."""
import base64
import json

import pytest


@pytest.mark.parametrize("brand", ["العلامة الذهبية", "مصنع المنتجات الممتازة"])
@pytest.mark.parametrize("kind,hs6", [
    ("حلاوة طحينية", "170490"), ("تمر", "080410"),
    ("قهوة محمصة", "090121"), ("عسل طبيعي", "040900")])
def test_vision_type_reaches_real_classifier_without_replacing_display_name(monkeypatch, brand, kind, hs6):
    import silk_product_intake as intake
    import silk_hs_from_image as image
    label = kind + " " + brand
    monkeypatch.setattr(intake, "_vision_extract", lambda *args: json.dumps({
        "product_name_ar": label, "product_type": kind,
        "readable": True, "confidence": 0.95, "ingredients": []}))
    raw = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 32).decode()
    read = intake.intake_image(raw, "image/png")
    result = image.classify_extraction(read, allow_claude=False)
    assert result["ok"] is True and result["hs6"] == hs6
    assert result["product_name"] == label


def test_uncertain_image_cannot_be_rescued_by_a_generic_type():
    import silk_hs_from_image as image
    out = image.classify_extraction({"ok": False, "product_name": "حلاوة",
        "extraction": {"product_type": "حلاوة طحينية"}}, allow_claude=False)
    assert out["ok"] is False and out["hs6"] is None


def test_generic_type_with_missing_tariff_detail_stays_undecided():
    import silk_hs_from_image as image
    out = image.classify_extraction({"ok": True, "product_name": "حليب علامة تجارية",
        "extraction": {"product_type": "حليب"}}, allow_claude=False)
    assert out["ok"] is False and out["hs6"] is None


def test_missing_type_keeps_the_existing_name_contract():
    import silk_hs_from_image as image
    out = image.classify_extraction({"ok": True, "product_name": "حلاوة طحينية",
                                    "extraction": {}}, allow_claude=False)
    assert out["ok"] is True and out["hs6"] == "170490"


def test_material_and_processing_qualifiers_are_forwarded_intact(monkeypatch):
    import silk_hs_classifier as hsc
    import silk_hs_from_image as image
    seen = []
    def classify(product, **kwargs):
        seen.append(product)
        return {"tier": "manual", "hs6": None}
    monkeypatch.setattr(hsc, "classify_general", classify)
    kind = "عصير برتقال مجمد مركز"
    image.classify_extraction({"ok": True, "product_name": "علامة تجارية",
                              "extraction": {"product_type": kind}})
    assert seen == [kind]
