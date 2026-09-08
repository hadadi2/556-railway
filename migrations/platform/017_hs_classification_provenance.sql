-- ترحيل ٠١٧: مصدرُ التصنيف — HS classification provenance.
--
-- لماذا (تدقيق «حلاوة طحينية» 2026-08-30): كان القرارُ يُبنى على **استنتاج**
-- مصدرِ الرمز من شكل الطلب (`hs_source="catalog"` يُلصَق في جسر المنصّة لكلّ
-- رمزٍ مخزَّن) لا على واقعةٍ مسجَّلة. فرمزٌ كتبه المصنعُ بيده في الكتالوج،
-- ورمزٌ حسمته الرؤيةُ من صورة العبوة، ورمزٌ ورثته صفوفٌ قديمة — ثلاثتُها
-- تصل المحرّكَ بالوسم نفسه وتُعامَل المعاملةَ نفسها. ومن هنا جاء التناقضُ بين
-- قرارين حيّين: الدرس ١٢٠ («رمزُ كتالوجٍ مُعادٌ ثقتُه غير معلومة») والدرس ٢٠٩
-- («رمزٌ يكتبه المصنعُ يُعتمَد كما هو») — كلاهما مُنفَّذ على المسار نفسه.
--
-- The trust decision was inferred from request shape instead of recorded as a
-- fact. These columns make provenance data, so the two standing owner rulings
-- stop contradicting each other on one code path.

-- على المنتج: كيف وصل رمزُه؟ `manual` (كتبه إنسان) | `image` (حسمته الرؤية من
-- العبوة) | `unknown` (صفوفٌ سابقة لهذا الترحيل — تواجه البوّاباتِ كاملةً كما
-- اليوم حرفياً؛ لا ترقيةَ صامتة لثقةِ صفٍّ قديم).
ALTER TABLE products ADD COLUMN hs_source TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE products ADD COLUMN hs_set_at TEXT;

-- على الدراسة: بأيّ طريقةٍ حُسِم بندُها فعلاً — تُكتَب من عقد التصنيف الواحد
-- (`silk_hs_pipeline.classification_method`). قيمتُها للتشخيص والإفصاح: تقريرٌ
-- بُني على `user_confirmed` ليس تقريراً بُني على `deterministic_exact`،
-- والفارقُ يجب أن يُقرأ بعد شهرٍ لا أن يُستنتَج.
ALTER TABLE studies ADD COLUMN hs_classification_method TEXT;
