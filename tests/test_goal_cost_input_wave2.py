"""هدف الدراسة الاحترافية — الموجة ٢: تكلفة الإنتاج من المستخدم (البند ٢).

الحادثة المؤسِّسة: كل رقم متعذّر في «أرقام القرار» يعود لمدخل واحد غائب —
تكلفة إنتاج المصدّر، وهي في يده لا في أي مصدر خارجي، والمنصّة لم تكن تسألها
على نموذج الدراسة أصلاً؛ والثغرة الحاملة: بطاقة المنتج كانت تسقط صامتة على
مسار المنصّة (`_platform_deep_run` بلا `product_card` في توقيعه). القواعد
المقفولة هنا: الحقل على نموذج الدراسة بوحدة السوق؛ التكلفة الأحدث تفوز؛
سطر الفتح الواحد بدل خمس «غير محسوب»؛ وسدّ الثغرة الحاملة بنيوياً.
"""
import inspect
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import platform_helpers as H

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── دمج التكلفة في البطاقة (المسار المباشر) ────────────────────────────────

def test_apply_production_cost_overrides_and_builds():
    import api
    assert api._apply_production_cost({"cost_per_unit": 9.0}, 3.5) == \
        {"cost_per_unit": 3.5}
    assert api._apply_production_cost(None, 2.0) == {"cost_per_unit": 2.0}


def test_apply_production_cost_never_invents_or_drops():
    import api
    card = {"cost_per_unit": 9.0, "unit": "كجم"}
    for bad in (None, "", "x", 0, -1):
        assert api._apply_production_cost(card, bad) == card
        assert api._apply_production_cost(None, bad) is None


