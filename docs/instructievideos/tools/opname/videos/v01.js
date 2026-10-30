// Video 01: de Stoqflow-koppeling in een notendop (demo database na de flows)
const { Recorder } = require('../rec');
(async () => {
  const r = new Recorder('/opt/rec/out/01'); global.__r = r;
  const p = await r.launch(); await r.login();
  const fld = n => p.locator(`div[name=${n}]`).first();
  const tab = t => p.locator(`.nav-link:has-text("${t}")`).first();
  const menu = t => p.locator(`.o_menu_sections a:has-text("${t}"), .o_menu_sections button:has-text("${t}")`).first();
  const ORDERS = '/odoo/action-webship.webship_orders_action';
  const openPicking = async name => {
    await r.goto(ORDERS);
    await p.locator(`.o_data_row:has-text("${name}") td[name=name]`).first().click(); await r.idle(800);
  };

  // s02: de app Stoqflow, lijst Orders
  await r.goto('/odoo/action-sale.action_quotations_with_onboarding');
  await r.startScene('s02');
  await r.click('.o_navbar_apps_menu button', { after: 700 });
  await r.click(p.locator('.o_app:has-text("Stoqflow")').first(), { after: 1200 });
  await r.highlight(p.locator('.o_list_table').first(), 2.0);
  await r.endScene();

  // s04: levering met status en link naar Stoqflow
  await r.cut(async () => { await openPicking('SQF/OUT/00012'); await tab('Stoqflow').click(); await r.idle(300); });
  await r.startScene('s04');
  await r.highlight(fld('df_status_webship'), 1.4);
  await r.highlight(fld('df_url_order'), 1.4);
  await r.endScene();

  // s05: voltooide levering met pakket en tracking
  await r.cut(async () => { await openPicking('SQF/OUT/00009'); });
  await r.startScene('s05');
  await r.highlight(p.locator('.o_statusbar_status').first(), 1.2);
  await r.click(tab('Stoqflow-pakketten'), { after: 500 });
  await r.highlight(p.locator('.tab-pane.active').first(), 2.0);
  await r.endScene();

  // s06: voorraad, retours, dashboard
  await r.startScene('s06');
  for (const m of ['Voorraad', 'Retours', 'Dashboard']) {
    await r.click(menu(m), { after: 1100 });
    await r.wait(0.6);
  }
  await r.endScene();
  await r.close();
})().catch(async e => { console.error(e); try { await global.__r.page.screenshot({ path: '/opt/rec/out/fail.png' }); } catch (x) {} process.exit(1); });
