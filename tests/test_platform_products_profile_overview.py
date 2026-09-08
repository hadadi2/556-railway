"""أقفال موجة B الخلفية — المنتجات + البروفايل + نظرة عامة (قرار 2026-08-18).

قرارات المالك المقفولة هنا:
- «اضف فوقها المتنجات»: كتالوج مستأجَري كامل (ترحيل 010) يغذي الدراسات —
  ربط الدراسة بمنتجٍ مملوك حصراً، والحذف يفكّ الربط ولا يمسّ دراسة.
- «بروفايل الشخص ويعدل منها كلمة المرور وبيانات المستخدم»: تغيير ذاتي لكلمة
  المرور (الحالية تُتحقَّق، السياسة تُفرَض، بقية الجلسات تُبطَل والجلسة
  الحالية تبقى) + تعديل الاسمين لأي دور.
- «داشبورد عام عن الدراسات الاسواق»: تجميع درجات الأسواق من قاعدة المحرّك
  عبر analysis_id — تعذُّرها فجوة معلنة لا انهيار ولا اختلاق.
"""
from __future__ import annotations

import pytest

from tests.platform_helpers import hdr, login, make_factory, seed, client


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    info = seed(monkeypatch)
    cl = client()
    fa = make_factory("silver", "prod-a@f.local")
    fb = make_factory("gold", "prod-b@f.local")
    ta = login(cl, fa["email"], fa["password"])
    tb = login(cl, fb["email"], fb["password"])
    return {"cl": cl, "fa": fa, "fb": fb, "ta": ta, "tb": tb, "info": info}


def _mk_product(cl, tok, **over):
    body = {"name": "تمر سكري فاخر", "description": "عبوة 1كغ",
            "hs_code": "080410", **over}
    r = cl.post("/platform/products", json=body, headers=hdr(tok))
    assert r.status_code == 200, r.text
    return r.json()


# ═══════════ المنتجات ═══════════
def test_product_crud_and_studies_count(env):
    cl, tok = env["cl"], env["ta"]
    p = _mk_product(cl, tok)
    assert p["name"] == "تمر سكري فاخر" and p["hs_code"] == "080410"
    r = cl.post("/platform/studies", headers=hdr(tok),
                json={"product": p["name"], "hs_code": p["hs_code"],
                      "market_pref": "ARE", "product_id": p["id"]})
    assert r.status_code == 200, r.text
    out = cl.get("/platform/products", headers=hdr(tok)).json()["products"]
    assert out[0]["studies_count"] == 1
    upd = cl.patch(f"/platform/products/{p['id']}",
                   json={"description": "عبوة 500غ"}, headers=hdr(tok))
    assert upd.json()["description"] == "عبوة 500غ"


def test_product_requires_name_and_valid_hs(env):
    r = env["cl"].post("/platform/products", json={"name": "  "},
                       headers=hdr(env["ta"]))
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "product_no_name"
    r = env["cl"].post("/platform/products",
                       json={"name": "عسل", "hs_code": "abc"},
                       headers=hdr(env["ta"]))
    assert r.status_code == 422


def test_product_cross_tenant_is_404_and_study_link_is_owned_only(env):
    cl = env["cl"]
    pb = _mk_product(cl, env["tb"], name="زيتون")
    # قراءة/تعديل/حذف منتج مستأجر آخر = 404 (لا تسريب وجود).
    assert cl.patch(f"/platform/products/{pb['id']}", json={"name": "x"},
                    headers=hdr(env["ta"])).status_code == 404
    assert cl.delete(f"/platform/products/{pb['id']}",
                     headers=hdr(env["ta"])).status_code == 404
    # ربط دراسة بمنتج مستأجر آخر = 422.
    r = cl.post("/platform/studies", headers=hdr(env["ta"]),
                json={"product": "زيتون", "product_id": pb["id"]})
    assert r.status_code == 422
    # والمنتج سليم لدى صاحبه.
    assert cl.get("/platform/products",
                  headers=hdr(env["tb"])).json()["products"][0]["name"] == "زيتون"


def test_product_delete_unlinks_but_keeps_studies(env):
    cl, tok = env["cl"], env["ta"]
    p = _mk_product(cl, tok)
    s = cl.post("/platform/studies", headers=hdr(tok),
                json={"product": p["name"], "product_id": p["id"]}).json()
    assert cl.delete(f"/platform/products/{p['id']}",
                     headers=hdr(tok)).json() == {"ok": True}
    row = cl.get(f"/platform/studies/{s['id']}", headers=hdr(tok)).json()
    assert row["product_id"] is None          # فُكّ الربط
    assert row["product"] == p["name"]        # الدراسة نفسها باقية بنصّها
    assert cl.get("/platform/products",
                  headers=hdr(tok)).json()["products"] == []


def test_products_are_factory_only(env):
    admin = login(env["cl"], "admin@silk.local", "AdminPass1")
    assert env["cl"].get("/platform/products",
                         headers=hdr(admin)).status_code == 403


