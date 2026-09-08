"""أقفال إشعارات المنصّة — in-platform notifications locks (قرار 2026-08-18).

القناة المقرَّرة: داخل المنصّة + إشعار المتصفح (لا بريد الآن). الكتابة نظامية
(جسر المحرّك، نفس معاملة الإنهاء — مقفولة في test_platform_deep_mode)؛ هنا
أقفال القراءة/التعليم: النطاق حساب الجلسة حصراً، عدّ غير المقروء دقيق،
التعليم لا يعبر المستأجرين، والمحلّل خارج القناة.
"""
from __future__ import annotations

import pytest

from tests.platform_helpers import hdr, login, make_factory, seed, client


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    info = seed(monkeypatch)
    cl = client()
    fa = make_factory("silver", "na@f.local")
    fb = make_factory("gold", "nb@f.local")
    ta = login(cl, fa["email"], fa["password"])
    tb = login(cl, fb["email"], fb["password"])
    return {"cl": cl, "fa": fa, "fb": fb, "ta": ta, "tb": tb, "info": info}


def _write(account_id, kind="study_completed", title="اكتملت دراسة «تمور»"):
    from silk_platform import db as pdb, notifications
    conn = pdb.connect()
    try:
        nid = notifications.record(conn, account_id=account_id, kind=kind,
                                   title=title, body="التقرير جاهز.",
                                   study_id=5)
        conn.commit()
        return nid
    finally:
        conn.close()


def test_list_is_account_scoped_with_unread_count(env):
    _write(env["fa"]["account_id"])
    _write(env["fa"]["account_id"], kind="study_failed", title="تعثّرت دراسة")
    _write(env["fb"]["account_id"], title="اكتملت دراسة «عسل»")
    ra = env["cl"].get("/platform/notifications", headers=hdr(env["ta"])).json()
    assert ra["unread_count"] == 2
    assert len(ra["notifications"]) == 2
    assert all("عسل" not in n["title"] for n in ra["notifications"])
    rb = env["cl"].get("/platform/notifications", headers=hdr(env["tb"])).json()
    assert rb["unread_count"] == 1
    assert rb["notifications"][0]["title"] == "اكتملت دراسة «عسل»"


def test_mark_read_all_and_by_ids(env):
    n1 = _write(env["fa"]["account_id"])
    _write(env["fa"]["account_id"], kind="study_failed")
    r = env["cl"].post("/platform/notifications/read", json={"ids": [n1]},
                       headers=hdr(env["ta"]))
    assert r.json() == {"ok": True, "marked": 1}
    assert env["cl"].get("/platform/notifications",
                         headers=hdr(env["ta"])).json()["unread_count"] == 1
    r = env["cl"].post("/platform/notifications/read", json={},
                       headers=hdr(env["ta"]))
    assert r.json()["marked"] == 1
    assert env["cl"].get("/platform/notifications",
                         headers=hdr(env["ta"])).json()["unread_count"] == 0


def test_mark_read_empty_list_marks_nothing(env):
    """[] ≠ «الكل» — الحذف الكامل للحقل وحده يعني الكل (§58 موجة A)."""
    _write(env["fa"]["account_id"])
    r = env["cl"].post("/platform/notifications/read", json={"ids": []},
                       headers=hdr(env["ta"]))
    assert r.json() == {"ok": True, "marked": 0}
    assert env["cl"].get("/platform/notifications",
                         headers=hdr(env["ta"])).json()["unread_count"] == 1


def test_mark_read_cannot_cross_tenants(env):
    nb = _write(env["fb"]["account_id"])
    r = env["cl"].post("/platform/notifications/read", json={"ids": [nb]},
                       headers=hdr(env["ta"]))
    assert r.json()["marked"] == 0          # صف مستأجر آخر لا يُمَسّ
    assert env["cl"].get("/platform/notifications",
                         headers=hdr(env["tb"])).json()["unread_count"] == 1


def test_bad_ids_shape_is_422_and_analyst_is_outside_the_channel(env):
    r = env["cl"].post("/platform/notifications/read", json={"ids": ["x"]},
                       headers=hdr(env["ta"]))
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "bad_notification_ids"
    analyst = login(env["cl"], env["info"]["analyst"]["email"],
                    env["info"]["analyst"]["password"])
    assert env["cl"].get("/platform/notifications",
                         headers=hdr(analyst)).status_code == 403
