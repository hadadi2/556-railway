# النشر على Railway — Deploying Silk on Railway

خدمة Railway واحدة تشغّل كل شيء: `api.py` يقدّم الـ API **والواجهة معًا** (`web/` تُقدَّم على `/`)، فلا حاجة لخدمة واجهة منفصلة.
*A single Railway service runs everything: `api.py` serves both the API and the dashboard (`web/` mounted at `/`).*

المستودع مهيأ بالكامل — Railway يكتشف `Dockerfile` تلقائيًا ويقرأ `railway.json` (فحص صحة على `/health`، إعادة تشغيل عند الفشل).
*The repo is fully pre-configured: Railway auto-detects the `Dockerfile` and reads `railway.json` (healthcheck on `/health`, restart on failure).*

---

## ١ · إنشاء الخدمة — Create the service

1. افتح [railway.com](https://railway.com) → **New Project** → **Deploy from GitHub repo** → اختر هذا المستودع، فرع `main`.
2. Railway يبني الصورة من `Dockerfile` ويشغّل **أمر `CMD` الصورة** حرفياً: `uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="${SILK_FORWARDED_ALLOW_IPS:-*}" --timeout-graceful-shutdown 15` (متغير `PORT` يُمرَّر تلقائيًا).
3. **Settings → Networking → Generate Domain** للحصول على رابط عام (`https://….up.railway.app`).

> **أمر التشغيل مصدرٌ واحد: `CMD` الصورة، و`railway.json` مرآته بايتاً ببايت.**
> (R0، تدقيق 2026-09-01/CI-2) — القفل `tests/test_audit_2026_09_01_r0.py::
> test_railway_start_command_matches_the_image_cmd_byte_for_byte` يفكّ الأمرين
> ويقارنهما، فتعديلُ أحدهما دون الآخر يحمرّ (كان `railway.json` يُثبّت
> `--forwarded-allow-ips=*` حرفياً فيتجاهل `SILK_FORWARDED_ALLOW_IPS` الذي تقرؤه
> الصورة). **لماذا لم يُحذَف `startCommand` من `railway.json`** رغم أن حذفه كان
> هدف التدقيق: قراءةٌ (لا تعديل) للوحة Railway في 2026-09-02 وجدت حقل
> **Settings → Deploy → Custom Start Command** لخدمة `web` — في **الإنتاج
> والتجهيز معاً** — يحمل `sh -c 'uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}'`
> (بلا `--proxy-headers` ولا `--forwarded-allow-ips` ولا `--timeout-graceful-shutdown`؛
> بقيّة PR #27). أولوية Railway: `railway.json` ← اللوحة ← `CMD`. فحذفُ
> `startCommand` من الملفّ يُسلّم الأمرَ للوحة لا للصورة: يسقط `--proxy-headers`
> (كل الزوّار بعنوان البروكسي الواحد — تنقفل خوانق الدخول والدفع عالمياً، §58 H1)
> وختمُ الإغلاق الرشيق (R2). **قرار المالك المطلوب:** فرِّغ الحقل في البيئتين ثم
> احذف `startCommand` من `railway.json` في PR واحد (وحدّث القفل). حتى ذلك الحين
> يبقى الملفّ مرآةً للصورة. وتُثبت وظيفة CI `docker-health` (في
> `.github/workflows/e2e-live-shape.yml`) أن الصورة تُبنى وتُقلِع وتجيب على `/health`
> قبل أي نشر. *The image CMD is the source; `railway.json` mirrors it byte for
> byte (locked). Removal is deferred until the owner clears the dashboard
> Custom Start Command on production and staging — today it still holds a
> flag-less command that would take over. CI builds and boots the image and
> curls `/health` inside it.*

## ٢ · القرص الدائم — Persistent volume (مهم · important)

نظام ملفات Railway **زائل**: بدون قرص دائم تضيع مع كل نشر جديد **أربعة** مخازن — `silk.db` (سجل التحليلات التراكمي)، `silk_store.db` (مخزن الحقائق: تدفقات كومتريد + مؤشرات البنك الدولي المجموعة)، `usage.db` (عدّاد السقف المدفوع)، و`cache/` (ذاكرة طلبات GET) — فيُعاد دفع ثمن الجلب نفسه بعد كل نشر.
*Railway's filesystem is ephemeral — without a volume, all four stores (analyses DB, fact store, usage counter, request cache) are wiped on every redeploy and the same fetches are paid for again.*

1. على الخدمة: **Right-click → Attach Volume** (أو ⌘K → Volume)، واضبط **Mount Path** إلى `/data`. (القرص إعداد خدمة في اللوحة — لا يُعلن في `railway.json`.)
2. أضف متغيّر بيئة واحدًا يوجّه كل المخازن للقرص:

| المتغير | القيمة |
|---|---|
| `SILK_DATA_DIR` | `/data` |

يشتقّ منه تلقائيًا: `/data/silk.db` و`/data/silk_store.db` و`/data/usage.db` و`/data/cache/`. المتغيرات الصريحة (`SILK_DB`, `SILK_STORE_DB`, `SILK_USAGE_DB`, `SILK_CACHE_DIR`) تبقى مدعومة وتفوز عليه فرادى.
*One var derives all four paths; the explicit per-store vars still win individually.*

3. تحقّق بعد النشر: `GET /health` يعيد قسم `storage` بالمسارات المحلولة فعليًا — يجب أن تقع كلها تحت `/data`.
*Verify: `GET /health` now returns a `storage` section with the resolved paths — all should live under `/data`.*

> ⚠️ **لا** تركّب القرص على `/app/data` — المجلد `data/` في المستودع يحوي ملفات CSV مرجعية (بذرة HS، `requirements_l1.csv`) سيحجبها القرص الفارغ ويكسر المحلّل والامتثال. القرص على `/data` والمسارات تُوجَّه بالمتغيرين أعلاه.
> *Never mount the volume over `/app/data` — that directory ships seed CSVs the resolver and compliance agent read; an empty volume would shadow them. Mount at `/data` and redirect via the two env vars.*

## ٣ · متغيّرات البيئة — Environment variables (Variables tab)

القائمة الكاملة مع الشرح في `.env.example`. الأساسية للإنتاج:
*Full annotated list in `.env.example`. Production essentials:*

| المتغير | إلزامي؟ | الغرض |
|---|---|---|
| `SILK_API_KEY` | **نعم في الإنتاج — إلزامي** | مصادقة `X-API-Key` على `/analyze` و`/deepen` **وعلى نقاط قراءة التحليلات المحفوظة** (`/analyses`, `/analyses/{id}`, `/brief`, `/report.docx` — إصلاح C-1). **بدونه القراءةُ مفتوحة للعموم بالتعداد وكل الحماية شكلية** — اضبطه أولاً. |
| `SILK_PAID_DAILY_CAP` | ينصح به | سقف تفعيلات الطبقات المدفوعة يوميًا (429 عند التجاوز؛ يفشل مغلقاً عند خطأ العدّاد — M-2) |
| `SILK_RATE_LIMIT` / `SILK_RATE_WINDOW` | اختياري | حدّ المعدّل بالذاكرة (الافتراضي 120 طلباً/60 ثانية؛ 0 يعطّله — M-1) |
| `SILK_DATA_DIR` | نعم (مع القرص) | توجيه كل المخازن (silk.db، silk_store.db، usage.db، cache/) للقرص الدائم (§٢ أعلاه) |
| `SILK_DB` / `SILK_STORE_DB` / `SILK_USAGE_DB` / `SILK_CACHE_DIR` | اختياري | توجيه مخزن بعينه لمسار مختلف — يفوز على `SILK_DATA_DIR` |
| `COMTRADE_API_KEY` | اختياري | يرفع حد Comtrade إلى ~500 طلب/يوم |
| `GOOGLE_MAPS_API_KEY`, `SEARCH_API_KEY` | اختياري | طبقات الإثراء المجانية بحصة |
| `VOLZA_API_KEY`, `EXPLEE_API_KEY`, `ANTHROPIC_API_KEY` | اختياري (مدفوع) | طبقات `/deepen` والحكم الذكي — **لا تضبطها دون `SILK_API_KEY`** |
| `CORS_ORIGINS` | اختياري | فقط إن نُشرت الواجهة على دومين منفصل (Netlify) |
| `SILK_TRACE_RETENTION_DAYS=30` | موصى به (R7) | كنسُ آثار التشغيل الأقدم من ٣٠ يوماً — يدور ساعياً مع حاصد `/research` (SEC-7) |
| `SILK_FORWARDED_ALLOW_IPS` | **إجراء مالك (R7)** | ١) اقرأ عنوانَ نظير بروكسي Railway من سجلّ الوصول (يبقى مفعّلاً — R7 ينقّح `token=` منه)؛ ٢) ضيّق القيمة إلى ذلك النظير وحده؛ ٣) تحقّق أن خنق المعدّل ما زال يميّز الزوّار (طلبان من جهازين = دلوان). لا تضييقَ بلا الخطوات الثلاث |
| `SILK_HSTS` | تلقائي (R7) | `Strict-Transport-Security` يُرسَل مع أيّ إشارة إنتاجٍ للمنصّة؛ `0` يطفئه، `1` يفرضه |
| `COMTRADE_API_KEY` (ترويسة) | — (R7) | يُرسَل ترويسةً `Ocp-Apim-Subscription-Key` لا معاملَ استعلام. **دخانُ ما بعد النشر:** `sources.comtrade` في `/health` = `key` وتحليلٌ واحد يعيد صفوفَ Comtrade؛ إن رفض المزوّد الترويسة اضبط `SILK_COMTRADE_KEY_IN_QUERY=1` مؤقّتاً وأبلغ |
| `SILK_PLATFORM_SESSION_ABSOLUTE_HOURS` | اختياري (R7) | العمرُ المطلق للجلسة (٧٢٠ ساعة = ٣٠ يوماً افتراضاً) |

