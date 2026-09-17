"""الصوت البشري في نص التقرير — اختبارٌ أوّلاً (طلب المالك «Humanized»).

العيبُ المُعاد إنتاجُه: الصوتَ الآليَّ **عقودُنا** تأمر به، لا النموذج يخترعه.
وكلُّ تغييرِ نبرةٍ خلف `SILK_HUMAN_VOICE` المطفأةِ افتراضياً؛ مطفأةً يبقى
الموجّهُ حرفياً كما كان.

Run: python3 -m pytest tests/test_report_voice_human.py -q
"""
from __future__ import annotations

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from conftest import block_network  # noqa: E402


class _env:
    """متغيّراتُ بيئةٍ باستعادةٍ مضمونة — اصطلاحُ هذه الحزمة."""

    def __init__(self, **vals):
        self.vals, self.old = vals, {}

    def __enter__(self):
        for k, v in self.vals.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def _repo(name: str) -> str:
    return open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), name), encoding="utf-8").read()


def _canonical_keys() -> list:
    from tools import gen_verdict_baseline as B
    return sorted(B.CANONICAL_BLOBS)


def _view(key: str) -> dict:
    import silk_render
    from tools import gen_verdict_baseline as B
    mod, fn = B.CANONICAL_BLOBS[key]
    return silk_render.build_view(getattr(importlib.import_module(mod), fn)())


# ══════════ العيبُ المُعاد إنتاجُه: العقودُ تأمر بالصيغ الجاهزة ══════════

def test_every_stock_phrase_is_one_our_own_contracts_prescribe():
    """هذا هو العيبُ حرفياً: الصوتُ الآليُّ **من كتابتنا**. لو كانت عبارةٌ
    في القائمة لا يأمر بها عقدٌ في الريبو لكان لومُ النموذج عليها ظلماً —
    والقائمةُ تُصان بهذا الشرط: كلُّ عبارةٍ فيها مأمورٌ بها في
    `silk_style_contract` نفسِه."""
    import silk_style_contract as S
    src = _repo("silk_style_contract.py")
    # تُستثنى البدائلُ الطبيعية: حضورُها في الملف من هذه القاعدة لا من عقدٍ.
    rule_start = src.index("HUMAN_VOICE_FLAG")
    contracts_src = src[:rule_start]
    prescribed = [p for p in S.stock_phrases() if p in contracts_src]
    assert len(prescribed) >= 6, prescribed
    for needle in ("توصي الدراسة", "تشير النتائج", "ينبغي التعامل مع",
                   "وهذا يعني"):
        assert needle in contracts_src, needle


def test_the_rule_is_silent_until_the_flag_is_on():
    """عقدُ عدم المساس: مطفأةً تُعيد الدالّتان فراغاً، فالموجّهُ كما كان."""
    import silk_style_contract as S
    for val in (None, "", "0", "no", "off"):
        with _env(SILK_HUMAN_VOICE=val):
            assert S.human_voice_rule() == ""
            assert S.human_voice_rule_en() == ""
    for val in ("1", "true", "yes"):
        with _env(SILK_HUMAN_VOICE=val):
            assert S.HUMAN_VOICE_RULE == S.human_voice_rule()
            assert S.HUMAN_VOICE_RULE_EN == S.human_voice_rule_en()


def test_the_writer_prompt_is_byte_identical_with_the_flag_off():
    """الدليلُ على «صفر فرق»: عقدُ الكاتب المبنيُّ مطفأةً **بايتاً ببايت**
    كالمبنيّ بلا وجودِ الراية أصلاً؛ ومفعّلةً يزيد بالقاعدة وحدَها."""
    import silk_style_contract as S
    base = S.WRITER_STYLE_CONTRACT
    with _env(SILK_HUMAN_VOICE=None):
        assert base + S.human_voice_rule() == base
    with _env(SILK_HUMAN_VOICE="1"):
        built = base + "\n\n" + S.human_voice_rule()
        assert built.startswith(base) and len(built) > len(base)
        assert "خاطِب القارئ" in built


