"""أقفال P3 — التنظيف (التدقيق الجنائي 2026-09-01، المرحلة الأخيرة).

لماذا هذا الملف: فوترةُ التخزين مجدولةٌ افتراضياً رغم أنّ الفوترةَ قرارُ مالكٍ مؤجَّل
(BIZ-6)؛ وطلبُ الاشتراك المكرَّر يكتب قيدَ تدقيقٍ ثانياً فيقرأ الأدمِن طلبين حيث طلبٌ
واحد (BIZ-7)؛ ورمزُ منتجٍ تغيّر بعد إطلاق دراسته لا يُقال (BIZ-10)؛ و«علّم الكلّ
مقروءاً» يمسح إشعاراتٍ وصلت **بعد** فتح القائمة (BIZ-11)؛ والبذرُ يزرع مصنعَين وهميّين
ورأسَ مالٍ خياليّ في أيّ قاعدةٍ تُبذَر (BIZ-12)؛ ولا مسارَ لإعادة تسمية حسابٍ (BIZ-13)؛
و`market_known` يقبل عند تعذّر المرجع (BIZ-14)؛ وشيفرةٌ ووثائقُ ميتة تتناقض مع الواقع
(DEBT/DOC/GIT).

هرمتي: قواعد مؤقّتة، لا شبكة. Hermetic only.
"""
from __future__ import annotations

import ast
import datetime
import os
import pathlib
import re
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.platform_helpers import (client, hdr, login, make_factory,  # noqa: E402
                                    make_product_study, seed, setup_env)

pytest.importorskip("fastapi")

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _pconn():
    from silk_platform import db as pdb
    return pdb.connect()


# ══════════════ BIZ-6 — فوترةُ التخزين لا تُجدوَل بلا قرارٍ صريح ═══════════════════
def test_storage_billing_is_not_scheduled_unless_opted_in(monkeypatch):
    from silk_platform import scheduler
    monkeypatch.delenv("SILK_PLATFORM_STORAGE_BILLING", raising=False)
    assert "storage_billing" not in scheduler.job_schedule(), \
        "الفوترةُ مجدولةٌ بلا قرارِ مالك"
    monkeypatch.setenv("SILK_PLATFORM_STORAGE_BILLING", "1")
    assert "storage_billing" in scheduler.job_schedule()
    assert callable(getattr(scheduler, "run_storage_billing", None)) or \
        "storage_billing" in _read("silk_platform/scheduler.py")


# ══════════════ BIZ-7 — طلبُ اشتراكٍ مكرَّر لا يُضاعف سجلَّ التدقيق ═══════════════
def test_a_duplicate_checkout_is_recorded_once(monkeypatch):
    seed(monkeypatch)
    monkeypatch.setenv("SILK_PLATFORM_CHECKOUT_DEDUPE_MIN", "1440")
    cl = client()
    body = {"plan": "gold", "billing_cycle": "monthly", "email": "buyer@f.local"}
    first = cl.post("/platform/billing/checkout", json=body)
    assert first.status_code == 200, first.text
    second = cl.post("/platform/billing/checkout", json=body)
    assert second.status_code == 200, second.text
    assert second.json().get("duplicate") is True, second.json()
    conn = _pconn()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM audit_log "
                         "WHERE action = 'checkout_requested'").fetchone()["c"]
    finally:
        conn.close()
    assert n == 1, f"قيودُ تدقيقٍ مكرّرة: {n}"


# ══════════════ BIZ-10 — رمزُ المنتج تغيّر بعد الإطلاق: يُقال ═════════════════════
def test_a_changed_product_code_is_declared_on_the_study_row(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "biz10@f.local")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    prod = cl.post("/platform/products", json={"name": "تمور", "hs_code": "080410"},
                   headers=hdr(tok)).json()
    st = cl.post("/platform/studies", json={"product": "تمور", "hs_code": "080410",
                                            "product_id": prod["id"]},
                 headers=hdr(tok))
    assert st.status_code in (200, 201), st.text
    sid = st.json()["id"]
    r = cl.patch(f"/platform/products/{prod['id']}", json={"hs_code": "080420"},
                 headers=hdr(tok))
    assert r.status_code == 200, r.text
    row = cl.get(f"/platform/studies/{sid}", headers=hdr(tok)).json()
    assert row.get("product_code_changed") is True, row
    page = _read("web/platform.html")
    assert "product_code_changed" in page and "رمز المنتج تغيّر" in page


