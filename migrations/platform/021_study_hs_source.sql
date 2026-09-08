-- مصدر إقرار المصنع على الدراسة نفسها؛ الصفوف القديمة لا تُرقّى تلقائياً.
-- Persist explicit factory confirmation; legacy rows retain unknown provenance.
ALTER TABLE studies ADD COLUMN hs_source TEXT NOT NULL DEFAULT 'unknown'
    CHECK (hs_source IN ('unknown', 'manual'));
