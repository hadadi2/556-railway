from copy import deepcopy

from silk_deep_pillars import build_pillar_inputs, build_components


def snapshot(value, note='', year=2023, source='UN Comtrade'):
    return dict(value=value, note=note, data_year=year, source=source,
                confidence=.9, status='', retrieved_at='2026-09-09')


def study(rows, key='competitors'):
    return {'missions': {key: {'failed': False, 'findings': [
        {'value': 'A narrative claim with no safely extractable metric',
         'source': 'UN Comtrade', 'confidence': .8, 'raw_evidence': rows}]}}}


def test_saved_competition_snapshot_reaches_decision_and_display_without_mutation():
    raw = snapshot({'hhi': 974, 'year': 2023, 'top_suppliers': [
        {'partner': 'Spain', 'share': 17.9}, {'partner': 'Saudi Arabia', 'share': 5.18}]})
    dr = study([raw, deepcopy(raw)])
    before = deepcopy(dr)
    p = build_pillar_inputs(dr)
    c = build_components(dr)
    assert p['competition_intensity']['hhi'] == 974
    assert p['competition_intensity']['top_supplier_share_pct'] == 17.9
    assert p['market_attractiveness']['saudi_share_pct'] == 5.18
    assert c['competition']['value'] == 974
    assert c['competition']['data_year'] == 2023
    assert c['competition']['source'] == 'UN Comtrade'
    assert c['competition']['confidence'] == .9
    assert dr == before


def test_numeric_snapshot_keeps_source_year_not_claim_retrieval_year():
    dr = study([snapshot(51128660.41, 'imports', 2023)], 'trade_flow')
    assert build_pillar_inputs(dr)['market_attractiveness']['tam_usd'] == 51128660.41
    assert build_components(dr)['market_size']['data_year'] == 2023


def test_prose_numbers_and_failed_snapshots_do_not_create_metrics():
    rows = [snapshot('HHI 974'), snapshot(None), snapshot(True),
            dict(snapshot(900, 'HHI'), confidence=0),
            dict(snapshot(900, 'HHI'), status='fetch_failed')]
    assert build_pillar_inputs(study(rows))['competition_intensity']['hhi'] is None


def test_direct_snapshot_retains_precedence_over_newer_mirror():
    direct = snapshot({'hhi': 974, 'year': 2023, 'top_suppliers': []})
    mirror = snapshot({'hhi': 3207, 'year': 2025, 'top_suppliers': []},
                      year=2025, source='UN Comtrade (mirror)')
    assert build_components(study([mirror, direct]))['competition']['value'] == 974
