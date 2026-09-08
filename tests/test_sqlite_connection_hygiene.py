"""عائلة `sqlite-connection-outlives-its-scope` — قفلُ تغطية لا إصلاحُ حادثة.

> **العائلة (تدقيق 2026-08-30).** `sqlite3.Connection` كمدير سياق **يلتزم
> ولا يُغلق**:
>
>     with connect(path) as conn:   # ← commit/rollback فقط
>         conn.execute(...)         # ← الاتصالُ يبقى مفتوحاً بعد الخروج
>
> على لينكس لا يظهر شيء (يُحذَف الملفُّ المفتوح بلا شكوى). على ويندوز يبقى
> الملفُّ محجوزاً، فينهار تنظيفُ `TemporaryDirectory` بـ`WinError 32` —
> **في اختبارٍ يقيس شيئاً آخر تماماً**. أربعةُ مواضع كانت مصابة:
> `silk_ops_log` و`silk_usage` و`silk_store` و`silk_storage` (٢٢+٧+٢٢+٢٠
> استعمالاً)، وأثرُها كان فشلاً متنقّلاً يُقرأ انحدارَ شيفرةٍ في كل موجة.

القفلُ هنا **تغطيةٌ لا حالات**: يمسح وحداتِ التخزين كلَّها ويرفض أيَّ استعمالٍ
جديد لا يُغلق — فوحدةٌ خامسة تُكتَب غداً تُحمِّر السويت بدل أن تُهدر يوماً من
التشخيص بعد شهر.
"""
import ast
import io
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# وحداتُ التخزين: كلُّ ما يفتح SQLite في مسار إنتاجيّ.
_STORAGE_MODULES = ("silk_storage.py", "silk_store.py", "silk_usage.py",
                    "silk_ops_log.py", "silk_sqlite.py",
                    # R5 (DB-8): الجامعون كانوا خارج الحارس ففاتته ثلاثةُ مواضع.
                    "silk_collectors.py",
                    os.path.join("silk_platform", "db.py"),
                    os.path.join("silk_platform", "repository.py"))


def _src(rel: str) -> str:
    return io.open(os.path.join(_ROOT, rel), encoding="utf-8").read()


def _connection_openers(tree: ast.AST) -> list[str]:
    """أسماءُ الدوالّ التي تُعيد اتصالاً — `connect` وأخواتها المحلّية."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in ("connect", "_connect"):
            out.append(n.name)
    return out


@pytest.mark.parametrize("rel", _STORAGE_MODULES)
def test_no_storage_module_uses_a_connection_as_a_bare_context_manager(rel):
    """`with connect(...) as conn:` ممنوع — يلتزم ولا يُغلق.

    البديلُ المعتمَد: مغلقةٌ `_open()` تُغلق في `finally`. الاستثناءُ الوحيد
    المسموح هو `with conn:` **داخل** تلك المغلقة نفسها (التزامٌ صريح حول
    اتصالٍ ستُغلقه هي).
    """
    src = _src(rel)
    tree = ast.parse(src, filename=rel)
    openers = set(_connection_openers(tree)) | {"connect", "_connect"}
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            call = item.context_expr
            if not isinstance(call, ast.Call):
                continue
            name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
            if name in openers:
                offenders.append(node.lineno)
    assert not offenders, (
        f"{rel}: اتصالٌ يُستعمَل مدير سياقٍ مباشرةً في السطور {offenders} — "
        "يلتزم ولا يُغلق، فيحجز الملفَّ على ويندوز. استعمل مغلقة `_open()`.")


@pytest.mark.parametrize("rel", _STORAGE_MODULES)
def test_every_storage_module_that_opens_also_closes(rel):
    """وحدةٌ تفتح اتصالاً يجب أن تُغلقه في مكانٍ ما — لا فتحٌ بلا إغلاق."""
    src = _src(rel)
    if src.count("connect(") == 0:
        pytest.skip(f"{rel} لا يفتح اتصالاً")
    if rel == "silk_sqlite.py":
        # المُوصِّلُ منخفضُ المستوى **يُسلّم** الاتصالَ لمستدعيه؛ إغلاقُه هناك
        # لا هنا. إلزامُه بالإغلاق يعني إعادةَ اتصالٍ مغلق — عكسُ الغرض.
        pytest.skip("silk_sqlite هو المُوصِّل نفسه — الإغلاقُ مسؤوليةُ المستدعي")
    assert ".close()" in src, (
        f"{rel}: يفتح اتصالات SQLite ولا يُغلق أيّاً منها")


def test_the_four_repaired_modules_expose_a_closing_helper():
    """الأربعةُ المُصلَحة تحمل المغلقةَ نفسَها — إصلاحٌ واحد لا أربعة أشكال."""
    for rel in ("silk_storage.py", "silk_store.py", "silk_usage.py",
                "silk_ops_log.py"):
        src = _src(rel)
        assert "def _open(" in src, f"{rel}: بلا مغلقةِ إغلاق"
        assert "conn.close()" in src, f"{rel}: المغلقةُ لا تُغلق"
        assert "finally:" in src, f"{rel}: الإغلاقُ ليس في `finally`"


def test_temp_dirs_are_swept_at_session_end():
    """كنسُ المجلّدات المؤقّتة منصوبٌ في `pytest_configure` لا في تجهيزة.

    بعضُ الملفّات ينادي `mkdtemp()` وقتَ الاستيراد — قبل أن تعمل أيُّ تجهيزة
    ولو كانت `session`-scope. التركةُ المرصودة قبل هذا الكنس: ٢٠٩٬٦٤٨ مجلّداً.
    """
    src = _src(os.path.join("tests", "conftest.py"))
    assert "_install_tmpdir_tracking()" in src
    assert "def pytest_unconfigure" in src
    i = src.index("def pytest_configure")
    j = src.index("_install_tmpdir_tracking()", i)   # النداء **بعد** التعريف
    assert j - i < 200, "الكنسُ لا يُنصَب في أوّل `pytest_configure`"
