# SILK forensic audit evidence — 8143125

هذه أدلة التقرير `SILK_FULL_FORENSIC_AUDIT_20260908.md` وليست إصلاحات للمنصة.

الـSHA المستهدف: `8143125ea37660986d616007ca1df355ad332b80`، فرع `main` عند baseline. بدأ الحصر في 2026-09-07 UTC؛ تاريخ اسم التقرير هو 2026-09-08 وفق الطلب. الطوابع الزمنية الأصلية محفوظة ولا تعدل لتعويض المنطقة الزمنية.

النتائج المثبتة:25 finding؛23 منها witnesses محلية، و015 من GitHub و023 من AST/static structure. F01 في JSON يقابل SILK-AUDIT-001 وهكذا. **نجاح assertions في الشواهد يعني أن الخطأ موجود؛ ليست اختبارات نجاح الإصلاح.**

| ملف | الغرض |
|---|---|
| repository-baseline.json | الجذر والفرع وSHA وremote وstatus/log قبل إضافات التقرير |
| repository-map.csv /inventory.json /repository-analysis.json | جميع752 ملفاً؛ أحجام/مجالات/رموز/import graph وduplicate groups |
| api-endpoints.csv |99 decorated route definitions بما فيها route اختبار مشروطة؛ guards المباشرة ليست تحليل تفويض كاملاً |
| audit-findings.json | findings المنظمة بكل severity/evidence/fix/test |
| reproduce_findings.py /reproduced_findings.json /reproduce.log |23 شواهد خطأ في بيئة مؤقتة وبلا مزود خارجي |
| forensic_checks.py /forensic-checks.json |26 migration وتطبيق ثانٍ صفر، مخططات/PRAGMAs/indexes/FKs، HS fixtures،JS/HTML/assets |
| queue_capacity_probe.py /queue-capacity.json |dispatcher وSQLite فعليان؛ payload انتظار20ms محاكى، cap3؛ ليس1000 AI concurrent |
| http_smoke.py /http-smoke.json |37 قراءة HTTP/asset إلى خادم خاص بالتدقيق ثم إيقافه |
| pytest-full.log/xml |4822 passed؛63 skipped؛0 failed/xfail؛CLI238.63s |
| pytest-real-server.log/xml |21 passed؛0 failed/skipped/xfail؛CLI184.40s |
| test-skips.json |أسباب التخطيات مصنفة |
| ruff-syntax.json /ruff-security.json |0 syntax diagnostics؛24 security candidates جرى triage لها، ليست24 ثغرة |
| formatter-summary.json |exit1:547 would reformat/73 formatted؛style-only؛يشمل Markdown code blocks؛لا تعديل |
| dependency-audit.json /dependency-audit.stderr.log |محاولة scanner محلي خرجت0 لكن dependencies=[]؛دليل غير كافٍ |
| github-verification.json /github-job-steps.json |main protection وCI/E2E/Docker step conclusions علىSHA |
| runtime-versions.json |نسخ البيئة الفعلية المباشرة؛Python3.12 مقابلCI/Docker3.11 |
| external-source-checks.json |المصادر الأولية للأسعار والتطبيع وعقد البيانات، مع تاريخ القراءة |
| credential-shape-scan.json |فحص محدود لأربعة أنماط token/private-key في752 ملفاً،0 تطابق؛لا يغني عن full-history gitleaks |
| audit-limitations.json |حدود browser/live providers/Railway/history/security scanner |
| evidence-manifest.json |SHA256/حجم كل ملف مشحون؛ليس توقيعاً من طرف مستقل |

ملف formatter raw التفصيلي8MB تقريباً بقي من وسيطات التدقيق ولم يُنسخ إلى المستودع؛ الملخص يكفي لأنه style-only. ملفات DB المؤقتة وآثار المستخدم ومفاتيح production غير مشحونة. قائمة import roots الخام ليست قائمة dependencies قابلة للحذف.

