"""قراءة **طبقة الـAPI** كنصّ واحد — read the API layer as one source text.

**لماذا (تدقيق 2026-08-27، البند ٧).** عشرات الحُرّاس في هذه الحزمة تؤكّد
حقائق بنيوية بقراءة نصّ `api.py` («هل يمرَّر `product_card` للكاتب؟»، «هل
يُلَفّ `silk_gap_recovery.recover` بـtry/except؟»، «هل يُنادى `_attach_watchdog`
من المسارين؟»). وهي حُرّاس **مقصودة وقيّمة**: تمنع اختفاء وصلةٍ بلا اختبار
سلوكيّ ممكن.

لكنها كانت تسأل السؤال بصيغة «هل الرمز في هذا **الملف**؟» بينما الحقيقة التي
تحرسها هي «هل الرمز في **طبقة الـAPI**؟». فحين انتقل جسم تشغيلة `/research`
(٨٨٤ سطراً) إلى `silk_research_pipeline.py` — **نقلاً حرفياً بلا تغيير منطق** —
حمرّت واحدٌ وعشرون منها رغم أن السلوك لم يتحرّك قيد أنملة.

هذه الوحدة تُصلح صيغة السؤال لا تُضعِّف الحارس: `api_layer()` تعيد نصّ
`api.py` **زائد** الوحدة المستخرَجة منه. الحارس يبقى يفشل إن اختفت الوصلة من
الاثنين معاً — وهو ما كان يعنيه أصلاً — ويكفّ عن الفشل على حدود ملفٍّ داخليّة.

**القاعدة للحُرّاس القادمة:** إن كنتَ تحرس وصلةً في مسار الطلب، اقرأ
`api_layer()` لا ملفاً بعينه. Ask "is it in the API layer?", not "is it in
this file?" — file boundaries are refactoring detail, wiring is the contract.
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ملفات طبقة الـAPI — `api.py` والوحدات المستخرَجة منه حرفياً (البند ٧).
# إضافةُ ملفٍّ هنا قرارٌ صريح: يعني «هذا امتدادٌ لطبقة الطلب نفسها».
API_LAYER_FILES = ("api.py", "silk_research_pipeline.py")


def api_layer() -> str:
    """نصّ طبقة الـAPI كاملاً — every API-layer file concatenated, in order."""
    parts = []
    for rel in API_LAYER_FILES:
        path = os.path.join(_ROOT, rel)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                parts.append(f.read())
    return "\n".join(parts)
