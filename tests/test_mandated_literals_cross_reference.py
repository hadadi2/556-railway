"""تقاطع الموجّه × قوائم الحظر بنائياً (تصحيح المالك — موجة حجب #12).

الحادثة النمطية: الموجّه يفرض عبارة إخراجاً ثم يحظرها فحصٌ لاحق (سابقة
«مؤشر سياقي» — فُرضت صياغةً مقيسة ثم حُظر تكرارها؛ وسابقة «فجوة معلنة» —
مفردة كانت مفروضة ثم دخلت قائمة الغياب المحظورة). الاكتشاف كان إنتاجياً
(تقرير حي يحجبه فحص على عبارة أملاه الموجّه نفسه). هذا الملف يرفعه
بنائياً عبر سجلّ `silk_ai_judge.MANDATED_OUTPUT_LITERALS` واختبار ثلاثي:
(أ) كل بند مسجّل موجود فعلاً في نص الموجّه/العقد، (ب) كل علامة إلزام
إخراجيّ («فعل إخراج + حرفياً») لها بند مسجّل أو تُحيل لمحتوى المدخلات
(«أعلاه»/"above")، (ج) لا بند يطابق — بعد `_norm_ar` — أي إبرة حظر.
هرمتي. Run: pytest tests/test_mandated_literals_cross_reference.py -q
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import silk_ai_judge as AJ                               # noqa: E402
import silk_quality_gate as QG                           # noqa: E402
import silk_style_contract as SC                         # noqa: E402

_JUDGE_PATH = os.path.join(_ROOT, "silk_ai_judge.py")
_CONTRACT_PATH = os.path.join(_ROOT, "silk_style_contract.py")


def _registry_line_range() -> tuple:
    with open(_JUDGE_PATH, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign)
                   else [])
        for t in targets:
            if getattr(t, "id", "") == "MANDATED_OUTPUT_LITERALS":
                return node.lineno, node.end_lineno or node.lineno
    raise AssertionError("سجل MANDATED_OUTPUT_LITERALS غير موجود")


def _prompt_constants() -> list:
    """كل الثوابت النصية في مصدر الموجّه (خارج السجل نفسه) + العقد."""
    lo, hi = _registry_line_range()
    consts = []
    for path, skip in ((_JUDGE_PATH, True), (_CONTRACT_PATH, False)):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if skip and lo <= node.lineno <= hi:
                    continue
                consts.append(node.value)
    return consts


def test_a_every_registered_literal_exists_in_the_prompt_source():
    """(أ) بند مسجّل غير موجود في الموجّه = سجل متقادم — يفشل البناء."""
    consts = _prompt_constants()
    missing = [lit for lit in AJ.MANDATED_OUTPUT_LITERALS
               if not any(lit in c for c in consts)]
    assert not missing, f"بنود مسجلة غابت عن نص الموجّه/العقد: {missing}"


# أفعال الإلزام الإخراجي: سطرُ «حرفياً» لا يُعَدّ علامة إلزامِ إخراجٍ إلا
# بفعل إخراج قربه — بقية أوامر «حرفياً» (استشهد/تبقى/بهذا الترتيب/لا
# تكرّر) قيودُ نقلٍ من الحقائق لا فرضُ سلسلةٍ من الموجّه نفسه.
_EMIT_VERBS = ("اكتب", "اطبع", "يطبع", "يُطبع", "متضمّناً", "احمل الوسم",
               "اعرض", "ضع ")


def _mandate_markers() -> list:
    with open(_JUDGE_PATH, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    markers = []
    for i, line in enumerate(lines):
        # صيغتا الإلزام: «حرفياً» بفعل إخراج قربها، أو «بعنوان '### …'»
        # (فرضُ عنوانٍ فرعيّ حرفيّ — كانت خارج نظر الماسح، صيد الفجوات ٣).
        heading_mandate = "بعنوان" in line and "###" in "\n".join(
            lines[i:i + 4])
        if "حرفياً" not in line and not heading_mandate:
            continue
        verb_window = "\n".join(lines[max(0, i - 2):i + 2])
        if heading_mandate or any(v in verb_window for v in _EMIT_VERBS):
            markers.append((i + 1, "\n".join(lines[max(0, i - 3):i + 7])))
    return markers


def test_b_every_output_mandate_marker_maps_to_a_registered_literal():
    """(ب) علامة إلزام إخراجي بلا بند مسجّل (ولا إحالة «أعلاه» لمحتوى
    المدخلات) = حرفية مفروضة أفلتت من السجل — يفشل البناء (لا تفويت
    مستقبلي: البند الجديد يُسجَّل في نفس التعديل)."""
    unmatched = []
    heads = [lit[:20] for lit in AJ.MANDATED_OUTPUT_LITERALS]
    # إحالات محتوى المدخلات: الإلزام هو نسخُ ما ورد في الحقائق/الموجّه
    # قبل هذا الموضع — لا حرفيةَ موجّهٍ ثابتة تُسجَّل.
    _INPUT_REFS = ("أعلاه", "above", "كما وردا", "كما وردت")
    for lineno, window in _mandate_markers():
        if any(r in window for r in _INPUT_REFS):
            continue
        if any(h in window for h in heads):
            continue
        unmatched.append(lineno)
    assert not unmatched, (
        f"علامات إلزام إخراجي بلا بند مسجل قربها (أسطر {unmatched}) — "
        "سجّل الحرفية في MANDATED_OUTPUT_LITERALS أو أحل لمحتوى المدخلات")


def test_b_marker_scan_actually_sees_the_known_mandates():
    """حارس فراغ للماسح نفسه: العلامات المعروفة الأربع على الأقل مرئية —
    ماسح لا يرى شيئاً «ينجح» فارغاً بلا قياس."""
    linenos = [ln for ln, _w in _mandate_markers()]
    assert len(linenos) >= 4, linenos


def test_c_no_registered_literal_hits_any_gate_blocklist():
    """(ج) التقاطع الأعلى قيمة: حرفية مفروضة تطابق إبرة حظر = موجّه يأمر
    بما تحجبه البوابة — يفشل البناء قبل أي تقرير حي."""
    blocklists = {
        "_ABSENCE_FORBIDDEN": QG._ABSENCE_FORBIDDEN,
        "_SYSTEM_LANGUAGE_NEEDLES": QG._SYSTEM_LANGUAGE_NEEDLES,
        "_EMPTY_CITATION_NEEDLES": QG._EMPTY_CITATION_NEEDLES,
        "ALARMIST_PHRASES": tuple(SC.ALARMIST_PHRASES),
        "banned_openers": (SC.ACADEMIC_SECTION_CLOSER,
                           SC.ACADEMIC_SECTION_CLOSER_EN),
        # دورة C4: القوائم الأقرب لعائلة الحادثة كانت غائبة — نصوص بوابة
        # نصّ المُنتَج النهائي (النائب الصلب + النائب العام).
        "_ARTIFACT_HARD_PLACEHOLDERS": QG._ARTIFACT_HARD_PLACEHOLDERS,
        "_PLACEHOLDER_STRINGS": QG._PLACEHOLDER_STRINGS,
        # الصوتُ البشريّ (طلب المالك «Humanized»): قائمةُ الحشو التي تعدّها
        # البوابة وقائمةُ البدائل التي يقرؤها الموجّه. **هذا القفلُ هو ما
        # كان سيمنع العيبَ**: «ينبغي التعامل مع» دخلت القائمةَ أوّلاً وهي
        # صدرُ مُخرَجٍ إلزاميّ — فمنعُها يأمر بإسقاط تحذيرٍ واجب.
        "FILLER_PHRASES": tuple(SC.FILLER_PHRASES),
        "STOCK_PHRASES": tuple(p for p, _a in SC.STOCK_PHRASES),
    }
    collisions = []
    for lit in AJ.MANDATED_OUTPUT_LITERALS:
        norm_lit = QG._norm_ar(lit)
        for name, needles in blocklists.items():
            for n in needles:
                if QG._norm_ar(n) and QG._norm_ar(n) in norm_lit:
                    collisions.append((lit, name, n))
    assert not collisions, (
        f"حرفية مفروضة تطابق إبرة حظر — الموجّه يأمر بما تحجبه البوابة: "
        f"{collisions}")


def test_c_no_registered_literal_hits_the_client_artifact_gate():
    """(ج مكمَّل — دورة C4): حارس مفردات العميل (silk_reports) هو الحاجب
    الفعلي للمُنتَج النهائي وكان خارج التقاطع — أنماطه regex لا إبر نص،
    تُفحَص بحثاً على كل حرفية مسجلة + سقالة «إذن ماذا»."""
    import silk_reports as SR
    collisions = []
    pats = (list(getattr(SR, "_CLIENT_FORBIDDEN_PATTERNS", []))
            + list(getattr(SR, "_CLIENT_FORBIDDEN_PATTERNS_EN", [])))
    assert pats, "أنماط حارس العميل غير مقروءة — الفحص بلا قياس"
    for lit in AJ.MANDATED_OUTPUT_LITERALS:
        for label, rex in pats:
            if rex.search(lit):
                collisions.append((lit, "client_forbidden", label))
        if QG._SO_WHAT_LEAK_RE.search(lit):
            collisions.append((lit, "so_what_scaffold", "إذن ماذا"))
    assert not collisions, (
        f"حرفية مفروضة يرفضها حارس مُنتَج العميل: {collisions}")


def test_c_the_collision_detector_is_not_vacuous():
    """حارس فراغ للكاشف: تصادم مصطنع يُلتقط فعلاً بنفس منطق الفحص."""
    fake = "القيمة غير مرصودة في هذا الجدول"     # يحمل إبرة «غير مرصود»
    norm = QG._norm_ar(fake)
    assert any(QG._norm_ar(n) in norm for n in QG._ABSENCE_FORBIDDEN)
