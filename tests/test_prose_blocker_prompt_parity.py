"""الدرس ٢٥٤ — الموجّهُ لا يُخالِف البوّابةَ التي تحكمه.

writer prompt vs. blocking gate: the instruction we hand the writer must not
itself contain what the gate blocks the writer for.

**الحادثةُ التي وُجد هذا الملفُّ من أجلها** (دراسة ماليزيا × قهوة محمصة،
٢٠٢٦-٠٩-١٧): الصنفُ ٨ سقّف تسميةَ نطاق الثقة في `silk_render.build_view`
(العرض) وفي `silk_quality_gate` (الحجب)، **ولم يصل السقفُ موجّهَ الكاتب**.
فسلّم `_summarize_verdict` الكاتبَ «الثقة: عالية (80%)» ومعه أمرٌ صريح: «درجة
الثقة الوحيدة المسموح ذكرها هي المذكورة أعلاه حرفياً». فكتب الكاتبُ في §١٠
«دخول مشروط بدرجة ثقة عالية» — **طائعاً** — فأطلق
`high_confidence_with_missing_pillar` غيرَ القابلِ للإصلاح (الراية مُفعَّلة)
فحُجبت الدراسةُ كلُّها بـ409 وقُرئ للعميل «أعِد توليد الدراسة». وإعادةُ
التوليد لا تُصلِح شيئاً: السببُ حتميٌّ يتكرّر بنفس المدخلات إلى الأبد.

القفلُ هنا مبنيٌّ على **الموجّه المبنيَّ فعلاً** لا على تركيبٍ يدويٍّ لأجزائه
(الدرس ١٨٦: اختبِر المفتاحَ الذي يبنيه الإنتاج). والفخُّ المقيسُ على هذه
الموجة نفسِها: كتابةُ النهي بلفظه («لا تكتب «ثقة عالية»») تُدخِل العبارةَ
الممنوعةَ في الموجّه — فالنهيُ يجب أن يُصاغ بلا لفظِ الممنوع.
"""
import os
import re

import pytest

import silk_quality_gate as Q


_PILLARS_GAP = {"market": {"value": None},
                "competition": {"value": 0.52},
                "profit": {"value": None}}
_ED_GAP = {"pillars": _PILLARS_GAP, "conditions": [],
           "confidence": 0.80, "score": 0.64}
_VERDICT = {"verdict": "CONDITIONAL-GO", "confidence": 0.80,
            "contributing_findings": [1] * 107}
_MISSIONS = {"trade_flows": {"summary": "واردات 2024 بلغت 89.4 مليون دولار",
                             "failed": False, "findings": []}}


def _build_writer_prompt(monkeypatch, *, discipline: str,
                         entry_decision=None) -> str:
    """الموجّهُ الذي يستلمه الكاتبُ فعلاً — يُقتنَص من نداء `_call` نفسِه."""
    monkeypatch.setenv("SILK_CONFIDENCE_DISCIPLINE", discipline)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-called")
    import silk_ai_judge as J
    seen: dict = {}

    def _fake_call(system, user, *a, **k):
        seen.setdefault("user", user)
        return ""

    monkeypatch.setattr(J, "_call", _fake_call)
    J.deep_report(_MISSIONS, "مسوّدة المحلل الشامل", _VERDICT,
                  "قهوة محمصة", "Malaysia", hs_code="090121",
                  entry_decision=entry_decision)
    assert seen.get("user"), "لم يُبنَ موجّهُ الكاتب — الاقتناصُ فشل"
    return seen["user"]


# ── (١) إعادةُ إنتاجِ الحادثة: السقفُ يصل الكاتب ───────────────────────────

def test_capped_band_reaches_the_writer_prompt(monkeypatch):
    """الرايةُ مُفعَّلة + عمودٌ أساسيٌّ مجهول ⇒ الموجّهُ يحمل «متوسطة»."""
    prompt = _build_writer_prompt(monkeypatch, discipline="1",
                                  entry_decision=_ED_GAP)
    assert "الثقة: متوسطة (80%)" in prompt
    assert "الثقة: عالية (80%)" not in prompt
    assert "سقف تسمية درجة الثقة" in prompt


