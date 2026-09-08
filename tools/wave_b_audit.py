"""تدقيقٌ بعديٌّ موجَّه على بنود الموجة B — على **المسار الحيّ** لا بالقراءة."""
import json, os, sys, tempfile
from unittest.mock import patch
sys.path.insert(0,"/home/user/Silk-market-intelligence")
sys.path.insert(0,"/home/user/Silk-market-intelligence/tools")
from audit_call_probe import _fake_call_tools, _fake_call, _fake_call_writer
from fastapi.testclient import TestClient
import api

R = []
def chk(bid, ok, detail):
    R.append((bid, bool(ok), detail))

db = os.path.join(tempfile.mkdtemp(), "silk.db")
with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "probe", "SILK_API_KEY": "secret"}), \
     patch("silk_llm_runtime._call_tools", side_effect=_fake_call_tools), \
     patch("silk_synthesis._call", side_effect=_fake_call), \
     patch("silk_ai_judge._call", side_effect=_fake_call_writer), \
     patch("silk_storage._db_path", return_value=db):
    c = TestClient(api.app); H={"X-API-Key":"secret"}
    r = c.post("/research", headers=H, json={"product":"تمور","market":"Netherlands",
              "hs_code":"080410","persist":True,"async_run":False})
    b = r.json(); aid = b.get("analysis_id")
    v = b["view"]; dr = v["deep_research"]; g = dr.get("quality_gate") or {}

    chk("V-01", dr.get("verdict_tone") in ("data_complete","data_partial","data_absent"),
        f"tone={dr.get('verdict_tone')} label={dr.get('verdict_label')}")
    chk("V-01b", "توصية" not in str(dr.get("verdict_label")),
        f"label={dr.get('verdict_label')}")
    checks = {f["check"] for f in (g.get("findings") or [])}
    chk("T-01", "source_coverage_below_threshold" in checks,
        f"gate={g.get('verdict')} checks={sorted(checks)}")
    # البوّابةُ الحاجزة على سطح المشغّل تمنع فعلاً
    rd = c.get(f"/analyses/{aid}/report.docx", headers=H)
    chk("G-01a", rd.status_code == 409, f"operator docx -> {rd.status_code}")
    chk("G-08", isinstance(g.get("skipped_checks"), list), f"{g.get('skipped_checks')}")

import silk_quality_gate as Q, silk_source_coverage as C, silk_export_gate as EG
ar_only = {x[0] for x in Q._AR_ONLY_CHECKS}
chk("G-06", not (ar_only & set(Q.FAIL_TRIGGER_CHECKS)),
    f"blocking-skipped={sorted(ar_only & set(Q.FAIL_TRIGGER_CHECKS))}")
chk("T-01b", C.compute_source_coverage({"missions":{}})["pct"] == 0.0, "zero-evidence pct")
chk("G-02", callable(getattr(EG,"client_quality_summary",None)), "summary fn")
chk("G-04", "engine_unavailable" not in EG.factory_detail([], "ar")["message"], "client wording")

import silk_trace, importlib
_s = os.environ.get("SILK_TRACE_DIR"); os.environ.pop("SILK_TRACE_DIR", None)
os.environ["SILK_DATA_DIR"]="/data"; importlib.reload(silk_trace)
chk("T-06", silk_trace._default_dir()=="/data/traces", silk_trace._default_dir())
os.environ.pop("SILK_DATA_DIR")
if _s: os.environ["SILK_TRACE_DIR"]=_s
importlib.reload(silk_trace)

import silk_i18n
chk("T-07", "خضعت كل معلومة للتحقّق" not in silk_i18n.TERMS["methodology_paragraph"]["ar"]
        and "Every figure was verified" not in silk_i18n.TERMS["methodology_paragraph"]["en"], "no unearned promise")
rep = open("/home/user/Silk-market-intelligence/silk_reports.py",encoding="utf-8").read()
chk("T-11", rep.count("_client_confidence_section(doc, dr, lang)")==1, "called once")
from silk_reports import _economics_md_lines
chk("E-03", bool(_economics_md_lines({"economics":{"reverse_solve":{},"gaps":["ف"]}})), "gaps survive")
src_pl = open("/home/user/Silk-market-intelligence/silk_plausibility.py",encoding="utf-8").read()
chk("X-01", 'if action() == "drop":\n        return []' not in src_pl, "drop no longer mutes")
chk("D-02", Q.DIRECTIVE_AUDIT_CHECKS["19-قاعدة القرار قبل الحكم"][1] != "بنيوي", "registry corrected")
chk("R-02", callable(getattr(Q,"_check_curated_reference_consulted",None)), "guard exists")
br = open("/home/user/Silk-market-intelligence/silk_platform/engine_bridge.py",encoding="utf-8").read()
_body = br.split("def _run_engine(")[1].split("\ndef ")[0]
chk("R-06", "with_requirements=True" in _body, "quick mode keeps regulatory")
gen = open("/home/user/Silk-market-intelligence/tools/gen_research_sample.py",encoding="utf-8").read()
chk("E2", gen.count("if _WRITE:")==2, "sample writes guarded")
import silk_llm_runtime as rt
chk("T-03", rt._parse_output(json.dumps({"findings":[],"gaps":[],"summary":"س"}),{}).get("summary_uncited") is True, "summary flagged")

print("="*66)
bad=[x for x in R if not x[1]]
for bid, ok, d in R:
    print(f"{'✓' if ok else '✗'} {bid:<8} {d}")
print("="*66)
print(f"{len(R)-len(bad)}/{len(R)} اجتاز")
sys.exit(1 if bad else 0)
