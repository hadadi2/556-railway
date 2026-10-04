"""الدرس ٢٩١ — فجوات المصادر في سجلّ الدراسة ٩ (2026-10-03) — أقفال hermetic.

١ التعرفة: WITS بلا جدول مُبلَّغ لسنة الطلب يتراجع حتى سنتين، والعطل الشبكي لا يتراجع.
٢ WTO: لا بُعد شريك لـTP_A_0010 (كان 400 لكل نداء)، مدى سنوات وأحدثها يُختار، ونصّ الرفض يُسجَّل.
٣ WGI: رمزٌ مرفوض في قاعدة source=3 ⇒ يُسأل فهرس القاعدة عن المعرّف الحالي ويُعاد مرة.
٤ FAOSTAT: دخول JWT (FAOSTAT_USERNAME/PASSWORD) ⇒ ترويسة Bearer؛ بلا حساب تسمّي الملاحظة المتغيّرات.
٥ Exa/FAOSTAT: مباعدة أوسع لكل مضيف.
٦ طبيعة المورّدين: مهلة داخلية تسلّم ما اكتمل، وسقف تعزيز 60ث.
٧ الدراسة: الجدول لا يسقط (صف فجوة)، سنة موردين بعد آخر سنة مكتملة «أولي»، المصدر المستشهد به يُلحق.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from contextlib import contextmanager
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_data_layer import DataPoint  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextmanager
def _env(**vals):
    old = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _gap(status):
    return DataPoint(None, "World Bank WITS", 0.0, "gap", "2026-10-03", status=status)


# ── ١ WITS ──────────────────────────────────────────────────────────────
def test_wits_steps_back_to_latest_reported_year():
    import silk_tariffs_agent as T
    calls = []

    def fake(hs, mkt, partner, year):
        calls.append(year)
        if year == 2021:
            return DataPoint(5.0, "World Bank WITS", 0.9, f"reported HS090121 {year}", "2026-10-03")
        return _gap("no_record")

    wto_gap = DataPoint(None, "WTO TTD", 0.0, "wto gap", "2026-10-03", status="fetch_failed")
    with mock.patch("silk_wto_tariff.wto_applied_tariff", return_value=wto_gap), \
         mock.patch.object(T, "applied_tariff", side_effect=fake):
        dp = T.tariff_with_fallback("090121", "MYS", "SAU", 2023)
    assert calls == [2023, 2022, 2021]
    assert dp.value == 5.0
    assert "2021" in dp.note and "2023" in dp.note


def test_wits_network_failure_does_not_step_back():
    import silk_tariffs_agent as T
    calls = []

    def fake(hs, mkt, partner, year):
        calls.append(year)
        return _gap("fetch_failed")

    wto_gap = DataPoint(None, "WTO TTD", 0.0, "wto gap", "2026-10-03", status="fetch_failed")
    with mock.patch("silk_wto_tariff.wto_applied_tariff", return_value=wto_gap), \
         mock.patch.object(T, "applied_tariff", side_effect=fake), \
         mock.patch("silk_itc_tariff.market_access_evidence",
                    return_value=DataPoint(None, "ITC", 0.0, "itc gap", "2026-10-03")):
        dp = T.tariff_with_fallback("090121", "MYS", "SAU", 2023)
    assert calls == [2023]
    assert dp.value is None


def _wits_http(code):
    import requests
    import silk_tariffs_agent as T
    resp = mock.MagicMock(status_code=code)
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError(str(code), response=resp)
    with mock.patch("silk_data_layer.throttled_get", return_value=resp):
        return T.applied_tariff("090121", "MYS", "SAU", 2023)


def test_wits_404_is_no_record_but_429_is_an_outage():
    assert _wits_http(404).status == "no_record"
    assert _wits_http(400).status == "no_record"
    for code in (401, 403, 429):
        dp = _wits_http(code)
        assert dp.status == "fetch_failed" and "غير مُغطّى" not in dp.note


def test_wits_value_carries_its_year():
    import silk_tariffs_agent as T
    resp = mock.MagicMock(status_code=200)
    with mock.patch("silk_data_layer.throttled_get", return_value=resp), \
         mock.patch.object(T, "_parse_rate", return_value=8.0):
        dp = T.applied_tariff("090121", "MYS", "SAU", 2021)
    assert dp.value == 8.0 and dp.data_year == 2021


# ── ٢ WTO ───────────────────────────────────────────────────────────────
def test_wto_request_has_no_partner_and_takes_latest_year():
    import silk_wto_tariff as W
    seen = {}

    def fake_cached_get(url, params=None, **kw):
        seen.update(params)
        return {"Dataset": [{"Value": 7.0, "Year": 2021}, {"Value": 5.0, "Year": 2023},
                            {"Value": 6.0, "Year": 2022}]}

    with _env(WTO_TTD_API_KEY="k"), mock.patch("silk_cache.cached_get", side_effect=fake_cached_get):
        dp = W.wto_applied_tariff("090121", "MYS", "SAU", 2023)
    assert "p" not in seen
    assert seen["ps"] == "2020-2023"
    assert dp.value == 5.0 and "2023" in dp.note and dp.data_year == 2023


def test_wto_rejection_body_is_logged_to_ops():
    import silk_wto_tariff as W
    resp = mock.MagicMock(status_code=400, text='{"message":"Invalid parameter pc"}')
    with mock.patch.object(W, "_record_failure") as rec:
        out = W._logging_fetcher(lambda u, p, headers=None: resp, "090121", "MYS")("u", {})
    assert out is resp
    assert "Invalid parameter pc" in rec.call_args[0][2]


# ── ٣ WGI ───────────────────────────────────────────────────────────────
def test_wgi_rejected_code_resolves_current_id_and_retries():
    import silk_data_layer as D
    D._WGI_ID_CACHE.clear()
    err = [{"message": [{"id": "120", "key": "Invalid value",
                         "value": "The provided parameter value is not valid"}]}]
    index = [{"page": 1}, [{"id": "GOV_WGI_RL.EST", "name": "Rule of Law: Estimate"},
                           {"id": "GOV_WGI_PV.EST",
                            "name": "Political Stability and Absence of Violence/Terrorism: Estimate"}]]
    data = [{"page": 1}, [{"date": "2024", "value": 0.12}]]

    def fake(url, params, **kw):
        if url.endswith("/sources/3/indicators"):
            return index
        if url.endswith("/GOV_WGI_PV.EST"):
            assert params.get("source") == "3"
            return data
        return err

    with mock.patch.object(D, "_cached_get", side_effect=fake):
        dp = D._world_bank_for_year("MYS", "PV.EST", None)
    assert dp.value == 0.12 and dp.data_year == 2024
    assert dp.note.startswith("PV.EST (2024)") and "GOV_WGI_PV.EST" in dp.note
    D._WGI_ID_CACHE.clear()


def test_wgi_unknown_in_index_stays_declared_gap():
    import silk_data_layer as D
    D._WGI_ID_CACHE.clear()
    err = [{"message": [{"value": "The provided parameter value is not valid"}]}]
    index = [{"page": 1}, [{"id": "OTHER", "name": "Something else"}]]

    def fake(url, params, **kw):
        return index if url.endswith("/sources/3/indicators") else err

    with mock.patch.object(D, "_cached_get", side_effect=fake):
        dp = D._world_bank_for_year("MYS", "PV.EST", None)
    assert dp.value is None and dp.confidence == 0.0
    assert "parameter value is not valid" in dp.note
    D._WGI_ID_CACHE.clear()


# ── ٤ FAOSTAT ───────────────────────────────────────────────────────────
def test_faostat_login_sends_bearer():
    import silk_faostat_agent as F
    F.reset_auth_block()
    login = mock.MagicMock(status_code=200)
    login.json.return_value = {"AuthenticationResult": {"AccessToken": "tok"}}
    data = mock.MagicMock(status_code=200)
    data.json.return_value = {"data": [{"Item": "Coffee and products", "Value": "2.5",
                                        "Unit": "kg", "Year": 2022}]}
    try:
        with _env(FAOSTAT_USERNAME="u", FAOSTAT_PASSWORD="p", FAOSTAT_TOKEN=None,
                  SILK_DISABLE_FAOSTAT=None), \
             mock.patch("silk_faostat_agent.requests.post", return_value=login) as post, \
             mock.patch("silk_data_layer.throttled_get", return_value=data) as get:
            dp = F.per_capita_supply("MYS", "Coffee", 2022)
    finally:
        F.reset_auth_block()
    assert post.call_args.kwargs["data"] == {"username": "u", "password": "p"}
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer tok"}
    assert dp.value == 2.5


def test_faostat_401_without_account_names_the_variables():
    import silk_faostat_agent as F
    F.reset_auth_block()
    r = mock.MagicMock(status_code=401)
    try:
        with _env(FAOSTAT_USERNAME=None, FAOSTAT_PASSWORD=None, FAOSTAT_TOKEN=None,
                  SILK_DISABLE_FAOSTAT=None), \
             mock.patch("silk_data_layer.throttled_get", return_value=r):
            dp = F.per_capita_supply("MYS", "Coffee", 2022)
    finally:
        F.reset_auth_block()
    assert dp.value is None and "FAOSTAT_USERNAME" in dp.note


def test_faostat_failed_login_is_not_retried_on_every_call():
    import silk_faostat_agent as F
    F.reset_auth_block()
    bad = mock.MagicMock(status_code=401)
    try:
        with _env(FAOSTAT_USERNAME="u", FAOSTAT_PASSWORD="wrong", FAOSTAT_TOKEN=None,
                  SILK_DISABLE_FAOSTAT=None), \
             mock.patch("silk_faostat_agent.requests.post", return_value=bad) as post, \
             mock.patch("silk_data_layer.throttled_get") as get, \
             mock.patch("silk_ops_log.record_service_failure") as ops:
            a = F.per_capita_supply("MYS", "Coffee", 2022)
            b = F.per_capita_supply("SAU", "Coffee", 2022)
    finally:
        F.reset_auth_block()
    assert post.call_count == 1 and get.call_count == 0
    assert a.value is None and b.value is None
    assert ops.call_count == 1


# ── ٥ المباعدة ──────────────────────────────────────────────────────────
def test_exa_and_faostat_have_wider_host_gap():
    import silk_data_layer as D
    with _env(SILK_EXA_MIN_GAP_MS=None, SILK_FAOSTAT_MIN_GAP_MS=None, SILK_HTTP_MIN_GAP_MS=None):
        assert D._min_gap_ms("mcp.exa.ai") == 700
        assert D._min_gap_ms("faostatservices.fao.org") == 550
        assert D._min_gap_ms("api.worldbank.org") == 250


# ── ٦ طبيعة المورّدين ───────────────────────────────────────────────────
def test_budget_deadline_stops_new_calls():
    import silk_commercial_analysis as C
    with mock.patch.object(C, "max_calls", return_value=10), \
         mock.patch("silk_collectors.comtrade_budget_left", return_value=10):
        b = C._Budget(0, deadline_s=1.0)
        assert b.has() and not b.timed_out
        b._deadline -= 5
        assert not b.has() and b.timed_out


def test_supplier_nature_has_its_own_augment_ceiling():
    import silk_commercial_analysis as C
    import silk_missions as M
    with _env(SILK_SUPPLIER_NATURE_TIMEOUT_S=None, SILK_SUPPLIER_NATURE_S=None):
        assert M._supplier_nature_timeout_s() == 60.0
        assert C._supplier_nature_deadline_s() == 25.0
    # المهلة الداخلية تبقى دون السقف بمهلة قراءة كاملة مهما ضُبطت
    with _env(SILK_SUPPLIER_NATURE_TIMEOUT_S="60", SILK_SUPPLIER_NATURE_S="90"):
        assert C._supplier_nature_deadline_s() == 25.0
    src = open(os.path.join(_ROOT, "silk_missions.py"), encoding="utf-8").read()
    assert "timeout=_supplier_nature_timeout_s()" in src


# ── ٧ قالب الدراسة ──────────────────────────────────────────────────────
def _case():
    with open(os.path.join(_ROOT, "evals", "golden_set", "malaysia_coffee_fixture.json"),
              encoding="utf-8") as f:
        return json.load(f)


def _render(mut, kn=True):
    from silk_study_render import load_knowledge, render_study
    c = copy.deepcopy(_case())
    mut(c)
    return render_study(c, load_knowledge("090121", "MY") if kn else None)


def test_empty_table_keeps_header_with_declared_gap_row():
    md = _render(lambda c: c["entities"].update(rows=[]))
    assert "| الجهة | الوصف | الدور المقترح |" in md
    assert "| غير مرصود في هذه النسخة | — | — |" in md


def test_supplier_year_after_last_complete_year_is_provisional():
    md = _render(lambda c: c["suppliers"].update(year=2025))
    assert "في عام 2025 (أولي)" in md


def test_cited_source_is_appended_to_sources_line():
    md = _render(lambda c: c.update(sources=[s for s in c["sources"] if "البنك الدولي" not in s]))
    from silk_study_linter import missing_sources
    assert missing_sources(md) == []
    assert "البنك الدولي" in md.split("**المصادر:**", 1)[1]


def test_degraded_studies_pass_the_template_linter():
    from silk_study_linter import lint
    cases = [
        lambda c: c["shelf_prices"].update(rows=[]),
        lambda c: c["entities"].update(rows=[]),
        lambda c: c["requirements"].update(rows=[]),
        lambda c: c["suppliers"].update(top=[]),
        lambda c: c["fx"].update(avg_rate=None),
        lambda c: c["suppliers"].update(year=2025),
        lambda c: c.update(sources=[s for s in c["sources"] if "البنك الدولي" not in s]),
    ]
    for mut in cases:
        assert lint(_render(mut)) == []
    assert lint(_render(lambda c: None, kn=False)) == []
