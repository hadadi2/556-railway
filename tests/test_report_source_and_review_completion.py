import json
from unittest.mock import patch

import pandas as pd


def test_dated_trends_reach_mission_without_a_second_fetch():
    import silk_trends_agent as t
    df = pd.DataFrame({'halva': [10, 30, 80]},
                      index=pd.to_datetime(['2025-01-01', '2025-01-15', '2025-03-01']))
    with patch.object(t, '_interest_with_series', return_value=df) as fetch:
        result = t.trends_interest('halva', geo='JO')
    assert fetch.call_count == 1
    assert '2025-01=20.00' in result.note
    assert '2025-03=80.00' in result.note
    assert '2025-02=' not in result.note
    assert 'not sales' in result.note


def test_stored_trends_keep_the_original_series_and_observation_date():
    import silk_trends_agent as t
    from silk_data_layer import DataPoint
    row = {'value': 20, 'confidence': .7, 'retrieved_at': '2025-04-01',
           'note': 'monthly mean search interest: 2025-01=20.00'}
    with patch.object(t, 'trends_interest', return_value=DataPoint(None, 'Google Trends', 0)), \
         patch('silk_store.get_indicator', return_value=row):
        result = t.trends_interest_resilient('halva', geo='JO')
    assert result.status == 'stale'
    assert result.retrieved_at == '2025-04-01'
    assert result.confidence == .5
    assert '2025-01=20.00' in result.note


def test_reviewer_can_return_a_complete_multi_issue_verdict():
    import silk_ai_judge as a
    issues = [('ملاحظة تحتاج تصحيح الرقم ومصدره. ' * 6) for _ in range(8)]
    verdict = json.dumps({'issues': issues, 'blocking': ['تناقض رقمي'],
                          'approved': False}, ensure_ascii=False)
    draft = '\n\n'.join(f'## {i}. {s}\nفقرة مكتملة.'
                        for i, s in enumerate(a.report_sections('ar'), 1))
    def provider(*args, max_tokens, **kwargs):
        return verdict if max_tokens >= 3000 else verdict[:500]
    with patch.object(a, 'available', return_value=True), \
         patch.object(a, '_call', side_effect=provider):
        result = a.review_report(draft, {})
    assert result['review_status'] == 'rejected'
    assert 'تناقض رقمي' in result['blocking']
    assert len(result['issues']) >= 8
