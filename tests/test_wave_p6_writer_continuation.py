"""الكاتب يُكمِل من الجزء المحفوظ لا يعيد التوليد — الموجة p6 (T7).

الفجوة الحرجة #3 (تدقيق 2026-08-22): عند stop_reason=max_tokens كان كل
«تصعيد» إعادةَ توليدٍ كاملةٍ بثمنٍ كامل للبرومبت نفسه بسقفٍ مضاعَف، ونصُّ
المحاولة السابقة يُحفَظ «الأطول يفوز» ولا يُكمَل — ثم يُهدَر كلُّه عند السقف.
العقد الجديد:
- نصٌّ مقتطع (max_tokens) أو بثٌّ مُجهَض (aborted_timeout) **ومعه نصّ** ⇒
  نداء إكمال من الذيل (`_continue_truncated_report`) — لا إعادة توليد.
- صفر نصّ (content=[]) ⇒ التصعيد المقيَّد القائم كما هو (قفل p5 لا يُمَسّ).
- الإكمال مقيَّد بـ`SILK_WRITER_CONTINUATIONS` (افتراضياً ٢).
- `on_attempt` قبل **كل** نداء كاتب (مسوّدة/إكمال) — لقطة تقدّم تحدّث
  updated_at فلا يحصد المكنَس تشغيلةً حيّة.
- الكاتب يبثّ (stream=True) ويبقى timeout=_LONG_TIMEOUT (الحقل المقفول).
- عند بقاء النقص بعد سقف الإكمال: report=None (§5) لكن `partial_text` يُعاد
  من write_reviewed_report كي يُخزَّن (لا نصّ مدفوع يُهدَر من القرص).
هرمتي بالكامل. Run: python -m pytest tests/test_wave_p6_writer_continuation.py -q
"""
import contextlib
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@contextlib.contextmanager
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


@pytest.fixture(autouse=True)
def _reset_provider_contextvars():
    import silk_llm_provider as lp
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)
    yield
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)


def _mission_reports():
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    return {"trade_flow": AgentReport(
        "LLMAgent:trade_flow",
        [DataPoint("واردات هولندا 33 مليون دولار", "UN Comtrade", 0.9, "note")],
        False, "ok")}


def _full_report(lang="ar") -> str:
    from silk_ai_judge import report_sections
    return "\n".join(f"## {i}. {s}\nفقرة." for i, s in
                     enumerate(report_sections(lang), 1))


def _truncated_report(lang="ar") -> str:
    from silk_ai_judge import report_sections
    secs = report_sections(lang)
    return f"## 1. {secs[0]}\nفقرة أولى.\n## 2. {secs[1]}\nفقرة ثانية تنقطع وسط"


def _rest_of_report(lang="ar") -> str:
    from silk_ai_judge import report_sections
    secs = report_sections(lang)
    return " الجملة.\n" + "\n".join(f"## {i}. {s}\nفقرة." for i, s in
                                    enumerate(secs[2:], 3))


def _is_continuation(user: str) -> bool:
    return "مهمة إكمال" in user


def _patch_call(script):
    """script(user, max_tokens) -> (text, stop_reason). يضبط last_stop_reason
    كما يفعل المزوّد الحقيقي ويعيد النصّ؛ يسجّل كل نداء."""
    import silk_llm_provider as lp
    seen: list[dict] = []

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        text, stop = script(user, max_tokens)
        seen.append({"cont": _is_continuation(user), "max_tokens": max_tokens,
                     "timeout": timeout, "stream": kw.get("stream"),
                     "user": user})
        lp._last_stop_reason.set(stop)
        if stop == "aborted_timeout":
            lp._last_error.set({"type": "ReadTimeout", "message": "idle"})
        return text
    return seen, fake_call


# ── (هـ) الإكمال بدل إعادة التوليد ─────────────────────────────────────────────

def test_truncation_with_text_continues_instead_of_regenerating():
    """الاختبار المطلوب (هـ): المحاولة الأولى مقتطعة **بنصّ** → النداء الثاني
    إكمالٌ (يحمل الذيل وعلامة الإكمال) بسقف الإكمال، ولا نداء يعيد إرسال
    برومبت المسوّدة بسقفٍ مضاعَف؛ النصّ النهائي = المسوّدة + الإكمال."""
    import silk_ai_judge as aj
    import silk_trace

    def script(user, cap):
        if _is_continuation(user):
            return _rest_of_report(), "end_turn"
        return _truncated_report(), "max_tokens"

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا", trace_id="run-p6-cont")
    assert [c["cont"] for c in seen] == [False, True]
    assert seen[1]["max_tokens"] == aj._MAX_TOKENS_CEILING
    assert "فقرة ثانية تنقطع وسط" in seen[1]["user"]           # الذيل مُمرَّر
    assert seen[0]["max_tokens"] == aj._WRITER_MAX_TOKENS
    assert all(c["max_tokens"] != 2 * aj._WRITER_MAX_TOKENS or c["cont"]
               for c in seen), "a doubled-cap regeneration happened"
    assert out and out.startswith(_truncated_report()[:30])
    assert aj._writer_incomplete(out) == []
    stages = [e["stage"] for e in silk_trace.read_trace("run-p6-cont")
              if e.get("kind") == "report_call"]
    assert stages == ["draft", "draft_continue"]


