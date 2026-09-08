"""مصدر رمز المصنع يبقى محفوظاً، ولا يُستنتج من إعادة حفظ رمز قديم.

Explicit factory provenance survives persistence and reaches the real bridge.
"""
import pathlib
import subprocess

import pytest

from tests.platform_helpers import hdr
from tests.test_platform_deep_mode import (
    env, _mk_study, _study_row, _register_gateway, _deep_result,
)


@pytest.mark.parametrize("source,expected", [("manual", "manual"), (None, "catalog")])
def test_direct_factory_source_reaches_deep_gateway(env, monkeypatch, source, expected):
    from silk_platform import engine_bridge as eb
    calls = []
    _register_gateway(monkeypatch, lambda **kw: (calls.append(kw) or _deep_result()))
    fields = {"hs_code": "080410", "market_pref": "ARE"}
    if source:
        fields["hs_source"] = source
    study = _mk_study(env["cl"], env["tok"], **fields)
    response = env["cl"].post(f"/platform/studies/{study['id']}/launch",
                              headers=hdr(env["tok"]))
    assert response.status_code == 200, response.text
    assert eb.wait_idle()
    assert calls[0]["hs_source"] == expected


@pytest.mark.parametrize("change,expected", [
    ({"description_ar": "تعديل الوصف"}, "manual"),
    ({"hs_code": "080410"}, "manual"),
    ({"hs_code": "170490"}, "unknown"),
    ({"hs_code": None}, "unknown"),
    ({"product": "حلاوة طحينية"}, "unknown"),
    ({"product": "حلاوة طحينية", "hs_code": "170490", "hs_source": "manual"}, "manual"),
])
def test_manual_provenance_is_invalidated_only_when_its_product_or_code_changes(env, change, expected):
    study = _mk_study(env["cl"], env["tok"], hs_code="080410", hs_source="manual")
    response = env["cl"].patch(f"/platform/studies/{study['id']}", json=change,
                               headers=hdr(env["tok"]))
    assert response.status_code == 200, response.text
    assert _study_row(study["id"])["hs_source"] == expected


def test_resaving_legacy_code_does_not_invent_factory_confirmation(env):
    study = _mk_study(env["cl"], env["tok"], hs_code="080410")
    response = env["cl"].patch(f"/platform/studies/{study['id']}",
                               json={"hs_code": "080410", "product": "تمور سكري"},
                               headers=hdr(env["tok"]))
    assert response.status_code == 200
    assert _study_row(study["id"])["hs_source"] == "unknown"


@pytest.mark.parametrize("body", [
    {"hs_source": "image", "hs_code": "080410"},
    {"hs_source": "manual"},
    {"hs_source": "manual", "hs_code": None},
])
def test_client_cannot_claim_image_proof_or_confirm_an_unspecified_code(env, body):
    response = env["cl"].post("/platform/studies", json={"product": "تمور", **body},
                              headers=hdr(env["tok"]))
    assert response.status_code == 422


def test_manual_form_source_and_old_classify_button_completion_are_fenced():
    page = (pathlib.Path(__file__).resolve().parent.parent / "web/platform.html").read_text()
    functions = page[page.index("function _wireStudyForm("):page.index("function studyDialog(")]
    script = r'''
const assert = require('node:assert/strict');
const listeners = {};
const hs = {value:'080410',addEventListener(k,fn){listeners.hs=fn;}};
const product = {value:'dates',addEventListener(k,fn){listeners.product=fn;}};
const file = {files:[],addEventListener(k,fn){listeners.file=fn;}};
const button = {disabled:false}, status = {};
const fields = {hs_code:hs, product, image_file:file, image_id:{value:'1'}};
const veil = {querySelector(s){
 if(s==='[data-act="classify"]') return button;
 if(s==='[data-role="classify-status"]') return status;
 const m=s.match(/name="([^"]+)"/); return m ? fields[m[1]] : null;
}};
const val=(v,k)=>fields[k]?.value || '';
const orNull=x=>x || null;
const ar_en=(a,b)=>a;
const _wireCostUnitHint=()=>{};
const _markets=async()=>[];
let resolveRead,resolveUpload;
const _classifyInto=()=>new Promise(r=>resolveRead=r);
const uploadImage=()=>new Promise(r=>resolveUpload=r);
''' + functions + r'''
(async()=>{
 _wireStudyForm(veil,{hs_code:'080410',product:'dates',hs_source:'unknown'});
 assert.notEqual(_studyBody(veil).hs_source,'manual');
 hs.value='170490'; listeners.hs();
 assert.equal(_studyBody(veil).hs_source,'manual');
 product.value='another product'; listeners.product();
 assert.notEqual(_studyBody(veil).hs_source,'manual');
 button.onclick();
 const oldRead=resolveRead;
 file.files=[{name:'new'}]; const upload=listeners.file();
 oldRead(); await new Promise(r=>setImmediate(r));
 assert.equal(button.disabled,true,'old manual request enabled the new upload button');
 resolveUpload({id:2}); await new Promise(r=>setImmediate(r));
 resolveRead(); await upload;
 assert.equal(button.disabled,false);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
