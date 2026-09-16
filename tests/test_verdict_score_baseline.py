"""قفل خطّ أساس الحكم والدرجة — أمر المالك (خطوة الإعداد ٢، هدف الدراسة الاحترافية).

القاعدة: «الحكم والدرجة لا يتغيّران على أي مدوّنة» — أي تعديل في هذا الهدف
(وحدات، تكلفة، مفردات، ملخص، نثر، استدلال، تقدير، كلفة) يجب ألّا يحرّك حكمَ
العرض ولا قرارَ المحرّك الحتمي على المدوّنات المجمّدة. البصمة تُبنى
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


# الدرس ٢٣٩ (موجة عيوب التقرير): صار السجلُّ اثنتي عشرة مدوّنة بعد إضافة
# مصر ونيجيريا للمراجعة الذاتية. العددُ يبقى مقفولاً (لا أقلّ ولا أكثر) كي
# لا تُضاف مدوّنةٌ بلا بصمةٍ ملتزَمة ولا تُسقَط واحدةٌ صامتةً — وتوسيعُه
# قرارٌ معلَن لا تحديثٌ لتمريرِ موجة. **ولم تتغيّر بصمةُ أيٍّ من العشر
# الأصلية** بالإضافة: ٣٤ سطرَ إدراجٍ وصفرُ سطرِ حذف.
_EXPECTED_BLOBS = 14


def test_baseline_file_covers_every_blob():
    """الملف الملتزَم يغطي كلَّ مدوّنة — لا أقل ولا أكثر."""
    assert set(_baseline()) == set(CANONICAL_BLOBS)
    assert len(CANONICAL_BLOBS) == _EXPECTED_BLOBS


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