def test_continuation_no_progress_stops_and_delivers_partial():
    """بلاغ تحليل 20 (تجاوز §5-الإتلاف + حارس العملية المدفوعة العقيمة):
    إكمالٌ لا يضيف قسماً ولا يُنهي جملةً مقطوعة → الحلقة **تتوقّف بعده فوراً**
    (لا تُنفَق نداءات إكمال إضافية على عملية عقيمة، وإن كان SILK_WRITER_
    CONTINUATIONS=2)، والمسوّدة الناقصة **تُسلَّم** موسومةً `incomplete` مع
    `missing_sections` — لا `report=None`."""
    import silk_ai_judge as aj

    def script(user, cap):
        if _is_continuation(user):
            return " جزء إضافي مقتطع أيضاً", "max_tokens"   # نصّ بلا عنوان قسم
        return _truncated_report(), "max_tokens"

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x",
              SILK_WRITER_CONTINUATIONS="2"), \
         mock.patch("silk_ai_judge._call", side_effect=fake), \
         mock.patch("silk_ai_judge.review_report",
                    return_value={"approved": True, "issues": [], "blocking": False}):
        res = aj.write_reviewed_report(_mission_reports(), "محلل",
                                       {"verdict": "WATCH"}, "تمور", "هولندا")
    # مسوّدة + إكمالٌ واحدٌ عقيم ثم توقّف (لا إكمالٌ ثانٍ مدفوعٌ بلا جدوى)
    assert [c["cont"] for c in seen] == [False, True]
    # قرار المالك: المسوّدة الأصلية تُسلَّم موسومةً، لا تُتلَف
    assert res["report"] and res["incomplete"] is True
    # مخرَج الإكمال العقيم يُهمَل (حشوٌ لا يزيد التغطية) — لا يُلوّث الجزء
    assert "جزء إضافي مقتطع" not in res["report"]
    assert res["report"].startswith(_truncated_report()[:20])
    assert res["missing_sections"]            # أقسام غائبة معلَنة
    assert res["review_cycles"] == 0          # المراجع مُتخطّى على الناقص
    assert res["partial_text"] == res["report"]


def test_progressing_continuation_is_retained_and_completes():
    """إكمالٌ **يزيد تغطية الأقسام** يُحتفَظ به ويُكمِل التقرير — لا يوقفه حارس
    العملية العقيمة (الذي يمنع فقط الإكمالات التي لا تضيف قسماً)."""
    import silk_ai_judge as aj

    def script(user, cap):
        if _is_continuation(user):
            return _rest_of_report(), "end_turn"      # يضيف الأقسام ٣-١١
        return _truncated_report(), "max_tokens"

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x",
              SILK_WRITER_CONTINUATIONS="2"), \
         mock.patch("silk_ai_judge._call", side_effect=fake):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا", trace_id="run-progress")
    assert [c["cont"] for c in seen] == [False, True]   # إكمالٌ واحدٌ كفى
    assert aj._writer_incomplete(out) == []             # اكتمل


def test_deep_report_returns_partial_not_none_when_incomplete():
    """تجاوز §5-الإتلاف على مستوى deep_report: مسوّدة ناقصة بنيوياً تُعاد
    **نصّاً** (لا None) — None محفوظ لصفر النصّ الحقيقي وحده."""
    import silk_ai_judge as aj

    def script(user, cap):
        # الإكمال لا يضيف قسماً (نصّ فقط) → يبقى ناقصاً بعد الحارس
        if _is_continuation(user):
            return " ذيلٌ لا يضيف قسماً", "max_tokens"
        return _truncated_report(), "max_tokens"

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x",
              SILK_WRITER_CONTINUATIONS="2"), \
         mock.patch("silk_ai_judge._call", side_effect=fake):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا", trace_id="run-partial")
    assert out                                   # نصّ جزئي، لا None
    assert aj._writer_incomplete(out)            # ما زال ناقصاً (معلَن للمستدعي)
    assert out.startswith(_truncated_report()[:20])


def test_zero_text_max_tokens_still_escalates_like_before():
    """صفر نصّ (content=[]) — لا شيء يُكمَل: التصعيد المقيَّد القائم كما هو
    (caps [base, ceiling] بالرمز ثم None)."""
    import silk_ai_judge as aj
    import silk_llm_provider as lp
    caps: list[int] = []

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        caps.append(max_tokens)
        lp._last_stop_reason.set("max_tokens")
        lp._last_error.set({"type": "empty_response", "message": "no text"})
        return None

    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake_call):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا")
    assert out is None
    assert caps == [aj._WRITER_MAX_TOKENS, aj._MAX_TOKENS_CEILING]


