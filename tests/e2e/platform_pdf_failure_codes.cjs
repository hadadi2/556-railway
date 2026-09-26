/* البند ٢٨٤ — متصفّحٌ حقيقيّ: كلُّ رمزِ عطلِ PDF يظهر للمصنع بجملته الخاصّة.
   بلاغ المالك: «توليد ملف PDF معطَّل على الخادم حالياً — أبلغ الإدارة» كان يظهر
   لرفض فحص الأقواس بعد تحويلٍ ناجح. «معطَّل» الآن لغياب المحرّك وحده، ونصُّ
   الخادم الداخليّ لا يصل الصفحة. Real Chromium, actual platform document. */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');

const CASES = [
  ['pdf_unavailable', 'معطَّل على الخادم'],
  ['pdf_failed', 'أعد المحاولة بعد دقيقة'],
  ['pdf_rejected', 'إعادة المحاولة لن تغيّر النتيجة'],
];

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.SILK_TEST_BROWSER ? {executablePath: process.env.SILK_TEST_BROWSER} : {})});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    let code = null;
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/platform.html') return route.fulfill({contentType: 'text/html',
        body: fs.readFileSync(path.join(__dirname, '../../web/platform.html'), 'utf8')});
      if (url.pathname.endsWith('/report.pdf')) return route.fulfill({status: 503,
        contentType: 'application/json', body: JSON.stringify({detail: {
          error: code, message: 'فشل فحص اتجاه الأقواس — نصٌّ داخليّ للمشغّل'}})});
      return route.fulfill({contentType: 'application/json', body: '{}'});
    });
    await page.goto('http://localhost/platform.html');
    await page.setViewportSize({width: 390, height: 844});
    for (const [c, expected] of CASES) {
      code = c;
      await page.evaluate(() => {
        window.testDialog = dialog('تقرير', '<p>دراسة</p>', async () => {}, 'حفظ', false);
        window.testDialog.querySelector('.ft').prepend(pdfBtn(7));
      });
      await page.locator('.veil .ft button').first().click();
      await page.waitForFunction(() => {
        const e = document.querySelector('.dialog-error');
        return e && e.textContent.trim().length > 0;
      });
      const shown = await page.locator('.dialog-error').textContent();
      assert(shown.includes(expected), `${c}: «${shown}»`);
      assert(!shown.includes('نصٌّ داخليّ'), `${c}: server text leaked: «${shown}»`);
      if (c !== 'pdf_unavailable') assert(!shown.includes('معطَّل'), `${c}: «${shown}»`);
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors, []);
    console.log('PASS: pdf_unavailable / pdf_failed / pdf_rejected each shown with its own sentence.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
