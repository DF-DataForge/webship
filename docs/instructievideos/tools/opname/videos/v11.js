// Video 11: opvolgen en fouten oplossen (demo database na prep11.py)
const { Recorder } = require('../rec');
const { execFileSync } = require('child_process');
const sh = (...a) => execFileSync(a[0], a.slice(1), { encoding: 'utf8' });
const rpc = (...a) => sh('python3', '/opt/rec/odoo_rpc.py', ...a);

(async () => {
  const r = new Recorder('/opt/rec/out/11'); global.__r = r;
  const p = await r.launch(); await r.login();
  const fld = n => p.locator(`div[name=${n}]`).first();
  const tab = t => p.locator(`.nav-link:has-text("${t}")`).first();
  const box = t => p.locator(`.o_setting_box:has-text("${t}")`).first();
  const btn = t => p.locator(`button:has-text("${t}")`).first();
  const ORDERS = '/odoo/action-webship.webship_orders_action';
  const SETTINGS = '/odoo/action-webship.webship_config_settings_action';
  const closeToasts = () => p.locator('.o_notification_close').evaluateAll(es => es.forEach(e => e.click())).catch(() => {});
  const filter = async (label, group = false) => {
    await r.click('.o_searchview_dropdown_toggler', { after: 600 });
    await r.click(p.locator(`.o-dropdown-item:has-text("${label}"), .dropdown-item:has-text("${label}")`).first(), { after: 800 });
    await p.keyboard.press('Escape'); await r.wait(0.3);
  };
  const openPicking = async name => {
    await r.goto(ORDERS);
    await p.locator(`.o_data_row:has-text("${name}") td[name=name]`).first().click(); await r.idle(800);
  };

  // s02: het dagelijks rapport (instellingen)
  await r.goto(SETTINGS);
  await r.startScene('s02');
  const rep = box('Ontvangers van het rapport');
  await rep.scrollIntoViewIfNeeded(); await r.wait(0.5);
  await r.highlight(rep, 2.4);
  await r.endScene();

  // s03: Stoqflow -> Orders als werklijst
  await r.cut(async () => { await r.goto(ORDERS); });
  await r.startScene('s03');
  await filter('Fout');
  await r.highlight(p.locator('.o_list_table').first(), 1.4);
  await r.click(p.locator('.o_data_row').first().locator('.o_list_record_selector input'), { after: 500 });
  await r.highlight(btn('Synchronisatie runnen'), 1.2);
  await r.highlight(btn('Haal hoeveelheden en status op'), 1.2);
  await r.click(p.locator('.o_data_row').first().locator('.o_list_record_selector input'), { after: 300 });
  await r.click('.o_searchview_facet .o_facet_remove', { after: 600 });
  await r.click('.o_searchview_dropdown_toggler', { after: 600 });
  await r.click(p.locator('.o-dropdown-item:has-text("Processcode"), .dropdown-item:has-text("Processcode")').last(), { after: 800 });
  await p.keyboard.press('Escape');
  await r.wait(1.2);
  await r.endScene();

  // s04: dashboard
  await r.cut(async () => { await r.goto('/odoo/action-webship.stoqflow_order_report_graph_action'); });
  await r.startScene('s04');
  await r.wait(1.4);
  await r.click('button.o_switch_view.o_pivot', { after: 1200 });
  await r.wait(1.4);
  await r.endScene();

  // s05: een fout lezen
  await r.cut(async () => { await openPicking('SQF/OUT/00012'); await tab('Stoqflow').click(); await r.idle(300); });
  await r.startScene('s05');
  await r.highlight(fld('df_picking_syncresult_webship'), 2.4);
  await r.highlight(p.locator('.o-mail-Message:has-text("SKU")').first(), 1.6);
  await r.endScene();

  // s06: SKU niet gevonden -> product synchroniseren
  await r.startScene('s06');
  await r.click(tab('Bewerkingen'), { after: 500 });
  await r.highlight(p.locator('.o_data_row:has-text("Sticker")').first(), 1.4);
  await r.cut(async () => {
    await r.goto('/odoo/action-stock.product_template_action_product');
    await p.locator('.o_searchview_input').fill('Sticker'); await p.keyboard.press('Enter'); await r.idle(700);
    await p.locator('.o_kanban_record:has-text("Sticker"), .o_data_row:has-text("Sticker")').first().click(); await r.idle(800);
    await tab('Stoqflow').click(); await r.idle(400);
  });
  const sync = btn('Synchroniseren met Stoqflow');
  await sync.scrollIntoViewIfNeeded();
  await r.clickCut(sync, { wait: 2000 });
  await closeToasts();
  await r.highlight(fld('df_url_prod'), 1.6);
  await r.endScene();

  // s07: adres onvolledig -> straat invullen
  await r.cut(async () => {
    await r.goto('/odoo/action-base.action_partner_form');
    await p.locator('.o_searchview_input').fill('Noah'); await p.keyboard.press('Enter'); await r.idle(700);
    await p.locator('.o_kanban_record:has-text("Noah Maes"), .o_data_row:has-text("Noah Maes")').first().click(); await r.idle(800);
  });
  await r.startScene('s07');
  await r.type(p.locator('div[name=street] input').first(), 'Veldstraat 12', { delay: 70 });
  await r.click('button.o_form_button_save', { after: 900 });
  await r.highlight(p.locator('.o_address_format, div[name=street]').first(), 1.4);
  await r.endScene();

  // s08: meerdere Stoqflow-klanten -> manueel matchen
  await r.cut(async () => {
    await r.goto('/odoo/action-base.action_partner_form');
    await p.locator('.o_searchview_input').fill('Emma'); await p.keyboard.press('Enter'); await r.idle(700);
    await p.locator('.o_kanban_record:has-text("Emma Janssens"), .o_data_row:has-text("Emma Janssens")').first().click(); await r.idle(800);
    await tab('Stoqflow').click(); await r.idle(400);
  });
  await r.startScene('s08');
  await r.click(btn('Matchen met Stoqflow'), { after: 1200 });
  await r.highlight(p.locator('.modal-content').first(), 1.6);
  await r.clickCut(p.locator('.modal button:has-text("Selecteren")').first(), { wait: 1500 });
  await closeToasts();
  await r.highlight(fld('df_url_client'), 1.6);
  await r.endScene();

  // s09: niet op voorraad -> instelling Volledige beschikbaarheid vereist
  await r.cut(async () => { await r.goto(SETTINGS); });
  await r.startScene('s09');
  await r.highlight(fld('webship_order_available_condition'), 2.6);
  await r.endScene();

  // s10: manueel en een niet-gekoppelde vervoerder
  await r.cut(async () => { await r.goto(ORDERS); });
  await r.startScene('s10');
  await filter('Manueel');
  await r.highlight(p.locator('.o_list_table').first(), 1.4);
  await r.cut(async () => { await openPicking('SQF/OUT/00008'); await tab('Stoqflow').click(); await r.idle(300); });
  await r.highlight(fld('df_picking_syncresult_webship'), 2.2);
  await r.endScene();

  // s11: opnieuw doorsturen
  await r.cut(async () => { await openPicking('SQF/OUT/00012'); await tab('Stoqflow').click(); await r.idle(300); });
  await r.startScene('s11');
  await r.clickCut('button[name=ws_sync_picking]', { wait: 2500 });
  await closeToasts();
  await r.highlight(fld('df_picking_syncresult_webship'), 1.6);
  await r.highlight(fld('df_url_order'), 1.2);
  await r.endScene();

  // s12: statusupdates
  await r.cut(async () => { await r.goto('/odoo/action-webship.webship_status_update_action'); });
  await r.startScene('s12');
  await r.wait(0.8);
  await r.highlight(p.locator('th:has-text("In wachtrij geplaatst op")').first(), 1.2);
  await r.click('.o_searchview_dropdown_toggler', { after: 600 });
  await r.highlight(p.locator('.o_filter_menu, .o-dropdown--menu').first(), 1.6);
  await p.keyboard.press('Escape');
  await r.endScene();

  // s13: JSON-historiek
  await r.cut(async () => { await r.goto('/odoo/action-webship.webship_json_history_action'); });
  await r.startScene('s13');
  await r.wait(0.8);
  await r.highlight(p.locator('.o_list_table thead').first(), 1.2);
  await r.click(p.locator('.o_data_row td').nth(2), { after: 900 });
  await r.wait(1.6);
  await r.endScene();

  // s14: hulp vragen: volledige trace kopiëren (ontwikkelaarsmodus)
  await r.cut(async () => { await openPicking('SQF/OUT/00013'); await r.goto(p.url() + (p.url().includes('?') ? '&' : '?') + 'debug=1'); await tab('Stoqflow').click(); await r.idle(400); });
  await r.startScene('s14');
  const trace = btn('Volledige Stoqflow-trace kopiëren');
  await r.highlight(trace, 1.4);
  await r.click(trace, { after: 900 });
  await r.wait(1.0);
  await r.endScene();

  // s15: geen fouten meer
  await r.cut(async () => {
    for (const n of ['SQF/OUT/00013', 'SQF/OUT/00014']) {
      await openPicking(n); await tab('Stoqflow').click(); await r.idle(300);
      await p.locator('button[name=ws_sync_picking]').first().click(); await p.waitForTimeout(2500); await r.idle(300);
    }
    await r.goto(ORDERS);
  });
  await r.startScene('s15');
  await filter('Fout');
  await r.wait(1.8);
  await r.endScene();
  await r.close();
})().catch(async e => { console.error(e); try { await global.__r.page.screenshot({ path: '/opt/rec/out/fail.png' }); } catch (x) {} process.exit(1); });
