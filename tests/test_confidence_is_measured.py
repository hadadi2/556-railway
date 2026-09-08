"""الموجة C · C7 — الثقةُ قياسٌ من الأدلة، لا تقريرُ النموذج عن نفسه.

> **الفجوة C-06 `CRITICAL`** (`docs/ENGINE_AUDIT.md` §٤-ز): `_parse_output`
> كان يأخذ `float(it.get("confidence"))` من JSON النموذج **مباشرةً** ويحصره
> في `[0,1]`، فتصير ثقةَ `DataPoint`، ثمّ يتوسّطها `JuryCommittee` وتُطبَع على
> غلاف تقرير المصنع. **فالتجميعُ حتميٌّ والمدخلاتُ تقاريرُ النموذج عن نفسه** —
> و«الثقة ٧٢٪» على تقريرٍ يشتريه مصنعٌ ليست قياساً بل انطباعاً.
>
> الاحتياطُ الحتميّ (`min(registry…)`) كان يعمل **فقط** حين يُغفِل النموذجُ
> الحقل، وهو الاستثناء لا القاعدة.

**القاعدةُ المقفولة:** ثقةُ الأدلة **سقفٌ**. للنموذج أن يخفضها معبّراً عن شكٍّ
في تفسيره؛ وليس له أن يرفعها فوق ما تحتمله البيانات — الرفعُ ادّعاءُ سندٍ لم
يُرصَد.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_llm_runtime as rt                          # noqa: E402
from silk_data_layer import DataPoint                  # noqa: E402


def _registry(*confs: float) -> dict:
    return {chr(97 + i): DataPoint(5.0 + i, "UN Comtrade", c, "n", "2026")
            for i, c in enumerate(confs)}


def _parse(registry: dict, ids: list, model_conf=None) -> dict:
    item = {"claim": "ادّعاء", "datapoint_ids": ids}
    if model_conf is not None:
        item["confidence"] = model_conf
    out = rt._parse_output(
        json.dumps({"findings": [item], "gaps": [], "summary": ""},
                   ensure_ascii=False), registry)
    return out["findings"][0] if out["findings"] else {}


def test_the_model_can_never_raise_confidence_above_its_evidence():
    """السقفُ من الأدلة — رقمٌ متفائلٌ من النموذج لا يخترقه."""
    reg = _registry(0.6, 0.9)
    assert _parse(reg, ["a", "b"], model_conf=0.99)["confidence"] == 0.6


def test_the_model_may_lower_confidence():
    """الخفضُ مقبول: للنموذج أن يشكّ في تفسيره هو."""
    reg = _registry(0.6, 0.9)
    assert _parse(reg, ["a", "b"], model_conf=0.3)["confidence"] == 0.3


def test_a_missing_model_confidence_falls_back_to_the_evidence():
    reg = _registry(0.6, 0.9)
    assert _parse(reg, ["a", "b"])["confidence"] == 0.6


def test_a_malformed_model_confidence_falls_back_to_the_evidence():
    """نصٌّ بدل رقم لا يُسقِط البند ولا يمنحه ثقةً افتراضيةً متفائلة."""
    reg = _registry(0.6)
    assert _parse(reg, ["a"], model_conf="عالية")["confidence"] == 0.6


def test_the_ceiling_is_the_weakest_cited_point_not_the_strongest():
    """أضعفُ دليلٍ يحكم — سلسلةٌ لا تقوى على أضعف حلقاتها."""
    reg = _registry(0.9, 0.9, 0.2)
    assert _parse(reg, ["a", "b", "c"], model_conf=0.9)["confidence"] == 0.2


def test_the_producer_derives_the_ceiling_deterministically():
    """حارسٌ مصدريّ: السقفُ من السجلّ لا من حقل النموذج."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_llm_runtime.py"),
        encoding="utf-8").read()
    assert "evidence_conf = min(registry[i].confidence for i in valid_ids)" \
        in src, "سقفُ ثقة الأدلة اختفى — عاد رقمُ النموذج مصدراً (C-06)"
    assert "conf = min(max(0.0, min(1.0, model_conf)), evidence_conf)" in src, (
        "رقمُ النموذج لم يعد محصوراً بسقف الأدلة (C-06)")


# ── C9 · شرحُ الثقة يصل المصنعَ جملةً مفهومة ─────────────────────────────

def test_confidence_is_explained_not_just_scored():
    """رقمٌ بلا سبب لا يفيد صاحب المصنع — الشرحُ جزءٌ من العقد."""
    import silk_i18n
    import silk_reports
    for lang in ("ar", "en"):
        for reason_key in ("confidence_reason_coverage", "confidence_reason_gaps",
                           "confidence_reason_stale",
                           "confidence_reason_conflict"):
            reason = silk_i18n.t(reason_key, lang)
            line = silk_i18n.t("confidence_because", lang,
                               band=silk_i18n.t("data_gap", lang),
                               reason=reason)
            assert reason in line, "الشرحُ لا يدخل الجملة"
            hits = silk_reports._client_forbidden_hits(line, lang)
            assert hits == [], f"شرحُ الثقة بلغةِ نظام في {lang}: {hits[:2]}"
