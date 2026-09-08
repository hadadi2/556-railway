"""إعدادات المصنع — factory-level settings resolution (الموجة ٠).

> **المسؤولية الواحدة.** حلّ **لغة المصنع** من مصدر حقيقتها الوحيد
> `accounts.language_preference`، ثمّ حلّ **لغة تقرير دراسة** من لقطتها
> `studies.report_language`.
>
> **القاعدة الصلبة (أمر المالك 2026-08-20).** لغة التقرير تأتي من عمود المصنع
> حصراً، وبعد بدء الدراسة من لقطة الدراسة حصراً. **ممنوع** السقوط على:
> `users.language_preference` · `Accept-Language` · لغة المتصفّح ·
> `localStorage` · ترويسات الطلب · لغة الواجهة الحالية · لغة الموجّه · لغة
> النموذج · لغة آخر تقرير.
>
> ولذلك دوالّ هذه الوحدة **لا تستقبل `Request` ولا أيّ ترويسة** — القيد بنيويّ
> لا اتفاقيّ، ويُقفَل بحارس AST في `tests/test_factory_report_language.py`.
> `users.language_preference` يبقى ما هو: لغة **واجهة** المستخدم، وهي إعداد
> مستقلّ لا يُستبدَل بلغة تقارير المصنع ولا يُشتقّ أحدهما من الآخر.

**Factory settings resolution.** Report language comes from
`accounts.language_preference` only, and — once a study starts — from that
study's `studies.report_language` snapshot only. Never from a user preference,
a request header, the browser, or the current UI language.
"""
from __future__ import annotations

import sqlite3

import silk_i18n

from .db import now_iso

# اللغات المقبولة على سطح المنصّة — مرآة `silk_i18n.LANGS`، والقيد نفسه مكتوبٌ
# في المخطّط (`CHECK (language_preference IN ('ar','en'))`) فالتحقّق مزدوج.
SUPPORTED = silk_i18n.LANGS
DEFAULT = silk_i18n.DEFAULT_LANG


def valid(raw: object) -> bool:
    """هل هذه لغةٌ مقبولة صراحةً؟ — للتحقّق من مدخلات النقاط (422 وإلا)."""
    return str(raw or "").strip().lower() in SUPPORTED


def factory_language(conn: sqlite3.Connection, account_id: int) -> str:
    """لغة المصنع من مصدرها الوحيد — `accounts.language_preference`.

    حسابٌ غير موجود أو قيمةٌ تالفة ⇒ الافتراضي العربي (نفس منطق
    `silk_i18n.normalize`: لا ينقلب تقريرٌ كان عربياً بصمتٍ لأيّ سبب).
    """
    row = conn.execute(
        "SELECT language_preference FROM accounts WHERE id = ?",
        (int(account_id),)).fetchone()
    return silk_i18n.normalize(row["language_preference"] if row else None)


def factory_language_chosen(conn: sqlite3.Connection, account_id: int) -> bool:
    """هل اختار المصنع لغته صراحةً؟ — ختمٌ يكتبه مسار الاختيار الوحيد.

    نفس دلالة الترحيل 008 على المستخدمين: NULL = لم يُختَر قطّ (القيمة المخزونة
    افتراضُ مخطّطٍ لا قرار)، وقيمةٌ = اختيارٌ صريح. تستهلكه الواجهة كي تعرض
    «الافتراضي» بدل ادّعاء اختيارٍ لم يحدث.
    """
    row = conn.execute(
        "SELECT language_chosen_at FROM accounts WHERE id = ?",
        (int(account_id),)).fetchone()
    return bool(row and row["language_chosen_at"])


def set_factory_language(conn: sqlite3.Connection, account_id: int,
                         lang: str) -> str:
    """اكتب لغة المصنع واختم اختيارها — مسار الكتابة الوحيد.

    لا يلتزم (`commit`) — المُنادي يملك حدود المعاملة كي يبقى القيد مع قيد
    التدقيق في معاملةٍ واحدة (نفس انضباط `audit.record`).
    """
    if not valid(lang):
        raise ValueError(f"unsupported language: {lang!r}")
    normalized = str(lang).strip().lower()
    now = now_iso()
    conn.execute(
        "UPDATE accounts SET language_preference = ?, language_chosen_at = ?, "
        "updated_at = ? WHERE id = ?",
        (normalized, now, now, int(account_id)))
    return normalized


def study_report_language(row: object) -> str:
    """لغة تقرير دراسةٍ من لقطتها — `studies.report_language`.

    صفٌّ سابقٌ للترحيل (`NULL`) ⇒ عربي: تلك الدراسات وُلِّدت عربيةً فعلاً، فقراءة
    تقريرها اليوم بأيّ لغةٍ أخرى تغييرٌ بأثرٍ رجعيّ لمصنوعٍ سُلِّم للعميل.

    يقبل `sqlite3.Row` أو `dict` (نقاط المنصّة تمرّر الاثنين).
    """
    value = None
    if isinstance(row, dict):
        value = row.get("report_language")
    elif row is not None:
        try:
            value = row["report_language"]
        except (IndexError, KeyError, TypeError):
            value = None
    return silk_i18n.normalize(value)
