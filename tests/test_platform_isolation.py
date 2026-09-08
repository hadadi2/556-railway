"""اختبارات العزل بين المستأجرين (القسم ١٣: ISOLATION) — Section 13 isolation.

الحساب A لا يسرد/يقرأ/يعدّل/يحذف كيانات الحساب B (404، لا 403)، ولا يتلاعب
بمعامل الاستعلام ليعبر، والقاعدة تبقى دون تغيير والمحاولات تُسجَّل تدقيقاً.
ربط صورة عابر للمستأجر مرفوض؛ الروابط الموقّعة لا تُولَّد لمالك أجنبي؛
المحفظة/الدفتر حساب المنادي فقط. (كيانات التنقيب حُذفت — قرار مالك 2026-08-17.)
"""
from platform_helpers import client, hdr, login, seed
from silk_platform import db as pdb


def _audit_rows(action=None):
    conn = pdb.connect()
    try:
        sql = "SELECT * FROM audit_log"
        args = ()
        if action:
            sql += " WHERE action = ?"
            args = (action,)
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def _setup(monkeypatch):
    """A ينشئ دراسة وصورة؛ يرجّع (cl, A, B, ids)."""
    info = seed(monkeypatch)
    cl = client()
    ta = login(cl, info["factory_a"]["email"], info["factory_a"]["password"])
    tb = login(cl, info["factory_b"]["email"], info["factory_b"]["password"])
    study = cl.post("/platform/studies", headers=hdr(ta),
                    json={"title_en": "A-Study", "product": "تمور"}).json()
    image = cl.post("/platform/images", headers=hdr(ta),
                    files={"file": ("a.png", b"\x89PNG\r\n\x1a\n-fake-bytes", "image/png")}
                    ).json()
    return cl, ta, tb, info, {"study": study["id"], "image": image["id"]}


def test_list_is_account_scoped(monkeypatch):
    cl, ta, tb, info, ids = _setup(monkeypatch)
    b_studies = cl.get("/platform/studies", headers=hdr(tb)).json()["studies"]
    assert all(s["id"] != ids["study"] for s in b_studies)
    a_studies = cl.get("/platform/studies", headers=hdr(ta)).json()["studies"]
    assert any(s["id"] == ids["study"] for s in a_studies)


def test_read_by_id_cross_tenant_404(monkeypatch):
    cl, ta, tb, info, ids = _setup(monkeypatch)
    assert cl.get(f"/platform/studies/{ids['study']}",
                  headers=hdr(tb)).status_code == 404


def test_query_param_manipulation_cannot_cross_tenant(monkeypatch):
    cl, ta, tb, info, ids = _setup(monkeypatch)
    a_account = info["factory_a"]["account_id"]
    # B يمرّر owner_id=A في الاستعلام — يُتجاهَل تماماً.
    r = cl.get(f"/platform/studies?owner_id={a_account}", headers=hdr(tb))
    assert all(s["id"] != ids["study"] for s in r.json()["studies"])
    # وكذلك دفتر المحفظة — ledger ignores any account_id query param.
    led = cl.get(f"/platform/wallet/ledger?account_id={a_account}", headers=hdr(tb))
    assert led.json()["account_id"] == info["factory_b"]["account_id"]


def test_cross_tenant_patch_404_db_unchanged_audited(monkeypatch):
    cl, ta, tb, info, ids = _setup(monkeypatch)
    before = cl.get(f"/platform/studies/{ids['study']}", headers=hdr(ta)).json()
    r = cl.patch(f"/platform/studies/{ids['study']}", headers=hdr(tb),
                 json={"title_ar": "HACKED", "product": "HACKED"})
    assert r.status_code == 404
    after = cl.get(f"/platform/studies/{ids['study']}", headers=hdr(ta)).json()
    # R6 (FE-8): `title_en` حقلٌ ميت لا يُكتَب — المجسُّ الحيّ `title_ar`/`product`.
    assert after["title_ar"] == before["title_ar"] and after["product"] == before["product"]
    assert "HACKED" not in (str(after["title_ar"]) + str(after["product"]))
    denied = _audit_rows("cross_tenant_write")
    assert any(row["account_id"] == info["factory_b"]["account_id"]
               and str(ids["study"]) == row["resource_id"] for row in denied)


def test_cross_tenant_delete_404_db_unchanged_audited(monkeypatch):
    cl, ta, tb, info, ids = _setup(monkeypatch)
    r = cl.delete(f"/platform/studies/{ids['study']}", headers=hdr(tb))
    assert r.status_code == 404
    # الصفّ لا يزال موجوداً للمالك — still present for the real owner.
    assert cl.get(f"/platform/studies/{ids['study']}",
                  headers=hdr(ta)).status_code == 200
    assert _audit_rows("cross_tenant_delete")


def test_cross_tenant_image_binding_rejected_and_productless_launch_blocked(monkeypatch):
    cl, ta, tb, info, ids = _setup(monkeypatch)
    # B يحاول ربط صورة A بدراسته — 422 عند الإنشاء (ملكية غير مطابقة).
    r = cl.post("/platform/studies", headers=hdr(tb),
                json={"product": "زيتون", "image_id": ids["image"]})
    assert r.status_code == 422
    # وحتى عند التعديل — patch binding a foreign image is rejected too.
    b_study = cl.post("/platform/studies", headers=hdr(tb),
                      json={"title_en": "B2"}).json()
    r2 = cl.patch(f"/platform/studies/{b_study['id']}", headers=hdr(tb),
                  json={"image_id": ids["image"]})
    assert r2.status_code == 422
    # الإطلاق بلا منتج محجوب معلَناً — a productless launch is refused.
    r3 = cl.post(f"/platform/studies/{b_study['id']}/launch", headers=hdr(tb), json={})
    assert r3.status_code == 422
    assert r3.json()["detail"]["error"] == "study_no_product"


def test_signed_url_never_for_foreign_owner(monkeypatch):
    cl, ta, tb, info, ids = _setup(monkeypatch)
    # A (المالك) يحصل على رابط موقّع — owner gets a signed url.
    ok = cl.get(f"/platform/images/{ids['image']}/signed-url", headers=hdr(ta))
    assert ok.status_code == 200 and ok.json()["signed_url"]
    # B لا يحصل على شيء — foreign owner: 404, no url generated.
    bad = cl.get(f"/platform/images/{ids['image']}/signed-url", headers=hdr(tb))
    assert bad.status_code == 404
    assert "signed_url" not in bad.json()


def test_wallet_ledger_returns_own_entries_only(monkeypatch):
    cl, ta, tb, info, ids = _setup(monkeypatch)
    # موّل A وB بمبالغ مختلفة عبر مسار الأدمِن — fund both via the admin path.
    tadmin = login(cl, info["admin"]["email"], info["admin"]["password"])
    cl.post("/platform/admin/fund", headers=hdr(tadmin),
            json={"account_id": info["factory_a"]["account_id"], "amount_cents": 500})
    cl.post("/platform/admin/fund", headers=hdr(tadmin),
            json={"account_id": info["factory_b"]["account_id"], "amount_cents": 900})
    a_led = cl.get("/platform/wallet/ledger", headers=hdr(ta)).json()
    b_led = cl.get("/platform/wallet/ledger", headers=hdr(tb)).json()
    assert all(e["account_id"] == info["factory_a"]["account_id"]
               for e in a_led["entries"])
    assert all(e["account_id"] == info["factory_b"]["account_id"]
               for e in b_led["entries"])
    # A لا يرى قيد 900 الخاص بـ B — A never sees B's 900 credit.
    assert all(e["amount"] != 900 for e in a_led["entries"])