## ٤ · التحديث الدوري — Scheduled refresh (اختياري · optional)

أضف متغيّرًا واحدًا لتفعيل تحديث المخزن الدوري داخل الخدمة نفسها:
*One variable turns on the periodic store refresh, in-process:*

| المتغير | القيمة | الأثر |
|---|---|---|
| `SILK_REFRESH_HOURS` | `24` | كل ٢٤ ساعة: مؤشرات البنك الدولي جماعيًا + تسخين مسبق لتدفقات Comtrade (رموز HS المطلوبة مؤخرًا × أسواق الأولوية، السنة المغلقة الأخيرة) |

- التسخين يعمل بميزانية Comtrade اليومية الصلبة نفسها (`COMTRADE_DAILY_BUDGET`) مع backoff يحترم `Retry-After`، ويترك احتياطيًا للطلبات الحية (`SILK_REFRESH_BUDGET_RESERVE`، افتراضي 150) — لا اندفاع على المصادر أبدًا.
- التحليل الحي التالي لنفس `hs+سوق+سنة` يُخدم من المخزن بصفر نداء — وهذا يعالج مباشرة مشكلة التقارير الفارغة بسبب حدّ المعدل.
- **لماذا ليس خدمة cron منفصلة؟** قرص Railway الدائم يُركَّب على **خدمة واحدة فقط** — خدمة منفصلة لا ترى `/data` نفسه فتملأ مخزنًا لا يقرأه أحد. لذا يعمل التحديث خيطًا خلفيًا داخل خدمة الويب. (للتشغيل اليدوي: `railway ssh` ثم `python3 silk_collectors.py`.)
- *Why not a separate cron service? A Railway volume mounts to ONE service; a separate job could not share `/data`. The refresh therefore runs as a daemon thread inside the web service. Manual run: `railway ssh` → `python3 silk_collectors.py`.*

