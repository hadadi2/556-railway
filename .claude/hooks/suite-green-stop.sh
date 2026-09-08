#!/usr/bin/env bash
# حارس «لا نهايةَ دورٍ والسويت أحمر» — أمر المالك (خطوة الإعداد ١ لهدف
# الدراسة الاحترافية): يجعل قاعدة «موجة لا تخضرّ = توقف» حتمية لا وعداً.
#
# السلوك: عند كل محاولة إنهاء دور يشغَّل `python3 -m pytest tests/ -q`؛
# فشلُه يمنع الإنهاء (exit 2) ويعرض ذيل المخرجات.
#
# مسار سريع حتمي (بالاتجاهين — ملاحظة مراجعة §58): تُحفَظ بصمةُ الشجرة
# **ونتيجتُها** (green/red) بعد كل تشغيلة؛ شجرةٌ مطابقة بايتاً بايتاً ⇒ نفس
# النتيجة بلا إعادة تشغيل (~8 دقائق): الخضراء تمرّ فوراً والحمراء تُحجَب
# فوراً برسالة النتيجة المحفوظة. أيُّ تغيير يغيّر البصمة فيُعاد التشغيل.
#
# فشل الوصول لمجلد المشروع = حجبٌ معلن (exit 2) لا تمريرٌ صامت — بوابة
# إنفاذ لا تفشل مفتوحةً (ملاحظة مراجعة §58).
#
# المخرجُ المتعمَّد الوحيد (سيناريو «توقّف عند آخر كوميت أخضر وأبلغ المالك»):
# إنشاء الملف .claude/hooks/.allow-red-stop يسمح بإنهاءٍ واحد ثم يُحذف —
# لا يُنشأ إلا مع بلاغ صريح للمالك في نص الرد.
set -u
cat >/dev/null 2>&1 || true   # استهلاك stdin (JSON الحدث) — لا نعتمد عليه
if ! cd "${CLAUDE_PROJECT_DIR:-.}"; then
    echo "بوابة السويت: تعذّر الوصول لمجلد المشروع (${CLAUDE_PROJECT_DIR:-.}) — حجبٌ معلن لا تمرير صامت" >&2
    exit 2
fi
marker=".claude/hooks/.allow-red-stop"
state=".claude/hooks/.last-green-tree"
if [ -f "$marker" ]; then
    rm -f "$marker"
    exit 0
fi
tree_hash="$({
    git rev-parse HEAD 2>/dev/null
    git diff HEAD 2>/dev/null
    git ls-files -o --exclude-standard 2>/dev/null | sort | while read -r f; do
        sha256sum "$f" 2>/dev/null
    done
} | sha256sum | cut -d' ' -f1)"
cached="$(cat "$state" 2>/dev/null || true)"
if [ "$cached" = "$tree_hash green" ]; then
    exit 0
fi
if [ "$cached" = "$tree_hash red" ]; then
    {
        echo "السويت أحمر على هذه الشجرة (نتيجة محفوظة، لم يُعَد التشغيل) —"
        echo "قاعدة المالك تمنع إنهاء الدور: أصلِح وغيّر الشجرة، أو لسيناريو"
        echo "التوقف المبلَّغ فقط أنشئ $marker."
    } >&2
    exit 2
fi
tmp="$(mktemp)"
# R7 (CI-9): مجموعةٌ فرعية اختيارية — SILK_STOP_HOOK_SUBSET=1 يشغّل أقفالَ التدقيق
# والدفاتر فقط؛ الافتراضُ كما كان (السويت كاملاً).
if [ "${SILK_STOP_HOOK_SUBSET:-0}" = "1" ]; then
    targets="tests/test_audit_2026_09_01_*.py tests/test_lessons_enforcement.py tests/test_regression_registry.py"
else
    targets="tests/"
fi
# shellcheck disable=SC2086
if python3 -m pytest $targets -q >"$tmp" 2>&1; then
    printf '%s green' "$tree_hash" >"$state"
    rm -f "$tmp"
    exit 0
fi
printf '%s red' "$tree_hash" >"$state"
{
    echo "السويت أحمر — قاعدة المالك تمنع إنهاء الدور. أصلِح أولاً"
    echo "(أو، لسيناريو التوقف المبلَّغ فقط: أنشئ $marker). آخر السطور:"
    tail -20 "$tmp"
} >&2
rm -f "$tmp"
exit 2
