"""أقفال R5 — سلامة البيانات (التدقيق الجنائي 2026-09-01، المرحلة ٥).

لماذا هذا الملف: ترحيلٌ يُطبَّق نصفه (`executescript` يلتزم قبل صفّ النسخة
فتعطُّلٌ بين ALTER الثاني والرابع يُعطِّل كلّ `/platform`)، وقاعدةٌ بلا WAL
(كاتبٌ طويل يحجب القرّاء ٣٠ ثانية)، وجداولٌ بلا فهارس لأنماط الاستعلام
الفعلية، و`init_db` يُعاد في كل نداء، وطوابعُ محلّية تُقارَن بدلوٍ UTC،
و`market_scores` تتضاعف مع كل حفظ، ونسخةٌ احتياطية بلا صورٍ ولا استرجاع،
واتصالاتٌ لا تُغلَق في الجامعين، وحذفُ دراسةٍ يتعثّر على صفوف عهد الحملات،
وفوترةٌ تقرأ ثم تكتب في معاملتين، وعمودان مسمّيان بلا تحقّق، وإشعاراتٌ
وتدقيقٌ بلا احتفاظ، وكنّاسان، و`run_token` يصل المستأجر.

هرمتي: قواعد مؤقّتة، لا شبكة. Hermetic only.
"""
from __future__ import annotations

import datetime
import glob
import inspect
import os
import pathlib
import shutil
import sqlite3
import sys
import threading
import time
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.platform_helpers import (client, hdr, login, make_factory,  # noqa: E402
                                    mock_engine, seed, setup_env)

pytest.importorskip("fastapi")

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PLATFORM_MIGRATIONS = _ROOT / "migrations" / "platform"
_ROOT_MIGRATIONS = _ROOT / "migrations"
_BAD_SQL = ("CREATE TABLE r5_probe (x INTEGER);\n"
            "INSERT INTO no_such_table VALUES (1);\n")


# ── أدوات مشتركة · shared helpers ────────────────────────────────────────────
def _copy_migrations(src_dir: pathlib.Path, dest: pathlib.Path,
                     upto: int | None = None) -> pathlib.Path:
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(src_dir.glob("[0-9]*.sql")):
        if upto is None or int(f.name[:3]) <= upto:
            shutil.copy(str(f), str(dest / f.name))
    return dest