## ٥ · التحقق — Verify

```
https://<domain>/health   → {"status":"ok"}   (+ تحذير إن وُجد مفتاح مدفوع بلا SILK_API_KEY)
https://<domain>/          → الواجهة (اترك حقل «رابط الباك-إند» فارغًا — نفس الخدمة)
```

جرّب تحليلًا من الواجهة ثم أعد النشر (Redeploy) وتأكد أن التحليل ما زال في القائمة — هذا يثبت أن القرص الدائم يعمل.
*Run one analysis, redeploy, and confirm it still appears in the list — that proves the volume works.*

**R9 (2026-09-05) — مسبارُ الحياة ≠ مسبارُ الجهوزية:** `/health` هو ما يقرؤه Railway — غيرُ متزامن
ويقرأ **لقطةً** تُحسَب عند الإقلاع وتُجدَّد كلَّ دورةِ حاصد (`probe_age_s` عمرُها بالثواني)، فلا يفحص
القرصَ ولا يفتح قاعدةً لكلّ طلب ولا يقف خلف مجمّع الخيوط المشبَع. للحقيقة **الآن**:
`https://<domain>/ready` — فحصٌ طازج للقرص والقاعدة، مخنوقٌ بحدّ المعدّل، **503** على سوء التهيئة. ومع
`SILK_REQUIRE_PERSISTENT_DATA_DIR=1` يعيد `/health` نفسُه 503 إن قالت اللقطةُ إنّ الوحدة لم تعد
مركَّبة — إعادةُ التشغيل مقصودة كي تفشل مصيدةُ الإقلاع بصوتٍ عالٍ بدل الكتابة على قرصٍ يُمحى.
النسخُ الاحتياطي الإنتاجيّ: `SILK_BACKUP_HOURS=24` + السحبُ الأسبوعي خارج الوحدة (§٧أ).

