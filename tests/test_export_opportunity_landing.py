"""Static contracts for the public export opportunity acquisition path."""
from pathlib import Path
import unittest
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


class LandingOpportunityTests(unittest.TestCase):
    def test_preview_blocks_duplicate_requests_and_honors_retry_after(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node unavailable')
        source = (ROOT / 'web/marketing.js').read_text(encoding='utf-8')
        source = source[source.index('var _opportunityPreviewData'):source.index('/* ═══ الظهور بالتمرير')]
        harness = r'''
const assert = require('node:assert/strict');
var LANG='en', timer;
class E {constructor(){this.value='';this.handlers={};this.children=[];this.classList={add(){}};}
 addEventListener(k,f){this.handlers[k]=f;} appendChild(e){this.children.push(e);} focus(){} }
const ids=Object.fromEntries(['opportunityForm','opportunityHs','opportunityStatus','opportunitySubmit','opportunityResult','opportunityProduct','opportunityMarkets','opportunityLogin','opportunitySignup'].map(k=>[k,new E()]));
const document={getElementById:k=>ids[k],createElement:()=>new E()};
const setInterval=f=>{timer=f;return 1;},clearInterval=()=>{};
let resolve, calls=0;
const fetch=url=>url.includes('/preview?')?(calls++,new Promise(r=>resolve=r)):Promise.resolve({});
const flush=()=>new Promise(r=>setImmediate(r));
''' + source + r'''
(async()=>{
 const submit=()=>ids.opportunityForm.handlers.submit({preventDefault(){}});
 ids.opportunityHs.value='010121';submit();submit();assert.equal(calls,1);
 resolve({ok:true,json:async()=>({product:{hs_code:'010121',name:'Horses',grouped:true,itc_code:'0101',itc_name:'Live equine animals'},markets:[]})});await flush();
 assert.match(ids.opportunityProduct.textContent,/0101/);assert.match(ids.opportunityLogin.href,/010121/);
 submit();assert.equal(calls,1,'Immediate repeat uses bounded recent preview');
 ids.opportunityHs.value='080410';submit();
 resolve({ok:false,status:429,headers:{get:()=> '37'},json:async()=>({})});await flush();
 assert.equal(ids.opportunitySubmit.disabled,true);assert.match(ids.opportunityStatus.textContent,/37/);
 submit();assert.equal(calls,2,'Cooldown prevents additional requests');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run([node, '-'], input=harness, text=True, encoding='utf-8', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_landing_preview_is_branded_bilingual_and_value_free(self):
        html = (ROOT / 'web/platform-landing.html').read_text(encoding='utf-8')
        js = (ROOT / 'web/marketing.js').read_text(encoding='utf-8')
        self.assertIn('id="opportunityForm"', html)
        self.assertIn('src="/silk-logo.png"', html)
        self.assertIn('pattern="[0-9]{6}"', html)
        self.assertIn('سجّل لرؤية القيم بالدولار الأمريكي', html)
        self.assertIn('opTitle:', js)
        self.assertIn('/platform/export-opportunities/preview?hs_code=', js)
        self.assertIn('opportunity_hs=', js)
        self.assertNotIn('market.potential', js)

    def test_platform_restores_landing_product_intent(self):
        platform = (ROOT / 'web/platform.html').read_text(encoding='utf-8')
        opportunities = (ROOT / 'web/platform-opportunities.js').read_text(encoding='utf-8')
        self.assertIn('handleOpportunityReturn()', platform)
        self.assertIn('query.get("opportunity_hs")', platform)
        self.assertIn('openProduct(match.id)', platform)
        self.assertIn('async function openProduct(pid)', opportunities)


if __name__ == '__main__': unittest.main()

