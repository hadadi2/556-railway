-- 014 — الحقولُ الاقتصادية على بطاقة المنتج · product economics (الموجة C، E-04).
--
-- **الفجوة:** `ProductCard` في المحرّك يطلب `cost_per_unit` إلزامياً و`tier`
-- و`monthly_capacity`، بينما كتالوجُ المنصّة يحمل `(name, description,
-- hs_code, image_id)` فقط. فالحقلُ كان **غيرَ قابلٍ للتعبئة** حتى لو وُصِّل،
-- ونتيجتُه المقيسة: `margin_waterfall` صفر · `landed_cost` صفر · `correlate`
-- صفر · SAM/SOM فجوةٌ دائمة على **كل** دراسة مصنع.
--
-- **ولا قيمةَ افتراضية لأيٍّ منها.** تكلفةُ الوحدة والطاقةُ الشهرية أرقامُ
-- المصنع نفسه لا أرقامٌ منشورةٌ نبحث عنها — فهي **فجوةُ إدخال** لا فجوةُ بحث،
-- وملؤها بالتقدير اختلاقٌ لبيانات العميل (§٦-١ من جرد التدقيق). `NULL` تعني
-- «لم يُدخِلها المصنع» ويُقال ذلك صراحةً في التقرير.
--
-- إضافي فقط — لا مساس بأي صف قائم. Additive only.
ALTER TABLE products ADD COLUMN cost_per_unit REAL;
ALTER TABLE products ADD COLUMN cost_unit TEXT;
ALTER TABLE products ADD COLUMN tier TEXT;              -- premium|standard|economy
ALTER TABLE products ADD COLUMN monthly_capacity REAL;
ALTER TABLE products ADD COLUMN shipping_per_unit REAL;
ALTER TABLE products ADD COLUMN certifications TEXT;    -- CSV: HALAL,ISO22000
