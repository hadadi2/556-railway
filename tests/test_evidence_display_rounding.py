from silk_data_layer import DataPoint
from silk_evidence_contract import unsupported_numbers


def test_decimal_millions_can_round_exact_source_value():
    points = [DataPoint(34588670.644, "UN Comtrade", .9, "HS 170490, 2019", unit="USD")]
    assert unsupported_numbers("واردات HS 170490 في 2019 بلغت 34.59 مليون دولار", points) == []


def test_unit_value_can_round_to_cents():
    assert unsupported_numbers("قيمة الوحدة 2.32 دولار", [DataPoint(2.3179, "UN Comtrade", .7)]) == []


def test_wrong_rounding_and_wrong_scale_are_still_rejected():
    points = [DataPoint(34588670.644, "UN Comtrade", .9)]
    assert unsupported_numbers("34.60 million", points)
    assert unsupported_numbers("34.59 billion", points)
    assert unsupported_numbers("34.59", points)


def test_unsupported_growth_cannot_be_laundered_by_rounding():
    assert unsupported_numbers("CAGR 10.78%", [DataPoint(34588670.644, "UN Comtrade", .9)])


def test_rounding_is_not_transitively_chained():
    assert unsupported_numbers("2.32 then 2.33", [DataPoint(2.3151, "UN Comtrade", .9)]) == [2.33]
