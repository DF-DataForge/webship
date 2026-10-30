// Video 02 scene 2: the empty database before installation.
const { Recorder } = require('../rec');
const BASE = 'http://localhost:8071';
(async () => {
  const r = new Recorder('/opt/rec/out/02'); const p = await r.launch();
  await p.goto(BASE + '/web/login'); await p.fill('input[name=login]', 'admin'); await p.fill('input[name=password]', 'admin');
  await p.press('input[name=password]', 'Enter'); await p.waitForURL(/\/odoo/); await r.idle(1000);
  await r.goto(BASE + '/odoo/action-sale.action_quotations_with_onboarding');
  await r.startScene('s02');
  await r.wait(1.0);
  await r.click('.o_navbar_apps_menu button', { after: 600 });
  for (const app of ['Verkoop', 'Inkoop', 'Voorraad']) await r.highlight(p.locator(`.o_app:has-text("${app}")`).first(), 0.9);
  await r.wait(0.5);
  await r.endScene();
  await r.close();
})().catch(e => { console.error(e); process.exit(1); });