def test_research_request_rejects_non_positive_cost_before_any_spend():
    """التحقق على مستوى النموذج (gt=0) — يرفض قبل أي حجز ميزانية."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    import api
    client = TestClient(api.app)
    with patch("requests.sessions.Session.request",
               side_effect=OSError("network disabled for offline test")):
        r = client.post("/research", json={
            "product": "حليب", "market": "JOR",
            "production_cost_per_unit": -1})
    assert r.status_code == 422


# ── سدّ الثغرة الحاملة: البطاقة تصل مسار المنصّة ───────────────────────────

def test_platform_runner_accepts_product_card():
    """`_runner_takes(runner, "product_card")` كان يرفضها فتسقط صامتة —
    الاختبارات القديمة قفلت شكل السطر لا وصول البطاقة (ثغرة مثبتة)."""
    import api  # noqa: F401 — تسجيل المغلقة في silk_research_gateway
    import silk_research_gateway as gateway
    from silk_platform.engine_bridge import _runner_takes
    runner = gateway.runner()
    assert runner is not None
    assert _runner_takes(runner, "product_card")


def test_platform_runner_passes_card_into_the_request():
    src = io.open(os.path.join(_ROOT, "api.py"), encoding="utf-8").read()
    i = src.find("def _platform_deep_run")
    body = src[i:i + 2500]
    assert "product_card: dict | None = None" in body
    assert "product_card=(product_card or None)" in body


# ── تكلفة الدراسة تغلب الكتالوج ────────────────────────────────────────────

def test_apply_study_cost_study_wins_over_catalogue():
    from silk_platform.engine_bridge import apply_study_cost
    card = {"cost_per_unit": 9.0, "unit": "كجم"}
    out = apply_study_cost(card, {"production_cost": 3.5}, product="تمور")
    assert out["cost_per_unit"] == 3.5 and out["unit"] == "كجم"


def test_apply_study_cost_builds_alone_with_market_unit():
    from silk_platform.engine_bridge import apply_study_cost
    out = apply_study_cost(None, {"production_cost": 0.4}, product="حليب")
    assert out == {"cost_per_unit": 0.4, "unit": "لتر"}


def test_apply_study_cost_ignores_bad_values():
    from silk_platform.engine_bridge import apply_study_cost
    card = {"cost_per_unit": 9.0}
    for bad in (None, "", "x", 0, -2):
        assert apply_study_cost(card, {"production_cost": bad}) == card
        assert apply_study_cost(None, {"production_cost": bad}) is None
    assert apply_study_cost(card, None) == card


# ── سطح المنصّة: الحقل والنقطة النهائية ────────────────────────────────────

def _factory_client(monkeypatch):
    H.seed(monkeypatch)
    cl = H.client()
    f = H.make_factory("basic", "cost-wave2@factory.local")
    tok = H.login(cl, f["email"], f["password"])
    return cl, H.hdr(tok)


def test_study_stores_and_clears_production_cost(monkeypatch):
    cl, hd = _factory_client(monkeypatch)
    r = cl.post("/platform/studies",
                json={"product": "حليب", "production_cost": 0.42}, headers=hd)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert r.json().get("production_cost") == 0.42
    # الفراغ يمحو صراحةً (عقد E-04) — لا قيمة شبحية من إدخال سابق.
    r2 = cl.patch(f"/platform/studies/{sid}",
                  json={"production_cost": None}, headers=hd)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("production_cost") is None


def test_study_rejects_bad_production_cost(monkeypatch):
    cl, hd = _factory_client(monkeypatch)
    for bad in (-1, 0, "abc"):
        r = cl.post("/platform/studies",
                    json={"product": "تمور", "production_cost": bad},
                    headers=hd)
        assert r.status_code == 422, (bad, r.text)


def test_unit_hint_follows_the_engine_registry(monkeypatch):
    cl, hd = _factory_client(monkeypatch)
    r = cl.get("/platform/unit-hint", params={"product": "حليب"}, headers=hd)
    assert r.status_code == 200
    assert r.json() == {"code": "litre", "label_ar": "لتر"}
    r2 = cl.get("/platform/unit-hint", params={"product": "تمور"}, headers=hd)
    assert r2.json()["code"] == "kg"
    # بلا مصادقة — مرفوض (عميل جديد: عميل الدخول يحمل كوكي الجلسة).
    assert H.client().get("/platform/unit-hint",
                          params={"product": "x"}).status_code in (401, 403)


def test_study_form_carries_the_cost_field():
    page = io.open(os.path.join(_ROOT, "web", "platform.html"),
                   encoding="utf-8").read()
    assert 'name="production_cost"' in page
    assert "unit-hint" in page            # التسمية تسأل المحرّك لا نسخة موازية
    assert "لا نبحث عنه ولا نقدّره" in page


# ── سطر الفتح الواحد ───────────────────────────────────────────────────────

def test_unlock_note_present_without_cost_and_absent_with_it():
    from silk_economics import economics_view
    dr = {"missions": {}}
    without = economics_view(dr, category="حليب")
    assert without["unlock_note"] and "اللتر" in without["unlock_note"]
    solid = economics_view(dr, category="تمور")
    assert "الكيلوغرام" in solid["unlock_note"]
    with_cost = economics_view(dr, product_card={"cost_per_unit": 0.4},
                               category="حليب")
    assert with_cost["unlock_note"] is None
    assert with_cost["waterfall"]          # التكلفة فتحت الشلال فعلاً


def test_writer_prompt_carries_the_unlock_instruction():
    import silk_ai_judge
    src = inspect.getsource(silk_ai_judge.deep_report)
    assert "اطبع سطر الفتح أعلاه كما ورد مرة واحدة" in src
    assert "Print this unlock line once" in src


# ── فحص تكرار الغياب (تحذيري) ─────────────────────────────────────────────

_SECTION = ("## 9. التوصيات الاستراتيجية\n### أرقام القرار\n{body}\n"
            "## 10. المنهجية\nنص.")


def test_uncomputed_repetition_fires_on_study14_pattern():
    from silk_quality_gate import _check_uncomputed_repetition
    body = "\n".join(f"- الرقم {i}: غير محسوب — الناقص: التكلفة"
                     for i in range(5))
    found = _check_uncomputed_repetition(_SECTION.format(body=body))
    assert found and found[0]["check"] == "uncomputed_repetition"
    assert found[0]["repairable"] is True          # تحذيري (الدرس 135)


def test_uncomputed_repetition_silent_when_grouped_or_outside():
    from silk_quality_gate import _check_uncomputed_repetition
    ok = _check_uncomputed_repetition(_SECTION.format(
        body="سطر الفتح: رقم واحد يفتحها كلها.\n- التعادل: غير محسوب"))
    assert ok == []
    outside = ("## 2. السوق\n" + "غير محسوب. " * 6
               + "\n### أرقام القرار\nكل الأرقام حاضرة.")
    assert _check_uncomputed_repetition(outside) == []


def test_uncomputed_repetition_not_a_fail_trigger():
    from silk_quality_gate import FAIL_TRIGGER_CHECKS
    assert "uncomputed_repetition" not in FAIL_TRIGGER_CHECKS
