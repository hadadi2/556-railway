"""حارس بنيوي للعزل — AST guard: no unscoped SQL on tenant tables.

**لماذا:** عزل المستأجرين كان مضموناً بمراجعةٍ يدوية فقط. كل استعلام في
`silk_platform/` يمرّ اليوم عبر `repository.py` أو يحمل قيد المالك صراحةً — لكن
لا شيء **آلي** يمنع PR قادماً من إضافة `SELECT * FROM studies WHERE id = ?` بلا
قيد مالك، فيصير كل مستأجر يقرأ دراسات الآخرين. مراجعةٌ يدوية تنسى؛ هذا الاختبار
لا ينسى.

**كيف:** يقرأ AST كل وحدة في `silk_platform/`، يستخرج كل نصّ SQL حرفيّ، ويؤكّد
أن أي جملة تمسّ جدولاً مُستأجَراً إمّا:
  (أ) تحمل قيد مالك (`owner_id` / `account_id` / `sending_account_id`)، أو
  (ب) مُدرَجة في `_INTENTIONAL_GLOBAL` بسببٍ مكتوب (قراءات مجمّعة للأدمِن/المحلّل،
      أو عامل الطابور الذي يعمل عبر الحسابات بحكم وظيفته).

إضافةُ استعلام غير مُنطَّق تُسقِط الاختبار وتُجبر قراراً صريحاً: إمّا تُنطِّقه،
أو تُدرِجه بسبب. Adding an unscoped query fails CI and forces a deliberate choice.
"""
import ast
import pathlib
import re

import pytest

_PKG = pathlib.Path(__file__).resolve().parent.parent / "silk_platform"

# الجداول التي تحمل عمود مالك (مُستأجَرة) — من الترحيل 001.
# `users` مُدرَج منذ PR-2: صار للمنصّة مسارُ إدارة مستخدمين فرعيين يكتب في هذا
# الجدول، فاستعلامٌ غير منطَّق فيه يعني قراءة/تعديل مستخدمي مستأجرٍ آخر — وهو
# أخطر من تسريب دراسة لأنه مسار صلاحية. Added in PR-2 with sub-user management.
TENANT_TABLES = {
    "studies", "prospects", "drafts", "images", "smtp_configs",
    "comparison_funnels", "wallets", "ledger_entries", "email_queue",
    "suppression_list", "consent_registry", "users",
    # جدولا وصل القمع مُدرَجان منذ PR-7 **رغم أنهما بلا عمود مالك**: مفتاحهما
    # مركَّب فقط، فلو تُركا خارج القائمة لما رآهما الحارس إطلاقاً — و
    # `INSERT INTO funnel_studies` بمعرّف دراسةٍ لحسابٍ آخر يربط بيانات مستأجرٍ
    # بقمع مستأجر ثانٍ بلا أن يُحمِّر شيء. إدراجهما يُلزِم كل جملة عليهما بسببٍ
    # مكتوب يشرح **كيف** تُفرَض الملكية، فيصير الخطر موثَّقاً لا خفيّاً.
    # Included despite having NO owner column: otherwise the guard would never
    # see them, and a cross-tenant join-table INSERT would pass silently.
    "funnel_studies", "funnel_prospects",
    # إشعارات داخل المنصّة (ترحيل 009، قرار 2026-08-18): يكتبها جسر المحرّك
    # ويقرؤها الحساب — استعلامٌ غير منطَّق فيها يعني قراءة إشعارات مستأجرٍ آخر.
    "platform_notifications",
    # كتالوج المنتجات (ترحيل 010، قرار 2026-08-18) — كيان مستأجَر كامل.
    "products",
    # سجلّ تشغيلات الدراسات (ترحيل 018، R2 2026-09-02) — بلا عمود مالك؛ يشير
    # إلى `studies` بمفتاحٍ أجنبي. مُدرَجٌ بنفس منطق جدولَي وصل القمع: لولا
    # الإدراج لما رآه الحارس، فكل جملة عليه تحمل سبباً يشرح **كيف** تُشتقّ
    # ملكيتُه (معرّفٌ من قراءةٍ مستأجَرة في طبقة الـAPI، أو من مسح المشرف نفسه).
    "study_runs",
}

