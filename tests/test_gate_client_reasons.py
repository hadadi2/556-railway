"""لا معرّفَ كودٍ في نصٍّ يقرؤه مصنع — قفلُ تغطيةٍ لا إصلاحُ حادثة.

الحادثة (بلاغ المالك الثالث، 2026-08-29): شاشةُ المصنع عرضت حرفياً

    «قائد الحجب: unit_conversion_refusal — الفحوص الحاجبة:
     unit_conversion_refusal، trends_hollow_completion»

معرّفا كودٍ على سطحٍ يقرؤه مصنعٌ دافع. وكلُّ فحصٍ من الاثنين يحمل **ملاحظةً
عربيةً جاهزة** في `silk_quality_gate` — تُحسَب ثمّ تُرمى، فيُطبَع المعرّف.

وهي ثالثُ ظهورٍ لعادةٍ واحدة في ثلاث طبقات (الدرسان ٢٠٦/٢٠٧): طبقةٌ تحسب
سبباً مقروءاً، وسطحٌ يطبع رمزاً بدله. ولذلك هذا الملفّ **قفلُ تغطية** لا
اختبارَ حالة: فحصٌ حاجبٌ جديد بلا جملةِ زائرٍ يُحمِّر السويت — تنتهي العائلة
لا الحادثة.

قرارُ `factory_detail` القديم («أسماء الفحوص فقط بلا نصوصها الداخلية») نيّتُه
صحيحة — ألّا تتسرّب لغةُ بوّابةٍ داخلية — لكنّه انتهى إلى أسوأ الاحتمالين:
لا شرحَ ولا لغةَ إنسان. الجملُ هنا مكتوبةٌ **للزائر** لا مقتبسةٌ من البوّابة.
"""
import os
import re

import silk_export_gate as G
import silk_quality_gate as Q

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _reachable_check_ids() -> set:
    """كلُّ معرّفٍ يمكن أن يصل سطحَ المصنع فعلاً — لا قائدو الفشل وحدهم.

    ملاحظةُ مراجعةٍ ذاتية §58: القفلُ الأوّل قاس `FAIL_TRIGGER_CHECKS` (٢٥)
    بينما `blocked_checks` تُبنى من **كلّ** ملاحظةٍ غير قابلة للإصلاح
    (`repairable: False`) — ٦٧ معرّفاً مجتمعةً. قفلٌ يقيس المجموعةَ الخطأ
    يمرّ بينما المعرّفُ يتسرّب.
    """
    src = _read("silk_quality_gate.py")
    ids = set(re.findall(
        r'"check":\s*"([a-z0-9_]+)"\s*,\s*"repairable":\s*False', src))
    ids |= set(re.findall(
        r'"repairable":\s*False\s*,\s*"check":\s*"([a-z0-9_]+)"', src))
    ids |= set(Q.FAIL_TRIGGER_CHECKS)
    ids |= set(getattr(Q, "_REGRESSION_GUARD_FIRED", ()) or ())
    return ids


# ═══════════ ١ — التغطية: لا فحصَ حاجبٍ بلا جملة ═════════════════════════════
def test_no_reachable_check_can_ever_render_as_a_raw_id():
    """القفلُ الذي ينهي العائلة: كلُّ معرّفٍ يبلغ المصنع يُعاد جملةً.

    العامّةُ مقبولةٌ هنا — المرفوضُ هو الفراغ (فيطبع السطحُ المعرّف).
    """
    ids = _reachable_check_ids()
    assert len(ids) > 50, ids          # حارسٌ على الاستخراج نفسه
    missing = [c for c in sorted(ids)
               if not (G.client_reason(c, "ar") and G.client_reason(c, "en"))]
    assert not missing, missing


def test_every_fail_driver_has_a_specific_sentence_not_the_generic_one():
    """قائدو الفشل الـ٢٥ لهم جملٌ **مخصَّصة** — العامّة لا تكفيهم.

    فحصٌ حاجبٌ جديد يُضاف إلى `FAIL_TRIGGER_CHECKS` بلا جملةٍ مخصَّصة يسقط
    هنا، فتبقى العائلةُ مُغلَقة لا الحادثةُ وحدها.
    """
    generic = G._GENERIC_REASON["ar"]
    thin = [c for c in sorted(Q.FAIL_TRIGGER_CHECKS)
            if G.client_reason(c) == generic]
    assert not thin, (
        "قائدُ فشلٍ بلا جملةٍ مخصَّصة — أضِفها في "
        f"silk_export_gate._CLIENT_REASONS: {thin}")


def test_no_visitor_sentence_leaks_a_check_id_or_a_code_token():
    """الجملةُ لغةُ إنسان: لا معرّفَ فحصٍ ولا رمزَ كودٍ بشرطةٍ سفلية."""
    ids = set(Q.FAIL_TRIGGER_CHECKS) | set(G._CLIENT_REASONS)
    bad = []
    for check, row in G._CLIENT_REASONS.items():
        for lang, txt in row.items():
            if any(i in txt for i in ids) or re.search(r"[a-z]+_[a-z_]+", txt):
                bad.append(f"{check}/{lang}")
    assert not bad, f"جملُ زائرٍ تحمل معرّفاتِ كود: {bad}"


