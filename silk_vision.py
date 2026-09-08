"""مقعدُ نداء الرؤية الواحد — EXT-13 (تدقيق 2026-09-01).

لماذا وحدةٌ مستقلّة: استقبالُ المنتج من صورة (`silk_product_intake`) محوّلٌ أماميّ معزول
عن طبقات التحليل بقرارٍ مقفول (الدرس ٢١ — لا يستورد `silk_ai_judge`)، وكان ينادي المزوّدَ
مباشرةً فلا يمرّ بسياسة حجب `ai_extras` ولا يُعَدّ. هنا السياسةُ الواحدة: حجبٌ سياقيّ ⇒ لا
نداء، والنجاحُ/الفشلُ يُعَدّان في عدّاد اقتصاد البيانات. `silk_ai_judge._call_vision` يفوّض إلى
هذه الدالّة فيبقى للحكم اسمُه ومقعدُه.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def call_vision(system: str, text: str, image_b64: str, media_type: str, *,
                max_tokens: int = 700, model: str | None = None,
                timeout: float | None = None) -> str | None:
    """نداءُ رؤيةٍ واحد عبر المزوّد — نصُّ الردّ أو None (بلا مفتاح/فشل/رفض/حجب)."""
    from silk_context import ai_extras_blocked, count_data
    if ai_extras_blocked():
        log.info("vision call skipped: ai-extras blocked in this context")
        return None
    from silk_llm_provider import get_provider
    if model is None or timeout is None:
        import silk_ai_judge as _judge
        model = model or _judge._MODEL
        timeout = timeout or _judge._TIMEOUT
    out = get_provider().complete_vision(system, text, image_b64, media_type,
                                         max_tokens=max_tokens, model=model, timeout=timeout)
    count_data("llm_calls" if out is not None else "llm_calls_failed")
    return out