def test_prompt_states_why_the_cap_applies(monkeypatch):
    """السببُ يُقال للكاتب — لا سقفٌ بلا علّةٍ يفهمها فيشرحها للقارئ."""
    prompt = _build_writer_prompt(monkeypatch, discipline="1",
                                  entry_decision=_ED_GAP)
    assert "مجهول" in prompt


def test_flag_off_prompt_is_byte_identical(monkeypatch):
    """مطفأةً: الموجّهُ حرفياً كما كان — لا سقفَ ولا سطرَ سببٍ ولا حرف."""
    on = _build_writer_prompt(monkeypatch, discipline="0",
                              entry_decision=_ED_GAP)
    bare = _build_writer_prompt(monkeypatch, discipline="0",
                                entry_decision=None)
    assert on == bare
    assert "الثقة: عالية (80%)" in on
    assert "سقف تسمية درجة الثقة" not in on


def test_no_cap_when_pillars_complete(monkeypatch):
    """أعمدةٌ كاملةٌ + بلا شروطٍ ⇒ لا سقف: التسميةُ الحقيقيةُ لا تُخفَض."""
    full = {"pillars": {"market": {"value": 0.7},
                        "competition": {"value": 0.4},
                        "profit": {"value": 0.6}},
            "conditions": [], "confidence": 0.80}
    prompt = _build_writer_prompt(monkeypatch, discipline="1",
                                  entry_decision=full)
    assert "الثقة: عالية (80%)" in prompt
    assert "سقف تسمية درجة الثقة" not in prompt


# ── (٢) القفلُ العام: الموجّهُ لا يحمل ما تحجبه البوّابة ────────────────────

def test_prompt_does_not_contain_what_the_gate_blocks(monkeypatch):
    """لكلّ فحصٍ في `PROSE_LITERAL_BLOCKERS`: نمطُه الممنوع **لا يُطابِق**
    موجّهَ الكاتبِ المبنيَّ فعلاً — وإلا فالحارسُ يُطلِق على أمرِنا نفسِه."""
    prompt = _build_writer_prompt(monkeypatch, discipline="1",
                                  entry_decision=_ED_GAP)
    for check, (pattern_name, _src) in Q.PROSE_LITERAL_BLOCKERS.items():
        pat = getattr(Q, pattern_name, None)
        assert pat is not None, (
            f"{check}: النمطُ المُعلَن {pattern_name} غيرُ موجودٍ في "
            "silk_quality_gate — سجلٌّ يسمّي رمزاً ميتاً لا يقفل شيئاً")
        assert isinstance(pat, re.Pattern)
        hit = pat.search(prompt)
        assert hit is None, (
            f"{check}: موجّهُ الكاتب يحمل العبارةَ التي يحجب عليها الفحصُ "
            f"نفسُه ({hit.group(0)!r}) — الكاتبُ سيُعاقَب على طاعته. صِغ "
            "التعليمة بلا لفظِ الممنوع، أو أصلِح منبعَ اللفظ في الموجّه.")


def test_every_flagged_blocker_is_classified():
    """كلُّ فحصٍ حاجبٍ مُفعَّلٍ براية **مصنَّفٌ** — إمّا بنمطٍ ثابتٍ مقفول،
    أو بسببٍ مكتوبٍ لعدم كونه لفظاً ثابتاً. لا فحصَ بلا تصنيف: هذا هو ما
    يمنع تكرارَ الحادثة على الفحصِ **القادم** لا على هذا وحده."""
    flagged = {t[0] for t in Q._FLAGGED_FAIL_TRIGGERS}
    classified = (set(Q.PROSE_LITERAL_BLOCKERS)
                  | set(Q.NON_LITERAL_FLAGGED_BLOCKERS))
    missing = sorted(flagged - classified)
    assert not missing, (
        f"فحوصٌ حاجبةٌ مُفعَّلةٌ براية بلا تصنيف: {missing}. أضِف لكلٍّ منها "
        "صفّاً في PROSE_LITERAL_BLOCKERS (نمطٌ ثابتٌ + مصدرُ تعليمته في "
        "موجّه الكاتب) أو في NON_LITERAL_FLAGGED_BLOCKERS بسببٍ مقيس.")
    stray = sorted(classified - flagged)
    assert not stray, (
        f"صفوفٌ في السجلّ لفحوصٍ لم تَعُد مُفعَّلةً براية: {stray} — "
        "سجلٌّ يوصّف ما لا وجود له يُوهِم بتغطيةٍ غائبة (الدرس ٩٨)")


