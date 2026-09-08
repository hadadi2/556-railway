"""الموجة C · C4 — حدودُ تحجيم السوق: الحسابُ في الشيفرة، والعرضُ في النموذج.

> **الفجوة Z-01** (`docs/ENGINE_AUDIT.md` §٤-د): الحاسبُ الحتميّ موجودٌ في
> `silk_research.py` **ويُعلن فجوتَه** عند نقص المدخلات — لكنّ موجِّهَ الكاتب
> كان يحمل أمراً صريحاً: «**احسب TAM/SAM/SOM في جدول Markdown**» مع سلسلة
> الضرب كاملةً. أي أنّ أخطر رقمٍ تجاريٍّ في التقرير — حجمُ الفرصة الذي يبني
> عليه المصنعُ قرارَ دخولٍ بمئات الآلاف — كان يُحسَب في **موجِّهٍ نصّيّ**.
>
> وهذا بعينه ما يحظره §9: الحسابُ الحاسم في الشيفرة، والنموذجُ يشرح ولا يحسب.

**التبعيةُ الملزِمة المقفولة هنا:** Z-01 **قبل** E-04. تمريرُ بطاقة المنتج
(E-04) بلا نقل التحجيم إلى الشيفرة كان **سيُفعِّل** الخرق: البطاقةُ تصل
النموذجَ ضمن الحقائق، والموجِّهُ يأمره بالضرب، فيشحن SAM/SOM من تأليفه.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name: str) -> str:
    with open(os.path.join(_ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def _uncommented(src: str) -> str:
    """جرِّد أسطرَ التعليق — التعليقاتُ تقتبس النصَّ المحظور شرحاً للحادثة.

    (نفسُ مزلق الدرس ٨٨: حارسٌ يفحص المصدر خاماً يُحمِّر على تعليقٍ يشرح ما
    أُزيل.)
    """
    return "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))


# ── Z-01 · الموجِّه لا يطلب حساباً ────────────────────────────────────────

def test_the_writer_prompt_never_orders_the_model_to_compute_sizing():
    """حارسٌ بنيويّ: لا أمرَ حسابٍ لأرقام التحجيم في أيّ موجِّه."""
    body = _uncommented(_src("silk_ai_judge.py"))
    banned = re.findall(r"احسب\s+TAM|احسب\s+SAM|احسب\s+SOM|compute\s+TAM",
                        body, re.I)
    assert not banned, (
        f"عاد الموجِّهُ يأمر النموذجَ بحساب التحجيم: {banned} (Z-01)")


def test_the_writer_prompt_orders_presentation_and_declares_the_gap():
    """وأمرُ العرض صريحٌ، ومعه أمرُ الإعلان عند غياب الرقم."""
    body = _uncommented(_src("silk_ai_judge.py"))
    assert "لا تحسبها ولا تشتقّها" in body, (
        "أمرُ «اعرض ولا تحسب» غائبٌ — الفراغُ وحده لا يمنع النموذج (Z-01)")
    assert "ولا تملأ الفراغ بتقدير" in body, (
        "غيابُ الرقم بلا أمرِ إعلانٍ يدعو النموذجَ إلى ملئه (Z-01)")


def test_the_multiplication_chain_is_no_longer_spelled_out_for_the_model():
    """سلسلةُ الضرب نفسها خرجت من الموجِّه — لا وصفةَ حسابٍ تُغري بتطبيقها."""
    body = _uncommented(_src("silk_ai_judge.py"))
    assert "SAM = TAM ×" not in body, (
        "وصفةُ الضرب ما تزال في الموجِّه (Z-01)")


# ── الحاسبُ الحتميّ يبقى هو المصدر ───────────────────────────────────────

def test_the_deterministic_calculator_still_exists_and_declares_its_gaps():
    """`silk_research` يحسب ويُعلن — لا يُستبدَل بنثرٍ ولا يُحذَف."""
    research = _src("silk_research.py")
    assert "TAM = إجمالي واردات السوق المرصودة" in research, (
        "الحاسبُ الحتميّ للـTAM اختفى (Z-01)")
    assert "sam_usd: يتطلب حجم سوق مرصوداً" in research, (   # قفل محدَّث معلن (الدرس 170)
        "إعلانُ فجوة SAM اختفى — الفجوةُ المعلنة هي البديلُ الشريف للتقدير")
    assert "SAM = TAM ×" in research, (
        "معادلةُ SAM لم تعد مطبوعةً مع نتيجتها")


def test_sizing_gaps_are_declared_not_zeroed():
    """نقصُ المدخل ⇒ فجوةٌ مسمّاة، لا صفرٌ ولا رقمٌ مُقدَّر (عقد التأسيس)."""
    research = _src("silk_research.py")
    idx = research.index("sam_usd: يتطلب حجم سوق مرصوداً")
    window = research[max(0, idx - 600):idx]
    assert "gaps.append" in window, (
        "فجوةُ SAM لم تعد تُسجَّل في قناة الفجوات")


# ── C9 · ما يُقال للمصنع حين لا يُحسَب الرقم ─────────────────────────────

def test_the_not_calculable_message_reads_as_business_language():
    """«غير قابل للحساب» تصل المصنعَ جملةً مفهومة لا رمزَ حالة."""
    import silk_i18n
    import silk_reports
    for lang in ("ar", "en"):
        for key in ("not_calculable", "not_calculable_why",
                    "not_calculable_action", "insufficient_evidence"):
            text = silk_i18n.t(key, lang, missing="تكلفة الوحدة")
            assert text.strip(), f"{key} فارغٌ في {lang}"
            hits = silk_reports._client_forbidden_hits(text, lang)
            assert hits == [], f"«{key}» بلغةِ نظام في {lang}: {hits[:2]}"
            assert "NOT_CALCULABLE" not in text, (
                f"رمزُ الحالة الخام تسرّب إلى نصّ العميل في {key}")


def test_the_not_calculable_message_names_the_missing_input():
    """لا يكفي أن نقول «تعذّر» — يُسمّى المدخلُ الناقص ويُطلَب الفعل."""
    import silk_i18n
    why = silk_i18n.t("not_calculable_why", "ar", missing="تكلفة الوحدة")
    assert "تكلفة الوحدة" in why, "الرسالةُ لا تسمّي ما ينقص"
    action = silk_i18n.t("not_calculable_action", "ar")
    assert action.strip(), "لا فعلَ مطلوبٌ مقترَح — المصنعُ يبقى بلا مخرج"


# ── Z-03 وZ-05 · التحجيمُ يُفحَص اشتقاقاً لا مقداراً فقط ─────────────────
#
# الفحصُ الوحيد المتعلّق بـTAM كان `_check_tam_below_single_country_flow` —
# فحصُ **مقدار** لا فحصُ **اشتقاق**. فرقمٌ سليمُ المقدار ومُختلَقُ الاشتقاق
# يمرّ بلا كلمة، وهو الحالةُ الأخطر: يبدو معقولاً فلا يستوقف أحداً.
#
# وحارسُ التأريض (`silk_evals.formula_grounded_numbers`) — الوحيدُ القادر على
# كشف رقمٍ مشتقٍّ بلا تأريض — كان يعيش في حزمة **التقييم** لا في مسار التشغيل.

_TABLE = """| المستوى | القيمة | طريقة الحساب |
| TAM | 61,000,000 | إجمالي واردات السوق المرصودة |
| SAM | 9,150,000 | TAM × 15% (افتراض الشريحة) |
| SOM | 12,000,000 |  |"""


def _gate(text: str, missions=None) -> list:
    import silk_quality_gate
    return silk_quality_gate._check_market_sizing_derivation(
        {"report": {"text": text}, "missions": missions or {}})


def test_a_sizing_row_without_its_method_is_reported():
    checks = {h["check"] for h in _gate(_TABLE)}
    assert "sizing_row_without_method" in checks, (
        "رقمُ تحجيمٍ بلا معادلته يمرّ — لا يستطيع المصنعُ التحقّق منه (Z-03)")


def test_an_inverted_sizing_order_is_reported():
    """الجزءُ لا يكون أكبر من الكلّ — خطأٌ اشتقاقيّ لا أسلوبيّ."""
    hits = [h for h in _gate(_TABLE) if h["check"] == "sizing_order_inverted"]
    assert hits, "SOM > SAM مرّ بلا ملاحظة (Z-03)"
    assert "الجزءُ لا يكون أكبر من الكلّ" in hits[0]["note"]


def test_the_grounding_guard_now_runs_in_the_delivery_path():
    """حارسُ `silk_evals` يُستدعى من البوّابة — لا نسخةٌ ثانيةٌ منه (Z-05)."""
    import io as _io
    src = _io.open(os.path.join(_ROOT, "silk_quality_gate.py"),
                   encoding="utf-8").read()
    assert "from silk_evals import formula_grounded_numbers" in src, (
        "حارسُ التأريض ما يزال خارج مسار التشغيل (Z-05)")


def test_the_sizing_checks_are_advisory_not_blocking():
    """الكاتبُ قد يعرض التحجيم نثراً مشروعاً — حجبُ تقريرٍ صحيحٍ ضررٌ لا نفع."""
    import silk_quality_gate
    for check in ("sizing_row_without_method", "sizing_order_inverted",
                  "sizing_not_grounded"):
        assert check not in silk_quality_gate.FAIL_TRIGGER_CHECKS
    assert all(h["repairable"] for h in _gate(_TABLE))


def test_a_report_without_a_sizing_table_is_left_alone():
    """لا جدولَ ⇒ لا لوم: العرضُ النثريّ المشروع لا يُعاقَب."""
    assert _gate("نصٌّ سرديٌّ بلا جدول تحجيم إطلاقاً.") == []


def test_a_clean_sizing_table_raises_no_structural_complaint():
    clean = """| المستوى | القيمة | طريقة الحساب |
