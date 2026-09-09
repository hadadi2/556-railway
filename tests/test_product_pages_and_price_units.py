from unittest.mock import Mock, patch

import pytest
from silk_product_pages import read_product_pages
from silk_price_units import normalize_listing, package_basis, report_price_issues


@pytest.mark.parametrize('title,amount,unit,expected', [
    ('حلاوة 300 غ', 1.25, 'kg', 4.1667),
    ('Juice 250 ml', 2, 'litre', 8),
    ('ماء 1.5 لتر', 3, 'litre', 2),
    ('Soap 4 pieces', 12, 'piece', 3),
])
def test_normalization_uses_observed_pack_not_a_universal_kilogram(title, amount, unit, expected):
    row = normalize_listing({'title': title, 'price': amount, 'currency': 'JOD'})
    assert row['comparison_unit'] == unit
    assert row['comparison_price'] == expected


@pytest.mark.parametrize('title', ['Product', '6 x 250 ml', '300 g / 500 g', '0 ml'])
def test_ambiguous_or_invalid_pack_is_not_normalized(title):
    assert package_basis(title) is None


def table(pack='300 غ', heading='السعر/كجم', price='غير متاح'):
    return ('| المنتج | العبوة | سعر التجزئة | ' + heading + ' |\n'
            '|---|---|---|---|\n| منتج | ' + pack + ' | ' + price + ' | غير محسوب |\n')


def test_claiming_observed_prices_without_any_numeric_retail_price_is_blocked():
    text = table() + 'أسعار السوق مرصودة؛ تحديد موقعك السعري يتطلب سعر المصنع.'
    assert report_price_issues(text)[0]['check'] == 'retail_price_presence_conflict'
    assert not report_price_issues(table(price='1.25 JOD') + 'أسعار السوق مرصودة')
    assert not report_price_issues(table() + 'لم نتمكن من توثيق سعر تجزئة.')


def test_litres_and_pieces_cannot_be_labelled_price_per_kg():
    for pack in ['250 ml', '4 قطع']:
        assert report_price_issues(table(pack=pack))[0]['check'] == 'retail_unit_mismatch'
        assert not report_price_issues(table(pack=pack, heading='السعر لوحدة المقارنة'))


def test_read_pages_preserves_real_source_text_and_limits_batch(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'test-key')
    url = 'https://store.example/product'
    response = Mock()
    response.json.return_value = {'results': [
        {'url': url, 'raw_content': 'حلاوة 300 غ — 1.25 JOD'},
        {'url': 'https://other.example/unrequested', 'raw_content': 'unrelated'}]}
    with patch('silk_product_pages.throttled_request', return_value=response) as call:
        rows = read_product_pages([url, 'http://127.0.0.1/private', url], 'حلاوة')
    assert len(rows) == 1 and rows[0].url == url
    assert '1.25 JOD' in rows[0].value['content']
    assert call.call_args.kwargs['json_body']['urls'] == [url]
    assert call.call_args.kwargs['json_body']['extract_depth'] == 'basic'


def test_extraction_failure_never_creates_a_price(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'test-key')
    with patch('silk_product_pages.throttled_request', side_effect=RuntimeError('unavailable')):
        row = read_product_pages(['https://store.example/product'])[0]
    assert row.value is None and row.confidence == 0


def test_price_checks_drive_export_failure():
    from silk_export_gate import _fail_drivers
    findings = report_price_issues(table() + 'أسعار السوق مرصودة')
    assert 'retail_price_presence_conflict' in _fail_drivers(findings)
