// node explore.js <base> <path> <out.png> [js-to-eval]
const { chromium } = require('playwright');
(async () => {
  const [base, url, out, js] = process.argv.slice(2);
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, locale: 'nl-BE' });
  await p.goto(base + '/web/login'); await p.fill('input[name=login]', 'admin'); await p.fill('input[name=password]', 'admin');
  await p.press('input[name=password]', 'Enter'); await p.waitForURL(/\/odoo/);
  await p.goto(base + url); await p.waitForTimeout(2500);
  if (js) console.log(await p.evaluate(js));
  await p.screenshot({ path: out }); await b.close();
})();
