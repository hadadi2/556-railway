"""اختبارات PR-2 — بوّابة الاستحقاقات، إدارة الطبقات، المجدول.

(«المقاعد» في اسم الملف أثرٌ تاريخي: حُذفت نهائياً بقرار المالك 2026-08-19 —
حسابٌ واحد لكل مصنع — وحارسُ حذفها `tests/test_platform_seats_deletion_guard.py`.
الاسم يبقى كما هو كي لا تنكسر مراسٍ توثيقية تشير إليه.)

هرمتية بالكامل: قاعدة منصّة معزولة لكل اختبار، بلا شبكة وبلا مفاتيح.
Hermetic: isolated platform DB per test, no network, no keys.

التغطية مقصودة **في الاتجاهين** لكل بوّابة: تُمنع حين يجب، وتَسمح حين يجب —
بوّابة ترفض دائماً تجتاز اختبار «رفَضَت» وهي معطّلة فعلياً.
"""
from __future__ import annotations

import datetime

import pytest

from tests.platform_helpers import (client, hdr, login, make_factory,
                                    make_product_study, mock_engine, seed)


# ══════════════════════ بوّابة الميزات · feature gate ═══════════════════════
def test_feature_gate_allows_and_denies_per_tier():
    """البوّابة تفتح للطبقة المستحقّة وتُغلق لغيرها — both directions."""
    from silk_platform import entitlements
    # (ميزة القمع حُذفت مع التنقيب — قرار مالك 2026-08-17.)
    # بعد حذف البلاتينية: التصدير/العلامة البيضاء/الـAPI في الذهبية العليا.
    for feat in ("api_access", "white_label", "export"):
        assert entitlements.has_feature("gold", feat) is True
        assert entitlements.has_feature("silver", feat) is False


def test_require_feature_raises_with_upgrade_prompt():
    """المنع يحمل دعوة ترقية قابلة للقراءة آلياً — §2 'show upgrade prompt'."""
    from silk_platform import entitlements
    with pytest.raises(entitlements.TierGateError) as exc:
        entitlements.require_feature("silver", "export")
    detail = exc.value.as_detail()
    assert detail["error"] == "tier_gate"
    assert detail["upgrade"] is True
    assert detail["feature"] == "export"
    assert detail["tier"] == "silver"
    # الطبقات التي تمنحها فعلاً — لا رسالة عامّة.
    assert set(detail["required_tiers"]) == {"gold"}


def test_require_feature_passes_silently_when_granted():
    """الطبقة المستحقّة لا تُمنَع — the gate is not a blanket denial."""
    from silk_platform import entitlements
    entitlements.require_feature("gold", "export")      # must not raise
    entitlements.require_feature("gold", "api_access")


def test_unknown_feature_raises_instead_of_silently_denying():
    """ميزة مجهولة خطأٌ صريح — a typo must not silently gate everyone out."""
    from silk_platform import entitlements
    with pytest.raises(ValueError):
        entitlements.has_feature("gold", "exports")     # typo


# (حُذفت أقسام «المقاعد» و«تصعيد الصلاحية» و«عزل المستخدمين» مع حذف
#  المستخدمين الفرعيين نهائياً — قرار المالك 2026-08-19: حسابٌ واحد لكل
#  مصنع. لا يبقى مسارٌ يقبل `role` من الجسم أصلاً، وحارسُ الحذف
#  tests/test_platform_seats_deletion_guard.py يمنع عودته — وفيه اختبارٌ
#  مضادّ يقيس أن دورة الدخول والهويّة بقيت سليمة.)

# ═══════════════════ لقطة الاستحقاقات · entitlements snapshot ═══════════════
def test_entitlements_endpoint_reports_limits_and_usage(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "ent-gold@example.com")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    body = cl.get("/platform/entitlements", headers=hdr(tok)).json()
    assert body["tier"] == "gold"
    assert body["studies_limit"] == 6 and body["studies_period"] == "month"
    assert body["dashboard"] == "full"
    assert body["export"] is True and body["api_access"] is True


