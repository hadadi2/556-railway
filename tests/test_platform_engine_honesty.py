"""أقفال صدق المحرّك — the empty-completion guard + run stats + diagnostics.

شكوى المالك الحرفية (2026-08-17): «لاحضت ان المحرك لا يعمل فقط ينتهي خلال
ثواني معدودة ويطلع التقرير فارغ». التشخيص المعاد إنتاجه مباشرةً: مصادر فاشلة
كلها ⇒ `classified=True` وكل نقاط البيانات None — والجسر كان يسم ذلك «مكتملاً».

الأقفال هنا:
1. نتيجة بلا أي بيانات حقيقية → الدراسة تعود مسودّةً بسبب معلن + إرجاع الحصّة.
2. نقطة بيانات واحدة حقيقية تكفي → «مكتملة» (لا صرامة زائفة تُفشل الصحيح).
3. `run_stats` (ترحيل 007) يُخزَّن ويظهر للأدمِن — ولا يتسرّب لأي ردّ مصنع.
4. `GET /platform/admin/diagnostics` أدمِن حصراً + مقيّد المعدل + بلا شبكة في
   الاختبار (المسبار يُحاكى — الرتبة الهرمتية لا تجسّ شيئاً حياً).
"""
from __future__ import annotations

from tests.platform_helpers import (client, hdr, login, make_factory,
                                    make_product_study, seed)

PW = "Factory1234"


# ── وحدات حارس الجوهر · substance predicate units ────────────────────────────
def test_result_is_substantive_predicate_both_datapoint_shapes():
    from silk_platform.engine_bridge import result_is_substantive

    # الشكل المعاد إنتاجه من شكوى المالك: مصنَّفة وكل شيء None/0.0.
    empty = {"classified": True, "markets": [{
        "country": "الإمارات", "total_score": 0.0, "confidence": 0.0,
        "components": {"market_size": {"value": None, "confidence": 0.0},
                       "competition": None}}]}
    assert result_is_substantive(empty) is False
    assert result_is_substantive(None) is False
    assert result_is_substantive({"markets": []}) is False

    # ثقة صف > 0 تكفي (شكل عيّنة المقعد الاختباري نفسها).
    assert result_is_substantive({"markets": [
        {"confidence": 0.5, "components": {}}]}) is True
    # قيمة مكوّن غير None تكفي — بشكل dict المُسلسَل.
    assert result_is_substantive({"markets": [
        {"confidence": 0.0,
         "components": {"market_size": {"value": 3.1}}}]}) is True

    # وبشكل DataPoint الحي (dataclass بحقل value) — نفس ما يمرّره المحرّك.
    class _DP:
        def __init__(self, value):
            self.value = value
    assert result_is_substantive({"markets": [
        {"confidence": 0, "components": {"m": _DP(7)}}]}) is True
    assert result_is_substantive({"markets": [
        {"confidence": 0, "components": {"m": _DP(None)}}]}) is False


def _mock_engine_result(monkeypatch, result: dict):
    import silk_platform.engine_bridge as eb
    monkeypatch.setattr(eb, "_run_engine",
                        lambda product, hs_code, market_pref, *_a, **_k: dict(result))
    return eb