def test_the_rule_never_touches_the_truth_layer():
    """الحدُّ الذي لا يُعبَر: النبرةُ وحدَها. لو مسّت القاعدةُ أفعالَ طبقات
    الأدلة لصار رقمٌ مشتقٌّ يُقرَأ مرصوداً — أخطرُ من أيّ جفافٍ أسلوبيّ."""
    import silk_style_contract as S
    rule = S.HUMAN_VOICE_RULE
    assert "لا يمسّ رقماً ولا مصدراً ولا أفعالَ طبقات الأدلة" in rule
    for verb in S.OBSERVED_VERBS + S.INFERRED_VERBS + S.PARAMETER_VERBS:
        assert f"«{verb}»" not in rule, verb
    # ومنعُ التهويل باقٍ صراحةً — «بشري» ليس «متحمّس».
    assert "التهويل" in rule and "استعارة" in rule
    # وسقفُ الخلاصة وترتيبُها لم يُلغَيا، إنما القالبُ الحرفيّ وحدَه.
    assert "الترتيبُ يبقى" in rule and "مئة والخمسين" in rule


# ══════════════════ الحارس: نثرٌ قالبيٌّ يُرصَد ولا يُلام الصحيح ══════════

def test_the_guard_fires_on_dense_filler_and_offers_the_alternative():
    import silk_quality_gate as G
    dense = (("وهذا يعني كذا. من الجدير بالذكر كذا. وفي هذا السياق كذا. "
              "تجدر الإشارة كذا. ") * 8) + ("كلمة " * 150)
    with _env(SILK_HUMAN_VOICE="1"):
        out = G._check_robotic_stock_phrase(dense)
    assert len(out) == 1 and out[0]["check"] == "robotic_stock_phrase"
    assert out[0]["repairable"] is True
    assert "«أي أنّ»" in out[0]["note"]          # البديلُ يُقال لا اللومُ وحده


def test_the_guard_measures_density_not_variety():
    """مأخذُ المراجعة الذاتية: العدُّ بالصيغ **المختلفة** كان يعاقب التنويع —
    ثلاثُ صيغٍ مرّةً واحدةً تُطلِق، وتكرارُ واحدةٍ ثلاثاً يصمت. والعتبةُ
    مقيسةٌ على متونٍ حقيقيةِ الطول: أعلى مشروعٍ 7.09 فالحدّ 12."""
    import silk_quality_gate as G
    assert G._FILLER_PER_1K_MAX == 12.0
    light = ("وهذا يعني كذا. من الجدير بالذكر كذا. وفي هذا السياق كذا. "
             + "كلمة " * 400)
    with _env(SILK_HUMAN_VOICE="1"):
        assert G._check_robotic_stock_phrase(light) == []
        # ومتنٌ قصيرٌ لا يُقاس — الكثافةُ على عيّنةٍ صغيرةٍ ضجيج.
        assert G._check_robotic_stock_phrase("وهذا يعني كذا. " * 5) == []


def test_the_guard_is_silent_while_the_prompt_has_no_such_instruction():
    """مأخذُ المراجعة الذاتية: الحارسُ كان يعمل بلا راية بينما العلاجُ خلفها
    — فيُلام كاتبٌ **أطاع عقدَه** ولا إرشادَ في موجّهه يتبعه."""
    import silk_quality_gate as G
    dense = (("وهذا يعني كذا. من الجدير بالذكر كذا. وفي هذا السياق كذا. "
              "تجدر الإشارة كذا. ") * 8) + ("كلمة " * 150)
    for off in (None, "", "0", "off"):
        with _env(SILK_HUMAN_VOICE=off):
            assert G._check_robotic_stock_phrase(dense) == [], off


