"""أقفال إصلاحات الموجة ٣ (2026-08-17) — engine + main-UI usability fixes.

أربع عائلات أُصلحت معاً، لكلٍّ قفلها:

1. **تناقض بريطانيا** (عائلة «وسمٌ بلا صفوف»): GBR كانت «مقنّن بالكامل» بينما
   المرجع الثابت لا يحمل صفاً واحداً لها — الوسم الصادق «موثّق جزئياً».
2. **توحيد مرجع الحصة المسلمة** (عائلة الدرس ٦٣ — القوائم المتشعّبة): حقيقة
   واحدة في ملفين؛ `silk_research` كان يقرأ الأقدم الناقص (٤٤ صفاً بلا
   LBN/YEM/GHA) — الأساس الآن `demographics_l1.csv` (٢٥٠ سوقاً، نفس أصل Pew).
3. **وسم أعطال الخدمات بهوية التشغيلة**: الضعف المصرَّح به في
   `silk_watchdog._check_services` (مطابقة زمنية تقريبية تتشارك سطراً بين
   تشغيلات متزامنة) — الوسم `trace_id` يجعلها يقينية، والصفوف القديمة غير
   الموسومة تبقى على النافذة (لا انحدار).
4. **واجهة index.html**: زر «التعميق» كان CTA ميتاً (toast «غير متاح») رغم
   اكتمال المسار الخادمي — الآن يستدعي `POST /deepen` فعلاً؛ وسجل المصداقية
   (outcome) كان PATCH بلا أي زرّ — الآن له سطح تسجيل.

هرمتي بالكامل — لا شبكة، لا مفاتيح.
"""
from __future__ import annotations

import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_INDEX = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")


# ═══════════ ١ — بريطانيا: الوسم يطابق التغطية ═══════════════════════════════
def test_gbr_tier_matches_its_actual_zero_coverage():
    from silk_requirements_agent import RequirementsAgent, codification_tier
    assert codification_tier("GBR")[0] == "موثّق جزئياً"
    rep = RequirementsAgent().run({"market_iso3": "GBR", "hs_code": "080410"})
    # لا تناقض بعد الآن: الوسم الجزئي + فجوة «تحقق محلياً» متّسقان معاً.
    assert "مقنّن بالكامل" not in rep.summary
    assert "موثّق جزئياً" in rep.summary


def test_eu27_members_keep_the_full_codification_tier():
    """التصحيح أخرج GBR وحدها — أعضاء EU27 الحقيقيون لم يمسّهم شيء."""
    from silk_requirements_agent import codification_tier
    for iso in ("DEU", "FRA", "HUN"):
        assert codification_tier(iso)[0] == "مقنّن بالكامل", iso


# ═══════════ ٢ — مرجع الحصة المسلمة الموحّد ══════════════════════════════════
def test_muslim_share_reads_the_canonical_demographics_reference(monkeypatch):
    import silk_research as R
    monkeypatch.setattr(R, "_muslim_cache", None)
    # القيم المشتركة لم تتغيّر (نفس أصل Pew) — لا انحدار على الأسواق القائمة.
    assert R.muslim_share("SAU")["pct"] == 93
    # والأسواق الثلاثة التي كانت فجوةً في الملف الأقدم صارت مغطاة.
    for iso in ("LBN", "YEM", "GHA"):
        got = R.muslim_share(iso)
        assert got is not None, f"{iso} ما تزال فجوة رغم التوحيد"
        assert got["pct"] > 0
    assert R.muslim_share("XKX") is None      # غير الموجود يبقى None لا صفراً


def test_muslim_share_falls_back_to_the_old_file_when_canonical_absent(
        monkeypatch, tmp_path):
    """فشل آمن مفتوح: غياب الأشمل لا يُفقد الميزة — يقرأ الأقدم كاحتياط."""
    import shutil
    import silk_research as R
    d = tmp_path / "data"
    d.mkdir()
    shutil.copy(_ROOT / "data" / "muslim_share.csv", d / "muslim_share.csv")
    monkeypatch.setattr(R, "_DATA_DIR", str(d))
    monkeypatch.setattr(R, "_muslim_cache", None)
    assert R.muslim_share("SAU")["pct"] == 93
    assert R.muslim_share("LBN") is None      # فجوة الأقدم تبقى فجوة معلنة


# ═══════════ ٣ — وسم أعطال الخدمات بهوية التشغيلة ═══════════════════════════
def _ops_db(monkeypatch, tmp_path):
    db = str(tmp_path / "ops_errors.db")
    monkeypatch.setenv("SILK_OPS_LOG_DB", db)
    return db


def test_service_failure_inside_a_trace_is_stamped_with_the_trace_id(
        monkeypatch, tmp_path):
    db = _ops_db(monkeypatch, tmp_path)
    import silk_ops_log
    import silk_trace
    with silk_trace.trace_context("t-stamp-1", dir_path=str(tmp_path)):
        silk_ops_log.record_service_failure("scraper", "boom", path=db)
    row = silk_ops_log.last_errors(1, path=db)[0]
    assert (row.get("context") or {}).get("trace_id") == "t-stamp-1"


def test_service_failure_outside_any_trace_stays_untagged(monkeypatch, tmp_path):
    db = _ops_db(monkeypatch, tmp_path)
    import silk_ops_log
    silk_ops_log.record_service_failure("scraper", "boom", path=db)
    row = silk_ops_log.last_errors(1, path=db)[0]
    assert "trace_id" not in (row.get("context") or {})


