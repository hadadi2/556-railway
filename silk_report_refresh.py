"""Prepare a regenerated report from current checkpoints, without database writes."""
from copy import deepcopy
from dataclasses import asdict, is_dataclass


def prepare(found, mission_reports, *, refresh_trends=False):
    result = deepcopy(found)
    reports = dict(mission_reports) if refresh_trends else mission_reports
    dr = result['deep_research']
    if refresh_trends:
        from silk_market_resolver import resolve_market
        from silk_llm_runtime import LLMMissionAgent
        from silk_missions import MISSIONS, _MISSION_TIMEOUT_S
        market = result.get('market') or {}
        ref, _ = resolve_market(market.get('iso3') or market.get('name_en') or '')
        if ref is None:
            raise ValueError('Stored market cannot be resolved for trend refresh')
        fresh = LLMMissionAgent(MISSIONS['demand_trends']).run({
            'market': ref, 'product': result.get('product', ''),
            'hs_code': result.get('hs_code'), 'budget': 6,
            'wall_timeout_s': _MISSION_TIMEOUT_S,
        })
        # A failed refresh cannot erase prior evidence. Keep its failure explicit.
        if fresh.failed:
            dr['trend_refresh'] = {'status': 'failed', 'note': fresh.summary}
        else:
            reports['demand_trends'] = fresh
            dr['trend_refresh'] = {'status': 'completed', 'note': fresh.summary}
    dr['missions'] = {key: asdict(value) if is_dataclass(value) else deepcopy(value)
                      for key, value in reports.items()}
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
