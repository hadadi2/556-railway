"""قاعدة «لا نقاط حذف» البنائية (بلاغ حجب تنزيل #12 — تصحيح المالك).

الحادثة: ثلاث رقعات متتالية لمُنتِجات «…» (بند 12، ثم D3، ثم `_clip_words`)
— كل واحدة اكتُشفت بعد بلوغ الذيل مُسلَّماً. القاعدة تُرفَع من رقعة عند
الطلب إلى **فشل بنائي**: مسح AST على وحدات إنتاج النص الواصلة لمُسلَّم
العميل يحظر أنماط إلحاق «…»/"..." الثلاثة (إلحاق سلسلة، ذيل f-string،
قالب .format)، ويحظر أي سلسلة حرفية تنتهي بحذف خارج docstrings وفحوص
endswith/startswith — بقائمة استثناء معلنة (فارغة حالياً).

حدود المسح (تصريح صريح): حصريّ على أنماط الإلحاق المصدرية الثلاثة
والسلاسل الحرفية؛ البناء الديناميكي (متغيّر يحمل «…» يُلحَق عبر join
وأشباهه) خارجه — تغطيه بوابة الطلب `_check_trailing_ellipsis` وبوابة نصّ
المُنتَج كطبقة ثانية. هرمتي. Run:
  python3 -m pytest tests/test_no_ellipsis_build_rule.py -q
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# وحدات إنتاج النص التي يبلغ ناتجها مُسلَّم العميل (docx/pdf/md/واجهة).
_CLIENT_TEXT_MODULES = ("silk_render.py", "silk_reports.py",
                        "silk_llm_runtime.py", "silk_narrative.py",
                        "silk_economics.py", "silk_i18n.py")

# قائمة الاستثناء المعلنة: (وحدة، سطر تقريبي غير مطلوب، مقتطف) — فارغة:
# لا مُنتِج «…» مشروعاً في هذه الوحدات بعد إصلاحات هذه الموجة.
_DECLARED_EXCEPTIONS: tuple = ()

_TAILS = ("…", "...")


def _ends_ellipsis(v) -> bool:
    return isinstance(v, str) and v.rstrip().endswith(_TAILS)


def _module_hits(path: str) -> list:
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    # docstrings مستثناة بنيوياً (نصوص شرح لا إنتاج)؛ وثوابت وسائط
    # endswith/startswith فحوصٌ لا إنتاج — تُستثنى كأزواج (سطر، قيمة).
    doc_lines: set = set()
    check_pairs: set = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)):
                d = body[0].value
                doc_lines.update(range(d.lineno, (d.end_lineno or d.lineno) + 1))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("endswith", "startswith")):
            for a in node.args:
                for c in ast.walk(a):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        check_pairs.add((c.lineno, c.value))
    hits = []
    for node in ast.walk(tree):
        # النمط ١: إلحاق سلسلة — X + "…ذيل"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            r = node.right
            if isinstance(r, ast.Constant) and _ends_ellipsis(r.value):
                hits.append((node.lineno, "concat", str(r.value)[-30:]))
        # النمط ٢: ذيل f-string حرفي ينتهي بحذف
        if isinstance(node, ast.JoinedStr) and node.values:
            last = node.values[-1]
            if isinstance(last, ast.Constant) and _ends_ellipsis(last.value):
                hits.append((node.lineno, "fstring", str(last.value)[-30:]))
        # النمط ٣: قالب .format حرفي ينتهي بحذف
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "format"
                and isinstance(node.func.value, ast.Constant)
                and _ends_ellipsis(node.func.value.value)):
            hits.append((node.lineno, "format", str(node.func.value.value)[-30:]))
        # العائلة الواسعة: أي سلسلة حرفية تنتهي بحذف خارج docstring/فحص
        if (isinstance(node, ast.Constant) and _ends_ellipsis(node.value)
                and node.lineno not in doc_lines
                and (node.lineno, node.value) not in check_pairs):
            hits.append((node.lineno, "literal", str(node.value)[-30:]))
    return hits


def test_no_ellipsis_emitters_in_client_text_modules():
    """الفشل بنائي لا عند الطلب: أي إلحاق «…» جديد في وحدات نص العميل
    يُسقِط السلسلة هنا قبل أن يبلغ مُسلَّماً ويُطلِق بوابة نصّ المُنتَج."""
    offenders = {}
    excepted = {(m, snip) for m, _ln, snip in _DECLARED_EXCEPTIONS}
    for mod in _CLIENT_TEXT_MODULES:
        hits = [h for h in _module_hits(os.path.join(_ROOT, mod))
                if (mod, h[2]) not in excepted]
        if hits:
            offenders[mod] = hits
    assert not offenders, (
        "مُنتِج «…» جديد في وحدة نص عميل — القاعدة البنائية: لا سلسلة "
        f"مبنية تُذيَّل بنقاط حذف. أصلِح المصدر أو أعلن الاستثناء: {offenders}")


def test_clip_words_declares_the_clip_instead_of_ellipsis():
    """فكس `_clip_words` تحت القاعدة: قصّ نظيف عند حدّ كلمة + لاحقة معلنة
    — لا «…» (المصدر الثالث الكامن الذي كان سيحجب حتى التقرير المعاد
    توليده)."""
    from silk_render import _clip_words
    long_text = ("بيانات اقتصادية فعلية للسنوات السابقة عن حجم الإنفاق "
                 "الاستهلاكي على منتجات الألبان في السوق الأردني")
    out = _clip_words(long_text, 70)
    assert "…" not in out and not out.endswith("...")
    assert out.endswith("(مختصر — التفصيل في حدود هذا التقرير)")
    body = out[:out.index(" (مختصر")]
    assert long_text.startswith(body)          # قصّ عند حدّ كلمة، لا وسطها
    assert _clip_words("نص قصير", 70) == "نص قصير"   # لا لاحقة بلا قصّ


def test_verification_gap_line_carries_no_ellipsis():
    """سطر «N بنداً تحتاج تحققاً» على سطوح الحكم — المستهلك الفعلي للقصّ:
    فجوة أطول من النافذة تصل بلاحقة معلنة لا بذيل «…»."""
    from silk_render import verification_gap_line
    gaps = [("بيانات اقتصادية فعلية للسنوات السابقة عن حجم الإنفاق "
             "الاستهلاكي على منتجات الألبان في السوق الأردني"),
            "سعر التجزئة المرصود لقناة التجزئة الحديثة"]
    line = verification_gap_line({"data_gaps": []}, gaps)
    assert "تحتاج تحققاً" in line
    assert "…" not in line and "..." not in line
    assert "(مختصر — التفصيل في حدود هذا التقرير)" in line
