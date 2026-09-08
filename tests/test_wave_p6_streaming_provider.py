"""بثّ نداءي المحلل والكاتب — الموجة p6 (T5، الجذر).

البلاغ الحيّ (الفرع ب): نداء غير مبثوث ينتظر الجسد كاملاً تحت مهلة قراءة
٣٠٠ث؛ توليدُ ١٢–١٦ ألف رمز على النموذج الذكي يجلس على الحدّ نفسه، فتُقتل
مهلةُ القراءة توليداً سليماً بطيئاً وتُحسَب رموزه ولا يُحفَظ منها شيء.

العقد المقفول هنا:
- `stream=True` يرسل `"stream": true` ويقرأ SSE ويجمّع **نفس شكل القاموس**
  الذي يعيده النداء غير المبثوث (content/stop_reason/usage) — لا تغيير عند
  أيّ مستدعٍ سوى تمرير الوسيط.
- مهلة القراءة مع البثّ = **خمول** بين الأحداث (SILK_AI_STREAM_IDLE_S)، مع
  سقفٍ كلّي (SILK_AI_STREAM_TOTAL_S)؛ الإجهاض يعيد **النصّ الجزئي** المجمَّع
  ويضبط last_stop_reason="aborted_timeout" وlast_error — لا None صامت.
- المسار الافتراضي (stream غير مُمرَّر) **لا يتغيّر حرفاً**: لا `stream` في
  الحمولة ولا في kwargs requests.post.
هرمتي بالكامل — requests.post مُحاكى، لا شبكة.
Run:  python -m pytest tests/test_wave_p6_streaming_provider.py -q
"""
import contextlib
import json
import os
import sys
from unittest.mock import patch

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import silk_llm_provider as lp  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_provider_contextvars():
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)
    yield
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)


@contextlib.contextmanager
def _env(**vals):
    saved = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _sse(event: str, data: dict) -> list[str]:
    return [f"event: {event}", f"data: {json.dumps(data)}", ""]


