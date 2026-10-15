"""طلب المالك 2026-10-14: «كقارئ لا تعنيني درجة الثقة والتقييم — أحتاج دراسة
للسوق المستهدف والفرصة الموجودة».

تحت `SILK_CLIENT_METRIC_PRIVACY` تخرج آليةُ التقييم من نسخة العميل (قاعدة الحكم،
جدول قوّة الجوانب بنسبه، الاعتراض على الحكم)، ويبقى ما يُحسَم قبل الالتزام —
والجانبُ الضعيف يُقال بمعناه في السوق بلا نسبة. سطحُ المشغّل لا يتغيّر.
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import silk_render as R                                       # noqa: E402
from test_wave_z_one_verdict import _docx_lines, _view        # noqa: E402

_MECHANICS = ("كيف وصلنا إلى هذا الحكم", "وضعنا قاعدة الحكم",
              "أقوى اعتراض على هذا الحكم")


def _with_privacy(on: bool):
    old = os.environ.get(R.CLIENT_METRIC_PRIVACY_FLAG)
    if on:
        os.environ[R.CLIENT_METRIC_PRIVACY_FLAG] = "1"
    else:
        os.environ.pop(R.CLIENT_METRIC_PRIVACY_FLAG, None)
    return old


def _restore(old):
    if old is None:
        os.environ.pop(R.CLIENT_METRIC_PRIVACY_FLAG, None)
    else:
        os.environ[R.CLIENT_METRIC_PRIVACY_FLAG] = old


def test_client_copy_drops_the_scoring_mechanics(tmp_path):
    old = _with_privacy(True)
    try:
        blob = "\n".join(_docx_lines(_view(jury_state="full", engine="NO-GO"),
                                     tmp_path))
    finally:
        _restore(old)
    leaked = [m for m in _MECHANICS if m in blob]
    assert not leaked, leaked
    assert "ما يجب حسمه قبل الالتزام" in blob


def test_operator_view_keeps_the_mechanics_without_the_flag(tmp_path):
    old = _with_privacy(False)
    try:
        blob = "\n".join(_docx_lines(_view(jury_state="full", engine="NO-GO"),
                                     tmp_path))
    finally:
        _restore(old)
    assert all(m in blob for m in _MECHANICS)


def test_weak_aspect_condition_has_no_strength_percentage():
    ed = {"condition_items": [
        {"id": "C1", "kind": "pillar_weak", "pillar": p, "pct": 38}
        for p in ("market", "competition", "regulatory", "profit", "risk")]}
    old = _with_privacy(True)
    try:
        rows = R.condition_texts(ed, "ar")
    finally:
        _restore(old)
    assert len(rows) == 5
    for r in rows:
        assert not re.search(r"\d+\s*%", r["text"]), r["text"]
    old = _with_privacy(False)
    try:
        assert "38%" in R.condition_texts(ed, "ar")[0]["text"]
    finally:
        _restore(old)
