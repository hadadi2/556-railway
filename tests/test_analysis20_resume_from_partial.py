"""تحليل 20 — الخطوة ٣ (الاستئناف من الجزء): بذرُ مسوّدةٍ محفوظةٍ ٨/١١ قسماً
(شكلُ تحليل 20 الحقيقيّ: ١-٨ حاضرة، ٨ مقطوعٌ منتصف كلمة، ٩-١١ غائبة) يجب أن:

1. **يتخطّى نداء المسوّدة الكامل الغالي** (~١٦ألف رمز): أوّل نداء كاتبٍ هو
   **إكمالٌ** لا توليدُ مسوّدةٍ من الصفر — هذا جوهرُ «قروشٌ لا دولارات».
2. **يُكمِل الأقسام ٩-١١** فيُنتِج تقريراً مكتملاً.
3. حين يعجز الإكمال عن إضافة قسم: يُسلَّم الجزءُ ٨/١١ موسوماً «غير مكتمل» بلا
   نداءات إكمالٍ إضافيةٍ عقيمة (حارس تحليل 20) — استردادٌ صادقٌ لا هدرٌ لا نهائيّ.

مساراتُ الوصل (`api.py` resume + `POST /analyses/{id}/report`) مقفولةٌ في
`test_wave_p2_writer_trace_regen_sanitize`؛ هذا الملفّ يقفل السلوكَ من طرفٍ لطرف
داخل `deep_report`/`write_reviewed_report`. هرمتي بالكامل. Run:
  python3 -m pytest tests/test_analysis20_resume_from_partial.py -q
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


def _partial_8_of_11(lang="ar") -> str:
    """شكلُ جزء تحليل 20: الأقسام ١-٧ كاملة، ٨ (اللوجستيات) مقطوعٌ منتصف كلمة،
    و٩-١١ (المخاطر/التوصيات/الملاحق) غائبة."""
    from silk_ai_judge import report_sections
    secs = report_sections(lang)
    parts = [f"## {i}. {s}\nفقرة كاملة." for i, s in enumerate(secs[:7], 1)]
    parts.append(f"## 8. {secs[7]}\nفقرةُ اللوجستيات تنقطع منتصف كلم")
    return "\n".join(parts)


def _completion_9_to_11(lang="ar") -> str:
    """إكمالٌ يُتِمّ الكلمة المقطوعة ثم يكتب الأقسام ٩-١١."""
    from silk_ai_judge import report_sections
    secs = report_sections(lang)
    return "ة.\n" + "\n".join(f"## {i}. {s}\nفقرة." for i, s in
                              enumerate(secs[8:], 9))


def _is_continuation(user: str) -> bool:
    return "مهمة إكمال" in user


def _patch_call(script):
    import silk_llm_provider as lp
    seen: list[dict] = []

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        text, stop = script(user, max_tokens)
        seen.append({"cont": _is_continuation(user), "max_tokens": max_tokens})
        lp._last_stop_reason.set(stop)
        return text
    return seen, fake_call


def test_seed_skips_fresh_draft_and_completes_missing_sections():
    """بذرةٌ ٨/١١ → أوّل نداء إكمالٌ (لا مسوّدةَ صفرٍ غالية) والأقسام ٩-١١ تُكتب
    فيكتمل التقرير. لا نداءَ بسقف المسوّدة الكامل (`_WRITER_MAX_TOKENS`)."""
    import silk_ai_judge as aj
    seed = _partial_8_of_11()
    assert len(aj._missing_sections(seed)) == 3      # الشكل الصحيح للبذرة

    def script(user, cap):
        assert _is_continuation(user), "نداءٌ ليس إكمالاً — بُدِئت مسوّدةٌ من الصفر"
        return _completion_9_to_11(), "end_turn"

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا", trace_id="run-seed",
                             seed_draft=seed)
    assert [c["cont"] for c in seen] == [True]        # إكمالٌ واحد فقط
    assert aj._writer_incomplete(out) == []           # اكتمل ١١/١١
    for _s in aj.report_sections("ar"):
        assert f". {_s}" in out                       # كلّ الأقسام حاضرة


def test_seed_that_cannot_progress_delivers_partial_flagged_without_burn():
    """بذرةٌ ٨/١١ وإكمالٌ لا يضيف قسماً → يُسلَّم الجزءُ ٨/١١ موسوماً `incomplete`
    مع `missing_sections`، وتتوقّف الحلقةُ بعد نداءٍ واحدٍ عقيم (لا هدرَ تحليل 20)."""
    import silk_ai_judge as aj
    seed = _partial_8_of_11()

    def script(user, cap):
        return " ذيلٌ لا يضيف قسماً", "max_tokens"   # نصّ بلا عنوان قسم جديد

    seen, fake = _patch_call(script)
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x",
              SILK_WRITER_CONTINUATIONS="2"), \
         mock.patch("silk_ai_judge._call", side_effect=fake), \
         mock.patch("silk_ai_judge.review_report",
                    return_value={"approved": True, "issues": [],
                                  "blocking": False}):
        res = aj.write_reviewed_report(_mission_reports(), "محلل",
                                       {"verdict": "WATCH"}, "تمور", "هولندا",
                                       seed_draft=seed)
    assert [c["cont"] for c in seen] == [True]        # نداءٌ عقيمٌ واحدٌ ثم توقّف
    assert res["report"] and res["incomplete"] is True
    assert set(res["missing_sections"]) == {
        "تقييم المخاطر", "التوصيات الاستراتيجية", "الملاحق"}
    assert res["review_cycles"] == 0
