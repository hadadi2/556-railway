-- 018 — سجلّ تشغيلات الدراسات الدائم · durable study runs (أمر المالك 2026-09-02، R2/RC-1).
--
-- لماذا: كانت تشغيلةُ الدراسة خيطَ daemon داخل عملية الويب، وسجلُّها الوحيد
-- `studies.state='in_progress'` + قاموسٌ في الذاكرة (`engine_bridge._ACTIVE`).
-- لا نبضةَ حياة، ولا هويّةَ إقلاع، ولا سقفَ تزامن، ولا إلغاء، ولا ختمَ إغلاق —
-- فإعادةُ النشر تترك «قيد الإعداد» ساعةً كاملة، والتشغيلةُ المتجاوزة تُنفق بعد
-- إرجاع صفّها. هذا الجدول يجعل **القاعدةَ المرجعَ** لكل محاولة تنفيذ:
-- queued → running → completed | failed | interrupted | cancelled.
--
-- `studies.state` تبقى رباعيّة القيم كما هي (قيد CHECK في 001 لا يُمَسّ):
-- `in_progress` ⇔ تشغيلةٌ نشطة هنا (queued أو running). ما يقرؤه المصنع لم يتغيّر.
--
-- One durable row per launch attempt; the DB (not memory) owns the lifecycle.
-- Additive only — لا مساس بأي صف قائم. `IF NOT EXISTS` في كل جملة كي تبقى
-- إعادةُ التطبيق بعد عطلٍ بين السكربت وصفّ الإصدار حميدة.

CREATE TABLE IF NOT EXISTS study_runs (
    id                  INTEGER PRIMARY KEY,
    study_id            INTEGER NOT NULL REFERENCES studies(id),
    run_token           TEXT NOT NULL,           -- = studies.run_token لهذه المحاولة
    state               TEXT NOT NULL
                            CHECK (state IN ('queued','running','completed',
                                             'failed','interrupted','cancelled')),
    mode                TEXT NOT NULL,           -- deep | quick | fake (ختم الإطلاق)
    boot_id             TEXT,                    -- هويّة إقلاع العملية التي طالبت بها
    params_json         TEXT NOT NULL,           -- لقطة وسائط الإطلاق (تكفي لبدئها لاحقاً)
    analysis_id         INTEGER,                 -- معرّف تشغيلة المحرّك لهذه المحاولة
    created_at          TEXT NOT NULL,
    started_at          TEXT,
    heartbeat_at        TEXT,                    -- آخر نبضة من مشرف العملية المالكة
    finished_at         TEXT,
    cancel_requested_at TEXT,                    -- NULL = لم يُطلَب إلغاء
    error_code          TEXT,                    -- رمز آلي قصير للنهاية غير الناجحة
    error_text          TEXT                     -- نصٌّ منقَّح — نفس ما يقرؤه المصنع
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_study_runs_token ON study_runs(run_token);
-- تشغيلةٌ نشطة واحدة لكل دراسة — حارسٌ بنيويّ ضدّ التنفيذ المزدوج.
CREATE UNIQUE INDEX IF NOT EXISTS ux_study_runs_active ON study_runs(study_id)
    WHERE state IN ('queued','running');
CREATE INDEX IF NOT EXISTS ix_study_runs_state ON study_runs(state);
