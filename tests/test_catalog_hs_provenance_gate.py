"""حادثة الدراسة #10 (حليب/الأردن، 2026-08-24) — رمزُ كتالوجٍ مخزَّن ليس إجابةَ مشغّل.

الدليل المباشر (تقرير الدراسة المُسلَّم + ملحق حدوده): جسرُ المنصّة مرّر رمزَ
كتالوجٍ قديماً (040110، «حليب ≤1% دسم») كأنه إدخالَ مستخدمٍ حاضر، فمرّ اختصارُ
محور `preflight_block` («المستخدم سمّى بندَه بنفسه») وبُنيت دراسةٌ كاملة (1.80$)
على بندٍ لا يطابق المنتج — بينما المُحلِّل الحتمي يومَها يعيد 040120.

الفكس: `hs_source="catalog"` يُوسَم من جسر المنصّة، و`api._hs_user_supplied`
يحرم الرمزَ الكتالوجيّ من الاختصار فيواجه البوّاباتِ كاملةً قبل أيّ إنفاق.
`hs_confirmed=true` (تأكيدُ المصنع الصريح) يبقى المَخرجَ الشرعيّ. هرمتي. Run:
  python3 -m pytest tests/test_catalog_hs_provenance_gate.py -q
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_MILK_REQ = {"product": "حليب", "market": "Jordan", "hs_code": "040110"}


def _client():
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.create_app())


def _post_research(body):
    # عرف الريبو لاختبارات TestClient: ترقيع requests لا حجب socket
    # (حجب socket يكسر ناقل TestClient نفسه).
    with mock.patch("requests.get", side_effect=OSError("offline")), \
         mock.patch("requests.post", side_effect=OSError("offline")):
        return _client().post("/research", json=body)


def _detail_error(resp):
    d = resp.json().get("detail")
    return d.get("error") if isinstance(d, dict) else None


def test_catalog_hs_faces_the_axis_gate_before_any_spend():
    """رمزُ كتالوجٍ غير مؤكَّد يُحجَب 422 قبل أيّ إنفاق — بوّابةُ الثقة أولاً
    (ثقتُه «غير معلومة» لا 1.00 مختلَقة — مراجعة §58) ثم المحور؛ أيّهما
    أمسك فالعقد واحد: سؤالٌ بمرشّحين، لا تشغيلة على بندٍ مخزَّن بلا تأكيد."""
    resp = _post_research({**_MILK_REQ, "hs_source": "catalog"})
    assert resp.status_code == 422
    assert _detail_error(resp) in ("hs_confidence_too_low",
                                   "hs_axis_disambiguation_needed")
    # السؤال يحمل مرشّحين فعليّين يختار منهم المصنع — لا «حاول مجدداً» عارية.
    assert (resp.json()["detail"].get("candidates") or []), \
        "حجبُ رمز الكتالوج بلا مرشّحين لا يعطي المصنعَ مخرجاً"


def test_user_typed_hs_keeps_the_answered_axis_shortcut():
    """السلوك القائم محفوظ حرفياً (بلاغ 2026-08-19): رمزٌ كتبه المستخدم وهو
    أحدُ مرشّحي المحور = إجابةُ السؤال — لا يُعاد طرحُه."""
    resp = _post_research(dict(_MILK_REQ))
    assert not (resp.status_code == 422
                and _detail_error(resp) == "hs_axis_disambiguation_needed"), \
        "رمزٌ أدخله المستخدم بنفسه عاد يُسأل عنه — انحدار بلاغ 2026-08-19"


def test_factory_confirmed_catalog_hs_passes_the_gate():
    """تأكيدُ المصنع الصريح (`hs_confirmed=true` — عمود `studies.hs_confirmed`)
    يبقى المَخرجَ الشرعيّ لرمزٍ كتالوجيّ."""
    resp = _post_research({**_MILK_REQ, "hs_source": "catalog",
                           "hs_confirmed": True})
    assert not (resp.status_code == 422
                and _detail_error(resp) == "hs_axis_disambiguation_needed"), \
        "تأكيد المصنع الصريح لم يعد يفتح البوّابة — طريق مسدود"


def test_bridge_stamps_catalog_provenance_on_deep_runs():
    """جسرُ المنصّة يُوسِم رمزَ الكتالوج بمصدره (`hs_source="catalog"`) عبر
    نفس نمط التمرير المتسامح — مغلقةٌ قديمة بلا الوسيط تبقى صالحة."""
    import silk_research_gateway as gateway
    from silk_platform import engine_bridge as eb
    seen = {}

    def fake_runner(product, market, hs_code=None, hs_confirmed=False,
                    lang="ar", resume=None, hs_source=None):
        seen.update(product=product, market=market, hs_code=hs_code,
                    hs_source=hs_source)
        return {"ok": True}

    gateway.reset()
    try:
        gateway.register(run=fake_runner, readiness=lambda: (True, ""))
        out = eb._run_engine_deep("حليب", "040110", "Jordan")
        assert out == {"ok": True}
        assert seen["hs_source"] == "catalog"
        assert seen["hs_code"] == "040110"
    finally:
        gateway.reset()


def test_bridge_omits_hs_source_when_no_code():
    """بلا رمزٍ كتالوجيّ لا وسمَ مصدرٍ — الحسم للمُحلِّل الحتمي كما اليوم."""
    import silk_research_gateway as gateway
    from silk_platform import engine_bridge as eb
    seen = {}

    def fake_runner(product, market, hs_code=None, hs_confirmed=False,
                    lang="ar", resume=None, hs_source=None):
        seen.update(hs_code=hs_code, hs_source=hs_source)
        return {"ok": True}

    gateway.reset()
    try:
        gateway.register(run=fake_runner, readiness=lambda: (True, ""))
        eb._run_engine_deep("حليب", None, "Jordan")
        assert seen["hs_source"] is None
    finally:
        gateway.reset()


def test_old_runner_closure_without_hs_source_still_works():
    """مغلقةٌ مسجَّلة قديمة (بلا وسيط `hs_source`) لا تنكسر — `_runner_takes`."""
    import silk_research_gateway as gateway
    from silk_platform import engine_bridge as eb

    def old_runner(product, market, hs_code=None, hs_confirmed=False,
                   lang="ar", resume=None):
        return {"ok": "old"}

    gateway.reset()
    try:
        gateway.register(run=old_runner, readiness=lambda: (True, ""))
        assert eb._run_engine_deep("حليب", "040110", "Jordan") == {"ok": "old"}
    finally:
        gateway.reset()


def test_quick_mode_catalog_hs_is_gated_too(monkeypatch):
    """مراجعة §58 («إصلاحٌ على مسارٍ واحد نصفُ إصلاح»): الوضع السريع للمنصّة
    يمرّ بنقطة الاختناق نفسها — رمزُ كتالوجٍ غير مؤكَّد يُرفَض رفضاً معلَناً
    بمرشّحين قبل أيّ تشغيل محرّك."""
    import pytest
    from silk_platform import engine_bridge as eb
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "quick")
    monkeypatch.delenv("SILK_PLATFORM_FAKE_ENGINE", raising=False)
    with mock.patch("requests.get", side_effect=OSError("offline")), \
         mock.patch("requests.post", side_effect=OSError("offline")):
        with pytest.raises(eb.DeepRunRefused) as exc:
            eb._run_engine("حليب", "040110", "Jordan", hs_confirmed=False)
    assert exc.value.candidates, "رفضُ الوضع السريع بلا مرشّحين — طريق مسدود"


def test_quick_mode_confirmed_catalog_hs_is_not_blocked(monkeypatch):
    """تأكيدُ المصنع يبقى المخرجَ على الوضع السريع أيضاً — البوّابة لا تعمل
    على رمزٍ مؤكَّد (لا نداء محرّك هنا: يكفي ألا يُرفَع الرفض من البوّابة)."""
    from silk_platform import engine_bridge as eb
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "quick")
    monkeypatch.delenv("SILK_PLATFORM_FAKE_ENGINE", raising=False)
    called = {}

    def fake_analyze(*a, **k):
        called["yes"] = True
        return {"markets": [], "product": "حليب"}

    import silk_engine
    with mock.patch.object(silk_engine, "analyze", side_effect=fake_analyze):
        eb._run_engine("حليب", "040110", "Jordan", hs_confirmed=True)
    assert called.get("yes"), "التأكيد الصريح لم يفتح الوضع السريع"


def test_revalidate_empty_code_desc_is_declared_not_quoted():
    """دراسة #10: وصفٌ فارغ كان يُطبَع «» حرفياً في «حدود هذا التقرير» —
    الغيابُ يُعلَن («غير متاح») لا يُقتبَس فارغاً."""
    import silk_hs_confirm as hc
    from silk_data_layer import DataPoint

    flagged = {"confirmed": False, "code_desc": "", "missing_terms": ["حليب"],
               "overlap": 0.0, "reason": "x"}
    with mock.patch.object(hc, "confirm_hs", return_value=flagged), \
         mock.patch("silk_hs_resolver.resolve",
                    return_value=DataPoint("040120", "seed", 0.9, "match")):
        out = hc.revalidate("حليب", "040110")
    assert out is not None
    assert "«»" not in out["message"]
    assert "غير متاح" in out["message"]
