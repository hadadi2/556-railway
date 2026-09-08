"""موجة صيد الفجوات الثالثة — أقفال طبقة البيانات · gap-sweep 3 data-layer locks.

خمسة صيادين متوازيين (2026-08-25) أعادوا 57 ملاحظة مؤكدة؛ هذا الملف يقفل
عائلة طبقة البيانات: إسناد المخزن يُسقَط عند حدود الاستهلاك، فشل الجلب
يُجمَع صفراً فيولّد إنذاراً كاذباً، fetch_failed ينهار إلى no_record،
حرف شارد يُحلّ رمز HS بثقة عالية، وإنفاق Serper خفي عن عدّاد الاقتصاد.
هرمتي بالكامل. Run: python3 -m pytest tests/test_gap_sweep3.py -q
"""
import datetime
import os
import sys
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import silk_context                                     # noqa: E402
from silk_data_layer import DataPoint                   # noqa: E402


def _block_network(monkeypatch):
    """اقطع الشبكة — **مع** إغلاق الجلسة المجمّعة (2026-08-27).

    ترقيعُ `socket.socket` وحده لا يوقف اتصالاً keep-alive مفتوحاً في
    `silk_data_layer._session` (إعادةُ استعماله لا تُنشئ socket جديداً) —
    راجع `tests/conftest.py::block_network`. النسختان الأخريان أُصلحتا وبقيت
    هذه، فوُحِّد السلوك ويقفله `test_every_network_block_closes_the_pooled_session`.
    """
    import socket

    def _blocked(*a, **k):
        raise OSError("network blocked (hermetic)")

    try:
        import silk_data_layer
        silk_data_layer._session.close()
    except Exception:  # noqa: BLE001 — أفضل جهد؛ الترقيع نافذ بدونه
        pass

    monkeypatch.setattr(socket, "socket", _blocked)


# ── A1: إسناد المخزن يصل مكوّن حجم السوق · store provenance reaches TAM ──

_STORE_MI = {
    "total_usd": 10_000_000.0,
    "competitors": [],
    "xval_note": "",
    "served_from": "store",
    "freshness": "stale",
    "retrieved_at": "2020-01-01T00:00:00+00:00",
    "provenance_note": "من المخزن — جُلبت أصلاً 2020-01-01 — أقدم من نافذة "
                       "الحداثة؛ يجري تحديثها بالخلفية",
}


def test_store_served_market_size_keeps_original_provenance(monkeypatch):
    """قيمة TAM المخدومة من المخزن تحمل تاريخ الجلب الأصلي + وسم «من المخزن»
    + status=stale — لا تُختم بتاريخ اليوم كجلب حي (الدرس 4/persist)."""
    _block_network(monkeypatch)
    import silk_market_ranker as MR
    monkeypatch.setattr(MR, "market_imports_cached",
                        lambda *a, **k: dict(_STORE_MI))
    row = MR._gather_row("040900", {"iso3": "NLD", "m49": "528"}, 2024)
    ms = row["components"]["market_size"]
    assert ms.value == 10_000_000.0
    assert str(ms.retrieved_at).startswith("2020-01-01"), ms.retrieved_at
    assert "من المخزن" in ms.note
    assert ms.status == "stale"


def test_fresh_store_hit_still_tagged_but_not_stale(monkeypatch):
    _block_network(monkeypatch)
    import silk_market_ranker as MR
    mi = dict(_STORE_MI)
    mi["freshness"] = "fresh"
    mi["retrieved_at"] = datetime.date.today().isoformat()
    mi["provenance_note"] = "من المخزن — جُلبت أصلاً " + mi["retrieved_at"]
    monkeypatch.setattr(MR, "market_imports_cached", lambda *a, **k: dict(mi))
    row = MR._gather_row("040900", {"iso3": "NLD", "m49": "528"}, 2024)
    ms = row["components"]["market_size"]
    assert "من المخزن" in ms.note
    assert ms.status == ""


# ── A3: فشل جلب متكرر لا ينهار إلى no_record ─────────────────────────────

def test_repeated_fetch_exceptions_declare_fetch_failed_not_no_record(
        monkeypatch):
    """كل سنوات نافذة التراجُع رمت استثناء ⇒ الفجوة fetch_failed («أعد
    المحاولة») لا no_record («لا سجل») — تمييز 1b لا يُفقد في الاحتياط."""
    _block_network(monkeypatch)
    import silk_market_ranker as MR

    def _boom(*a, **k):
        raise RuntimeError("simulated repeated fetch-layer crash")

    monkeypatch.setattr(MR, "market_imports_cached", _boom)
    row = MR._gather_row("080410", {"iso3": "QAT", "m49": "634"}, 2022)
    ms = row["components"]["market_size"]
    assert ms.value is None
    assert ms.status == "fetch_failed", ms.status
    assert "أعد المحاولة" in ms.note