| TAM | 61,000,000 | إجمالي واردات السوق المرصودة |
| SAM | 9,150,000 | TAM × 15% (افتراض الشريحة) |
| SOM | 1,830,000 | SAM × 20% (افتراض الحصة المستهدفة) |"""
    checks = {h["check"] for h in _gate(clean)}
    assert "sizing_row_without_method" not in checks
    assert "sizing_order_inverted" not in checks


def test_z04_the_honest_renderer_belongs_to_the_analyze_surface():
    """**Z-04 محسومٌ بغير ما اقترحه الجرد — والسببُ مُسجَّل هنا.**

    `_docx_market_size` يقرأ حزمةَ بحث `/analyze` (`m["research"]["agents"]`)
    ويُستدعى من `render_docx` وحدَه. وجعلُه «قابلاً للوصول من مسار الدراسة»
    يتطلّب تركيبَ حزمةٍ بشكل `/analyze` من بعثاتٍ عميقة — أي **مسارَ عرضٍ
    ثانياً** تحظره قاعدةُ «عرضٌ واحد».

    فضمانتاه — سطرُ مصدرٍ لكلّ رقم، ووسمُ «مُقدَّر» بمعادلته — تُسلَّمان على
    المسار العميق عبر القناة القانونية نفسها: الكاتبُ يعرض أرقامَ الحاسب
    الحتميّ (Z-01) بمعادلتها وافتراضها، والبوّابةُ تتحقّق من ذلك (Z-03).
    """
    import io as _io
    rep = _io.open(os.path.join(_ROOT, "silk_reports.py"), encoding="utf-8").read()
    assert rep.count("_docx_market_size(doc, top_m)") == 1, (
        "تعدّدت مواضعُ نداء مُصيّر التحجيم — مسارُ عرضٍ ثانٍ")
    assert '"research"' in rep, "شكلُ حزمة /analyze تغيّر — راجِع تعليل Z-04"