def test_no_banned_phrase_collides_with_a_mandated_output():
    """**أخطرُ مآخذ المراجعة الذاتية**: «ينبغي التعامل مع» كانت ممنوعةً وهي
    صدرُ `MEASURED_TONE_HINT` — مُخرَجٌ إلزاميٌّ يفرضه المراجعُ نفسُه. فمنعُها
    يأمر الكاتبَ بإسقاط تحذيرٍ واجب (الدرس ٢٣٩: عقابُ الإفصاح أسوأ من
    غيابه). والقفلُ الدائم في
    `tests/test_mandated_literals_cross_reference.py`."""
    import silk_ai_judge as AJ
    import silk_quality_gate as G
    import silk_style_contract as S
    banned = tuple(S.FILLER_PHRASES) + S.stock_phrases()
    for lit in AJ.MANDATED_OUTPUT_LITERALS:
        n_lit = G._norm_ar(lit)
        for b in banned:
            nb = G._norm_ar(b)
            assert not (nb and nb in n_lit), (lit, b)
    assert S.MEASURED_TONE_HINT.startswith("ينبغي التعامل مع")


def test_the_flag_parser_accepts_the_same_words_as_its_neighbours():
    """مأخذُ المراجعة الذاتية: `on` كانت تمرّ صامتةً بلا أثر."""
    import silk_style_contract as S
    for on in ("1", "true", "yes", "on", "ON", " On "):
        with _env(SILK_HUMAN_VOICE=on):
            assert S.human_voice() is True, on
    for off in (None, "", "0", "no", "off", "false"):
        with _env(SILK_HUMAN_VOICE=off):
            assert S.human_voice() is False, off


def test_the_academic_register_is_left_alone():
    """مأخذُ المراجعة الذاتية: القاعدةُ كانت تُلحَق حتى في السجل الأكاديميّ،
    فيتلقّى الكاتبُ قاعدتين إلزاميتين متناقضتين (الأكاديميُّ يمنع خطابَ
    القارئ ويأمر بالصيغ الثلاث التي تمنعها هذه)."""
    src = _repo("silk_ai_judge.py")
    i = src.index("from silk_style_contract import human_voice_rule")
    assert '"" if academic else' in src[i:i + 320]


def test_the_guard_is_silent_on_every_corpus_with_the_flag_either_way():
    """صفرُ إطلاقةٍ على الست عشرة بالرايتين — قاعدةٌ تُطلِق على الصحيح لا
    تُشحَن (سابقةُ الصنف ١١)."""
    import silk_quality_gate as G
    for flag in (None, "1"):
        with _env(SILK_HUMAN_VOICE=flag), block_network():
            for key in _canonical_keys():
                dr = _view(key).get("deep_research") or {}
                assert G._check_robotic_stock_phrase(
                    G._report_text(dr)) == [], (key, flag)
    # وأعلى كثافةٍ مشروعةٍ مقيسة (مصر) تحت الحدّ — والمحاولةُ الأولى 6.0
    # كانت تُطلِق عليها، فلولا القياسُ لشُحِنت قاعدةٌ تُدين الصحيح.
    with _env(SILK_HUMAN_VOICE="1"), block_network():
        dr = _view("egypt_olive_oil").get("deep_research") or {}
        body = G._split_off_appendix(G._report_text(dr))
        flat = G._flat_ar(body)
        import silk_style_contract as S
        hits = sum(flat.count(G._flat_ar(p)) for p in S.filler_phrases())
        density = hits * 1000.0 / len(body.split())
        assert 6.0 < density < G._FILLER_PER_1K_MAX, density


def test_the_guard_reads_the_prompt_list_not_a_second_copy():
    """مصدرٌ واحد: لو نُسِخت القائمةُ إلى البوابة لافترقت عن قائمة الكاتب
    عند أوّل تعديل (نفسُ مبدأ `FORBIDDEN_READER_PHRASES`)."""
    gate = _repo("silk_quality_gate.py")
    i = gate.index("def _check_robotic_stock_phrase")
    body = gate[i:i + 1600]
    assert "silk_style_contract" in body and "STOCK_PHRASES" in body
    import silk_style_contract as S
    assert "FILLER_PHRASES" in body or "filler_phrases" in body
    for phrase in tuple(S.FILLER_PHRASES) + S.stock_phrases():
        assert f'"{phrase}"' not in body, phrase


