"""قفل خطّ أساس الحكم والدرجة — أمر المالك (خطوة الإعداد ٢، هدف الدراسة الاحترافية).

القاعدة: «الحكم والدرجة لا يتغيّران على أي مدوّنة» — أي تعديل في هذا الهدف
(وحدات، تكلفة، مفردات، ملخص، نثر، استدلال، تقدير، كلفة) يجب ألّا يحرّك حكمَ
العرض ولا قرارَ المحرّك الحتمي على المدوّنات العشر المجمّدة. البصمة تُبنى
بنفس دالة المولّد (`tools/gen_verdict_baseline.py`) وتُقارَن حرفياً ضد الملف
الملتزَم. كسرُ هذا الاختبار لا يُصلَح بإعادة توليد خطّ الأساس — يُصلَح بإزالة
أثر التغيير على الحكم، أو يتوقف العمل ويُبلَّغ المالك (قاعدة «موجة لا تخضرّ»).

The committed fingerprint is regenerated only on an explicit owner decision.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import pytest

from conftest import block_network
from gen_verdict_baseline import (BASELINE_PATH, CANONICAL_BLOBS, fingerprint,
                                  load_blob)


def _baseline() -> dict:
    with open(BASELINE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_baseline_file_covers_all_ten_blobs():
    """الملف الملتزَم يغطي المدوّنات العشر كلها — لا أقل ولا أكثر."""
    assert set(_baseline()) == set(CANONICAL_BLOBS)
    assert len(CANONICAL_BLOBS) == 10


@pytest.mark.parametrize("key", sorted(CANONICAL_BLOBS))
def test_verdict_and_score_unchanged(key):
    """بصمة الحكم/الدرجة الحيّة تطابق الملتزَمة حرفياً — بلا شبكة."""
    with block_network():
        live = fingerprint(load_blob(key))
    expected = _baseline()[key]
    assert live == expected, (
        f"تغيّر الحكم/الدرجة على «{key}» — ممنوع في هذا الهدف.\n"
        f"الملتزَم: {json.dumps(expected, ensure_ascii=False)}\n"
        f"الحيّ:    {json.dumps(live, ensure_ascii=False)}")