# ══════════════ BIZ-11 — «علّم الكلّ» لا يبتلع ما وصل بعد العرض ═══════════════════
def test_mark_all_read_uses_a_watermark_not_a_blanket(monkeypatch):
    from silk_platform import notifications
    setup_env(monkeypatch)
    f = make_factory("gold", "biz11@f.local")
    conn = _pconn()
    try:
        for i in range(3):
            notifications.record(conn, account_id=f["account_id"], kind="study_completed",
                                 title=f"قديم {i}", body="")
        seen_max = conn.execute("SELECT MAX(id) m FROM platform_notifications "
                                "WHERE account_id = ?", (f["account_id"],)).fetchone()["m"]
        notifications.record(conn, account_id=f["account_id"], kind="study_completed",
                             title="وصل بعد العرض", body="")
        conn.commit()
        marked = notifications.mark_read(conn, f["account_id"], up_to_id=seen_max)
        assert marked == 3, marked
        unread = conn.execute(
            "SELECT COUNT(*) c FROM platform_notifications "
            "WHERE account_id = ? AND read_at IS NULL", (f["account_id"],)).fetchone()["c"]
        assert unread == 1, "الإشعارُ الذي وصل بعد العرض عُلِّم مقروءاً"
    finally:
        conn.close()


# ══════════════ BIZ-12 — لا مصانعَ وهمية ولا رأسَ مالٍ خياليّ في الإنتاج ═══════════
def test_seeding_under_a_production_signal_creates_no_demo_data(monkeypatch, tmp_path):
    from silk_platform import db as pdb, seed as pseed
    monkeypatch.setenv("SILK_PLATFORM_DB", str(tmp_path / "p.db"))
    monkeypatch.setenv("SILK_PLATFORM_SECRET", "s" * 40)
    monkeypatch.setenv("SILK_PLATFORM_REQUIRE_SECRET", "1")      # إشارةُ إنتاج
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "Seed-Admin-Pass-2026!")
    monkeypatch.delenv("SILK_SEED_DEMO_FACTORIES", raising=False)
    pdb.init_db(str(tmp_path / "p.db"), force=True)
    conn = pdb.connect()
    try:
        pseed.seed(conn)
        rows = [dict(r) for r in conn.execute(
            "SELECT name, kind, is_vault FROM accounts").fetchall()]
        ledger = conn.execute("SELECT COUNT(*) c FROM ledger_entries").fetchone()["c"]
    finally:
        conn.close()
    assert not [r for r in rows if r["kind"] == "factory"], rows
    assert ledger == 0, f"رأسُ مالٍ خياليّ قُيِّد في الإنتاج: {ledger}"
    assert [r for r in rows if r["is_vault"]], "حسابُ الخزنة نفسُه يجب أن يبقى"