## ملاحظات — Notes

- كل push إلى `main` ينشر تلقائيًا (افتراضي Railway؛ يمكن تقييده بـ **Check Suites** ليننتظر نجاح CI).
- ترحيل من Render: هذا الدليل يحلّ محل `render.yaml` (حُذف). لا ترحيل بيانات تلقائي — إن كانت لديك `silk.db` قديمة على قرص Render انسخها إلى قرص Railway عبر `railway ssh` / `scp` قبل إيقاف الخدمة القديمة، فسجل التحليلات تراكمي ولا يُحذف (قاعدة المستودع).
- *Migrating from Render: this guide replaces the deleted `render.yaml`. No automatic data migration — copy any existing `silk.db` from the old Render disk onto the Railway volume before decommissioning; the analyses track record is cumulative and must never be lost.*

## ٦ · بوابة قبول PDF/RTL قبل الإصدار — PDF/RTL release-acceptance gate (§3/§4)

المُسلَّم النهائي PDF غير قابل للتحرير (§3)، وكامله RTL (§4). محرّك التحويل
(LibreOffice/`soffice`) وخطّ عربي الشكل يجب أن يكونا حاضرين على النشر — وهذا
**لا يُلتقَط هرمتياً**.

**تبعيةٌ ثالثةٌ منذ 2026-08-27: `pymupdf`.** حارسُ اتجاه الأقواس
(`silk_reports._pdf_bracket_check`) يقيس هندسةَ الـPDF عبر `fitz`؛ بلا الحزمة
يرتدّ الحارسُ صامتاً فتُسلَّم المستنداتُ بلا فحص. صارت في `requirements.txt`
فتُثبَّت مع بقية الاعتماديات — لا خطوةَ نشرٍ إضافية. (نُقِلت **بعد** معايرة
المقياس: النسخةُ السابقة منه كانت ترفض المستندَ السليم، فتفعيلُها قبل ذلك كان
سيُسقِط كلَّ تصدير PDF عربيّ بـ503. التفصيل في `docs/DEEP_RESEARCH_DECISIONS.md`.)

**طبقةُ نصّ الـPDF مُطبَّعةٌ تلقائياً** (`SILK_PDF_TEXTLAYER_FIX`، الافتراض
مُفعَّل): بلا التطبيع يُسلَّم PDF سليمُ الورقة مبعثرُ النصّ المنسوخ/المبحوث
عنه. لا خطوةَ نشرٍ إضافية — يعمل مع `pymupdf` المثبَّتة أصلاً.

**افحص متغيّراً واحداً عند النشر:** `SILK_PDF_BRACKET_FAIL_MAX` غيّر
دلالته (صار يعدّ **أزواجاً مقلوبةً هندسياً**، افتراضُه صفر). إن كان
مضبوطاً في بيئة Railway بقيمةٍ عاليةٍ للالتفاف على الإنذارات الكاذبة
السابقة، أزِله — وإلا صار الحارسُ مُعطَّلاً بصمت.

**مثبَّتان في الصورة (`Dockerfile`):** `libreoffice-writer` + `fonts-hosny-amiri`
+ `fontconfig` يُثبَّتان وقت البناء، فيتوفّر `soffice` وخطّ Amiri العربي على
النشر ويعمل زرّ «تصدير التقرير (PDF)» حيّاً (لا فرع 503). نفس التبعية مثبَّتة
في وظيفة CI `e2e-live-shape` كي يؤكّد المتصفّح الحقيقي توقيع `%PDF`. عند ترقية
صورة الأساس تحقّق أن الحزمتين ما زالتا تُثبَّتان (`soffice --version` و
`fc-list | grep -i amiri`). قبل أي إصدار:

