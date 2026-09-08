"""الحصص والطبقات — subscription quota enforcement.

- العدّاد يزيد **فقط** عند انتقال draft→in_progress (أوّل بريد يُصفّ)، لا عند
  إنشاء/تحرير المسودّة.
- Basic: دراسة واحدة مدى الحياة (لا تُصفَّر أبداً). البقية: عدّاد شهري.
- إعادة التصفير الشهرية: أوّل الشهر 00:00 UTC، تصفّر كل الطبقات عدا Basic.
- تجاوز الحصّة عند الإطلاق: امنع + سجّل تدقيقاً (الواجهة تعرض دعوة ترقية).

The counter increments only on launch (first email queued), never on draft edit.
"""
from __future__ import annotations

import dataclasses
import datetime
import sqlite3

from . import audit
from .db import now_iso
from . import tier_config
from .models import Tier, tier_limits


def current_period(at: datetime.datetime | None = None) -> str:
    """الشهر الحالي بصيغة 'YYYY-MM' UTC — the quota period key."""
    dt = at or datetime.datetime.now(datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m")


@dataclasses.dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str = ""          # كود سبب المنع · machine-readable reason code
    limit: int = 0
    used: int = 0
    tier: str = ""
    # حصّة المستخدم (قرار مالك 2026-08-17) — 0 في `user_limit` = بلا حدّ.
    user_limit: int = 0
    user_used: int = 0


def storage_cap_bytes(tier: str | Tier) -> int:
    """سقفُ التخزين التجميعي لهذه الطبقة بالبايت — tier default or env override.

    R4.2 (تدقيق 2026-09-01، API-2؛ قرار المالك 2026-09-02). التجاوزُ بالبيئة
    بالميغابايت (`SILK_PLATFORM_STORAGE_CAP_MB_{TIER}`) كي يُشدّ أو يُرخى على
    نشرٍ بعينه بلا إصدار. قيمةٌ غير صالحة = افتراضُ الطبقة (لا سقفَ مُخترَع،
    ولا انفتاحٌ صامت).
    """
    import os
    t = tier if isinstance(tier, Tier) else Tier(str(tier))
    raw = os.environ.get(
        f"SILK_PLATFORM_STORAGE_CAP_MB_{t.value.upper()}", "").strip()
    if raw:
        try:
            mb = int(raw)
            if mb > 0:
                return mb * 1024 * 1024
        except ValueError:
            pass
    return int(tier_limits(t).storage_bytes)


def storage_used_bytes(conn: sqlite3.Connection, account_id: int) -> int:
    """مجموعُ بايتات صور هذا الحساب — measured column only, never estimated."""
    row = conn.execute(
        "SELECT COALESCE(SUM(size_bytes), 0) AS b FROM images WHERE owner_id = ?",
        (account_id,)).fetchone()
    return int(row["b"] if hasattr(row, "keys") else row[0])


def per_user_limit(conn: sqlite3.Connection, account_id: int) -> int:
    """سقف الإطلاقات الشهري لكل مستخدم في هذا الحساب — 0 = بلا حدّ.

    تجاوزُ الأدمِن (`accounts.per_user_monthly_studies`) يفوز إن ضُبط؛ وإلا
    افتراض الطبقة (`TierLimits.per_user_monthly_studies` — صفر لكل الطبقات
    اليوم فلا يتغيّر سلوك حسابٍ لم يضبطه الأدمِن). Admin override wins; the
    tier default (currently 0 everywhere) applies otherwise.
    """
    acc = _account(conn, account_id)
    override = acc["per_user_monthly_studies"]
    if override is not None:
        return max(0, int(override))
    return max(0, int(tier_limits(Tier(acc["tier"])).per_user_monthly_studies))


def user_launches_this_period(conn: sqlite3.Connection, account_id: int,
                              user_id: int) -> int:
    """إطلاقات المستخدم المثبتة في الفترة الحالية — مشتقّة من الدراسات نفسها.

    العدّ من `studies.launched_by_user_id` + شهر `launched_at` (لا عدّاد موازٍ
    ينحرف عن الحقيقة): تُحسَب الدراسة التي **بقيت منطلقة** فعلاً — مسار التعويض
    عند رفض الحجز يمسح الختم فلا تُحتسَب دراسة لم تنطلق. الأرشفة/الإنهاء لا
    يمسحان الختم (الإطلاق حدث واستهلك حصّة). Counts launches that stuck;
    the compensation path clears the stamp so a refused launch never counts.
    """
    # درس 192 (F17): العدّ يحترم علامة إعادة التعيين — ما أُطلق **بعد** آخر
    # إعادة تعيينٍ للحساب ضمن الفترة فقط، فتصفّر إعادةُ التعيين الإدارية هذا
    # العدّاد المشتقّ كما تصفّر العدّاد المخزَّن (مصدر حقيقةٍ واحد لنقطة الصفر).
    acc = _account(conn, account_id)
    try:
        watermark = acc["quota_reset_at"]
    except (KeyError, IndexError):
        watermark = None
    if watermark:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM studies WHERE owner_id = ? "
            "AND launched_by_user_id = ? AND launched_at IS NOT NULL "
            "AND substr(launched_at, 1, 7) = ? AND launched_at > ?",
            (account_id, user_id, current_period(), watermark)).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM studies WHERE owner_id = ? "
            "AND launched_by_user_id = ? AND launched_at IS NOT NULL "
            "AND substr(launched_at, 1, 7) = ?",
            (account_id, user_id, current_period())).fetchone()
    return int(row["c"])


