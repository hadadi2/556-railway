"""الموجة C · C2 — الادّعاءُ يحمل معرّفَ دليله، وحقولُ عقد المصدر تُملأ.

> **الفجوتان** (`docs/ENGINE_AUDIT.md`):
> - **T-04:** `dpN` يُنشأ ويُستعمَل للتحقّق **مرّةً** ثمّ يُهمَل — لا يُخزَّن
>   على `DataPoint` ولا يُحفَظ. فلا يمكن **ميكانيكياً** اقتفاءُ جملةٍ في
>   التقرير إلى معرّف دليلها، والضمانُ المعلَن «كلُّ رقمٍ يقتفى إلى مصدره»
>   يبقى شفهياً: يمكن أن يُقال، ولا يمكن أن يُثبَت.
> - **T-08:** حقولُ عقد المصدر (`unit`/`url`/`data_year`/`reference_period`/
>   `retrieval_method`) موجودةٌ في العقد منذ الموجة ١ لكنها **لا تُملأ أبداً**
>   على مسار البعثات، ففحصُ اكتمالها يقيس صفراً دائماً.

**المبدأ المقفول:** الوراثةُ **نقلٌ لا اشتقاق**. تُورَث القيمةُ حين تتّفق عليها
النقاطُ المُستشهَد بها؛ واختلافُها يعني أنّ البند يجمع مقياسين فلا يُنسَب
لأيّهما — نسبتُه لإحداهما اختلاقُ دقّةٍ لم تُرصَد.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_llm_runtime as L                          # noqa: E402
from silk_data_layer import DataPoint                 # noqa: E402


def _dp(**kw) -> DataPoint:
    base = dict(value=1, source="UN Comtrade", confidence=0.9, note="n",
                retrieved_at="2026-01-01")
    base.update(kw)
    return DataPoint(**base)


# ── T-04 · معرّفُ الدليل يُحفَظ ─────────────────────────────────────────────

def test_datapoint_carries_evidence_ids_separately_from_source_ids():
    """حاملان متمايزان عمداً — دمجُهما يُفسِد الإسنادَ في المراجع.

    `source_ids` أسماءُ مصادرَ عمومية (تُسطَّح في المراجع وتُسنِد الروابط)،
    و`evidence_ids` معرّفاتٌ داخل سجلّ البعثة (للاقتفاء). خلطُهما يُعيد إنتاج
    خطأ الإسناد المركّب الذي عالجه HF1.
    """
    dp = _dp(source_ids=("UN Comtrade", "World Bank"),
             evidence_ids=("dp1", "dp7"))
    assert dp.evidence_ids == ("dp1", "dp7")
    assert dp.source_ids == ("UN Comtrade", "World Bank")
    assert _dp().evidence_ids == (), "الافتراضُ ليس فارغاً — عقدٌ غيرُ رجعيّ"


def test_the_producer_persists_the_cited_ids():
    """المنتِجُ نفسه يحفظها — لا اقتفاءَ يُعاد بناؤه لاحقاً بالتخمين."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_llm_runtime.py"),
        encoding="utf-8").read()
    assert 'evidence_ids=tuple(f.get("datapoint_ids") or ())' in src, (
        "معرّفاتُ الأدلة عادت تُهمَل بعد التحقّق (T-04)")


# ── T-08 · وراثةُ حقول عقد المصدر — بلا لبسٍ فقط ──────────────────────────

def test_unanimous_fields_are_inherited():
    a = _dp(unit="USD", reference_period="2023 CY", retrieval_method="api")
    b = _dp(unit="USD", reference_period="2023 CY", retrieval_method="api")
    out = L._cited_contract_fields([a, b], "UN Comtrade")
    assert out["unit"] == "USD"
    assert out["reference_period"] == "2023 CY"
    assert out["retrieval_method"] == "api"


def test_conflicting_units_are_not_inherited_at_all():
    """وحدتان مختلفتان ⇒ البند يجمع مقياسين، فلا يُنسَب لأيّهما."""
    a = _dp(unit="USD")
    b = _dp(unit="tonnes", source="World Bank")
    assert "unit" not in L._cited_contract_fields([a, b], "UN Comtrade")


def test_the_url_comes_from_the_primary_source_point_only():
    """رابطُ كومتريد لا يُسنَد إلى بندٍ مصدرُه الأساسيُّ البنكُ الدولي.

    «الوحيدةُ غير الفارغة» كانت ستفعل ذلك بالضبط — وهو خطأُ الإسناد المركّب
    (HF1) بشكلٍ آخر: رابطٌ صحيحٌ في ذاته، مُسنَدٌ إلى المصدر الخطأ.
    """
    ct = _dp(source="UN Comtrade", url="https://comtrade.un.org")
    wb = _dp(source="World Bank", url="")
    assert L._cited_contract_fields([ct, wb], "World Bank").get("url") is None
    assert (L._cited_contract_fields([ct, wb], "UN Comtrade")["url"]
            == "https://comtrade.un.org")


def test_data_year_takes_the_newest_cited_evidence():
    """البندُ لا يمكن أن يكون أقدمَ من أحدث دليلٍ بناه."""
    out = L._cited_contract_fields([_dp(data_year=2021), _dp(data_year=2024)],
                                   "UN Comtrade")
    assert out["data_year"] == 2024


def test_no_field_is_invented_when_no_cited_point_carries_it():
    """صفرُ اختلاق: ما لا تحمله أيُّ نقطةٍ لا يظهر."""
    out = L._cited_contract_fields([_dp(), _dp()], "UN Comtrade")
    assert out == {}, f"حقولٌ اختُلِقت من العدم: {out}"


def test_an_empty_citation_list_yields_nothing():
    assert L._cited_contract_fields([], "UN Comtrade") == {}