لإعادة الإنتاج استخدم checkout معزولاً على SHA المحدد وبيئة Python جديدة. لا تستعمل DB المستخدم أو production credentials. لتشغيل الحزم يلزم متطلبات المشروع؛ تثبيت dependencies يتصل بمصادر الحزم وقد يختلف transitive resolution عن snapshot. استخدم Python3.11 لمطابقة Docker/CI؛ التشغيل المحلي الموثق استعمل3.12.13 مع direct pins المطابقة.

```bash
# نفذ من جذر checkout التدقيق المعزول.
python3 -m venv /tmp/silk-forensic-env
/tmp/silk-forensic-env/bin/python -m pip install -r requirements.txt -r requirements-ci.txt

# لا تعِد الكتابة فوق الأدلة الأصلية؛ اختر مجلد نتائج جديداً.
export SILK_AUDIT_REPO="$PWD"
export SILK_AUDIT_OUTPUT_DIR="$(mktemp -d /tmp/silk-forensic-results-XXXXXX)"

/tmp/silk-forensic-env/bin/python audit/20260908/reproduce_findings.py
/tmp/silk-forensic-env/bin/python audit/20260908/forensic_checks.py
/tmp/silk-forensic-env/bin/python audit/20260908/queue_capacity_probe.py
/tmp/silk-forensic-env/bin/python audit/20260908/http_smoke.py
```

إن كان checkout على SHA الأصلي لا يحمل ملفات audit المضافة بعده، انسخ **هذه الأدوات فقط** إلى مجلد مستقل واستعمل `SILK_AUDIT_REPO` لتوجيهها إلى checkout الأصلي و`SILK_AUDIT_OUTPUT_DIR` للناتج. لا تغيّر SHA ولا تنقل ملفات التطبيق من التقرير.

السكربتات تزيل متغيرات SILK/Anthropic/Comtrade/Search وDATABASE_URL الموروثة قبل import التطبيق، وتستعمل SQLite مؤقتة. witnesses والطابور يمنعان requests الخارجي أثناء التنفيذ؛ `http_smoke` يستعمل loopback عبر LiveShapeServer ومزوّداته المعزولة. `forensic_checks` لا يستدعي نموذجاً، وHTTP الاختياري يحتاج URL loopback صريحاً يملكه التدقيق. أداة المسح/الحزم لا تقع ضمن هذا المنع؛ لا تشغّل acceptance live مدفوعاً باسم إعادة الشواهد.

لـpytest خذ بيئة نظيفة من مفاتيح production، وضع `SILK_DATA_DIR` في مجلد مؤقت واتبع fixture/conftest المشروع. رُتبة الخادم تتطلب أدوات PDF/الخطوط الموجودة في CI لبعض الاختبارات؛ النتائج المحلية المرفقة تبين ما نجح، ولا تعد metadata بدل dependency install:

```bash
python3 -m pytest tests/ -q --junitxml=/tmp/silk-pytest-full.xml
SILK_RUN_E2E=1 python3 -m pytest tests/test_rung2_real_server.py tests/test_rung2_factory_language_flow.py tests/test_rung2_restart_drill.py tests/test_rung4_platform_real_bridge.py -q --junitxml=/tmp/silk-pytest-real-server.xml
python3 -m ruff check --select E9,F63,F7,F82 --no-cache .
```

هذه commands قابلة للمراجعة، وليست ادعاء تشغيل مزودين حقيقيين. لا تجمع عدد اختبارات التشغيلين كمجموع فريد. مدة الطابور الاصطناعي/RSS ليست latency/memory لدراسة تجارية. النماذج والأسعار فرضيات مؤرخة يجب إعادة التحقق منها عند الاستخدام لاحقاً.

كل URLs الشيفرة في التقرير مثبتة على SHA. GitHub evidence read-only؛ لم تُغير الحماية/الإعدادات. HTTP المحلي نجح، لكن Browser Work منع الوصول إلى loopback بـERR_BLOCKED_BY_CLIENT؛ لم يحصل visual/console/keyboard check محلي جديد. وظائف browser/PDF/Docker على CI نجحت علىSHA، وهي دليل منفصل. Railway dashboard/config/replicas/invoices وقاعدة الإنتاج والتاريخ الكامل للأسرار ما زالت تحتاج وصول قراءة مناسباً.