# ═══════════ البروفايل ═══════════
def test_patch_me_names_for_factory_and_analyst(env):
    cl = env["cl"]
    r = cl.patch("/platform/me", json={"first_name": "عبدالله",
                                       "last_name": "المصنع"},
                 headers=hdr(env["ta"]))
    assert r.status_code == 200, r.text
    me = cl.get("/platform/me", headers=hdr(env["ta"])).json()
    assert (me["first_name"], me["last_name"]) == ("عبدالله", "المصنع")
    # المحلّل — الدور الذي كان بلا أي مسار لتعديل اسمه.
    analyst = login(cl, env["info"]["analyst"]["email"],
                    env["info"]["analyst"]["password"])
    assert cl.patch("/platform/me", json={"first_name": "محلّل"},
                    headers=hdr(analyst)).status_code == 200
    assert cl.get("/platform/me",
                  headers=hdr(analyst)).json()["first_name"] == "محلّل"
    # جسم فارغ = 422 لا تحديث صامت بلا حقول.
    assert cl.patch("/platform/me", json={},
                    headers=hdr(env["ta"])).status_code == 422


def test_me_carries_identity_for_profile_card(env):
    """بطاقة الحساب بالنمط العالمي (تصحيح المالك 2026-08-19): «الملف التعريفي»
    يعرض اسم المصنع وتاريخ الانضمام — GET /me يحملهما من accounts.name
    وusers.created_at، عرضاً فقط (تعديل اسم الحساب صلاحية أدمِن)."""
    cl = env["cl"]
    me = cl.get("/platform/me", headers=hdr(env["ta"])).json()
    assert me["account_name"] == "Factory-silver"     # اسم حساب make_factory
    assert me["member_since"] and me["member_since"][:2] == "20"  # ختم ISO
    # الدورَان الآخران يحملان المفتاحين أيضاً (قيمة أو None معلَن — لا KeyError).
    analyst = login(cl, env["info"]["analyst"]["email"],
                    env["info"]["analyst"]["password"])
    me_an = cl.get("/platform/me", headers=hdr(analyst)).json()
    assert "account_name" in me_an and me_an["member_since"]


def test_change_password_full_contract(env):
    cl, fa = env["cl"], env["fa"]
    tok_a = env["ta"]
    tok_b = login(cl, fa["email"], fa["password"])   # جلسة ثانية
    # حالية خاطئة = 403 معلَن.
    r = cl.post("/platform/me/password",
                json={"current_password": "Wrong123", "new_password": "NewPass12"},
                headers=hdr(tok_a))
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "wrong_current_password"
    # جديدة تخالف السياسة = 422 (ولا تغيير).
    r = cl.post("/platform/me/password",
                json={"current_password": fa["password"], "new_password": "weak"},
                headers=hdr(tok_a))
    assert r.status_code == 422
    # النجاح: الجلسة الحالية تبقى، الثانية تُبطَل، القديمة لا تدخل والجديدة تدخل.
    r = cl.post("/platform/me/password",
                json={"current_password": fa["password"],
                      "new_password": "NewPass12"},
                headers=hdr(tok_a))
    assert r.status_code == 200, r.text
    assert cl.get("/platform/me", headers=hdr(tok_a)).status_code == 200
    assert cl.get("/platform/me", headers=hdr(tok_b)).status_code == 401
    assert cl.post("/platform/auth/login",
                   json={"email": fa["email"],
                         "password": fa["password"]}).status_code == 401
    assert login(cl, fa["email"], "NewPass12")


# ═══════════ أقفال مراجعة §58 (موجة B) ═══════════
def test_change_password_guessing_is_throttled(env):
    """تخمين «الحالية» من جلسة مسروقة يُخنَق كالدخول تماماً (§58)."""
    cl, tok = env["cl"], env["ta"]
    for _ in range(10):
        r = cl.post("/platform/me/password",
                    json={"current_password": "Guess123", "new_password": "NewPass12"},
                    headers=hdr(tok))
        assert r.status_code == 403
    r = cl.post("/platform/me/password",
                json={"current_password": "Guess123", "new_password": "NewPass12"},
                headers=hdr(tok))
    assert r.status_code == 429


def test_password_change_is_audited_atomically(env):
    """قيد `password_changed` يُكتب مع التغيير نفسه — لا تغيير أمني بلا أثر."""
    cl, fa = env["cl"], env["fa"]
    tok = login(cl, fa["email"], fa["password"])
    r = cl.post("/platform/me/password",
                json={"current_password": fa["password"],
                      "new_password": "Audited12"}, headers=hdr(tok))
    assert r.status_code == 200, r.text
    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_log WHERE action = "
            "'password_changed' AND account_id = ?",
            (fa["account_id"],)).fetchone()
        assert int(row["c"]) == 1
    finally:
        conn.close()


