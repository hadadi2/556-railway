"""تحليل 20 — الخطوة ٢ (قرار المالك): تقريرٌ حاضرةٌ فيه الأقسام الأحد عشر كلّها
لكنه ينتهي بجملةٍ مقطوعة تقريرٌ **مكتمل** رُفِض على نقطةٍ ناقصة — لا هيكلٌ ناقص.
نقصّ الشَّظِيّة المعلَّقة (الجملة الأخيرة غير المكتملة) ونقبله مكتملاً بدل تسليمه
موسوماً «غير مكتمل». حتمي بلا نداء كلود.

الحارس (لا نُخفي اقتطاعاً حقيقياً): يُطبَّق **فقط** حين تكون كلّ الأقسام حاضرة
والنقص الوحيد «قطع وسط جملة»، والشَّظِيّة المقصوصة صغيرة؛ نقصٌ بنيويّ (قسمٌ غائب)
أو شظيّةٌ كبيرة (اقتطاعٌ حقيقيّ لفقرة) يبقى موسوماً كما هو.

هرمتي بالكامل. Run:
  python3 -m pytest tests/test_analysis20_trailing_fragment.py -q
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


def _full_but_dangling(lang="ar") -> str:
    """كل الأقسام الأحد عشر حاضرة، لكن القسم الأخير ينتهي بجملةٍ مقطوعة قصيرة."""
    from silk_ai_judge import report_sections
    secs = report_sections(lang)
    parts = [f"## {i}. {s}\nفقرة كاملة." for i, s in enumerate(secs[:-1], 1)]
    parts.append(f"## {len(secs)}. {secs[-1]}\nفقرة أخيرة كاملة. وجملةٌ تنقطع وسط")
    return "\n".join(parts)


def _full_last_section_is_all_fragment(lang="ar") -> str:
    """كل العناوين حاضرة لكن القسم الأخير كلُّه شظيّةٌ طويلة بلا نهايةٍ مقبولة —
    اقتطاعٌ حقيقيّ لا شظيّةٌ مهمَلة؛ يجب أن يبقى موسوماً (لا نُخفيه بالقصّ)."""
    from silk_ai_judge import report_sections
    secs = report_sections(lang)
    parts = [f"## {i}. {s}\nفقرة كاملة." for i, s in enumerate(secs[:-1], 1)]
    parts.append(f"## {len(secs)}. {secs[-1]}\n" + "كلمةٌ " * 200)
    return "\n".join(parts)


def _missing_and_dangling(lang="ar") -> str:
    from silk_ai_judge import report_sections
    secs = report_sections(lang)
    return f"## 1. {secs[0]}\nفقرة أولى.\n## 2. {secs[1]}\nفقرة ثانية تنقطع وسط"


# ── وحدة: `_finalize_trailing_fragment` ────────────────────────────────────

def test_finalize_trims_dangling_fragment_when_all_sections_present():
    import silk_ai_judge as aj
    src = _full_but_dangling()
    assert aj._writer_incomplete(src) == ["قطع وسط جملة"]   # قبل: موسوم بالقطع
    out = aj._finalize_trailing_fragment(src)
    assert aj._writer_incomplete(out) == []                 # بعد: مكتمل
    assert out.rstrip().endswith("فقرة أخيرة كاملة.")       # قُصّت الشظيّة فقط
    assert "وجملةٌ تنقطع وسط" not in out


def test_finalize_leaves_structurally_incomplete_report_flagged():
    """قسمٌ غائب = نقصٌ بنيويّ لا شظيّة — لا يُقصّ ولا يُقبل مكتملاً."""
    import silk_ai_judge as aj
    src = _missing_and_dangling()
    out = aj._finalize_trailing_fragment(src)
    assert out == src                                       # بلا تغيير
    assert aj._writer_incomplete(out)                       # ما زال ناقصاً


def test_finalize_is_noop_on_already_complete_report():
    import silk_ai_judge as aj
    from silk_ai_judge import report_sections
    complete = "\n".join(f"## {i}. {s}\nفقرة كاملة." for i, s in
                         enumerate(report_sections("ar"), 1))
    assert aj._finalize_trailing_fragment(complete) == complete
    assert aj._writer_incomplete(complete) == []


def test_finalize_refuses_to_mask_a_whole_truncated_last_section():
    """شظيّةٌ كبيرة (القسم الأخير كلُّه مقطوع) = اقتطاعٌ حقيقيّ — يبقى موسوماً،
    لا يُخفى بقصّ فقرةٍ كاملة (عقد لا-اختلاق: لا نُظهر ناقصاً مكتملاً)."""
    import silk_ai_judge as aj
    src = _full_last_section_is_all_fragment()
    out = aj._finalize_trailing_fragment(src)
    assert out == src
    assert aj._writer_incomplete(out)                       # يبقى موسوماً


# ── تكامل: عبر deep_report / write_reviewed_report ─────────────────────────

def test_deep_report_accepts_complete_report_with_trailing_fragment():
    """مسوّدةُ نداءٍ واحد بكل الأقسام لكنها تنتهي بجملةٍ مقطوعة (end_turn) —
    تُقبَل مكتملةً بعد قصّ الشظيّة، لا تُسلَّم موسومةً «غير مكتملة»."""
    import silk_ai_judge as aj

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        return _full_but_dangling()

    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake_call):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا", trace_id="run-frag")
    assert out and aj._writer_incomplete(out) == []
    assert "وجملةٌ تنقطع وسط" not in out


def test_write_reviewed_report_delivers_fragment_report_as_complete():
    import silk_ai_judge as aj

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        return _full_but_dangling()

    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake_call), \
         mock.patch("silk_ai_judge.review_report",
                    return_value={"approved": True, "issues": [],
                                  "blocking": False}):
        res = aj.write_reviewed_report(_mission_reports(), "محلل",
                                       {"verdict": "WATCH"}, "تمور", "هولندا")
    assert res["report"]
    assert not res.get("incomplete")                       # سُلِّم مكتملاً
    assert not res.get("missing_sections")


# ── تصلّبات المراجعة الذاتية §58 (الملاحظات ١-٤) ───────────────────────────

def test_finalize_does_not_swallow_complete_bulleted_last_section():
    """مراجعة §58 #1: قسمٌ أخيرٌ بقائمةٍ نقطية (أسطرٌ كاملةٌ بلا نقطة) وكلمةٌ
    مقطوعةٌ آخرَه — القصُّ إلى آخر نقطةٍ سيبتلع القائمةَ كلَّها ويُخفي اقتطاعاً؛
    وجودُ سطرٍ جديدٍ في الشظيّة يمنع القصّ، فيبقى موسوماً (لا محتوى يُبتلع)."""
    import silk_ai_judge as aj
    from silk_ai_judge import report_sections
    secs = report_sections("ar")
    parts = [f"## {i}. {s}\nفقرة كاملة." for i, s in enumerate(secs[:-1], 1)]
    parts.append(f"## {len(secs)}. {secs[-1]}\nمقدّمةٌ كاملة.\n"
                 "- البند الأول\n- البند الثاني\n- بندٌ ثالثٌ ينقطع وسط")
    src = "\n".join(parts)
    out = aj._finalize_trailing_fragment(src)
    assert out == src                                       # لم يُبتلع شيء
    assert "البند الأول" in out and "البند الثاني" in out   # القائمة سليمة
    assert aj._writer_incomplete(out)                       # يبقى موسوماً بصدق


def test_finalize_trims_only_to_a_true_terminator_not_a_bracket():
    """مراجعة §58 #2: القصُّ إلى منهي جملةٍ حقيقيّ (.؟?!) لا إلى «)» أو «:» —
    شظيّةٌ بعد نقطةٍ تحوي قوساً مغلقاً تُقصّ إلى النقطة، فلا يُسلَّم «…(قوس)»
    مبتوراً بوصفه مكتملاً."""
    import silk_ai_judge as aj
    from silk_ai_judge import report_sections
    secs = report_sections("ar")
    parts = [f"## {i}. {s}\nفقرة كاملة." for i, s in enumerate(secs[:-1], 1)]
    parts.append(f"## {len(secs)}. {secs[-1]}\nخلاصةٌ مكتملة. ثم (إحالةٌ) وكلمةٌ تنقطع")
    src = "\n".join(parts)
    out = aj._finalize_trailing_fragment(src)
    assert aj._writer_incomplete(out) == []
    assert out.rstrip().endswith("خلاصةٌ مكتملة.")          # قُصّ إلى النقطة
    assert not out.rstrip().endswith(")")                   # لا إلى القوس


def test_english_report_ending_in_question_is_complete():
    """مراجعة §58 #3: تقريرٌ إنجليزيٌّ كامل ينتهي بسؤالٍ «?» مكتملٌ لا مقطوع —
    «?» اللاتينية في مجموعة النهايات، فلا يُوسَم ولا تُقصّ جملتُه الأخيرة."""
    import silk_ai_judge as aj
    secs = aj.report_sections("en")
    body = "\n".join(f"## {i}. {s}\nA complete paragraph." for i, s in
                     enumerate(secs[:-1], 1))
    body += f"\n## {len(secs)}. {secs[-1]}\nIs this market viable for Saudi dates?"
    assert aj._writer_incomplete(body, "en") == []          # مكتملٌ لا مقطوع
    assert aj._finalize_trailing_fragment(body, "en") == body   # بلا قصّ


def test_seed_with_all_sections_dangling_spends_zero_continuation_calls():
    """مراجعة §58 #4: بذرةٌ ١١/١١ تنتهي بجملةٍ مقطوعة تُقصّ **قبل** حلقة الإكمال
    فلا يُنفَق نداءُ إكمالٍ مدفوعٌ عقيم — صفر نداء كاتب، تقريرٌ مكتمل."""
    import silk_ai_judge as aj
    calls = {"n": 0}

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None, **kw):
        calls["n"] += 1
        return "لا ينبغي أن يُستدعى"

    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("silk_ai_judge._call", side_effect=fake_call):
        out = aj.deep_report(_mission_reports(), "محلل", {"verdict": "WATCH"},
                             "تمور", "هولندا", trace_id="run-seed-frag",
                             seed_draft=_full_but_dangling())
    assert calls["n"] == 0                                  # لا نداء إطلاقاً
    assert out and aj._writer_incomplete(out) == []         # اكتمل بالقصّ فقط
