// رُتبة ٣ — لغة تقارير المصنع في متصفّح حقيقي (rung 3: factory report language).
//
// > التدفّق الذي طلبه المالك حرفياً، بالنقر لا بالـHTTP:
// >   إعدادات المصنع ← تغيير لغة التقارير ← حفظ ← إنشاء دراسة ← لقطة اللغة
// >   ← توليد التقرير ← DOCX نهائي ← PDF نهائي — **باللغتين**.
//
// ويؤكّد ثلاثة قيود بنيوية إضافية:
//   (١) تدفّقُ إنشاء الدراسة يعرض لغةَ التقرير **مؤشّراً** ولا يسأل عنها (§15).
//   (٢) بطاقةُ «لغة تقارير المصنع» منفصلةٌ عن بطاقة «لغة الواجهة» — قلبُ
//       الواجهة لا يغيّر لغة التقارير، وهو الخلطُ الذي يمنعه القرار.
//   (٣) تبديلُ اللغة بعد إطلاق دراسة لا يمسّ لقطتها.
//
// المحرّك خلف مقعد SILK_PLATFORM_FAKE_ENGINE (يضبطه LiveShapeServer) — والمقعد
// يُنتِج سرداً بلغة الدراسة وبالبنية المرقّمة القانونية، فما يُنزَّل هنا مصنوعٌ
// حقيقيّ الشكل. CommonJS عمداً (NODE_PATH) كبقية التدفّقات.

const { chromium } = require("playwright");
const fs = require("fs");
const os = require("os");
const path = require("path");

const BASE = process.env.BASE_URL;
const FACTORY_EMAIL = process.env.FACTORY_EMAIL || "owner@factory-a.local";
const PASSWORD = process.env.PLATFORM_PASSWORD;

if (!BASE || !PASSWORD) {
  console.error("MISSING BASE_URL/PLATFORM_PASSWORD env");
  process.exit(2);
}

function ok(name, detail) { console.log(`OK ${name} ${detail || ""}`); }
function fail(name, detail) {
  throw new Error(`STEP FAILED: ${name} — ${detail || ""}`);
}

// نثرٌ عربيٌّ = ثلاث كلماتٍ عربية متتالية فأكثر (نفس عتبة `silk_i18n`:
// كلمةٌ عابرة أو اسمُ علَمٍ ليس نثراً).
const AR_RUN = /[؀-ۿ]+(?:[\s،]+[؀-ۿ]+){2,}/;