def test_declared_prompt_sources_exist():
    """المصدرُ المُسمّى لكلّ نمطٍ ثابتٍ رمزٌ **موجود** فعلاً في وحدته."""
    import importlib
    for check, (_pat, (module, symbol)) in Q.PROSE_LITERAL_BLOCKERS.items():
        mod = importlib.import_module(module)
        assert hasattr(mod, symbol), (
            f"{check}: التعليمةُ المُعلَنة {module}.{symbol} غيرُ موجودة — "
            "مرساةٌ ميتة")


# ── (٣) العميلُ يقرأ سبباً صحيحاً ونصيحةً قابلةً للتنفيذ ───────────────────

def test_every_effective_fail_trigger_has_a_client_sentence(monkeypatch):
    """لا فحصٍ يقود FAIL بلا جملةِ عميلٍ مخصَّصة — الجملةُ العامّة تقول
    «يُغلقه: إعادة التوليد» وهي **نصيحةٌ خاطئة** على حاجبٍ حتميّ."""
    monkeypatch.setenv("SILK_CONFIDENCE_DISCIPLINE", "1")
    monkeypatch.setenv("SILK_FIGURE_STORE", "1")
    monkeypatch.setenv("SILK_OPEN_CONDITIONS_SINGLE", "1")
    monkeypatch.setenv("SILK_DERIVED_PROVENANCE", "1")
    import silk_export_gate as EG
    bare = sorted(c for c in Q.effective_fail_triggers()
                  if c not in EG._CLIENT_REASONS)
    assert not bare, f"فحوصٌ حاجبةٌ بلا جملةِ عميلٍ مخصَّصة: {bare}"


def test_deterministic_blocker_does_not_advise_regeneration():
    """`high_confidence_with_missing_pillar` حتميّ: إعادةُ التوليد تُعيد
    إنتاجَه حرفياً، فالنصيحةُ تُسمّي المدخلَ الناقص لا التكرار."""
    import silk_export_gate as EG
    ar = EG.client_reason("high_confidence_with_missing_pillar", "ar")
    en = EG.client_reason("high_confidence_with_missing_pillar", "en")
    assert "إعادة التوليد" not in ar or "لا تُغيّره" in ar
    assert "المدخل الناقص" in ar
    assert "re-evaluate" in en
    assert ar != EG._GENERIC_REASON["ar"]


# ── (٤) الحجبُ نفسُه يزول على نفس المدوّنة بعد وصولِ السقف ─────────────────

def test_gate_no_longer_blocks_a_compliant_report(monkeypatch):
    """عرضٌ يحمل التسميةَ المسقَّفة في العرضِ والنثرِ معاً: الفحصُ صامت.
    ونفسُ العرضِ بالتسميةِ العالية: يُطلِق غيرَ قابلٍ للإصلاح — فالفرقُ
    هو الطاعةُ لا الرقم (٨٠٪ في الحالتين)."""
    monkeypatch.setenv("SILK_CONFIDENCE_DISCIPLINE", "1")
    import importlib
    import silk_render
    importlib.reload(silk_render)
    good = ("الحكم الصادر هو دخول مشروط بدرجة ثقة متوسطة (80%) "
            "لأن جانب هامش الربحية لا نعرفه بعد.")
    bad = ("الحكم الصادر هو دخول مشروط بدرجة ثقة عالية "
           "استناداً إلى نمو الواردات.")
    for text, expect in ((good, False), (bad, True)):
        view = {"markets": [{"entry_decision": _ED_GAP}],
                "decision": {"basis": {}},
                "deep_research": {"report": {"text": text}}}
        out = Q._check_high_confidence_with_missing_pillar(
            view, view["deep_research"])
        assert bool(out) is expect, (text, out)
        if out:
            assert out[0]["repairable"] is False