def _stream_lines(stop_reason="end_turn", with_tool=False,
                  text_deltas=("مرحباً ", "بالعالم", "."),
                  out_tokens=42, in_tokens=10):
    lines = []
    lines += _sse("message_start", {"type": "message_start", "message": {
        "id": "msg_1", "role": "assistant", "content": [],
        "usage": {"input_tokens": in_tokens, "output_tokens": 1,
                  "cache_read_input_tokens": 3,
                  "cache_creation_input_tokens": 4}}})
    lines += _sse("content_block_start", {"type": "content_block_start",
                                          "index": 0, "content_block":
                                          {"type": "text", "text": ""}})
    for t in text_deltas:
        lines += _sse("content_block_delta", {
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": t}})
    lines += _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    if with_tool:
        lines += _sse("content_block_start", {
            "type": "content_block_start", "index": 1,
            "content_block": {"type": "tool_use", "id": "toolu_1",
                              "name": "comtrade_imports", "input": {}}})
        lines += _sse("content_block_delta", {
            "type": "content_block_delta", "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"hs": "08'}})
        lines += _sse("content_block_delta", {
            "type": "content_block_delta", "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '0410"}'}})
        lines += _sse("content_block_stop", {"type": "content_block_stop",
                                             "index": 1})
    lines += _sse("message_delta", {"type": "message_delta",
                                    "delta": {"stop_reason": stop_reason,
                                              "stop_sequence": None},
                                    "usage": {"output_tokens": out_tokens}})
    lines += _sse("message_stop", {"type": "message_stop"})
    return lines


class _StreamResp:
    """ردّ HTTP مبثوث مُحاكى — iter_lines يعيد أسطر SSE؛ يرمي اختيارياً بعد n."""
    def __init__(self, lines, raise_after=None, exc=None, status=200):
        self._lines = lines
        self._raise_after = raise_after
        self._exc = exc
        self.status_code = status
        self.headers = {}
        self.text = ""
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.exceptions.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err

    def iter_lines(self, decode_unicode=True, **kw):
        for i, ln in enumerate(self._lines):
            if self._raise_after is not None and i >= self._raise_after:
                raise self._exc
            yield ln

    def close(self):
        self.closed = True

    def json(self):  # لا يُستدعى في المسار المبثوث — حارس
        raise AssertionError("json() must not be called on a streamed response")


def _capture_post(resp):
    calls = []

    def fake_post(url, **kw):
        calls.append(kw)
        return resp
    return calls, fake_post


# ── الشكل المتطابق · identical dict shape ────────────────────────────────────

def test_streamed_complete_tools_matches_non_streamed_shape():
    lp.reset_provider()
    calls, fake_post = _capture_post(_StreamResp(_stream_lines(
        stop_reason="tool_use", with_tool=True)))
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post):
        out = lp.get_provider().complete_tools(
            "sys", [{"role": "user", "content": "hi"}], tools=[{"name": "t"}],
            max_tokens=100, model="claude-test", timeout=300.0, stream=True)
    assert calls[0]["stream"] is True
    assert calls[0]["json"]["stream"] is True
    assert calls[0]["timeout"][0] == 10.0          # مهلة الاتصال كما كانت
    assert out["stop_reason"] == "tool_use"
    assert out["content"] == [
        {"type": "text", "text": "مرحباً بالعالم."},
        {"type": "tool_use", "id": "toolu_1", "name": "comtrade_imports",
         "input": {"hs": "080410"}}]
    assert out["usage"]["input_tokens"] == 10
    assert out["usage"]["output_tokens"] == 42
    assert lp.last_error() is None


def test_streamed_complete_returns_text_stop_reason_and_meters_usage():
    import silk_context
    lp.reset_provider()
    _, fake_post = _capture_post(_StreamResp(_stream_lines()))
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post):
        silk_context.begin_data_counter()
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
        c = silk_context.data_counter() or {}
    assert out == "مرحباً بالعالم."
    assert lp.last_stop_reason() == "end_turn"
    usage = c.get("llm_usage") or {}
    # رموز الردّ المبثوث تُقاس مرّة واحدة (مدخل من message_start، مخرج من message_delta)
    flat = json.dumps(usage, default=str)
    assert "42" in flat and "10" in flat


def test_streamed_max_tokens_still_signals_stop_reason():
    """اقتطاع الإخراج في البثّ يصل عبر message_delta — طبقة الكاتب تقرؤه كما كانت."""
    lp.reset_provider()
    _, fake_post = _capture_post(_StreamResp(_stream_lines(stop_reason="max_tokens")))
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out == "مرحباً بالعالم."
    assert lp.last_stop_reason() == "max_tokens"


# ── الإجهاض يعيد الجزئي · abort keeps the partial ─────────────────────────────

def test_streamed_idle_timeout_returns_partial_and_flags():
    lp.reset_provider()
    lines = _stream_lines()
    # يرمي ReadTimeout بعد أول دلتا نصّ (السطر ٩ تقريباً: start + block_start + delta)
    resp = _StreamResp(lines, raise_after=9,
                       exc=requests.exceptions.ReadTimeout("idle"))
    _, fake_post = _capture_post(resp)
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out == "مرحباً"                        # الجزء المجمَّع قبل الخمول (يُقصّ كالمعتاد)
    assert lp.last_stop_reason() == "aborted_timeout"
    err = lp.last_error()
    assert err and err["type"] == "ReadTimeout"
    assert resp.closed


def test_streamed_total_ceiling_aborts_with_partial():
    lp.reset_provider()
    lines = _stream_lines()
    resp = _StreamResp(lines)
    _, fake_post = _capture_post(resp)
    clock = {"t": 1000.0}

    def fake_monotonic():
        clock["t"] += 400.0            # كل قراءة تقفز ٤٠٠ث — تتجاوز السقف بسرعة
        return clock["t"]

    with _env(ANTHROPIC_API_KEY="k", SILK_AI_STREAM_TOTAL_S="600"), \
         patch("requests.post", side_effect=fake_post), \
         patch("silk_llm_provider.time.monotonic", side_effect=fake_monotonic):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert lp.last_stop_reason() == "aborted_timeout"
    assert lp.last_error()["type"] == "StreamTotalTimeout"
    assert out is None or isinstance(out, str)    # جزئي أو لا شيء — لا استثناء


def test_streamed_idle_with_no_text_yet_returns_none_and_flags():
    lp.reset_provider()
    resp = _StreamResp(_stream_lines(), raise_after=3,
                       exc=requests.exceptions.ReadTimeout("idle"))
    _, fake_post = _capture_post(resp)
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out is None
    assert lp.last_error()["type"] == "ReadTimeout"
    assert lp.last_stop_reason() == "aborted_timeout"


# ── سياسة الإعادة · retry only before first byte ─────────────────────────────

def test_stream_connect_timeout_is_retried_but_read_after_bytes_is_not():
    lp.reset_provider()
    attempts = {"n": 0}
    good = _StreamResp(_stream_lines())

    def fake_post(url, **kw):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise requests.exceptions.ConnectTimeout("connect")
        return good

    with _env(ANTHROPIC_API_KEY="k", SILK_LLM_MAX_RETRIES="2",
              SILK_LLM_RETRY_BASE_S="0"), \
         patch("requests.post", side_effect=fake_post):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out == "مرحباً بالعالم." and attempts["n"] == 2

    # بعد وصول بايتات: ReadTimeout لا يُعاد (محاولة واحدة فقط)
    lp.reset_provider()
    attempts["n"] = 0
    bad = _StreamResp(_stream_lines(), raise_after=9,
                      exc=requests.exceptions.ReadTimeout("idle"))

    def fake_post2(url, **kw):
        attempts["n"] += 1
        return bad

    with _env(ANTHROPIC_API_KEY="k", SILK_LLM_MAX_RETRIES="2",
              SILK_LLM_RETRY_BASE_S="0"), \
         patch("requests.post", side_effect=fake_post2):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out == "مرحباً" and attempts["n"] == 1


def test_streamed_http_error_before_body_is_reported_like_today():
    lp.reset_provider()
    resp = _StreamResp([], status=400)
    resp.text = '{"type":"invalid_request_error"}'
    _, fake_post = _capture_post(resp)
    with _env(ANTHROPIC_API_KEY="k", SILK_LLM_MAX_RETRIES="0"), \
         patch("requests.post", side_effect=fake_post):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out is None
    err = lp.last_error()
    assert err["type"] == "HTTPError" and err["status_code"] == 400
    assert "invalid_request_error" in err["response_body"]


# ── المسار الافتراضي لا يتغيّر · default path untouched ───────────────────────

def test_default_path_sends_no_stream_flag_and_no_stream_kwarg():
    lp.reset_provider()

    class _Plain:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"stop_reason": "end_turn", "content": [
                {"type": "text", "text": "OK"}],
                "usage": {"input_tokens": 1, "output_tokens": 1}}

    calls, fake_post = _capture_post(_Plain())
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test", 300.0)
        out2 = lp.get_provider().complete_tools(
            "sys", [{"role": "user", "content": "x"}], None, 100,
            "claude-test", 300.0)
    assert out == "OK" and out2["stop_reason"] == "end_turn"
    for kw in calls:
        assert "stream" not in kw
        assert "stream" not in kw["json"]
        assert kw["timeout"] == (10.0, 300.0)   # زوج المهلة كما كان حرفياً


def test_stream_timeouts_read_env_with_defaults():
    with _env(SILK_AI_STREAM_IDLE_S=None, SILK_AI_STREAM_TOTAL_S=None):
        assert lp._stream_idle_s() == 120.0
        assert lp._stream_total_s(300.0) == 900.0
    with _env(SILK_AI_STREAM_IDLE_S="45", SILK_AI_STREAM_TOTAL_S="100"):
        assert lp._stream_idle_s() == 45.0
        # السقف الكلّي لا ينزل تحت مهلة المستدعي (الحقل المقفول في التتبّع)
        assert lp._stream_total_s(300.0) == 300.0
        assert lp._stream_total_s(50.0) == 100.0


# ── T7 · بوّابة تتجاهل stream: تراجع إلى JSON عند صفر أحداث فقط ─────────────

class _JsonOnlyResp:
    """بوّابة/وسيط يتجاهل "stream": true ويعيد جسد JSON عادياً — iter_lines
    يعطي سطر JSON واحداً بلا بادئة data: (صفر أحداث SSE)."""
    status_code = 200
    headers = {}
    text = ""

    def __init__(self, payload):
        self._payload = payload
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=True, **kw):
        yield json.dumps(self._payload)

    def json(self):
        return self._payload

    def close(self):
        self.closed = True


def test_json_fallback_only_when_zero_sse_events(caplog):
    lp.reset_provider()
    payload = {"stop_reason": "end_turn",
               "content": [{"type": "text", "text": "ردّ عبر بوّابة"}],
               "usage": {"input_tokens": 7, "output_tokens": 3}}
    _, fake_post = _capture_post(_JsonOnlyResp(payload))
    import logging
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post), \
         caplog.at_level(logging.INFO, logger="silk_llm_provider"):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out == "ردّ عبر بوّابة"
    assert lp.last_stop_reason() == "end_turn"
    assert lp.last_error() is None
    assert any("json_fallback" in r.getMessage() for r in caplog.records), \
        "gateway ignoring the stream flag must be visible in logs"