def test_basic_entitlements_are_measured_on_the_lifetime_counter(monkeypatch):
    """Basic تُقاس على عدّاد مدى الحياة لا الشهري — no contradictory pair."""
    seed(monkeypatch)
    f = make_factory("basic", "ent-basic@example.com")
    mock_engine(monkeypatch)
    sid = make_product_study(f["account_id"], f["user_id"])
    cl = client()
    tok = login(cl, f["email"], f["password"])
    body = cl.get("/platform/entitlements", headers=hdr(tok)).json()
    assert body["studies_period"] == "lifetime"
    assert body["studies_limit"] == 1 and body["studies_used"] == 0
    cl.post(f"/platform/studies/{sid}/launch", headers=hdr(tok))
    body = cl.get("/platform/entitlements", headers=hdr(tok)).json()
    assert body["studies_used"] == 1


def test_stale_month_counter_reads_as_zero_not_as_exhausted(monkeypatch):
    """عدّاد شهرٍ مضى يُقرأ صفراً — لا «2/2 ممنوع» بينما الإطلاق سينجح.

    `reserve_launch` يصفّر الفترة **كسولاً**، فقراءةٌ خام لعدّاد يونيو في يوليو
    كانت ستعرض على العميل حدّاً مستهلَكاً يخالف ما يسمح به النظام فعلاً —
    رقمان متعارضان من نفس القاعدة. القراءة هنا تطبّق قاعدة الفترة بلا كتابة.
    """
    seed(monkeypatch)
    f = make_factory("silver", "stale-period@example.com")
    from silk_platform import db as pdb, entitlements
    conn = pdb.connect()
    try:
        # عدّاد ممتلئ موسوم بفترة قديمة · a full counter stamped with an old period.
        conn.execute("UPDATE accounts SET current_month_study_count = 2, "
                     "quota_period = '2020-01' WHERE id = ?", (f["account_id"],))
        conn.commit()
        snap = entitlements.snapshot(conn, f["account_id"])
    finally:
        conn.close()
    assert snap.studies_used == 0, "a stale period must not read as exhausted"
    assert snap.studies_limit == 2


def test_current_period_counter_is_reported_as_is(monkeypatch):
    """عدّاد الفترة الجارية يُعرَض كما هو — the stale-fix must not zero live usage."""
    seed(monkeypatch)
    f = make_factory("silver", "live-period@example.com")
    from silk_platform import db as pdb, entitlements, quota
    conn = pdb.connect()
    try:
        conn.execute("UPDATE accounts SET current_month_study_count = 1, "
                     "quota_period = ? WHERE id = ?",
                     (quota.current_period(), f["account_id"]))
        conn.commit()
        snap = entitlements.snapshot(conn, f["account_id"])
    finally:
        conn.close()
    assert snap.studies_used == 1


