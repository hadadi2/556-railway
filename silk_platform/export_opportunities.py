"""Opt-in opportunity workflow. Existing study validation and launch remain authoritative."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, HTTPException, Request, Query
from . import audit, repository, export_opportunity_store as store, throttle, tokens
from .db import now_iso
from .models import Role
from export_potential import client, hs_catalog

PREFIX = '/platform/export-opportunities'
GEO = {str(r['itcId']): r for r in json.loads((Path(__file__).resolve().parents[1] / 'export_potential/geography.json').read_text(encoding='utf-8'))}
PUBLIC_EVENTS = {'search_started', 'signup_clicked', 'login_completed', 'subscription_clicked'}


def public_products():
    return hs_catalog.products()


def itc_product(hs_code):
    item = public_products().get(hs_code)
    if not item:
        raise HTTPException(404, {'code': 'hs_not_found', 'message': 'رمز HS غير موجود في جدول مطابقة ITC / HS not found in ITC correspondences'})
    if item['excluded']:
        raise HTTPException(422, {'code': 'itc_product_excluded', 'message': 'هذا الرمز صحيح لكن ITC يستبعده من حساب إمكانات التصدير / Valid HS code excluded from ITC export potential', 'reason': item['exclusion_reason']})
    return item


def enabled():
    return os.environ.get('SILK_EXPORT_OPPORTUNITIES', '0') == '1'


def allowed(ctx):
    accounts = os.environ.get('SILK_EXPORT_OPPORTUNITY_ACCOUNTS', '').strip()
    if not accounts or ctx.role == Role.SILK_ADMIN:
        return True
    parts = accounts.split(',')
    return all(p.strip().isascii() and p.strip().isdigit() for p in parts) and str(ctx.account_id) in {p.strip() for p in parts}


def mount(app, open_db, require, validate_study):
    def public_identity(request):
        # A stable keyed digest supports aggregate funnel counts without storing
        # the visitor's network address in analytics.
        return tokens.sign('ep-preview|' + (request.client.host if request.client else '-'))

    def public_event(conn, request, kind, hs_code=None):
        audit.record(conn, action='opportunity_public_' + kind,
                     resource_type='export_opportunity_preview',
                     resource_id=public_identity(request),
                     changes={'hs_code': hs_code} if hs_code else None)
        conn.commit()

    @app.get(PREFIX + '/preview')
    def preview(request: Request, hs_code: str = Query(..., min_length=6, max_length=6)):
        if not enabled():
            raise HTTPException(404, 'Feature disabled')
        if not hs_code.isascii() or not hs_code.isdigit():
            raise HTTPException(422, 'HS code must contain six Latin digits / رمز HS يجب أن يتكون من ستة أرقام إنجليزية')
        item = itc_product(hs_code)
        conn = db()
        try:
            ident = 'ep-preview|' + public_identity(request)
            limits = throttle.named_limits('EPPREVIEW', 20, 60)
            if throttle.is_throttled(conn, ident, limits):
                raise HTTPException(429, 'Too many previews / تجاوزت حد البحث المؤقت', headers={'Retry-After': str(limits[1])})
            throttle.record_failure(conn, ident, limits)
        finally:
            conn.close()
        try:
            payload = client.chart(axis='markets', exporter='682', market='w',
                                   product=item['itc_code'], from_marker='i',
                                   to_marker='j', what_marker='k')
        except client.SourceError as exc:
            raise HTTPException(503, 'ITC unavailable; no substitute values / تعذر جلب ITC، لا توجد نتائج بديلة') from exc
        rows = sorted((r for r in payload['rows'] if r['id'] != '682'),
                      key=lambda r: (-(r['potential'] if r['potential'] is not None else -1), r['id']))[:3]
        if not rows:
            raise HTTPException(404, {'code': 'itc_no_results', 'message': 'الرمز صحيح، لكن ITC لا يعرض فرصًا للصادرات السعودية لهذا المنتج / Valid code, but ITC has no Saudi export opportunities for this product'})
        conn = db()
        try:
            public_event(conn, request, 'valid_code', hs_code)
            public_event(conn, request, 'preview_shown', hs_code)
        finally:
            conn.close()
        period = client.period_info()
        return {'product': {'hs_code': hs_code, **item},
                'markets': [{'rank': rank, 'code': row['id'],
                             'name': row['item']['name'],
                             'name_ar': GEO.get(row['id'], {}).get('name_ar')}
                            for rank, row in enumerate(rows, 1)],
                'period': {'target_year': period.get('target_year')},
                'source': 'ITC Export Potential Map', 'currency': 'USD'}

    @app.post(PREFIX + '/public-event')
    def track_public(request: Request, body: dict = Body(default=None)):
        if not enabled():
            raise HTTPException(404, 'Feature disabled')
        body = body if isinstance(body, dict) else {}
        kind = str(body.get('kind') or '')
        hs_code = str(body.get('hs_code') or '')
        if kind not in PUBLIC_EVENTS or (hs_code and (len(hs_code) != 6 or not hs_code.isascii() or not hs_code.isdigit())):
            raise HTTPException(422, 'Invalid funnel event')
        conn = db()
        try:
            ident = 'ep-funnel|' + public_identity(request)
            limits = throttle.named_limits('EPFUNNEL', 120, 3600)
            if throttle.is_throttled(conn, ident, limits):
                raise HTTPException(429, 'Too many events', headers={'Retry-After':'3600'})
            throttle.record_failure(conn, ident, limits)
            public_event(conn, request, kind, hs_code or None)
        finally:
            conn.close()
        return {'ok': True}

    def guard(request, role):
        ctx = require(request, role)
        if not enabled() or not allowed(ctx):
            raise HTTPException(404, 'Feature disabled')
        if request.method != 'GET' and getattr(request.state, 'auth_via', None) != 'bearer':
            origin = request.headers.get('origin')
            if (request.headers.get('sec-fetch-site') == 'cross-site' or
                    (origin and (urlsplit(origin).scheme, urlsplit(origin).netloc) != (request.url.scheme, request.url.netloc))):
                raise HTTPException(403, 'Cross-origin write refused')
        return ctx

    def db():
        return open_db()

    def product(conn, ctx, pid):
        row = repository.products(conn).get(ctx.account_id, pid)
        if row is None:
            raise HTTPException(404, 'Product not found')
        hs = str(row.get('hs_code') or '')
        if len(hs) != 6 or not hs.isascii() or not hs.isdigit():
            raise HTTPException(422, 'A specific six-digit product code is required / يلزم رمز منتج محدد من ستة أرقام')
        return row

    def owned(conn, ctx, oid):
        row = conn.execute('SELECT * FROM export_opportunities WHERE id=? AND account_id=?', (oid, ctx.account_id)).fetchone()
        if row is None:
            raise HTTPException(404, 'Opportunity not found')
        return dict(row)

    def chart(ctx, pid, exporter):
        if exporter != '682':
            raise HTTPException(422, 'Unknown exporter')
        conn = db()
        try:
            p = product(conn, ctx, pid)
            if not store.admit(conn, ctx.account_id):
                raise HTTPException(429, 'Too many requests / انتظر دقيقة ثم أعد المحاولة', headers={'Retry-After':'60'})
        finally:
            conn.close()
        try:
            mapped = itc_product(p['hs_code'])
            payload = client.chart(axis='markets', exporter=exporter, market='w', product=mapped['itc_code'], from_marker='i', to_marker='j', what_marker='k')
            payload['product_mapping'] = {'hs_code': p['hs_code'], **mapped}
        except client.SourceError as exc:
            conn = db()
            try:
                store.record_source(conn, ctx.account_id, failed=True)
            finally:
                conn.close()
            raise HTTPException(503, 'ITC unavailable; no substitute values / تعذر جلب ITC، لا توجد أرقام بديلة') from exc
        for row in payload['rows']:
            row['item']['name_ar'] = GEO.get(row['id'], {}).get('name_ar')
        conn = db()
        try:
            store.record_source(conn, ctx.account_id, payload['provenance'])
        finally:
            conn.close()
        return p, payload

    @app.get(PREFIX + '/config')
    def config(request: Request):
        ctx = require(request, Role.FACTORY, Role.SILK_ADMIN, Role.SILK_ANALYST)
        return {'enabled': enabled() and allowed(ctx) and ctx.role in (Role.FACTORY, Role.SILK_ADMIN)}

    @app.get(PREFIX + '/markets')
    def markets(request: Request, product_id: int, exporter: str = '682'):
        ctx = guard(request, Role.FACTORY)
        p, data = chart(ctx, product_id, exporter)
        return {**data, 'product': {'id': p['id'], 'name': p['name'], 'hs_code': p['hs_code']}, 'period': client.period_info()}

    @app.get(PREFIX)
    def listing(request: Request, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), archived: bool = False):
        ctx = guard(request, Role.FACTORY)
        conn = db()
        try:
            return store.listing(conn, ctx.account_id, page=page, page_size=page_size, archived=archived)
        finally:
            conn.close()

    @app.post(PREFIX + '/{oid}/archive')
    def archive(oid: int, request: Request, body: dict = Body(...)):
        ctx = guard(request, Role.FACTORY)
        if type(body.get('archived')) is not bool:
            raise HTTPException(422, 'Invalid archive status')
        conn = db()
        try:
            owned(conn, ctx, oid)
            store.set_archive(conn, ctx.account_id, oid, body['archived'])
            conn.commit()
            return {'id':oid, 'archived':body['archived']}
        finally:
            conn.close()

    @app.post(PREFIX)
    def save(request: Request, body: dict = Body(...)):
        ctx = guard(request, Role.FACTORY)
        pid = body.get('product_id')
        if type(pid) is not int or pid < 1:
            raise HTTPException(422, 'Invalid product')
        exporter, market = str(body.get('exporter', '682')), str(body.get('market', ''))
        if market not in GEO or market == exporter:
            raise HTTPException(422, 'Choose a foreign economy / اختر سوقًا خارجيًا')
        p, payload = chart(ctx, pid, exporter)
        if body.get('response_sha256') != payload['provenance']['response_sha256']:
            raise HTTPException(409, 'Refresh the market list before saving / حدّث قائمة الأسواق قبل الحفظ')
        row = next((r for r in payload['rows'] if r['id'] == market), None)
        if row is None:
            raise HTTPException(422, 'Market absent from ITC results')
        snapshot = {'row': row, 'provenance': payload['provenance'], 'period': client.period_info(), 'product_name': p['name'], 'product_mapping': payload.get('product_mapping')}
        conn = db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            if product(conn, ctx, pid)['hs_code'] != p['hs_code']:
                raise HTTPException(409, 'Product changed; refresh')
            oid, created = store.save(conn, ctx.account_id, p, exporter, market, GEO[market]['alpha3'], snapshot)
            conn.commit()
            return {'id':oid, 'created':created}
        finally:
            conn.close()

    @app.post(PREFIX + '/{oid}/study')
    def study(oid: int, request: Request, body: dict = Body(...)):
        ctx = guard(request, Role.FACTORY)
        if body.get('confirmed') is not True:
            raise HTTPException(422, 'Confirm the product, code and market first')
        notes = body.get('notes', '')
        if not isinstance(notes, str) or len(notes) > 2000:
            raise HTTPException(422, 'Notes must be at most 2000 characters')
        conn = db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            o = owned(conn, ctx, oid)
            if o['archived_at']:
                raise HTTPException(409, 'Restore the opportunity first / استعد الفرصة أولًا')
            if o['study_id']:
                existing = repository.studies(conn).get(ctx.account_id, o['study_id'])
                if existing:
                    if existing['product_id'] != o['product_id'] or existing['hs_code'] != o['hs_code'] or existing['market_pref'] != o['market_iso3']:
                        raise HTTPException(409, 'Linked study scope changed; review the study / تغير نطاق الدراسة المرتبطة؛ راجع الدراسة')
                    return {'study_id': o['study_id'], 'created': False}
                # A deleted draft may be recreated, but never duplicate a live study.
            p = product(conn, ctx, o['product_id'])
            if p['hs_code'] != o['hs_code']:
                raise HTTPException(409, 'Product code changed; save a new opportunity / تغير رمز المنتج، احفظ فرصة جديدة')
            # The existing engine is the Saudi export study workflow; don't silently
            # reinterpret a different origin, which it cannot accept as a study field.
            if o['exporter'] != '682':
                raise HTTPException(422, 'Study integration currently supports Saudi exports / ربط الدراسة متاح حاليًا للصادرات السعودية')
            fields = validate_study(conn, ctx, {'product': p['name'], 'product_id': p['id'], 'hs_code': o['hs_code'], 'market_pref': GEO[o['market']]['alpha3'], 'image_id': p.get('image_id')})
            fields.update(title_ar=p['name'], created_by_user_id=ctx.user_id, hs_source='unknown', description_ar=notes)
            created = repository.studies(conn).create(ctx.account_id, fields, commit=False)
            store.link_study(conn, ctx.account_id, oid, created['id'], notes)
            audit.record(conn, action='study_created', user_id=ctx.user_id, account_id=ctx.account_id, resource_type='study', resource_id=created['id'])
            conn.commit()
            return {'study_id':created['id'],'created':True}
        finally:
            conn.close()

    @app.get(PREFIX + '/admin/metrics')
    def metrics(request: Request, days: int = 30):
        guard(request, Role.SILK_ADMIN)
        if days not in (7,30,90):
            raise HTTPException(422,'Invalid period')
        conn = db()
        try:
            result = store.metrics(conn, days)
            cutoff = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ','now',?)", (f'-{days} days',)).fetchone()[0]
            result['public_funnel'] = {r['kind']: r['n'] for r in conn.execute(
                "SELECT substr(action,20) kind,COUNT(*) n FROM audit_log "
                "WHERE action LIKE 'opportunity_public_%' AND created_at>=? GROUP BY action", (cutoff,))}
            for row in result['top_markets']:
                row['market_name_ar'] = GEO.get(row['market'], {}).get('name_ar')
            return result
        finally:
            conn.close()