1. **على النشر الحيّ**: `python3 tools/post_deploy_smoke.py https://<host> --key <SILK_API_KEY>`
   — الخطوة ٥ تضرب `GET /analyses/{id}/report.pdf` فعلياً (٥٠٣ = محرّك التحويل
   غائب). يجب أن يعيد توقيع `%PDF`. المفتاح يُقرأ من `SILK_LIVE_API_KEY` افتراضاً.
   **بوّابة المصانع (R0، CI-6):** اضبط `SILK_SMOKE_EMAIL`/`SILK_SMOKE_PASSWORD`
   (أو `--platform-email/--platform-password`) لحساب مصنعٍ حقيقي فيُضاف مسارٌ
   للقراءة فقط: دخول ← `GET /platform/me` ← `GET /platform/studies` ←
   `GET …/report` (عرض التقرير) لأحدث دراسة مكتملة — لا إطلاق ولا حذف، ولا
   تشغيل لمحرّك PDF. بلا السرّين يُعلَن المسار «متخطّى» صراحةً (ليس نجاحاً)؛
   أحدُهما وحده = خطأ ضبط يُفشل الفحص بسببه. في وظيفة `post-deploy-smoke.yml`
   يُمرَّران كسرَّين اختياريَّين (Settings → Secrets → Actions).
2. **على التجهيز/الـstaging** (حيث `soffice` وخطّ عربي مثبّتان):
   `SILK_PDF_ACCEPTANCE=1 python3 -m pytest tests/test_report_output_overhaul.py::test_pdf_rtl_geometry_and_arabic_font -q`
   — يفشل **بصوتٍ عالٍ** إن غاب الخطّ العربي أو محرّك التحويل أو أداة قياس
   الـPDF (pdfplumber/pdftotext)، ويقيس أن ≥٩٥٪ من الأسطر القصيرة المتعرّجة
   تنحاز يميناً (الفحص الحاسم لانقلاب `jc` المنطقي في الـPDF المُصيَّر).
   **لا يجوز أن يبقى هذا الاختبار مُتخطّى قبل الإصدار** — خطّ النشر يضبط
   `SILK_PDF_ACCEPTANCE=1` فيتحوّل التخطّي إلى فشل صريح.

## ٧ · النسخ الاحتياطي والاسترجاع — backup & restore (تدقيق 2026-08-27، البند ١٧)

> **نصفُ نسخةٍ احتياطية ليس نسخةً احتياطية.** كان الريبو يملك مسارَ **أخذ**
> النسخة (`silk_backup.run_backup`، `GET /ops/backup`) بلا أيّ إجراء **استرجاع**
> موثَّق ولا تمرين جافّ — أي أن أول مرّة يُجرَّب فيها الاسترجاع كانت ستكون يوم
> الكارثة، على قاعدة إنتاجٍ حيّة، بلا خطوةٍ مكتوبة. هذا القسم يغلق ذلك.

### ٧أ — التفعيل (قرار مالك، مطفأ افتراضاً)

```bash
SILK_BACKUP_HOURS=24        # نسخة ليلية داخل نفس العملية (لا خدمة cron ثانية)
SILK_BACKUP_DIR=/data/backups   # الافتراضي؛ يجب أن يكون على **نفس الوحدة المركَّبة**
SILK_BACKUP_KEEP_DAYS=7
```

نسخة يدوية فورية (محروسة بالمصادقة): `curl -sS "$BASE/ops/backup" -H "$(H)"`.
الردّ **مانيفست صادق**: ما نُسخ بحجمه المقيس فعلاً، وما فشل ولماذا. طبعةٌ لكل
مخزن باسم `‏<name>.<YYYY-MM-DD>.db` — الأسماء: `silk` (التحاليل) · `store`
(الحقائق) · `usage` (المحاسبة) · `ops_errors` · `watchdog` · `platform`.
**R5 (2026-09-05):** طبعةٌ سابعة `platform_files.<YYYY-MM-DD>.tar` = أرشيفُ صور المصانع
المرفوعة (صفوفُ `images` بلا ملفّاتها كانت نسخةً تشير إلى فراغ)، وكلُّ طبعة قاعدةٍ تُفحَص
بـ`PRAGMA integrity_check` قبل اعتمادها (طبعةٌ فاسدة لا تصل المجلّد).