async function login(page, email) {
  await page.goto(BASE + "/platform.html",
    { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForSelector("#loginView:not(.hide) #email", { timeout: 15000 });
  await page.fill("#email", email);
  await page.fill("#pw", PASSWORD);
  await page.click("#loginBtn");
  await page.waitForSelector("#appView:not(.hide)", { timeout: 15000 });
}

async function gotoSection(page, key) {
  await page.click(`#sideNav button[data-key="${key}"]`);
  await page.waitForSelector(`#${key}Panel.on`, { timeout: 8000 });
}


/** صفُّ دراسةٍ بعينها في الجدول — الخليّةُ الأولى معرّفُها.
 *
 * `.first()` على أزرار الجدول يفترض ترتيباً لا يضمنه شيء: مع صفَّين مكتملين
 * (إنجليزيّ ثمّ عربيّ) قد يقع النقرُ على **الدراسة الخطأ**، فيمرّ الاختبار
 * على مصنوعٍ ليس الذي يزعم فحصَه. */
function studyRow(page, id) {
  // تعبيرٌ **مُرسًى** على نصّ الخليّة كلِّه: `:text-is` يطابق أصغرَ عنصرٍ
  // يحمل النصّ (وهو `span.num` داخل الخليّة لا الخليّةُ نفسها)، و`has-text`
  // يطابق جزئياً فيلتقط «1» من «12». الإرساءُ يعمل مع الغلاف وبدونه.
  return page.locator("#studiesBody tr").filter({
    has: page.locator("td:first-child")
      .filter({ hasText: new RegExp(`^\\s*${id}\\s*$`) }),
  });
}

/** إعدادات المصنع: اختر لغة التقارير واحفظ — المسار الذي يعيشه المصنع. */
/** امسح صندوقَ الرسالة **قبل** الفعل، ثم انتظر رسالةً جديدة.
 *
 * لماذا: `say()` في `web/platform.html` يزيل صنفَ التوهّج بعد **٧ ثوانٍ**
 * (`setTimeout(..., 7000)`). فخطوةٌ تنتظر `#appMsg.on.good` بعد خطوةٍ ناجحةٍ
 * سابقةٍ قد تطابق **رسالةَ الخطوة السابقة** فتمضي قبل أن يكتمل فعلُها هي —
 * ثم تقرأ حالةً لم تُكتَب بعد. رُصِد حيّاً على CI: تشغيلتان على نفس المدى،
 * إحداهما خضراء والأخرى تسقط بـ`study_not_created` بعد `set_report_language`
 * مباشرة (أي داخل نافذة الـ٧ ثوانٍ).
 *
 * هذه هي نفسُ العلّة التي عُولجت لنصّ **الجدول** أعلاه (انتظارٌ يمرّ فوراً على
 * صفٍّ قديم) — بقيت في **صندوق الرسالة**. المسحُ يجعل الانتظارَ على حدثٍ
 * جديدٍ حتماً. Clear first, then wait: never match the previous step's toast. */
async function clearToast(page) {
  await page.evaluate(() => {
    const el = document.getElementById("appMsg");
    if (el) { el.className = "msg"; el.textContent = ""; }
  });
  // القفلُ: لو بقي التوهّجُ بعد المسح لعاد الانتظارُ التالي يطابق رسالةً
  // قديمة — نفشل هنا باسمٍ صريح بدل أن نمضي على انتظارٍ زائف.
  const still = await page.evaluate(() =>
    (document.getElementById("appMsg") || {}).className || "");
  if (/\bon\b/.test(still))
    fail("toast_not_cleared", `صندوقُ الرسالة لم يُمسَح: ${still}`);
}


async function setReportLanguage(page, lang) {
  await gotoSection(page, "profile");
  await page.waitForSelector("#rlangSel", { timeout: 8000 });
  await page.selectOption("#rlangSel", lang);
  await clearToast(page);
  await page.click("#rlangSaveBtn");
  await page.waitForSelector("#appMsg.on.good", { timeout: 10000 });
  // الحفظ يعيد قراءة /me — المؤشّر يعكس الإعداد الجديد فعلاً.
  await page.waitForFunction(
    (l) => (document.getElementById("rlangSel") || {}).value === l,
    lang, { timeout: 8000 });
}

/** أنشئ دراسةً وأطلقها وانتظر اكتمال **هذه الدراسة بعينها**.
 *
 * الانتظارُ على نصّ الجدول («مكتملة» في أيّ صفّ) خاطئٌ بنيوياً: الجدول يحمل
 * دراساتٍ سابقةً مكتملة، فيمرّ الشرطُ فوراً على صفٍّ قديم بينما الجديدةُ ما
 * تزال قيد الإعداد — ثمّ يُقرأ تقريرُ الدراسة الخطأ. الانتظارُ هنا على
 * **معرّف** الدراسة المنشأة للتوّ، عبر جلسة المتصفّح نفسها. */
async function runStudy(page, product) {
  await gotoSection(page, "studies");
  // The approved workspace defaults to folders. Select the table through its
  // visible control before using the study-id-specific row actions below.
  const tableView = page.locator("#studyViewBtn").filter({
    hasText: /^(عرض كجدول|Table view)$/,
  });
  if (await tableView.count()) await tableView.click();
  await page.click("#newStudyBtn");
  await page.waitForSelector(".veil .dlg", { timeout: 5000 });

  // §15: مؤشّرٌ إعلاميّ للغة التقرير، وبلا أيّ منتقي لغةٍ في هذا التدفّق.
  const note = await page.textContent("#studyLangNote").catch(() => null);
  if (!note) fail("study_lang_indicator", "لا مؤشّر لغة في نافذة الدراسة");
  const langSelectors = await page.evaluate(() => {
    const sels = Array.from(document.querySelectorAll(".veil .dlg select"));
    return sels.filter((el) => {
      const vals = Array.from(el.options || []).map((o) => o.value);
      return vals.includes("ar") && vals.includes("en");
    }).map((el) => el.id || el.name || "(unnamed)");
  });
  if (langSelectors.length)
    fail("study_lang_selector",
      `منتقي لغةٍ ظهر في تدفّق إنشاء الدراسة (§15): ${langSelectors}`);

  await page.fill('.veil [name="product"]', product);
  await clearToast(page);
  await page.click(".veil .btn.go");
  await page.waitForSelector("#appMsg.on.good", { timeout: 10000 });

  // معرّفُ الدراسة المنشأة للتوّ — أحدثُ مسودّةٍ بهذا المنتج.
  const sid = await page.evaluate(async (prod) => {
    const r = await fetch("/platform/studies", { credentials: "same-origin" });
    const j = r.ok ? await r.json() : {};
    const list = (j.studies || j || []).filter(
      (s) => s.product === prod && s.state === "draft");
    return list.length ? Math.max(...list.map((s) => s.id)) : null;
  }, product);
  if (!sid) fail("study_not_created", `لم تُنشأ دراسةٌ للمنتج ${product}`);

  await page.waitForSelector("#studyTable:not(.hide)", { timeout: 10000 });
  const launchBtn = studyRow(page, sid).locator(
    'button:has-text("إطلاق"), button:has-text("Launch")').first();
  await launchBtn.click();
  await page.waitForSelector(".veil .dlg", { timeout: 5000 });
  await page.click(".veil .btn.go");

  // اكتمالُ **هذه** الدراسة تحديداً — لا «أيّ صفٍّ يقول مكتملة».
  await page.waitForFunction(async (id) => {
    const r = await fetch(`/platform/studies/${id}`,
      { credentials: "same-origin" });
    if (!r.ok) return false;
    const s = await r.json();
    return s.state === "completed" && !!s.analysis_id;
  }, sid, { timeout: 60000, polling: 1000 });

  // والجدولُ يعكس الاكتمال فعلاً في الواجهة (لا حالةٌ خلفيةٌ وحدها):
  // ظهورُ زرّ الـPDF شرطٌ أقوى من نصّ الحالة — لا يُبنى إلا لصفٍّ مكتمل.
  await page.waitForFunction(
    () => /مكتملة|Completed/.test(
      document.getElementById("studiesBody").innerText || ""),
    { timeout: 20000 });
  await studyRow(page, sid).locator('button:has-text("PDF")').first()
    .waitFor({ state: "visible", timeout: 20000 });
  return { note, sid };
}

/** نزّل الـPDF **بجلسة المتصفّح نفسها** ويعيد مساره على القرص.
 *
 * زرّ التنزيل يفتح تبويباً (`window.open`) — والتقاطُ حدث التنزيل من نافذةٍ
 * منبثقة هشّ. فنُثبِت أمرين منفصلين: (١) الزرّ موجودٌ ويفتح التبويب فعلاً
 * (نقرةٌ حقيقية)، (٢) البايتات تُجلَب بكوكي الجلسة نفسه عبر النقطة نفسها —
 * فالمصادقةُ والمسارُ والمحتوى كلُّها حقيقية، بلا هشاشة النوافذ المنبثقة. */
async function downloadPdf(page, studyId, outDir, tag) {
  // **انتظارٌ لا تأكيدٌ لحظيّ.** زرّ الـPDF يظهر مع إعادة بناء صفّ الدراسة
  // بعد الاكتمال؛ تحت حِملٍ (رُتبتان تعملان معاً) قد يتأخّر البناء أجزاءَ
  // ثانيةٍ عن ظهور نصّ الحالة. التأكيدُ اللحظيّ كان يفشل هنا فشلاً كاذباً.
  const btn = studyRow(page, studyId).locator(
    'button:has-text("PDF")').first();
  try {
    await btn.waitFor({ state: "visible", timeout: 20000 });
  } catch (_e) {
    fail("pdf_button_missing", "زرّ الـPDF لم يظهر بعد اكتمال الدراسة");
  }
  const popup = page.waitForEvent("popup", { timeout: 15000 }).catch(() => null);
  await btn.click();
  const pop = await popup;
  if (pop) await pop.close().catch(() => {});

  const b64 = await page.evaluate(async (id) => {
    const r = await fetch(`/platform/studies/${id}/report.pdf`,
      { credentials: "same-origin" });
    // اقرأ نصّ السبب المُعلَن مع الرمز (عودة CI الحيّة 2026-08-27): «-> 503»
    // وحدها بلاغٌ غير قابل للتشخيص. Carry the server's declared reason.
    if (!r.ok) {
      let why = "";
      try { why = (await r.text()).slice(0, 400); } catch (e) { why = String(e); }
      return { error: r.status, why };
    }
    const buf = new Uint8Array(await r.arrayBuffer());
    let bin = "";
    for (let i = 0; i < buf.length; i++) bin += String.fromCharCode(buf[i]);
    return { data: btoa(bin) };
  }, studyId);
  if (b64.error)
    fail("pdf_http", `report.pdf -> ${b64.error} — ${b64.why || ""}`);
  const dest = path.join(outDir, `study_${studyId}_${tag}.pdf`);
  fs.writeFileSync(dest, Buffer.from(b64.data, "base64"));
  return dest;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "silk_rung3_lang_"));
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));

  try {
    await login(page, FACTORY_EMAIL);
    ok("factory_login");

    // ═══ (أ) المسار الإنجليزيّ كاملاً ═══════════════════════════════════
    await setReportLanguage(page, "en");
    ok("set_report_language_en");

    const { note: noteEn, sid: sidEn } = await runStudy(page, "premium dates");
    // المؤشّر يُكتب **بلغة الواجهة** ويسمّي **لغة التقرير** — فواجهةٌ عربية
    // تعرض «لغة التقرير: الإنجليزية». هذا عينُ الاستقلال المطلوب: الشاشةُ
    // بلغةٍ والتقريرُ بأخرى، وكلٌّ معلَنٌ بوضوح.
    if (!/English|الإنجليزية/i.test(noteEn || ""))
      fail("study_indicator_en",
        `مؤشّر اللغة لا يقول الإنجليزية: ${(noteEn || "").slice(0, 90)}`);
    ok("study_completed_en");

    const pdfEn = await downloadPdf(page, sidEn, outDir, "en");
    const sizeEn = fs.statSync(pdfEn).size;
    if (sizeEn < 5000) fail("pdf_en_size", `PDF صغير: ${sizeEn}`);
    const headEn = fs.readFileSync(pdfEn).subarray(0, 5).toString();
    if (headEn !== "%PDF-") fail("pdf_en_magic", headEn);
    ok("pdf_downloaded_en", `${sizeEn}B`);

    // ═══ (ب) لغةُ الواجهة **لا** تغيّر لغة التقارير (إعدادان مستقلّان) ═══
    await gotoSection(page, "profile");
    await page.click("#langBtn3");                 // يقلب لغة الشاشة فقط
    await page.waitForTimeout(700);                // loadAll يعيد البناء
    await gotoSection(page, "profile");
    const rlangAfterUiFlip = await page.inputValue("#rlangSel");
    if (rlangAfterUiFlip !== "en")
      fail("ui_lang_leaked_into_report_lang",
        `قلبُ لغة الواجهة غيّر لغة التقارير إلى: ${rlangAfterUiFlip}`);
    ok("ui_language_is_independent");

    // ═══ (ج) المسار العربيّ كاملاً — السلوك القائم بلا انحدار ══════════
    await setReportLanguage(page, "ar");
    ok("set_report_language_ar");

    const { note: noteAr, sid: sidAr } = await runStudy(page, "تمور سكري فاخرة");
    if (!/العربية|Arabic/.test(noteAr || ""))
      fail("study_indicator_ar",
        `مؤشّر اللغة لا يقول العربية: ${(noteAr || "").slice(0, 90)}`);
    ok("study_completed_ar");

    const snapAr = await page.evaluate(async (id) => {
      const r = await fetch(`/platform/studies/${id}`,
        { credentials: "same-origin" });
      return r.ok ? await r.json() : null;
    }, sidAr);
    if (!snapAr || snapAr.report_language !== "ar")
      fail("snapshot_ar",
        `لقطةُ الدراسة ليست عربية: ${snapAr && snapAr.report_language}`);
    const pdfAr = await downloadPdf(page, sidAr, outDir, "ar");
    const sizeAr = fs.statSync(pdfAr).size;
    if (sizeAr < 5000) fail("pdf_ar_size", `PDF صغير: ${sizeAr}`);
    ok("pdf_downloaded_ar", `${sizeAr}B`);

    // ═══ (د) التبديل بعد الإطلاق لا يمسّ لقطة الدراسة ═══════════════════
    // الدراسةُ العربية أعلاه اكتملت؛ نبدّل الآن إلى الإنجليزية ونؤكّد أنّ
    // عرضَ تقريرها ما يزال عربياً (اللقطة تحكم، لا الإعداد الحيّ).
    await setReportLanguage(page, "en");
    // اللقطةُ نفسها أولاً: الصفُّ ما يزال `ar` رغم أنّ الإعداد صار `en`.
    const afterFlip = await page.evaluate(async (id) => {
      const r = await fetch(`/platform/studies/${id}`,
        { credentials: "same-origin" });
      return r.ok ? await r.json() : null;
    }, sidAr);
    if (!afterFlip || afterFlip.report_language !== "ar")
      fail("snapshot_flipped",
        `لقطةُ دراسةٍ مكتملة انقلبت إلى: ${afterFlip && afterFlip.report_language}`);
    // ومحتوى تقريرها المعروض ما يزال نثراً عربياً فعلاً.
    const dr = await page.evaluate(async (id) => {
      const r = await fetch(`/platform/studies/${id}/report`,
        { credentials: "same-origin" });
      if (!r.ok) return null;
      const j = await r.json();
      return ((j.view || {}).deep_research || {}).report || null;
    }, sidAr);
    if (!dr || !AR_RUN.test(dr.text || ""))
      fail("snapshot_body_flipped",
        "متنُ تقريرٍ عربيٍّ مكتمل صار بلا نثرٍ عربيّ بعد تبديل الإعداد");
    ok("completed_report_keeps_its_language");

    if (pageErrors.length)
      fail("page_errors", pageErrors.slice(0, 2).join(" | "));

    // مساراتُ المصنوعات تُطبَع كي يفحص جانبُ بايثون لغتَها فعلياً.
    console.log(`ARTIFACT_PDF_EN=${pdfEn}`);
    console.log(`ARTIFACT_PDF_AR=${pdfAr}`);
    console.log("PLATFORM LANGUAGE RUNG3 PASS");
  } finally {
    await browser.close();
  }
}

main().catch((e) => { console.error(String(e && e.message || e)); process.exit(1); });
