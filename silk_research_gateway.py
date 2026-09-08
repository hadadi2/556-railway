"""بوابة تشغيل البحث العميق لغير HTTP · deep-research gateway for non-HTTP callers.

لماذا هذه الوحدة (قرار المالك 2026-08-18 — «المنصّة لا تعمل»): دراسات المنصّة
كانت تشغّل `silk_engine.analyze` السريع فتكتمل «دراسة» في ثوانٍ بلا أي بحث
عميق. الإصلاح يوصل جسر المنصّة (`silk_platform/engine_bridge.py`) بجسم تشغيلة
`/research` **نفسه** — والجسم مغلقة داخل `create_app()` في `api.py` لا تُستورد،
فتُسجَّل هنا وقت الإقلاع ويستهلكها الجسر وقت الإطلاق.

العقد (مبدأ المسار الواحد — لا خط أنابيب موازٍ):
- `api.create_app()` يستدعي `register(run=..., readiness=...)` بعد بناء المغلقات؛
  `run` هي مغلقة تستدعي `_research_impl` (نفس البوابات والحجوزات والفشل
  والنقاط المرجعية حرفياً) وتعيد نتيجة التشغيلة قاموساً.
- الجسر يستدعي `readiness()` قبل مطالبة الدراسة (رفض مبكر معلَن بلا حرق حصّة)
  ثم `run(...)` داخل خيطه (تنفيذ متزامن في الخيط — لا خيوط متداخلة).
- عملية بلا تسجيل (اختبار منصّة معزول بلا محرّك) = `runner() is None` والجسر
  يفشل بسبب معلَن — لا تدهور صامت إلى التحليل السريع (عقد عدم الاختلاق).
"""
from __future__ import annotations

from typing import Callable

_RUN: Callable[..., dict] | None = None
_READINESS: Callable[[], tuple[bool, str]] | None = None


def register(run: Callable[..., dict],
             readiness: Callable[[], tuple[bool, str]]) -> None:
    """سجّل مغلقتَي التشغيل والجهوزية — يستدعيها `api.create_app()` وقت الإقلاع."""
    global _RUN, _READINESS
    _RUN = run
    _READINESS = readiness


def runner() -> Callable[..., dict] | None:
    """مغلقة التشغيل المسجَّلة — None إن لم يُقلِع المحرّك في هذه العملية."""
    return _RUN


def readiness() -> tuple[bool, str]:
    """جهوزية البحث العميق — (ready, reason). غير مسجَّلة = غير جاهزة بسبب معلَن."""
    if _READINESS is None:
        return False, ("محرّك البحث العميق غير مسجَّل في هذه العملية — "
                       "أقلِع عبر api:app (uvicorn api:app) لا عبر تركيب "
                       "المنصّة وحدها.")
    return _READINESS()


def reset() -> None:
    """صفّر التسجيل — لعزل الاختبارات فقط."""
    global _RUN, _READINESS
    _RUN = None
    _READINESS = None
