from __future__ import annotations
import csv
import json
import io
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from . import client

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'web'
REGIONS_AR = {'World':'العالم','Africa':'أفريقيا','Americas':'الأمريكتان','Asia':'آسيا','Europe':'أوروبا','Oceania':'أوقيانوسيا','Middle East':'الشرق الأوسط','East Asia':'شرق آسيا','South Asia':'جنوب آسيا','Southeast Asia':'جنوب شرق آسيا','Northern Africa':'شمال أفريقيا','Eastern Africa':'شرق أفريقيا','Western Africa':'غرب أفريقيا','Southern Africa':'جنوب أفريقيا','Central Africa':'وسط أفريقيا','North America':'أمريكا الشمالية','South & Central America':'أمريكا الجنوبية والوسطى','Caribbean':'الكاريبي','Pacific':'المحيط الهادئ','EU & West Europe':'الاتحاد الأوروبي وغرب أوروبا','East Europe & Central Asia':'شرق أوروبا وآسيا الوسطى'}

@lru_cache(maxsize=1)
def geography():
    return {str(r['itcId']): r for r in json.loads((Path(__file__).parent/'geography.json').read_text(encoding='utf-8'))}

@lru_cache(maxsize=1)
def product_ar():
    with (ROOT/'data/hs_codes.csv').open(encoding='utf-8-sig') as f:
        return {r['hs_code']: r['name_ar'] for r in csv.DictReader(f) if r.get('name_ar')}

def translate_item(item, kind):
    item = dict(item)
    code = str(item['code'])
    name = item.get('name') or {'w':'World','a':'All products'}.get(code,code)
    item['name'] = name
    geo = geography().get(code, {}) if kind == 'countries' else {}
    item['name_ar'] = geo.get('name_ar') if geo else product_ar().get(code) if kind == 'products' else REGIONS_AR.get(name)
    item['geo'] = {k: geo[k] for k in ('lat','lng','alpha3') if k in geo} or None
    return item

def mount(app):
    router = APIRouter(prefix='/export-potential', tags=['export-potential'])

    @router.get('/health')
    def health():
        return {'status':'ok','module':'silk_export_potential','isolated':True,'source_mode':'itc_public_charts','estimates_enabled':False,'version':'2.0'}

    @router.get('/catalog')
    def catalog():
        kinds = ('countries','sub-regions','regions','products','sub-sectors','sectors')
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(lambda k: client.read('/api/en/'+k), kinds))
            for data, _ in results:
                if not isinstance(data, list) or any(not isinstance(r, dict) or not isinstance(r.get('code'), (str, int)) for r in data):
                    raise client.SourceError('ITC catalogue schema changed')
            result = {kind:[translate_item(r,kind) for r in data] for kind,(data,_) in zip(kinds,results)}
            result['provenance'] = results[0][1]
            return result
        except client.SourceError as exc:
            raise HTTPException(502,detail={'code':'itc_unavailable','message':str(exc)}) from exc

    @router.get('/data')
    def data(axis: Literal['markets','products','exporters']='markets', exporter: str='682', market: str='w', product: str='080410', from_marker: str='i', to_marker: str='j', what_marker: str='k'):
        try:
            result = client.chart(axis=axis,exporter=exporter,market=market,product=product,from_marker=from_marker,to_marker=to_marker,what_marker=what_marker)
            kind = ('products' if what_marker=='k' else 'sectors' if what_marker=='ls' else 'sub-sectors') if axis=='products' else ('countries' if (to_marker if axis=='markets' else from_marker) in ('i','j') else 'regions')
            for row in result['rows']:
                row['item'] = translate_item(row['item'],kind)
            result['period'] = client.period_info()
            return result
        except ValueError as exc:
            raise HTTPException(422,detail=str(exc)) from exc
        except client.SourceError as exc:
            raise HTTPException(502,detail={'code':'itc_unavailable','message':str(exc)}) from exc

    @router.get('/estimate')
    def disabled_estimate():
        raise HTTPException(410,detail={'code':'local_estimate_retired','message':'Local approximation withdrawn. Use /export-potential/data for ITC chart values.'})

    @router.get('/download')
    def download(axis: Literal['markets','products','exporters']='markets',exporter: str='682',market: str='w',product: str='080410',from_marker: str='i',to_marker: str='j',what_marker: str='k',ids: str='',sort: str='potential',expected: str=''):
        result = data(axis,exporter,market,product,from_marker,to_marker,what_marker)
        if expected and result['provenance']['response_sha256'] != expected:
            raise HTTPException(409,'ITC data changed. Refresh the chart before downloading.')
        wanted = set(ids.split(','))
        selected = [row for row in result['rows'] if row['id'] in wanted]
        if not selected:
            raise HTTPException(422,'Select chart items before downloading')
        if sort not in {'potential','baseline','unrealized','demand','ease'}:
            raise HTTPException(422,'Invalid sort metric')
        selected.sort(key=lambda r: (-(r[sort] if r[sort] is not None else -float('inf')),r['id']))
        def safe(value):
            if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
                return "'"+value
            return value
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['code','name_en','name_ar','potential_usd','baseline_exports_usd','unrealized_usd','realized_ratio','demand','ease','axis','exporter','market','product','from_marker','to_marker','what_marker','target_year','trade_years','source_url','retrieved_at','response_sha256'])
        p = result['provenance']
        for r in selected:
            writer.writerow(map(safe,[r['id'],r['item']['name'],r['item'].get('name_ar'),r['potential'],r['baseline'],r['unrealized'],r['realized_ratio'],r['demand'],r['ease'],axis,exporter,market,product,from_marker,to_marker,what_marker,result['period']['target_year'],result['period']['trade_years'],p['source_url'],p['retrieved_at'],p['response_sha256']]))
        return Response(content=('\ufeff'+stream.getvalue()).encode('utf-8'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="silk-itc-{axis}.csv"','Cache-Control':'no-store'})

    @router.get('/assets/{name}')
    def assets(name: str):
        files = {'app.js':('export-potential-enhance.js','application/javascript'),'app.css':('export-potential.css','text/css')}
        if name not in files:
            raise HTTPException(404)
        file,mime = files[name]
        return FileResponse(ASSETS/file,media_type=mime,headers={'Cache-Control':'no-cache'})

    @app.get('/export-potential',include_in_schema=False)
    @app.get('/export-potential/',include_in_schema=False)
    def page():
        return FileResponse(ASSETS/'export-potential.html',headers={'Cache-Control':'no-cache'})
    app.include_router(router)