def _tables(path: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()


def _indexes(path: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'")}
    finally:
        conn.close()


def _versions(path: str, table: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute(f"SELECT version FROM {table}")}
    finally:
        conn.close()


def _columns(path: str, table: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _pragma(conn, name: str):
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def _count(sql: str, args: tuple = ()) -> int:
    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        return int(conn.execute(sql, args).fetchone()[0])
    finally:
        conn.close()


# ══════════════ DB-1 / TEST-10 — ترحيلاتٌ ذرّية لكل ملف ═════════════════════
def test_platform_migration_file_rolls_back_entirely_and_boot_survives(tmp_path, monkeypatch):
    """ملفٌ يفشل في جملته الثانية لا يترك جملتَه الأولى ملتزَمة، و`/platform` يُقلِع بعده."""
    from silk_platform import db as pdb
    d = _copy_migrations(_PLATFORM_MIGRATIONS, tmp_path / "mig")
    (d / "099_bad.sql").write_text(_BAD_SQL, encoding="utf-8")
    monkeypatch.setattr(pdb, "_MIGRATIONS_DIR", str(d))
    path = str(tmp_path / "p.db")
    with pytest.raises(sqlite3.OperationalError):
        pdb.apply_migrations(path)
    assert "r5_probe" not in _tables(path)              # الجملةُ الأولى لم تلتزم
    assert "099" not in _versions(path, "platform_migrations")
    os.remove(d / "099_bad.sql")
    assert pdb.apply_migrations(path) == []            # كلُّ ما قبلها مكتمل
    monkeypatch.setenv("SILK_PLATFORM_DB", path)
    monkeypatch.setenv("SILK_PLATFORM_SECRET", "fixed-test-secret-do-not-use-in-prod")
    monkeypatch.setenv("SILK_PLATFORM_STORAGE_DIR", str(tmp_path / "files"))
    assert client().get("/platform/pricing").status_code == 200


def test_platform_migration_crash_between_ddl_and_version_row_is_recoverable(tmp_path, monkeypatch):
    """تعطّلٌ بعد DDL الملفّ ٠١٣ وقبل صفّ نسخته — إعادةُ التطبيق تنجح بدل «duplicate column»."""
    from silk_platform import db as pdb
    d = _copy_migrations(_PLATFORM_MIGRATIONS, tmp_path / "mig", upto=12)
    monkeypatch.setattr(pdb, "_MIGRATIONS_DIR", str(d))
    path = str(tmp_path / "p.db")
    assert "012" in pdb.apply_migrations(path)
    _copy_migrations(_PLATFORM_MIGRATIONS, d)          # الآن الملفّات كلّها
    real_now = pdb.now_iso
    calls = {"n": 0}

    def crash_once():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("crash before the version row")
        return real_now()

    monkeypatch.setattr(pdb, "now_iso", crash_once)
    with pytest.raises(RuntimeError):
        pdb.apply_migrations(path)
    monkeypatch.setattr(pdb, "now_iso", real_now)
    applied = pdb.apply_migrations(path)
    assert "013" in applied and "019" in applied
    assert "language_chosen_at" in _columns(path, "accounts")


def test_platform_legacy_half_applied_alter_is_benign(tmp_path, monkeypatch):
    """قاعدةٌ تحمل عموداً من ترحيلٍ نصفيّ قديم — تطبيقُ الملفّ لا يتعثّر عليه."""
    from silk_platform import db as pdb
    d = _copy_migrations(_PLATFORM_MIGRATIONS, tmp_path / "mig", upto=12)
    monkeypatch.setattr(pdb, "_MIGRATIONS_DIR", str(d))
    path = str(tmp_path / "p.db")
    pdb.apply_migrations(path)
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE accounts ADD COLUMN language_preference TEXT NOT NULL "
                 "DEFAULT 'ar' CHECK (language_preference IN ('ar','en'))")
    conn.commit()
    conn.close()
    _copy_migrations(_PLATFORM_MIGRATIONS, d)
    applied = pdb.apply_migrations(path)
    assert "013" in applied
    assert {"language_preference", "language_chosen_at"} <= _columns(path, "accounts")


def test_store_migrate_is_atomic_per_file(tmp_path, monkeypatch):
    """مخزنُ الحقائق يتبع القاعدة نفسها (`silk_store.migrate`)."""
    import silk_store
    d = _copy_migrations(_ROOT_MIGRATIONS, tmp_path / "mig")
    (d / "099_bad.sql").write_text(_BAD_SQL, encoding="utf-8")
    monkeypatch.setattr(silk_store, "_MIGRATIONS_DIR", str(d))
    path = str(tmp_path / "store.db")
    monkeypatch.setenv("SILK_STORE_DB", path)
    with pytest.raises(sqlite3.OperationalError):
        silk_store.migrate()
    assert "r5_probe" not in _tables(path)
    assert "099" not in _versions(path, "schema_migrations")
    os.remove(d / "099_bad.sql")
    assert silk_store.migrate() == []


def test_statement_splitter_matches_executescript_on_real_migrations():
    """حارسُ التكافؤ: المقسِّم يُنتِج المخطّطَ نفسَه الذي ينتجه `executescript`."""
    from silk_sqlite import iter_statements
    files = (sorted(_PLATFORM_MIGRATIONS.glob("[0-9]*.sql"))
             + sorted(_ROOT_MIGRATIONS.glob("[0-9]*.sql")))
    assert files
    for group in (sorted(_PLATFORM_MIGRATIONS.glob("[0-9]*.sql")),
                  sorted(_ROOT_MIGRATIONS.glob("[0-9]*.sql"))):
        a, b = sqlite3.connect(":memory:"), sqlite3.connect(":memory:")
        for f in group:
            script = f.read_text(encoding="utf-8")
            for stmt in iter_statements(script):
                a.execute(stmt)
            b.executescript(script)
        sa = {r for r in a.execute("SELECT type, name, sql FROM sqlite_master")}
        sb = {r for r in b.execute("SELECT type, name, sql FROM sqlite_master")}
        assert sa == sb, group[0].parent


# ══════════════ DB-6 / CONC-6 — WAL ═════════════════════════════════════════
def test_every_store_connection_runs_in_wal_with_normal_sync(tmp_path, monkeypatch):
    """كلُّ موصِّلٍ يفتح القاعدة على WAL + synchronous=NORMAL — الكاتب لا يحجب القرّاء."""
    import silk_sqlite
    import silk_storage
    from silk_platform import db as pdb
    monkeypatch.delenv("SILK_SQLITE_JOURNAL_MODE", raising=False)
    for i, connector in enumerate((silk_sqlite.connect, pdb.connect,
                                   silk_storage._connect)):
        conn = connector(str(tmp_path / f"s{i}.db"))
        try:
            assert _pragma(conn, "journal_mode") == "wal", connector
            assert _pragma(conn, "synchronous") == 1, connector
        finally:
            conn.close()


def test_journal_mode_rollback_env_returns_to_delete(tmp_path, monkeypatch):
    import silk_sqlite
    path = str(tmp_path / "s.db")
    monkeypatch.delenv("SILK_SQLITE_JOURNAL_MODE", raising=False)
    silk_sqlite.connect(path).close()
    monkeypatch.setenv("SILK_SQLITE_JOURNAL_MODE", "delete")
    conn = silk_sqlite.connect(path)
    try:
        assert _pragma(conn, "journal_mode") == "delete"
    finally:
        conn.close()


# ══════════════ DB-7 — فهارس أنماط الاستعلام الفعلية ════════════════════════
def test_platform_indexes_exist_after_migrations(tmp_path):
    from silk_platform import db as pdb
    path = str(tmp_path / "p.db")
    assert "020" in pdb.apply_migrations(path)
    assert {"ix_sessions_expires", "ix_login_attempts_created",
            "ix_reset_tokens_expires", "ix_notifications_account_id",
            "ix_audit_action_created"} <= _indexes(path)


def test_engine_store_indexes_exist_after_init_db(tmp_path):
    import silk_storage
    path = str(tmp_path / "silk.db")
    silk_storage.init_db(path)
    assert {"idx_market_scores_analysis",
            "idx_analyses_status_updated"} <= _indexes(path)


def test_fact_store_collection_runs_index_exists(tmp_path, monkeypatch):
    import silk_store
    path = str(tmp_path / "store.db")
    monkeypatch.setenv("SILK_STORE_DB", path)
    silk_store.migrate()
    assert "idx_collection_runs_source_started" in _indexes(path)


# ══════════════ DB-11 — `init_db` يُحفَظ لكل مسار ═══════════════════════════
def test_init_db_is_memoized_per_path_force_reruns_and_survives_file_deletion(tmp_path, monkeypatch):
    import silk_storage as st
    opens = {"n": 0}
    real_open = st._open

    def counting_open(path):
        opens["n"] += 1
        return real_open(path)

    monkeypatch.setattr(st, "_open", counting_open)
    p = str(tmp_path / "silk.db")
    st.init_db(p)
    st.init_db(p)
    assert opens["n"] == 1
    st.init_db(p, force=True)
    assert opens["n"] == 2
    os.remove(p)
    st.init_db(p)                                      # الملفُّ غاب ⇒ يُعاد بناؤه
    assert opens["n"] == 3 and os.path.exists(p)


# ══════════════ DB-12 — طوابع UTC ودلوُ المصالحة ═══════════════════════════
def test_storage_stamps_are_utc_and_reconcile_bucket_holds_at_midnight(tmp_path, monkeypatch):
    """الساعة المحلّية 02:30 من الغد = 23:30 UTC اليوم — الطابعُ يتبع UTC فلا
    يُغادر دلوَ `silk_usage._today()` وتُصالَح الحجوز فعلاً."""
    import silk_storage as st
    import silk_usage

    class _FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            utc = datetime.datetime(2026, 9, 5, 23, 30, tzinfo=datetime.timezone.utc)
            return utc.astimezone(tz) if tz else datetime.datetime(2026, 9, 6, 2, 30)

    fake = types.SimpleNamespace(datetime=_FakeDT, timezone=datetime.timezone,
                                 timedelta=datetime.timedelta, date=datetime.date)
    monkeypatch.setattr(st, "datetime", fake)
    monkeypatch.setattr(silk_usage, "_today", lambda: "2026-09-05")
    rec: list = []
    monkeypatch.setattr(silk_usage, "reconcile_usd",
                        lambda reserved, actual, path=None, **kw:
                        rec.append((reserved, actual)) or True)
    db = str(tmp_path / "silk.db")
    aid = st.create_research_run("عسل", "GBR", None, {"product": "عسل"},
                                 path=db, market_name="المملكة المتحدة")
    row = st.get_research_run(aid, path=db)
    assert str(row["created_at"]).startswith("2026-09-05")
    assert str(row["created_at"]).endswith("+00:00")
    st.update_research_progress(aid, path=db, cost_usd_estimate=0.8)
    st.mark_research_failed(aid, "boom", path=db)
    st.reconcile_failed_run_usd(aid, path=db)
    assert len(rec) == 1, "الدلو لم يطابق — الطابعُ محلّيّ"
    assert "datetime.datetime.now()" not in (_ROOT / "silk_storage.py").read_text(
        encoding="utf-8")


# ══════════════ API-17 — لا تكرار في market_scores ══════════════════════════
def test_resaving_the_same_analysis_id_keeps_one_market_scores_row_per_market(tmp_path):
    import silk_storage as st
    db = str(tmp_path / "silk.db")
    aid = st.create_research_run("تمور", "ARE", "080410", {"product": "تمور"},
                                 path=db, market_name="الإمارات")
    result = {"product": "تمور", "hs_code": "080410",
              "markets": [{"country": c, "iso3": c[:3].upper(),
                           "total_score": 0.5, "confidence": 0.5}
                          for c in ("Alpha", "Beta", "Gamma")]}
    st.save_analysis(result, path=db, analysis_id=aid)
    st.save_analysis(result, path=db, analysis_id=aid)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM market_scores WHERE analysis_id = ?",
                            (aid,)).fetchone()[0] == 3
    finally:
        conn.close()


# ══════════════ DB-9 / DB-10 / TEST-8 / CONC-7 — النسخ والاسترجاع ═══════════
def _backup_env(tmp_path, monkeypatch) -> pathlib.Path:
    """منصّة مبذورة + صورةٌ مرفوعة + بقيّة المخازن غائبة + مجلد نسخ مؤقّت."""
    from silk_platform import db as pdb, storage
    p = tmp_path / "platform.db"
    monkeypatch.setenv("SILK_PLATFORM_DB", str(p))
    pdb.init_db(str(p), force=True)
    monkeypatch.setenv("SILK_PLATFORM_STORAGE_DIR", str(tmp_path / "files"))
    storage.write("1/a.png", b"\x89PNG-bytes")
    for var in ("SILK_DB", "SILK_STORE_DB", "SILK_USAGE_DB", "SILK_OPS_LOG_DB",
                "SILK_WATCHDOG_DB"):
        monkeypatch.setenv(var, str(tmp_path / f"absent-{var}.db"))
    dest = tmp_path / "backups"
    monkeypatch.setenv("SILK_BACKUP_DIR", str(dest))
    return dest


def _stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def test_backup_includes_uploads_and_restore_round_trips(tmp_path, monkeypatch):
    """صورُ المصانع داخل النسخة، و`restore()` يُعيد القاعدةَ والملفات بعد فحص السلامة."""
    import silk_backup
    dest = _backup_env(tmp_path, monkeypatch)
    m = silk_backup.run_backup()
    assert m["failures"] == []
    assert {"platform", "platform_files"} <= {f["name"] for f in m["files"]}
    out_db = tmp_path / "restored.db"
    r = silk_backup.restore("platform", _stamp(), str(out_db))
    assert r["ok"] and r["integrity"] == "ok"
    assert len(_versions(str(out_db), "platform_migrations")) >= 19
    out_dir = tmp_path / "restored_files"
    r2 = silk_backup.restore("platform_files", _stamp(), str(out_dir))
    assert r2["ok"]
    assert (out_dir / "1" / "a.png").read_bytes() == b"\x89PNG-bytes"
    assert not any(n.endswith("-wal") for n in os.listdir(dest))


def test_verify_backup_tool_passes_then_fails_on_a_corrupt_artifact(tmp_path, monkeypatch, capsys):
    import importlib.util
    import silk_backup
    dest = _backup_env(tmp_path, monkeypatch)
    silk_backup.run_backup()
    spec = importlib.util.spec_from_file_location(
        "verify_backup", str(_ROOT / "tools" / "verify_backup.py"))
    vb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vb)
    assert vb.main(["--dir", str(dest)]) == 0
    assert "platform_files" in capsys.readouterr().out
    with open(silk_backup.latest_backup("platform", str(dest)), "r+b") as fh:
        fh.truncate(100)
    assert vb.main(["--dir", str(dest)]) == 1


