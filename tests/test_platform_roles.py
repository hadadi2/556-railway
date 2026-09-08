"""اختبارات الأدوار (القسم ١٣: ROLES) — Section 13 role acceptance.

Analyst: 200 على المجمّعات، 403 على أي تفصيل/إنشاء/إرسال/مفتاح قتل/دفتر.
Admin: 200 على المجمّعات/الخزنة، 403 على محتوى المصنع/PII؛ التمويل قيدان
ذرّيان بختم الأدمِن؛ مفتاح القتل يضبط العلم + قيد تدقيق.
Factory: 403 على كل نقاط الأدمِن؛ لا يرى تدقيق حساب آخر.
"""
from platform_helpers import client, hdr, login, seed
from silk_platform import db as pdb


def _tokens(monkeypatch):
    info = seed(monkeypatch)
    cl = client()
    return cl, info, {
        "admin": login(cl, info["admin"]["email"], info["admin"]["password"]),
        "analyst": login(cl, info["analyst"]["email"], info["analyst"]["password"]),
        "fa": login(cl, info["factory_a"]["email"], info["factory_a"]["password"]),
        "fb": login(cl, info["factory_b"]["email"], info["factory_b"]["password"]),
    }


# ── ANALYST ──────────────────────────────────────────────────────────────────
def test_analyst_aggregates_200_details_403(monkeypatch):
    cl, info, tk = _tokens(monkeypatch)
    # دراسة مصنع موجودة — a factory study exists.
    study = cl.post("/platform/studies", headers=hdr(tk["fa"]),
                    json={"title_en": "S"}).json()
    assert cl.get("/platform/analyst/aggregates", headers=hdr(tk["analyst"])
                  ).status_code == 200
    # 403 على كل تفصيل/إنشاء/إرسال/مفتاح قتل/دفتر.
    assert cl.get(f"/platform/studies/{study['id']}", headers=hdr(tk["analyst"])
                  ).status_code == 403
    assert cl.post("/platform/studies", headers=hdr(tk["analyst"]),
                   json={"title_en": "x"}).status_code == 403
    assert cl.get("/platform/wallet/ledger", headers=hdr(tk["analyst"])
                  ).status_code == 403
    assert cl.post(f"/platform/studies/{study['id']}/launch",
                   headers=hdr(tk["analyst"]), json={}).status_code == 403
    assert cl.post("/platform/admin/fund", headers=hdr(tk["analyst"]),
                   json={"account_id": 1, "amount_cents": 1}).status_code == 403


# ── ADMIN ────────────────────────────────────────────────────────────────────
def test_admin_aggregates_and_vault_200(monkeypatch):
    cl, info, tk = _tokens(monkeypatch)
    m = cl.get("/platform/admin/metrics", headers=hdr(tk["admin"]))
    assert m.status_code == 200
    assert m.json()["vault_balance_cents"] > 0  # seeded vault capitalization
    assert "accounts_by_tier" in m.json()


def test_admin_opens_a_factory_study_and_the_open_is_audited(monkeypatch):
    """قرار المالك 2026-08-19: «المفروض الأدمن يشوف الدراسات».

    كان الأدمِن يرتدّ 403 على دراسة مصنع (جدار المحتوى) — فبدا جدولُ «كل
    الدراسات» بلا زرّ تقرير. فُتحت **الدراسات وحدها**، وثمنُ الفتح قيدٌ
    تدقيقي باسم من فتح: `admin_study_view`. Every open leaves a name.
    """
    cl, info, tk = _tokens(monkeypatch)
    study = cl.post("/platform/studies", headers=hdr(tk["fa"]),
                    json={"title_en": "S"}).json()
    r = cl.get(f"/platform/studies/{study['id']}", headers=hdr(tk["admin"]))
    assert r.status_code == 200, r.text
    assert r.json()["id"] == study["id"]
    conn = pdb.connect()
    try:
        rows = [dict(x) for x in conn.execute(
            "SELECT * FROM audit_log WHERE action = 'admin_study_view'").fetchall()]
    finally:
        conn.close()
    assert len(rows) == 1, rows
    assert rows[0]["user_id"] == info["admin"]["id"]
    assert int(rows[0]["resource_id"]) == study["id"]


