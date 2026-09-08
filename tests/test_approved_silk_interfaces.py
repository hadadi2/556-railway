"""تصميم المالك: اختيار ملفات الدراسات لا يفقد الأفعال أو يخلط بياناتها."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pathlib
import re
import shutil
import subprocess
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_initial_navigation_uses_role_default_and_keeps_explicit_selection():
    if not shutil.which('node'):
        pytest.skip('Node required for navigation behavior')
    page = (ROOT/'web/platform.html').read_text()
    show = page[page.index('function showSection('):page.index('const NAV_ICONS')]
    build = page[page.index('function buildNav('):page.index('function navButton(')]
    script = r'''
const assert=require('node:assert/strict');
class E {
  constructor(){this.children=[];this.dataset={};this.className='';this.classList={toggle(){},remove(){}};}
  set textContent(v){this.children=[];this.value=v;}
  appendChild(e){this.children.push(e);return e;}
  setAttribute(){} removeAttribute(){}
}
const elements={};const $=id=>elements[id]||(elements[id]=new E());
const document={createElement:()=>new E()};const ar_en=(ar,en)=>en;
const NAV_GROUPS=[];
const SECTIONS=[{key:'home',panel:'homePanel',role:'factory'}, {key:'studies',panel:'studiesPanel',role:'factory'}, {key:'overview',panel:'adminHomePanel',role:'silk_admin'}];
let ME={role:'factory'},SECT=null;
const visibleSections=()=>SECTIONS.filter(x=>x.role===ME.role);
const navButton=x=>Object.assign(new E(),{dataset:{key:x.key}});
''' + show + build + r'''
buildNav();assert.equal(SECT,'studies','New factory session must open the approved studies workspace');
SECT='home';buildNav();assert.equal(SECT,'home','Keep a factory section selected by the user');
ME={role:'silk_admin'};SECT=null;buildNav();assert.equal(SECT,'overview');
'''
    result=subprocess.run(['node','-'],input=script,text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_folder_selection_preserves_actions_filters_and_plain_text():
    if not shutil.which("node"):
        pytest.skip("Node is required for the JavaScript behavior check")
    page = (ROOT / "web/platform.html").read_text()
    source = page[page.index('let SELECTED_STUDY ='):page.index('function mkBtn(')]
    harness = r'''
const assert = require('node:assert/strict');
class Element {
  constructor(tag='div') { this.tag=tag; this.children=[]; this.dataset={}; this.attrs={}; this.value=''; this.hidden=false;
    this.classList={toggle:(key,on)=>{if(key==='hide')this.hidden=on;}}; }
  set textContent(v){this.value=String(v);this.children.forEach(x=>x.parent=null);this.children=[];}
  get textContent(){return this.value+this.children.map(x=>x.textContent).join('');}
  appendChild(x){if(x.parent)x.parent.children=x.parent.children.filter(y=>y!==x);x.parent=this;this.children.push(x);return x;}
  append(...xs){xs.forEach(x=>this.appendChild(x));}
  setAttribute(k,v){this.attrs[k]=v;}
  get lastElementChild(){return this.children.at(-1);}
  querySelectorAll(q){const match=x=>q==='button'?x.tag==='button':q==='button, a'?['button','a'].includes(x.tag):q==='.foot'?x.className==='foot':false;
    return this.children.flatMap(x=>[...(match(x)?[x]:[]),...x.querySelectorAll(q)]);}
  cloneNode(){const x=new Element(this.tag);x.className=this.className;x.textContent=this.textContent;return x;}
  focus(){document.activeElement=this;}
}
const hosts=Object.fromEntries(['studiesPanel','studyFolders','studyInspector','studiesBody','studyWorkspace','studyTable','studyViewBtn'].map(k=>[k,new Element()]));
const $=id=>hosts[id];
const document={activeElement:null,createElement:tag=>new Element(tag)};
const ar_en=(ar,en)=>en;
const studyChip=s=>({text:s.state});
const _durText=s=>s.duration||'—';
let calls=[];
const actionA=new Element('button'),actionB=new Element('button');
actionA.textContent='Launch'; actionA.onclick=()=>calls.push('A');
actionB.textContent='Report'; actionB.onclick=()=>calls.push('B');
function seedTable(actions) {
  hosts.studiesBody.textContent='';
  actions.forEach((action,i)=>{const tr=new Element('tr');tr.append(new Element('td'),new Element('td'),new Element('td'));
    if(i===0){const warning=new Element();warning.className='foot';warning.textContent='Product code changed';tr.children[1].append(warning);}
    tr.lastElementChild.append(action);hosts.studiesBody.append(tr);});
}
const a={id:1,product:'<img src=x onerror=bad()>',market_pref:'Netherlands',state:'draft'};
const b={id:2,product:'Coffee',market_pref:'UAE',state:'completed',hs_code:'090111'};
let currentRows=[a,b];
function renderStudyRows(){seedTable(currentRows.map(s=>s.id===1?actionA:actionB));renderStudyWorkspace(currentRows);}
'''
    checks = r'''
renderStudyRows();
assert.equal(hosts.studyFolders.children.length,2);
assert.equal(hosts.studyFolders.children[0].children[0].textContent,a.product);
assert.equal(hosts.studyFolders.children[0].children[0].children.length,0,'Product name must remain text');
assert.match(hosts.studyInspector.textContent,/Product code changed/);
assert.ok(hosts.studyInspector.querySelectorAll('button').includes(actionA));
hosts.studyFolders.children[1].onclick();
assert.match(hosts.studyInspector.textContent,/Coffee/);
assert.doesNotMatch(hosts.studyInspector.textContent,/Product code changed/);
assert.equal(hosts.studyFolders.children.filter(x=>x.attrs['aria-pressed']==='true').length,1);
hosts.studyInspector.querySelectorAll('button')[0].onclick();
assert.deepEqual(calls,['B']);
hosts.studyFolders.children[0].onclick();
assert.ok(hosts.studyInspector.querySelectorAll('button').includes(actionA),'Returning to a folder retains its original handler');
hosts.studyViewBtn.onclick();
assert.equal(hosts.studyTable.hidden,false);
assert.equal(hosts.studyWorkspace.hidden,true);
assert.equal(hosts.studiesBody.querySelectorAll('button').length,2,'Table view restores every action');
hosts.studyViewBtn.onclick();
currentRows=[b];renderStudyRows();
assert.equal(SELECTED_STUDY,'2','Filtering must not expose a hidden study');
assert.doesNotMatch(hosts.studyInspector.textContent,/Netherlands/);
currentRows=[];renderStudyRows();
assert.equal(SELECTED_STUDY,null);
assert.equal(hosts.studyInspector.textContent,'');
assert.equal(hosts.studyWorkspace.hidden,true);
currentRows=[a,b];renderStudyRows();
clearStudyWorkspace(true);
assert.equal(hosts.studyInspector.textContent,'');
assert.equal(hosts.studiesPanel.attrs['aria-busy'],'true');
clearStudyWorkspace();
assert.equal(hosts.studyFolders.textContent,'');
assert.equal(hosts.studiesPanel.attrs['aria-busy'],'false');
'''
    result = subprocess.run(['node', '-e', harness+source+checks], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_pages_have_valid_scripts_unique_ids_and_shared_logo():
    if not shutil.which('node'):
        pytest.skip('Node is required for the JavaScript syntax check')
    for name in ('platform.html', 'platform-landing.html'):
        page = (ROOT / 'web' / name).read_text()
        # Limit IDs to actual markup; templates may intentionally repeat modal IDs.
        markup = page.split('<script>')[0]
        ids = re.findall(r'\bid="([^"\s]+)"', markup)
        assert len(ids) == len(set(ids)), name
        assert 'src="/silk-logo.png"' in markup
        for script in re.findall(r'<script>(.*?)</script>', page, re.S):
            result = subprocess.run(['node', '--check'], input=script, text=True, capture_output=True)
            assert result.returncode == 0, result.stderr
    assert (ROOT / 'web/silk-logo.png').read_bytes().startswith(b'\x89PNG')


def test_admin_metrics_keep_real_values_without_duplicates():
    if not shutil.which('node'):
        pytest.skip('Node is required for the JavaScript behavior check')
    page = (ROOT / 'web/platform.html').read_text()
    source = page[page.index('function renderKpis('):page.index('const _SVG_NS')]
    script = r'''
const assert=require('node:assert/strict');
class Host {
  constructor(){this.children=[];}
  set textContent(v){this.children=[];}
  appendChild(x){if(x.parent)x.parent.children=x.parent.children.filter(y=>y!==x);x.parent=this;this.children.push(x);}
}
const hosts={kpiGrid:new Host(),adminActivity:new Host()};
const $=id=>hosts[id], ar_en=(ar,en)=>en, _kpi=(label,value,foot)=>({label,value,foot});
''' + source + r'''
renderKpis({factory_accounts:9,active_studies:0,launched_this_month:4,completed_this_month:3,total_users:12,checkout_requests_this_month:2});
assert.deepEqual(hosts.kpiGrid.children.map(x=>x.value),['9','0','4']);
assert.deepEqual(hosts.adminActivity.children.map(x=>x.value),['3','12','2']);
assert.equal(new Set([...hosts.kpiGrid.children,...hosts.adminActivity.children].map(x=>x.label)).size,6);
renderKpis({});
assert.equal(hosts.kpiGrid.children.length,3);assert.equal(hosts.adminActivity.children.length,3);
assert.ok([...hosts.kpiGrid.children,...hosts.adminActivity.children].every(x=>x.value==='—'));
'''
    result = subprocess.run(['node','-e',script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
