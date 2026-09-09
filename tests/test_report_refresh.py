from copy import deepcopy
from unittest.mock import patch

from silk_agents import AgentReport
from silk_data_layer import DataPoint
from silk_report_refresh import prepare


def saved():
    return {'product': 'halva', 'hs_code': '170490', 'market': {'iso3': 'JOR'},
            'markets': [{'deep': True, 'components': {}, 'regulatory': {}}],
            'deep_research': {'missions': {}, 'verdict': {}}}


def reports():
    return {'trade_flow': AgentReport('trade', [DataPoint(51128660, 'UN Comtrade',
            .9, 'imports', data_year=2023)], False, 'ok'),
            'demand_trends': AgentReport('trends', [DataPoint(2, 'Google Trends', .7)],
                                        False, 'old')}


def test_regeneration_updates_components_without_network_or_mutating_stored_result():
    original, missions = saved(), reports()
    before = deepcopy(original)
    with patch('silk_llm_runtime.LLMMissionAgent.run') as run:
        result, current = prepare(original, missions)
    run.assert_not_called()
    assert current is missions
    assert original == before
    assert result['markets'][0]['components']['market_size']['value'] == 51128660
    assert result['markets'][0]['components']['market_size']['data_year'] == 2023


def test_explicit_refresh_replaces_only_trends_with_actual_agent_result():
    old = reports()
    fresh = AgentReport('trends', [DataPoint(12, 'Google Trends', .7)], False, 'new')
    with patch('silk_llm_runtime.LLMMissionAgent.run', return_value=fresh) as run:
        result, current = prepare(saved(), old, refresh_trends=True)
    assert run.call_count == 1
    assert current['demand_trends'] is fresh
    assert current['trade_flow'] is old['trade_flow']
    assert old['demand_trends'].summary == 'old'
    assert result['deep_research']['trend_refresh']['status'] == 'completed'


def test_failed_refresh_keeps_prior_evidence_and_records_failure():
    old = reports()
    with patch('silk_llm_runtime.LLMMissionAgent.run',
               return_value=AgentReport('trends', [], True, 'source unavailable')):
        result, current = prepare(saved(), old, refresh_trends=True)
    assert current['demand_trends'] is old['demand_trends']
    assert result['deep_research']['trend_refresh']['status'] == 'failed'


def test_refresh_reaches_real_runtime_with_bounded_tool_budget():
    # Exercise the runtime's budget merge; mocking Agent.run alone hid a
    # scalar-vs-mapping mismatch before any search could start.
    with patch('silk_llm_runtime.LLMMissionAgent.run', autospec=True,
               side_effect=lambda agent, task: agent._execute(task)), \
         patch('silk_llm_runtime._run_loop', return_value={'findings': []}) as loop:
        prepare(saved(), reports(), refresh_trends=True)
    assert loop.call_count == 1
    assert loop.call_args.args[2]['tool_calls'] == 6


def test_price_refresh_runs_only_pricing_and_preserves_other_checkpoints():
    old = reports()
    fresh = AgentReport('prices', [DataPoint('Product 300 g: 1.25 JOD',
                                           'Store', .65)], False, 'priced listing')
    with patch('silk_llm_runtime.LLMMissionAgent.run', return_value=fresh) as run:
        result, current = prepare(saved(), old, refresh_prices=True)
    assert run.call_count == 1
    assert run.call_args.args[0]['budget'] == {'tool_calls': 8}
    assert current['pricing_scout'] is fresh
    assert current['demand_trends'] is old['demand_trends']
    assert result['deep_research']['price_refresh']['status'] == 'completed'