def test_admin_403_stays_on_factory_pii_and_images(monkeypatch):
    """ما فُتح هو الدراسات فقط — الصور وبريد المستخدمين خلف الجدار كما كانا."""
    cl, info, tk = _tokens(monkeypatch)
    r = cl.post("/platform/images", headers=hdr(tk["fa"]),
                files={"file": ("a.png", b"\x89PNG\r\n\x1a\n-fake", "image/png")})
    image = r.json()
    assert cl.get(f"/platform/images/{image['id']}/signed-url",
                  headers=hdr(tk["admin"])).status_code == 403
    # (مسار المستخدمين الفرعيين لم يعد موجوداً أصلاً — حُذفت المقاعد نهائياً
    #  بقرار المالك 2026-08-19؛ يحرسه test_platform_seats_deletion_guard.)
    assert cl.get("/platform/users", headers=hdr(tk["admin"])).status_code == 404


def test_admin_funding_two_atomic_entries_with_admin_actor(monkeypatch):
    cl, info, tk = _tokens(monkeypatch)
    fa = info["factory_a"]["account_id"]
    vault = info["vault_account_id"]
    r = cl.post("/platform/admin/fund", headers=hdr(tk["admin"]),
                json={"account_id": fa, "amount_cents": 2500})
    assert r.status_code == 200
    conn = pdb.connect()
    try:
        rows = [dict(x) for x in conn.execute(
            "SELECT * FROM ledger_entries WHERE operation_type = 'wallet_funded' "
            "AND actor_user_id = ? ORDER BY id", (info["admin"]["id"],)).fetchall()]
        # قيد افتتاح الخزنة + خصم الخزنة + إيداع المصنع = ثلاثة بختم الأدمِن.
        debit = [x for x in rows if x["account_id"] == vault and x["amount"] == -2500]
        credit = [x for x in rows if x["account_id"] == fa and x["amount"] == 2500]
        assert len(debit) == 1 and len(credit) == 1
        assert debit[0]["actor_user_id"] == credit[0]["actor_user_id"] == info["admin"]["id"]
    finally:
        conn.close()


def test_admin_oversees_all_studies_without_pii(monkeypatch):
    """إشراف الأدمِن (قرار 2026-08-17): يرى كل الدراسات ببياناتها التشغيلية
    فقط — لا بريد مستخدمين (جدار PII كما هو)."""
    cl, info, tk = _tokens(monkeypatch)
    cl.post("/platform/studies", headers=hdr(tk["fa"]),
            json={"product": "تمور", "market_pref": "ARE"})
    r = cl.get("/platform/admin/studies", headers=hdr(tk["admin"]))
    assert r.status_code == 200
    rows = r.json()["studies"]
    assert any(x["product"] == "تمور" for x in rows)
    import json as _json
    assert "@" not in _json.dumps(rows, ensure_ascii=False)


# ── FACTORY ──────────────────────────────────────────────────────────────────
def test_factory_403_on_all_admin_endpoints(monkeypatch):
    cl, info, tk = _tokens(monkeypatch)
    fa = tk["fa"]
    assert cl.get("/platform/admin/metrics", headers=hdr(fa)).status_code == 403
    assert cl.post("/platform/admin/fund", headers=hdr(fa),
                   json={"account_id": info["factory_b"]["account_id"],
                         "amount_cents": 100}).status_code == 403
    assert cl.get("/platform/admin/studies", headers=hdr(fa)).status_code == 403
    assert cl.get("/platform/admin/audit", headers=hdr(fa)).status_code == 403


def test_factory_cannot_see_other_accounts_audit(monkeypatch):
    cl, info, tk = _tokens(monkeypatch)
    # A ينشئ دراسة (يولّد قيد تدقيق لحسابه) — A's action logs to A's account.
    cl.post("/platform/studies", headers=hdr(tk["fa"]), json={"title_en": "A"})
    b_audit = cl.get("/platform/audit", headers=hdr(tk["fb"])).json()
    assert b_audit["account_id"] == info["factory_b"]["account_id"]
    assert all(row["account_id"] == info["factory_b"]["account_id"]
               for row in b_audit["audit"])