# أعمدة المالك · owner columns.
OWNER_COLUMNS = ("owner_id", "account_id", "sending_account_id")


def _has_owner_predicate(sql: str) -> bool:
    """هل يقيّد المالكَ **فعلاً**؟ — is the owner column an actual constraint?

    الفحص السابق كان «هل يظهر اسم عمود المالك في النصّ؟» فكان
    `SELECT u.account_id AS account_id FROM users WHERE token = ?` يمرّ لأن الاسم
    ظهر في قائمة الإسقاط — لا في قيدٍ. حارسٌ يُخدَع بذكر الاسم يعطي طمأنينة
    كاذبة، فالتمييز الآن على **شكل** الاستعمال:

    - `INSERT`: وجود العمود في قائمة الأعمدة **هو** الشكل الصحيح (الملكية تُكتب).
    - غيرها (`SELECT`/`UPDATE`/`DELETE`): يجب أن يكون العمود في مقارنة —
      `account_id = ?` أو `IN (...)` أو `IS NULL` — أي قيداً لا إسقاطاً.

    Distinguishes a real constraint from a mere mention of the column name.
    """
    if re.match(r"\s*INSERT\b", sql, re.IGNORECASE):
        return any(col in sql for col in OWNER_COLUMNS)
    return any(re.search(rf"\b{col}\s*(=|!=|<>|\bIN\b|\bIS\b)", sql, re.IGNORECASE)
               for col in OWNER_COLUMNS)

