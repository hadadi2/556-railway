"""LESSONS ٩٦ — المقعدُ الاختباريّ يلتزم **العقدَ البنيويّ** لِما يستبدله.

الحادثة: `SILK_PLATFORM_FAKE_ENGINE=deep` هو المقعدُ الذي تعمل عليه رُتبتا ٢
و٣ (خادمٌ حقيقيّ ومتصفّحٌ حقيقيّ) بلا نداء كلود. كان يبني نصَّ عيّنةٍ بعناوين
`#`/`##` حرّةٍ بلا ترقيم، بينما مُصدِّرُ تقرير العميل يمفصل على الرقم الترتيبي
(`## N. <عنوان>`). فتُفكَّك **صفرُ أقسام**، ويسقط كلُّ قسمٍ إلى سطر «السرد غير
متاح» — ورُتبتان «خضراوان» تُصدِّقان مصنوعاً نهائياً فارغَ المتن. ونصُّه كان
عربياً مُرمَّزاً صلباً، فالمسار الإنجليزيّ لم يُختبَر حيّاً قطّ.

هذه الأقفال **سلوكية**: تُفكِّك نصَّ المقعد فعلاً وتعدُّ ما نتج، وتتحقّق أن
عناوينه من **المنتِج نفسه** (`silk_ai_judge.report_sections`) لا من نسخةٍ ثانية.

Behavioural locks: a test seam that does not reproduce the structural contract
of what it replaces makes every rung above it vacuous.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_ai_judge import report_sections            # noqa: E402
from silk_platform import engine_bridge              # noqa: E402
import silk_i18n                                     # noqa: E402
import silk_render                                     # noqa: E402
import silk_reports                                    # noqa: E402


@pytest.mark.parametrize("lang", ["ar", "en"])
def test_fake_seam_parses_into_every_canonical_section(lang):
    """كلُّ قسمٍ قانونيّ يُفكَّك من نصّ المقعد — لا صفر، ولا نقصان."""
    text = engine_bridge._fake_report_text(lang)
    parsed = silk_reports._parse_writer_sections_numbered(text)
    titles = report_sections(lang)
    assert len(parsed) == len(titles), (
        f"المقعد بلغة «{lang}» فُكِّك إلى {len(parsed)} قسماً والمتوقّع "
        f"{len(titles)} — العناوينُ لم تعد بالبنية المرقّمة (LESSONS ٩٦)")
    assert [n for n, _, _ in parsed] == list(range(1, len(titles) + 1)), (
        "الأرقامُ الترتيبية غير متتابعة — التمفصلُ على الرقم ينكسر (LESSONS ٩٦)")
    assert [t for _, t, _ in parsed] == list(titles), (
        "عناوينُ المقعد ليست عناوينَ المنتِج — نسخةٌ ثانيةٌ تتباعد (LESSONS ٩٦)")
    for num, title, body in parsed:
        assert any(str(ln).strip() for ln in body), (
            f"قسم «{title}» بلا متن في المقعد (LESSONS ٩٦)")


@pytest.mark.parametrize("lang", ["ar", "en"])
def test_fake_seam_leaves_no_client_section_without_narrative(lang):
    """صفرُ سطورِ «السرد غير متاح» — الرُتبتان تصدّقان متناً حقيقياً.

    الفحصُ يمرّ على **العرض القانوني** (`build_view`) لا على النتيجة الخام،
    لأن مُصدِّرَ تقرير العميل يستهلك العرضَ وحده — وهذا بالضبط ما تراه رُتبتا
    ٢ و٣ عبر HTTP.
    """
    result = engine_bridge._fake_result_deep("زيت زيتون", "150910", lang)
    view = silk_render.build_view(result, lang)
    missing = silk_reports._client_missing_narrative_heads(
        view["deep_research"])
    assert missing == {}, (
        f"أقسامُ عميلٍ بلا سردٍ على المقعد بلغة «{lang}»: "
        f"{sorted(missing)} (LESSONS ٩٦)")


@pytest.mark.parametrize("lang", ["ar", "en"])
def test_fake_seam_follows_the_study_language(lang):
    """المقعدُ يتبع لغةَ الدراسة — وإلا بقي أحدُ الفرعين غيرَ مُختبَرٍ حيّاً.

    يُفحَص **ما يصل المصنوع** (متونُ الأقسام وعناوينها) لا سطرُ الوسم: الوسمُ
    ديباجةٌ قبل أوّل عنوانٍ مرقّم فيُسقِطها التفكيك، وفيه اسمُ متغيّر بيئةٍ
    (معرّفٌ تقنيّ) لا نثرٌ أجنبيّ.
    """
    parsed = silk_reports._parse_writer_sections_numbered(
        engine_bridge._fake_report_text(lang))
    body = "\n".join(t + "\n" + "\n".join(b) for _, t, b in parsed)
    spans = silk_i18n.foreign_prose_spans(body, lang)
    assert spans == [], f"نثرٌ بلغةٍ أخرى في مقعد «{lang}»: {spans[:2]}"
    other = engine_bridge._fake_report_text("en" if lang == "ar" else "ar")
    assert engine_bridge._fake_report_text(lang) != other, (
        "المقعدُ لا يتفرّع باللغة أصلاً (LESSONS ٩٦)")


@pytest.mark.parametrize("lang", ["ar", "en"])
def test_fake_seam_is_always_tagged_as_a_simulation(lang):
    """الوسمُ أوّلاً في اللغتين — عيّنةٌ لا تُقدَّم حيّةً (البند ١)."""
    result = engine_bridge._fake_result_deep("زيت زيتون", "150910", lang)
    text = (result["deep_research"]["report"]["report"] or "")
    # المرساةُ **معنى** الوسم لا اسمُ متغيّر البيئة. كانت تطابق
    # «SILK_PLATFORM_FAKE_ENGINE=deep» حرفياً، وقد أُخرِج ذلك المعرّفُ من نصّ
    # الوسم في الموجة B: معرّفٌ داخليّ في نصٍّ يواجه العميل سباكةٌ مسرَّبة،
    # وبوّابةُ اتساق اللغة ترصده نثراً إنجليزياً في تقريرٍ عربيّ — فكان
    # المقعدُ نفسُه يُرسِب الرُتبتين ٢ و٣. الشرطُ الجوهريّ لم يتغيّر: العيّنةُ
    # موسومةٌ في أوّل سطرٍ وفي ملاحظة النتيجة، فلا تُقدَّم حيّةً أبداً.
    marker = "ليست بحثاً حياً" if lang == "ar" else "not live research"
    assert marker in text.splitlines()[0], (
        "وسمُ المحاكاة ليس في أوّل سطر من نصّ المقعد")
    assert marker in (result.get("note") or ""), (
        "وسمُ المحاكاة غاب عن ملاحظة النتيجة")
    assert "SILK_PLATFORM_FAKE_ENGINE" not in text, (
        "اسمُ متغيّر بيئةٍ عاد إلى نصٍّ يواجه العميل — سباكةٌ مسرَّبة")


def test_fake_seam_headings_come_from_the_producer_not_a_second_copy():
    """حارسٌ مصدريّ: العناوينُ مشتقّةٌ من `report_sections` لا مكتوبةً ثانيةً."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_platform", "engine_bridge.py"),
        encoding="utf-8").read()
    assert "from silk_ai_judge import report_sections" in src, (
        "المقعدُ لم يعد يشتقّ عناوينه من المنتِج (LESSONS ٩٦)")
    assert "for i, title in enumerate(report_sections(lang), 1)" in src, (
        "بناءُ العناوين المرقّمة من المنتِج اختفى (LESSONS ٩٦)")


