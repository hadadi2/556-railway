"""أقفال متابعة المالك: تصنيف الصورة ولغة التقارير. Offline owner regressions."""
import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("tier", ["auto", "candidates", "manual"])
def test_study_image_flow_never_exposes_candidate_lists_or_confidence(monkeypatch, tier):
    import silk_product_intake as intake
    import silk_hs_classifier as classifier
    from silk_platform import engine_bridge as eb
    monkeypatch.setenv("SILK_IMAGE_INTAKE", "1")
    monkeypatch.setattr(eb, "_vision_allowed", lambda: (True, ""))
    monkeypatch.setattr(intake, "intake_image", lambda *a, **kw: {
        "ok": True, "product_name": "حلاوة طحينية",
        "extraction": {"ingredients": ["سمسم", "سكر"], "confidence": 0.99}})
    monkeypatch.setattr(classifier, "classify_general", lambda *a, **kw: {
        "tier": tier, "hs6": "170490" if tier == "auto" else None,
        "confidence": 0.95, "candidates": [{"hs6": "170490"}], "source": "test"})
    out = eb.classify_image_flow(b"\x89PNG\r\n\x1a\nabc", "image/png")
    assert out["ok"] is (tier == "auto")
    assert out.get("hs6") == ("170490" if tier == "auto" else None)
    assert not any(k in json.dumps(out) for k in ('"confidence"', '"candidates"', '"tier"'))


@pytest.mark.parametrize("url", ["https://source.example/CAGR?series=SAM#HHI",
                                  "https://source.example/CAGR_(SAM)",
                                  "http://[::1]/CAGR_(SAM)"])
def test_plain_language_simplifies_cited_arabic_without_changing_url(url):
    from silk_reports import _plain_language
    out = _plain_language("بلغ CAGR نحو 12% وفق " + url + " ويظل نمو CAGR مهماً")
    assert "متوسط النمو السنوي" in out
    assert "12%" in out and url in out
    assert "نمو CAGR" not in out


@pytest.mark.parametrize("edited_during_request", [False, True])
def test_photo_classification_never_overwrites_a_factory_code(edited_during_request):
    if not shutil.which("node"):
        pytest.skip("Node unavailable")
    page = (ROOT / "web/platform.html").read_text()
    fn = page[page.index("async function _classifyInto("):page.index("function _studyFormHtml(")]
    script = '''
const assert = require('node:assert/strict');
let resolve;
let calls = 0;
const api = async () => { calls++; return new Promise(r => resolve = r); };
const ar_en = (ar,en) => ar;
const fields = {image_id:{value:'1'}, hs_code:{value:INITIAL}, product:{value:'اسم المصنع'}};
const veil = {querySelector(s) { return fields[s.match(/name="([^"]+)"/)[1]]; }};
const val = (v,n) => fields[n].value;
''' .replace("INITIAL", "''" if edited_during_request else "'170490'") + fn + '''
(async () => {
 const pending = _classifyInto(veil, {textContent:''});
 if (calls) { fields.hs_code.value='170490'; resolve({ok:true,hs6:'200819',product_name:'اسم آخر'}); }
 await pending;
 assert.equal(fields.hs_code.value,'170490');
 assert.equal(fields.product.value,'اسم المصنع');
})().catch(e => {console.error(e);process.exitCode=1;});
'''
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert out.returncode == 0, out.stderr


def test_photo_classification_preserves_a_product_name_edited_in_flight():
    if not shutil.which("node"):
        pytest.skip("Node unavailable")
    page = (ROOT / "web/platform.html").read_text()
    fn = page[page.index("async function _classifyInto("):page.index("function _studyFormHtml(")]
    script = '''
const assert = require('node:assert/strict');
let resolve;
const api = () => new Promise(r => resolve = r);
const ar_en = (ar,en) => ar;
const fields = {image_id:{value:'1'}, hs_code:{value:''}, product:{value:''}};
const veil = {querySelector(s) { return fields[s.match(/name="([^"]+)"/)[1]]; }};
const val = (v,n) => fields[n].value;
''' + fn + '''
(async () => {
 const pending = _classifyInto(veil, {textContent:''});
 fields.product.value='منتج مختلف كتبه المصنع';
 resolve({ok:true,hs6:'170490',product_name:'حلاوة'});
 await pending;
 assert.equal(fields.product.value,'منتج مختلف كتبه المصنع');
 assert.equal(fields.hs_code.value,'');
})().catch(e => {console.error(e);process.exitCode=1;});
'''
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert out.returncode == 0, out.stderr


def test_replacing_a_photo_ignores_the_older_upload_response():
    if not shutil.which("node"):
        pytest.skip("Node unavailable")
    page = (ROOT / "web/platform.html").read_text()
    fn = page[page.index("function _wireStudyForm("):page.index("function _studyBody(")]
    script = '''
const assert = require('node:assert/strict');
const pending = new Map(), classified = [];
let change;
const file = {files:[],value:'',addEventListener(name,cb) {change=cb;}};
const image = {value:''}, status = {textContent:''}, button = {disabled:false};
const veil = {querySelector(s) {
 return {'[name="image_file"]':file,'[name="image_id"]':image,
         '[data-role="classify-status"]':status,'[data-act="classify"]':button}[s];
}};
const ar_en = (ar,en) => ar;
const _wireCostUnitHint = () => {};
const _markets = async () => [];
const _classifyInto = async () => {classified.push(image.value);};
const uploadImage = f => new Promise(r => pending.set(f.name,r));
''' + fn + '''
(async () => {
 _wireStudyForm(veil, null);
 file.files=[{name:'old'}]; const old=change();
 file.files=[{name:'new'}]; const current=change();
 pending.get('new')({id:2}); await current;
 pending.get('old')({id:1}); await old;
 assert.equal(image.value,2);
 assert.deepEqual(classified,[2]);
 assert.equal(button.disabled,false);
})().catch(e => {console.error(e);process.exitCode=1;});
'''
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert out.returncode == 0, out.stderr