def test_backup_uses_shared_connector_paged_copy_and_single_file_artifact(tmp_path, monkeypatch):
    import silk_backup
    src = (_ROOT / "silk_backup.py").read_text(encoding="utf-8")
    assert "closing(silk_sqlite.connect(src" in src and "pages=" not in src
    dest = _backup_env(tmp_path, monkeypatch)
    silk_backup.run_backup()
    conn = sqlite3.connect(silk_backup.latest_backup("platform", str(dest)))
    try:
        assert _pragma(conn, "journal_mode") == "delete"
    finally:
        conn.close()


# ══════════════ DB-8 — الجامعون يغلقون اتصالاتهم ════════════════════════════
def test_collectors_use_the_closing_store_helper():
    src = (_ROOT / "silk_collectors.py").read_text(encoding="utf-8")
    assert "silk_store._open()" in src
    assert "with silk_store.connect() as conn" not in src
    hygiene = (_ROOT / "tests" / "test_sqlite_connection_hygiene.py").read_text(
        encoding="utf-8")
    assert '"silk_collectors.py"' in hygiene


# ══════════════ DB-3 — حذفُ دراسةٍ لها صفوفٌ من عهد الحملات ═════════════════
def test_delete_study_with_legacy_fk_rows_succeeds_and_clears_dangling_notifications(monkeypatch):
    from silk_platform import db as pdb
    from silk_platform.db import now_iso
    info = seed(monkeypatch)
    cl = client()
    ta = login(cl, info["factory_a"]["email"], info["factory_a"]["password"])
    aid = info["factory_a"]["account_id"]
    s = cl.post("/platform/studies", json={"product": "تمور"}, headers=hdr(ta)).json()
    conn = pdb.connect()
    try:
        now = now_iso()
        cur = conn.execute(
            "INSERT INTO comparison_funnels (owner_id, state, created_at, "
            "updated_at, selected_study_id) VALUES (?,?,?,?,?)",
            (aid, "compared", now, now, s["id"]))
        fid = cur.lastrowid
        conn.execute("INSERT INTO funnel_studies (funnel_id, study_id) VALUES (?,?)",
                     (fid, s["id"]))
        conn.execute("INSERT INTO drafts (owner_id, study_id, created_at, updated_at) "
                     "VALUES (?,?,?,?)", (aid, s["id"], now, now))
        conn.execute("INSERT INTO platform_notifications (account_id, kind, study_id, "
                     "title, body, created_at) VALUES (?,?,?,?,?,?)",
                     (aid, "study_completed", s["id"], "t", "b", now))
        conn.commit()
    finally:
        conn.close()
    r = cl.delete(f"/platform/studies/{s['id']}", headers=hdr(ta))
    assert r.status_code == 200, r.text
    assert _count("SELECT COUNT(*) FROM studies WHERE id = ?", (s["id"],)) == 0
    assert _count("SELECT COUNT(*) FROM funnel_studies WHERE study_id = ?", (s["id"],)) == 0
    assert _count("SELECT COUNT(*) FROM drafts WHERE owner_id = ? AND study_id IS NULL",
                  (aid,)) == 1
    assert _count("SELECT COUNT(*) FROM comparison_funnels WHERE id = ? "
                  "AND selected_study_id IS NULL", (fid,)) == 1
    assert _count("SELECT COUNT(*) FROM platform_notifications WHERE account_id = ? "
                  "AND study_id IS NULL AND title = 't'", (aid,)) == 1


