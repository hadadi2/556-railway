-- قرار المالك 2026-09-14: حذف الباقة البلاتينية نهائياً.
-- نحول أي حساب قديم إلى أعلى باقة باقية قبل أن يرفضه Enum التطبيق الجديد،
-- ثم نحذف تجاوز سعر الباقة الملغاة. لا تُحذف حسابات ولا دراسات ولا ملفات.
UPDATE accounts SET tier = 'gold', updated_at = CURRENT_TIMESTAMP
WHERE tier = 'platinum';

DELETE FROM tier_settings WHERE tier = 'platinum';
