"""ملاحظات المراجعة الذاتية (§58) على الموجة p6 — إصلاحات مُقاسة.

كل اختبار هنا يقفل ملاحظةً واحدة من مراجعة `683558a..HEAD`، أحمرَ قبل الإصلاح.
Run: python -m pytest tests/test_wave_p6_review_fixes.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_wave_p6_pipeline_resilience import (  # noqa: E402
    _CompletedMission, _client, _fake_call_tools_ok, _research_env, _tmp_db)


@pytest.fixture(autouse=True)
def _reset_provider_contextvars():
    import silk_llm_provider as lp
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)
    yield
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)


# ── R1 · تشخيص المحلل لا يُمحى بنداءٍ ناجحٍ لاحق ────────────────────────────

def test_analyst_failure_reason_survives_a_later_successful_claude_call():
    """المراجعة #1: `failure_reason()` كان يُقرأ **حيّاً** عند بناء الرد — بعد
    أن يكون نداء التوليف (المرحلة ٢) قد صفّر `_last_error` بنجاحه — فيضيع
    «ReadTimeout» ويحلّ محلّه نصٌّ عامّ. التشخيص يُبنى من الخطأ الملتقَط وقتَه."""
    import contextlib
    from unittest.mock import patch
    import requests
    import silk_llm_provider as lp
    db = _tmp_db()

    def analyst_fails_then_synth_succeeds(system, messages, tools=None,
                                          max_tokens=1600, model=None,
                                          timeout=None, **kw):
        lp._last_error.set({"type": "ReadTimeout",
                            "message": "read timed out (analyst)"})
        return None

    def synth_ok(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        lp._last_error.set(None)          # نداء ناجح يُصفّر الخطأ كما في المزوّد
        return json.dumps({"verdict": "WATCH", "confidence": 0.5,
                           "reasoning": "ok"})

    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch("silk_llm_runtime._call_tools",
                               side_effect=analyst_fails_then_synth_succeeds))
        st.enter_context(patch("silk_synthesis._call", side_effect=synth_ok))
        st.enter_context(patch("silk_ai_judge._call", side_effect=synth_ok))
        r = _client().post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text
    rep = r.json()["deep_research"]["report"]
    assert rep["skip_reason"] == "analyst_call_failed"
    assert rep["error_type"] == "ReadTimeout"
    assert "ReadTimeout" in rep["failure_reason"], rep["failure_reason"]


# ── R2 · حارس الميزانية يقرّر **بعد** أغلى نداء ─────────────────────────────

def test_budget_gate_for_synthesis_counts_the_analyst_spend():
    """المراجعة #5: بوّابة التوليف كانت تُقيَّم قبل نداء المحلل، فتقرّر بميزانيةٍ
    لا تشمل أغلى نداء في التشغيلة. الآن تُقاس بعده."""
    import contextlib
    from unittest.mock import patch
    import silk_ai_judge as aj
    import silk_context
    import silk_synthesis
    db = _tmp_db()
    seen: dict = {}

    def costly_analyst(system, messages, tools=None, max_tokens=1600,
                       model=None, timeout=None, **kw):
        silk_context.record_llm_usage(aj._MODEL, 100000, 100000)   # 1.20$ at verified Sonnet 5 standard price
        return _fake_call_tools_ok(system, messages, tools, max_tokens,
                                   model, timeout)

    real_synth = silk_synthesis.synthesize

    def capture_synth(*a, **k):
        seen["with_ai"] = k.get("with_ai")
        return real_synth(*a, **k)

    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        st.enter_context(patch.dict(os.environ, {"SILK_RESEARCH_MAX_USD": "1.0"}))
        st.enter_context(patch("silk_llm_runtime._call_tools",
                               side_effect=costly_analyst))
        st.enter_context(patch("silk_synthesis.synthesize",
                               side_effect=capture_synth))
        st.enter_context(patch("silk_ai_judge._call",
                               side_effect=lambda *a, **k: "## 1. x\nنصّ."))
        r = _client().post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text
    assert seen.get("with_ai") is False, (
        "stage-2 was green-lit on a budget measured before the analyst call")


def test_budget_ok_survives_a_malformed_expected_usd():
    """المراجعة #11: `float()` عارية على SILK_RESEARCH_EXPECTED_USD كانت ترفع
    ValueError من حارسٍ عقدُه «لا خطأ صلب» فتُسقِط التشغيلة بعد دفع البعثات."""
    import contextlib
    from unittest.mock import patch
    db = _tmp_db()
    with contextlib.ExitStack() as st:
        for p in _research_env(db):
            st.enter_context(p)
        # دفترٌ خاصٌّ بهذا الاختبار: الدفتر المشترك للجلسة يتراكم بحجوزات
        # مئات الاختبارات فيتجاوز السقف، فتردّ البوّابة 429 ويسقط الاختبار
        # لسببٍ لا علاقة له بمقصده (تبعيةُ ترتيبٍ في اختباري أنا — رُصدت في
        # التشغيلة الكاملة، ٣٢٣٣ اختباراً، ونجحت منفردةً).
        st.enter_context(patch.dict(os.environ, {
            "SILK_RESEARCH_EXPECTED_USD": "", "SILK_PAID_DAILY_USD_CAP": "10",
            "SILK_USAGE_DB": os.path.join(os.path.dirname(db), "usage.db")}))
        st.enter_context(patch("silk_ai_judge._call",
                               side_effect=lambda *a, **k: "## 1. x\nنصّ."))
        r = _client().post("/research", headers={"X-API-Key": "secret"}, json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": True})
    assert r.status_code == 200, r.text


# ── R3 · الكاتب: لا تصعيد على إجهاضٍ بلا نصّ؛ ولا لصقَ كلمات ────────────────

def test_aborted_stream_without_text_does_not_escalate_max_tokens():
    """المراجعة #2: إجهاضُ بثٍّ بلا نصّ كان يسقط في حلقة مضاعفة السقف —
    ثلاثُ إعاداتِ توليدٍ كاملةٍ مدفوعة، وكلٌّ أطولُ فأقربُ للإجهاض."""
    import silk_ai_judge as aj
    import silk_llm_provider as lp
    from unittest import mock
    caps: list = []

    def aborts(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        caps.append(max_tokens)
        lp._last_stop_reason.set("aborted_timeout")
        lp._last_error.set({"type": "ReadTimeout", "message": "idle"})
        return None

    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k",
                                      "SILK_API_KEY": "x"}), \
         mock.patch("silk_ai_judge._call", side_effect=aborts):
        out = aj.deep_report({}, "محلل", {"verdict": "WATCH"}, "تمور", "هولندا")
    assert out is None
    assert caps == [aj._WRITER_MAX_TOKENS], (
        f"a timeout triggered token-budget escalation: {caps}")


def test_zero_text_max_tokens_still_escalates():
    """الضدّ: نفادُ رموزٍ حقيقي (max_tokens) بلا نصّ يبقى مُصعَّداً كما كان."""
    import silk_ai_judge as aj
    import silk_llm_provider as lp
    from unittest import mock
    caps: list = []

    def truncates(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        caps.append(max_tokens)
        lp._last_stop_reason.set("max_tokens")
        return None

    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k",
                                      "SILK_API_KEY": "x"}), \
         mock.patch("silk_ai_judge._call", side_effect=truncates):
        aj.deep_report({}, "محلل", {"verdict": "WATCH"}, "تمور", "هولندا")
    assert caps == [aj._WRITER_MAX_TOKENS, aj._MAX_TOKENS_CEILING]


def test_continuation_does_not_glue_the_last_word_to_the_first():
    """المراجعة #6: `draft.rstrip()` كان يمحو المسافة التي بُني عليها قرارُ
    «لا فاصل»، فتلتصق آخرُ كلمةٍ بأوّل كلمةِ الإكمال — وصار هذا المسارَ
    الأساسيّ بعد T7."""
    import silk_ai_judge as aj
    from unittest import mock

    def script(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        import silk_llm_provider as lp
        if "مهمة إكمال" in user:
            lp._last_stop_reason.set("end_turn")
            return "ويُتوقّع نموّ الطلب."
        lp._last_stop_reason.set("max_tokens")
        return "## 1. الخلاصة التنفيذية\nينمو السوق الهولندي.\n"

    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k",
                                      "SILK_API_KEY": "x"}), \
         mock.patch("silk_ai_judge._call", side_effect=script), \
         mock.patch("silk_ai_judge._writer_incomplete", return_value=[]):
        out = aj._continue_truncated_report(
            None, "برومبت", "## 1. الخلاصة التنفيذية\nينمو السوق الهولندي.\n")
    assert "الهولندي.ويُتوقّع" not in out, out
    assert "الهولندي." in out and "ويُتوقّع" in out


# ── R4 · حكم المرحلة ٢ لا يرث خطأ المحلل ────────────────────────────────────

def test_synthesis_ai_error_is_not_a_stale_analyst_error():
    """المراجعة #4: نداءُ المرحلة ٢ قد يعود None **قبل** أن يمسّ المزوّد
    (وكيل معطّل/بلا مفتاح) فيبقى خطأ المحلل في contextvar ويُنسَب للتوليف."""
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_llm_provider as lp
    import silk_synthesis
    lp._last_error.set({"type": "ReadTimeout", "message": "من المحلل"})
    reports = [AgentReport("LLMAgent:trade_flow", [], False, "ok")]
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_synthesis._call", side_effect=lambda *a, **k: None):
        verdict = silk_synthesis.synthesize(reports, product="تمور",
                                            market="Nigeria", with_ai=True)
    assert verdict.get("ai_error") != {"type": "ReadTimeout", "message": "من المحلل"}
    assert verdict["synthesis_stage"] == 1


# ── R5 · المزوّد: رموزُ إجهاضٍ لا تُسجَّل صفراً؛ والردّ يُغلَق عند الإعادة ────

def test_aborted_stream_does_not_record_zero_output_tokens():
    """المراجعة #3: `message_delta` لا يصل عند الإجهاض، فكانت رموزُ الإخراج
    تُسجَّل **صفراً** — يُخفي أغلى إنفاق عن حارس الميزانية وعن المصالحة."""
    from unittest.mock import patch
    import requests
    import silk_context
    import silk_llm_provider as lp
    from tests.test_wave_p6_streaming_provider import _StreamResp, _stream_lines
    lp.reset_provider()
    resp = _StreamResp(_stream_lines(text_deltas=("نصّ طويل " * 200,)),
                       raise_after=9,
                       exc=requests.exceptions.ReadTimeout("idle"))
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), \
         patch("requests.post", side_effect=lambda *a, **k: resp):
        silk_context.begin_data_counter()
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
        usage = (silk_context.data_counter() or {}).get("llm_usage") or {}
    assert out and len(out) > 100
    row = usage.get("claude-test") or {}
    assert row.get("output_tokens", 0) > 0, (
        f"aborted stream recorded {row.get('output_tokens')} output tokens")


def test_streamed_retryable_status_closes_the_response():
    """المراجعة #10: ردٌّ مبثوث على 429 كان يُترَك مفتوحاً عند الإعادة —
    تسريبُ اتصالٍ لكل محاولة تحت اثنتي عشرة بعثة متوازية."""
    from unittest.mock import patch
    import silk_llm_provider as lp
    from tests.test_wave_p6_streaming_provider import _StreamResp, _stream_lines
    lp.reset_provider()
    first = _StreamResp([], status=429)
    first.headers = {}
    ok = _StreamResp(_stream_lines())
    seq = [first, ok]
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k",
                                 "SILK_LLM_MAX_RETRIES": "2",
                                 "SILK_LLM_RETRY_BASE_S": "0"}), \
         patch("requests.post", side_effect=lambda *a, **k: seq.pop(0)):
        out = lp.get_provider().complete("sys", "user", 100, "claude-test",
                                         300.0, stream=True)
    assert out == "مرحباً بالعالم."
    assert first.closed, "the retried streamed response was never closed"


def test_unclosed_tool_use_block_is_dropped_not_emitted_empty():
    """المراجعة #7: كتلةُ أداةٍ لم تُغلَق كانت تُسلَّم بـinput فارغ (لأن
    content_block_start يحمل input={} أصلاً) بدل أن تُسقَط."""
    from unittest.mock import patch
    import requests
    import silk_llm_provider as lp
    from tests.test_wave_p6_streaming_provider import _StreamResp, _stream_lines
    lp.reset_provider()
    lines = _stream_lines(stop_reason="tool_use", with_tool=True)
    # اقطع قبل content_block_stop للأداة (آخر ٩ أسطر: stop + message_delta + stop)
    resp = _StreamResp(lines, raise_after=len(lines) - 9,
                       exc=requests.exceptions.ReadTimeout("idle"))
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), \
         patch("requests.post", side_effect=lambda *a, **k: resp):
        data = lp.get_provider().complete_tools(
            "sys", [{"role": "user", "content": "hi"}], tools=[{"name": "t"}],
            max_tokens=100, model="claude-test", timeout=300.0, stream=True)
    kinds = [b.get("type") for b in (data or {}).get("content", [])]
    assert "tool_use" not in kinds, (data or {}).get("content")


# ── R6 · المخزن: الدمج في معاملةٍ واحدة ─────────────────────────────────────

def test_mark_research_failed_reads_and_writes_in_one_transaction():
    """المراجعة #13: القراءة والكتابة في اتصالين ⇒ كاتبان متزامنان يمحو
    أحدُهما دمجَ الآخر (وقد يمحو نتيجةً مدفوعة كُتبت بينهما)."""
    from unittest.mock import patch
    import silk_storage
    from tests.test_wave_p6_pipeline_resilience import _seed_run
    db = _tmp_db()
    aid = _seed_run(db)
    real_connect = silk_storage._connect
    opened: list = []

    def counting_connect(path):
        opened.append(path)
        return real_connect(path)

    with patch("silk_storage._connect", side_effect=counting_connect):
        silk_storage.mark_research_failed(aid, "boom", path=db)
    # init_db يفتح اتصالاً أيضاً — المهم ألّا يفتح الدمجُ نفسُه اتصالين.
    assert opened.count(db) <= 2, f"merge used {opened.count(db)} connections"


# ── R7 · الجسر: مطابقةُ السوق بالرمز لا بالتهجئة ────────────────────────────

def test_resume_matches_compares_market_by_iso3_not_display_name():
    """المراجعة #8: المقارنة بالسلسلة الخام كانت تُعطّل الاستئناف صامتاً حين
    تختلف التهجئة (`Netherlands` مقابل `NLD`/`هولندا`) — فتُدفَع البعثات
    والمحلل مرّتين، وهو عينُ ما وُضِع T10 لمنعه."""
    from silk_platform.engine_bridge import _resume_matches
    from silk_storage import create_research_run
    aid = create_research_run("تمور سكري", "NLD", "080410",
                              {"product": "تمور سكري", "market": "Netherlands",
                               "market_iso3": "NLD", "hs_code": "080410"})
    assert _resume_matches(aid, "تمور سكري", "NLD") is True
    assert _resume_matches(aid, "تمور سكري", "Netherlands") is True
    assert _resume_matches(aid, "تمور سكري", "هولندا") is True
    assert _resume_matches(aid, "تمور سكري", "KWT") is False
    assert _resume_matches(aid, "منتج آخر", "NLD") is False


# ── الانحدار الحاجب · every new kwarg passes through a signature probe ──────

def test_run_llm_agent_probes_before_passing_stream_to_run_loop():
    """الانحدار الحاجب (مراجعة §58): `stream=stream` كان يُمرَّر عارياً إلى
    `_run_loop`، فكسر مموّهاتٍ قائمةً ذاتَ توقيعٍ ثابت وأحمَرَّ الرُتبة ١.
    العقد: يُمرَّر فقط لمن يقبله — كما في كل موضعٍ آخر في الموجة."""
    from unittest import mock
    import silk_llm_runtime as rt
    from silk_missions import MISSIONS
    seen: list = []

    def fixed_signature_loop(mission, ctx, budget, timeout=None, model=None):
        seen.append({"model": model, "timeout": timeout})
        return {"findings": [], "gaps": [], "summary": "ok", "registry": {},
                "tool_calls_used": 0}

    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), \
         mock.patch.object(rt, "_run_loop", fixed_signature_loop):
        rt.run_llm_agent(MISSIONS["pricing_scout"], _market_ref(),
                         product="تمور", hs_code="080410", stream=True)
    assert len(seen) == 1                       # لا TypeError

    got: dict = {}

    def flexible_loop(mission, ctx, budget, timeout=None, model=None,
                      stream=False):
        got["stream"] = stream
        return {"findings": [], "gaps": [], "summary": "ok", "registry": {},
                "tool_calls_used": 0}

    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}), \
         mock.patch.object(rt, "_run_loop", flexible_loop):
        rt.run_llm_agent(MISSIONS["pricing_scout"], _market_ref(),
                         product="تمور", hs_code="080410", stream=True)
    assert got["stream"] is True                # ويصل من يقبله


def _market_ref():
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market("Nigeria")
    return ref


# ── الانحدار ١ (مقارنة الأساس) · استئنافٌ لا يردّ 409 على المحفوظ ───────────

def test_resume_of_a_reportless_completed_run_replays_when_engine_not_ready():
    """انحدارُ T4: تشغيلةٌ مكتملةٌ بلا نصّ تقرير صارت تسقط للمسار الحيّ، فردّت
    بوّابةُ الجهوزية 409 على استئنافٍ بلا مفتاح — رفضٌ صلب يحجب المحفوظ.
    الآن: يُعاد المحفوظ (200) بسببٍ معلَن، وبلا إعادة تشغيل أيّ بعثة."""
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_missions as M
    import silk_storage as S
    db = _tmp_db()
    seen: dict = {}

    def _must_not_run(*a, **k):
        seen["called"] = True
        raise RuntimeError("لا إعادة تشغيل على استئنافٍ غير جاهز")

    with patch("silk_storage._db_path", return_value=db), \
         patch.dict(os.environ, {"SILK_API_KEY": "secret"}), \
         patch("silk_missions.deep_research", side_effect=_must_not_run):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        aid = S.create_research_run(
            "تمر", "NLD", "080410",
            {"product": "تمر", "market": "Netherlands", "market_iso3": "NLD",
             "hs_code": "080410"}, path=db, market_name="Netherlands")
        for k in M.MISSION_ORDER:
            S.save_mission_checkpoint(aid, k, AgentReport(f"m:{k}", [], False,
                                                          "ok"),
                                      path=db, market_iso3="NLD")
        S.save_analysis({"product": "تمر", "markets": [],
                         "deep_research": {"missions": {}}},
                        analysis_id=aid, path=db)
        S.update_research_status(aid, "completed", path=db)
        r = _client().post("/research", headers={"X-API-Key": "secret"},
                           json={"resume": aid})
    assert r.status_code == 200, r.text
    assert seen.get("called") is None
    assert "resume_note" in r.json()


# ── الانحدار ٢ · لا يُنسَب عطلٌ محليّ إلى المزوّد ────────────────────────────

def test_stage2_timeout_is_passed_through_a_signature_probe():
    """الانحدار ٢: `timeout=` مُرِّر عارياً فكسر مموّهاً قائماً ذا توقيعٍ ثابت،
    والاستثناءُ ابتُلع فبدا وكأن نداءً اختفى. يُمرَّر بفحص توقيع كبقيّة الموجة."""
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_ai_judge as aj
    import silk_synthesis
    reports = [AgentReport("LLMAgent:trade_flow", [], False, "ok")]
    narrow: dict = {}

    def narrow_fake(system, user, max_tokens=900):       # بلا timeout — كالقائم
        narrow["called"] = True
        return '{"verdict":"WATCH","confidence":0.5,"reasoning":"ok"}'

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_synthesis._call", side_effect=narrow_fake):
        v = silk_synthesis.synthesize(reports, product="تمور", market="ARE",
                                      with_ai=True)
    assert narrow.get("called") is True                  # لم يُكسَر المموّه
    assert v["synthesis_stage"] == 2 and "ai_error" not in v

    wide: dict = {}

    def wide_fake(system, user, max_tokens=900, model=None, timeout=None,
                  **kw):
        wide["timeout"] = timeout
        return '{"verdict":"WATCH","confidence":0.5,"reasoning":"ok"}'

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_synthesis._call", side_effect=wide_fake):
        silk_synthesis.synthesize(reports, product="تمور", market="ARE",
                                  with_ai=True)
    assert wide["timeout"] == aj._LONG_TIMEOUT           # ويصل من يقبله


def test_local_stage2_defect_is_reported_as_local_not_as_a_provider_failure(caplog):
    """المطلب: عطلٌ برمجيّ محليّ في المرحلة ٢ لا يلبس ثوبَ «المزوّد غير متاح».
    يُميَّز بـsource="local"، ويُسجَّل تحذيراً **بأثر المكدّس** — لا تدهورٌ صامت."""
    import logging
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_llm_provider as lp
    import silk_synthesis
    reports = [AgentReport("LLMAgent:trade_flow", [], False, "ok")]
    lp._last_error.set({"type": "ReadTimeout", "message": "خطأ مزوّدٍ قديم"})

    def local_bug(system, user, max_tokens=900, **kw):
        raise TypeError("unexpected keyword argument 'whatever'")

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_synthesis._call", side_effect=local_bug), \
         caplog.at_level(logging.WARNING, logger="silk_synthesis"):
        v = silk_synthesis.synthesize(reports, product="تمور", market="ARE",
                                      with_ai=True)
    err = v.get("ai_error") or {}
    assert err.get("source") == "local", err
    assert err.get("type") == "TypeError", err
    assert "ReadTimeout" not in str(err)          # لا يُنسَب لخطأ المزوّد القديم
    assert v["synthesis_stage"] == 1              # الجورية الحتمية قائمة
    recs = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert recs, "العطل المحليّ لم يُسجَّل"
    assert any(r.exc_info for r in recs), "التحذير بلا أثر مكدّس"


def test_provider_failure_is_reported_as_provider():
    from unittest.mock import patch
    from silk_agents import AgentReport
    import silk_llm_provider as lp
    import silk_synthesis
    reports = [AgentReport("LLMAgent:trade_flow", [], False, "ok")]

    def provider_fails(system, user, max_tokens=900, **kw):
        lp._last_error.set({"type": "ReadTimeout", "message": "idle"})
        return None

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
         patch("silk_synthesis._call", side_effect=provider_fails):
        v = silk_synthesis.synthesize(reports, product="تمور", market="ARE",
                                      with_ai=True)
    err = v.get("ai_error") or {}
    assert err.get("source") == "provider" and err.get("type") == "ReadTimeout"