# نافذة فحصٍ قابلة للتوسعة صناعياً في اختبار التزامن (نفس نمط قفل المقاعد —
# الدرس ٧٦: اختبار تزامنٍ لا يُثبِت أنه يُفشِل النسخة غير الذرّية حارسٌ خامل).
# Test seam: widened artificially so the concurrency test measures the LOCK,
# not transient GIL ordering (LESSONS row 76).
def _user_quota_check_delay() -> None:
    return None


def _account(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise ValueError(f"no account {account_id}")
    return row


def _roll_period_if_needed(conn: sqlite3.Connection, acc: sqlite3.Row) -> int:
    """صفّر العدّاد الشهري كسولاً عند دخول شهر جديد — lazy monthly roll.

    تصفير **ذرّي مشروط** بتعليمة UPDATE واحدة: يعيد الضبط فقط حين يختلف الشهر
    المخزَّن (أو كان NULL)، فتشغيلات متزامنة على حساب حديث لا تصفّر العدّاد
    مراراً وتُفسِد السقف (خلل التقطه تدقيق التزامن). لا يمسّ Basic.
    Atomic conditional roll — a single guarded UPDATE, so concurrent first
    launches can't each reset the counter and break the cap.
    """
    if Tier(acc["tier"]) == Tier.BASIC:
        return int(acc["current_month_study_count"])
    period = current_period()
    conn.execute(
        "UPDATE accounts SET current_month_study_count = 0, quota_period = ?, "
        "updated_at = ? WHERE id = ? AND (quota_period IS NULL OR quota_period != ?)",
        (period, now_iso(), acc["id"], period))
    conn.commit()
    row = conn.execute("SELECT current_month_study_count FROM accounts WHERE id = ?",
                       (acc["id"],)).fetchone()
    return int(row["current_month_study_count"])


# لا دالّة `evaluate()` منفصلة عمداً: مسار الحصّة **واحد** هو `reserve_launch`
# (فحص وزيادة ذرّيان في تعليمة واحدة). نسخة «قراءة فقط» ثانية كانت تكرّر منطق
# الطبقات بلا الشكل الآمن من TOCTOU، فأيّ مُنادٍ لها يعيد إدخال السباق المُغلَق.
# Deliberately one quota path (reserve_launch); a read-only twin would duplicate
# the tier rules without the race-safe guarded UPDATE.


def reserve_launch(conn: sqlite3.Connection, account_id: int, *,
                   actor_user_id: int | None) -> QuotaDecision:
    """احجز إطلاق دراسة — check the quota and, if allowed, increment the counter.

    يُستدعى مرّة واحدة عند draft→in_progress. عند المنع يكتب قيد تدقيق
    (over-quota launch attempt) ولا يزيد شيئاً.

    **حصّة المستخدم (قرار مالك 2026-08-17):** تُفحَص قبل عدّاد الحساب. الذرّية
    هنا **بالتصميم لا بقفل إضافي** (نفس اتجاه الدرس ٧٦: الكتابة قبل الفحص):
    المطالبة draft→in_progress — وهي كتابة UPDATE محروسة مثبَّتة قبل النداء —
    تختم `launched_by_user_id`، والعدّ أدناه **يشمل** الدراسة المُطالَب بها،
    فإطلاقان متزامنان فوق السقف يرى كلٌّ منهما عدّاً ≥ الحدّ ويُرفَض المتجاوز
    (قد يُرفَض كلاهما تحفّظاً — fail-closed؛ لا قبولَ فوق السقف أبداً)، ومسار
    التعويض يمسح الختم فلا تُحتسَب دراسة رُفض حجزها.
    Write-before-check by construction: the committed claim IS the reservation
    stamp, and the count includes self — over-admission is impossible; the
    worst concurrent case is conservative double-refusal.
    """
    # زيادة ذرّية محروسة بالسقف — atomic guarded increment closes the
    # check-then-increment TOCTOU (ملاحظة مراجعة خصامية): تشغيلان متزامنان لا
    # يتجاوزان الحدّ لأن الشرط `< limit` والزيادة في تعليمة UPDATE واحدة.
    acc = _account(conn, account_id)
    tier = Tier(acc["tier"])
    # الحدّ **الفعّال** لا الثابت: المالك يعدّل حصّة الباقة من لوحة
    # الأدمِن (2026-08-20)، والتجاوز يعيش في القاعدة. قراءةٌ لكل مطالبة
    # بلا تخبئة — قيمةٌ قديمة هنا تعني إطلاقاً كان يجب منعه.
    limits = tier_config.effective_limits(conn, tier)
    # (٠) سقف المستخدم أولاً — رفضُه لا يزيد عدّاد الحساب أصلاً.
    ulimit = per_user_limit(conn, account_id)
    uused_now = 0
    if ulimit and actor_user_id is not None:
        _user_quota_check_delay()   # نافذة اختبار التزامن — لا أثر إنتاجياً
        uused_now = user_launches_this_period(conn, account_id, actor_user_id)
        if uused_now > ulimit:      # العدّ يشمل الدراسة المُطالَب بها
            prior = max(0, uused_now - 1)
            audit.record(conn, action="quota_exceeded", user_id=actor_user_id,
                         account_id=account_id, resource_type="study",
                         changes={"reason": "user_quota_exceeded",
                                  "tier": tier.value, "user_limit": ulimit,
                                  "user_used": prior})
            conn.commit()
            # الزوج العام (limit/used) يحمل **نطاق المستخدم** هنا لا نطاق
            # الحساب — خلط النطاقين كان يُخرج «1/10» لمستهلكٍ عام بينما القيد
            # الفعلي «1/1» (ملاحظة المراجعة الذاتية §58): سببُ الرفض ومقياسه
            # من نطاقٍ واحد دائماً.
            return QuotaDecision(False, "user_quota_exceeded",
                                 ulimit, prior, tier.value,
                                 user_limit=ulimit, user_used=prior)
    if tier == Tier.BASIC:
        cur = conn.execute(
            "UPDATE accounts SET lifetime_study_count = lifetime_study_count + 1, "
            "updated_at = ? WHERE id = ? AND lifetime_study_count < ?",
            (now_iso(), account_id, limits.lifetime_studies))
        conn.commit()
        used = int(_account(conn, account_id)["lifetime_study_count"])
        reason, limit = "lifetime_quota_exceeded", limits.lifetime_studies
    else:
        _roll_period_if_needed(conn, acc)   # صفّر كسولاً عند شهر جديد أولاً
        cur = conn.execute(
            "UPDATE accounts SET current_month_study_count = "
            "current_month_study_count + 1, quota_period = ?, updated_at = ? "
            "WHERE id = ? AND current_month_study_count < ?",
            (current_period(), now_iso(), account_id, limits.monthly_studies))
        conn.commit()
        used = int(_account(conn, account_id)["current_month_study_count"])
        reason, limit = "monthly_quota_exceeded", limits.monthly_studies
    if cur.rowcount == 0:   # الشرط لم يتحقّق ⇒ عند/فوق الحدّ · at/over the cap
        audit.record(conn, action="quota_exceeded", user_id=actor_user_id,
                     account_id=account_id, resource_type="study",
                     changes={"reason": reason, "tier": tier.value,
                              "limit": limit, "used": used})
        conn.commit()
        return QuotaDecision(False, reason, limit, used, tier.value,
                             user_limit=ulimit, user_used=max(0, uused_now - 1))
    return QuotaDecision(True, "", limit, used, tier.value,
                         user_limit=ulimit, user_used=uused_now)


def release_launch(conn: sqlite3.Connection, account_id: int,
                   launched_at: str | None = None) -> bool:
    """أرجِع حجز إطلاقٍ لم يُنتج شيئاً — guarded decrement (جسر المحرّك).

    **متى يُستدعى:** فشل تشغيل المحرّك (أو يُتم إعادة نشر) أعاد الدراسة
    مسودّةً — دراسةٌ لم تُنتج تقريراً لا تُحسَب على المصنع. نفس مبدأ سابقة
    التعويض القائمة في مسار الإطلاق («لا تُحرَق حصّة بدراسة لم تنطلق»)؛
    حصّة **المستخدم** تتحرّر تلقائياً بمسح ختم `launched_by_user_id` (العدّ
    مشتق من الختم لا من عدّاد موازٍ) — هذه الدالة تُرجِع عدّاد **الحساب** فقط.

    الإنقاص محروس (`> 0`)، وللطبقات الشهرية محروس أيضاً بمفتاح الفترة: إرجاعٌ
    بعد انقلاب الشهر لا يمسّ عدّاد شهرٍ جديد لم يُحجَز منه شيء (التصفير الكسول
    سيتكفّل به). الإرجاع المزدوج مستحيل من المسار المستدعي: يُستدعى فقط حين
    ينجح الإرجاع الذرّي draft (rowcount=1) — مرة واحدة لكل إطلاق.
    Guarded, period-aware decrement; caller invokes it exactly once per launch.
    """
    acc = _account(conn, account_id)
    tier = Tier(acc["tier"])
    # درس 193 (F17 — تتمّة العلامة المائية): إطلاقٌ سبق آخرَ إعادة تعيينٍ
    # للحساب (`launched_at <= quota_reset_at`) صُفِّرت مساهمتُه في العدّاد
    # أصلاً بإعادة التعيين — إرجاعُه يُنقِص مرّةً ثانية فيسرق حجزَ دراسةٍ
    # لاحقة (تحت-إنفاذ الحصّة = دراسة مجّانية فوق الباقة). لا إرجاع لما قبل
    # العلامة. (العلامة تسري على الشهريّ والمدى-حياتيّ سواء.)
    try:
        _wm = acc["quota_reset_at"]
    except (KeyError, IndexError):
        _wm = None
    # مقارنةٌ صارمة `<`: إطلاقٌ في ثانية إعادة التعيين نفسها (تعذّر تمييز
    # قبل/بعد بدقّة الثانية) يُرجَع طبيعياً بدل حجبٍ زائد — الاتجاه الأسلم.
    if launched_at and _wm and str(launched_at) < str(_wm):
        return False
    if tier == Tier.BASIC:
        cur = conn.execute(
            "UPDATE accounts SET lifetime_study_count = lifetime_study_count - 1, "
            "updated_at = ? WHERE id = ? AND lifetime_study_count > 0",
            (now_iso(), account_id))
    else:
        cur = conn.execute(
            "UPDATE accounts SET current_month_study_count = "
            "current_month_study_count - 1, updated_at = ? "
            "WHERE id = ? AND current_month_study_count > 0 "
            "AND (quota_period IS NULL OR quota_period = ?)",
            (now_iso(), account_id, current_period()))
    released = cur.rowcount > 0
    if released:
        audit.record(conn, action="quota_released", account_id=account_id,
                     resource_type="study",
                     changes={"tier": tier.value, "reason": "run_produced_nothing"})
    conn.commit()
    return released


def monthly_reset(conn: sqlite3.Connection) -> int:
    """التصفير الشهري — reset current_month counters for all tiers EXCEPT Basic.

    مهمّة أوّل الشهر 00:00 UTC. يكتب قيد تدقيق. يرجّع عدد الحسابات المصفَّرة.
    Basic's lifetime counter is deliberately untouched (survives the reset).

    محروسة بمفتاح الفترة (`quota_period != period`) فتكون **خاملة التكرار**:
    نداء ثانٍ في نفس الشهر (إعادة تشغيل المجدول، أو إطلاق مزدوج) لا يصفّر شيئاً
    ولا يمنح حصّة إضافية. Period-guarded ⇒ idempotent within a month.
    """
    period = current_period()
    now = now_iso()
    # درس 192 (F17): تختم العلامة المائية أيضاً — فيُصفَّر العدّاد المشتقّ لكل
    # مستخدم كما يُصفَّر المخزَّن (مصدرٌ واحد لنقطة الصفر).
    cur = conn.execute(
        "UPDATE accounts SET current_month_study_count = 0, quota_period = ?, "
        "quota_reset_at = ?, updated_at = ? WHERE tier != 'basic' "
        "AND (quota_period IS NULL OR quota_period != ?)",
        (period, now, now, period))
    audit.record(conn, action="monthly_quota_reset", resource_type="accounts",
                 changes={"period": period, "accounts_reset": cur.rowcount})
    conn.commit()
    return cur.rowcount


def reset_account_quota(conn: sqlite3.Connection, account_id: int) -> dict:
    """صفّر حصّة حسابٍ بعينه الآن (F17، درس 192) — إعادةُ تعيينٍ إدارية تصفّر
    **العدّادين معاً**: المخزَّن للحساب (`current_month_study_count`) والعلامة
    المائية التي يحترمها العدّاد المشتقّ لكل مستخدم. مصدرُ حقيقةٍ واحد لنقطة
    الصفر — لا عدّاد يبقى «مستهلَكاً» بعد إعادة التعيين.

    العدّاد مدى-الحياة (Basic) لا يُمَسّ (عقده «دراسة واحدة مدى الحياة»)؛
    العلامة تُختَم للكلّ فتُصفّر العدّاد المشتقّ للمستخدمين أياً كانت الطبقة.
    """
    now = now_iso()
    conn.execute(
        "UPDATE accounts SET current_month_study_count = 0, quota_reset_at = ?, "
        "quota_period = ?, updated_at = ? WHERE id = ?",
        (now, current_period(), now, account_id))
    audit.record(conn, action="quota_reset", account_id=account_id,
                 resource_type="account", changes={"reset_at": now})
    conn.commit()
    return {"account_id": account_id, "quota_reset_at": now}
