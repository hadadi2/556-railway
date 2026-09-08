-- 010 — كتالوج منتجات المصنع · factory product catalog (قرار المالك 2026-08-18).
--
-- «المزايا احذفها واستبدلها بالدارسات واضف فوقها المتنجات»: المصنع يسجّل
-- منتجاته مرة واحدة (اسم + وصف + رمز HS اختياري + صورة اختيارية)، ومن كل
-- منتج يُطلق دراسات تُربط به (`studies.product_id`) — فيتجمّع تاريخ دراسات
-- كل منتج تحت بطاقته وتتعبأ حقول الدراسة الجديدة تلقائياً.
--
-- إضافي فقط — لا مساس بأي صف قائم. Additive only.
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    hs_code TEXT,                                  -- 4–6 أرقام؛ NULL = غير محدد
    image_id INTEGER REFERENCES images(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_products_account ON products(account_id, id);

-- ربط الدراسة بمنتجها — NULL للدراسات السابقة على الكتالوج (فجوة معلنة،
-- لا اختلاق ربط بأثر رجعي).
ALTER TABLE studies ADD COLUMN product_id INTEGER REFERENCES products(id);
