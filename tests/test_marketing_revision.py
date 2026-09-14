"""تصحيح الواجهات: مرجع المالك، صفحة أسعار واحدة المصدر، ومخرجات صادقة."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pathlib
import re
import shutil
import subprocess
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_shared_prices_handle_cycles_features_loading_and_failure():
    if not shutil.which('node'):
        pytest.skip('Node required for marketing runtime check')
    js = (ROOT/'web/marketing.js').read_text()
    dictionaries = js[js.index('var L_EN ='):js.index('var LANG =')]
    renderer = js[js.index('function txt('):js.index('if (document.getElementById("plansGrid"))')]
    script = r'''
const assert=require('node:assert/strict');
class E {
  constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this.value='';this.classList={add(){},remove(){},toggle(){}};}
  appendChild(x){this.children.push(x);return x;}
  set textContent(v){this.children=[];this.value=String(v);}
  get textContent(){return this.value+this.children.map(x=>x.textContent).join(' ');}
  setAttribute(k,v){this.attrs[k]=v;}
}
const ids={plansGrid:new E(),pricingMsg:new E(),billMonthly:new E(),billAnnual:new E()};
const document={getElementById:id=>ids[id],createElement:tag=>new E(tag)};
var LANG='ar',_cycle='monthly';
''' + dictionaries + renderer + r'''
renderPlans(undefined);assert.match(ids.pricingMsg.textContent,/جارٍ تحميل/);
const data={annual_discount_pct:17,tiers:[
{key:'basic',price:0,lifetime_studies:1,dashboard:'none'},
{key:'gold',price:101,price_annual:1010,monthly_studies:6,dashboard:'full',export:true}]};
renderPlans(data);
assert.equal(ids.plansGrid.children.length,2);
assert.match(ids.plansGrid.children[0].textContent,/دراسة تجريبية واحدة/);
assert.match(ids.plansGrid.children[1].textContent,/لوحة متابعة متكاملة/);
assert.equal(ids.plansGrid.children[1].children.at(-1).href,'/checkout.html?plan=gold');
_cycle='annual';renderPlans(data);
assert.match(ids.plansGrid.children[1].textContent,/84.17/,'Do not truncate the monthly equivalent');
assert.match(ids.plansGrid.children[1].textContent,/1,010/);
assert.equal(ids.plansGrid.children[1].children.at(-1).href,'/checkout.html?plan=gold&cycle=annual');
assert.equal(ids.plansGrid.children[0].children.at(-1).href,'/checkout.html?plan=basic');
LANG='en';renderPlans(data);assert.match(ids.plansGrid.children[1].textContent,/Full dashboard/);
renderPlans(null);assert.equal(ids.plansGrid.children.length,0);assert.match(ids.pricingMsg.textContent,/Could not load/);
delete ids.plansGrid;assert.doesNotThrow(()=>renderPlans(data),'Landing has no prices container');
'''
    result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_marketing_pages_share_runtime_and_have_complete_local_links():
    script=(ROOT/'web/marketing.js').read_text()
    translations=set(re.findall(r'^  (\w+):',script,re.M))
    for filename in ['platform-landing.html','pricing.html']:
        text=(ROOT/'web'/filename).read_text()
        assert len(re.findall(r'src="/marketing\.js(?:\?[^"]*)?"', text)) == 1
        assert re.search(
            r'<a class="brand" href="/platform-landing\.html">\s*<img[^>]+alt="SILK"',
            text)
        assert 'الإمارات' not in text
        assert '15 دقيقة' not in text
        keys=set(re.findall(r'data-i18n="(\w+)"',text))
        assert keys<=translations,keys-translations
        ids=re.findall(r'\bid="([^"]+)"',text)
        assert len(ids)==len(set(ids))
        for fragment in re.findall(r'href="#([^"]+)"',text):
            assert fragment in ids,fragment
        for asset in re.findall(r'(?:src|href)="(/[^"?#]+\.(?:png|js|css|html))',text):
            assert (ROOT/'web'/asset.lstrip('/')).is_file(),asset
    result=subprocess.run(['node','--check',str(ROOT/'web/marketing.js')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    pricing=(ROOT/'web/pricing.html').read_text()
    assert '.pricing-page .plans{grid-template-columns:repeat(3,' in pricing


def test_pricing_page_and_assets_are_publicly_served(monkeypatch):
    from fastapi.testclient import TestClient
    import api
    with TestClient(api.create_app()) as cl:
        for url,content_type in [('/pricing.html','text/html'),('/marketing.js','javascript'),('/research-motion.css','text/css'),('/silk-approved-preview.png','image/png')]:
            response=cl.get(url)
            assert response.status_code==200,url
            assert content_type in response.headers['content-type']


def test_research_motion_pauses_for_user_visibility_and_reduced_motion():
    if not shutil.which('node'):
        pytest.skip('Node required for motion-control check')
    js = (ROOT/'web/marketing.js').read_text()
    motion = js[js.index('(function researchMotion()'):js.index('/* ═══ الباقات —')]
    harness = r'''
const assert = require('node:assert/strict');
const scene = {attrs:{},setAttribute(k,v){this.attrs[k]=v;}};
const button = {attrs:{},setAttribute(k,v){this.attrs[k]=v;},hidden:true};
let onPreference, onVisibility, onIntersection;
const preference = {matches:false,addEventListener(type,fn){onPreference=fn;}};
const document = {hidden:false,getElementById(id){return id==='researchMotion'?scene:button;},addEventListener(type,fn){onVisibility=fn;}};
class IntersectionObserver {constructor(fn){onIntersection=fn;} observe(){}}
const window = {matchMedia(){return preference;},IntersectionObserver};
''' + motion + r'''
assert.equal(scene.attrs['data-motion'],'playing');
assert.equal(button.hidden,false);
button.onclick();assert.equal(scene.attrs['data-motion'],'paused');
onIntersection([{isIntersecting:false}]);onIntersection([{isIntersecting:true}]);
assert.equal(scene.attrs['data-motion'],'paused','Scrolling must preserve manual pause');
button.onclick();assert.equal(scene.attrs['data-motion'],'playing');
document.hidden=true;onVisibility();assert.equal(scene.attrs['data-motion'],'paused');
document.hidden=false;onVisibility();assert.equal(scene.attrs['data-motion'],'playing');
preference.matches=true;onPreference();assert.equal(scene.attrs['data-motion'],'paused');assert.equal(button.disabled,true);
preference.matches=false;onPreference();assert.equal(scene.attrs['data-motion'],'playing');
'''
    result = subprocess.run(['node','-'],input=harness,text=True,capture_output=True,timeout=10)
    assert result.returncode == 0, result.stderr