# ══════════════ BIZ-13 — إعادةُ تسمية حساب (مسار + تدقيق + زر) ═══════════════════
def test_an_admin_can_rename_an_account_and_it_is_audited(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("gold", "biz13@f.local")
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    r = cl.patch(f"/platform/admin/accounts/{f['account_id']}",
                 json={"name": "مصنع التمور الجديد"}, headers=hdr(tok))
    assert r.status_code == 200, r.text
    conn = _pconn()
    try:
        name = conn.execute("SELECT name FROM accounts WHERE id = ?",
                            (f["account_id"],)).fetchone()["name"]
        n = conn.execute("SELECT COUNT(*) c FROM audit_log "
                         "WHERE action = 'account_renamed'").fetchone()["c"]
    finally:
        conn.close()
    assert name == "مصنع التمور الجديد", name
    assert n == 1, n
    assert "إعادة تسمية" in _read("web/platform.html")


# ══════════════ BIZ-14 — بوّابةُ السوق تفشل مغلقةً ═══════════════════════════════
def test_market_known_fails_closed_when_the_reference_is_unavailable(monkeypatch):
    from silk_platform import engine_bridge
    with patch.dict(sys.modules, {"silk_market_ranker": None}):
        assert engine_bridge.market_known("ZZZ") is False, \
            "المرجعُ متعذّر ⇒ قبولٌ متسامح (كان يمرّر سوقاً مجهولة)"


# ══════════════ DEBT — لا شيفرةَ ميتة ولا استيرادٌ زائد ═══════════════════════════
def test_the_dead_store_readers_and_tools_are_gone():
    store = _read("silk_store.py")
    for dead in ("def get_analysis", "def list_analyses"):
        assert dead not in store, f"{dead} ما زالت في silk_store"
    assert not (_ROOT / "tools" / "fetch_hs_codes.py").exists()
    assert not (_ROOT / "netlify.toml").exists()
    assert "netlify" not in _read("README.md").lower()


def test_the_platform_api_has_no_unused_imports():
    tree = ast.parse(_read("silk_platform/api.py"))
    src = _read("silk_platform/api.py")
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.col_offset == 0:
            for a in node.names:
                imported.add(a.asname or a.name)
    body = src.split("\n", 40)[-1] if False else src
    unused = [n for n in sorted(imported)
              if len(re.findall(rf"\b{re.escape(n)}\b", body)) <= 1]
    assert not unused, f"استيراداتٌ غيرُ مستعمَلة: {unused}"


def test_declared_runtime_dependencies_are_pinned():
    req = _read("requirements.txt")
    assert re.search(r"^pydantic==", req, re.M), "pydantic تُستعمَل ولا تُعلَن"


def test_env_example_has_no_variable_the_code_never_reads():
    """DEBT-8 — الفحصُ العكسيّ: كلُّ `SILK_*` في `.env.example` تقرؤه الشيفرةُ أو له
    سببٌ مكتوب في قائمة الاستثناء (وثيقةٌ تعِد بصمّامٍ غير موجود أسوأُ من صمتٍ)."""
    guard = _read("tests/test_env_documented.py")
    assert "def test_every_documented_env_var_is_read_or_exempt" in guard
    assert "_DOC_ONLY" in guard


# ══════════════ رُتبة ٣ — إعادةُ التسمية تُنقَر في متصفّحٍ حقيقيّ ═══════════════════
def test_rung3_platform_flow_renames_an_account():
    """BIZ-13 مسارٌ بشريّ لا نقطةُ نهاية: النقرُ يفتح النافذة، والجدولُ يعرض الاسمَ
    الجديد بعده — رسالةٌ خضراء فوق صفٍّ لم يتغيّر ليست تصحيحاً."""
    flow = _read("tests/e2e/platform_flow.cjs")
    assert 'ok("admin_rename_account")' in flow
    assert 'rowAct("rename")' in flow and '[name="acctname"]' in flow


# ══════════════ DOC — الوثائقُ لا تَعِد بما لا وجود له ═══════════════════════════
def test_docs_do_not_promise_deleted_or_stale_facts():
    claude = _read("CLAUDE.md")
    assert "٧٧+ درساً" not in claude and "77+ lessons" not in claude
    assert "e2e-live-shape" in claude
    assert "docs/PLATFORM_ROADMAP.md" in claude
    readme = _read("README.md")
    assert "SILK_DATA_DIR=/data" in readme
    assert "SILK_REQUIRE_PERSISTENT_DATA_DIR" in readme
    for gone in ("render.yaml", "silk_snapshot"):
        assert gone not in readme, gone


def test_the_lessons_ledger_count_in_the_docs_matches_the_ledger():
    rows = re.findall(r"^\| (\d+) \|", _read("docs/LESSONS.md"), re.M)
    last = max(int(r) for r in rows)
    assert last >= 227, last
    claude = _read("CLAUDE.md")
    m = re.search(r"(\d{3})\+? درساً", claude)
    assert m, "CLAUDE.md بلا عدّ دروسٍ مقروء"
    assert int(m.group(1)) <= last, (m.group(1), last)
