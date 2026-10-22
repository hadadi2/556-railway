"""الدرس ٣٠٢ (PR-B البند ب، قرار المالك): فحوصُ F1–F7 الحتمية تعمل على كلّ دراسة في **وضع
الظلّ** — تُسجَّل نتيجتُها ولا تحجب شيئاً ولا تمسّ مستندَ العميل ولا حكمَ البوّابة — لأسبوعٍ
يقرأ المالكُ بعده تقريرَ الإنذارات قبل التحويل إلى رفض (البند ج).

Lesson 302 locks: shadow-mode wiring of the deterministic study checks. Written test-first.
"""
import os
import sys
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools"), os.path.join(_ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from test_lesson300_series_head import _bahrain_blob    # noqa: E402

_BAD = ("## 1. الخلاصة التنفيذية\n\nالتوصية دخول مشروط. بلغت واردات البحرين من القهوة المحمّصة "
        "نحو 15.12 مليون دولار عام 2025، بنمو 213% منذ 2019.\n")


def _blob(text=_BAD):
    b = _bahrain_blob()
    b["deep_research"]["report"] = {"report": text, "review_cycles": 1, "unresolved_notes": []}
    return b


def _env(tmp_path, **extra):
    return mock.patch.dict(os.environ, {"SILK_OPS_LOG_DB": str(tmp_path / "ops.db"),
                                        "SILK_STUDY_CHECKS": "shadow", **extra})


def test_shadow_is_the_default_and_off_disables_it(tmp_path):
    import silk_study_checks_shadow as S
    with _env(tmp_path):
        os.environ.pop("SILK_STUDY_CHECKS", None)
        assert S.mode() == "shadow"
    with _env(tmp_path, SILK_STUDY_CHECKS="off"):
        assert S.mode() == "off"
        assert S.run_and_record(_blob(), analysis_id=7, source="pipeline") is None
        assert S.recent(10) == []
    with _env(tmp_path, SILK_STUDY_CHECKS="anything-else"):
        assert S.mode() == "shadow"              # لا رفضَ في هذا البند — القيمةُ المجهولة ظلّ


def test_run_records_each_check_status_and_the_failing_reasons(tmp_path):
    import silk_study_checks_shadow as S
    with _env(tmp_path):
        out = S.run_and_record(_blob(), analysis_id=7, source="pipeline")
        assert out["statuses"]["F3"] == "FAIL" and out["statuses"]["F5"] == "FAIL"
        rows = S.recent(10)
    assert len(rows) == 1 and rows[0]["analysis_id"] == 7 and rows[0]["source"] == "pipeline"
    f3 = [f for f in rows[0]["fails"] if f["check"] == "F3"][0]
    assert f3["why"]                                   # السببُ الأول محفوظ للمراجعة


def test_shadow_never_raises_and_never_changes_the_result(tmp_path):
    import copy
    import silk_study_checks_shadow as S
    b = _blob()
    before = copy.deepcopy(b)
    with _env(tmp_path):
        S.run_and_record(b, analysis_id=1, source="pipeline")
        assert S.run_and_record({"garbage": object()}, analysis_id=2, source="pipeline") is None
        with mock.patch("silk_study_checks.run_all", side_effect=RuntimeError("boom")):
            assert S.run_and_record(_blob(), analysis_id=3, source="pipeline") is None
    assert b == before


def test_weekly_report_counts_each_check(tmp_path):
    import silk_study_checks_shadow as S
    with _env(tmp_path):
        S.run_and_record(_blob(), analysis_id=1, source="pipeline")
        S.run_and_record(_blob(), analysis_id=2, source="post_deploy")
        rep = S.report(days=7)
    assert rep["runs"] == 2 and rep["studies"] == 2 and rep["mode"] == "shadow"
    assert rep["by_check"]["F3"]["FAIL"] == 2 and rep["by_check"]["F5"]["FAIL"] == 2
    assert rep["by_check"]["F1"]["PASS"] == 2


def test_ring_keeps_a_bounded_number_of_rows(tmp_path):
    import silk_study_checks_shadow as S
    with _env(tmp_path, SILK_STUDY_CHECKS_CAP="3"):
        for i in range(5):
            S.run_and_record(_blob(), analysis_id=i, source="pipeline")
        assert [r["analysis_id"] for r in S.recent(10)] == [4, 3, 2]


def test_stored_studies_are_checked_after_deploy(tmp_path):
    import silk_storage
    import silk_study_checks_shadow as S
    db = str(tmp_path / "silk.db")
    silk_storage.init_db(db)
    aid = silk_storage.save_analysis(_blob(), path=db)
    import sqlite3
    with sqlite3.connect(db) as conn:                    # شكلُ الإنتاج: تشغيلةٌ بحثية
        conn.execute("UPDATE analyses SET kind = 'research' WHERE id = ?", (aid,))
    with _env(tmp_path):
        n = S.audit_stored(path=db)
        rows = S.recent(10)
    assert n == 1 and rows[0]["analysis_id"] == aid and rows[0]["source"] == "post_deploy"


