"""أقفال المرحلة ١ (PR-A) — الفحوصات الحتمية F1–F7 + G0 وأداة القياس (الدرس ٢٩٩).

قرار المالك (2026-10-21): الأخطاء نفسها عادت في أربع دراسات مدفوعة لأن الإصلاح كان
في التعليمات لا في الشيفرة. هذه الأقفال تثبت ثلاثة أشياء على الدراسة رقم ١ الحقيقية
(مجمَّدة في tests/golden/fixtures/study_001_bahrain_coffee من Railway عبر MCP):
  ١) كل فحص يمسك خطأه المعروف بعينه (لا FAIL عامّ)؛
  ٢) تصحيحُ ذلك الخطأ وحده يقلب الفحص إلى PASS (الفحص يقيس الخطأ لا يرفض كل شيء)؛
  ٣) الأداة تقرأ كل مصدر (حالة مرجعية، قاعدة، خادم بعيد، ملف) وتخرج بالرموز المعلنة،
     وخط الأساس يمسك أي تراجع.
هرمتي: صفر شبكة خارجية (الخادم البعيد خادمٌ محليّ على 127.0.0.1)، صفر نموذج.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import silk_study_checks as C  # noqa: E402

CASE = "study_001_bahrain_coffee"
FIX = os.path.join(ROOT, "tests", "golden", "fixtures", CASE)
RUNNER = os.path.join(ROOT, "tests", "golden", "run_checks.py")
ORIGIN_RULE = (" (بشرط استيفاء قاعدة المنشأ الخليجية: قيمة مضافة لا تقل عن 40% من سعر المصنع، "
               "وملكية خليجية لا تقل عن 51%، وشهادة منشأ)")


def _read(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def _json(name: str) -> dict:
    return json.loads(_read(name))


def _doc(report: "str | None" = None, evidence: "str | None" = None, **meta) -> C.StudyDoc:
    m = _json("meta.json")
    m.update(meta)
    return C.StudyDoc(report=_read("report.md") if report is None else report,
                      evidence=_read("evidence.txt") if evidence is None else evidence,
                      meta=m, expected=_json("expected.json"))


def _runner():
    spec = importlib.util.spec_from_file_location("golden_run_checks", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _blob(f: C.Finding) -> str:
    return json.dumps(f.to_dict(), ensure_ascii=False)


# ── ١) كل فحص يمسك خطأ الدراسة ١ المعروف ─────────────────────────────────────

def test_study1_known_errors_are_each_caught_by_their_check():
    res = {f.check: f for f in C.run_all(_doc())}
    for err in _json("expected.json")["known_errors"]:
        f = res[err["check"]]
        assert f.status == C.FAIL, f"{err['check']} لم يمسك: {err['why']}"
        assert err["text"].split()[0] in _blob(f), (err["check"], err["text"])
    assert res["F6"].status == C.PASS, "النسخة الحالية لا توصي بالبن الأخضر — F6 يجب ألا يخطئ"


def test_f1_flags_tonnes_that_are_kilograms():
    f = C.check_units(_doc())
    bad = [i for i in f.items if i["status"] == C.FAIL]
    assert len(bad) == 1 and "817,876" in bad[0]["quantity"]
    assert bad[0]["reference_usd_per_kg"] == 10.72 and bad[0]["reference_year"] == 2023
    assert "كيلوغرام" in bad[0]["why"], "التلميح يجب أن يسمّي الوحدة الصحيحة"


def test_f2_rejects_instagram_price_below_floor_and_its_reuse_in_prose():
    f = C.check_shelf_prices(_doc())
    floor, basis = C.shelf_floor_local_per_kg(_doc())
    assert floor == pytest.approx(10.72 * 0.376 * 1.10, rel=1e-3)   # ≈ 4.43 د.ب/كغ
    zad = next(i for i in f.items if i.get("pack_kg") and "زاد" in i["product"])
    assert zad["below_floor"] is True and zad["social"] is True
    prose = [i for i in f.items if "pack_kg" not in i and i["status"] == C.FAIL]
    assert any("2.50" in i["row"] for i in prose), "سعر إنستغرام دخل نطاق الأسعار في النثر"
    assert any("أعلى سعر رف" in i["row"] for i in prose), "سعرٌ غير موثق في جدول شروط القرار"
    assert any("6.49" in i.get("why", "") for i in f.items if i["status"] == C.WARN)


def test_f3_flags_unlabelled_divergence_and_mirror_headed_ledger():
    f = C.check_mirror(_doc())
    inds = {i.get("indicator") for i in f.items}
    assert {"الحصة السعودية", "واردات السوق"} <= inds
    ledger = [i for i in f.items if i.get("where") == "سجلّ الحقائق"]
    keys = {i["key"] for i in ledger}
    assert {C.norm_digits(k) for k in ("واردات السوق", "أحدث سنة بيانات للواردات", "نمو الواردات",
                                       "معدل النمو السنوي المركّب")} <= keys
    assert all("دخل الفرد" not in k for k in keys), "دخل الفرد 2025 مباشر — لا يُوسَم"


def test_f4_f5_f7_on_study1():
    assert len(C.check_tariff_claims(_doc()).items) == 5
    f5 = C.check_verdict_basis(_doc())
    assert f5.items[0]["required_label"] == C.SCREENING_LABEL
    f7 = C.check_consistency(_doc())
    assert f7.items[0]["requirement"] == "الحلال"
    assert "5." in f7.items[0]["mandatory"][0]["section"]
    assert "7." in f7.items[0]["optional"][0]["section"]


# ── ٢) تصحيحُ الخطأ وحده يقلب الفحص ───────────────────────────────────────────

def test_f1_passes_when_the_unit_is_kilograms():
    ev = _read("evidence.txt").replace("817,876 طن", "817,876 كيلوغرام")
    assert C.check_units(_doc(evidence=ev)).status == C.PASS


_DOC_TABLE = """## 6. المشهد التنافسي

