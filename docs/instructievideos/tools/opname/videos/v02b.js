// Video 02, settings scenes on the demo database (mock Stoqflow running).
const { Recorder } = require('../rec');
(async () => {
  const r = new Recorder('/opt/rec/out/02');
  const p = await r.launch(); await r.login();
  const SETTINGS = '/odoo/action-webship.webship_config_settings_action';
  const f = n => p.locator(`div[name=${n}] input`).first();

  await r.goto(SETTINGS);
  // s07: sleutels invullen
  await r.startScene('s07');
  await r.wait(0.6);
  await r.highlight('.o_setting_box:has-text("Sleutel:")', 1.6);
  await r.type(f('webship_login'), 'sf_live_7d2c9a41e8b03f9a', { delay: 45 });
  await r.type(f('webship_password'), 'k9Xq2LmZ8vTr4WcYp1Hs', { delay: 40 });
  await r.highlight(f('webship_url'), 1.3);
  await r.highlight(f('webship_app_url'), 1.3);
  await r.click('button.o_form_button_save, button:has-text("Opslaan")');
  await r.wait(0.8);
  await r.endScene();

  // s08: verbinding testen; een foute sleutel geeft een rode melding
  const test = 'button:has-text("Verbinding testen")';
  const closeToasts = () => p.locator('.o_notification_close').evaluateAll(es => es.forEach(e => e.click())).catch(() => {});
  await r.startScene('s08');
  await r.click(test, { after: 1000 });
  await r.highlight('.o_notification', 2.0);
  await closeToasts();
  await r.type(f('webship_login'), 'wrong-key', { delay: 60 });
  await r.click('button.o_form_button_save', { after: 800 });
  await r.click(test, { after: 1000 });
  await r.highlight('.o_notification', 2.4);
  await r.cut(async () => {
    await closeToasts();
    await f('webship_login').fill('sf_live_7d2c9a41e8b03f9a');
    await f('webship_login').press('Tab');
    await p.locator('button.o_form_button_save').first().click();
    await p.waitForTimeout(1500);
    await p.locator(test).first().click();
    await p.waitForTimeout(1500);
    await closeToasts();
  });
  await r.endScene();

  // s09: bedrijven, merken en magazijnen laden
  await r.startScene('s09');
  const load = p.locator('button:has-text("Bedrijven / merken / magazijnen laden")').first();
  await load.scrollIntoViewIfNeeded(); await r.wait(0.8);
  await r.highlight(p.locator('.o_setting_box:has-text("Merk & Shop")').first(), 1.6).catch(() => {});
  await r.click(load, { after: 1500 });
  await r.wait(1.0);
  await r.endScene();

  // s10: standaardmerk en -shop
  await r.startScene('s10');
  for (const [name, text] of [['webship_default_brand', "Woody"], ['webship_default_shop', 'Woody']]) {
    await r.type(f(name), text, { delay: 70 });
    await r.wait(0.8);
    await r.click(p.locator('.o-autocomplete--dropdown-item a, .o-autocomplete--dropdown-item').first(), { after: 500 });
  }
  await r.highlight(p.locator('.o_setting_box:has-text("Merk & Shop")').first(), 1.4).catch(() => {});
  await r.click('button.o_form_button_save, button:has-text("Opslaan")');
  await r.endScene();

  // s11: overzicht
  await r.startScene('s11');
  await r.cut(async () => { await r.goto(SETTINGS); });
  await r.wait(1.0);
  await r.highlight('.o_setting_box:has-text("Sleutel:")', 1.6);
  await r.scroll(500);
  await r.wait(1.2);
  await r.endScene();
  await r.close();
})().catch(e => { console.error(e); process.exit(1); });
