-- ترحيل ٠٠٥ (مخزن الحقائق): فهرسُ ميزانية Comtrade اليومية — R5 (DB-7).
-- `silk_collectors.comtrade_budget_left` يجمع `fetched + failed` لليوم الجاري
-- بالمصدر والزمن؛ بلا فهرس كان مسحاً كاملاً مع كلّ فحصٍ للميزانية.
CREATE INDEX IF NOT EXISTS idx_collection_runs_source_started
    ON collection_runs(source, started_at);