# استثناءات مقصودة **مقيَّدة بالوحدة**: (الوحدة، مقتطف) → السبب.
# تقييد الوحدة يُبقي الحارس حادّاً: تحويلات حالة الطابور مسموحة في عامل الطابور
# (معرّفات الصفوف من مسحه الخاص، لا من طلب) وتبقى **مرفوضة** لو أضافها أحد في
# `api.py` على مسار طلبٍ مستأجَر. Module-scoped so a request path stays guarded.
_INTENTIONAL_GLOBAL: dict[tuple[str, str], str] = {
    # R5 (DB-16): تقليمُ الإشعارات **المقروءة** الأقدم من نافذة الاحتفاظ تنظيفٌ
    # جدوليّ يقوده المجدول عبر المستأجرين كلّهم بالتصميم — لا يصل من طلبٍ ولا
    # يخاطب صفّاً بعينه، ولا يمسّ غيرَ المقروء.
    ("notifications.py", "DELETE FROM platform_notifications WHERE read_at IS NOT NULL"):
        "R5 retention prune: scheduler-driven, all tenants by design; deletes only "
        "read rows older than an env window and is never reachable from a request.",
    # R2 (2026-09-02) — مُشرِف التشغيلات عاملُ نظامٍ يعمل عبر الحسابات بحكم
    # وظيفته (نفس منطق عامل الطابور القديم): كل معرّفٍ يمسّه يأتي من مسحه هو
    # لـ`study_runs` (مطالبة/نبضة/تقادم/إغلاق) أو من طبقة الـAPI بعد قراءةٍ
    # مستأجَرة (`repository.studies(conn).get(ctx.account_id, …)`) — لا يقبل
    # معرّفاً من طلبٍ أبداً، و`owner_id` يُقرأ بالـJOIN ليُمرَّر لإرجاع الحصّة
    # والإشعار لصاحب الدراسة نفسه.
    ("study_runtime.py", "study_runs"):
        "system worker across tenants by design (like the old queue worker): "
        "every study_id comes from its own scan of study_runs or from the API "
        "layer after a TenantRepository read; owner_id is joined only to refund "
        "and notify the study's own account (R2, 2026-09-02)",
    # الجسر يُغلق صفّ التشغيلة على **رمز المحاولة** (فريدٌ عالمياً، يملكه خيط
    # التشغيلة وحده) أو على معرّف صفّه الذي خصّصه المشرف — لا معرّف من طلب.
    ("engine_bridge.py", "UPDATE study_runs SET"):
        "closes/links the run row by its attempt token or its own run id — "
        "both minted by the bridge/supervisor, never taken from a request "
        "(R2, 2026-09-02)",
    # كنس الصفوف القديمة يقرأ **معرّفات الدراسات** ذات السجلّ النشط ليتخطّاها —
    # قراءةُ مفاتيح لا بيانات، وعبر الحسابات بحكم وظيفة الكنس عند الإقلاع.
    ("engine_bridge.py", "SELECT study_id FROM study_runs"):
        "boot-time sweep reads only the ids of run-backed studies to skip them; "
        "the sweep itself was already cross-tenant by design (R2, 2026-09-02)",
    # حذفُ الدراسة: صفوفُ تشغيلاتها المنتهية تُحذف معها **بعد** التحقّق من
    # ملكيتها عبر `repository.studies(conn).get(ctx.account_id, study_id)`.
    ("api.py", "DELETE FROM study_runs WHERE study_id = ?"):
        "runs after repository.studies(conn).get(ctx.account_id, study_id) "
        "proved ownership; deletes only terminal rows of that study "
        "(R2, 2026-09-02)",
    # لغة الواجهة (2026-08-17): ذاتية النطاق **بالبناء** — المعرّف هو
    # `ctx.user_id` من الجلسة حصراً ولا يُقبل من جسم الطلب، فلا سبيل لعبور
    # مستأجر أصلاً (نقطة PATCH /me/language لكل الأدوار).
    ("api.py", "SELECT first_name, last_name, language_chosen_at, created_at "
               "FROM users WHERE id = ?"):
        "self-scoped by construction: the id is ctx.user_id from the session "
        "(GET /me — profile fields + explicit-choice stamp §58 M4 + "
        "member_since for the profile account card, 2026-08-19)",
    # البروفايل (2026-08-18): نفس البناء الذاتي — المعرّف من الجلسة حصراً.
    ("api.py", "SELECT first_name, last_name FROM users WHERE id = ?"):
        "self-scoped by construction: the id is ctx.user_id from the session "
        "(PATCH /me reads current names before the static-column update)",
    ("api.py", "UPDATE users SET first_name = ?, last_name = ?"):
        "self-scoped by construction: the id is ctx.user_id from the session, "
        "never request input (PATCH /me, any role)",
    ("api.py", "UPDATE users SET language_preference = ?, "
               "language_chosen_at = ?, updated_at = ? WHERE id = ?"):
        "self-scoped by construction: the id is ctx.user_id from the session, "
        "never request input (PATCH /me/language, any role)",
    # عدّاد نظرة عامة الأدمِن: مجمّع عبر كل الحسابات بحكم الدور (أدمِن فقط)،
    # عدد بلا أي حقل صف — نفس عائلة مجمّعات المحلّل المصرّح بها أدناه.
    ("api.py", "SELECT COUNT(*) AS c FROM users WHERE is_active = 1"):
        "admin overview aggregate count across accounts (admin-only route, "
        "no row fields leave the server)",
    # عامل الطابور مهمّة خلفية تعمل عبر كل الحسابات بحكم وظيفتها (لا طلب مستأجر).
    ("email_queue.py", "SELECT * FROM email_queue WHERE status = 'queued'"):
        "background worker processes all accounts by design (not a tenant request)",
    ("email_queue.py", "SELECT COUNT(*) AS c FROM email_queue WHERE status = 'queued'"):
        "worker summary counter across accounts (background job)",
    # تحويلات حالة الصفّ داخل حلقة العامل: `id` يأتي من مسح العامل نفسه، ولا
    # يُقبَل من مدخلات المستخدم في أي مسار.
    ("email_queue.py", "UPDATE email_queue SET status"):
        "worker-owned row-id state transitions; ids come from the worker's own "
        "scan and are never user-supplied",
    ("email_queue.py", "SELECT * FROM smtp_configs WHERE id = ?"):
        "worker reads the smtp config the study was launched with (already "
        "ownership-validated at launch time)",
    ("email_queue.py", "SELECT id, attempts FROM email_queue WHERE status = 'sending'"):
        "PR-5 reaper scan for stuck rows is a background job across all "
        "accounts by design, same rationale as the queued-row scan above",
    # فوترة التخزين تجمع لكل حساب بـGROUP BY owner_id ثم تشحن كل حساب على حدة.
    ("jobs.py", "FROM images GROUP BY owner_id"):
        "monthly billing aggregates per account via GROUP BY owner_id",
    # التحوّل لدراسات السوق (قرار مالك 2026-08-17) — جسر المحرّك:
    # ETA الصادق مجمّعٌ عالمي لمدد التشغيل (قيمتان زمنيتان، لا محتوى مستأجر
    # يعود للطالب) — نطاقه عبر الحسابات **هو** مصدر دقّته.
    ("engine_bridge.py",
     "SELECT run_started_at, run_finished_at, run_stats FROM studies"):
        "honest-ETA duration aggregate across accounts; returns two timestamps "
        "plus the run mode per row to a per-mode median, never tenant content",
    # كنس أيتام الإقلاع مهمّة خلفية عبر كل الحسابات بحكم وظيفتها (نفس منطق
    # عامل الطابور)، ومعرّفات صفوفها من مسحها الخاص لا من أي طلب مستأجر.
    ("engine_bridge.py",
     "SELECT id, owner_id, analysis_id, run_started_at, run_stats"):
        "boot orphan sweep scans all accounts by design (background, "
        "not a tenant request)",
    ("engine_bridge.py", "UPDATE studies SET state = 'completed', completed_at"):
        "orphan-sweep completion; row ids come from the sweep's own scan and "
        "are never user-supplied",
    ("engine_bridge.py",
     "UPDATE studies SET state = 'draft', launched_at = NULL"):
        "orphan-sweep revert; row ids come from the sweep's own scan and are "
        "never user-supplied",
    # تعطيلُ مستخدم مصنع من الأدمِن — السطح الوحيد الباقي بعد حذف المستخدمين
    # الفرعيين (2026-08-19): بلا سبيلٍ لتعطيل بقاياهم يبقى دخولُهم أبدياً.
    # الدور مفحوصٌ قبله، والصفّ يُقرأ بمعرّفه ثم يُرفض ما ليس دور «مصنع».
    ("api.py", "SELECT id, account_id, role, is_active FROM users WHERE id = ?"):
        "admin-only deactivation of a legacy sub-user; role checked before the "
        "write and every call audited",
    ("api.py", "UPDATE users SET is_active = 0"):
        "admin-only deactivation of a legacy sub-user (role verified from the "
        "row that was just read); audited",
    # إشراف الأدمِن على كل الدراسات (قرار المالك): نقطة أدمِن حصراً، حقول طلب
    # تشغيلية بلا بريد ولا محتوى — الجدار القائم على PII غير مخروق.
    ("api.py", "SELECT s.id, a.name AS account_name"):
        "admin oversight of all factory studies per explicit owner decision "
        "2026-08-17; admin-only route, operational fields only, no emails/PII",
    # مجمّع المحلّل «المنتجات الأكثر طلباً» — GROUP BY product بلا معرّفات ولا
    # PII (بديل مجمّع العملاء المحتملين المحذوف مع التنقيب).
    # R7 (AUTH-22): مجمّعُ فصول HS للمحلّل — بلا أسماءٍ ولا معرّفات، عبر المستأجرين بالتصميم.
    ("api.py", "SELECT substr(hs_code, 1, 2) AS chapter, COUNT(*) AS c FROM studies"):
        "R7 analyst aggregate: HS chapters across all tenants by design (no names, no ids).",
    # R7 (AUTH-7): بريدُ المستخدم ولغتُه لإرسال رمز إعادة التعيين — مسارُ أدمِن سِلك فقط.
    ("api.py", "SELECT email, language_preference FROM users WHERE id = ?"):
        "R7 admin issue-reset: silk-admin-only lookup of the target user's email/language.",
    # R7 (مراجعة): تأكيدُ إعادة التعيين يقرأ بريدَ صاحب الرمز (القدرةُ = الرمزُ نفسه، ٣٢ بايتاً
    # عشوائياً) ليمسح قفلَ عدّاد الدخول بالبريد — لا هويّةَ مستأجرٍ في الطلب أصلاً.
    ("api.py", "SELECT u.email FROM password_reset_tokens t JOIN users u ON u.id = t.user_id"):
        "R7 reset-confirm: token-hash keyed lookup (the token is the capability); "
        "clears the per-email login lock after a successful reset.",
    # R7 (مراجعة): فكُّ قفل الدخول بالبريد — مسارُ أدمِن سِلك فقط.
    ("api.py", "SELECT email FROM users WHERE id = ?"):
        "R7 admin unlock-login: silk-admin-only lookup of the target user's email.",
    ("api.py", "SELECT product, COUNT(*) AS studies FROM studies"):
        "analyst aggregate of top requested products (GROUP BY, counts only, "
        "no identifiers/PII) — replaces the deleted prospects aggregate",
    # مقاييس الأدمِن/المحلّل: مجمّعات بلا معرّفات ولا PII (COUNT فقط).
    ("api.py", "SELECT COUNT(*) AS c FROM studies WHERE state = 'in_progress'"):
        "admin metric: platform-wide count, no ids and no PII",
    ("api.py", "SELECT state, COUNT(*) AS c FROM studies GROUP BY state"):
        "analyst aggregate: counts by state, no ids and no PII",
    ("api.py", "SELECT industry, COUNT(*) AS prospects FROM prospects"):
        "analyst aggregate: counts by industry, no ids and no PII",
    # فحص ملكية بعد الجلب: يُقرأ الصفّ بمعرّفه ثم يُقارَن owner_id في بايثون
    # ويُرفَض 422 عند عدم التطابق (`_validate_smtp_binding`).
    ("api.py", "SELECT * FROM smtp_configs WHERE id = ?"):
        "ownership verified immediately after fetch in _validate_smtp_binding "
        "(rejects with 422 when owner_id differs)",
    ("api.py", "SELECT storage_key, mime_type FROM images WHERE storage_key = ?"):
        "GET /files is a public signed-URL route (PR-8), same trust model as "
        "/platform/unsubscribe — the HMAC signature verified just above is "
        "the actual authorization; storage_key is UNIQUE platform-wide (not "
        "per-account) so an owner predicate doesn't apply to this lookup",
    # ── مسارات الهويّة على `users` · identity paths (PR-2) ───────────────────
    # الدخول وإعادة التعيين **يجب** أن تكون عالمية: البريد هو هويّة الدخول وهو
    # فريد على مستوى المنصّة، فالحساب غير معروف بعد قبل أن تُحلّ الهويّة. تقييدها
    # بحساب يعني استحالة تسجيل الدخول أصلاً.
    ("auth.py", "SELECT u.*, u.is_active AS user_active, "
               "a.is_active AS account_active FROM users u "
               "JOIN accounts a ON a.id = u.account_id WHERE u.email = ?"):
        "login must resolve a globally-unique email before any account is known "
        "(the account is a RESULT of authentication, not an input to it); the "
        "JOIN reads only that same user's own account row, to refuse a suspended "
        "account at login exactly as resolve_session already refuses it per "
        "request — no cross-tenant read is possible from an email lookup",
    ("auth.py", "SELECT id FROM users WHERE email = ?"):
        "password-reset request resolves the global login identity; the endpoint "
        "returns 200 regardless so it leaks no existence",
    ("auth.py", "SELECT language_preference FROM users WHERE email = ?"):
        "same global-identity resolution as issue_reset_token, for the reset "
        "email's language — called only after that lookup already succeeded",
    ("auth.py", "SELECT u.id AS id, u.is_active AS user_active, "
               "a.is_active AS account_active FROM users u "
               "JOIN accounts a ON a.id = u.account_id WHERE u.id = ?"):
        "admin-issued reset (silk_admin-only route) targets a user by id across "
        "accounts by design; the route itself is role-walled. The JOIN reads "
        "only that same user's own account row, to refuse issuing or consuming "
        "a reset token for a deactivated user/account — no cross-tenant read",
    # تغيير كلمة المرور الذاتي (بروفايل 2026-08-18): المعرّف من الجلسة حصراً.
    ("auth.py", "SELECT password_hash FROM users WHERE id = ?"):
        "self-scoped by construction: the id is ctx.user_id from the session "
        "(POST /me/password verifies the current password first)",
    ("auth.py", "UPDATE users SET password_hash"):
        "reset confirmation is authenticated by the single-use token itself, not "
        "by a session, so no account context exists at that point",
    ("auth.py", "SELECT s.*, u.account_id AS account_id"):
        "session resolution is keyed by the sha256 token hash (unguessable) and "
        "is what PRODUCES the account context every other query scopes by",
    # ── التأسيس والجهوزيّة · bootstrap + readiness ────────────────────────────
    # كلاهما يعمل **قبل وجود أي سياق طلب**: `maybe_seed` عند الإقلاع (لا مستخدم
    # ولا حساب بعد — الحساب **نتيجةُ** البذر لا مدخلٌ له)، و`readiness` تُغذّي
    # `/health` بعددٍ على مستوى المنصّة. فلا account_id يُنطَّق به أصلاً.
    # لا يُرجَع أي صفّ ولا بريد — منطقيّ/عدديّ فقط، فلا سطح تسريب.
    ("bootstrap.py", "SELECT 1 FROM users WHERE role = 'silk_admin' LIMIT 1"):
        "boot-time seed predicate: runs before any request context exists, so no "
        "account is known yet (the accounts are the RESULT of seeding). Returns a "
        "boolean only — never a row",
    ("bootstrap.py", "SELECT COUNT(*) FROM users"):
        "platform-wide readiness counter for /health (answers 'was this DB ever "
        "seeded?'). A count, not identities — /health is public so it must never "
        "expose emails",
    ("seed.py", "SELECT id FROM users WHERE role = 'silk_admin' LIMIT 1"):
        "bootstrap lookup for the seeded silk_admin; runs at seed time before any "
        "request context exists",
    # (سقط مدخل `users.py` مع حذف وحدة المستخدمين الفرعيين نهائياً — قرار
    #  المالك 2026-08-19؛ حارسه tests/test_platform_seats_deletion_guard.py.)
    # ── قمع المقارنة (PR-7) · comparison funnels ──────────────────────────────
    ("funnels.py", "SELECT 1 FROM comparison_funnels WHERE id = ?"):
        "exists_anywhere returns a BOOLEAN only (never a row) so the endpoint can "
        "audit a cross-tenant attempt while still answering 404 — a boolean "
        "existence probe whose row id is never returned to the caller",
    # جدولا الوصل بلا عمود مالك: الملكية تُفرَض **قبل** كل كتابة هنا — القمع عبر
    # funnels.get (منطَّق بالمالك) وكل معرّف دراسة/عميل/مسودّة عبر repository
    # (منطَّق بالمالك)، فمعرّفٌ لحسابٍ آخر يُرفَض قبل أن يصل هذه الجُمَل.
    ("funnels.py", "SELECT study_id FROM funnel_studies WHERE funnel_id = ?"):
        "join table has no owner column; the funnel_id was ownership-verified via "
        "funnels.get() (owner-scoped) before this read, and no row enters "
        "funnel_studies without its study passing repository's owner predicate",
    ("funnels.py", "SELECT prospect_id FROM funnel_prospects WHERE funnel_id = ?"):
        "join table has no owner column; funnel_id ownership-verified via "
        "funnels.get() before this read, and rows only enter after each prospect "
        "id passed repository.prospects().get(account_id, ...)",
    ("funnels.py", "INSERT INTO funnel_studies (funnel_id, study_id)"):
        "both ids are ownership-verified immediately before this write: the funnel "
        "via funnels.get(account_id, ...) and the study via "
        "repository.studies(conn).get(account_id, ...) — a foreign id raises first",
    ("funnels.py", "DELETE FROM funnel_studies WHERE funnel_id = ? AND study_id = ?"):
        "the funnel was ownership-verified via funnels.get(account_id, ...) above; "
        "a foreign funnel_id never reaches here, and rowcount==0 is reported as "
        "not_attached rather than silently succeeding",
    ("funnels.py", "INSERT OR IGNORE INTO funnel_prospects (funnel_id, prospect_id)"):
        "every prospect id is verified via repository.prospects().get(account_id, "
        "...) and the funnel via funnels.get(account_id, ...) before this write; "
        "a foreign id raises prospect_not_found first",
}

