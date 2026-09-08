"""أقفال الموجة ٤ (2026-08-17) — النسخ الاحتياطي + تنبيه الحارس الأحمر.

**الفجوة:** لا آلية نسخ احتياطي إطلاقاً لأي مخزن SQLite (معترف بها في
docs/ANALYSIS.md ومخطّطة في REBUILD_PLAN M8 بلا تنفيذ) — تلف وحدة Railway
يمحو السجلّ التراكمي المدفوع كله. و«الحارس يرى ولا ينادي»: خرق عقد أحمر يبقى
صامتاً حتى يفتح المالك الصفحة.

العقود المقفولة هنا:
- النسخة متّسقة عبر `sqlite3.backup` وحجمها مقيس فعلاً (لا اختلاق).
- الفشل لكل هدف بند معلن في المانيفست، لا انهيار ولا صمت.
- الدورة تحذف طبعات النسخ القديمة **فقط** — لا تلمس ملفاً غريباً أبداً.
- الصمّامان مطفآن افتراضاً (`SILK_BACKUP_HOURS`، `SILK_WATCHDOG_ALERT_EMAIL`)
  — قاعدة الأعلام الجديدة (الدرس ٧٠): التفعيل قرار مالك.
- التنبيه قناة جانبية: لا يرفع أبداً، وعطله يُعلَن في سجلّ العمليات.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

import silk_backup


def _mk_db(path: str, rows: int = 3) -> None:
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE t (x INTEGER)")
        c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(rows)])


@pytest.fixture()
def stores(monkeypatch, tmp_path):
    """مخازن مؤقتة موجَّهة بالبيئة — يعزل الأهداف عن قواعد الريبو الحقيقية."""
    silk = tmp_path / "silk.db"
    usage = tmp_path / "usage.db"
    _mk_db(str(silk))
    _mk_db(str(usage))
    monkeypatch.setenv("SILK_DB", str(silk))
    monkeypatch.setenv("SILK_USAGE_DB", str(usage))
    # وجّه البقية لمسارات غير موجودة — أهداف غائبة تُسقَط بصمت مشروع
    # (target absent ≠ failure؛ الفشل هو هدف موجود تعذّر نسخه).
    for var in ("SILK_STORE_DB", "SILK_OPS_LOG_DB", "SILK_WATCHDOG_DB",
                "SILK_PLATFORM_DB"):
        monkeypatch.setenv(var, str(tmp_path / f"absent-{var}.db"))
    dest = tmp_path / "backups"
    monkeypatch.setenv("SILK_BACKUP_DIR", str(dest))
    return {"silk": silk, "usage": usage, "dest": dest}


def test_run_backup_copies_live_stores_with_measured_sizes(stores):
    m = silk_backup.run_backup()
    names = {f["name"] for f in m["files"]}
    assert {"silk", "usage"} <= names
    for f in m["files"]:
        assert os.path.exists(f["path"])
        assert f["bytes"] == os.path.getsize(f["path"]) > 0   # مقيس لا مختلَق
        # والنسخة قاعدة صالحة فعلاً تُفتَح وتُقرأ — لا نسخ ملف ساذج.
        with sqlite3.connect(f["path"]) as c:
            assert c.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3
    assert m["failures"] == []


def test_a_failing_target_is_a_declared_gap_not_a_crash(stores, monkeypatch):
    """هدف موجود يتعذّر نسخه ⇒ بند failure معلن، وبقية الأهداف تُنسخ."""
    bad = stores["silk"].parent / "bad.db"
    bad.write_text("ليس SQLite إطلاقاً", encoding="utf-8")
    monkeypatch.setenv("SILK_STORE_DB", str(bad))
    m = silk_backup.run_backup()
    assert {"silk", "usage"} <= {f["name"] for f in m["files"]}
    assert [f["name"] for f in m["failures"]] == ["store"]
    assert m["failures"][0]["error"]


def test_rotation_removes_only_our_old_stamps(stores, monkeypatch):
    monkeypatch.setenv("SILK_BACKUP_KEEP_DAYS", "7")
    dest = stores["dest"]
    dest.mkdir(parents=True, exist_ok=True)
    old = dest / "silk.2020-01-01.db"
    old.write_bytes(b"x")
    foreign = dest / "important-notes.db"          # ليس من نمط طبعاتنا
    foreign.write_bytes(b"y")
    m = silk_backup.run_backup()
    assert "silk.2020-01-01.db" in m["rotated_out"]
    assert not old.exists()
    assert foreign.exists(), "الدورة لمست ملفاً ليس من طبعات النسخ — ممنوع"
    # طبعة اليوم الجديدة بقيت.
    assert silk_backup.latest_backup("silk") is not None


def test_latest_backup_none_when_absent(stores):
    assert silk_backup.latest_backup("silk") is None   # قبل أول نسخة


def test_scheduler_is_off_by_default(monkeypatch):
    monkeypatch.delenv("SILK_BACKUP_HOURS", raising=False)
    assert silk_backup.start_scheduler() is False


# ═══════════ نقطتا المشغّل ═══════════════════════════════════════════════════
def _client():
    from fastapi.testclient import TestClient
    import api as api_mod
    return TestClient(api_mod.create_app())


def test_ops_backup_endpoint_is_guarded_and_returns_the_manifest(
        stores, monkeypatch):
    monkeypatch.setenv("SILK_API_KEY", "k-backup")
    cl = _client()
    assert cl.get("/ops/backup").status_code == 401
    r = cl.get("/ops/backup", headers={"X-API-Key": "k-backup"})
    assert r.status_code == 200
    m = r.json()
    assert {"silk", "usage"} <= {f["name"] for f in m["files"]}
    # التنزيل: أحدث طبعة للمخزن المسمّى؛ اسم مجهول = 404 صريحة.
    d = cl.get("/ops/backup/silk", headers={"X-API-Key": "k-backup"})
    assert d.status_code == 200 and len(d.content) > 0
    assert cl.get("/ops/backup/nope",
                  headers={"X-API-Key": "k-backup"}).status_code == 404


def test_ops_backup_download_404_before_any_backup(stores, monkeypatch):
    monkeypatch.setenv("SILK_API_KEY", "k-backup")
    cl = _client()
    r = cl.get("/ops/backup/usage", headers={"X-API-Key": "k-backup"})
    assert r.status_code == 404
    assert "شغّل" in str(r.json().get("detail"))


# ═══════════ تنبيه الحارس الأحمر ═════════════════════════════════════════════
def _red_record():
    return {"analysis_id": 7, "kind": "research", "product": "تمور",
            "market": "NLD", "overall": "red", "created_at": "2026-08-17T00:00:00",
            "findings": [{"check": "cross_market_leak", "severity": "red"}]}


def test_red_alert_is_off_without_the_owner_valve(monkeypatch):
    import silk_watchdog
    monkeypatch.delenv("SILK_WATCHDOG_ALERT_EMAIL", raising=False)
    sent = []
    from silk_platform import smtp_transport
    monkeypatch.setattr(smtp_transport, "send",
                        lambda **kw: sent.append(kw))
    silk_watchdog._maybe_alert_red(_red_record())
    assert sent == []          # الصمّام مطفأ = صفر بريد (قاعدة الدرس ٧٠)


def test_red_alert_sends_one_line_when_armed(monkeypatch):
    import silk_watchdog
    monkeypatch.setenv("SILK_WATCHDOG_ALERT_EMAIL", "owner@example.com")
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_FROM_EMAIL", "noreply@x.com")
    sent = []
    from silk_platform import smtp_transport
    monkeypatch.setattr(smtp_transport, "send", lambda **kw: sent.append(kw))
    silk_watchdog._maybe_alert_red(_red_record())
    assert len(sent) == 1
    assert sent[0]["to_email"] == "owner@example.com"
    assert "أحمر" in sent[0]["subject"]
    assert "cross_market_leak" in sent[0]["body"]
    # سجلّ أخضر لا يُرسل شيئاً.
    sent.clear()
    green = dict(_red_record(), overall="green")
    silk_watchdog._maybe_alert_red(green)
    assert sent == []


def test_red_alert_failure_never_raises_and_is_operator_visible(
        monkeypatch, tmp_path):
    import silk_ops_log
    import silk_watchdog
    db = str(tmp_path / "ops.db")
    monkeypatch.setenv("SILK_OPS_LOG_DB", db)
    monkeypatch.setenv("SILK_WATCHDOG_ALERT_EMAIL", "owner@example.com")
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SILK_PLATFORM_OPERATOR_SMTP_FROM_EMAIL", "noreply@x.com")
    from silk_platform import smtp_transport

    def _boom(**_kw):
        raise OSError("smtp down")

    monkeypatch.setattr(smtp_transport, "send", _boom)
    silk_watchdog._maybe_alert_red(_red_record())   # يجب ألا يرفع أبداً
    rows = silk_ops_log.last_errors(5, path=db)
    assert any((r.get("context") or {}).get("service") == "watchdog_alert"
               for r in rows), "عطل التنبيه غير معلن للمشغّل (عائلة الدرس ٢٦)"


if __name__ == "__main__":
    import subprocess
    import sys
    sys.exit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
