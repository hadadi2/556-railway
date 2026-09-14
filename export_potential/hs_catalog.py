"""مطابقة HS6 الرسمية مع منتجات ITC؛ لا تغيير أو تقدير للقيم المالية."""
import csv
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def products():
    root = Path(__file__).resolve().parents[1]
    with (root / 'data/hs_codes.csv').open(encoding='utf-8-sig') as source:
        arabic = {r['hs_code']: r['name_ar'] for r in csv.DictReader(source)}
    with (root / 'export_potential/hs_correspondences.csv').open(encoding='utf-8') as source:
        return {r['HS6']: {
            'name': r['HS6_name'], 'name_ar': arabic.get(r['HS6']),
            'itc_code': r['k'], 'itc_name': r['k_name_short'],
            'grouped': r['HS6'] != r['k'],
            'excluded': 'EPI' in r['Excluded_from'],
            'exclusion_reason': r['Reason'],
        } for r in csv.DictReader(source)}