# ══════════════ DB-5 — فوترةُ التخزين معاملةٌ واحدة ═════════════════════════
def test_storage_billing_check_and_post_are_one_transaction(monkeypatch):
    from silk_platform import db as pdb, jobs, wallet
    from silk_platform.db import now_iso
    setup_env(monkeypatch)
    f = make_factory("gold", "bill@f.local")
    conn = pdb.connect()
    try:
        conn.execute("INSERT INTO images (owner_id, filename, storage_key, mime_type, "
                     "size_bytes, uploaded_at) VALUES (?,?,?,?,?,?)",
                     (f["account_id"], "a.png", f"{f['account_id']}/a.png", "image/png",
                      1024, now_iso()))
        conn.commit()
    finally:
        conn.close()
    real_apply = wallet.apply_entry
    gate, started = threading.Event(), threading.Event()

    def slow_apply(conn, **kw):
        started.set()
        gate.wait(3)
        return real_apply(conn, **kw)

    monkeypatch.setattr(wallet, "apply_entry", slow_apply)

    def run():
        c = pdb.connect()
        try:
            jobs.run_storage_billing(c, period="2026-09")
        finally:
            c.close()

    t1 = threading.Thread(target=run)
    t1.start()
    assert started.wait(5)
    t2 = threading.Thread(target=run)
    t2.start()
    time.sleep(0.3)
    gate.set()
    t1.join(20)
    t2.join(20)
    assert _count("SELECT COUNT(*) FROM ledger_entries WHERE account_id = ? "
                  "AND operation_type = 'storage_charge'", (f["account_id"],)) == 1