def test_streamed_path_is_logged_as_streamed(caplog):
    lp.reset_provider()
    _, fake_post = _capture_post(_StreamResp(_stream_lines()))
    import logging
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post), \
         caplog.at_level(logging.DEBUG, logger="silk_llm_provider"):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out == "مرحباً بالعالم."
    msgs = [r.getMessage() for r in caplog.records]
    assert any("path=streamed" in m for m in msgs)
    assert not any("json_fallback" in m for m in msgs)


def test_mid_stream_death_never_falls_back_to_json():
    """بثٌّ بدأ ثم مات — **لا** تراجع إلى .json(): المسار القائم يعيد الجزئي
    بوسم aborted_timeout؛ التراجع هنا كان سيخفي عين العطل الذي نصلحه."""
    lp.reset_provider()
    lines = _stream_lines()

    class _DiesThenHasJson(_StreamResp):
        def json(self):
            return {"stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "نصّ كامل مزيّف"}]}

    resp = _DiesThenHasJson(lines, raise_after=9,
                            exc=requests.exceptions.ReadTimeout("idle"))
    _, fake_post = _capture_post(resp)
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out == "مرحباً"                      # الجزئي، لا "نصّ كامل مزيّف"
    assert lp.last_stop_reason() == "aborted_timeout"
    assert lp.last_error()["type"] == "ReadTimeout"


def test_zero_events_and_unparseable_body_stays_a_declared_failure():
    lp.reset_provider()

    class _Garbage(_JsonOnlyResp):
        def iter_lines(self, decode_unicode=True, **kw):
            yield "<html>502 Bad Gateway</html>"

        def json(self):
            raise ValueError("not json")

    _, fake_post = _capture_post(_Garbage({}))
    with _env(ANTHROPIC_API_KEY="k"), patch("requests.post", side_effect=fake_post):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out is None
    assert lp.last_error() and lp.last_error()["type"]
