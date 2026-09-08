"""لغة التاجر في تقرير العميل (قرار المالك 2026-08-19).

البلاغ: «التقرير بلغة غير مفهومة». الشاهد الحرفي من تقريره:
«سوق مورّدين مجزَّأ (HHI (مؤشر يقيس تركّز السوق بين المورّدين: فوق 2500
تركّز مرتفع)≈2350، لا مورّد مهيمناً)» — الشرح المقحوم أطول من الجملة.

القاعدة: على **سطح العميل** يُستبدَل المصطلح بمعناه ولا يُشرح بين قوسين؛
نسخة المدقّق تحتفظ بالمصطلحات. عام لكل تقرير وكل منتج — هرمتي بالكامل.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# الجملة الحقيقية من تقرير المالك — لا نموذج مثالي.
_REAL = ("سوق مورّدين مجزَّأ (HHI (مؤشر يقيس تركّز السوق بين المورّدين: "
         "فوق 2500 تركّز مرتفع)≈2350، لا مورّد مهيمناً)")


def test_the_owners_actual_sentence_becomes_readable():
    import silk_reports as R
    out = R._client_sanitize(_REAL)
    assert "HHI" not in out
    assert "مؤشر يقيس تركّز السوق بين المورّدين" not in out   # الشرح المقحوم زال
    assert "مؤشر تركّز السوق" in out                          # المعنى حلّ محلّه
    assert "2350" in out                                      # الرقم لم يُمَسّ


def test_every_jargon_term_is_replaced_by_its_meaning():
    import silk_reports as R
    from silk_style_contract import PLAIN_TERMS
    for term, plain in PLAIN_TERMS.items():
        out = R._client_sanitize(f"القيمة {term} = 12.")
        assert term not in out, f"{term} بقي عارياً في نص العميل"
        assert plain in out
        assert "12" in out          # لا رقم يُمَسّ


def test_real_system_names_stay_untouched_and_unglossed():
    """أسماء الأنظمة تبقى بالاسم **بلا وصفٍ مقحوم**: التطهير يجري لكل فقرة
    على حدة فلا سبيل لمعرفة «أوّل ذكر»، وكان الوصف يتكرّر في كل فقرة فيعيد
    الكسر نفسه الذي وُجد التبسيط ليزيله (مراجعة ذاتية §58). شرحها في المسرد."""
    import silk_reports as R
    out = R._client_sanitize("يتطلب إخطار TRACES قبل الشحن.")
    assert "TRACES" in out, "اسم نظام حقيقي يحتاجه التاجر حُذف"
    assert "(" not in out, "وصفٌ مقحوم عاد إلى المتن"
    twice = R._client_sanitize("إخطار TRACES ثم فقرة أخرى TRACES.")
    assert twice.count("نظام الإخطار") == 0


def test_company_names_urls_and_identifiers_are_never_corrupted():
    """أخطر ما التقطته المراجعة الذاتية: «SAM Food Trading BV» كان يصير
    «الجزء الذي يمكن خدمته فعلاً Food Trading BV»، والروابط تنكسر."""
    import silk_reports as R
    for intact in ("SAM Food Trading BV", "https://www.TAM-foods.nl",
                   "CHED Logistics BV", "المؤشر LP.LPI.OVRL.XQ للشحن"):
        assert R._client_sanitize(intact) == intact, f"تشوّه: {intact}"


def test_layer_has_a_kill_switch_defaulting_on(monkeypatch):
    import silk_reports as R
    assert R.plain_language_enabled() is True
    monkeypatch.setenv("SILK_PLAIN_LANGUAGE_ENABLED", "0")
    assert R.plain_language_enabled() is False
    assert R._plain_language("قيمة HHI = 2100") == "قيمة HHI = 2100"


def test_numbers_sources_and_dates_are_never_touched():
    import silk_reports as R
    src = "واردات 61,000,000$ عام 2023 (UN Comtrade) بنمو 9%."
    out = R._client_sanitize(src)
    for keep in ("61,000,000", "2023", "UN Comtrade", "9%"):
        assert keep in out, f"{keep} تغيّر — التبسيط يمسّ الأسلوب لا المحتوى"


def test_empty_parens_left_behind_are_cleaned():
    import silk_reports as R
    from silk_style_contract import GLOSSARY
    out = R._client_sanitize(f"النمو ({GLOSSARY['CAGR']}) مستقر.")
    assert "()" not in out and "( )" not in out


def test_writer_contract_carries_the_plain_language_rule():
    from silk_style_contract import (ACADEMIC_WRITER_CONTRACT,
                                     WRITER_STYLE_CONTRACT)
    for contract in (WRITER_STYLE_CONTRACT, ACADEMIC_WRITER_CONTRACT):
        assert "تكتب لتاجر لا لأكاديمي" in contract
        assert "ممنوع الشرح بين قوسين وسط الجملة" in contract
        # امتداد لا استبدال: العقد القديم باقٍ
        assert "عقد" in contract


def test_gate_flags_jargon_and_nested_gloss_as_warnings_only():
    import silk_quality_gate as Q
    from silk_style_contract import GLOSSARY
    # (أ) ما تُصلحه الطبقة حتمياً لا يُنبَّه عليه — وإلا ضجيجٌ دائم.
    auto_fixed = {"report": {"text": f"سوق مجزَّأ HHI≈2350 ({GLOSSARY['HHI']})."}}
    assert Q._check_plain_language({}, auto_fixed) == []
    # (ب) **لا إنذار كاذب** على اسم شركةٍ أو اسم مصدر — الفحص يستعمل نفس
    # قواعد سياق المُبسِّط لا مجرّد وجود الحروف (مراجعة ذاتية §58).
    for benign in ("تعاقد مع SAM Food Trading BV في روتردام.",
                   "وفق World Bank LPI فإن الأداء مرتفع."):
        assert Q._check_plain_language({}, {"report": {"text": benign}}) == [], benign
    # (ج) لا فحصَ ميّتاً: «الشرح المقحوم» أُسقِط لأنّ التبسيط يزيله دائماً.
    assert "plain_language_nested_gloss" not in open(
        os.path.join(_ROOT, "silk_quality_gate.py"), encoding="utf-8").read()
    assert "plain_language_jargon" not in Q.FAIL_TRIGGER_CHECKS
    clean = {"report": {"text": "السوق موزّع على موردين كثيرين ومؤشر تركّزه 2350."}}
    assert Q._check_plain_language({}, clean) == []


def test_an_acronym_inside_a_source_name_is_kept_verbatim():
    """اسمُ المصدر لا يُترجَم: «World Bank LPI» إسنادٌ لا مصطلح، وترجمتُه
    تنتج «World Bank تقييم جودة الشحن» فتُفسِد الإسناد. الحرفُ اللاتينيّ
    المجاور هو الفارق — نفسُ الحارس الذي يحمي أسماء الشركات."""
    import silk_reports as R
    kept = R._client_sanitize("الأداء اللوجستي الهولندي من الأعلى (World Bank LPI).")
    assert "World Bank LPI" in kept, "اسم المصدر تُرجم — الإسناد فسد"
    # ونفسُ المصطلح داخل نثرٍ عربيّ يُترجَم
    prose = R._client_sanitize("بلغ LPI الهولندي 4.1 نقطة.")
    assert "LPI" not in prose and "تقييم جودة الشحن" in prose


def test_a_rendered_client_docx_has_no_bare_jargon(tmp_path):
    """الأثر المُصيَّر فعلاً (ملف .docx مفتوح) لا مجرّد دالّة — الدرس ٦٩."""
    import silk_render as RR
    import silk_reports as REP
    from docx import Document
    from tools.canonical_netherlands import netherlands_research_blob
    path = str(tmp_path / "client.docx")
    REP.render_client_docx(RR.build_view(netherlands_research_blob()), path)
    text = "\n".join(p.text for p in Document(path).paragraphs)
    for term in ("HHI", "CAGR", "TAM", "SAM", "SOM"):
        assert term not in text, f"{term} وصل مستند العميل عارياً"


def test_no_doubled_meaning_when_writer_already_named_it_in_arabic():
    """كشفَته الطبعة الحقيقية لا اختبار وحدة: «مؤشر تركّز المورّدين HHI»
    كان يصير «مؤشر تركّز المورّدين مؤشر تركّز السوق»."""
    import silk_reports as R
    out = R._client_sanitize("ويبلغ مؤشر تركّز المورّدين HHI نحو 2100.")
    assert out.count("مؤشر تركّز") == 1
    assert "HHI" not in out and "2100" in out
    # وحين لا يسمّيه الكاتب، يظهر المعنى كاملاً
    solo = R._client_sanitize("صفّ المورّدين معتدل (HHI≈2100).")
    assert "مؤشر تركّز السوق" in solo


def test_client_glossary_is_not_circular():
    import silk_reports as R
    entry = {"term": "HHI",
             "gloss": "مؤشر يقيس تركّز السوق بين المورّدين: فوق 2500 تركّز مرتفع"}
    client = R._client_sanitize(R._glossary_line(entry, plain=True))
    assert client.startswith("مؤشر تركّز السوق:")
    assert "مؤشر يقيس تركّز السوق" not in client, "تعريف دائري"
    # نسخة المدقّق تبقى بالمصطلح وتعريفه الكامل
    auditor = R._glossary_line(entry, plain=False)
    assert auditor.startswith("HHI:") and "مؤشر يقيس" in auditor


def test_system_names_get_their_short_description_in_the_client_glossary():
    """KEEP_WITH_SHORT_DESC كان ثابتاً ميّتاً بعد إخراج الوصف من المتن —
    مستهلكه الحيّ الآن مسردُ العميل (مراجعة ذاتية §58)."""
    import silk_reports as R
    entry = {"term": "TRACES",
             "gloss": "نظام الإخطار الجمركي الأوروبي الإلكتروني للشحنات"}
    assert R._glossary_line(entry, plain=True) == (
        "TRACES: نظام الإخطار الجمركي الأوروبي")
    assert "الإلكتروني للشحنات" in R._glossary_line(entry, plain=False)


def test_no_stray_space_left_after_dropping_an_acronym():
    import silk_reports as R
    assert R._client_sanitize("مؤشر تركّز السوق (HHI) ≈2350 مرتفع.") == (
        "مؤشر تركّز السوق≈2350 مرتفع.")


def test_writer_contracts_have_no_orphaned_fragments():
    """المراجعة الذاتية (٢): الحذفُ الجراحيّ للقاعدة المُبطَلة خلّف شظايا
    («وأمثالها)؛ لا اختصار إنجليزي…»، «قوسين بعد العربية لا وحدها.») تناقض
    القاعدة الجديدة داخل البرومبت نفسه وتترك قوساً غير مغلق."""
    from silk_style_contract import (ACADEMIC_WRITER_CONTRACT,
                                     WRITER_STYLE_CONTRACT)
    for contract in (WRITER_STYLE_CONTRACT, ACADEMIC_WRITER_CONTRACT):
        for orphan in ("وأمثالها)", "قوسين بعد العربية لا وحدها",
                       "اشرحه فوراً", "لا اختصار إنجليزي مستقلّ بلا شرح عربي"):
            assert orphan not in contract, f"شظية باقية: {orphan}"
        assert contract.count("(") == contract.count(")"), "قوس غير مغلق"
        assert "في المسرد لا في المتن. **العملة" in contract   # الوصل سليم


def test_a_source_url_does_not_disable_simplification_for_the_whole_report():
    """المراجعة الذاتية (٣): رابطُ مصدرٍ واحد كان يُلغي التبسيط من أوّل
    التقرير لآخره، فيُطلِق حارسُ البوابة تحذيراً على كلّ تقرير."""
    import silk_quality_gate as Q
    import silk_reports as R
    from silk_style_contract import GLOSSARY
    body = ("سوق مجزَّأ HHI≈2350 (" + GLOSSARY["HHI"] + ").\n"
            "المصدر: https://comtradeplus.un.org/data")
    out = R._client_sanitize(body)
    assert "HHI" not in out.splitlines()[0]
    assert "https://comtradeplus.un.org/data" in out    # الرابط سليم
    assert Q._check_plain_language({}, {"report": {"text": body}}) == []
