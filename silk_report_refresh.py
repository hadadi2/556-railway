"""Prepare a regenerated report from current checkpoints, without database writes."""
from copy import deepcopy
from dataclasses import asdict, is_dataclass


def _plain(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def prepare(found, mission_reports, *, refresh_trends=False, refresh_prices=False,
            refresh_analysis=False):
    result = deepcopy(found)
    reports = dict(mission_reports) if refresh_trends or refresh_prices else mission_reports
    dr = result['deep_research']
    if refresh_trends or refresh_prices or refresh_analysis:
        from silk_market_resolver import resolve_market
        from silk_llm_runtime import LLMMissionAgent
        from silk_missions import MISSIONS, _MISSION_TIMEOUT_S
        market = result.get('market') or {}
        ref, _ = resolve_market(market.get('iso3') or market.get('name_en') or '')
        if ref is None:
            raise ValueError('Stored market cannot be resolved for trend refresh')
        selected = [('demand_trends', 'trend_refresh', 6)] if refresh_trends else []
        if refresh_prices:
            selected.append(('pricing_scout', 'price_refresh', 8))
        for mission, status_key, limit in selected:
            fresh = LLMMissionAgent(MISSIONS[mission]).run({
                'market': ref, 'product': result.get('product', ''),
                'hs_code': result.get('hs_code'), 'budget': {'tool_calls': limit},
                'wall_timeout_s': _MISSION_TIMEOUT_S,
            })
            # A failed refresh cannot erase prior evidence. Keep its failure explicit.
            if fresh.failed:
                dr[status_key] = {'status': 'failed', 'note': fresh.summary}
            else:
                reports[mission] = fresh
                dr[status_key] = {'status': 'completed', 'note': fresh.summary}
    dr['missions'] = {key: asdict(value) if is_dataclass(value) else deepcopy(value)
                      for key, value in reports.items()}
    if refresh_analysis:
        from silk_market_analyst import analyze_market, to_synthesis_input
        fresh_analysis = analyze_market(ref, result.get('product', ''), reports,
            hs_code=result.get('hs_code'), product_card=result.get('product_card'))
        if fresh_analysis['report'].failed:
            raise ValueError('Analysis refresh failed; stored report has not been changed')
        dr['analyst'] = _plain(fresh_analysis)
        dr['analysis_refresh'] = {'status': 'completed',
            'analyst_input': _plain(to_synthesis_input(fresh_analysis))}
    from silk_deep_pillars import decide_for_deep, promote_engine_verdict, build_components
    rows = result.get('markets') or []
    # Reuse stored regulatory evidence, and calculate once for writer and display.
    if rows:
        row = rows[0]
        decision = decide_for_deep(dr, product_card=result.get('product_card'),
                                   regulatory=row.get('regulatory'))
        if decision:
            dr['verdict'] = promote_engine_verdict(dr.get('verdict') or {}, decision)
            row['decision'] = decision
            row['components'] = build_components(dr)
            if decision.get('score') is not None:
                row['total_score'] = decision['score']
            if decision.get('confidence') is not None:
                row['confidence'] = decision['confidence']
    return result, reports
