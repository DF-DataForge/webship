// Video 02, scenes on the empty database: developer mode, update apps list, install.
const { Recorder } = require('../rec');
const BASE = 'http://localhost:8071';
(async () => {
  const r = new Recorder('/opt/rec/out/02');
  const p = await r.launch();
  await p.goto(BASE + '/web/login'); await p.fill('input[name=login]', 'admin'); await p.fill('input[name=password]', 'admin');
  await p.press('input[name=password]', 'Enter'); await p.waitForURL(/\/odoo/); await r.idle(1500);

  // s04: Instellingen -> Ontwikkelaarsmodus activeren; Apps -> Lijst met apps bijwerken
  await r.goto(BASE + '/odoo/settings');
  await r.startScene('s04');
  await r.wait(0.8);
  const dev = p.getByText('Ontwikkelaarsmodus activeren', { exact: true }).first();
  await dev.scrollIntoViewIfNeeded(); await r.wait(0.6);
  await r.highlight(dev, 1.4);
  await r.cut(async () => { await r.click(dev, { after: 200 }); await p.waitForURL(/debug=1/); });
  await r.wait(0.8);
  await r.cut(async () => { await p.goto(BASE + '/odoo/action-base.open_module_tree?debug=1'); });
  await r.wait(0.8);
  await r.click('.o_menu_sections >> text=Lijst met apps bijwerken');
  await r.wait(1.0);
  const upd = p.locator('.modal-footer button:has-text("Bijwerken"), .modal-footer button.btn-primary').first();
  await r.cut(async () => { await r.click(upd, { after: 300 }); });
  await r.wait(0.8);
  await r.endScene();

  // s05: zoeken op Stoqflow, Activeer, app verschijnt op het startscherm
  await r.startScene('s05');
  const search = p.locator('.o_searchview_input').first();
  await r.click('.o_searchview_facet .o_facet_remove', { after: 400 }).catch(() => {});
  await r.type(search, 'Stoqflow');
  await p.keyboard.press('Enter'); await r.idle(900);
  const card = p.locator('.o_kanban_record:has-text("Koppeling Stoqflow by Data Forge")').first();
  await r.highlight(card, 1.6);
  await r.cut(async () => {
    await r.click(card.locator('button:has-text("Activeer")'), { after: 200 });
    await p.waitForURL(/\/odoo/, { timeout: 300000 });
    await p.waitForTimeout(3000);
  });
  await r.cut(async () => { await p.goto(BASE + '/odoo/action-base.open_module_tree?debug=1'); });
  await r.wait(0.8);
  await r.click('.o_navbar_apps_menu button', { after: 700 });
  const icon = p.locator('.o_app:has-text("Stoqflow")').first();
  await r.moveTo(icon); await r.highlight(icon, 1.8);
  await r.endScene();
  await r.close();
})().catch(e => { console.error(e); process.exit(1); });