def test_every_sentence_says_what_closes_it():
    """طلبُ فعلٍ من المصنع يسمّي موضوعه — لا «حُجِب» عارية."""
    rows = list(G._CLIENT_REASONS.items()) + [("(العامّة)", G._GENERIC_REASON)]
    thin = [c for c, r in rows
            if "يُغلقه" not in r["ar"] or "Fix:" not in r["en"]]
    assert not thin, f"جملٌ بلا سبيلِ إغلاق: {thin}"


def test_an_unknown_check_falls_back_to_the_generic_never_the_raw_id():
    """معرّفٌ لا نعرفه يُوصَف عامّاً — ولا يُطبَع خاماً أبداً."""
    out = G.client_reason("no_such_check_id")
    assert out == G._GENERIC_REASON["ar"]
    assert "no_such_check_id" not in out
    assert G.client_reason(None) == "" and G.client_reason("") == ""


def test_client_reasons_dedupes_and_keeps_order():
    """قائمةُ الجمل بلا تكرارٍ وبترتيب الورود."""
    out = G.client_reasons(["unit_conversion_refusal",
                            "unit_conversion_refusal",
                            "trends_hollow_completion"])
    assert len(out) == 2
    assert out[0] == G.client_reason("unit_conversion_refusal")


# ═══════════ ٢ — الحمولتان تحملان الجمل، والمعرّفاتُ تبقى للآلة ══════════════
def test_factory_detail_carries_the_sentences_beside_the_ids():
    digest = [{"check": "unit_conversion_refusal"},
              {"check": "trends_hollow_completion"}]
    out = G.factory_detail(digest, "ar",
                           fail_drivers=["unit_conversion_refusal"])
    assert out["blocked_checks"] == ["unit_conversion_refusal",
                                     "trends_hollow_completion"]  # عقدٌ قائم
    assert len(out["blocked_reasons"]) == 2
    assert "لتر↔كجم" in out["blocked_reasons"][0]
    assert out["fail_driver_reasons"] == [
        G.client_reason("unit_conversion_refusal")]


def test_client_quality_summary_carries_them_on_the_read_surface():
    d = G.client_quality_summary(
        {"verdict": "FAIL",
         "blocking": [{"check": "unit_conversion_refusal"}],
         "fail_drivers": ["unit_conversion_refusal"]})
    assert d["blocked_reasons"] and d["fail_driver_reasons"]
    assert "الموسمية" not in d["blocked_reasons"][0]      # الجملةُ الصحيحة
    en = G.client_quality_summary(
        {"verdict": "FAIL", "blocking": [{"check": "unit_conversion_refusal"}],
         "fail_drivers": []}, "en")
    assert "litre" in en["blocked_reasons"][0]


def test_a_passing_report_carries_no_blocking_payload():
    d = G.client_quality_summary({"verdict": "PASS", "blocking": []})
    assert "blocked_reasons" not in d and "blocked_checks" not in d


# ═══════════ ٣ — السطحُ يعرض الجملة، والمعرّفُ احتياطٌ لا أصل ════════════════
def test_the_factory_screen_never_renders_a_check_id():
    """`web/platform.html`: الجملُ وحدها — لا مسارَ يطبع معرّفاً.

    ملاحظةُ مراجعةٍ ذاتية: الارتدادُ «الجملُ وإلا المعرّفات» كان يُسقِط
    فحصاً بلا جملةٍ صامتاً حين يملك شقيقُه جملة — أُلغي الارتدادُ كلّه بعد
    أن صار الفراغُ مستحيلاً (`client_reason` لا تعيد فراغاً لمعرّفٍ حقيقي).
    """
    page = _read("web/platform.html")
    assert page.count("blocked_reasons") >= 2
    assert page.count("fail_driver_reasons") >= 2, (
        "سببُ الحجب القائد لا يصل الشاشة")
    # المعرّفاتُ مسموحةٌ **مرجعاً للدعم** لا رسالةً: كلُّ موضعٍ يطبعها
    # مسبوقٌ بوسم «للدعم» (شرط المُشرِف F محفوظ — الحجب يسمّي فحوصه).
    for m in re.finditer(r"(fail_drivers|blocked_checks)\.join", page):
        window = page[max(0, m.start() - 400):m.start()]
        assert "للدعم" in window, (
            "معرّفٌ يُطبَع للمصنع خارج سياق الدعم عند الموضع " + str(m.start()))
    # ولا يتصدّر المعرّفُ الرسالةَ بوسم «قائد الحجب» كما كان.
    assert "\"قائد الحجب: \"" not in page


def test_the_operator_surface_keeps_the_ids():
    """`web/index.html` جمهورُه تقنيّ — المعرّفاتُ تبقى له عمداً."""
    assert "fail_drivers" in _read("web/index.html")
