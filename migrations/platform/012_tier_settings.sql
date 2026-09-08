-- ترحيل ٠١٢: إعدادات الباقات القابلة للتعديل من اللوحة · editable tier settings.
--
-- لماذا (قرار المالك 2026-08-20): جدول الباقات في لوحة الأدمِن يعدّل **السعر
-- وحصّة الدراسات الشهرية** لكل باقة. وأين تُخزَّن القيمة سؤالٌ لا يُخمَّن:
--   • `config/pricing.yaml` ملفٌ داخل صورة النشر — الكتابة عليه تتبخّر عند
--     أول إعادة نشر، والمالك يرى رقمه القديم عائداً بلا سبب ظاهر.
--   • `models.TIER_LIMITS` ثوابتُ كود — لا تُكتَب أصلاً وقت التشغيل.
--   • قاعدة المنصّة تشتقّ مسارها من `SILK_DATA_DIR` (`silk_platform/db.py`)
--     أي أنها على الوحدة المركَّبة — الموضع الوحيد الذي يعيش (الدرس ٤:
--     التخزين على وحدة مركَّبة، لا فقدان صامت).
-- The file lives inside the deploy image; the DB lives on the mounted volume.
--
-- إضافيّ بحت: صفٌّ غائب = لا تجاوز، فتُقرأ القيمة من الملف/الثوابت كما كانت.
-- الملف يبقى **بذرةَ** الأسعار المُقرّة ومرجعَ السقوط، لا سجلّاً حيّاً.
-- A missing row means "no override" — the pre-existing sources still answer.
CREATE TABLE IF NOT EXISTS tier_settings (
    tier            TEXT PRIMARY KEY
                    CHECK (tier IN ('basic','silver','gold','platinum')),
    -- سعرٌ بعملة ملف التسعير (ر.س) — نفس وحدة `*_price` هناك، لا سنتات:
    -- وحدتان لرقمٍ واحد تُنتجان انحرافاً بمقدار ١٠٠ عند أول التباس.
    price           INTEGER NOT NULL CHECK (price >= 0),
    price_annual    INTEGER NOT NULL CHECK (price_annual >= 0),
    -- حصّة الدراسات الشهرية — **البوّابة** التي تفرضها `quota.py` فعلاً،
    -- لا رقم عرض. الأساسية محكومةٌ بسقف مدى الحياة فلا يقرؤها لها أحد.
    monthly_studies INTEGER NOT NULL CHECK (monthly_studies >= 0),
    updated_at      TEXT    NOT NULL,
    updated_by      INTEGER REFERENCES users(id)
);