# ── LESSONS ٩٧ — تصادمُ أرقام الترحيلات ──────────────────────────────────

def test_platform_migration_versions_are_unique():
    """رقمُ الترحيل مفتاحٌ أساسيّ — تصادمُه يُسقِط ترحيلاً **صامتاً**.

    `db.apply_migrations` يشتقّ `version` من البادئة الرقمية ويحفظها في
    `platform_migrations(version TEXT PRIMARY KEY)`، ثمّ يتخطّى أيّ ملفٍّ
    نسختُه مسجَّلة. فملفّان بالرقم نفسه ⇒ **الأول يُطبَّق والثاني لا يُطبَّق
    أبداً** على أيّ قاعدةٍ جديدة أو قائمة — بلا خطأ ولا سجلّ. الحادثة:
    فرعان متوازيان أضاف كلٌّ منهما `012_*.sql`، والتصادمُ ظهر عند الدمج لا
    عند الكتابة؛ ولولا الالتقاط لَشُحن جدولُ إعدادات الباقات غيرَ موجودٍ في
    الإنتاج بينما الاختباراتُ خضراء (كلُّ فرعٍ وحدَه سليم).

    Migration version is a PRIMARY KEY: a duplicated numeric prefix silently
    drops one migration on every database, new or existing.
    """
    import collections
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(root, "migrations", "platform")
    nums = collections.defaultdict(list)
    for name in sorted(os.listdir(d)):
        m = re.match(r"(\d+).*\.sql$", name)
        if m:
            nums[m.group(1)].append(name)
    dupes = {k: v for k, v in nums.items() if len(v) > 1}
    assert not dupes, (
        f"أرقامُ ترحيلٍ متصادمة — واحدٌ منها لن يُطبَّق أبداً: {dupes} "
        "(LESSONS ٩٧)")
    assert nums, "لم يُقرَأ أيّ ترحيل — مسارٌ خاطئ لا نجاحٌ"
