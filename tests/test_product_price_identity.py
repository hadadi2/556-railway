from silk_agents import AgentReport
from silk_data_layer import DataPoint
from silk_product_evidence import price_reports
from silk_ai_judge import _facts


def test_tahini_price_cannot_be_renamed_as_halva():
    wrong = DataPoint("حلاوة الدرة 400 غرام 1.99 دينار", "Retailer", .7,
                      url="https://example.test/product/durra-tahina-400-g/s/912943")
    right = DataPoint("حلاوة طحينية بالفستق 500 غرام 2.10 دينار", "Retailer", .7)
    named_wrong = DataPoint("تحينة الدرة 400 غرام 2.25 دينار", "Retailer", .7)
    report = AgentReport("pricing_scout", [wrong, right, named_wrong])
    fixed = price_reports({"pricing_scout": report}, "حلاوة طحينية")
    assert [dp.value for dp in fixed["pricing_scout"].findings] == [None, right.value, None]
    assert "1.99" not in _facts(list(fixed.values()))
    assert report.findings[0].value == wrong.value
    assert not fixed["pricing_scout"].failed


def test_reverse_product_and_unrelated_studies():
    halva = DataPoint("Halva 500 g 2.10 JOD", "Retailer", .7)
    tahini = DataPoint("Tahini 400 g 1.99 JOD", "Retailer", .7)
    report = AgentReport("pricing_scout", [halva, tahini])
    assert price_reports({"pricing_scout": report}, "Tahini")["pricing_scout"].findings[0].value is None
    assert price_reports({"pricing_scout": report}, "Honey")["pricing_scout"] is report