# ══════════════════ إدارة الطبقات · admin tier management ═══════════════════
def test_admin_can_upgrade_a_factory_tier_and_it_is_audited(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("silver", "tier-up@example.com")
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    r = cl.post(f"/platform/admin/accounts/{f['account_id']}/tier",
                headers=hdr(tok), json={"tier": "gold"})
    assert r.status_code == 200, r.text
    assert r.json()["tier"] == "gold" and r.json()["previous_tier"] == "silver"
    from silk_platform import audit, db as pdb
    conn = pdb.connect()
    try:
        rows = audit.search(conn, account_id=f["account_id"],
                            action="account_tier_changed")
    finally:
        conn.close()
    assert len(rows) == 1


def test_tier_change_rejects_unknown_tier_and_non_factory_accounts(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("silver", "tier-bad@example.com")
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    r = cl.post(f"/platform/admin/accounts/{f['account_id']}/tier",
                headers=hdr(admin), json={"tier": "diamond"})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "unknown_tier"
    # حساب سِلك نفسه ليس مشتركاً · the silk account has no subscription.
    r = cl.post(f"/platform/admin/accounts/{info['vault_account_id']}/tier",
                headers=hdr(admin), json={"tier": "gold"})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "not_a_factory_account"
    r = cl.post("/platform/admin/accounts/999999/tier",
                headers=hdr(admin), json={"tier": "gold"})
    assert r.status_code == 404


def test_factory_cannot_change_its_own_tier(monkeypatch):
    """المصنع لا يرقّي نفسه — the tier is an admin-only, billing-bearing field."""
    seed(monkeypatch)
    f = make_factory("basic", "self-upgrade@example.com")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    r = cl.post(f"/platform/admin/accounts/{f['account_id']}/tier",
                headers=hdr(tok), json={"tier": "gold"})
    assert r.status_code == 403
    assert cl.get("/platform/entitlements", headers=hdr(tok)).json()["tier"] == "basic"


def test_tier_change_does_not_reset_usage_counters(monkeypatch):
    """الترقية ترفع السقف لا الاستهلاك — counters measure what was actually used."""
    info = seed(monkeypatch)
    f = make_factory("silver", "tier-counter@example.com")
    from silk_platform import db as pdb, quota
    conn = pdb.connect()
    try:
        conn.execute("UPDATE accounts SET current_month_study_count = 2, "
                     "quota_period = ? WHERE id = ?",
                     (quota.current_period(), f["account_id"]))
        conn.commit()
    finally:
        conn.close()
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    cl.post(f"/platform/admin/accounts/{f['account_id']}/tier",
            headers=hdr(admin), json={"tier": "gold"})
    owner = login(cl, f["email"], f["password"])
    body = cl.get("/platform/entitlements", headers=hdr(owner)).json()
    assert body["studies_limit"] == 6 and body["studies_used"] == 2


def test_admin_accounts_listing_shows_tier_and_quota(monkeypatch):
    info = seed(monkeypatch)
    f = make_factory("gold", "admin-list@example.com")
    cl = client()
    admin = login(cl, info["admin"]["email"], info["admin"]["password"])
    rows = cl.get("/platform/admin/accounts", headers=hdr(admin)).json()["accounts"]
    mine = [r for r in rows if r["id"] == f["account_id"]]
    assert len(mine) == 1
    assert mine[0]["tier"] == "gold"
    # حقول المقاعد ذهبت مع حذفها — لا يجوز أن تعود صامتةً في حمولة الأدمِن.
    assert "seats_limit" not in mine[0] and "seats_used" not in mine[0]
    # لا حسابات سِلك/الخزنة في القائمة · factories only.
    assert all(r["id"] != info["vault_account_id"] for r in rows)


def test_factory_cannot_list_accounts(monkeypatch):
    seed(monkeypatch)
    f = make_factory("gold", "no-list@example.com")
    cl = client()
    tok = login(cl, f["email"], f["password"])
    assert cl.get("/platform/admin/accounts", headers=hdr(tok)).status_code == 403


# ══════════════════════════ المجدول · scheduler ═════════════════════════════
def _utc(y, m, d, h):
    return datetime.datetime(y, m, d, h, tzinfo=datetime.timezone.utc)


@pytest.fixture(autouse=False)
def _billing_scheduled(monkeypatch):
    """P3 (BIZ-6): فوترةُ التخزين لم تعد مجدولةً بلا صمّام. هذه الاختباراتُ تقيس
    **المواعيدَ والخمول** لا الصمّام، فتُشغَّل به مرفوعاً؛ والصمّامُ نفسُه مقفولٌ في
    `tests/test_audit_2026_09_01_p3.py::test_storage_billing_is_not_scheduled_unless_opted_in`."""
    monkeypatch.setenv("SILK_PLATFORM_STORAGE_BILLING", "1")


def test_due_jobs_respects_day_and_hour(_billing_scheduled):
    from silk_platform import scheduler
    # أوّل الشهر 00:xx: التصفير مستحقّ، والفوترة (01:00) لم تحن بعد.
    assert scheduler.due_jobs(_utc(2026, 8, 1, 0), {}) == ["monthly_quota_reset"]
    due = scheduler.due_jobs(_utc(2026, 8, 1, 1), {})
    assert set(due) == {"monthly_quota_reset", "storage_billing"}
    # يومية الجلسات تستحقّ من 02:00 · daily job due from its hour onward.
    assert "session_cleanup" in scheduler.due_jobs(_utc(2026, 8, 2, 2), {})
    assert "session_cleanup" not in scheduler.due_jobs(_utc(2026, 8, 2, 1), {})


def test_due_jobs_is_idempotent_within_a_slot(_billing_scheduled):
    """المهمّة المنفَّذة في فتحتها لا تُعاد — the slot id is the dedupe key."""
    from silk_platform import scheduler
    now = _utc(2026, 8, 1, 3)
    last = {"monthly_quota_reset": "2026-08", "storage_billing": "2026-08",
            "session_cleanup": "2026-08-01"}
    assert scheduler.due_jobs(now, last) == []
    # شهر جديد ⇒ الشهريّتان تستحقّان مرّة أخرى.
    assert set(scheduler.due_jobs(_utc(2026, 9, 1, 3), last)) == {
        "monthly_quota_reset", "storage_billing", "session_cleanup"}


def test_monthly_jobs_catch_up_after_downtime(_billing_scheduled):
    """مهمّة شهرية فاتت لأن العملية كانت متوقّفة تُنفَّذ لاحقاً في نفس الشهر.

    بلا اللحاق تُسقَط فوترة تخزين شهرٍ كامل صمتاً لو كانت الحاوية متوقّفة يوم ١
    — والدفتر غير قابل للتعديل فلا تُصحَّح لاحقاً.
    """
    from silk_platform import scheduler
    due = scheduler.due_jobs(_utc(2026, 8, 17, 9), {})    # منتصف الشهر
    assert "monthly_quota_reset" in due and "storage_billing" in due


def test_scheduler_does_not_start_unless_explicitly_enabled(monkeypatch):
    """بلا `SILK_PLATFORM_SCHEDULER=1` لا خيط — tests never bill or reset silently."""
    from silk_platform import scheduler
    monkeypatch.delenv("SILK_PLATFORM_SCHEDULER", raising=False)
    assert scheduler.start() is None


def test_run_due_executes_real_jobs_and_marks_the_slot(monkeypatch):
    """تشغيلة فعلية: تنظيف الجلسات يعمل ويُوسَم فلا يُعاد في نفس الفتحة."""
    seed(monkeypatch)
    from silk_platform import scheduler
    last: dict[str, str] = {}
    now = _utc(2026, 8, 5, 3)          # يومية فقط (ليس أوّل الشهر)
    out = scheduler.run_due(now=now, last_run=last)
    assert "session_cleanup" in out
    assert isinstance(out["session_cleanup"], dict)
    assert last["session_cleanup"] == "2026-08-05"
    assert scheduler.run_due(now=now, last_run=last) == {}   # لا تكرار


def test_a_failing_job_is_recorded_and_retried_next_pass(monkeypatch):
    """فشل مهمّة لا يوسمها منفَّذة — so the next pass retries instead of skipping."""
    seed(monkeypatch)
    from silk_platform import scheduler
    monkeypatch.setattr(scheduler, "run_job",
                        lambda name: (_ for _ in ()).throw(RuntimeError("boom")))
    last: dict[str, str] = {}
    out = scheduler.run_due(now=_utc(2026, 8, 5, 3), last_run=last)
    assert "failed: boom" in str(out["session_cleanup"])
    assert "session_cleanup" not in last          # لم تُوسَم ⇒ ستُعاد


def test_unknown_job_name_raises():
    from silk_platform import scheduler
    with pytest.raises(ValueError):
        scheduler.run_job("no_such_job")
