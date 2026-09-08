FROM python:3.11-slim

WORKDIR /app

# R7 (SEC-8/EXT-15): الخطوطُ من **إيداعٍ مثبَّت** في google/fonts وبصماتُها تُفحَص
# (`docker/fonts.sha256`) — كان التنزيلُ من `main` المتحرّك بلا تحقّق؛ والخادمُ
# يعمل بمستخدمٍ غير مميّز `silk` (uid 10001) عبر `docker/entrypoint.sh`.
ARG GOOGLE_FONTS_COMMIT=5e35378e6bda803962ee6fd257e444a7d459660d
COPY docker/fonts.sha256 /tmp/fonts.sha256

# محرّك تحويل PDF غير القابل للتحرير (§3، اتفاق المالك): LibreOffice headless
# (soffice) + خطّ عربي الشكل (Amiri) — بدونهما يقع GET /analyses/{id}/report.pdf
# في فرع 503 «محرّك التحويل غير متاح» فيصبح زرّ «تصدير التقرير (PDF)» ميتاً حياً.
# راجع docs/DEPLOY_RAILWAY.md §6 (بوابة قبول PDF/RTL) و silk_reports.docx_to_pdf.
# The final client deliverable is a non-editable PDF; LibreOffice + an Arabic
# font must ship on the image or the PDF endpoint 503s live.
# §7 (قرار المالك): العائلة الرسمية IBM Plex Sans Arabic (OFL) — تُنزَّل من
# مستودع google/fonts الرسمي (Regular+Bold+SemiBold). بلا هذا الخطّ يبدّل
# LibreOffice صامتًا فيسقط قبول §7؛ curl -f يُفشِل البناء إن تعذّر التنزيل.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libreoffice-writer fonts-hosny-amiri fontconfig curl ca-certificates \
    && mkdir -p /usr/share/fonts/truetype/ibmplex \
    && for w in Regular Bold SemiBold; do \
         curl -fsSL -o "/usr/share/fonts/truetype/ibmplex/IBMPlexSansArabic-$w.ttf" \
           "https://raw.githubusercontent.com/google/fonts/${GOOGLE_FONTS_COMMIT}/ofl/ibmplexsansarabic/IBMPlexSansArabic-$w.ttf"; \
       done \
    && (cd /usr/share/fonts/truetype/ibmplex && sha256sum -c /tmp/fonts.sha256) \
    && fc-cache -f \
    && useradd -r -u 10001 -d /app -s /usr/sbin/nologin silk \
    && setpriv --version \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=silk:silk . /app
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8000

# Railway يمرّر PORT وقت التشغيل؛ محليًا يسقط إلى 8000.
# Railway injects PORT at runtime; falls back to 8000 locally.
# §58 H1: خلف بروكسي حافة Railway — بلا `--proxy-headers` يكون
# `request.client.host` عنوانَ البروكسي الواحد لكل الزوّار، فتنقفل عدّادات
# التقييد العامة (checkout) عالمياً بعشرة طلبات من أي شخص. الحاوية لا تُبلغ
# إلا عبر البروكسي، فالوثوق بترويسات التمرير هنا هو المعيار.
#
# تدقيق 2026-08-27 (البند ١٣): `*` يثق بترويسة `X-Forwarded-For` من **أي**
# نظير — فمن يبلغ الحاوية مباشرةً يوماً (خدمة ثانية في نفس المشروع، منفذ
# مكشوف) ينتحل أي IP فيلتفّ على خنق المعدّل ويسمّم سجلّ التدقيق.
#
# **لماذا بقي `*` هو الافتراض:** تضييقه لنطاقاتٍ خاصة يتطلّب معرفة النطاق
# الذي يتّصل منه بروكسي حافة Railway فعلاً — وهو غير قابل للقراءة من
# المستودع. وتضييقٌ خاطئ يُعيد **حادثة §58 H1 نفسها** (كل الزوّار يصيرون
# عنوانَ البروكسي فينقفل خنق المعدّل عالمياً) — وهي أسوأ من الخطر النظري
# الذي نُغلقه. فالقيمة صارت **متغيّراً بيئياً** بدل ثابتٍ في الصورة:
#   ١) اقرأ عنوان النظير الفعلي من سجلّ الطلبات على النشر.
#   ٢) اضبط `SILK_FORWARDED_ALLOW_IPS` على ذلك النطاق وحده.
#   ٣) تحقّق أن `X-Forwarded-For` ما زال يُقرأ (خنق المعدّل يعمل لكل زائر).
# بلا هذه الخطوات الثلاث لا تُضيَّق القيمة — تضييقٌ غير متحقَّق منه أسوأ من
# الوضع القائم. Configurable now; narrowing requires verifying Railway's
# actual proxy peer range first (a wrong narrowing re-opens incident §58 H1).
ENV SILK_FORWARDED_ALLOW_IPS="*"
# R2 (قرار المالك 2026-09-02): `--timeout-graceful-shutdown 15` — بلا حدٍّ كان
# uvicorn ينتظر طلباً متزامناً طويلاً (تحليل بالدقائق) إلى الأبد قبل حدث الإغلاق،
# فيقتله Railway قبل أن يختم مُشرِف التشغيلات دراساتِ العملية «انقطعت».
# 15 ثانية في الملفّين (هنا وفي railway.json) — لا 10.
CMD ["sh", "-c", "exec /app/docker/entrypoint.sh uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=\"${SILK_FORWARDED_ALLOW_IPS:-*}\" --timeout-graceful-shutdown 15"]
