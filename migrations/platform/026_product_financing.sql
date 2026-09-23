-- 026 — مدخلا تمويل مخزون التجربة على بطاقة المنتج · product financing inputs (تقرير ٧ §3.5).
--
-- **الفجوة:** تمويلُ مخزون الشحنة التجريبية مقياسٌ منفصلٌ عن التعادل والاسترداد،
-- ولا مدخلَ له: كلفةُ التمويل = قيمةُ الشحنة × معدّلُ التمويل السنويّ × مدّةُ
-- التحصيل ÷ 365. **لا قيمةَ افتراضية** — `NULL` تعني «لم يُدخِلها المصنع»
-- ويبقى البندُ فجوةً تسمّي المدخل الناقص. إضافي فقط. Additive only.
ALTER TABLE products ADD COLUMN financing_rate_pct REAL;
ALTER TABLE products ADD COLUMN collection_days REAL;
