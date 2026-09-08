"""الموجة C · Z-02 وE-10 — نثرُ الكاتب يُردّ إلى أدلته، والمدوّنةُ تُمرِّن النظام.

> **Z-02:** عقدُ الاستشهاد (`dpN`) يحرس **البعثات** وحدَها؛ ونثرُ الكاتب لا
> يمرّ به إطلاقاً. فرقمٌ لم يرد في أيّ دليل يمكن أن يظهر في التقرير بثقةٍ
> تامّة ولا شيء يقف في وجهه.
>
> **E-10:** مدوّنةُ رُتبة ٢ استعملت مفتاح البعثة `competition` بينما مفتاحُ
> الإنتاج `competitors`. فلم يُمرَّن مسارُ الاقتصاد (HHI ⇒ بوّابة الإزاحة) في
> أيّ تشغيلةِ قبولٍ إطلاقاً — تُختبَر المدوّنةُ نفسَها لا النظام. وهذه أخطرُ
> صور الاختبار الكاذب: أخضرُ يقيس شيئاً آخر.

**نطاقُ Z-02 مقصودٌ ضيّق:** المبالغُ المالية وحدَها — الأرقامُ التي يُبنى عليها
قرارُ الدخول. توسيعُه إلى كلّ رقمٍ كان سيُنتِج ضجيجاً يُخفي الإشارة، وحارسٌ
يصرخ دائماً لا يُسمَع. والإصلاحُ الكامل (إخضاعُ نثر الكاتب لعقد `dpN` نفسه)
يتطلّب تغييرَ بروتوكول الكاتب — خارجَ نطاق هذه الموجة عمداً.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

import silk_economics as E                              # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import silk_quality_gate as Q                           # noqa: E402

_MISSIONS = {"trade_flow": {"findings": [
    {"value": 61000000, "note": "إجمالي واردات السوق"}]}}


def _dr(text: str, missions=None) -> dict:
    return {"missions": _MISSIONS if missions is None else missions,
            "report": {"text": text}}


# ── Z-02 · المبالغُ في النثر تُردّ إلى دليلها ────────────────────────────

def test_an_amount_matching_the_evidence_passes():
    assert Q._check_narrative_money_grounded(
        _dr("بلغت الواردات 61 مليون دولار.")) == []


def test_an_amount_that_appears_nowhere_in_the_evidence_is_reported():
    hits = Q._check_narrative_money_grounded(_dr("السوق يبلغ 900 مليون دولار."))
    assert [h["check"] for h in hits] == ["narrative_money_not_grounded"], (
        "رقمٌ لم يرد في أيّ دليل مرّ بلا كلمة (Z-02)")


def test_a_number_whose_equation_is_written_out_is_not_penalised():
    """حارسٌ يعاقب الشفافيةَ يُدرَّب الناسُ على تفاديه.

    رقمٌ ناتجُ معادلةٍ **ظاهرةٍ للقارئ** أفضلُ توثيقاً من رقمٍ منقول، فلا
    يُطالَب بمصدرٍ مستقلّ؛ ومدخلاتُه تُفحَص في مكانها.
    """
    assert Q._check_narrative_money_grounded(
        _dr("TAM 61000000 × 15% (افتراض) = 9150000 دولار.")) == []


def test_a_rounding_variant_of_the_evidence_passes():
    """«٦١٫٢ مليون» و«61,000,000» رقمٌ واحدٌ بصياغتين."""
    assert Q._check_narrative_money_grounded(
        _dr("نحو 61.2 مليون دولار.")) == []


def test_no_numeric_evidence_means_no_blame():
    """بلا أدلةٍ رقمية لا مرجعَ للمقارنة — الصمتُ هنا صواب."""
    assert Q._check_narrative_money_grounded(
        _dr("900 مليون دولار.", missions={})) == []


def test_the_check_is_advisory():
    """الرقمُ قد يُذكَر بوحدةٍ أخرى — حجبُ تقريرٍ صحيحٍ لأجل صياغةٍ ضررٌ لا نفع."""
    assert "narrative_money_not_grounded" not in Q.FAIL_TRIGGER_CHECKS
    hits = Q._check_narrative_money_grounded(_dr("السوق يبلغ 900 مليون دولار."))
    assert all(h["repairable"] for h in hits)


# ── E-10 · مدوّنةُ رُتبة ٢ تطابق شكلَ الإنتاج ────────────────────────────

def test_every_canonical_corpus_uses_the_production_mission_keys():
    """يكنس **كلَّ** المدوّنات لا واحدة — والفرقُ ليس شكلياً.

    المرورُ الأول أصلح `canonical_netherlands` وحدَها وقفلها وحدَها، فبقيت
    **ستُّ مدوّناتٍ أخرى** تحمل العطلَ نفسه: `competition` بدل `competitors`
    و`economic` بدل `demographics_economy`، وواحدةٌ تحمل `trade_history` —
    **بعثةً لا وجودَ لها في الإنتاج إطلاقاً**، لا اسماً خاطئاً لبعثةٍ قائمة.
    فقفلٌ يحرس مدوّنةً واحدة يُعطي طمأنينةَ تغطيةٍ لا يملكها.
    """
    import importlib
    import inspect
    import os
    from silk_missions import MISSIONS

    tools_dir = os.path.join(_ROOT, "tools")
    bad, checked = {}, 0
    for fn in sorted(os.listdir(tools_dir)):
        if not (fn.startswith("canonical_") and fn.endswith(".py")):
            continue
        mod = importlib.import_module(fn[:-3])
        for name, obj in vars(mod).items():
            if not callable(obj) or name.startswith("_"):
                continue
            try:
                if inspect.signature(obj).parameters:
                    continue
                blob = obj()
            except Exception:      # noqa: BLE001 — ليست مدوّنةَ تشغيلة
                continue
            if not isinstance(blob, dict):
                continue
            missions = (blob.get("deep_research") or {}).get("missions") or {}
            if not missions:
                continue
            checked += 1
            unknown = [k for k in missions if k not in MISSIONS]
            if unknown:
                bad[f"{fn}:{name}"] = unknown
    assert checked >= 5, f"لم تُفحَص مدوّناتٌ كافية ({checked}) — الكنسُ انكسر"
    assert not bad, (
        f"مفاتيحُ بعثاتٍ لا وجودَ لها في الإنتاج: {bad} — المدوّنةُ تختبر "
        "نفسَها لا النظام، وتشغيلةُ القبول تُعلَن خضراء وهي تقيس شيئاً آخر "
        "(E-10)")


def test_the_yemen_series_lives_inside_a_real_mission():
    """جوهرُ حالة اليمن كان تحت بعثةٍ مخترَعة فلم يقرأه أحد.

    انهيارُ التسجيل ٢٠٢٠–٢٠٢٢ ثمّ عودتُه هو **الحقيقةُ التحليلية** لتلك
    الحالة؛ وتحت مفتاحٍ لا وجودَ له لم يصله تحليلُ تقادُمٍ ولا فحصُ تناقضٍ
    ولا عمودُ سوق.
    """
    from canonical_nadec_yemen_dairy import nadec_yemen_research_blob
    missions = nadec_yemen_research_blob()["deep_research"]["missions"]
    assert "trade_history" not in missions
    notes = " ".join(str(f.get("note") or "")
                     for f in missions["trade_flow"]["findings"])
    for year in ("2018", "2019", "2023"):
        assert year in notes, f"سنةُ {year} ضاعت في الدمج"
    assert sum(1 for f in missions["trade_flow"]["findings"]
               if f.get("value") is None) == 3, (
        "سنواتُ «لا سجل» الثلاث ضاعت — وهي جوهرُ الحالة")


def test_the_corpus_now_exercises_the_economics_path():
    """قبل الإصلاح: `hhi=None` دائماً، فبوّابةُ الإزاحة غيرُ مُمرَّنةٍ إطلاقاً."""
    from canonical_netherlands import netherlands_research_blob
    dr = netherlands_research_blob()["deep_research"]
    out = E.economics_view(dr)
    assert out["hhi"] == 940.0, "مسارُ HHI ما يزال غيرَ مُمرَّن (E-10)"
    assert out["displacement_measured"] is True
    assert (out["anchor_price"] or {}).get("raw_value") == 7.49, (
        "مرساةُ السعر لا تتكوّن من المدوّنة الإنتاجية")