def test_pipeline_and_post_deploy_call_the_shadow_hook():
    src = open(os.path.join(_ROOT, "silk_research_pipeline.py"), encoding="utf-8").read()
    assert "silk_study_checks_shadow.run_async(" in src
    col = open(os.path.join(_ROOT, "silk_collectors.py"), encoding="utf-8").read()
    assert "silk_study_checks_shadow.audit_stored(" in col
    api_src = open(os.path.join(_ROOT, "api.py"), encoding="utf-8").read()
    assert 'source="regenerated"' in api_src and 'source="refined"' in api_src


def test_ops_endpoint_is_guarded_and_returns_rows_and_report(tmp_path):
    from fastapi.testclient import TestClient
    import api
    import silk_study_checks_shadow as S
    with _env(tmp_path, SILK_API_KEY="k"):
        S.run_and_record(_blob(), analysis_id=9, source="pipeline")
        c = TestClient(api.create_app())
        assert c.get("/ops/study-checks").status_code == 401
        r = c.get("/ops/study-checks?report=1", headers={"X-API-Key": "k"}).json()
    assert r["mode"] == "shadow" and r["rows"][0]["analysis_id"] == 9
    assert r["report"]["by_check"]["F3"]["FAIL"] == 1


# ── المراجعة الذاتية (§58) ─────────────────────────────────────────────────────

def test_review_first_failing_item_is_recorded_not_the_first_item(tmp_path):
    import silk_study_checks as C
    import silk_study_checks_shadow as S
    f = C.Finding("F2", "x", C.FAIL, "n", [{"status": C.PASS, "why": "موثق"},
                                           {"status": C.FAIL, "why": "دون الحدّ", "where": "§4"}])
    _st, fails = S._summarize([f])
    assert fails[0]["why"] == "دون الحدّ" and fails[0]["count"] == 1


def test_review_post_deploy_keeps_one_row_per_study_and_report_dedupes(tmp_path):
    import silk_study_checks_shadow as S
    with _env(tmp_path):
        for _ in range(3):
            S.run_and_record(_blob(), analysis_id=5, source="post_deploy")
        S.run_and_record(_blob(), analysis_id=5, source="refined")
        assert len([r for r in S.recent(10) if r["source"] == "post_deploy"]) == 1
        rep = S.report()
    assert rep["by_check"]["F3"]["FAIL"] == 1 and rep["by_source"]["post_deploy"]["F3"]["FAIL"] == 1


def test_review_post_deploy_measures_a_fresh_view_not_the_stored_one(tmp_path):
    import json
    import sqlite3
    import silk_storage
    import silk_study_checks_shadow as S
    db = str(tmp_path / "silk.db")
    silk_storage.init_db(db)
    b = _blob()
    b["view"] = {"deep_research": {"report": {"text": "## 1. الخلاصة التنفيذية\n\nنصٌّ قديم سليم.\n"}}}
    aid = silk_storage.save_analysis(b, path=db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE analyses SET kind = 'research' WHERE id = ?", (aid,))
        assert "نصٌّ قديم" in json.loads(conn.execute("SELECT json_blob FROM analyses").fetchone()[0])[
            "view"]["deep_research"]["report"]["text"]
    with _env(tmp_path):
        S.audit_stored(path=db)
        assert S.recent(1)[0]["statuses"]["F3"] == "FAIL"     # النصُّ المسلَّم بالشيفرة الحالية


def test_review_english_studies_are_not_measured(tmp_path):
    import silk_study_checks_shadow as S
    b = _blob()
    b["lang"] = "en"
    with _env(tmp_path):
        assert S.run_and_record(b, analysis_id=1) is None and S.recent(5) == []


def test_review_a_corrupt_row_does_not_break_the_read(tmp_path):
    import sqlite3
    import silk_study_checks_shadow as S
    with _env(tmp_path):
        S.run_and_record(_blob(), analysis_id=1)
        with sqlite3.connect(str(tmp_path / "ops.db")) as conn:
            conn.execute("INSERT INTO study_checks (analysis_id, source, statuses_json, fails_json, "
                         "created_at) VALUES (2, 'pipeline', '{bad', '[]', '2099-01-01T00:00:00Z')")
        assert [r["analysis_id"] for r in S.recent(10)] == [1]
        assert S.report()["runs"] == 1


def test_review_async_runs_on_a_copy(tmp_path):
    import silk_study_checks_shadow as S
    b = _blob()
    with _env(tmp_path):
        t = S.run_async(b, analysis_id=11)
        b["deep_research"]["report"]["report"] = "تغيّر بعد الإطلاق"
        t.join(30)
        assert S.recent(1)[0]["statuses"]["F3"] == "FAIL"


def test_async_writes_to_the_database_chosen_at_launch(tmp_path):
    import threading
    import silk_study_checks_shadow as S
    gate = threading.Event()
    real = S.run_and_record

    def slow(*a, **k):
        gate.wait(10)
        return real(*a, **k)
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    with mock.patch.object(S, "run_and_record", slow):
        with _env(first):
            t = S.run_async(_blob(), analysis_id=15)
        with _env(second):
            gate.set()
            t.join(30)
            assert S.recent(10) == []                 # لا شيءَ في قاعدة الاختبار التالي
    with _env(first):
        assert [r["analysis_id"] for r in S.recent(10)] == [15]
