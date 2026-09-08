"""بوّابةُ دليل الـPDF المشتركة — R8 (TEST-5، تدقيق 2026-09-01).

كان تخطّي LibreOffice مكتوباً في ثلاثة ملفّاتٍ بثلاث صيغ (`pytest.skip("soffice غائب")`)،
فبيئةٌ بلا محوّلٍ تُخفي **دليلَ التسليم كلَّه** بلا أن يقول أحدٌ إنّه لم يُؤخَذ. القاعدةُ
واحدة الآن ومطابقةٌ لقرار المالك ٥: غيابُ المحوّل **فشلٌ** إلا في بيئةٍ محلّيةٍ موسومة
`SILK_PDF_LOCAL_SKIP=1`، وحينها يُقال صراحةً إنّ الدليل لم يُؤخَذ.
"""
from __future__ import annotations

import os

import pytest


def local_skip_allowed() -> bool:
    return os.environ.get("SILK_PDF_LOCAL_SKIP", "").strip() == "1"


def pdf_gate(reason: str = "") -> None:
    """استدعِها في أوّل اختبارٍ يحتاج soffice: تتخطّى معلِنةً محلّياً، وتفشل في CI."""
    import silk_reports
    if silk_reports._find_soffice() is not None:  # noqa: SLF001
        return
    tail = f" ({reason})" if reason else ""
    if local_skip_allowed():
        pytest.skip("SILK_PDF_LOCAL_SKIP=1 — دليلُ الـPDF **لم يُؤخَذ** في هذه البيئة" + tail)
    pytest.fail("محوّل الـPDF (soffice) غائب — الإنتاج وCI يشحنانه؛ لا يُعلَن التسليم "
                "جاهزاً بلا PDF مُتحقَّق منه" + tail)


def pdf_engine_broken(reason: str = "") -> None:
    """المحوّلُ موجودٌ لكنّه لا يعمل في هذه البيئة (صندوقٌ معزول) — تخطٍّ معلَن."""
    if local_skip_allowed():
        pytest.skip("SILK_PDF_LOCAL_SKIP=1 — محوّلُ الـPDF لا يعمل هنا: " + (reason or "—"))
    pytest.fail("محوّلُ الـPDF موجودٌ ولا يعمل — " + (reason or "—"))