**السحبُ خارج الوحدة (أسبوعياً — قرارك وروتينك):** الطبعاتُ على الوحدة نفسها التي تحميها،
فتلفُ الوحدة يمحوها معاً. من جهازك:
```bash
for s in silk store usage ops_errors watchdog platform platform_files; do
  curl -fsS -o "backups/$s.$(date +%F).bak" "$BASE/ops/backup/$s" -H "X-API-Key: $KEY"
done
python3 tools/verify_backup.py --dir backups     # بعد إعادة تسمية الامتدادات .db/.tar
```

### ٧ب — التحقّق **قبل** الحاجة (التمرين الجافّ — افعله مرّةً بعد التفعيل)

```bash
python3 tools/verify_backup.py            # قراءة فقط: يفحص أحدث طبعة لكل مخزن
```

الأداة تفتح كل طبعة `mode=ro`، تشغّل `PRAGMA integrity_check`، وتطبع عدد صفوف
الجداول الحرجة (`analyses` مثلاً) وتاريخ الطبعة. **نسخةٌ لم تُفحَص ليست نسخة**:
هذا هو التمرين الجافّ الذي يكشف الطبعة الفاسدة قبل يوم الكارثة لا بعده.

### ٧ج — الاسترجاع (الإجراء الفعلي)

الاسترجاع **استبدال ملف** — لا سحر فيه، لكن ترتيبه يهمّ:

1. **أوقف الكتابة أولاً.** أوقف الخدمة من لوحة Railway (أو `Restart` بعد ضبط
   نسخةٍ صفرية). استرجاعٌ فوق قاعدةٍ مفتوحة يخلط صفحاتٍ قديمة بجديدة.
2. **احفظ الحاليّ قبل الاستبدال** (حتى لو بدا تالفاً — قد يحوي صفوفاً أحدث من
   النسخة):
   ```bash
   cp /data/silk.db /data/silk.db.before-restore-$(date +%F-%H%M)
   ```
3. **استبدل من الطبعة المختارة** — بالشيفرة المُختبَرة (R5) التي تفحص السلامة أولاً وترفض
   الكتابة فوق وجهةٍ قائمة إلا بـ`overwrite=True` وتزيل بقايا WAL:
   ```bash
   python3 -c "import silk_backup; print(silk_backup.restore('silk', '2026-08-27', '/data/silk.db', overwrite=True))"
   python3 -c "import silk_backup; print(silk_backup.restore('platform_files', '2026-08-27', '/data/platform_files', overwrite=True))"
   ```
   (أو يدوياً: `cp /data/backups/silk.2026-08-27.db /data/silk.db && rm -f /data/silk.db-wal /data/silk.db-shm`.)
   ملاحظة WAL (R5): المخازنُ تعمل في وضع WAL؛ الطبعاتُ نفسُها ملفٌّ واحد في وضع DELETE.
   الرجوعُ عن WAL: `SILK_SQLITE_JOURNAL_MODE=delete` ثم إعادةُ الإقلاع (تقلب الملفّ الدائم).
4. **افحص قبل الإقلاع:**
   ```bash
   sqlite3 /data/silk.db "PRAGMA integrity_check; SELECT COUNT(*) FROM analyses;"
   ```
5. **أقلِع وتحقّق حيّاً:** `GET /health` ⇒ `storage.persist_guard: true` و
   `is_mount: true`، ثم `GET /analyses?limit=5` يُعيد صفوفاً فعلاً.

> **قانون لا يُكسَر:** الاسترجاع لا يُشغَّل «تجربةً» على الإنتاج. جرّبه على
> نسخةٍ محلية من ملف الطبعة (الخطوة ٧ب تكفي للتحقّق الدوري)، ولا تحذف
> `‏*.before-restore-*` حتى تتأكّد من الحيّ (قانون «لا حذف بيانات»).

**قيدٌ معلَن:** المخازن الستّة تُنسَخ كلٌّ على حدة، فطبعتان لمخزنين مختلفين
قد تختلفان بثوانٍ — لا لقطة ذرّية عبر المخازن كلها. عملياً لا يضرّ (المخازن
مستقلّة دلالياً)، لكنه يُذكَر كي لا يُفترَض خلافه.
