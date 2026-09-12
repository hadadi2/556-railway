import unittest
from unittest.mock import patch
from export_potential import client

class ChartContractTests(unittest.TestCase):
    def test_economy_codes_are_itc_codes_not_m49_rewrites(self):
        self.assertEqual(client.chart_path('markets','699','w','080410','i','j','k'),
            '/api/en/epis/markets/from/i/699/to/j/all/what/k/080410')

    def test_axes_and_aggregate_markers(self):
        self.assertEqual(client.chart_path('products','682','887','a','i','j','s'),
            '/api/en/epis/products/from/i/682/to/j/887/what/s/all')
        self.assertEqual(client.chart_path('exporters','w','w','080410','r','w','k'),
            '/api/en/epis/exporters/from/r/all/to/w/all/what/k/080410')

    def test_preserves_source_precision_and_itc_unrealized_definition(self):
        row={'item':{'code':'784','name':'United Arab Emirates'},'value':220405616.82,
             'exportValue':114084733.33,'realizedPotential':0.5176126406,'gap':0.4823873594,
             'lineWidth':11.179614401,'bubbleSize':357680282.19}
        actual=client.normalize(row)
        self.assertEqual(actual['potential'],220405616.82)
        self.assertEqual(actual['baseline'],114084733.33)
        self.assertEqual(actual['unrealized'],220405616.82*(1-0.5176126406))
        self.assertEqual(actual['raw'],row)

    def test_missing_values_never_become_zero(self):
        actual=client.normalize({'item':{'code':'1','name':'A'},'value':0})
        self.assertEqual(actual['potential'],0)
        self.assertIsNone(actual['baseline'])
        self.assertIsNone(actual['unrealized'])

    def test_rejects_invalid_numbers_and_paths(self):
        with self.assertRaises(client.SourceError):
            client.normalize({'item':{'code':'1','name':'A'},'value':float('nan')})
        with self.assertRaises(ValueError):
            client.chart_path('markets','../../secrets','w','a','i','j','a')
        with self.assertRaises(ValueError):
            client.chart_path('markets','682','w','a','i','g','a')

    def test_source_changes_fail_without_estimation(self):
        for text in ('<html>Sign in</html>','[]','AAAA'):
            with self.assertRaises(client.SourceError):
                client.decode_public_response(text)
        with patch.object(client,'read',return_value=([{'item':{'code':'1','name':'A'}}]*2,{})):
            with self.assertRaises(client.SourceError):
                client.chart(axis='markets',exporter='682',market='w',product='a',from_marker='i',to_marker='j',what_marker='a')

    def test_download_preserves_values_and_checks_source_revision(self):
        import csv, io
        from fastapi import HTTPException
        from export_potential.routes import mount
        class TestApp:
            def get(self,*args,**kwargs):
                return lambda f:f
            def include_router(self,router):
                self.routes=router.routes
        app=TestApp()
        mount(app)
        endpoint = next(r.endpoint for r in app.routes if r.path=='/export-potential/download')
        row = client.normalize({'item':{'code':'080410','name':'=untrusted label'},'value':12.34567,'exportValue':0,'realizedPotential':0})
        sample={'rows':[row],'provenance':{'source_url':'https://exportpotential.intracen.org/api/en/test','retrieved_at':'2026-09-12','response_sha256':'verified'}}
        with patch.object(client,'chart',return_value=sample),patch.object(client,'period_info',return_value={'target_year':2030,'trade_years':'2020–2024'}):
            response=endpoint(axis='products',ids='080410',expected='verified')
            parsed=list(csv.DictReader(io.StringIO(response.body.decode('utf-8-sig'))))
            self.assertEqual(parsed[0]['code'],'080410')
            self.assertEqual(parsed[0]['potential_usd'],'12.34567')
            self.assertEqual(parsed[0]['baseline_exports_usd'],'0')
            self.assertEqual(parsed[0]['name_en'],"'=untrusted label")
            with self.assertRaises(HTTPException) as failure:
                endpoint(axis='products',ids='080410',expected='changed')
            self.assertEqual(failure.exception.status_code,409)

if __name__=='__main__':
    unittest.main()