# ── A2: فشل الجلب لا يولّد إنذار «نمو سالب» كاذباً ───────────────────────

def test_post_entry_fetch_failure_never_fires_growth_alert(monkeypatch):
    """comtrade_trade→None (تعذّر جلب) كان يُجمَع صفراً فيطلق إنذار نمو سالب
    كاذباً لسوق مدخول — القياس المتعذّر يُتخطى معلَناً، لا يُختلَق اتجاه."""
    _block_network(monkeypatch)
    import silk_collectors as SC
    import silk_data_layer as DL

    item = {"id": 99, "full": {"hs_code": "080410",
                               "market": {"iso3": "NLD", "m49": "528"}}}
    monkeypatch.setattr(SC, "_entered_deep_research_analyses",
                        lambda path: [item])
    year = SC._today_year() - 1
    real = [{"primaryValue": 1000.0}]

    def _trade(hs, m49, y, flow="M", partner=0):
        return None if y == year else real   # السنة الجارية تعذّر جلبها

    monkeypatch.setattr(DL, "comtrade_trade", _trade)
    alerts = SC.check_post_entry(path=":memory:")
    assert alerts == [], alerts


def test_post_entry_real_decline_still_alerts(monkeypatch):
    _block_network(monkeypatch)
    import silk_collectors as SC
    import silk_data_layer as DL

    item = {"id": 7, "full": {"hs_code": "080410",
                              "market": {"iso3": "NLD", "m49": "528"}}}
    monkeypatch.setattr(SC, "_entered_deep_research_analyses",
                        lambda path: [item])
    year = SC._today_year() - 1

    def _trade(hs, m49, y, flow="M", partner=0):
        return ([{"primaryValue": 500.0}] if y == year
                else [{"primaryValue": 1000.0}])

    monkeypatch.setattr(DL, "comtrade_trade", _trade)
    alerts = SC.check_post_entry(path=":memory:")
    assert len(alerts) == 1 and alerts[0]["growth_negative"] is True


# ── A4: مرآة الصادرات — ضربة مخزن عتيقة تُعلَّم ولا تُخدَم كحية ──────────