def test_watchdog_matches_tagged_rows_by_trace_not_by_time_window(
        monkeypatch, tmp_path):
    """المطابقة اليقينية: صفّ تشغيلةٍ أخرى يُستبعد ولو وقع داخل النافذة —
    وهو بالضبط سيناريو «تشغيلات متزامنة تتشارك سطراً» المصرَّح به سابقاً."""
    db = _ops_db(monkeypatch, tmp_path)
    import silk_ops_log
    import silk_trace
    import silk_watchdog
    with silk_trace.trace_context("t-mine", dir_path=str(tmp_path)):
        silk_ops_log.record_service_failure("scraper", "mine", path=db)
    with silk_trace.trace_context("t-other", dir_path=str(tmp_path)):
        silk_ops_log.record_service_failure("trends", "other-run", path=db)
    services, _f = silk_watchdog._check_services(60, trace_id="t-mine")
    names = {s["service"] for s in services}
    assert names == {"scraper"}, (
        f"المتوقع صفّ التشغيلة الموسوم وحده، وُجد: {names}")


def test_watchdog_keeps_the_window_heuristic_for_untagged_rows(
        monkeypatch, tmp_path):
    """لا انحدار: الصفوف غير الموسومة (ما قبل الوسم/مسارات بلا تتبّع) تبقى
    تُلتقط بالنافذة الزمنية التقريبية كما كانت."""
    db = _ops_db(monkeypatch, tmp_path)
    import silk_ops_log
    import silk_watchdog
    silk_ops_log.record_service_failure("imf", "untagged", path=db)
    services, _f = silk_watchdog._check_services(60, trace_id="t-whatever")
    assert {s["service"] for s in services} == {"imf"}


# ═══════════ ٤ — الواجهة الرئيسية: زر التعميق الحيّ + سطح outcome ════════════
def test_the_deepen_button_actually_calls_the_paid_endpoint():
    """CTA «فعّل التعميق» يستدعي `POST /deepen` — لا toast «غير متاح» بعد اليوم.

    (عائلة «نجاح ظاهري يعد بأقل مما يُظهر» — نفس التي حرّمها الدرس ٩ على
    الأزرار الميتة.) يُفحَص **ما يُعرَض** لا الشروح — ذكرُ العبارة في تعليقٍ
    يشرح إزالتها لا يُحمِّر الحارس (نفس قاعدة `_without_comments` في حارس
    صفحة المنصّة).
    """
    visible = re.sub(r"/\*.*?\*/", " ", re.sub(r"<!--.*?-->", " ", _INDEX,
                                               flags=re.S), flags=re.S)
    assert "غير متاح في هذا التشغيل" not in visible, (
        "نص الزرّ الميت ما يزال معروضاً — الزرّ عاد يعد ولا ينفّذ")
    assert 'addEventListener("click",deepenFlow)' in _INDEX
    m = re.search(r'post\("/deepen",\{(.*?)\}\)', _INDEX, re.S)
    assert m, "لا نداء POST /deepen في الصفحة"
    payload = m.group(1)
    for key in ("product", "hs_code", "hs_confirmed",
                "with_localprice", "with_volza", "with_explee"):
        assert key in payload, f"جسم /deepen بلا `{key}`"


def test_the_deepen_dialog_is_honest_about_cost_and_requirements():
    """النافذة تسمّي شرطي التشغيل (مفاتيح الخادم + السقف اليومي) قبل النقرة."""
    dlg = _INDEX[_INDEX.index("function deepenFlow"):]
    dlg = dlg[:dlg.index("function ", 20)]
    assert "السقف اليومي" in dlg
    assert "مفاتيح" in dlg


def test_the_credibility_ledger_finally_has_a_write_surface():
    """سجلّ المصداقية (outcome): زرّ + نافذة + PATCH — كان خادمياً فقط منذ
    الموجة ١ بلا أي سبيل من الواجهة."""
    assert "data-outcome-id" in _INDEX, "لا زرّ لتسجيل النتيجة على صفّ السجل"
    assert re.search(r'patchJSON\("/analyses/"\s*\+\s*id\s*\+\s*"/outcome"',
                     _INDEX), "لا نداء PATCH لنقطة outcome"
    # والنتيجة المسجّلة تُعرَض على الصفّ (قراءة outcome/outcome_date).
    assert "r.outcome" in _INDEX


def test_index_script_still_parses_with_a_real_js_engine(tmp_path):
    """تعديلات اليوم لم تكسر السكربت — نفس ضمانة صفحة المنصّة (تحليل فعلي)."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node غير متوفّر — رُتبة ٣ تغطي هذا في CI")
    m = re.search(r"<script>(.*)</script>", _INDEX, re.S)
    f = tmp_path / "index_page.js"
    f.write_text(m.group(1), encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, f"سكربت index.html لا يُحلَّل:\n{r.stderr[:1200]}"


def test_trend_docstring_no_longer_claims_a_ui_tab():
    import inspect
    src = pathlib.Path(_ROOT / "api.py").read_text(encoding="utf-8")
    assert "يغذّي تبويب «الاتجاه» في الواجهة" not in src, (
        "docstring /trend ما يزال يدّعي تبويب واجهةٍ لا وجود له")


if __name__ == "__main__":
    import subprocess
    import sys
    sys.exit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
