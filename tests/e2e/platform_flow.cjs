// رُتبة ٣ — منصّة دراسات السوق في متصفّح حقيقي (rung 3: the studies platform).
//
// > التحوّل (قرارات المالك 2026-08-17): الدراسة طلبُ دراسة سوقٍ يشغّل محرّك
// > سِلك آلياً — لا حملات بريدية. هذا التدفّق ينقر الرحلة كاملةً كما سيعيشها
// > المالك: أدمِن (تمويل + حصّة مستخدم + تكاليف البحث + إشراف كل الدراسات) ثم
// > مصنع (دراسة جديدة بمنتج ← إطلاق ← «قيد الإعداد» بمؤقّت ← «مكتملة» ← عرض
// > التقرير + تنزيل Word ← حصّة المستخدم تُنفَّذ برسالة عربية) — ويؤكّد الحذف
// > النهائي: **لا أثر لأي واجهة تنقيب** ولا تكلفة داخلية على شاشة مصنع.
//
// المحرّك خلف مقعد SILK_PLATFORM_FAKE_ENGINE (يضبطه LiveShapeServer) — عيّنة
// موسومة تعبر silk_storage الحقيقي، فالمسار المفحوص هو مسار الإنتاج نفسه.
//
// CommonJS (.cjs) عمداً — require يحترم NODE_PATH (نفس اتفاق بقية التدفّقات).
// يُشغَّل من tests/test_rung3_playwright_e2e.py مع BASE_URL/ADMIN_EMAIL/
// FACTORY_EMAIL/PLATFORM_PASSWORD عبر البيئة. يخرج 0 عند نجاح كل خطوة.

const { chromium } = require("playwright");

const BASE = process.env.BASE_URL;
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || "admin@silk.local";
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