# ══════════════ DB-13 — الأعمدة المسمّاة تُتحقَّق عند الكتابة ═══════════════
def test_enum_columns_are_validated_in_the_write_path(tmp_path, monkeypatch):
    import silk_storage as st
    from silk_platform import db as pdb, notifications, repository
    setup_env(monkeypatch)
    f = make_factory("gold", "enum@f.local")
    conn = pdb.connect()
    try:
        with pytest.raises(ValueError):
            repository.products(conn).create(f["account_id"],
                                             {"name": "x", "hs_source": "bogus"})
        with pytest.raises(ValueError):
            notifications.record(conn, account_id=f["account_id"], kind="bogus",
                                 title="t")
    finally:
        conn.close()
    with pytest.raises(ValueError):
        st.update_research_status(1, "bogus", path=str(tmp_path / "s.db"))


# ══════════════ DB-16 / AUTH-20 — الاحتفاظ ═════════════════════════════════
def test_session_cleanup_prunes_read_notifications_and_scrubs_checkout_pii_within_env_windows(monkeypatch):
    from silk_platform import db as pdb, scheduler
    setup_env(monkeypatch)
    f = make_factory("gold", "ret@f.local")
    aid = f["account_id"]
    old = (datetime.datetime.now(datetime.timezone.utc)
           - datetime.timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def seed_rows():
        conn = pdb.connect()
        try:
            conn.execute("DELETE FROM platform_notifications WHERE account_id = ?", (aid,))
            for title, created, read in (("old-read", old, old), ("old-unread", old, None),
                                         ("new-read", fresh, fresh)):
                conn.execute("INSERT INTO platform_notifications (account_id, kind, "
                             "title, body, created_at, read_at) VALUES (?,?,?,?,?,?)",
                             (aid, "study_completed", title, "b", created, read))
            conn.execute("INSERT INTO audit_log (account_id, action, resource_type, "
                         "changes, created_at) VALUES (?,?,?,?,?)",
                         (None, "checkout_requested", "checkout",
                          '{"email": "lead@x.com", "plan": "gold"}', old))
            conn.commit()
        finally:
            conn.close()

    seed_rows()
    monkeypatch.setenv("SILK_PLATFORM_NOTIF_RETENTION_DAYS", "30")
    monkeypatch.setenv("SILK_PLATFORM_CHECKOUT_PII_DAYS", "90")
    scheduler.run_job("session_cleanup")
    titles = {r[0] for r in pdb.connect().execute(
        "SELECT title FROM platform_notifications WHERE account_id = ?", (aid,))}
    assert titles == {"old-unread", "new-read"}
    assert _count("SELECT COUNT(*) FROM audit_log WHERE action = 'checkout_requested' "
                  "AND changes LIKE '%lead@x.com%'") == 0
    monkeypatch.delenv("SILK_PLATFORM_NOTIF_RETENTION_DAYS", raising=False)
    seed_rows()
    scheduler.run_job("session_cleanup")
    assert _count("SELECT COUNT(*) FROM platform_notifications WHERE account_id = ?",
                  (aid,)) == 3                      # مطفأٌ افتراضاً ⇒ لا حذف


# ══════════════ ENG-12 — كنّاسٌ واحد ════════════════════════════════════════
def test_scheduler_loop_owns_no_second_sweeper(monkeypatch):
    from silk_platform import engine_bridge, scheduler
    setup_env(monkeypatch)
    assert "sweep_orphans" not in inspect.getsource(scheduler.start)
    called: list = []
    monkeypatch.setattr(engine_bridge, "sweep_orphans", lambda conn: called.append(1))
    scheduler._scheduler_tick({})
    assert called == []


# ══════════════ ENG-13 — لا `run_token` للمستأجر ═══════════════════════════
def test_tenant_study_payload_has_no_run_token(monkeypatch):
    import silk_platform.engine_bridge as eb
    seed(monkeypatch)
    cl = client()
    f = make_factory("gold", "tok@f.local")
    tok = login(cl, f["email"], f["password"])
    mock_engine(monkeypatch)
    s = cl.post("/platform/studies", json={"product": "تمور", "market_pref": "ARE"},
                headers=hdr(tok)).json()
    assert cl.post(f"/platform/studies/{s['id']}/launch", headers=hdr(tok)).status_code == 200
    assert eb.wait_idle()
    one = cl.get(f"/platform/studies/{s['id']}", headers=hdr(tok)).json()
    lst = cl.get("/platform/studies", headers=hdr(tok)).json()["studies"]
    assert "run_token" not in one
    assert all("run_token" not in x for x in lst)


# ══════════════ CONC-9 / CONC-11 — خيوطٌ ونموٌّ محدودان ════════════════════
def test_gmaps_async_executor_is_shut_down_after_submit(monkeypatch):
    import silk_gmaps
    src = (_ROOT / "silk_gmaps.py").read_text(encoding="utf-8")
    assert src.count("shutdown(wait=False)") >= 2
    monkeypatch.setattr(silk_gmaps, "enabled", lambda: True)
    monkeypatch.setattr(silk_gmaps, "localized_queries", lambda p, m: ["q"])
    monkeypatch.setattr(silk_gmaps, "cache_get", lambda iso3, q: [{"name": "x"}])
    before = {t.ident for t in threading.enumerate()}
    fut = silk_gmaps.submit_scrape_async("x", types.SimpleNamespace(iso3="ARE"))
    assert fut.result(2)
    time.sleep(0.5)
    leftover = [t for t in threading.enumerate()
                if t.ident not in before and t.name.startswith("ThreadPoolExecutor")]
    assert leftover == []


def test_word_token_regex_cache_is_bounded():
    import silk_narrative as sn
    for i in range(5000):
        sn._replace_token("a b", f"tok{i}", "x")
    assert sn._word_rx.cache_info().currsize <= 4096
