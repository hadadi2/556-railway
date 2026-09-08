"""المستخلِص المتين الواحد لِـJSON مخرَجات النموذج — the one robust extractor.

**قانون البند ٦ (`docs/LESSONS.md`):** كل JSON من نموذج يمرّ عبر مستخلِص متين؛
والفشل = فجوة معلنة (`None`) لا كائنٌ فارغ يبدو نجاحاً — لا اختلاق.

**لماذا وُجد هذا الملف (تدقيق 2026-08-27، البند ٥).** «المستخلِص الواحد» كان
ثلاث نسخ متطابقة المنطق: `silk_llm_runtime._json_candidates`،
`silk_ai_judge._extract_json`، `silk_product_intake._extract_json` — ومعها
`_FENCE_RE` مكرّرة. وحين عضّت حادثةٌ حيّة (ردّ مسيَّج بـ```json يتبعه تعليق
ختامي بقوس معقوف، فيمتدّ `rfind('}')` الساذج فوق حدود JSON فيسقط الردّ كاملاً)
أُصلحت النسخ **واحدةً واحدة** — وdocstring إحداها يعترف صراحةً بأنه «إصلاح
مطابق» للأخرى. ثلاثةُ مواضع لقاعدةٍ واحدة تعني أن الإصلاح الرابع سينسى واحداً.

**العقد (لم يتغيّر حرفاً عن النسخ الثلاث):**

1. جرّب محتوى كل سياج ```...``` على حدة أولاً — المحتوى المعزول لا يمكن أن
   يحوي ما بعد السياج، فينجو من التعليق الختامي.
2. ثم النصّ كاملاً احتياطاً (ردّ بلا سياج).
3. داخل كل مرشّح: أول `{` إلى آخر `}`، ثم `json.loads`.
4. فشل الجميع ⇒ `None`.

`dict_only=True` يرفض المصفوفة العليا (المستدعي ينتظر كائناً) — سلوك
`silk_product_intake` الأصلي.

stdlib فقط، بلا أي استيراد من هذا الريبو — فلا دورة استيراد مع أيٍّ من
مستهلكيه الثلاثة.
"""
import json
import re

# سياج ماركداون: ```json ... ``` أو ``` ... ``` — نفس النمط الذي كان مكرّراً.
FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.S | re.I)


def candidates(text: str) -> list[str]:
    """مرشّحو نص JSON بترتيب الأولوية — fenced blocks first, whole text last."""
    out = [m.group(1).strip() for m in FENCE_RE.finditer(text or "")
           if m.group(1).strip()]
    out.append(text or "")
    return out


def extract(text: str | None, *, dict_only: bool = False):
    """أول JSON صالح من ردّ النموذج، أو `None` — never a fabricated empty object."""
    if not text:
        return None
    for cand in candidates(text):
        cand = cand.strip()
        start, end = cand.find("{"), cand.rfind("}")
        if start < 0 or end < start:
            continue
        try:
            obj = json.loads(cand[start:end + 1])
        except Exception:  # noqa: BLE001 — مرشّح فاشل، جرّب التالي
            continue
        if dict_only and not isinstance(obj, dict):
            continue
        return obj
    return None