# ── الإجهاض المبثوث يدخل مسار الإكمال ────────────────────────────────────────

def test_aborted_timeout_partial_enters_continuation():
    """بثّ الكاتب أُجهِض (خمول) بنصّ جزئي → إكمال من الذيل، لا None ولا إعادة
    توليد — هذا بالضبط ما ضاع في الفرع ب الحيّ."""
    import silk_ai_judge as aj

    def script(user, cap):
        if _is_continuation(user):
            return _rest_of_report(), "end_turn"
        return _truncated_report(), "aborted_timeout"

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا")
    assert [c["cont"] for c in seen] == [False, True]
    assert out and aj._writer_incomplete(out) == []


# ── لقطة التقدّم لكل نداء + البثّ + المهلة المقفولة ─────────────────────────

def test_on_attempt_fires_before_every_writer_call_including_continuations():
    import silk_ai_judge as aj
    stages: list[str] = []

    from silk_ai_judge import report_sections
    secs = report_sections("ar")
    calls = {"n": 0}

    def script(user, cap):
        # كل إكمال **يزيد التغطية** فتمرّ المحاولتان (لا يوقفهما حارس العملية
        # العقيمة) — فيثبت أن on_attempt يُطلَق قبل كل نداء كاتب بما فيه الإكمالان.
        if _is_continuation(user):
            calls["n"] += 1
            if calls["n"] == 1:
                return (" الجملة.\n" + "\n".join(
                    f"## {i}. {secs[i-1]}\nفقرة." for i in range(3, 7)),
                    "max_tokens")
            return ("\n".join(f"## {i}. {secs[i-1]}\nفقرة."
                              for i in range(7, 12)), "end_turn")
        return _truncated_report(), "max_tokens"

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x",
              SILK_WRITER_CONTINUATIONS="2"), \
         mock.patch("silk_ai_judge._call", side_effect=fake), \
         mock.patch("silk_ai_judge.review_report",
                    return_value={"approved": True, "issues": [], "blocking": False}):
        aj.write_reviewed_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                                 "تمور", "هولندا", on_stage=stages.append)
    writer_pings = [s for s in stages if s == "writer"]
    assert len(writer_pings) == len(seen) == 3   # واحدة قبل كل نداء كاتب


def test_writer_passes_stream_true_and_locked_long_timeout():
    import silk_ai_judge as aj

    def script(user, cap):
        return _full_report(), "end_turn"

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا")
    assert out and len(seen) == 1
    assert seen[0]["stream"] is True
    assert seen[0]["timeout"] == aj._LONG_TIMEOUT


def test_continuations_cap_reads_env_with_default_two():
    import silk_ai_judge as aj
    with _env(SILK_WRITER_CONTINUATIONS=None):
        assert aj._writer_continuations() == 2
    with _env(SILK_WRITER_CONTINUATIONS="5"):
        assert aj._writer_continuations() == 5
    with _env(SILK_WRITER_CONTINUATIONS="garbage"):
        assert aj._writer_continuations() == 2


def test_continuation_starting_with_heading_is_joined_on_new_line():
    """إكمالٌ يبدأ بعنوان قسم (القطع وقع عند حدّ قسم) يُلحَق على **سطر جديد** —
    كان يُلصَق بمسافة فلا يُعَدّ العنوان (يُعَدّ عند بداية السطر فقط) ويُرفَض
    التقرير المكتمل فعلاً بـ§5."""
    import silk_ai_judge as aj

    def script(user, cap):
        if _is_continuation(user):
            return _full_report(), "end_turn"          # يبدأ بـ"## 1."
        return "## 0. مقدّمة\nجملة كاملة.", "max_tokens"

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا")
    assert out and aj._writer_incomplete(out) == []
    assert "\n## 1. " in out                            # العنوان على سطره


def test_writer_ignores_stale_stop_reason_from_a_previous_call():
    """T7 fix-up ٢: stop_reason قديم في contextvar المزوّد (نداء سابق في السياق
    نفسه، و`_call` الحالي لم يمرّ بالمزوّد فلم يُعِد ضبطه) **لا** يطلق إكمالاً
    على مسوّدة مكتملة من نداء واحد — القرار يقرأ دليل هذا النداء حصراً."""
    import silk_ai_judge as aj
    import silk_llm_provider as lp
    calls: list = []

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        calls.append(1)
        return _full_report()            # لا يلمس contextvars المزوّد

    lp._last_stop_reason.set("max_tokens")          # بقايا نداء سابق
    lp._last_error.set({"type": "ReadTimeout", "message": "stale"})
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake_call):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا")
    assert len(calls) == 1, "stale stop_reason triggered a continuation"
    assert out and aj._writer_incomplete(out) == []