_SQL_RE = re.compile(r"\b(SELECT|INSERT\s+INTO|INSERT\s+OR\s+IGNORE\s+INTO|UPDATE|DELETE\s+FROM)\b",
                     re.IGNORECASE)


def _iter_sql_literals():
    """كل نصّ SQL حرفيّ في الحزمة — (module, statement) for every SQL string.

    يجمع النصوص المتلاصقة (implicit concatenation) لأن الجُمَل مكتوبة على أسطر،
    فقيد `WHERE owner_id = ?` قد يكون في جزء تالٍ من نفس الجملة.
    """
    for path in sorted(_PKG.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        # أجزاء الـf-string الحرفيّة تُزار **مرّتين** بـ`ast.walk`: مرّة داخل
        # `JoinedStr` ومرّة كعقدة `Constant` مستقلّة. بلا استثنائها كان
        # `f"UPDATE users SET {cols} WHERE account_id = ?"` يُبلَّغ عنه كجملة
        # مقطوعة «UPDATE users SET» بلا قيد مالك — **إنذار كاذب** يدفع لإدراج
        # استثناء لا حاجة له، وكل استثناء زائد يوسّع الثقب الحقيقي.
        # f-string fragments are visited twice by ast.walk; count them once.
        in_fstring = {id(v) for node in ast.walk(tree)
                      if isinstance(node, ast.JoinedStr)
                      for v in node.values if isinstance(v, ast.Constant)}
        for node in ast.walk(tree):
            # نصّ حرفيّ مفرد (وليس جزءاً من f-string سبق جمعه)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in in_fstring:
                    continue
                if _SQL_RE.search(node.value):
                    yield path.name, " ".join(node.value.split())
            # f-string / تلاصق: اجمع كل الأجزاء الحرفيّة في عقدة واحدة
            elif isinstance(node, ast.JoinedStr):
                parts = [v.value for v in node.values
                         if isinstance(v, ast.Constant) and isinstance(v.value, str)]
                joined = " ".join(" ".join(p.split()) for p in parts)
                if _SQL_RE.search(joined):
                    yield path.name, joined


def _tables_touched(sql: str) -> set[str]:
    """الجداول المُستأجَرة التي تمسّها الجملة — tenant tables referenced."""
    found = set()
    for table in TENANT_TABLES:
        if re.search(rf"\b(FROM|INTO|UPDATE|JOIN)\s+{table}\b", sql, re.IGNORECASE):
            found.add(table)
    return found


def _is_allowlisted(module: str, sql: str) -> bool:
    """مُدرَجٌ بسببٍ **لهذه الوحدة** — allowlisted for this module specifically."""
    return any(mod == module and snippet in sql
               for (mod, snippet) in _INTENTIONAL_GLOBAL)


def test_every_tenant_query_is_owner_scoped_or_declared():
    """كل استعلام على جدول مُستأجَر منطَّقٌ بالمالك أو مُعلَن بسبب.

    الفشل هنا يعني: أضفتَ استعلاماً يمسّ بيانات مستأجر بلا قيد مالك. أضِف
    `AND owner_id = ?` (أو مرّ عبر `repository.TenantRepository`)، أو — إن كان
    عالمياً بقصد — أدرِجه في `_INTENTIONAL_GLOBAL` بسببٍ مكتوب.
    """
    violations = []
    for module, sql in _iter_sql_literals():
        # `repository.py` هو طبقة العزل نفسها: جُمَله مبنيّة بعمود المالك
        # (`{self.owner_col}`) الذي لا يظهر نصّاً حرفياً — تغطّيه اختبارات العزل.
        if module == "repository.py":
            continue
        tables = _tables_touched(sql)
        if not tables:
            continue
        if _has_owner_predicate(sql):
            continue
        if _is_allowlisted(module, sql):
            continue
        violations.append(f"{module}: {sql[:120]}")
    assert not violations, (
        "unscoped SQL on tenant table(s) — add an owner predicate, route through "
        "repository.TenantRepository, or declare it in _INTENTIONAL_GLOBAL with a "
        "reason:\n  " + "\n  ".join(violations))


def test_repository_is_the_only_place_building_tenant_sql_dynamically():
    """بناء SQL بأسماء جداول مُتغيّرة محصورٌ في طبقة العزل وحدها.

    f-string يضع اسم جدول أو عمود مالك من متغيّر هو بابٌ لتخطّي النطاق؛ يجوز في
    `repository.py` (حيث القيد مبنيّ بنيوياً) ويُمنَع في غيره.
    """
    offenders = []
    for path in sorted(_PKG.glob("*.py")):
        if path.name == "repository.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            literal = " ".join(v.value for v in node.values
                              if isinstance(v, ast.Constant)
                              and isinstance(v.value, str))
            if not _SQL_RE.search(literal):
                continue
            # اسم جدول مُستأجَر يأتي من تعبير (لا نصّ) ⇒ رفض.
            if re.search(r"\b(FROM|INTO|UPDATE|JOIN)\s*$", literal.strip(),
                         re.IGNORECASE):
                offenders.append(f"{path.name}: interpolated table name")
    assert not offenders, (
        "dynamic tenant-table SQL outside repository.py:\n  " + "\n  ".join(offenders))


