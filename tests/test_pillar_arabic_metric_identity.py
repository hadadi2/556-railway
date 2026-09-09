import pytest
from silk_data_layer import DataPoint
from silk_deep_pillars import _numeric


@pytest.mark.parametrize("text,note", [
    ("نصيبُ الفردِ 5,347.78 دولار", "World Bank 2025"),
    ("متوسط الدخل 5,347.78 دولار", "NY.GDP.PCAP.CD (2025)"),
    ("دخلُ الفردِ 5,347.78 دولار", "World Bank 2025"),
])
def test_income_metric_survives_arabic_vocalization(text, note):
    assert _numeric([DataPoint(text, "World Bank", .9, note)], "gdp_per_capita_usd") == 5347.78


def test_population_is_not_mistaken_for_income():
    assert _numeric([DataPoint("عدد السكان 11,520,684", "World Bank", .9,
                              "SP.POP.TOTL (2025)")], "gdp_per_capita_usd") is None
