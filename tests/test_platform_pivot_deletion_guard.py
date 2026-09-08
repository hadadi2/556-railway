"""حارس اكتمال حذف التنقيب — the prospecting-deletion completeness guard.

قرار المالك (2026-08-17) حرفياً: «استبعد البحث عن العملاء، خلّ فقط الدراسات»
ثم اختار **الحذف النهائي** صراحةً. هذا الحارس يمنع عودة أي أثر تدريجياً:

١) لا مسار HTTP تنقيبي مسجَّلاً في تطبيق المنصّة.
٢) لا وحدة تنقيب على القرص، ولا استيراد لها في `silk_platform/`.
٣) لا قسم/نداء تنقيبي في صفحة المنصّة.

الجداول اليتيمة (prospects وأخواتها) **تبقى في المخطّط عمداً** — قانون «لا حذف
بيانات» يعلو كل شيء؛ الحارس يفحص الشيفرة لا المخطّط.
"""
from __future__ import annotations

import pathlib
import re

from tests.platform_helpers import setup_env

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "silk_platform"

_DELETED_MODULES = ("funnels", "email_queue", "unsubscribe", "reporting",
                    "settings", "crypto")
_BANNED_ROUTES = ("/prospects", "/drafts", "/funnels", "/smtp-configs",
                  "/unsubscribe", "/admin/kill-switch")


def test_no_prospecting_route_is_registered(monkeypatch):
    setup_env(monkeypatch)
    from silk_platform.api import create_platform_app
    paths = {getattr(r, "path", "") for r in create_platform_app().routes}
    leftovers = {p for p in paths
                 if any(b in p for b in _BANNED_ROUTES)}
    assert not leftovers, f"مسارات تنقيب ما تزال مسجَّلة: {sorted(leftovers)}"


def test_deleted_modules_are_gone_and_unimported():
    for name in _DELETED_MODULES:
        assert not (_PKG / f"{name}.py").exists(), (
            f"silk_platform/{name}.py عاد بعد الحذف النهائي")
    src = ""
    for p in sorted(_PKG.glob("*.py")):
        src += p.read_text(encoding="utf-8")
    # استيرادات فقط — الذكر في تعليقٍ يؤرّخ القرار مشروع.
    for name in _DELETED_MODULES:
        assert not re.search(rf"(?m)^\s*from \.\s*import .*\b{name}\b", src), (
            f"وحدة محذوفة ما تزال مستورَدة: {name}")
        assert not re.search(rf"(?m)^\s*from \.{name} import", src), (
            f"وحدة محذوفة ما تزال مستورَدة: {name}")


def test_page_has_no_prospecting_sections_or_calls():
    page = (_ROOT / "web" / "platform.html").read_text(encoding="utf-8")
    m = re.search(r"const SECTIONS = \[(.*?)\n\];", page, re.S)
    assert m
    for key in ('key: "drafts"', 'key: "prospects"', 'key: "funnels"'):
        assert key not in m.group(1), f"قسم تنقيب عاد للقائمة الجانبية: {key}"
    for needle in ('api("/prospects', 'api("/drafts', 'api("/funnels',
                   'api("/smtp-configs', "kill-switch", "draft_id",
                   "prospect_ids"):
        assert needle not in page, f"نداء/أثر تنقيب في الصفحة: {needle}"


def test_surviving_operator_smtp_is_not_tenant_campaign_smtp():
    """`smtp_transport` الباقي تشغيليّ حصراً — لا يقرأ جدول `smtp_configs`.

    الفحص على SQL لا على مجرّد الذكر: توثيق الوحدة يشرح انفصالها عن الجدول
    اليتيم بالاسم، وذلك مشروع — قراءتُه هي الممنوعة.
    """
    src = (_PKG / "smtp_transport.py").read_text(encoding="utf-8")
    assert "operator_config_from_env" in src
    assert "FROM smtp_configs" not in src
    assert "sqlite3" not in src          # الوحدة بلا قاعدة إطلاقاً


def test_orphaned_tables_stay_in_schema(monkeypatch):
    """الجداول اليتيمة باقية ببياناتها — «لا حذف بيانات» يعلو قرار الحذف."""
    path = setup_env(monkeypatch)
    from silk_platform import db as pdb
    conn = pdb.connect(path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        conn.close()
    for t in ("prospects", "drafts", "smtp_configs", "comparison_funnels",
              "email_queue", "consent_registry"):
        assert t in tables, f"جدول يتيم اختفى من المخطّط: {t}"