def test_hs_code_rejects_non_ascii_digits_everywhere(env):
    """«٠٨٠٤١٠» الهندية تُرفض في المنتجات والدراسات معاً — لا رمز لا يطابق شيئاً."""
    cl, tok = env["cl"], env["ta"]
    for path, body in (("/platform/products", {"name": "تمور", "hs_code": "٠٨٠٤١٠"}),
                       ("/platform/studies", {"product": "تمور", "hs_code": "٠٨٠٤١٠"})):
        r = cl.post(path, json=body, headers=hdr(tok))
        assert r.status_code == 422, f"{path}: {r.text}"


def test_product_patch_without_fields_is_422_and_unaudited(env):
    """جسم بلا حقل قابل للكتابة = 422 — لا قيد «product_updated» كاذباً (§58)."""
    cl, tok = env["cl"], env["ta"]
    p = _mk_product(cl, tok)
    r = cl.patch(f"/platform/products/{p['id']}", json={}, headers=hdr(tok))
    assert r.status_code == 422
    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_log WHERE action = "
            "'product_updated' AND account_id = ?",
            (env["fa"]["account_id"],)).fetchone()
        assert int(row["c"]) == 0
    finally:
        conn.close()


def test_overview_truncation_is_declared_not_silent(env):
    """13 سوقاً: المخطط أفضل 12، والعدّاد 13، والاقتطاع مُعلَن نصاً (§58)."""
    from silk_storage import init_db, save_analysis
    init_db(None)
    markets = [{"country": f"C{i}", "iso3": f"M{i:02d}",
                "total_score": 0.9 - i * 0.05, "confidence": 0.5}
               for i in range(13)]
    aid = save_analysis({"product": "تمور", "hs_code": "080410",
                         "markets": markets}, None)
    _completed_study_with_analysis(env["fa"]["account_id"], "تمور", "ARE", aid)
    out = env["cl"].get("/platform/overview", headers=hdr(env["ta"])).json()
    assert out["markets_studied"] == 13
    assert len(out["markets"]) == 12
    assert "12" in out["markets_note"] and "13" in out["markets_note"]


# ═══════════ نظرة عامة ═══════════
def _completed_study_with_analysis(account_id, product, market, analysis_id):
    from silk_platform import db as pdb
    from silk_platform.db import now_iso
    conn = pdb.connect()
    try:
        now = now_iso()
        conn.execute(
            "INSERT INTO studies (owner_id, title_en, state, product, "
            "market_pref, analysis_id, completed_at, created_at, updated_at) "
            "VALUES (?,?, 'completed', ?, ?, ?, ?, ?, ?)",
            (account_id, product, product, market, analysis_id, now, now, now))
        conn.commit()
    finally:
        conn.close()


def test_overview_aggregates_markets_from_engine_scores(env):
    from silk_storage import init_db, save_analysis
    init_db(None)
    a1 = save_analysis({"product": "تمور", "hs_code": "080410", "markets": [
        {"country": "الإمارات", "iso3": "ARE", "total_score": 0.61,
         "confidence": 0.5},
        {"country": "قطر", "iso3": "QAT", "total_score": 0.42,
         "confidence": 0.4}]}, None)
    a2 = save_analysis({"product": "عسل", "hs_code": "040900", "markets": [
        {"country": "الإمارات", "iso3": "ARE", "total_score": 0.55,
         "confidence": 0.6}]}, None)
    _completed_study_with_analysis(env["fa"]["account_id"], "تمور", "ARE", a1)
    _completed_study_with_analysis(env["fa"]["account_id"], "عسل", "ARE", a2)
    out = env["cl"].get("/platform/overview", headers=hdr(env["ta"])).json()
    assert out["studies"]["completed"] == 2
    isos = [m["iso3"] for m in out["markets"]]
    assert isos == ["ARE", "QAT"]             # الأفضل لكل سوق، مرتبة تنازلياً
    assert out["markets"][0]["score"] == 0.61  # أعلى درجة للإمارات لا 0.55
    assert out["best_market"]["iso3"] == "ARE"
    assert out["recent"] and len(out["recent"]) <= 5
    # لا مفتاح تكلفة في أي حمولة نظرة عامة.
    assert "data_economics" not in str(out)


def test_overview_engine_gap_is_declared_not_fabricated(env, monkeypatch):
    _completed_study_with_analysis(env["fa"]["account_id"], "تمور", "ARE", 999)
    import silk_storage
    def boom(ids):
        raise OSError("engine store unreachable")
    monkeypatch.setattr(silk_storage, "market_scores_for_analyses", boom)
    out = env["cl"].get("/platform/overview", headers=hdr(env["ta"])).json()
    assert out["markets"] == []
    assert "غير متاحة" in out["markets_note"]
    assert out["best_market"] is None


def test_overview_is_factory_only_and_tenant_scoped(env):
    admin = login(env["cl"], "admin@silk.local", "AdminPass1")
    assert env["cl"].get("/platform/overview",
                         headers=hdr(admin)).status_code == 403
    _completed_study_with_analysis(env["fb"]["account_id"], "زيتون", "FRA", 555)
    out = env["cl"].get("/platform/overview", headers=hdr(env["ta"])).json()
    assert out["studies"]["completed"] == 0   # دراسات المستأجر الآخر لا تُعدّ