def test_allowlist_entries_all_have_reasons():
    """كل استثناء يحمل سبباً غير فارغ — an undocumented exemption is a hole."""
    for (module, snippet), reason in _INTENTIONAL_GLOBAL.items():
        assert module.endswith(".py"), f"allowlist key must name a module: {module}"
        assert reason and len(reason) > 20, f"weak/missing reason for: {snippet}"


def test_guard_actually_catches_an_unscoped_query(tmp_path, monkeypatch):
    """الحارس نفسه يُختبَر: استعلام غير منطَّق **يجب** أن يُلتقَط.

    حارسٌ لا يُثبَت أنه يصطاد شيئاً قد يكون خاملاً بلا أن يعلم أحد
    («الاختبار الأخضر الفارغ»). نزرع وحدةً مخالفة ونؤكّد الالتقاط.
    """
    fake = tmp_path / "silk_platform_fake"
    fake.mkdir()
    (fake / "bad.py").write_text(
        'def leak(conn, sid):\n'
        '    return conn.execute("SELECT * FROM studies WHERE id = ?", (sid,))\n',
        encoding="utf-8")
    monkeypatch.setattr(__import__(__name__), "_PKG", fake, raising=False)
    globals()["_PKG"] = fake
    try:
        found = [f"{m}: {s}" for m, s in _iter_sql_literals()
                 if _tables_touched(s) and not _has_owner_predicate(s)
                 and not _is_allowlisted(m, s)]
        assert found, "the guard failed to catch a deliberately unscoped query"
    finally:
        globals()["_PKG"] = pathlib.Path(__file__).resolve().parent.parent / "silk_platform"