def _launch(cl, tok, study_id: int):
    r = cl.post(f"/platform/studies/{study_id}/launch", headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


# ── القفل ١: كلها None ⇒ مسودّة + سبب + إرجاع حصّة ──────────────────────────
def test_empty_completion_reverts_to_draft_with_declared_reason_and_refund(
        monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        acc = make_factory("gold", "empty-run@f.local")
        eb = _mock_engine_result(monkeypatch, {
            "classified": True, "analysis_id": 424242,
            "data_economics": {"live_fetches": 9, "store_hits": 0,
                               "cache_hits": 0},
            "markets": [{"country": "الإمارات", "total_score": 0.0,
                         "confidence": 0.0,
                         "components": {"market_size": {"value": None}}}]})
        tok = login(cl, "empty-run@f.local", PW)
        sid = make_product_study(acc["account_id"], acc["user_id"], "تمور")
        _launch(cl, tok, sid)
        assert eb.wait_idle()

        row = cl.get(f"/platform/studies/{sid}", headers=hdr(tok)).json()
        assert row["state"] == "draft"
        assert "دون أي بيانات من المصادر" in (row.get("run_error") or "")
        assert row.get("analysis_id") in (None, 0)

        # §58 M2: توكيد الإرجاع الحقيقي — القراءة من /entitlements (المصدر
        # الذي تعرضه الواجهة فعلاً) بلا أي شرط: التشغيلة الفارغة لا تُحسب.
        ent = cl.get("/platform/entitlements", headers=hdr(tok)).json()
        assert ent["studies_used"] == 0, ent


# ── القفل ٢: نقطة واحدة حقيقية ⇒ مكتملة ─────────────────────────────────────
def test_single_real_datapoint_is_enough_to_complete(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        acc = make_factory("gold", "one-dp@f.local")
        eb = _mock_engine_result(monkeypatch, {
            "classified": True, "analysis_id": 424243,
            "markets": [{"country": "الإمارات", "total_score": 0.1,
                         "confidence": 0.0,
                         "components": {"market_size": {"value": 1234.5}}}]})
        tok = login(cl, "one-dp@f.local", PW)
        sid = make_product_study(acc["account_id"], acc["user_id"], "تمور")
        _launch(cl, tok, sid)
        assert eb.wait_idle()
        row = cl.get(f"/platform/studies/{sid}", headers=hdr(tok)).json()
        assert row["state"] == "completed"
        assert row["analysis_id"] == 424243


# ── القفل ٣: run_stats للأدمِن ولا يتسرّب للمصنع ────────────────────────────
def test_run_stats_stored_admin_visible_and_stripped_from_factory(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        acc = make_factory("gold", "stats@f.local")
        _mock = {
            "classified": True, "analysis_id": 424244,
            "data_economics": {"live_fetches": 3, "store_hits": 2,
                               "cache_hits": 1},
            "markets": [{"country": "الإمارات", "confidence": 0.6,
                         "components": {}}]}
        eb = _mock_engine_result(monkeypatch, _mock)
        tok = login(cl, "stats@f.local", PW)
        sid = make_product_study(acc["account_id"], acc["user_id"], "تمور")
        _launch(cl, tok, sid)
        assert eb.wait_idle()

        atok = login(cl, "admin@silk.local", "AdminPass1")
        rows = cl.get("/platform/admin/studies",
                      headers=hdr(atok)).json()["studies"]
        mine = next(r for r in rows if r["id"] == sid)
        rs = mine.get("run_stats")
        assert isinstance(rs, dict)
        assert rs["live"] == 3 and rs["store"] == 2 and rs["cache"] == 1
        assert isinstance(rs["duration_s"], (int, float))

        # صفوف المصنع (قائمة + مفردة) لا تحمل المفتاح إطلاقاً — تجريد بنيوي
        # في المستودع (run_stats ∈ _COST_KEYS).
        flist = cl.get("/platform/studies", headers=hdr(tok)).json()["studies"]
        assert all("run_stats" not in r for r in flist)
        frow = cl.get(f"/platform/studies/{sid}", headers=hdr(tok)).json()
        assert "run_stats" not in frow


def test_run_stats_survives_failure_path_too(monkeypatch):
    """فشل التصنيف يخزّن العدّادات أيضاً — التشخيص لا يضيع مع الفشل."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        acc = make_factory("gold", "stats-fail@f.local")
        eb = _mock_engine_result(monkeypatch, {
            "classified": False, "analysis_id": 424245,
            "hs_note": "لا مرشّح", "markets": [],
            "data_economics": {"live_fetches": 1, "store_hits": 0,
                               "cache_hits": 0}})
        tok = login(cl, "stats-fail@f.local", PW)
        sid = make_product_study(acc["account_id"], acc["user_id"], "منتج غامض")
        _launch(cl, tok, sid)
        assert eb.wait_idle()
        atok = login(cl, "admin@silk.local", "AdminPass1")
        rows = cl.get("/platform/admin/studies",
                      headers=hdr(atok)).json()["studies"]
        mine = next(r for r in rows if r["id"] == sid)
        assert mine["state"] == "draft"
        assert (mine.get("run_stats") or {}).get("live") == 1


# ── القفل ٤: نقطة التشخيص — دور + معدل + بلا شبكة ───────────────────────────
def test_admin_diagnostics_is_admin_only_throttled_and_mocked(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        acc = make_factory("silver", "diag@f.local")
        ftok = login(cl, "diag@f.local", PW)
        assert cl.get("/platform/admin/diagnostics",
                      headers=hdr(ftok)).status_code == 403

        calls = {"n": 0}

        def _fake_diag(year: int = 2022):
            calls["n"] += 1
            return {"overall": "unreachable", "agents_can_work": False,
                    "sources": [{"name": "UN Comtrade", "state": "unreachable",
                                 "detail": "مُحاكى", "hint": "أضِف المفتاح"}]}

        import silk_diagnostics
        monkeypatch.setattr(silk_diagnostics, "run_diagnostics", _fake_diag)
        atok = login(cl, "admin@silk.local", "AdminPass1")
        r = cl.get("/platform/admin/diagnostics", headers=hdr(atok))
        assert r.status_code == 200
        body = r.json()
        assert body["overall"] == "unreachable"
        assert body["sources"][0]["name"] == "UN Comtrade"
        assert calls["n"] == 1

        # المعدل: السقف الافتراضي ١٠ في النافذة — النداء الحادي عشر 429 برمز
        # معلَن (المصادر الحية لا تُستنزف بالتحديث المتكرر).
        codes = [cl.get("/platform/admin/diagnostics",
                        headers=hdr(atok)).status_code for _ in range(10)]
        assert codes[-1] == 429
        last = cl.get("/platform/admin/diagnostics", headers=hdr(atok))
        assert last.status_code == 429
        assert last.json()["detail"]["error"] == "diagnostics_throttled"


def test_admin_diagnostics_is_audited(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        import silk_diagnostics
        monkeypatch.setattr(silk_diagnostics, "run_diagnostics",
                            lambda year=2022: {"overall": "ok", "sources": []})
        atok = login(cl, "admin@silk.local", "AdminPass1")
        assert cl.get("/platform/admin/diagnostics",
                      headers=hdr(atok)).status_code == 200
        from silk_platform.db import connect
        conn = connect()
        try:
            n = conn.execute("SELECT COUNT(*) FROM audit_log "
                             "WHERE action = 'diagnostics_run'").fetchone()[0]
        finally:
            conn.close()
        assert n == 1
