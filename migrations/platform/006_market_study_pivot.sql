-- 006 — التحوّل إلى دراسات السوق (قرارات مالك 2026-08-17) · market-study pivot.
--
-- قرارات المالك الثلاثة حرفياً: (١) المنصّة للدراسات فقط والتنقيب عن العملاء
-- يُحذف نهائياً؛ (٢) «ربط آلي بالمحرك من واجهة العميل» مع عداد وقت وحد شهري
-- وإشراف أدمِن؛ (٣) الباقة وحدها البوابة — لا خصم محفظة لكل دراسة.
--
-- إضافي فقط (قاعدة الترحيلات): لا DROP ولا تعديل صفوف. جداول التنقيب اليتيمة
-- (prospects, drafts, comparison_funnels + جدولا وصله, email_queue,
-- smtp_configs, consent_registry, suppression_list, system_settings) تبقى في
-- المخطّط موثَّقةً هنا كيتيمة — الشيفرة التي كانت تكتبها حُذفت نهائياً بقرار
-- المالك، وبياناتها القائمة محفوظة (قانون «لا حذف بيانات» يعلو كل شيء).
--
-- الدراسة تصبح طلب دراسة سوق حقيقياً:
--   product        — المنتج (إلزامي للإطلاق؛ يُفرَض في النقطة لا المخطّط لأن
--                    ALTER الإضافي لا يضيف NOT NULL، وصفوف عهد الحملات القديمة
--                    بلا منتجٍ شرعاً).
--   market_pref    — سوق مستهدف اختياري (iso3)؛ فارغ = ترتيب المحرّك الكامل.
--   hs_code        — رمز HS اختياري؛ يتجاوز محلّل الرموز (نفس عقد /deepen).
--   image_id       — صورة المنتج (اختيارية) من مخزن صور الحساب القائم.
--   analysis_id    — معرّف نتيجة المحرّك في silk.db (قاعدة أخرى — لا FK).
--   run_started_at / run_finished_at — ختما التشغيل المقيسان (ETA الصادق
--                    يُشتق منهما وقت القراءة؛ لا عمود ETA — تجميده كذبة مؤجلة).
--   run_error      — سبب فشل آخر محاولة، معلَنٌ للمصنع (الفشل يعيد الدراسة
--                    مسودّةً — لا «مكتملة» كاذبة أبداً).
ALTER TABLE studies ADD COLUMN product         TEXT;
ALTER TABLE studies ADD COLUMN market_pref     TEXT;
ALTER TABLE studies ADD COLUMN hs_code         TEXT;
ALTER TABLE studies ADD COLUMN image_id        INTEGER REFERENCES images(id);
ALTER TABLE studies ADD COLUMN analysis_id     INTEGER;
ALTER TABLE studies ADD COLUMN run_started_at  TEXT;
ALTER TABLE studies ADD COLUMN run_finished_at TEXT;
ALTER TABLE studies ADD COLUMN run_error       TEXT;