| المنتج/العلامة | العبوة | سعر التجزئة | السعر لوحدة المقارنة | المتجر وتاريخ الرصد | الرابط |
|---|---|---|---|---|---|
| Italcaffe Espresso Casa حبوب | 500 غرام | 6.490 دينار بحريني | 12.98 دينار بحريني/كجم | Lulu Hypermarket، أكتوبر 2026 | https://example.test/lulu/italcaffe |
| قهوة عربية | 400 غرام | 5.140 دينار بحريني | 12.85 دينار بحريني/كجم | Al Jazira، أكتوبر 2026 | https://example.test/jazira/arabic |
| عيّنة اختبار ١ | 250 غرام | 3.200 دينار بحريني | 12.80 دينار بحريني/كجم | Carrefour، أكتوبر 2026 | https://example.test/carrefour/1 |
| عيّنة اختبار ٢ | 1 كيلوغرام | 9.900 دينار بحريني | 9.90 دينار بحريني/كجم | Talabat Mart، أكتوبر 2026 | https://example.test/talabat/2 |
| عيّنة اختبار ٣ | 200 غرام | 2.100 دينار بحريني | 10.50 دينار بحريني/كجم | محمصة محلية، سبتمبر 2026 | https://example.test/roastery/3 |

تتراوح الأسعار الموثقة بين 9.90 و12.98 دينار بحريني للكيلوغرام.
"""


def test_f2_passes_with_five_documented_prices_above_floor():
    f = C.check_shelf_prices(_doc(report=_DOC_TABLE))
    assert f.status == C.PASS, _blob(f)
    low = _DOC_TABLE.replace("2.100 دينار بحريني | 10.50", "0.700 دينار بحريني | 3.50")
    f = C.check_shelf_prices(_doc(report=low))
    assert f.status == C.FAIL and any(i.get("below_floor") for i in f.items)
    insta = _DOC_TABLE.replace("محمصة محلية، سبتمبر 2026 | https://example.test/roastery/3",
                               "إنستغرام، سبتمبر 2026 | https://instagram.com/p/x")
    f = C.check_shelf_prices(_doc(report=insta))
    assert f.status == C.FAIL and any(i.get("social") for i in f.items)


def _corrected_mirror():
    rep = (_read("report.md")
           .replace("فهو التناقض في الأرقام", "فهو التباين في الأرقام")
           .replace("فلا تجعله أساس حساباتك قبل التأكد منه.",
                    "فلا تجعله أساس حساباتك قبل التأكد منه؛ وهو تباين مع آخر تصريح مباشر.")
           .replace("لكننا كما قلنا نتعامل معه بحذر حتى نتأكد منه.",
                    "وهذا تباين مع بيانات 2023 المباشرة نتعامل معه بحذر."))
    ev = re.sub(r"^سجلّ الحقائق — واردات السوق: .*$",
                "سجلّ الحقائق — واردات السوق: 9.17 مليون دولار (UN Comtrade 2024)",
                _read("evidence.txt"), flags=re.M)
    ev = (ev.replace("أحدث سنة بيانات للواردات: 2025 (UN Comtrade)",
                     "أحدث سنة بيانات للواردات: 2024 (UN Comtrade)")
            .replace("نمو الواردات: 213.1% (UN Comtrade 2025)", "نمو الواردات: 89.9% (UN Comtrade 2024)")
            .replace("معدل النمو السنوي المركّب: 21% (UN Comtrade 2025)",
                     "معدل النمو السنوي المركّب: 13.7% (UN Comtrade 2024)"))
    return rep, ev


def test_f3_passes_when_divergence_is_labelled_and_ledger_is_direct():
    rep, ev = _corrected_mirror()
    f = C.check_mirror(_doc(report=rep, evidence=ev))
    assert f.status == C.PASS, _blob(f)


def test_f3_mirror_figure_banned_in_exec_summary_and_as_first_figure():
    rep, ev = _corrected_mirror()
    rep = rep.replace("التوصية: دخول مشروط إلى سوق البحرين",
                      "التوصية: دخول مشروط إلى سوق وارداتها نحو 15.12 مليون دولار (تباين) في البحرين")
    f = C.check_mirror(_doc(report=rep, evidence=ev))
    assert any(i.get("where") == "القسم 1" for i in f.items)
    rep2, _ = _corrected_mirror()
    rep2 = rep2.replace("## 4. ديناميكيات السوق\n\n",
                        "## 4. ديناميكيات السوق\n\nحصة السعودية 12.02% (تباين).\n\n")
    f = C.check_mirror(_doc(report=rep2, evidence=ev))
    assert any("القسم 4" in str(i.get("where")) for i in f.items)


def _with_origin_rule(rep: str) -> str:
    rep = C.norm_digits(rep)  # الفقرات تُقرأ مطبَّعة (بلا حركات) — الاستبدال على النصّ نفسه
    for p in C.paragraphs(rep):
        if C._EXEMPT_RE.search(p) and p in rep:
            rep = rep.replace(p, p + ORIGIN_RULE)
    return rep


def test_f4_passes_when_every_exemption_carries_the_origin_rule():
    assert C.check_tariff_claims(_doc(report=_with_origin_rule(_read("report.md")))).status == C.PASS
    plain = "## 7. التنظيم\n\nالرسوم الجمركية 0% على المنتج.\n"
    assert C.check_tariff_claims(_doc(report=plain)).status == C.FAIL
    assert C.check_tariff_claims(_doc(report="## 7. التنظيم\n\nرسوم جمركية 5% تجاه الخارج.\n")).status == C.PASS


def test_f5_screening_label_or_cost_makes_the_verdict_valid():
    rep = _read("report.md").replace("التوصية: دخول مشروط", "التوصية: فرز سوق أولي", 1)
    assert C.check_verdict_basis(_doc(report=rep)).status == C.PASS
    assert C.check_verdict_basis(_doc(production_cost_per_unit=30.0)).status == C.PASS
    ceiling = _read("report.md") + "\nأقصى سعر مصنع قابل للمنافسة 4.1 دينار بحريني للكيلوغرام.\n"
    assert C.check_verdict_basis(_doc(report=ceiling)).status == C.PASS


def test_f7_passes_when_halal_is_classified_once():
    rep = (_read("report.md")
           .replace("### الاشتراطات التي يطلبها المشترون عملياً", "### اشتراطات إلزامية إضافية")
           .replace("فهي شرط عملي للقبول لدى الموزّعين وسلاسل التجزئة",
                    "وهي إلزامية بموجب نظام الحلال الوطني"))
    assert C.check_consistency(_doc(report=rep)).status == C.PASS


def test_fully_corrected_study1_passes_every_check():
    """معيار الإنجاز بصيغته الهرمتية: دراسة البحرين بأخطائها مصحّحةً تنجح في كل الفحوصات."""
    rep, ev = _corrected_mirror()
    rep = rep.replace("التوصية: دخول مشروط", "التوصية: فرز سوق أولي", 1)
    rep = (rep.replace("### الاشتراطات التي يطلبها المشترون عملياً", "### اشتراطات إلزامية إضافية")
              .replace("فهي شرط عملي للقبول لدى الموزّعين وسلاسل التجزئة",
                       "وهي إلزامية بموجب نظام الحلال الوطني"))
    start = rep.index("## 6. المشهد التنافسي")
    end = rep.index("أما على مستوى الجملة")
    rep = rep[:start] + _DOC_TABLE + "\n" + rep[end:]
    rep = rep.replace("| أعلى سعر رف مرصود لمنتج منافس | 20.00 دينار بحريني/كجم (منتج سعودي، محمصة الرياض) |",
                      "| أعلى سعر رف موثق | 12.98 دينار بحريني/كجم (Lulu) |")
    rep = rep.replace("التي تتراوح بين 2.50 و20.00 دينار بحريني للكيلوغرام",
                      "التي تتراوح بين 9.90 و12.98 دينار بحريني للكيلوغرام")
    rep = _with_origin_rule(rep)  # آخراً: تُطبِّع النصّ (بلا حركات)
    rep += ("\nضريبة القيمة المضافة في البحرين 10%، والدينار مربوط بالدولار عند 0.376 دينار "
            "للدولار.\n")
    ev = ev.replace("817,876 طن", "817,876 كيلوغرام")
    res = C.run_all(_doc(report=rep, evidence=ev))
    bad = {f.check: f.status for f in res if f.status != C.PASS}
    assert not bad, {f.check: f.items for f in res if f.status != C.PASS}


# ── F6 النطاق: مثال المالك ووعي النفي ─────────────────────────────────────────

_H = "### خارطة طريق الدخول (90 يوماً)"


@pytest.mark.parametrize("code,line,status,term", [
    ("090121", "ننصح أيضاً ببيع البن الأخضر للمحامص.", C.FAIL, "090111"),
    ("090121", "ننصح بطرح قهوة محمصة غير منزوعة الكافيين بعبوات 250 غرام.", C.PASS, None),
    ("090121", "اطرح نسخة منزوعة الكافيين لاحقاً.", C.FAIL, "090122"),
    ("090121", "ننصح بطرح قهوة محمصة منزوعة الكافيين.", C.FAIL, "090122"),
    ("090121", "يمكن لاحقاً التوسع إلى البند 090111.", C.FAIL, "090111"),
    ("090121", "احصل على الضوء الأخضر من الموزع قبل الشحن.", C.PASS, None),
    ("090111", "ننصح ببيع البن الأخضر للمحامص البحرينية.", C.FAIL, "090121"),
    ("080410", "ركّز على التمور الطازجة غير المجففة في رمضان.", C.PASS, None),
    ("190219", "ننصح بطرح معكرونة مطبوخة جاهزة.", C.FAIL, None),
    ("200911", "ننصح بعصير برتقال غير مجمد.", C.FAIL, "200912"),
])
def test_f6_scope_is_read_from_the_official_hs_description(code, line, status, term):
    """لا جدول لكل منتج: الصفات وقطبيتها من وصف البند الرسمي عبر معجمٍ عامّ."""
    rep = _read("report.md").replace(_H, _H + "\n\n" + line)
    f = C.check_scope(_doc(report=rep, hs_code=code))
    assert f.status == status, _blob(f)
    if term:
        assert any(i["hs_code"] == term for i in f.items), _blob(f)


def test_f6_descriptor_spec_parses_hs_grammar():
    assert C.descriptor_spec("090111") == {"roasted": "-", "decaffeinated": "-"}
    assert C.descriptor_spec("090121") == {"roasted": "+", "decaffeinated": "-"}
    assert C.descriptor_spec("090122") == {"roasted": "+", "decaffeinated": "+"}
    assert C.descriptor_spec("190230") == {"stuffed": "-"}, "«cooked or otherwise prepared» بديل"
    assert C.descriptor_spec("080410") == {}, "«fresh or dried» بديلٌ لا شرط"
    assert C.descriptor_spec("200912") == {"frozen": "-", "fermented": "-"}
    assert not os.path.exists(os.path.join(ROOT, "data", "hs_scope_terms_l1.csv"))


def test_f6_decaf_study_is_not_flagged_for_its_own_product():
    rep = "## 10. التوصيات الاستراتيجية\n\nننصح بطرح قهوة محمصة منزوعة الكافيين، وdecaf roasted coffee.\n"
    assert C.check_scope(_doc(report=rep, hs_code="090122")).status == C.PASS


def test_f3_does_not_read_expected_json():
    """F3 من أدلة الدراسة نفسها: النتيجة واحدة بالقيم المرجعية وبدونها."""
    with_exp = C.check_mirror(_doc())
    doc = _doc()
    doc.expected = {}
    without = C.check_mirror(doc)
    assert with_exp.status == without.status == C.FAIL
    assert [i["why"] for i in with_exp.items] == [i["why"] for i in without.items]
    facts = C.study_facts(doc)
    share = {(f.kind, f.value) for f in facts if f.indicator == "saudi_share_pct"}
    assert ("direct", 1.43) in share and ("mirror", 12.02) in share
    assert ("direct", 9.23) not in share, "«المملكة المتحدة» ليست السعودية"
    assert {f.year for f in facts if f.indicator == "imports_usd" and f.kind == "direct"} >= {2019, 2022, 2023}


def test_f3_mirror_only_market_may_cite_a_labelled_mirror_figure():
    """سوقٌ لا تصرّح (لا رقم مباشر): المرآة مسموحة في الخلاصة موسومةً، وممنوعة بلا وسم."""
    ev = "تدفقات التجارة: مرآة صادرات الشركاء 2023: 9.6 مليون دولار [المصدر: UN Comtrade (مرآة)]"
    ok = "## 1. الخلاصة التنفيذية\n\nالواردات نحو 9.6 مليون دولار (تقدير من بيانات الشركاء، مرآة).\n"
    bad = "## 1. الخلاصة التنفيذية\n\nالواردات نحو 9.6 مليون دولار.\n"
    assert C.check_mirror(C.StudyDoc(report=ok, evidence=ev)).status == C.PASS
    assert C.check_mirror(C.StudyDoc(report=bad, evidence=ev)).status == C.FAIL


# ── G0 القيم المرجعية والتسامح ─────────────────────────────────────────────────

def test_g0_catches_a_wrong_year_and_tolerates_rounding():
    rep = _read("report.md").replace("ثم 9.17 مليون دولار في 2024", "ثم 9.71 مليون دولار في 2024")
    g = C.check_reference_values(_doc(report=rep))
    assert [i["key"] for i in g.items if i["status"] == C.FAIL] == ["imports_2024"]
    assert C.near(16.48, 16.477, 0.5) and not C.near(16.6, 16.477, 0.5)


# ── ٣) الأداة: المصادر ورموز الخروج وخط الأساس ─────────────────────────────────

def test_runner_cli_exit_codes_and_json():
    r = subprocess.run([sys.executable, RUNNER, "--case", CASE, "--json"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 1, r.stderr
    out = json.loads(r.stdout)
    assert out["overall"] == C.FAIL and out["checks"]["F1"] == C.FAIL
    r = subprocess.run([sys.executable, RUNNER, "--all", "--baseline"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([sys.executable, RUNNER, "--case", "no_such_case"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 2


def test_baseline_detects_regressions_in_both_modes():
    rc = _runner()
    base = {"a": {"mode": "detect", "checks": {"F1": "FAIL", "F6": "PASS"}},
            "b": {"mode": "quality", "checks": {"F1": "PASS", "F2": "WARN"}}}
    assert rc.compare_baseline("a", {"F1": "FAIL", "F6": "PASS"}, base) == []
    assert rc.compare_baseline("a", {"F1": "PASS", "F6": "PASS"}, base), "فحصٌ توقّف عن الإمساك"
    assert rc.compare_baseline("b", {"F1": "PASS", "F2": "PASS"}, base) == []
    assert rc.compare_baseline("b", {"F1": "WARN", "F2": "WARN"}, base)


def test_every_golden_case_is_in_the_baseline():
    rc = _runner()
    with open(rc.BASELINE, encoding="utf-8") as fh:
        base = json.load(fh)
    for k in rc.cases():
        assert k in base, f"دراسة مرجعية بلا خط أساس: {k}"
        assert not rc.compare_baseline(k, rc._status_map(C.run_all(rc.case_doc(k))), base)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # صمت
        pass

    def do_GET(self):  # noqa: N802
        if self.headers.get("X-API-Key") != "k":
            self.send_response(401)
            self.end_headers()
            return
        if self.path == "/analyses/1/report/refined":
            body = {"markdown": _read("report.md")}
        elif self.path == "/analyses/1/evidence":
            body = {"context": _read("evidence.txt") + "\nالتقرير المكتوب للدراسة:\n" + _read("report.md")}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)


def test_runner_remote_reads_report_and_evidence_and_matches_the_frozen_case(monkeypatch, capsys):
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        monkeypatch.setenv("SILK_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
        monkeypatch.setenv("SILK_API_KEY", "k")
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("http_proxy", raising=False)
        monkeypatch.setenv("NO_PROXY", "127.0.0.1")
        rc = _runner()
        code = rc.main(["--analysis-id", "1", "--remote", "--json"])
    finally:
        srv.shutdown()
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["meta"]["hs_code"] == "090121" and out["meta"]["currency"] == "BHD"
    frozen = C.summarize(C.run_all(_doc()))["checks"]
    assert out["checks"] == frozen, "الدراسة نفسها من الخادم يجب أن تعطي نتيجة النسخة المجمَّدة"


def test_runner_reads_a_stored_analysis_read_only(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from canonical_bahrain_coffee import bahrain_coffee_research_blob
    db = tmp_path / "silk.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE analyses (id INTEGER PRIMARY KEY, json_blob TEXT)")
    con.execute("INSERT INTO analyses VALUES (7, ?)",
                (json.dumps(bahrain_coffee_research_blob(), ensure_ascii=False, default=str),))
    con.commit()
    con.close()
    before = db.read_bytes()
    monkeypatch.setenv("SILK_DB", str(db))
    rc = _runner()
    code = rc.main(["--analysis-id", "7", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code in (0, 1)
    assert set(out["checks"]) == {"G0", "F1", "F2", "F3", "F4", "F5", "F6", "F7"}
    assert out["meta"]["hs_code"] == "090121" and out["meta"]["market_iso3"] == "BHR"
    assert out["checks"]["F5"] == C.FAIL, "العيّنة: «دخول مشروط» بلا تكلفة ولا سقف"
    assert db.read_bytes() == before, "الأداة للقراءة فقط"
    doc = C.StudyDoc.from_result(bahrain_coffee_research_blob())
    assert "## 1. الخلاصة التنفيذية" in doc.report
    assert "## 1. الخلاصة التنفيذية" not in doc.evidence, "نصّ التقرير لا يُعَدّ دليلاً على نفسه"
    assert "UN Comtrade" in doc.evidence


def test_module_is_stdlib_only_and_offline():
    """الفحص حتمي: لا شبكة ولا نموذج في رأس الوحدة (`silk_render` كسول داخل from_result)."""
    tree = ast.parse(open(os.path.join(ROOT, "silk_study_checks.py"), encoding="utf-8").read())
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            top.add((node.module or "").split(".")[0])
    assert top <= {"__future__", "csv", "os", "re", "dataclasses"}, top


def test_checks_run_with_the_network_cut():
    from tests.conftest import block_network
    with block_network():
        res = C.run_all(_doc())
    assert {f.check for f in res} == {"G0", "F1", "F2", "F3", "F4", "F5", "F6", "F7"}


# ── أقفال المراجعة الذاتية (§58) — كل ملاحظة أُعيد إنتاجها ثم أُصلحت ──────────────

def test_review_embedded_report_copy_is_stripped_even_when_not_byte_identical():
    ev = ("سجلّ الحقائق — واردات السوق: 9.17 مليون دولار (UN Comtrade 2024)\n"
          "التقرير المكتوب للدراسة:\n## 1. الخلاصة\n\nنصٌّ مُطهَّر 777 مليون دولار.\n\n"
          "## 11. الملاحق\n\nملحق.\n"
          "حجم واردات السوق = 9170000 [المصدر: UN Comtrade]\nحدّ معلن: شيء")
    out = C.strip_embedded_report(ev, report="نصٌّ خام مختلف 777")
    assert "777" not in out and "## 1." not in out
    assert "حجم واردات السوق = 9170000" in out and C.norm_digits("حدّ معلن: شيء") in out
    assert out.startswith(C.norm_digits("سجلّ الحقائق — واردات السوق"))
    raw = ("التقرير المكتوب للدراسة:\n## 1. خ\n\nنص 555.\nمورّد: Brazil — حصة 30% [UN Comtrade]\n"
           "حدّ معلن: شيء")
    kept = C.strip_embedded_report(raw)
    assert "555" not in kept and "Brazil" in kept, "سطور ما بعد التقرير بحركاتها تُنهي القصّ"


def test_review_from_result_measures_the_bound_text_and_excludes_it_from_evidence():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from canonical_bahrain_coffee import bahrain_coffee_research_blob
    doc = C.StudyDoc.from_result(bahrain_coffee_research_blob())
    needle = C.norm_digits("المسار الأول برّي بالشاحنات")
    assert needle in doc.report
    assert needle not in doc.evidence
    assert "التقرير المكتوب للدراسة" not in doc.evidence


def test_review_f4_ten_percent_is_not_a_zero_tariff():
    assert C.check_tariff_claims(_doc(report="## 7. ت\n\nالرسوم الجمركية 10% على المنتج.\n")).status == C.PASS
    assert C.check_tariff_claims(_doc(report="## 7. ت\n\nالرسوم الجمركية 20% و100% أحياناً.\n")).status == C.PASS
    assert C.check_tariff_claims(_doc(report="## 7. ت\n\nالرسوم الجمركية 0.0% على المنتج.\n")).status == C.FAIL


def test_review_f1_ignores_a_per_kg_price_next_to_a_volume():
    ev = "تدفقات التجارة: بلغت الواردات 5,000 طن بمتوسط 6.2 دولار للكيلوغرام في 2023."
    f = C.check_units(_doc(report="", evidence=ev))
    assert f.status != C.FAIL, _blob(f)


def test_review_f6_adjacency_does_not_shield_an_out_of_scope_decaf():
    rep = "## 10. التوصيات الاستراتيجية\n\nننصح بطرح قهوة محمصة منزوعة الكافيين.\n"
    f = C.check_scope(_doc(report=rep, hs_code="090121"))
    assert f.status == C.FAIL and f.items[0]["hs_code"] == "090122"


def test_review_f7_not_mandatory_is_optional_and_mixed_is_unclassified():
    assert C._classify("الحلال غير إلزامي لكن يطلبه المشترون", "") == "optional"
    assert C._classify("الحلال إلزامي واختياري معاً", "") is None
    rep = ("## 5. الطلب\n\nشهادة الحلال غير إلزامية في هذا السوق.\n\n"
           "## 7. التنظيم\n\nشهادة الحلال يطلبها المشترون عملياً.\n")
    assert C.check_consistency(_doc(report=rep)).status == C.PASS


def test_review_g0_fx_reads_only_exchange_rate_sentences():
    ok = _read("report.md") + "\nعبوة 250 غرام بسعر 0.350 دينار.\n"
    g = C.check_reference_values(_doc(report=ok))
    assert not any(i["key"] == "fx_local_per_usd" and i["status"] == C.FAIL for i in g.items)
    bad = _read("report.md") + "\nالدينار مربوط بالدولار عند 0.390 دينار للدولار.\n"
    g = C.check_reference_values(_doc(report=bad))
    assert any(i["key"] == "fx_local_per_usd" and i["status"] == C.FAIL for i in g.items)


def test_review_f5_a_declared_missing_cost_is_not_a_cost():
    rep = ("## 1. الخلاصة التنفيذية\n\nالتوصية: دخول مشروط.\n\n"
           "سعر المصنع غير متاح، ومتوسط الاستيراد 6.2 دولار للكيلوغرام.\n")
    assert C.check_verdict_basis(_doc(report=rep)).status == C.FAIL


def test_review_verdict_labels_are_whole_words():
    assert C._find_label("The market looks good and the government is stable") is None
    assert C._find_label("لا ننصح بالدخول في الوقت الراهن") == "لا ننصح بالدخول"
    assert C._find_label("Verdict: CONDITIONAL-GO") == "CONDITIONAL-GO"


def test_review_f3_single_sentence_pair_follows_the_markers():
    ev = "حصة السعودية في المرآة 12.02% مقابل 1.43% في البيانات المباشرة."
    doc = C.StudyDoc(report="## 4. د\n\nالحصة 12.02% في 2025.\n", evidence=ev, meta={}, expected={})
    f = C.check_mirror(doc)
    share = {(x.kind, x.value) for x in C.study_facts(doc) if x.indicator == "saudi_share_pct"}
    assert ("direct", 1.43) in share and ("mirror", 12.02) in share
    assert f.status == C.FAIL


def test_review_link_cell_with_na_letters_is_a_link():
    rep = ("| المنتج | العبوة | سعر التجزئة | المتجر وتاريخ الرصد | الرابط |\n|---|---|---|---|---|\n"
           "| بن | 500 غرام | 6.490 دينار بحريني | National Stores، أكتوبر 2026 | nationalstores.bh/coffee |\n")
    f = C.check_shelf_prices(_doc(report=rep))
    row = next(i for i in f.items if "pack_kg" in i)
    assert row["has_link"] is True and "بلا رابط" not in row["why"]


def test_review_remote_prefers_the_full_blob(monkeypatch, capsys):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from canonical_bahrain_coffee import bahrain_coffee_research_blob
    blob = json.dumps(bahrain_coffee_research_blob(), ensure_ascii=False, default=str).encode("utf-8")

    class H(_Handler):
        def do_GET(self):  # noqa: N802
            if self.path == "/analyses/7":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(blob)
                return
            self.send_response(404)
            self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("SILK_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
        monkeypatch.setenv("SILK_API_KEY", "k")
        monkeypatch.setenv("NO_PROXY", "127.0.0.1")
        code = _runner().main(["--analysis-id", "7", "--remote", "--json"])
    finally:
        srv.shutdown()
    out = json.loads(capsys.readouterr().out)
    local = C.summarize(C.run_all(C.StudyDoc.from_result(bahrain_coffee_research_blob(),
                                                         meta=out["meta"])))["checks"]
    assert code in (0, 1) and out["checks"] == local


# ── أقفال قياس الإنذارات الكاذبة (الدراسة ١ + ٢٠ دراسة مقنَّنة) ───────────────────

def _r(body: str, **meta) -> C.StudyDoc:
    return C.StudyDoc(report=body, meta=meta)


def test_measure_f2_prose_shelf_price_needs_a_documented_record():
    """jordan/egypt/kenya…: سعر رف في النصّ بلا جدولٍ موثّق ولا رابط = مخالفة."""
    f = C.check_shelf_prices(_r("## 4. د\n\nعلاوة تجزئة: 0.85 دينار/لتر مقابل 0.55 دينار/لتر.\n"))
    assert f.status == C.FAIL and "بلا سجل" in f.items[0]["why"]


def test_measure_f2_production_cost_is_not_a_shelf_price():
    """india_honey: «تكلفة إنتاج الكيلوغرام (95 روبية)» في جملةٍ تذكر سعر الرف لاحقاً."""
    body = ("## 2. م\n\nأدخل المصدر تكلفة إنتاج الكيلوغرام (95 روبية)، ورصد سعر رف منافس واحد موثق.\n")
    assert C.check_shelf_prices(_r(body)).status == C.WARN


def test_measure_f2_usd_retail_counts_and_usd_border_price_does_not():
    retail = C.check_shelf_prices(_r("## 6. م\n\nمتوسط سعر التجزئة 18–34 دولار/كغم للعسل الفاخر.\n"))
    border = C.check_shelf_prices(_r("## 3. س\n\nمتوسط سعر الاستيراد الحدودي 3.40 دولار للكيلوغرام.\n"))
    fee = C.check_shelf_prices(_r("## 7. ت\n\nرسوم بيان جمركي 3 دينار للشحنة.\n"))
    assert retail.status == C.FAIL and border.status == C.WARN and fee.status == C.WARN


def test_measure_f4_reads_through_arabic_diacritics():
    """qatar: «فتتمتّع واردات المنشأ السعوديّ بإعفاءٍ جمركيّ» كان يفلت بسبب الحركات."""
    body = "## 7. ت\n\nقطر عضوٌ في مجلس التعاون، فتتمتّع واردات المنشأ السعوديّ بإعفاءٍ جمركيّ.\n"
    assert C.check_tariff_claims(_r(body)).status == C.FAIL
    assert C.norm_digits("بإعفاءٍ جمركيّ بـ2.50") == "بإعفاء جمركي ب2.50"


def test_measure_f5_hold_verdicts_commit_no_money():
    """«مراقبة السوق»/«لا تدخل» لا تلتزم بمال — قراءةٌ معلنة للمالك؛ حكم الدخول وحده يحتاج تكلفة."""
    for v in ("مراقبة السوق", "لا تدخل", "NO-GO"):
        assert C.check_verdict_basis(_r(f"## 1. الخلاصة التنفيذية\n\nالتوصية: {v}.\n")).status == C.PASS, v
    for v in ("دخول مشروط", "توصية أولية بالدخول", "CONDITIONAL-GO"):
        assert C.check_verdict_basis(_r(f"## 1. الخلاصة التنفيذية\n\nالتوصية: {v}.\n")).status == C.FAIL, v


def test_measure_f3_only_indicator_values_are_mirror_figures():
    """jordan: كل رقمٍ في جملةٍ فيها «مرآة» كان يُعَدّ رقم مرآة («5» من «فجوة 5.6×»)."""
    ev = "تحليل المنافسين: صادرات السعودية للأردن تحت 040110 (مرآة) 2024: 11.2 مليون دولار، فجوة 5 أضعاف [المصدر: UN Comtrade (مرآة)]"
    rep = "## 9. م\n\nفجوة المرآة غير المحسومة (5) تبقى الخطر الأكبر.\n"
    f = C.check_mirror(C.StudyDoc(report=rep, evidence=ev))
    assert f.status == C.PASS, _blob(f)
    assert [x.indicator for x in C.study_facts(C.StudyDoc(report="", evidence=ev))] == ["saudi_flow_usd"]


def test_measure_codified_corpus_has_no_unlabelled_change():
    """الدراسات المقنَّنة العشرون في خط الأساس بنمط detect — كل حالة موسومة يدوياً."""
    rc = _runner()
    with open(rc.BASELINE, encoding="utf-8") as fh:
        base = json.load(fh)
    cod = [k for k in rc.cases() if k.startswith(rc.CODIFIED_PREFIX)]
    assert len(cod) == 20
    for k in cod:
        assert base[k]["mode"] == "detect"
        assert not rc.compare_baseline(k, rc._status_map(C.run_all(rc.case_doc(k))), base), k


# ── أقفال المراجعة الذاتية الثانية (§58) ─────────────────────────────────────────

def test_review2_supplier_line_is_not_a_market_total():
    line = ("مورّد: Brazil — حصة 30.0% من إجمالي واردات السوق؛ قيمة صادرات هذا المورّد وحده "
            "4536000.0$ (ليست إجمالي واردات السوق)")
    assert not [f for f in C._facts_from_text(line, "UN Comtrade", "direct") if f.indicator == "imports_usd"]


def test_review2_thousands_separator_is_not_a_clause_break():
    fs = C._facts_from_text("بلغت واردات السوق الإجمالية 15,120,000 دولار حسب UN Comtrade.", "UN Comtrade", "direct")
    assert [(f.indicator, f.value) for f in fs] == [("imports_usd", 15120000.0)]


def test_review2_yen_needs_a_word_boundary():
    body = "## 6. م\n\nطرحت العلامة الجديدة منتجها في السوق يوم 15 يناير.\n"
    assert C.check_shelf_prices(_r(body)).status == C.WARN


def test_review2_brand_and_vat_words_do_not_hide_a_shelf_price():
    for body in ("## 6. م\n\nتباع Costa Coffee بسعر 4.500 دينار للعبوة على الرفوف.\n",
                 "## 6. م\n\nسعر التجزئة 4.5 دينار شامل ضريبة القيمة المضافة.\n"):
        assert C.check_shelf_prices(_r(body)).status == C.FAIL, body


def test_review2_wrapped_cost_line_is_not_a_shelf_price():
    """india_honey حرفياً: «تكلفة إنتاج\\nالكيلوغرام (95 روبية)» — السطر الملفوف جملةٌ واحدة."""
    body = ("## 2. م\n\nأدخل المصدر تكلفة إنتاج\nالكيلوغرام (95 روبية)، ورصد سعر رف منافس واحد موثق.\n")
    assert C.check_shelf_prices(_r(body)).status == C.WARN
    india = _runner().case_doc("codified/india_honey")
    whys = [i["why"] for i in C.check_shelf_prices(india).items]
    assert not any("95 روبية" in w for w in whys) and any("480" in w for w in whys)


def test_review2_a_direct_figure_equal_to_a_mirror_figure_is_not_mirror_usage():
    ev = ("تحليل المنافسين: 12 دولة موردة في 2023 [المصدر: UN Comtrade]\n"
          "تقاطع: تقدير مرآة 2025 يظهر 12 دولة موردة وحصة سعودية 12.02% [المصدر: UN Comtrade (مرآة)]")
    rep = "## 1. الخلاصة التنفيذية\n\nتصل القهوة من 12 دولة مورّدة، والواردات تنمو 12% سنوياً.\n"
    f = C.check_mirror(C.StudyDoc(report=rep, evidence=ev))
    assert not any(i.get("where") == "القسم 1" for i in f.items), _blob(f)


def test_review2_f6_negation_and_generic_words():
    assert C._mentions("عبوة أولا محمصة.", "0901")[0][1] == "+"
    rep = "## 10. التوصيات الاستراتيجية\n\nنوصي بتأمين المواد الخام محليا.\n"
    assert C.check_scope(_doc(report=rep, hs_code="151219")).status == C.PASS


def test_review2_free_text_entry_verdict_is_not_read_as_hold():
    rep = "## 1. الخلاصة التنفيذية\n\nالتوصية: ادخل تدريجيا لأجل اختبار السوق.\n"
    assert C.check_verdict_basis(_r(rep)).status == C.FAIL


def test_review2_evidence_link_needs_the_same_record():
    ev = "تحليل الأسعار: منتج x https://shop.bh/p/3 بسعر 7 دينار"
    doc = C.StudyDoc(report="## 6. م\n\nسعر التجزئة 3 دينار للعبوة.\n", evidence=ev)
    assert C.check_shelf_prices(doc).status == C.FAIL
    ok = C.StudyDoc(report="## 6. م\n\nسعر التجزئة 7 دينار للعبوة.\n", evidence=ev)
    assert C.check_shelf_prices(ok).status != C.FAIL