def test_mirror_store_hit_stale_is_flagged(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    monkeypatch.setenv("SILK_SWR", "0")   # لا خيط تحديث يعيش بعد رقعة السوكت
    os.environ["SILK_STORE_DB"] = str(tmp_path / "store.db")
    try:
        import silk_store
        import silk_data_layer_v2 as V2
        monkeypatch.setattr(
            silk_store, "get_trade_flow",
            lambda *a, **k: {"value_usd": 5_500_000.0, "qty_kg": None,
                            "retrieved_at": "2020-01-01T00:00:00+00:00"})
        dp = V2.mirror_saudi_export("040900", "528", "NLD", 2024)
        assert dp.value == {"value_usd": 5_500_000.0, "qty_kg": None}
        assert dp.status == "stale", dp.status
        assert "أقدم من نافذة الحداثة" in dp.note
        assert str(dp.retrieved_at).startswith("2020-01-01")
    finally:
        os.environ.pop("SILK_STORE_DB", None)


def test_mirror_store_hit_unknown_date_declares_it(monkeypatch, tmp_path):
    """تاريخ جلب غائب = «غير مسجَّل» لا «أقدم من النافذة» — لا ادعاء عمرٍ
    لتاريخ لم يُسجَّل (عقد freshness نفسه)."""
    _block_network(monkeypatch)
    monkeypatch.setenv("SILK_SWR", "0")
    os.environ["SILK_STORE_DB"] = str(tmp_path / "store.db")
    try:
        import silk_store
        import silk_data_layer_v2 as V2
        monkeypatch.setattr(
            silk_store, "get_trade_flow",
            lambda *a, **k: {"value_usd": 100.0, "qty_kg": None,
                            "retrieved_at": None})
        dp = V2.mirror_saudi_export("040900", "528", "NLD", 2024)
        assert "غير مسجَّل" in dp.note
        assert "أقدم من نافذة الحداثة" not in dp.note
    finally:
        os.environ.pop("SILK_STORE_DB", None)


# ── A8: اللاحقة ثلاثية الحالة مشتركة · tri-state staleness helper ─────────

def test_staleness_suffix_tristate():
    import silk_store
    s, st = silk_store.staleness_suffix(datetime.date.today().isoformat())
    assert (s, st) == ("", "")
    s, st = silk_store.staleness_suffix("2019-01-01")
    assert "أقدم من نافذة الحداثة" in s and st == "stale"
    s, st = silk_store.staleness_suffix(None)
    assert "غير مسجَّل" in s and "أقدم" not in s and st == "stale"


# ── A9: نقاط TradeFlow تحمل retrieved_at ─────────────────────────────────

def test_tradeflow_success_datapoint_carries_retrieved_at(monkeypatch):
    _block_network(monkeypatch)
    import silk_agents as SA
    monkeypatch.setattr(SA.TradeFlowAgent, "_world_row_from_store",
                        lambda self, *a, **k: None)
    with patch("silk_agents.comtrade_trade",
               return_value=[{"primaryValue": 1234.0}]):
        rep = SA.TradeFlowAgent().run({"hs_code": "040900", "market_m49": "528",
                                       "iso3": "NLD", "year": 2024})
    dps = [f for f in rep.findings if f.value is not None]
    assert dps, rep.findings
    assert all(f.retrieved_at for f in dps), [f.retrieved_at for f in dps]


def test_tradeflow_failure_datapoints_carry_retrieved_at(monkeypatch):
    _block_network(monkeypatch)
    import silk_agents as SA
    monkeypatch.setattr(SA.TradeFlowAgent, "_world_row_from_store",
                        lambda self, *a, **k: None)
    with patch("silk_agents.comtrade_trade", return_value=None):
        rep = SA.TradeFlowAgent().run({"hs_code": "040900", "market_m49": "528",
                                       "iso3": "NLD", "year": 2024})
    assert rep.findings
    assert all(f.retrieved_at for f in rep.findings)


# ── A5: حرف شارد لا يُحلّ رمز HS بثقة عالية ──────────────────────────────

def test_resolver_rejects_degenerate_single_char_queries():
    """«م» كانت تُحلّ 020230 (لحم بقر مجمد) بثقة 0.95 عبر فرع الاحتواء —
    استعلام أقصر من ٣ أحرف لا يكسب رتبة الاحتواء؛ يبقى الضبابي < العتبة."""
    import silk_hs_resolver as R
    for q in ("م", "ت", "s", "ab"):
        dp = R.resolve(q)
        assert dp.value is None, (q, dp.value, dp.confidence)
        assert dp.confidence == 0.0
    # الاستعلام الحقيقي القصير المشروع (٣ أحرف فأكثر) يبقى يعمل.
    ok = R.resolve("عسل")
    assert ok.value is not None and ok.confidence >= 0.7


# ── A6/A7: إنفاق حي لا يفلت من عدّاد اقتصاد البيانات ─────────────────────

def test_direct_fallback_fetch_is_counted(monkeypatch):
    """سقوط طبقة الكاش إلى GET مباشر نداءٌ حي ثانٍ — يُحسب في live_fetches
    (قاعدة «لا إنفاق خفي»)."""
    import silk_data_layer as DL
    monkeypatch.setattr(DL, "_cached_get", lambda *a, **k: None)

    def _fail(*a, **k):
        raise OSError("network blocked (hermetic)")

    monkeypatch.setattr(DL, "_http_get", _fail)
    counter = silk_context.begin_data_counter()
    DL.comtrade_trade("040900", "528", 2024, flow="M", partner=0)
    assert counter.get("live_fetches", 0) >= 1, dict(counter)


def test_serper_shopping_call_is_counted(monkeypatch):
    import silk_websearch_agent as WS
    monkeypatch.setattr(WS, "search_key", lambda: "k-test")

    class _Resp:
        def raise_for_status(self):
            raise OSError("network blocked (hermetic)")

    import requests
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(
                            OSError("network blocked (hermetic)")))
    counter = silk_context.begin_data_counter()
    WS.web_search_shopping("عسل سدر", gl="nl")
    assert counter.get("live_fetches", 0) >= 1, dict(counter)


# ── مخاطر المخزن في مسار المخاطر · _enrich_risk store provenance ─────────

def test_enrich_risk_store_hit_keeps_stored_date(monkeypatch):
    _block_network(monkeypatch)
    import silk_engine as SE
    import silk_store

    monkeypatch.setattr(
        silk_store, "get_indicator",
        lambda iso3, ind: {"value": 0.83, "year": 2023, "source": "World Bank",
                           "confidence": 0.9,
                           "retrieved_at": "2024-02-02T00:00:00+00:00"})
    monkeypatch.setattr(silk_store, "get_indicator_series", lambda *a, **k: [])
    rows = [{"iso3": "NLD"}]
    SE._enrich_risk(rows)
    dps = rows[0].get("risk", [])
    got = [d for d in dps if getattr(d, "value", None) == 0.83]
    assert got, dps
    assert str(got[0].retrieved_at).startswith("2024-02-02"), \
        got[0].retrieved_at
