"""تغطية السقف المدفوع على أسطح المنصّة (find all gaps مجموعة 3 — درس 189).

قرار المالك 2026-08-27 (F4/F10):
- F4: `admin/diagnostics` يُطلق مسابير مدفوعة حيّة بمفاتيح الخادم بلا حجزٍ من
  السقف المدفوع اليومي (نظيرتُه في المحرّك تحجز) — أُضيف الحجز بنفس عقد المحرّك.
- F10: `classify-image` يحجز من السقف **المشترك** بلا خانقٍ لكل حساب — مستأجرٌ
  واحد كان يستنزف ميزانية الكل بحلقة؛ أُضيف خانق `vision|<account>`.

Hermetic؛ منصّة معزولة + دفتر استخدام معزول (conftest).
"""
from __future__ import annotations

from tests.platform_helpers import client, hdr, login, make_factory, seed


def _seed_throttle_rows(ident: str, n: int) -> None:
    """امْلأ عدّاد هويّة إلى السقف (صفوف طازجة داخل النافذة)."""
    import datetime
    from silk_platform import db as pdb
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    conn = pdb.connect()
    try:
        for _ in range(n):
            conn.execute(
                "INSERT INTO login_attempts (identity, created_at) VALUES (?,?)",
                (ident, now))
        conn.commit()
    finally:
        conn.close()


# ── F10: خانق الرؤية لكل حساب ─────────────────────────────────────────────

def test_classify_image_is_throttled_per_account(monkeypatch):
    """السقف 20/نافذة؛ العدّاد ممتلئ ⇒ النداء التالي 429 قبل لمس الصورة —
    فلا يستنزف مستأجرٌ واحد السقف المشترك بحلقة."""
    seed(monkeypatch)
    fac = make_factory("gold", "vision@f.example")
    _seed_throttle_rows(f"vision|{fac['account_id']}", 20)   # الهويّة الحرفية
    with client() as cl:
        tok = login(cl, fac["email"], fac["password"])
        r = cl.post("/platform/classify-image", json={"image_id": 1},
                    headers=hdr(tok))
        assert r.status_code == 429, r.text
        assert r.json()["detail"]["error"] == "vision_throttled"


def test_vision_prefix_is_registered_for_pruning():
    from silk_platform import throttle
    assert "VISION" in throttle.NAMED_WINDOW_DEFAULTS


# ── F4: حجز السقف المدفوع في التشخيص ──────────────────────────────────────

def test_diagnostics_reserves_from_the_daily_paid_cap(monkeypatch):
    monkeypatch.setenv("SILK_PAID_DAILY_CAP", "0")   # السقف مُستنفَد
    monkeypatch.delenv("SILK_DIAG_EXEMPT", raising=False)
    info = seed(monkeypatch)
    with client() as cl:
        tok = login(cl, info["admin"]["email"], info["admin"]["password"])
        r = cl.get("/platform/admin/diagnostics", headers=hdr(tok))
        assert r.status_code == 429, r.text
        assert r.json()["detail"]["error"] == "daily_paid_cap_exhausted"


def test_diagnostics_cap_reservation_is_exemptible(monkeypatch):
    """الإعفاء الصريح يتخطّى الحجز (لا 429-سقف) — عقد المحرّك نفسه."""
    monkeypatch.setenv("SILK_PAID_DAILY_CAP", "0")
    monkeypatch.setenv("SILK_DIAG_EXEMPT", "1")
    info = seed(monkeypatch)
    with client() as cl:
        tok = login(cl, info["admin"]["email"], info["admin"]["password"])
        r = cl.get("/platform/admin/diagnostics", headers=hdr(tok))
        # قد يعيد 200 أو 503 (وحدات المحرّك) لكن **ليس** 429-السقف.
        assert not (r.status_code == 429
                    and r.json().get("detail", {}).get("error")
                    == "daily_paid_cap_exhausted"), r.text
