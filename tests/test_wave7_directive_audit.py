"""الموجة ٧ — سجلّ تدقيق التوجيه: كل فحص جديد مذكور في السجل موجود فعلاً،
وكل الفحوص الجديدة خارج FAIL_TRIGGER_CHECKS (قرار المالك). هرمتي."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_quality_gate as Q  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_registry_names_only_existing_checks():
    src = open(os.path.join(_ROOT, "silk_quality_gate.py"),
               encoding="utf-8").read()
    for label, (check, sev) in Q.DIRECTIVE_AUDIT_CHECKS.items():
        if sev == "WARN":
            assert f'"{check}"' in src, f"{label}: فحص غير موجود {check}"


def test_all_new_directive_checks_are_advisory():
    for label, (check, sev) in Q.DIRECTIVE_AUDIT_CHECKS.items():
        if sev == "WARN":
            assert check not in Q.FAIL_TRIGGER_CHECKS, (
                f"{label}: {check} صار حاجباً بلا قرار مالك")


def test_closing_ledger_entry_exists():
    doc = open(os.path.join(_ROOT, "docs/DEEP_RESEARCH_DECISIONS.md"),
               encoding="utf-8").read()
    assert "خريطة التنفيذ الختامية" in doc
    assert "DIRECTIVE_AUDIT_CHECKS" in doc
    assert "غير المنفَّذ صراحةً" in doc   # لا ادعاء تحقق زائف
