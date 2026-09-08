"""موجة صيد الفجوات الثالثة — أقفال الطبقة الفوقية · meta-layer locks.

الصياد الخامس (2026-08-25): ثلاثةُ صفوف في LESSONS.md كانت تسمّي اختباراتٍ
لا وجود لها (سجلٌّ يدّعي إنفاذاً غير موجود يُسكِت السؤال)، وأربعةُ توكيدات
`or True` توتولوجية «تنجح» فارغةً — إحداها كانت تخفي رمزاً لم يوجد قط.
هرمتي. Run: python3 -m pytest tests/test_gap_sweep3_meta.py -q
"""
import ast
import os
import pathlib
import re
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_TESTS = _ROOT / "tests"


def _all_test_defs_and_files() -> tuple[set, set]:
    defs: set[str] = set()
    files: set[str] = set()
    for p in _TESTS.glob("*.py"):
        files.add(p.stem)
        defs.update(re.findall(r"^\s*def\s+(test_\w+|_guard_\w+)",
                               p.read_text(encoding="utf-8"), re.M))
    return defs, files


def test_every_test_name_cited_in_lessons_exists():
    """(الدرس 164) عمود الإنفاذ في LESSONS.md عقدٌ لا زخرفة: كل اسم اختبار/
    حارس مذكور فيه يجب أن يوجد فعلاً — ثلاثةُ صفوف ظلت تسمّي اختباراتٍ
    حُذفت/أعيدت تسميتها فيقرأ المشغّل إنفاذاً وهمياً."""
    ledger = (_ROOT / "docs" / "LESSONS.md").read_text(encoding="utf-8")
    cited = set(re.findall(r"\b(test_[a-z0-9_]+|_guard_[a-z0-9_]+)\b", ledger))
    defs, files = _all_test_defs_and_files()
    known = defs | files
    # «test_run» مفتاح بيانات في العرض لا اسم اختبار؛ والاستشهاد بعائلة ملفات
    # ببادئة («test_wave_p6_…») مشروع — يُقبل الاسم إن كان بادئةً لاسم معروف.
    _NOT_TEST_NAMES = {"test_run"}
    missing = sorted(
        c for c in cited
        if c not in known and c not in _NOT_TEST_NAMES
        and not any(k.startswith(c) for k in known))
    assert missing == [], (
        f"أسماء اختبارات/حراس في LESSONS.md بلا وجود: {missing} — حدِّث "
        "الصف أو أعد الاختبار المحذوف")


def test_the_lessons_citation_scan_is_not_vacuous():
    ledger = (_ROOT / "docs" / "LESSONS.md").read_text(encoding="utf-8")
    cited = set(re.findall(r"\btest_[a-z0-9_]+\b", ledger))
    assert len(cited) >= 100, len(cited)   # السجل يستشهد بمئات الأسماء فعلاً


# قائمة استثناء معلنة لتوكيدات `or True` المشروعة — فارغة: لا استعمال مشروعاً
# معروفاً (الأربعة التي وُجدت كانت كلها توتولوجيات أُصلحت في هذه الموجة).
_DECLARED_OR_TRUE_EXCEPTIONS: tuple = ()


def test_no_tautological_or_true_asserts_in_the_suite():
    """(الدرس 162) `assert X or True` ينجح دائماً — اختبارٌ ميت يُحسب في
    العدّ الأخضر. مسح AST: توكيدٌ شرطُه BoolOp(Or) وآخرُ قيمه ثابتُ True
    (يلتقط أيضاً `A and B or True` بأسبقية العوامل) — فشلٌ بنائي."""
    offenders = []
    for p in sorted(_TESTS.glob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            t = node.test
            if (isinstance(t, ast.BoolOp) and isinstance(t.op, ast.Or)
                    and isinstance(t.values[-1], ast.Constant)
                    and t.values[-1].value is True):
                key = (p.name, node.lineno)
                if key not in _DECLARED_OR_TRUE_EXCEPTIONS:
                    offenders.append(key)
    assert offenders == [], (
        f"توكيدات `or True` توتولوجية: {offenders} — احذف الذيل أو أعلن "
        "الاستثناء بسبب مقروء")


def test_the_or_true_detector_can_actually_fail():
    src = "def test_toy():\n    assert 1 == 2 or True\n"
    tree = ast.parse(src)
    hits = [n for n in ast.walk(tree)
            if isinstance(n, ast.Assert)
            and isinstance(n.test, ast.BoolOp)
            and isinstance(n.test.values[-1], ast.Constant)
            and n.test.values[-1].value is True]
    assert hits, "كاشف التوتولوجيا أعمى عن الحالة الصريحة"
