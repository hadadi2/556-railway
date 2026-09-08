/* Real Chromium, actual platform document; providers are mocked, no paid calls. */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.SILK_TEST_BROWSER ? {executablePath: process.env.SILK_TEST_BROWSER} : {})});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/platform.html') return route.fulfill({contentType: 'text/html',
        body: fs.readFileSync(path.join(__dirname, '../../web/platform.html'), 'utf8')});
      if (url.pathname.endsWith('/report.pdf')) return route.fulfill({status: 409,
        contentType: 'application/json', body: JSON.stringify({detail: {
          message: 'تعذر تسليم التقرير حتى اكتمال التحقق.',
          blocked_checks: ['agent_failed']}})});
      return route.fulfill({contentType: 'application/json', body: '{}'});
    });
    await page.goto('http://localhost/platform.html');
    for (const size of [{width: 1280, height: 720}, {width: 390, height: 844},
                        {width: 320, height: 568}, {width: 844, height: 390}]) {
      await page.setViewportSize(size);
      await page.evaluate(() => {
        window.testDialog = dialog('اختبار دراسة طويلة',
          '<div class="two"><input aria-label="منتج"><input aria-label="سوق"></div>' +
          '<p>محتوى التقرير وأرقام الدراسة '.repeat(300) + '</p>',
          async () => { throw new Error('خطأ ظاهر داخل النافذة'); }, 'حفظ', false);
      });
      const geometry = await page.evaluate(() => {
        const v = window.testDialog;
        const d = v.querySelector('.dlg').getBoundingClientRect();
        const f = v.querySelector('.ft').getBoundingClientRect();
        const b = v.querySelector('.bd');
        return {top: d.top, bottom: d.bottom, right: d.right, left: d.left,
          footerBottom: f.bottom, scrollable: b.scrollHeight > b.clientHeight,
          locked: document.body.classList.contains('dialog-open')};
      });
      assert(geometry.top >= 0 && geometry.bottom <= size.height);
      assert(geometry.left >= 0 && geometry.right <= size.width);
      assert(geometry.footerBottom <= size.height && geometry.scrollable && geometry.locked);
      await page.locator('.veil .go').click();
      await page.locator('.dialog-error').waitFor({state: 'visible'});
      assert.equal(await page.locator('.dialog-error').textContent(), 'خطأ ظاهر داخل النافذة');
      await page.evaluate(() => window.testDialog.querySelector('.ft').prepend(pdfBtn(1)));
      await page.locator('.veil .ft button').first().click();
      await page.waitForFunction(() => document.querySelector('.dialog-error').textContent.includes('agent_failed'));
      assert((await page.locator('.dialog-error').textContent()).includes('agent_failed'));
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('.veil').count(), 0);
      assert.equal(await page.evaluate(() => document.body.classList.contains('dialog-open')), false);
    }
    assert.deepEqual(errors, []);
    console.log('PASS: 4 viewport sizes; scrolling, visible actions, inline errors, PDF refusal, Escape.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