async function login(page, email) {
  await page.goto(BASE + "/platform.html",
    { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForSelector("#loginView:not(.hide) #email", { timeout: 15000 });
  await page.fill("#email", email);
  await page.fill("#pw", PASSWORD);
  await page.click("#loginBtn");
  await page.waitForSelector("#appView:not(.hide)", { timeout: 15000 });
}

async function logout(page) {
  await page.click("#logoutBtn");
  await page.waitForSelector("#loginView:not(.hide)", { timeout: 10000 });
}

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


async function newStudy(page, product, hsCode) {
  await page.click("#newStudyBtn");
  await page.waitForSelector(".veil .dlg", { timeout: 5000 });
  await page.fill('.veil [name="product"]', product);
  if (hsCode) await page.fill('.veil [name="hs_code"]', hsCode);
  await clearToast(page);
  const saved = hsCode ? page.waitForResponse(r =>
    r.url().endsWith('/platform/studies') && r.request().method() === 'POST') : null;
  await page.click(".veil .btn.go");
  if (saved) {
    const response = await saved;
    const row = await response.json();
    if (response.status() !== 200 || row.hs_source !== 'manual' || row.hs_code !== hsCode)
      fail('factory_manual_hs_persisted', 'رمز المصنع لم يُحفظ بمصدره اليدوي');
    ok('factory_manual_hs_persisted');
  }
  await page.waitForSelector("#appMsg.on.good", { timeout: 10000 });
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  const consoleErrors = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });

  try {
    // ═══════════ صفحة الهبوط (طلب المالك) ═══════════
    await page.goto(BASE + "/platform", { waitUntil: "networkidle", timeout: 30000 });
    const landingBtn = page.locator('a[href="/platform.html"]').first();
    if (!(await landingBtn.count()))
      fail("landing_cta", "زر «الدخول إلى البوابة» غائب عن صفحة الهبوط");
    await landingBtn.click();
    await page.waitForSelector("#loginView:not(.hide) #email", { timeout: 15000 });
    ok("landing_page_to_portal");

    // اللغة الثنائية (قرار المالك): التبديل يقلب الاتجاه والنصوص ويعود.
    await page.click("#langBtn");
    await page.waitForFunction(
      () => document.documentElement.dir === "ltr", { timeout: 5000 });
    const enLogin = await page.textContent("#loginBtn");
    if (!/Sign in/.test(enLogin || ""))
      fail("lang_en_login", `زر الدخول بالإنجليزية: ${enLogin}`);
    await page.click("#langBtn");
    await page.waitForFunction(
      () => document.documentElement.dir === "rtl", { timeout: 5000 });
    ok("language_toggle_prelogin");

    // شاشة الدخول بلا خطأ 401 في الكونسول (جولة 2026-08-17: جسّ /me الأعمى).
    await page.waitForTimeout(600);
    const me401 = consoleErrors.filter((t) => /401/.test(t));
    if (me401.length)
      fail("login_console_401", `أخطاء كونسول على شاشة الدخول: ${me401[0]}`);
    ok("login_console_clean");

    // ═══════════ الأدمِن ═══════════
    await login(page, ADMIN_EMAIL);
    ok("admin_login");

    // الاتجاه الصحيح: الشريط الجانبي على النصف الأيمن من الشاشة (بلاغ المالك).
    const sideBox = await page.locator("#sideBar").boundingBox();
    const viewport = page.viewportSize();
    if (!sideBox || sideBox.x + sideBox.width / 2 < viewport.width / 2)
      fail("rtl_sidebar_right",
        `الشريط الجانبي ليس يميناً: x=${sideBox && sideBox.x}, vw=${viewport.width}`);
    ok("rtl_sidebar_on_the_right");

    // هوية سِلك (قرار مالك 2026-08-20 ينسخ «نمط Stripe» 2026-08-18): شريط
    // فاتح بأيقونات، ولون الفعل أزرق سِلك 2563EB لا نيلي Stripe 635BFF.
    const sideBg = await page.evaluate(() =>
      getComputedStyle(document.getElementById("sideBar")).backgroundColor);
    if (!/255,\s*255,\s*255/.test(sideBg))
      fail("silk_sidebar_light", `خلفية الشريط ليست فاتحة: ${sideBg}`);
    // القائمة تُبنى بعد اكتمال تحميل الدور — انتظارٌ صريح لا عدٌّ فوري (سباق).
    await page.waitForSelector("#sideNav button svg", { timeout: 8000 });
    // اللون الأساسي المحسوب فعلياً في المتصفّح — لا نصّ ملف. نيلي Stripe
    // rgb(99,91,255) ممنوع؛ أزرق سِلك rgb(37,99,235) هو المطلوب.
    const priColor = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--pri").trim());
    if (priColor.toUpperCase() !== "#2563EB")
      fail("silk_primary_color", `اللون الأساسي ليس أزرق سِلك: ${priColor}`);
    // مجموعتا التنقّل («العمل» و«الحساب») — الشريط بنيةُ منتج لا قائمة روابط.
    const groups = await page.$$eval("#sideNav .navgroup",
      (els) => els.map((e) => e.textContent.trim()));
    if (groups.length < 2)
      fail("silk_nav_groups", `مجموعات التنقّل ناقصة: ${JSON.stringify(groups)}`);
    ok("silk_dashboard_theme", `pri=${priColor} groups=${groups.length}`);

    // الأدمِن يهبط على «نظرة عامة»: بطاقات KPI بقيم + رسم/حالة فراغ معلنة.
    await page.waitForSelector("#adminHomePanel.on", { timeout: 10000 });
    const primaryCount = await page.locator("#kpiGrid .stat").count();
    const secondaryCount = await page.locator("#adminActivity .stat").count();
    const kpiCount = primaryCount + secondaryCount;
    if (primaryCount !== 3 || secondaryCount !== 3)
      fail("admin_overview_kpis", `بطاقات KPI: ${primaryCount} + ${secondaryCount}`);
    const kpiVals = await page.$$eval("#kpiGrid .stat b.v, #adminActivity .stat b.v",
      (bs) => bs.map((b) => b.textContent.trim()));
    if (kpiVals.some((v) => !v)) fail("admin_overview_kpi_values", kpiVals.join("|"));
    // R6: الرسمُ (أو حالةُ الفراغ المعلنة) يُرسَم بعد وصول المقاييس — يُنتظَر لا يُفترَض فورياً.
    await page.waitForSelector("#studiesChart svg, #studiesChart .empty", { timeout: 10000 })
      .catch(() => fail("admin_overview_chart", "لا رسم ولا حالة فراغ معلنة"));
    const hasChart = await page.locator("#studiesChart svg").count();
    const hasEmpty = await page.locator("#studiesChart .empty").count();
    if (!hasChart && !hasEmpty)
      fail("admin_overview_chart", "لا رسم ولا حالة فراغ معلنة");
    ok("admin_overview_panel", `kpi=${kpiCount} chart=${hasChart ? "svg" : "empty"}`);

    // فحص المصادر بنقرة — جدول حالات (مجسات فاشلة بيئياً = حالات معلنة).
    await page.click("#diagBtn");
    await page.waitForFunction(
      () => document.querySelectorAll("#diagBody tr").length >= 4,
      { timeout: 90000 });
    const diagRows = await page.locator("#diagBody tr").count();
    ok("admin_diagnostics_table", `${diagRows} مصادر`);

    // «تكاليف البحث» و«كل الدراسات» موجودان للأدمِن.
    await page.waitForSelector('#sideNav button[data-key="accounts"]',
      { timeout: 10000 });
    if (!(await page.locator('#sideNav button[data-key="costs"]').count()))
      fail("admin_costs_nav", "قسم تكاليف البحث غائب");
    await page.click('#sideNav button[data-key="costs"]');
    await page.waitForSelector("#adminCostsPanel.on", { timeout: 5000 });
    ok("admin_costs_panel");
    await page.click('#sideNav button[data-key="admin_studies"]');
    await page.waitForSelector("#adminStudiesPanel.on", { timeout: 5000 });
    ok("admin_all_studies_panel");
    // R6 (FE-9): تحت الحدّ (١٠٠ دراسة) لا تظهر ملاحظةُ «أحدث N فقط».
    const noteHidden = await page.evaluate(() => {
      const n = document.getElementById("adminStudiesNote");
      return !n || n.classList.contains("hide");
    });
    if (!noteHidden) fail("admin_all_studies_no_note_below_limit", "ملاحظةُ الحدّ ظاهرة تحت الحدّ");
    ok("admin_all_studies_no_note_below_limit");

    // تمويل مصنع (المحفظة سجلّ تمويل — لا بوّابة إطلاق بعد التحوّل).
    await page.click('#sideNav button[data-key="accounts"]');
    await page.waitForSelector("#accountsPanel.on", { timeout: 5000 });

    /* أفعال الحساب من صفّه في الجدول — لا من زرٍّ عامٍّ في الرأس (قرار
       المالك 2026-08-20: كان الاثنان على نفس الشاشة يفتحان نفس النافذة).
       هذا مسار المستخدم الحقيقي: الصفّ يأتي بالحساب مُختاراً سلفاً.
       وخطوة «تمويل حساب» حُذفت مع سطح التمويل كلّه (قرار المالك: «حساب
       التمويل ما له أي فائدة» — بعد «الباقة فقط» لا يُخصَم منه شيء عند
       الإطلاق). النقطة والدفتر باقيان خادمياً ويغطّيهما `test_platform_roles`؛
       وتغطية Escape انتقلت إلى نافذة «الحصّة» فلم تُفقَد. */
    const rowAct = (act) => `#accountsBody tr:first-child button[data-act="${act}"]`;
    await page.waitForSelector(rowAct("quota"), { timeout: 10000 });
    if (await page.$(rowAct("fund")))
      fail("funding_surface_removed", "زرّ تمويل ما زال في صفّ الحساب");

    // Escape يغلق النافذة (جولة 2026-08-17: كان بلا أثر على div.veil).
    await page.click(rowAct("quota"));
    await page.waitForSelector(".veil .dlg", { timeout: 5000 });
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => !document.querySelector("#dlgHost .veil"),
      { timeout: 3000 });
    ok("escape_closes_dialog");

    // حصّة المستخدم (قرار المالك): 1 لكل مستخدم.
    await page.click(rowAct("quota"));
    await page.waitForSelector(".veil .dlg", { timeout: 5000 });
    await page.fill('.veil [name="quota"]', "1");
    await page.click(".veil .btn.go");
    // انتظر رسالة الحصّة **بنصّها** لا أي .good — رسالة التمويل السابقة تبقى
    // خضراء ٧ ثوانٍ فترضي المحدِّد العام قبل أن تُكتب رسالة الحصّة (سباق).
    await page.waitForFunction(
      () => /حصّة المستخدم/.test(
        (document.getElementById("appMsg") || {}).textContent || ""),
      { timeout: 10000 });
    ok("admin_set_user_quota");

    /* P3 (BIZ-13، تدقيق 2026-09-01): تصحيحُ اسمِ حسابٍ مكتوبٍ خطأً. كان الاسمُ يُكتَب
       مرّةً عند الإنشاء بلا مسارٍ لتصحيحه، فيبقى الخطأُ على كلّ تقريرٍ وفاتورة.
       الخطوةُ تفتح النافذة، تكتب اسماً جديداً، وتتحقّق أنّ **الجدولَ نفسَه** يعرضه
       بعد النجاح — لا رسالةٌ خضراء فوق صفٍّ لم يتغيّر. */
    const acctName = () => page.evaluate(() => {
      const tr = document.querySelector("#accountsBody tr:first-child");
      return tr ? (tr.cells[1] || tr.cells[0]).textContent.trim() : null;
    });
    const nameBefore = await acctName();
    await page.click(rowAct("rename"));
    await page.waitForSelector('.veil [name="acctname"]', { timeout: 5000 });
    const renamed = "مصنع مُعاد تسميته";
    await page.fill('.veil [name="acctname"]', renamed);
    await page.click(".veil .btn.go");
    await page.waitForFunction(
      (want) => Array.from(document.querySelectorAll("#accountsBody tr"))
        .some((r) => (r.textContent || "").includes(want)),
      renamed, { timeout: 10000 });
    if ((await acctName()) === nameBefore)
      fail("admin_rename_account", "الرسالةُ نجحت والجدولُ ما زال على الاسم القديم");
    ok("admin_rename_account");
    /* «الباقات» (قرار المالك 2026-08-20): الجدول يُقرأ ويُعدَّل، والرقم
       الجديد يعود **من الخادم** بعد الكتابة لا من النموذج، ويصير مصدره
       «معدَّل» بدل «الملف». */
    await page.click('#sideNav button[data-key="tiers"]');
    await page.waitForSelector("#tiersPanel.on", { timeout: 5000 });
    await page.waitForSelector('#tiersBody tr button[data-act="plan"]',
      { timeout: 8000 });
    const goldRow = () => page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll("#tiersBody tr"));
      const tr = rows.find((r) => /ذهبية/.test(r.cells[0].textContent || ""));
      return tr ? Array.from(tr.cells).map((c) => c.textContent.trim()) : null;
    });
    const before = await goldRow();
    if (!before) fail("plans_table_rows", "صفّ الباقة الذهبية غائب");
    if (before[5] !== "الملف")
      fail("plans_source_before", `مصدر الصفّ قبل التعديل: ${before[5]}`);
    if (before[3] !== "6")
      fail("plans_quota_before", `حصّة الذهبية قبل التعديل: ${before[3]}`);
    await page.click('#tiersBody tr:nth-child(3) button[data-act="plan"]');
    await page.waitForSelector(".veil .dlg", { timeout: 5000 });
    await page.fill('.veil [name="monthly_studies"]', "9");
    await page.click(".veil .btn.go");
    await page.waitForSelector("#appMsg.on.good", { timeout: 10000 });
    await page.waitForFunction(() => {
      const rows = Array.from(document.querySelectorAll("#tiersBody tr"));
      const tr = rows.find((r) => /ذهبية/.test(r.cells[0].textContent || ""));
      return tr && tr.cells[3].textContent.trim() === "9";
    }, { timeout: 8000 });
    const after = await goldRow();
    if (after[5] !== "معدَّل")
      fail("plans_source_after", `المصدر بعد التعديل: ${after[5]}`);
    ok("admin_plan_settings_edited");

    // «إعادة تعيين كلمة مرور مستخدم» صارت بطاقةً في «الملف التعريفي»
    // (قرار المالك 2026-08-20) — أدمِن حصراً، وتُصدر رمزاً حقيقياً.
    await page.click('#sideNav button[data-key="profile"]');
    await page.waitForSelector("#profilePanel.on", { timeout: 5000 });
    await page.waitForSelector("#pfResetCard:not(.hide)", { timeout: 5000 });
    if (await page.$("#resetUserBtn"))
      fail("reset_moved_to_profile", "زرّ إعادة التعيين ما زال في الرأس");
    await page.click("#pfResetBtn");
    await page.waitForSelector(".veil .dlg", { timeout: 5000 });
    await page.fill('.veil [name="user_id"]', "1");
    await page.click(".veil .btn.go");
    await page.waitForFunction(
      () => /رمز إعادة التعيين/.test(
        (document.getElementById("appMsg") || {}).textContent || ""),
      { timeout: 10000 });
    ok("admin_reset_token_from_profile");

    // توزيع المشتركين على الباقات — شريطٌ برقمٍ لكل باقة، لا سطرٌ مدفون.
    await page.click('#sideNav button[data-key="overview"]');
    await page.waitForSelector("#adminHomePanel.on", { timeout: 5000 });
    const mix = await page.evaluate(() => {
      const h = document.getElementById("tierBar");
      return {segs: h.querySelectorAll(".tbar-track .seg").length,
              text: (h.innerText || "").replace(/\n+/g, " | ")};
    });
    if (!mix.segs) fail("plan_mix_bar", `الشريط بلا شرائح: ${mix.text}`);
    if (!/فضية/.test(mix.text) || !/%/.test(mix.text))
      fail("plan_mix_legend", `وسيلة الإيضاح ناقصة: ${mix.text}`);
    ok("admin_plan_mix_bar", `segs=${mix.segs}`);

    await logout(page);
    ok("admin_logout");

    // ═══════════ المصنع ═══════════
    await login(page, FACTORY_EMAIL);
    await page.waitForSelector("#factoryStats:not(.hide)", { timeout: 10000 });
    // بطاقة الحصّة (لا بطاقة رصيد بعد قرار «الباقة فقط») + حصّة المستخدم ظاهرة.
    await page.waitForFunction(
      () => (document.getElementById("eStudies").textContent || "").trim() !== "—",
      { timeout: 15000 });
    await page.waitForSelector("#eUserFoot:not(.hide)", { timeout: 5000 });
    const uq = await page.textContent("#eUserFoot");
    if (!/1/.test(uq || "")) fail("factory_user_quota", `النص: ${uq}`);
    ok("factory_dashboard_quota_visible");

    // ═══ R3 (FE-3): جلسةٌ منتهية تُنهي الجلسة أينما وقع الـ401 ═══
    // كان الحارس في `loadAll` وحدها: رمزٌ فاسد يترك الشاشةَ كأنّ المستخدم
    // داخل، ثم يفشل كلُّ فعلٍ بلا سبب مفهوم. الرمزُ في الذاكرة (`let TOKEN`)
    // لا في التخزين، فنُفسده مباشرةً ونطلب تحديثاً صريحاً — لا انتظارَ
    // استطلاع. موضعُها **قبل** خطوة الـPDF عمداً: تلك تسقط بيئياً حيث لا
    // LibreOffice، فتحجب كلَّ ما بعدها عن الدليل المحلّي.
    await page.evaluate(() => { TOKEN = "expired-e2e-token"; });
    await page.evaluate(() => { loadStudies().catch(() => {}); });
    await page.waitForSelector("#loginView:not(.hide)", { timeout: 10000 });
    const stillIn = await page.evaluate(
      () => !document.getElementById("appView").classList.contains("hide"));
    if (stillIn)
      fail("expired_session_returns_to_login", "شاشةُ التطبيق ما تزال ظاهرة");
    ok("expired_session_returns_to_login");
    await login(page, FACTORY_EMAIL);          // استأنف بقيّةَ رحلة المصنع
    await page.waitForSelector("#factoryStats:not(.hide)", { timeout: 10000 });

    // The approved factory workspace opens on studies; overview remains available.
    await page.waitForSelector("#studiesPanel.on", { timeout: 5000 });
    await page.click('#sideNav button[data-key="home"]');
    // Keep the full overview checks after explicitly opening that section.
    await page.waitForSelector("#homePanel.on", { timeout: 5000 });
    /* ينتظر بطاقاتٍ **حقيقية** لا هياكل تحميل: `skeletonKpis` تبذر ثلاث
       عقد `.stat` قبل وصول `/me`، فشرطُ العدد وحده كان يتحقّق منها ويمرّ
       الفحص التالي فراغاً (مراجعة ذاتية ثانية). البطاقة الحقيقية تحمل
       `b.v` بنصّ، والهيكل يحمل `span.sk` بلا نصّ. */
    await page.waitForFunction(() => {
      const cards = document.querySelectorAll("#homeKpis .stat");
      if (cards.length < 3) return false;
      return Array.from(cards).every((c) => {
        const v = c.querySelector("b.v");
        return v && v.textContent.trim() !== "" && !c.querySelector(".sk");
      });
    }, { timeout: 10000 });
    const deadKpis = await page.$$eval("#homeKpis .stat b.v",
      (els) => els.map((e) => e.textContent.trim()).filter((t) => t === "—"));
    if (deadKpis.length)
      fail("factory_home_kpi_placeholder",
        `بطاقة KPI قيمتها شرطة — لا تجيب عن شيء: ${deadKpis.length}`);
    const chartEmpty = await page.evaluate(() => {
      const c = document.getElementById("marketsChart");
      return c && (c.querySelector("svg") || c.querySelector(".estate")
                   || c.querySelector(".empty")) ? 1 : 0;
    });
    if (!chartEmpty) fail("factory_home_chart", "لا مخطط ولا حالة فارغة معلنة");
    ok("factory_home_overview");

    // الحذف النهائي: لا قسم ولا زرّ تنقيب، ولا «تكاليف البحث» على شاشة مصنع.
    for (const key of ["drafts", "prospects", "funnels", "costs"]) {
      if (await page.locator(`#sideNav button[data-key="${key}"]`).count())
        fail("factory_no_prospecting_nav", `قسم تنقيب/تكلفة ظاهر لمصنع: ${key}`);
    }
    const visibleText = await page.evaluate(() =>
      document.getElementById("appView").innerText);
    for (const banned of ["تكاليف البحث", "العملاء المحتملون", "نصوص الرسائل",
                          "قمع المقارنة", "بريد الإرسال"]) {
      if (visibleText.includes(banned))
        fail("factory_no_prospecting_text", `نص تنقيب/تكلفة مرئي: ${banned}`);
    }
    ok("factory_prospecting_deleted");

    // رفع صورة يقرأها تلقائياً؛ غياب الرؤية معلن بلا اختلاق.
    // Upload triggers classification without a second click.
    await page.click("#newStudyBtn");
    await page.waitForSelector(".veil .dlg", { timeout: 5000 });
    if (await page.locator('#sideNav button[data-key="images"]').count())
      fail("images_panel_gone", "قسم الصور ما زال في القائمة الجانبية");
    const png = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBg" +
      "AAAABQABh6FO1AAAAABJRU5ErkJggg==", "base64");
    await page.setInputFiles('.veil [name="image_file"]',
      { name: "p.png", mimeType: "image/png", buffer: png });
    await page.waitForFunction(() => {
      const s = document.querySelector('.veil [data-role="classify-status"]');
      const t = (s && s.textContent) || "";
      const id = document.querySelector('.veil [name="image_id"]');
      const btn = document.querySelector('.veil [data-act="classify"]');
      return id && id.value && btn && !btn.disabled && t && !/جارٍ/.test(t);
    }, { timeout: 15000 });
    const clsMsg = await page.textContent('.veil [data-role="classify-status"]');
    if (/رمز مقترح|080410/.test(clsMsg || ""))
      fail("classify_no_fabrication", `اقتراح بلا مفتاح رؤية: ${clsMsg}`);
    ok("inline_image_upload_and_declared_classify", (clsMsg || "").slice(0, 60));
    await page.click(".veil .cancel");
    await page.waitForFunction(() => !document.querySelector("#dlgHost .veil"),
      { timeout: 3000 });

    // Vision response is mocked; upload, wiring and visible fields are real.
    // إثبات واجهة، لا إثبات دقة الرؤية على صورة منتج حقيقية.
    let imageCalls = 0;
    await page.route("**/platform/classify-image", async (route) => {
      imageCalls++;
      await route.fulfill({json: {ok:true, hs6:imageCalls === 1 ? "170490" : "080410",
        product_name:imageCalls === 1 ? "حلاوة طحينية" : "تمور سكري", source:"image"}});
    });
    await page.click("#newStudyBtn");
    await page.waitForSelector(".veil .dlg");
    await page.setInputFiles('.veil [name="image_file"]',
      {name:"first.png", mimeType:"image/png", buffer:png});
    await page.waitForFunction(() =>
      document.querySelector('.veil [name="hs_code"]').value === "170490");
    if (await page.inputValue('.veil [name="product"]') !== "حلاوة طحينية")
      fail("study_photo_autofill", "لم يُملأ اسم المنتج");
    await page.setInputFiles('.veil [name="image_file"]',
      {name:"second.png", mimeType:"image/png", buffer:png});
    await page.waitForFunction(() =>
      document.querySelector('.veil [name="hs_code"]').value === "080410");
    await page.fill('.veil [name="hs_code"]', "170490");
    const previousImage = await page.inputValue('.veil [name="image_id"]');
    await page.setInputFiles('.veil [name="image_file"]',
      {name:"manual.png", mimeType:"image/png", buffer:png});
    await page.waitForFunction((oldId) => {
      const id = document.querySelector('.veil [name="image_id"]');
      const btn = document.querySelector('.veil [data-act="classify"]');
      return id.value && id.value !== oldId && !btn.disabled;
    }, previousImage);
    if (imageCalls !== 2 || await page.inputValue('.veil [name="hs_code"]') !== "170490")
      fail("study_photo_manual_code", `نداءات الرؤية: ${imageCalls}`);
    ok("study_photo_automatic_and_manual_paths", "mocked vision; real uploads and UI");
    await page.click(".veil .cancel");
    await page.unroute("**/platform/classify-image");

    // دراسة جديدة بمنتج ← إطلاق ← «قيد الإعداد» بمؤقّت ← «مكتملة».
    // (قسم الدراسات لم يعد الأول — نظرة عامة أولاً منذ 2026-08-18 — والنص
    //  داخل قسمٍ مخفي يقرأ فارغاً، فنفتح القسم قبل أي فحص على جدوله.)
    await page.click('#sideNav button[data-key="studies"]');
    await page.waitForSelector("#studiesPanel.on", { timeout: 5000 });
    // The approved workspace opens as folders; preserve the existing full table flow.
    await page.waitForSelector("#studyViewBtn");
    if (await page.locator('#studyFolders button').count()) {
      await page.locator('#studyFolders button').first().click();
      await page.waitForSelector('#studyInspector h3');
      if (await page.locator('#studyFolders button[aria-pressed="true"]').count() !== 1)
        fail("factory_folder_selection", "Expected one selected study");
      ok("factory_folder_selection", "Selected folder exposes its study details");
    }
    await page.click('#studyViewBtn');


    // ═══ R3: النهايةُ تُسمّى — «انقطعت» ليست «مسودّة» ═══
    // انقطاعُ إعادة النشر لا يُبلَغ بنقرة (يحتاج قتلَ خادمٍ في منتصف تشغيلة)،
    // فيبذر LiveShapeServer صفَّه كما يتركه ختمُ الإغلاق حرفياً خلف
    // SILK_LIVE_SHAPE_SEED_INTERRUPTED=1. بلا بذرٍ: تخطٍّ **معلَن** لا مرورٌ صامت.
    if (process.env.SEED_INTERRUPTED === "1") {
      await page.waitForFunction((prod) => [...document.querySelectorAll(
        "#studiesBody tr")].some((r) => (r.innerText || "").includes(prod)),
        "عسل سِدر منقطع", { timeout: 10000 });
      const chip = await page.evaluate((prod) => {
        const rows = [...document.querySelectorAll("#studiesBody tr")];
        const tr = rows.find((r) => (r.innerText || "").includes(prod));
        if (!tr) return { missing: true };
        const p = tr.querySelector(".pill");
        return { text: p ? (p.textContent || "").trim() : "",
                 cls: p ? p.className : "" };
      }, "عسل سِدر منقطع");
      if (chip.missing)
        fail("interrupted_chip_visible", "صفُّ الدراسة المنقطعة غائب عن الجدول");
      if (chip.text !== "انقطعت")
        fail("interrupted_chip_visible",
             `الشريحة «${chip.text}» لا «انقطعت» — النهاية ما تزال مبهمة`);
      // «انقطعت» تُستأنَف بإطلاقٍ جديد — تنبيهٌ لا عطل (`warn`)، ومتمايزةٌ
      // لوناً عن «تعثّرت» (`bad`) و«أُلغيت» (محايد).
      if (!chip.cls.split(/\s+/).includes("warn"))
        fail("interrupted_chip_tone", `لونُ الشريحة: ${chip.cls}`);
      ok("interrupted_chip_visible", chip.text);
    } else {
      console.log("SKIP interrupted_chip_visible (SEED_INTERRUPTED != 1)");
    }

    await newStudy(page, "تمور سكري فاخرة", "080410");
    await page.waitForFunction(
      () => document.getElementById("studiesBody").innerText.includes("مسودّة"),
      { timeout: 10000 });
    ok("factory_study_created");

    await page.click('#studiesBody button:has-text("إطلاق")');
    await page.waitForSelector(".veil .dlg", { timeout: 5000 });
    const confirmText = await page.textContent(".veil .dlg");
    if (!/محرّك سِلك/.test(confirmText || ""))
      fail("launch_confirm", "نافذة الإطلاق لا تشرح تشغيل المحرّك");
    await page.click(".veil .btn.go");
    await page.waitForSelector("#appMsg.on.good", { timeout: 15000 });
    ok("factory_launch");

    // «قيد الإعداد» ثم — عبر استطلاع الصفحة الدوري — «مكتملة» بأزرار التقرير.
    // (مقعد المحرّك ينام نصف ثانية فيُتاح التقاط الحالة الجارية غالباً؛
    //  الحاسم هو الاكتمال، فلا نفشل إن سبقنا الاستطلاع إليها.)
    await page.waitForFunction(
      () => document.getElementById("studiesBody").innerText.includes("مكتملة"),
      { timeout: 30000 });
    ok("factory_study_completed");

    // جرس الإشعارات (قرار 2026-08-18): اكتمال الدراسة يكتب إشعاراً — الشارة
    // تظهر عبر الاستطلاع الدوري، وفتح القائمة يعرض «اكتملت» ويعلّم مقروءاً.
    await page.waitForFunction(() => {
      const b = document.getElementById("notifBadge");
      return b && !b.classList.contains("hide") && Number(b.textContent) >= 1;
    }, { timeout: 15000 });
    await page.click("#notifBtn");
    await page.waitForSelector("#notifMenu:not(.hide)", { timeout: 3000 });
    const notifText = await page.textContent("#notifMenu");
    if (!/اكتملت دراسة/.test(notifText || ""))
      fail("notif_menu", `قائمة الإشعارات بلا خبر الاكتمال: ${(notifText || "").slice(0, 80)}`);
    await page.waitForFunction(() => {
      const b = document.getElementById("notifBadge");
      return b && b.classList.contains("hide");
    }, { timeout: 5000 });
    await page.click("#notifBtn");   // أغلِق القائمة قبل بقية التدفّق
    ok("factory_notification_bell");
    // R6 (FE-19): الشارةُ صُفِّرت **بعد** نجاح التعليم على الخادم (تحقّقنا أعلاه من
    // اختفائها) — وعندَ الخادم لا يبقى إشعارٌ غيرُ مقروء.
    const unreadLeft = await page.evaluate(async () => {
      const r = await fetch("/platform/notifications", {credentials: "same-origin"});
      const j = await r.json();
      return Number(j.unread_count || 0);
    });
    if (unreadLeft !== 0) fail("factory_bell_click_zeroes_badge", `unread_count=${unreadLeft}`);
    ok("factory_bell_click_zeroes_badge");

    await page.click('#studiesBody button:has-text("عرض التقرير")');
    await page.waitForSelector(".veil .dlg", { timeout: 10000 });
    const repText = await page.textContent(".veil .dlg");
    if (!/تقرير الدراسة/.test(repText || ""))
      fail("factory_report_dialog", `نافذة التقرير: ${(repText || "").slice(0, 80)}`);
    // لا مفتاح تكلفة داخلية في نص التقرير المعروض (قرار المالك).
    if (/cost_usd|data_economics|تكاليف البحث/.test(repText || ""))
      fail("factory_report_cost_leak", "أثر تكلفة داخلية في تقرير المصنع");
    // العرض المقنع (2026-08-18): نافذة عريضة + شارة حكم + نص منسّق (العيّنة
    // العميقة تحمل عناوين وقوائم فيُثبت التنسيق فعلياً لا شكلياً).
    if (!(await page.locator(".veil .dlg.wide").count()))
      fail("report_dialog_wide", "نافذة التقرير ليست بالعرض الجديد");
    if (!(await page.locator(".veil .rverdict").count()))
      fail("report_verdict_badge", "لا شارة حكم في نافذة التقرير");
    if (!(await page.locator(".veil .rtext .rh").count()))
      fail("report_formatted_text", "نص التقرير بلا عناوين منسّقة");
    if (!(await page.locator(".veil .rtext ul li").count()))
      fail("report_formatted_list", "قائمة التقرير لم تُنسَّق");
    // جداول Markdown هي «أهمّ مخرَج» عند كاتب البحث العميق — أنابيبها الخام
    // في نافذة العميل عطبٌ صريح (§58): العيّنة تحمل جدولاً ويجب أن يُصيَّر.
    if (!(await page.locator(".veil .rtext table td").count()))
      fail("report_markdown_table", "جدول التقرير ظهر أنابيب خاماً");
    const rawPipes = await page.evaluate(() => {
      const t = document.querySelector(".veil .rtext");
      return t ? /\|\s*---/.test(t.innerText) : true;
    });
    if (rawPipes) fail("report_markdown_table_raw", "سطر فواصل الجدول ظاهر خاماً");
    await page.click(".veil .cancel").catch(() => {});
    await page.keyboard.press("Escape").catch(() => {});
    ok("factory_report_view_charts");

    // تنزيل PDF عبر نفس جلسة المتصفّح (طلب المالك: «اريده pdf») — 200 بجسم
    // يبدأ بـ%PDF فعلاً (تحويل LibreOffice حقيقي، لا نوع محتوى شكلي).
    const sid = await page.evaluate(() => {
      const row = document.querySelector("#studiesBody tr");
      return row ? row.querySelector("td span").textContent.trim() : "";
    });
    const pdf = await page.request.get(
      `${BASE}/platform/studies/${sid}/report.pdf`);
    if (pdf.status() !== 200) {
      // اطبع **سبب** الخادم لا رمزه وحده (عودة CI الحيّة 2026-08-27): كان
      // «HTTP 503» يصل بلا نصّ `detail` المُعلَن، فعطلٌ قابلٌ للتشخيص يصل
      // غير مُشخَّص. Print the server's declared reason, not just the code.
      let why = "";
      try { why = (await pdf.text()).slice(0, 400); } catch (e) { why = String(e); }
      fail("factory_pdf", `HTTP ${pdf.status()} — ${why}`);
    }
    const pdfBody = await pdf.body();
    if (pdfBody.length < 1000 || pdfBody.slice(0, 5).toString() !== "%PDF-")
      fail("factory_pdf_magic",
           `${pdfBody.length} bytes, head=${pdfBody.slice(0, 5)}`);
    ok("factory_pdf_download");

    // حصّة المستخدم (1) تُنفَّذ برسالة عربية على الإطلاق الثاني.
    // أغلق أي نافذة متبقية أولاً.
    await page.evaluate(() => {
      document.querySelectorAll(".veil").forEach((v) => v.remove());
    });
    await newStudy(page, "زيتون مخلّل");
    await page.waitForFunction(
      () => document.getElementById("studiesBody").innerText.includes("مسودّة"),
      { timeout: 10000 });
    await page.click('#studiesBody button:has-text("إطلاق")');
    await page.waitForSelector(".veil .dlg", { timeout: 5000 });
    await page.click(".veil .btn.go");
    await page.waitForFunction(
      () => /حصّتك/.test(document.querySelector(".veil .dialog-error")?.innerText || ""),
      { timeout: 15000 });
    ok("factory_user_quota_enforced_arabic");
    // نافذة الإطلاق تبقى مفتوحة عند الرفض (الخطأ يُعرض والحوار قائم) —
    // أغلقها كي لا يعترض غشاؤها النقرات التالية.
    await page.click(".veil .cancel");
    await page.waitForFunction(() => !document.querySelector("#dlgHost .veil"),
      { timeout: 3000 });

    // ═══════════ المنتجات (2026-08-18): كتالوج يغذي الدراسات ═══════════
    await page.click('#sideNav button[data-key="products"]');
    await page.waitForSelector("#productsPanel.on", { timeout: 5000 });
    await page.click("#newProductBtn");
    await page.waitForSelector(".veil .dlg", { timeout: 5000 });
    await page.fill('.veil [name="pname"]', "عسل سدر جبلي");
    await page.fill('.veil [name="phs"]', "040900");
    // تحديث واحد بعد الحفظ؛ الثاني كان يمحو الصف بهيكل فارغ أثناء قراءته.
    // Saving must trigger one catalog refresh, not two successive renders.
    let productRefreshes = 0;
    const countProductRefresh = (request) => {
      if (request.method() === "GET" && new URL(request.url()).pathname.endsWith("/products"))
        productRefreshes += 1;
    };
    page.on("request", countProductRefresh);
    await page.click(".veil .btn.go");
    await page.waitForFunction(() =>
      document.getElementById("productsBody").innerText.includes("عسل سدر جبلي"),
      { timeout: 8000 });
    await page.waitForFunction(() => _loading === null, { timeout: 8000 });
    page.off("request", countProductRefresh);
    if (productRefreshes !== 1)
      fail("factory_product_single_refresh", `GET /products count: ${productRefreshes}`);
    ok("factory_product_single_refresh");
    ok("factory_product_created");
    // R6 (FE-7): مصدرُ الرمز مرئيّ في الجدول — أُنشئ المنتجُ برمزٍ يدويّ فتظهر «يدوي».
    const srcTxt = await page.textContent("#productsBody tr:first-child");
    if (!/يدوي/.test(srcTxt || ""))
      fail("factory_hs_source_badge", `لا شارةَ مصدرٍ للرمز: ${(srcTxt || "").slice(0, 80)}`);
    ok("factory_hs_source_badge");
    // «ابدأ دراسة» من المنتج — الاسم والرمز معبآن والدراسة تُربَط به.
    await page.click('#productsBody button:has-text("ابدأ دراسة")');
    await page.waitForSelector(".veil .dlg", { timeout: 5000 });
    const preName = await page.inputValue('.veil [name="product"]');
    const preHs = await page.inputValue('.veil [name="hs_code"]');
    if (preName !== "عسل سدر جبلي" || preHs !== "040900")
      fail("product_prefill", `تعبئة ناقصة: ${preName} / ${preHs}`);
    await page.click(".veil .btn.go");
    await page.waitForSelector("#appMsg.on.good", { timeout: 8000 });
    await page.waitForFunction(() => {
      const rows = document.querySelectorAll("#productsBody tr");
      return rows.length && /1/.test(rows[0].cells[4].textContent || "");
    }, { timeout: 8000 });
    ok("factory_study_from_product");

    // ═══════════ البروفايل (2026-08-18): بيانات + كلمة مرور + باقة ═══════════
    await page.click('#sideNav button[data-key="profile"]');
    await page.waitForSelector("#profilePanel.on", { timeout: 5000 });
    // بطاقة الحساب بالنمط العالمي (2026-08-19): اسم المصنع والبريد وشارة
    // الباقة كلها داخل الملف التعريفي — والشريط الجانبي بلا زرّ لغة مكرّر.
    const pfFactory = await page.inputValue("#pfFactory");
    // الاسم الذي غيّره الأدمِن أعلاه يجب أن يصل إلى ملف المصنع أيضاً.
    // Assert the renamed value, not the obsolete seed name.
    if (pfFactory !== renamed)
      fail("profile_factory_name", `اسم المصنع في الملف: ${pfFactory}`);
    const pfEmailV = await page.inputValue("#pfEmail");
    if (pfEmailV !== FACTORY_EMAIL)
      fail("profile_email_shown", `بريد الملف: ${pfEmailV}`);
    const tierBadge = await page.textContent("#whoTier");
    if (!/فضية/.test(tierBadge || ""))
      fail("profile_tier_badge", `شارة الباقة في الملف: ${tierBadge}`);
    if (await page.$("#langBtn2"))
      fail("sidebar_no_duplicate_lang", "زرّ لغة مكرّر في الشريط الجانبي");
    ok("profile_identity_card");
    await page.fill("#pfFirst", "عبدالله");
    await page.click("#pfSaveBtn");
    await page.waitForFunction(() =>
      /حُفظت بياناتك/.test(
        (document.getElementById("appMsg") || {}).textContent || ""),
      { timeout: 8000 });
    ok("factory_profile_details");

    /* قسم «الاشتراك والباقة» (قرار مالك 2026-08-20): كانت بطاقة الباقة
       مدفونةً في «الملف التعريفي»، وكان هذا التدفّق يقرأها **وهو على لوحٍ
       آخر** — `textContent` لا يعبأ بالظهور فتمرّ الخطوة على عنصرٍ مخفيّ.
       الآن نفتح القسم من مدخله في الشريط ونتحقّق أنّه مرئيّ فعلاً. */
    await page.click('#sideNav button[data-key="plan"]');
    await page.waitForSelector("#planPanel.on", { timeout: 5000 });
    if (!(await page.isVisible("#pfPlanCard")))
      fail("plan_card_visible", "بطاقة الباقة غير مرئية في قسم الاشتراك");
    const planTxt = await page.textContent("#pfPlanCard");
    if (!/فضية/.test(planTxt || ""))
      fail("plan_card_tier", `بطاقة الباقة بلا اسم الطبقة: ${planTxt}`);
    if (!/في الباقة البلاتينية/.test(planTxt || ""))
      fail("plan_unlock_hint", "بطاقة الباقة لا تسمّي باقة الفتح");
    // بطاقة الاستخدام: المتبقي والتجديد — أرقامٌ من /entitlements لا مخترَعة.
    if (!(await page.isVisible("#planUsageCard")))
      fail("plan_usage_visible", "بطاقة الاستخدام غائبة عن قسم الاشتراك");
    const usageTxt = await page.textContent("#planUsageCard");
    if (!/المتبقي/.test(usageTxt || ""))
      fail("plan_usage_remaining", `بطاقة الاستخدام بلا سطر المتبقي: ${usageTxt}`);
    if (!/(تُجدَّد الحصّة|سقف مدى الحياة)/.test(usageTxt || ""))
      fail("plan_usage_renewal", "بطاقة الاستخدام لا تشرح التجديد");
    ok("factory_subscription_section");
    await page.click('#sideNav button[data-key="profile"]');
    await page.waitForSelector("#profilePanel.on", { timeout: 5000 });
    // تغيير كلمة المرور ذاتياً: الجلسة الحالية تبقى، والدخول التالي بالجديدة.
    await page.fill("#pwCur", PASSWORD);
    await page.fill("#pwNew", "NewFactory12");
    await page.fill("#pwNew2", "NewFactory12");
    await page.click("#pwSaveBtn");
    await page.waitForFunction(() =>
      /غُيِّرت كلمة المرور/.test(
        (document.getElementById("appMsg") || {}).textContent || ""),
      { timeout: 8000 });
    await logout(page);
    await page.fill("#email", FACTORY_EMAIL);
    await page.fill("#pw", "NewFactory12");
    await page.click("#loginBtn");
    await page.waitForSelector("#appView:not(.hide)", { timeout: 15000 });
    // بطاقة الحصّة وشريط الأدوات صارا منطَّقَين بقسمي العمل (2026-08-19)،
    // والجلسة تعود إلى آخر قسم كان مفتوحاً («الملف التعريفي») — فالتحقّق
    // يكون بعد الانتقال إلى قسمٍ يخصّهما.
    await page.click('#sideNav button[data-key="home"]');
    await page.waitForSelector("#homePanel.on", { timeout: 5000 });
    await page.waitForSelector("#factoryStats:not(.hide)", { timeout: 10000 });
    ok("factory_password_change_and_relogin");

    // والعكس مقاسٌ أيضاً: لا شريط أدوات ولا بطاقة حصّة على «الملف التعريفي»
    // ولا «المنتجات» — كانا يظهران على كل الأقسام بلا معنى (فحص بصري).
    for (const key of ["profile", "products"]) {
      await page.click(`#sideNav button[data-key="${key}"]`);
      await page.waitForTimeout(200);
      const shown = await page.evaluate(() => [
        !document.getElementById("factoryBar").classList.contains("hide"),
        !document.getElementById("factoryStats").classList.contains("hide")]);
      if (shown[0] || shown[1])
        fail("toolbar_section_scope", `${key}: bar=${shown[0]} stats=${shown[1]}`);
    }
    await page.click('#sideNav button[data-key="studies"]');
    await page.waitForSelector("#studiesPanel.on", { timeout: 5000 });
    await page.waitForSelector("#factoryStats:not(.hide)", { timeout: 5000 });
    ok("toolbar_and_quota_are_section_scoped");


    // اللغة داخل الجلسة — من بطاقة اللغة في «الملف التعريفي» حصراً (النمط
    // العالمي 2026-08-19؛ زرّ الشريط المكرّر حُذف): EN تنقل الشريط لليسار
    // وتُحفَظ في الحساب.
    await page.click('#sideNav button[data-key="profile"]');
    await page.waitForSelector("#profilePanel.on", { timeout: 5000 });
    await page.click("#langBtn3");
    await page.waitForFunction(
      () => document.documentElement.dir === "ltr", { timeout: 8000 });
    await page.waitForTimeout(700);   // loadAll يعيد البناء
    const sbEn = await page.locator("#sideBar").boundingBox();
    const vpEn = page.viewportSize();
    if (!sbEn || sbEn.x + sbEn.width / 2 > vpEn.width / 2)
      fail("lang_en_sidebar_left",
        `الشريط ليس يساراً في EN: x=${sbEn && sbEn.x}`);
    // القسم يُحفَظ عبر إعادة البناء فبطاقة اللغة ما تزال ظاهرة للعودة.
    await page.waitForSelector("#profilePanel.on", { timeout: 5000 });
    await page.click("#langBtn3");
    await page.waitForFunction(
      () => document.documentElement.dir === "rtl", { timeout: 8000 });
    await page.waitForTimeout(500);
    ok("language_toggle_in_session");


    // ═══ إشراف الأدمِن (قرار 2026-08-19): يفتح تقرير المصنع، ولا مقاعد ═══
    await logout(page);
    await login(page, ADMIN_EMAIL);
    await page.click('#sideNav button[data-key="admin_studies"]');
    await page.waitForSelector("#adminStudiesPanel.on", { timeout: 5000 });
    await page.waitForFunction(
      () => /مكتملة/.test(
        (document.getElementById("adminStudiesBody") || {}).innerText || ""),
      { timeout: 15000 });
    await page.click('#adminStudiesBody button:has-text("عرض التقرير")');
    await page.waitForSelector(".veil .dlg", { timeout: 15000 });
    const admRep = await page.textContent(".veil .dlg");
    if (!/تقرير الدراسة/.test(admRep || ""))
      fail("admin_report_dialog",
           `نافذة تقرير الأدمِن: ${(admRep || "").slice(0, 80)}`);
    await page.click(".veil .cancel").catch(() => {});
    await page.waitForFunction(() => !document.querySelector("#dlgHost .veil"),
      { timeout: 5000 });
    ok("admin_opens_factory_report");

    // المقاعد حُذفت نهائياً (قرار 2026-08-19) — لا أثر في لوحة الحسابات.
    await page.click('#sideNav button[data-key="accounts"]');
    await page.waitForSelector("#accountsPanel.on", { timeout: 5000 });
    const seatTrace = await page.evaluate(
      () => (document.body.innerText || "").includes("المقاعد"));
    if (seatTrace) fail("seats_deleted", "أثر «المقاعد» ما يزال معروضاً");
    ok("seats_are_gone");


    // ═══════════ صفحة إعادة التعيين ═══════════
    await page.goto(BASE + "/reset-password?token=e2e-dummy",
      { waitUntil: "networkidle", timeout: 15000 });
    await page.waitForSelector("#pw1", { timeout: 10000 });
    const title = await page.title();
    if (!/إعادة تعيين/.test(title)) fail("reset_page", `العنوان: ${title}`);
    ok("reset_password_page");

    if (pageErrors.length) {
      fail("no_page_errors", pageErrors.join(" | ").slice(0, 400));
    }
    // ═══════════ صفحة الدفع (لا دفع وهمي) ═══════════
    await page.goto(BASE + "/checkout.html?plan=gold",
      { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForFunction(() => {
      // 1,799 = الذهبية الشهرية من config/pricing.yaml (إعادة تسعير #205) —
      // القصاصة القديمة 1,899 بقيت من عهد #201 فكسرت الرتبة بعد الدمج.
      const t = document.getElementById("sumTotal");
      return t && /1,799/.test(t.textContent || "");
    }, { timeout: 10000 });
    await page.fill("#fEmail", "owner@factory-e2e.example");
    await page.fill("#fName", "مصنع الرتبة الثالثة");
    await page.click("#sendBtn");
    await page.waitForSelector("#outMsg.msg.info.on", { timeout: 10000 });
    const payMsg = await page.textContent("#outMsg");
    if (!/لم يُفعَّل بعد/.test(payMsg || ""))
      fail("checkout_declared", `رسالة غير متوقعة: ${payMsg}`);
    const outCls = await page.getAttribute("#outMsg", "class");
    if (/good|success/.test(outCls || ""))
      fail("checkout_no_fake_success", outCls);
    ok("checkout_honest_flow", (payMsg || "").slice(0, 50));

    console.log("PLATFORM RUNG3 PASS");
    await browser.close();
    process.exit(0);
  } catch (e) {
    console.error(String(e && e.stack ? e.stack : e));
    await browser.close();
    process.exit(1);
  }
}

main();
