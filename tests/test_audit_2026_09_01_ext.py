"""أقفال EXT — الخدمات الخارجية (التدقيق الجنائي 2026-09-01، مرحلة EXT).

لماذا هذا الملف: القاطعُ المفتوح كان يسمح بمحاولةٍ واحدة (فلا «فشلٌ سريع» حقيقيّ)
ولا يلتقط أعطالَ الاتصال أصلاً (EXT-1/9)؛ وفشلُ الجلب داخل الكاش كان يُعيد `None`
فيُعاد الجلبُ حيّاً مرّةً ثانية (EXT-2)؛ وأغلفةُ الخطأ والردودُ الفارغة تُخزَّن يوماً
كاملاً (EXT-3)؛ والكتابةُ غيرُ ذرّية وبلا نافذةِ احتفاظٍ افتراضية (EXT-4)؛ ومهلةُ
الاتصال تساوي مهلةَ القراءة فيُنتظَر ٤٥ ث على مضيفٍ ميت (EXT-11)؛ والمباعدةُ تنام
بلا سقف (EXT-10/CONC-2)؛ ومجمّعُ البعثات ينتظر عمّالَه عند الخروج (EXT-5/6/API-13)؛
ولا مهلةَ كلّية للتحليل (EXT-21)؛ وإعادةُ نداء كلود على أعطال الاتصال بلا تمييزٍ ولا
عدّاد (EXT-7)؛ وصياغةُ الأقسام بلا سقفٍ ولا قياسٍ دولاريّ (EXT-8)؛ وحجزُ التفعيلة لا
يُحرَّر حين يفشل الحجزُ الدولاريّ (EXT-16)؛ ونداءُ الرؤية بحارسين متكرّرين (EXT-13)؛
وتريندز تجلب السلسلةَ مرّتين (EXT-12)؛ وستةُ وكلاء ينادون `requests.get` عارياً
(EXT-17)؛ وفشلُ الجلب في المرآة/المنافسين لا يُميَّز عن «لا سجل» (EXT-19/20).

هرمتي: بلا شبكة، بلا مفاتيح. Hermetic only.
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys
import threading
import time
import types
from unittest import mock
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class _Resp:
    """ردٌّ بشكل `requests.Response` — بلا شبكة."""

    def __init__(self, status: int = 200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload if payload is not None else {"ok": True}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ══════════════ EXT-1 / EXT-9 — القاطعُ يفشل فوراً ويلتقط أعطالَ الاتصال ═══════════
def test_open_breaker_raises_circuit_open_with_zero_network_calls(monkeypatch):
    """«فشلٌ سريع بمحاولةٍ واحدة» كان لا يزال نداءً حيّاً لكلّ واحدٍ من ~١٥٠ نداء
    fan-out على مضيفٍ ميت — القاطعُ المفتوح الآن يرفع `CircuitOpen` بلا أيّ نداء."""
    import silk_circuit
    import silk_data_layer as dl
    silk_circuit.http_breaker.reset()
    assert issubclass(silk_circuit.CircuitOpen, ConnectionError)
    calls = {"n": 0}

    def _get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        return _Resp(503)
    monkeypatch.setattr(dl._session, "get", _get)
    monkeypatch.setenv("SILK_HTTP_RETRIES", "0")
    for _ in range(5):
        dl._http_get("https://dead.example/api")
    assert silk_circuit.http_breaker.is_open("dead.example")
    calls["n"] = 0
    with pytest.raises(silk_circuit.CircuitOpen):
        dl._http_get("https://dead.example/api")
    assert calls["n"] == 0, "القاطعُ المفتوح ما زال ينادي الشبكة"
    silk_circuit.http_breaker.reset()


def test_connection_errors_trip_the_breaker_and_emit_a_declared_event(monkeypatch):
    """`_session.get` كان خارج أيّ `try` — عطلُ اتصالٍ (لا 5xx) لا يزيد عدّادَ القاطع
    ولا يترك حدثاً في التتبّع، فيبقى المضيفُ الميت يُنادَى إلى الأبد."""
    import silk_circuit
    import silk_data_layer as dl
    silk_circuit.http_breaker.reset()
    events: list = []
    monkeypatch.setattr(dl, "_record_fetch_failure_event",
                        lambda host, endpoint, **kw: events.append((host, kw)))
    monkeypatch.setenv("SILK_HTTP_RETRIES", "0")

    def _boom(url, params=None, headers=None, timeout=None):
        raise ConnectionError("socket died")
    monkeypatch.setattr(dl._session, "get", _boom)
    with pytest.raises(ConnectionError):
        dl._http_get("https://flaky.example/api")
    assert silk_circuit.http_breaker.failures("flaky.example") == 1
    assert events and events[0][0] == "flaky.example"
    silk_circuit.http_breaker.reset()


# ══════════════ EXT-2 — فشلُ الجلب لا يُعاد حيّاً مرّةً ثانية ═══════════════════════
def test_a_failed_fetch_is_not_retried_live_by_the_caller(monkeypatch, tmp_path):
    """`cached_get` كان يعيد `None` سواءً تعذّرت طبقةُ الكاش أو فشل الجلبُ نفسه —
    فيظنّ المستدعي أنّ الكاش غائب ويجلب حيّاً **مرّةً ثانية** (إنفاقٌ مضاعف)."""
    import silk_cache
    import silk_data_layer as dl
    monkeypatch.setenv("SILK_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("SILK_HTTP_RETRIES", "0")
    monkeypatch.delenv("COMTRADE_API_KEY", raising=False)
    calls = {"n": 0}

    def _get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        return _Resp(429)
    monkeypatch.setattr(dl._session, "get", _get)
    monkeypatch.setattr(dl, "_http_get",
                        lambda url, params=None, **kw: _get(url, params))
    assert silk_cache._FETCH_FAILED is not None
    out = dl._cached_get("https://x.example/api", {"a": 1})
    assert out is silk_cache._FETCH_FAILED
    before = calls["n"]
    assert dl.comtrade_trade("080410", "784", 2024) is None
    assert calls["n"] - before <= 1, "المستدعي أعاد الجلبَ حيّاً بعد فشلٍ معلَن"


# ══════════════ EXT-3 — لا تخزينَ لأغلفة الخطأ، والفارغُ يعيش عشرَ دقائق ═══════════
def test_error_envelopes_are_never_cached_and_empty_payloads_expire_fast(monkeypatch, tmp_path):
    import silk_cache
    monkeypatch.setenv("SILK_CACHE_DIR", str(tmp_path))
    url = "https://wb.example/v2/country/all/indicator/X"
    err = [{"message": [{"key": "Invalid value", "value": "bad param"}]}]

    def _fetch_err(u, p=None, **kw):
        return _Resp(200, err)
    silk_cache.cached_get(url, {"a": 1}, fetcher=_fetch_err,
                          cacheable=lambda p: not (isinstance(p, list) and p
                                                   and isinstance(p[0], dict)
                                                   and p[0].get("message")))
    assert not list(pathlib.Path(str(tmp_path)).glob("*.json")), "غلافُ خطأٍ خُزِّن"

    def _fetch_empty(u, p=None, **kw):
        return _Resp(200, {"data": []})
    silk_cache.cached_get(url, {"b": 2}, fetcher=_fetch_empty,
                          short_lived=lambda p: not p.get("data"),
                          empty_ttl_seconds=600)
    files = list(pathlib.Path(str(tmp_path)).glob("*.json"))
    assert len(files) == 1, "الردُّ الفارغ لم يُخزَّن إطلاقاً (كان يجب أن يُخزَّن قصيراً)"
    age = time.time() - files[0].stat().st_mtime
    assert age > 600 - 60, "الفارغُ خُزِّن بعمرٍ كامل لا بنافذةٍ قصيرة"


# ══════════════ EXT-4 — كتابةٌ ذرّية ونافذةُ احتفاظٍ افتراضية للكاش ═════════════════
def test_cache_writes_are_atomic_and_the_default_retention_is_thirty_days(monkeypatch, tmp_path):
    import silk_cache
    import silk_janitor
    src = _read("silk_cache.py")
    assert "os.replace(" in src, "الكتابةُ ليست ذرّية — قارئٌ قد يرى ملفاً مبتوراً"
    monkeypatch.setenv("SILK_CACHE_DIR", str(tmp_path))
    seen: list = []
    real_replace = os.replace

    def spy(a, b):
        seen.append((a, b))
        return real_replace(a, b)
    monkeypatch.setattr(os, "replace", spy)
    silk_cache.cached_get("https://x.example/y", {"q": 1},
                          fetcher=lambda u, p=None, **kw: _Resp(200, {"data": [1]}))
    assert seen and str(seen[0][1]).endswith(".json")
    for var in ("SILK_CACHE_RETENTION_DAYS", "SILK_RETENTION_DAYS"):
        monkeypatch.delenv(var, raising=False)
    assert silk_janitor._days("cache") == 30.0
    assert silk_janitor._days("traces") == 30.0     # حفظ محدود؛ قواعد الأدلة لا تُحذف


# ══════════════ EXT-11 — مهلةُ الاتصال قصيرة، ومهلةُ القراءة كما هي ════════════════
def test_connect_timeout_is_capped_at_ten_seconds_everywhere(monkeypatch):
    import silk_data_layer as dl
    assert dl._timeout_pair_for("api.worldbank.org") == (10.0, 45.0)
    assert dl._timeout_pair_for("comtradeapi.un.org") == (10.0, 30.0)
    seen: dict = {}

    def _get(url, params=None, headers=None, timeout=None):
        seen["timeout"] = timeout
        return _Resp(200)
    monkeypatch.setattr(dl._session, "get", _get)
    dl._http_get("https://api.worldbank.org/v2/x")
    assert seen["timeout"] == (10.0, 45.0)
    import requests
    monkeypatch.setattr(requests, "get", _get)
    dl.throttled_get("https://api.worldbank.org/v2/y")
    assert seen["timeout"] == (10.0, 45.0)


# ══════════════ EXT-10 / CONC-2 — لا نومَ بلا سقف على المباعدة ════════════════════
def test_a_long_projected_throttle_wait_refuses_instead_of_sleeping(monkeypatch):
    """`_throttle` كان ينام حصّته مهما طال الطابور — مئةُ نداءٍ متزامن على مضيفٍ
    بمباعدةٍ ثانية = آخرُهم ينام مئةَ ثانية داخل خيطِ طلب."""
    import silk_data_layer as dl
    assert issubclass(dl.ThrottleBacklog, ConnectionError)
    monkeypatch.setenv("SILK_HTTP_MIN_GAP_MS", "1000")
    monkeypatch.setenv("SILK_HTTP_MAX_THROTTLE_WAIT_S", "3")
    slept: list = []
    monkeypatch.setattr(dl._time, "sleep", lambda s: slept.append(s))
    host = "backlog.example"
    with dl._host_lock:
        dl._last_hit[host] = dl._time.monotonic() + 60      # طابورٌ طويل محجوز
    with pytest.raises(dl.ThrottleBacklog):
        dl._throttle(host)
    assert not slept, "نام رغم تجاوز السقف"
    with dl._host_lock:
        dl._last_hit.pop(host, None)


# ══════════════ EXT-5 / EXT-6 / API-13 — المجمّعُ لا يُبقي العمّال بعد الجدار ═══════
def test_mission_pool_shuts_down_without_waiting_and_cancels_pending():
    src = _read("silk_missions.py")
    assert "shutdown(wait=False" in src and "cancel_futures=True" in src
    assert "fut.cancel()" in src
    assert '"wall_timeout_s": _MISSION_TIMEOUT_S + _WALL_GRACE_S' in src   # لم يُمَسّ
    assert "SILK_MISSION_AUGMENT_TIMEOUT_S" in src


def test_opportunity_gaps_and_augmentations_are_bounded(monkeypatch):
    """بعثةُ الفجوات كانت تعمل **خارج** المجمّع بلا مهلة، والتعزيزاتُ بعدها بلا سقف —
    فتشغيلةٌ تتجاوز جدارَها الزمنيّ كاملاً بسببهما."""
    import silk_missions
    src = _read("silk_missions.py")
    body = src.split("def run_all_missions(")[1].split("\ndef ")[0]
    assert "opportunity_gaps" in body
    i = body.index("gaps_agent")
    assert "cf_wait" in body[i - 1200:i + 1200] or "submit(" in body[i - 400:i + 400], \
        "بعثةُ الفجوات ما زالت خارج المجمّع بلا مهلة"
    assert "_bounded_augment(" in body, "التعزيزاتُ ما زالت بلا مهلة"


def test_run_market_returns_at_the_shared_deadline(monkeypatch):
    """`fut.result(timeout=…)` بالتتابع كان يمنح كلَّ وكيلٍ المهلةَ كاملةً — ثمانيةُ
    وكلاء = ثمانيةُ أضعاف الجدار في أسوأ حال."""
    src = _read("silk_research.py")
    body = src.split("def run_market(")[1].split("\n    @staticmethod")[0]
    assert "cf_wait" in body or "_cf.wait(" in body or "as_completed" in body
    assert "shutdown(wait=False" in body and "cancel_futures=True" in body


# ══════════════ EXT-21 — مهلةٌ كلّية معلَنة للتحليل ═════════════════════════════
def test_analyze_respects_a_deadline_and_declares_the_layers_it_skipped():
    import silk_context
    assert hasattr(silk_context, "deadline_context") and hasattr(silk_context, "remaining_s")
    with silk_context.deadline_context(0.05):
        assert silk_context.remaining_s() <= 0.05
        time.sleep(0.06)
        assert silk_context.remaining_s() == 0.0
    assert silk_context.remaining_s() is None       # خارج السياق: بلا جدار
    src = _read("silk_engine.py")
    assert "deadline_s" in src and "SILK_ANALYZE_DEADLINE_S" in src
    assert '"deadline"' in src and "skipped_layers" in src
    assert "SILK_ANALYZE_DEADLINE_S" in _read(".env.example")


# ══════════════ EXT-7 — إعادةُ نداء كلود تميّز طورَ الاتصال وتُعَدّ ═══════════════
def test_non_connect_connection_errors_are_retried_at_most_once(monkeypatch):
    import requests
    import silk_context
    import silk_llm_provider as lp
    monkeypatch.setenv("SILK_LLM_MAX_RETRIES", "5")
    monkeypatch.setenv("SILK_LLM_RETRY_BASE_S", "0")
    monkeypatch.setattr(lp, "_scrub_sampling_params", lambda p, m: p)
    calls = {"n": 0}

    def _post(*a, **kw):
        calls["n"] += 1
        raise requests.exceptions.ConnectionError("read side dropped")
    monkeypatch.setattr(requests, "post", _post)
    silk_context.begin_data_counter()
    prov = lp.AnthropicProvider()
    with pytest.raises(requests.exceptions.ConnectionError):
        prov._post("k", {"model": "m"}, 10.0)
    assert calls["n"] == 2, f"محاولاتٌ غير مقيَّدة على عطلٍ غير اتصاليّ: {calls['n']}"
    counter = silk_context.data_counter() or {}
    assert counter.get("llm_retried_attempts", 0) >= 1


# ══════════════ EXT-8 — صياغةُ الأقسام مسقوفةٌ ومقيسة ═══════════════════════════
def test_rephrase_is_capped_and_metered(monkeypatch):
    import silk_ai_judge as judge
    import silk_context
    monkeypatch.setenv("SILK_REPHRASE_MAX_SECTIONS", "2")
    monkeypatch.setattr(judge, "available", lambda: True)
    monkeypatch.setattr(judge, "_call", lambda *a, **kw: "نصٌّ تجاريّ موجز.")
    heads = {f"قسم {i}": [f"بند {i}"] for i in range(5)}
    monkeypatch.setattr("silk_reports._client_missing_narrative_heads", lambda dr: heads)
    recorded: list = []
    import silk_usage
    monkeypatch.setattr(silk_usage, "record_usd", lambda amount, path=None: recorded.append(amount))
    silk_context.begin_data_counter()
    out = judge.rephrase_client_sections({"x": 1})
    assert len(out) == 2, f"السقفُ لم يُحترَم: {len(out)}"
    assert recorded, "نداءاتُ الصياغة بلا قياسٍ دولاريّ"


def test_a_failed_llm_call_is_counted(monkeypatch):
    import silk_ai_judge as judge
    import silk_context
    monkeypatch.setattr(judge, "get_provider" if hasattr(judge, "get_provider") else "_MODEL",
                        getattr(judge, "get_provider", judge._MODEL), raising=False)
    silk_context.begin_data_counter()
    with patch("silk_llm_provider.get_provider") as gp:
        gp.return_value = mock.Mock(complete=mock.Mock(return_value=None))
        assert judge._call("s", "u") is None
    counter = silk_context.data_counter() or {}
    assert counter.get("llm_calls_failed", 0) == 1, counter


# ══════════════ EXT-16 — التفعيلةُ تُحرَّر حين يفشل الحجزُ الدولاريّ ════════════════
def test_a_failed_usd_reservation_releases_the_paid_activation(monkeypatch, tmp_path):
    import silk_hs_classifier as hsc
    import silk_usage
    db = str(tmp_path / "usage.db")
    monkeypatch.setenv("SILK_USAGE_DB", db)
    monkeypatch.setenv("SILK_PAID_DAILY_CAP", "10")
    monkeypatch.setenv("SILK_PAID_DAILY_USD_CAP", "0.001")   # يرفض الحجزَ الدولاريّ
    assert hasattr(silk_usage, "release_paid_calls")
    before = silk_usage.paid_calls_today(db)
    assert hsc._reserve_llm_call() is False
    assert silk_usage.paid_calls_today(db) == before, "التفعيلةُ حُجزت ولم تُحرَّر"


# ══════════════ EXT-13 — نداءُ الرؤية بحارسٍ واحد ═══════════════════════════════
def test_vision_has_one_guard_and_one_call_site():
    import silk_usage
    assert hasattr(silk_usage, "vision_allowed")
    judge = _read("silk_ai_judge.py")
    assert "def _call_vision" in judge
    intake = _read("silk_product_intake.py")
    assert "call_vision(" in intake and "silk_vision" in intake, \
        "الاستقبالُ ما زال ينادي المزوّدَ مباشرةً"
    assert "get_provider" not in intake            # الدرس ٢١: لا حكمَ ولا مزوّدَ مباشراً
    assert "def call_vision" in _read("silk_vision.py")
    for rel, fn in (("api.py", "_intake_vision_allowed"),
                    ("silk_platform/api.py", "_vision_allowed_for_platform")):
        src = _read(rel)
        body = src.split(f"def {fn}(")[1].split("\n    @app")[0]
        assert "vision_allowed(" in body, f"{rel}:{fn} لا يفوّض إلى الحارس الواحد"


def test_blocked_context_makes_zero_vision_calls(monkeypatch):
    import silk_ai_judge as judge
    import silk_context
    import silk_vision
    with patch("silk_llm_provider.get_provider") as gp:
        with silk_context.block_ai_extras():
            assert judge._call_vision("s", "t", "b64", "image/png") is None
            assert silk_vision.call_vision("s", "t", "b64", "image/png") is None
        gp.assert_not_called()


# ══════════════ EXT-12 — تريندز تجلب السلسلةَ مرّةً واحدة ══════════════════════════
def test_trends_fetches_the_series_once_on_the_happy_path(monkeypatch):
    src = _read("silk_trends_agent.py")
    assert "def _interest_with_series" in src, "لا مسارَ جلبٍ واحد للسلسلة"
    assert src.count("TrendReq(") <= 2, "ما زالت التهيئةُ مكرّرةً لكلّ نداء"


# ══════════════ EXT-17 — لا `requests.get` عارياً في الوكلاء ══════════════════════
_BARE_MODULES = ("silk_volza_agent.py", "silk_explee_agent.py", "silk_localprice_agent.py",
                 "silk_gdelt_agent.py", "silk_google_news_agent.py", "silk_collectors.py")


def test_agents_fetch_through_the_hardened_path():
    for rel in _BARE_MODULES:
        tree = ast.parse(_read(rel))
        bad = [n.lineno for n in ast.walk(tree)
               if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute) and n.func.attr in ("get", "post")
               and getattr(n.func.value, "id", "") == "requests"]
        assert not bad, f"{rel}: نداءٌ عارٍ في {bad}"
        assert "throttled_get" in _read(rel) or "throttled_request" in _read(rel), rel


# ══════════════ EXT-19 / EXT-20 — «تعذّر الجلب» ≠ «لا سجل»، وتحذيرٌ مرّةً واحدة ═════
def test_mirror_and_competitors_declare_a_fetch_failure_distinctly():
    for rel, needle in (("silk_data_layer_v2.py", 'status="fetch_failed"'),
                        ("silk_agents.py", 'getattr(c, "status", "") == "fetch_failed"')):
        assert needle in _read(rel), rel
    # المقعدُ المرقَّع في الاختبارات (`silk_agents.market_competitors`) لم يُتجاوَز.
    body = _read("silk_agents.py").split("class CompetitionAgent")[1]
    assert "market_competitors(hs, market, year)" in body


def test_store_failures_warn_once_per_process():
    src = _read("silk_data_layer.py") + _read("silk_data_layer_v2.py")
    assert "_warned_once" in src, "تحذيرُ المخزن ما زال يتكرّر مع كلّ صفّ"


# ══════════════ مراجعة EXT (§58، يدوية) — اكتشافان أُقفلا أحمر أوّلاً ══════════════
def test_analyze_enters_the_deadline_context_so_nested_layers_see_the_wall(monkeypatch):
    """`deadline_context`/`remaining_s` كانتا شيفرةً ميتة: المحرّك يحمل جدارَه في متغيّرٍ
    محلّي، فالبعثاتُ والوكلاءُ والجلبُ تحته لا ترى المتبقّي إطلاقاً."""
    import silk_context
    import silk_engine
    seen: dict = {}

    class _Stop(RuntimeError):
        pass

    def _spy_rank(*a, **kw):
        seen["remaining"] = silk_context.remaining_s()
        raise _Stop()
    monkeypatch.setattr(silk_engine, "rank_markets", _spy_rank)
    monkeypatch.setattr(silk_engine, "resolve",
                        lambda name: silk_engine.DataPoint("080410", "seed", 0.9, "", "2026-01-01"))
    with pytest.raises(_Stop):
        silk_engine.analyze("تمور", countries=[{"iso3": "CHN", "m49": "156"}],
                            year=2023, deadline_s=30)
    assert seen["remaining"] is not None, "الطبقاتُ المتداخلة لا ترى الجدار"
    assert 0 < seen["remaining"] <= 30
    assert silk_context.remaining_s() is None, "الجدارُ تسرّب خارج التحليل"


def test_the_trends_agent_fetches_the_series_once_per_run(monkeypatch):
    """الاهتمامُ والموسميةُ نداءان لنفس السلسلة في كلّ تشغيلة وكيل — حصّةُ pytrends
    محدودة أصلاً (429 مرصود حيّاً)."""
    import silk_trends_agent as ta
    built: list = []

    class _DF:
        empty = False
        columns = ["تمور"]
        index = types.SimpleNamespace(month=[1, 2, 3])

        def __getitem__(self, k):
            import statistics

            class _S(list):
                def mean(self_inner):
                    return statistics.fmean(self_inner)

                def groupby(self_inner, by):
                    return types.SimpleNamespace(mean=lambda: _S([10.0, 90.0, 20.0]),
                                                 idxmax=lambda: 2)

                @property
                def iloc(self_inner):
                    return self_inner
            return _S([10.0, 50.0, 90.0])

    class _Trend:
        def __init__(self, *a, **kw):
            built.append(1)

        def build_payload(self, *a, **kw):
            return None

        def interest_over_time(self):
            return _DF()
    monkeypatch.setitem(sys.modules, "pytrends",
                        types.SimpleNamespace(request=types.SimpleNamespace(TrendReq=_Trend)))
    monkeypatch.setitem(sys.modules, "pytrends.request",
                        types.SimpleNamespace(TrendReq=_Trend))
    ta.reset_series_memo()
    rep = ta.TrendsAgent()._execute({"keyword": "تمور", "geo": "AE"})
    assert not rep.failed, rep.summary
    assert len(built) == 1, f"جلبُ السلسلة تكرّر {len(built)} مرّات في تشغيلةٍ واحدة"
    ta.reset_series_memo()
