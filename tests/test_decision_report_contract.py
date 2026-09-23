from unittest.mock import patch

import silk_ai_judge as writer
from silk_render import _flip_conditions


def test_missing_profitability_remains_a_condition_even_with_public_contacts():
    contacts = {'leads': [{'title': 'Wholesale company', 'phone': '+96260000000'}]}
    conditions = _flip_conditions('conditional', False, contacts, 'Jordan',
                                  missing_components=['factory_price', 'retail_price'])
    # الدرس ٢٨٣ (معلن): المكوّناتُ الناقصة شرطٌ واحد بقائمتها لا شرطٌ لكلٍّ.
    assert len(conditions) == 2
    assert all(item['met'] is False for item in conditions)
    assert any('إعادة تقييم' in item['condition'] for item in conditions)


def test_writer_receives_decision_language_without_automatic_two_condition_upgrade():
    calls = []
    with patch.object(writer, 'available', return_value=True), \
         patch.object(writer, '_call', side_effect=lambda system, user, **kw:
                      calls.append((system, user)) or None):
        writer.deep_report({}, 'old analysis', {
            'verdict': 'WATCH', 'decision_missing_components': ['factory_price']},
            'حليب', 'الأردن')
    prompt = '\n'.join(calls[0])
    assert 'شروط إعادة تقييم القرار' in prompt
    assert 'لا تفرض عدد شرطين' in prompt
    assert 'الحكم إلى GO (مثل:' not in prompt
    assert 'إلى GO إذا <شرطان' not in prompt
    assert 'سعة الحاوية حد نقل' in prompt
    assert 'ليس نسبة مشترين' in prompt
    assert 'لا تفترض كمية استهلاك للفرد' in prompt
    assert 'احسب حجم الشريحة في جدول' not in prompt