# ══════════════ التعليقاتُ القديمة عن الأسلوب الافتراضيّ ══════════════

def test_the_default_report_style_is_decision_and_the_comments_say_so():
    """مأخذُ القراءة: تعليقتان كانتا تقولان إنّ الأكاديميّ هو الافتراض،
    والقارئُ الفعليّ يُرجِع `decision` — حدٌّ مُعلَنٌ يخالف المقيس."""
    with _env(SILK_REPORT_STYLE=None):
        import silk_research_pipeline  # noqa: F401
        src = _repo("silk_research_pipeline.py")
        assert 'os.environ.get("SILK_REPORT_STYLE", "decision")' in src
    for name in ("api.py", "silk_ai_judge.py"):
        src = _repo(name)
        assert 'المضبوط "academic"' not in src, name
        assert 'مضبوطٌ "academic"' not in src, name


def _blocking(findings: list) -> set:
    """أسماءُ الفحوص غيرِ القابلة للإصلاح — ما يصنع الحجبَ فعلاً."""
    return {f["check"] for f in findings if not f.get("repairable")}


def test_the_guard_fires_through_run_quality_gate_not_only_when_called_direct():
    """الدرس ١٨٦: نداءٌ مباشرٌ للدالّة ليس دليلاً على أنّ الحارسَ حيٌّ في
    الإنتاج. هذا القفلُ يمرّ بـ`run_quality_gate` على **عرضٍ يبنيه**
    `build_view` فعلاً، ويُثبِت أيضاً أنّ البلاغَ تحذيريٌّ لا حاجب.

    وقياسُ هذا القفل نفسُه كشف أنّ حقنَ النثرِ بعد عنوان الملاحق لا يُطلِق —
    وهو **سلوكٌ صحيح**: `_split_off_appendix` يقصّ قائمةَ المراجع بحقّ."""
    import importlib

    import silk_quality_gate as G
    import silk_render
    from tools import gen_verdict_baseline as B

    mod, fn = B.CANONICAL_BLOBS["egypt_olive_oil"]
    # حشوٌ كثيفٌ **بلا تكرارٍ حرفيّ**: التثبيتةُ الأولى أعادت الجملةَ نفسَها
    # ثماني مرّات فحجبها `repeated_span` — أثرُ التثبيتة لا عيبُ هذا الفحص.
    robotic = "\n\n" + " ".join(
        f"وهذا يعني أنّ البند {i} قائم. من الجدير بالذكر أنّ الرسم {i} مرتفع. "
        f"وفي هذا السياق يضيق الهامش {i}. تجدر الإشارة إلى المنافس {i}."
        for i in range(1, 9)) + "\n"

    def _gate(inject_before_appendix: bool) -> list:
        blob = getattr(importlib.import_module(mod), fn)()
        body = blob["deep_research"]["report"]["report"]
        cut = body.index("## 11")
        blob["deep_research"]["report"]["report"] = (
            body[:cut] + robotic + body[cut:] if inject_before_appendix
            else body + robotic)
        out = G.run_quality_gate(silk_render.build_view(blob))
        return ([f for f in out["findings"]
                 if f["check"] == "robotic_stock_phrase"], out["findings"])

    with _env(SILK_HUMAN_VOICE="1"), block_network():
        fired, verdict_findings = _gate(True)
        assert len(fired) == 1, fired
        assert "«أي أنّ»" in fired[0]["note"]
        # تحذيريٌّ لا حاجب: الفحصُ `repairable` فلا يدخل قائمةَ الحجب.
        assert fired[0]["repairable"] is True
        assert "robotic_stock_phrase" not in _blocking(verdict_findings)
        after_appendix, _ = _gate(False)
        assert after_appendix == [], "الملحقُ يُقصّ — صيغةٌ في المراجع لا تُعَدّ"
