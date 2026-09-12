"""Real auth + tenant DB integration, offline ITC fixture only inside these tests."""
import copy
import os
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
import requests
import socket
import threading
import time
import uvicorn


class TestClient:
    __test__ = False
    """Exercise the real HTTP stack on an ephemeral loopback port."""
    def __init__(self, app):
        sock=socket.socket();sock.bind(('127.0.0.1',0))
        self.base='http://127.0.0.1:'+str(sock.getsockname()[1])
        self.server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
        self.thread=threading.Thread(target=self.server.run,kwargs={'sockets':[sock]},daemon=True);self.thread.start()
        for _ in range(100):
            if self.server.started:break
            time.sleep(.05)
        assert self.server.started
        self.session=requests.Session();self.cookies=self.session.cookies
    def request(self,method,path,**kw):return self.session.request(method,self.base+path,timeout=15,**kw)
    def get(self,path,**kw):return self.request('GET',path,**kw)
    def post(self,path,**kw):return self.request('POST',path,**kw)
    def close(self):self.server.should_exit=True;self.thread.join(5);self.session.close()


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.env=patch.dict(os.environ, {'SILK_PLATFORM_DB':cls.tmp.name+'/platform.db','SILK_DATA_DIR':cls.tmp.name,'SILK_EXPORT_OPPORTUNITIES':'1','SILK_PLATFORM_BCRYPT_ROUNDS':'4','SILK_PLATFORM_SCHEDULER':'0'})
        cls.env.start()
        from silk_platform import api, db, seed, repository
        cls.db=db
        db.init_db()
        conn=db.connect();cls.identities=seed.seed(conn,demo_factories=True);conn.close()
        cls.app=FastAPI()
        with patch.object(api.study_runtime,'start'),patch.object(api.study_runtime,'recover',return_value={}):
            api.mount(cls.app)
        cls.http=TestClient(cls.app)
        cls.headers={}
        for name in ('factory_a','factory_b','admin','analyst'):
            who=cls.identities[name]
            r=cls.http.post('/platform/auth/login',json={'email':who['email'],'password':who['password']})
            assert r.status_code==200,r.text
            # Auth response exposes a token only if configured; use session cookie per identity.
            cls.headers[name]={'Cookie':'silk_session='+cls.http.cookies.get('silk_session')}
            cls.http.cookies.clear()
        r=cls.http.post('/platform/products',headers=cls.headers['factory_a'],json={'name':'Dates test','hs_code':'080410','hs_source':'manual'})
        assert r.status_code==200,r.text
        cls.pid=r.json()['id']
        cls.payload={'rows':[
            {'id':'887','item':{'code':'887','name':'Yemen'},'potential':100.25,'baseline':30,'unrealized':70.25,'raw':{'fixture':True}},
            {'id':'784','item':{'code':'784','name':'United Arab Emirates'},'potential':90,'baseline':20,'unrealized':70,'raw':{'fixture':True}},
            {'id':'368','item':{'code':'368','name':'Iraq'},'potential':80,'baseline':10,'unrealized':70,'raw':{'fixture':True}},
            {'id':'512','item':{'code':'512','name':'Oman'},'potential':70,'baseline':15,'unrealized':55,'raw':{'fixture':True}}], 'provenance':{'response_sha256':'verified-fixture','retrieved_at':'2026-09-12T10:00:00Z','source_url':'https://exportpotential.intracen.org/api/en/epis/markets','source':'ITC'},'count':4,'selection':{}}

    @classmethod
    def tearDownClass(cls):
        cls.http.close();cls.env.stop();cls.tmp.cleanup()

    def setUp(self):
        per_test_env=patch.dict(os.environ, {'SILK_PLATFORM_DB':self.tmp.name+'/platform.db','SILK_DATA_DIR':self.tmp.name,'SILK_EXPORT_OPPORTUNITIES':'1','SILK_EXPORT_OPPORTUNITY_ACCOUNTS':''})
        per_test_env.start();self.addCleanup(per_test_env.stop)
        conn=self.db.connect()
        try:
            for table in ('export_opportunities','export_opportunity_events','export_opportunity_source_status','export_opportunity_rate_windows','studies'):
                conn.execute('DELETE FROM '+table)
            conn.execute("UPDATE products SET hs_code='080410' WHERE id=?",(self.pid,))
            conn.commit()
        finally:conn.close()
        self.chart=patch('silk_platform.export_opportunities.client.chart',side_effect=lambda **kw:copy.deepcopy(self.payload));self.chart.start()
        self.period=patch('silk_platform.export_opportunities.client.period_info',return_value={'target_year':2030,'trade_years':'2020–2024'});self.period.start()
        self.addCleanup(self.chart.stop);self.addCleanup(self.period.stop)

    def request(self,method,path='',who='factory_a',**kw):
        return self.http.request(method,'/platform/export-opportunities'+path,headers=self.headers[who],**kw)

    def save(self):
        r=self.request('POST',json={'product_id':self.pid,'market':'887','response_sha256':'verified-fixture','potential':999999})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()['id']

    def test_01_auth_role_and_tenant_walls(self):
        self.assertEqual(self.http.get('/platform/export-opportunities').status_code,401)
        self.assertEqual(self.request('GET','/admin/metrics').status_code,403)
        self.assertEqual(self.request('GET',who='admin').status_code,403)
        self.assertEqual(self.request('GET','/markets?product_id='+str(self.pid),who='factory_b').status_code,404)
        self.assertEqual(self.request('GET','/config',who='analyst').json(),{'enabled':False})

    def test_public_preview_has_only_ranked_market_names(self):
        r=self.http.get('/platform/export-opportunities/preview?hs_code=080410')
        self.assertEqual(r.status_code,200,r.text)
        body=r.json();self.assertEqual(body['product']['hs_code'],'080410')
        self.assertEqual([m['rank'] for m in body['markets']],[1,2,3])
        self.assertEqual([m['code'] for m in body['markets']],['887','784','368'])
        serialized=str(body['markets'])
        for forbidden in ('potential','unrealized','baseline','provenance','response_sha256','raw'):
            self.assertNotIn(forbidden,serialized)
        self.assertEqual(self.http.get('/platform/export-opportunities/preview?hs_code=08041').status_code,422)
        self.assertEqual(self.http.get('/platform/export-opportunities/preview?hs_code=999999').status_code,404)

    def test_public_preview_failure_has_no_fallback(self):
        from export_potential.client import SourceError
        with patch('silk_platform.export_opportunities.client.chart',side_effect=SourceError('offline')):
            r=self.http.get('/platform/export-opportunities/preview?hs_code=080410')
        self.assertEqual(r.status_code,503)
        self.assertIn('no substitute',r.text)

    def test_public_funnel_is_aggregate_in_admin_metrics(self):
        r=self.http.post('/platform/export-opportunities/public-event',json={'kind':'search_started','hs_code':'080410'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.http.post('/platform/export-opportunities/public-event',json={'kind':'invented'}).status_code,422)
        d=self.request('GET','/admin/metrics',who='admin').json()
        self.assertGreaterEqual(d['public_funnel']['search_started'],1)
        self.assertNotIn('resource_id',str(d['public_funnel']))

    def test_02_verified_save_duplicate_and_tamper(self):
        oid=self.save();self.assertEqual(self.save(),oid)
        rows=self.request('GET').json()['opportunities'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['snapshot']['row']['potential'],100.25)
        self.assertEqual(self.request('GET',who='factory_b').json()['opportunities'],[])
        r=self.request('POST',json={'product_id':self.pid,'market':'887','response_sha256':'stale'})
        self.assertEqual(r.status_code,409)

    def test_03_source_failure_has_no_fallback(self):
        from export_potential.client import SourceError
        with patch('silk_platform.export_opportunities.client.chart',side_effect=SourceError('offline')):
            self.assertEqual(self.request('GET','/markets?product_id='+str(self.pid)).status_code,503)

    def test_04_study_atomic_idempotent_draft_and_quota(self):
        oid=self.save()
        self.assertEqual(self.request('POST',f'/{oid}/study',json={'confirmed':False}).status_code,422)
        self.assertEqual(self.request('POST',f'/{oid}/study',who='factory_b',json={'confirmed':True}).status_code,404)
        with patch('silk_platform.engine_bridge.market_known',return_value=True):
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses=list(pool.map(lambda _:self.request('POST',f'/{oid}/study',json={'confirmed':True,'notes':'Factory objective'}),range(2)))
        for r in responses:self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(responses[0].json()['study_id'],responses[1].json()['study_id'])
        sid=responses[0].json()['study_id']
        r=self.http.get('/platform/studies/'+str(sid),headers=self.headers['factory_a'])
        self.assertEqual(r.status_code,200,r.text)
        study=r.json();self.assertEqual(study['state'],'draft');self.assertEqual(study['market_pref'],'YEM');self.assertEqual(study['hs_source'],'unknown')
        conn=self.db.connect()
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM studies').fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM export_opportunity_events WHERE kind='study_requested'").fetchone()[0],1)
        finally:conn.close()

    def test_05_admin_is_aggregate_only(self):
        self.save()
        d=self.request('GET','/admin/metrics',who='admin').json()
        self.assertEqual(d['scope'],'aggregate_only');self.assertEqual(d['events']['saved'],1)
        self.assertNotIn('account_id',str(d));self.assertNotIn('Factory objective',str(d));self.assertNotIn('owner@',str(d))

    def test_06_feature_off_leaves_existing_routes_working(self):
        with patch.dict(os.environ,{'SILK_EXPORT_OPPORTUNITIES':'0'}):
            self.assertFalse(self.request('GET','/config').json()['enabled'])
            self.assertEqual(self.request('GET').status_code,404)
            for path in ('/platform/me','/platform/products','/platform/studies','/platform/overview'):
                r=self.http.get(path,headers=self.headers['factory_a']);self.assertEqual(r.status_code,200,(path,r.text))

    def test_07_cross_origin_cookie_write_rejected(self):
        h={**self.headers['factory_a'],'Origin':'https://untrusted.example'}
        r=self.http.post('/platform/export-opportunities',headers=h,json={})
        self.assertEqual(r.status_code,403)

    def test_08_changed_product_blocks_study(self):
        oid=self.save()
        conn=self.db.connect()
        try:
            conn.execute('UPDATE export_opportunities SET study_id=NULL WHERE id=?',(oid,));conn.execute("UPDATE products SET hs_code='080810' WHERE id=?",(self.pid,));conn.commit()
        finally:conn.close()
        self.assertEqual(self.request('POST',f'/{oid}/study',json={'confirmed':True}).status_code,409)

    def test_allowlist_is_server_enforced_and_invalid_fails_closed(self):
        for value in ('999999', 'not-an-account'):
            with patch.dict(os.environ,{'SILK_EXPORT_OPPORTUNITY_ACCOUNTS':value}):
                self.assertFalse(self.request('GET','/config').json()['enabled'])
                self.assertEqual(self.request('GET').status_code,404)
                self.assertTrue(self.request('GET','/config',who='admin').json()['enabled'])

    def test_archive_restore_and_tenant_boundary(self):
        oid=self.save()
        self.assertEqual(self.request('POST',f'/{oid}/archive',who='factory_b',json={'archived':True}).status_code,404)
        self.assertEqual(self.request('POST',f'/{oid}/archive',json={'archived':True}).status_code,200)
        self.assertEqual(self.request('GET').json()['total'],0)
        self.assertEqual(self.request('GET','?archived=true').json()['total'],1)
        self.assertEqual(self.request('POST',f'/{oid}/study',json={'confirmed':True}).status_code,409)
        self.assertEqual(self.request('POST',f'/{oid}/archive',json={'archived':False}).status_code,200)
        self.assertEqual(self.request('GET').json()['total'],1)

    def test_saving_an_archived_opportunity_restores_it(self):
        oid=self.save()
        self.assertEqual(self.request('POST',f'/{oid}/archive',json={'archived':True}).status_code,200)
        self.assertEqual(self.request('GET').json()['total'],0)
        self.assertEqual(self.save(),oid)
        self.assertEqual(self.request('GET').json()['total'],1)
        self.assertEqual(self.request('GET','?archived=true').json()['total'],0)

    def test_scope_change_is_excluded_from_admin_results(self):
        oid=self.save()
        with patch('silk_platform.engine_bridge.market_known',return_value=True):
            sid=self.request('POST',f'/{oid}/study',json={'confirmed':True}).json()['study_id']
        conn=self.db.connect()
        try:
            conn.execute("UPDATE studies SET market_pref='ARE',state='completed' WHERE id=?",(sid,));conn.commit()
        finally:conn.close()
        self.assertEqual(self.request('GET').json()['opportunities'][0]['link_status'],'changed')
        self.assertEqual(self.request('GET').json()['summary']['completed'],0)
        self.assertEqual(self.request('POST',f'/{oid}/study',json={'confirmed':True}).status_code,409)
        d=self.request('GET','/admin/metrics',who='admin').json()
        self.assertEqual(d['changed_study_links'],1)
        self.assertNotIn('completed',d['study_states'])

    def test_large_list_has_correct_totals_and_pages(self):
        oid=self.save();conn=self.db.connect()
        try:
            for n in range(505):
                conn.execute("INSERT INTO export_opportunities(account_id,product_id,exporter,market,hs_code,market_name,snapshot,created_at) SELECT account_id,product_id,exporter,?,hs_code,market_name,snapshot,created_at FROM export_opportunities WHERE id=?",('test-'+str(n),oid))
            conn.commit()
        finally:conn.close()
        d=self.request('GET','?page=6&page_size=100').json()
        self.assertEqual(d['total'],506);self.assertEqual(len(d['opportunities']),6)
        self.assertEqual(self.request('GET','?page_size=101').status_code,422)
        self.assertEqual(self.request('GET',who='factory_b').json()['total'],0)

    def test_rate_limit_does_not_call_itc(self):
        self.save();conn=self.db.connect()
        try:
            conn.execute('UPDATE export_opportunity_rate_windows SET hits=30');conn.commit()
        finally:conn.close()
        with patch('silk_platform.export_opportunities.client.chart') as remote:
            r=self.request('GET','/markets?product_id='+str(self.pid))
            self.assertEqual(r.status_code,429);self.assertEqual(r.headers['Retry-After'],'60');remote.assert_not_called()

    def test_draft_creation_rolls_back_when_audit_fails(self):
        oid=self.save()
        with patch('silk_platform.engine_bridge.market_known',return_value=True),patch('silk_platform.export_opportunities.audit.record',side_effect=RuntimeError('test rollback')):
            self.assertEqual(self.request('POST',f'/{oid}/study',json={'confirmed':True}).status_code,500)
        conn=self.db.connect()
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM studies').fetchone()[0],0)
            self.assertIsNone(conn.execute('SELECT study_id FROM export_opportunities WHERE id=?',(oid,)).fetchone()[0])
        finally:conn.close()

if __name__=='__main__':unittest.main()

