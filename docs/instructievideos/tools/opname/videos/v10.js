// Video 10: retours, backorders en voorraad (demo database + mock Stoqflow)
const { Recorder } = require('../rec');
const { execFileSync } = require('child_process');
const sh = (...a) => execFileSync(a[0], a.slice(1), { encoding: 'utf8' });
const ctl = (...a) => sh('python3', '/opt/stoqflow_mock/ctl.py', ...a);
const live = (kind, ref, out, still) => sh('python3', '/opt/rec/live_slide.py', kind, ref, out, ...(still ? ['--still'] : []));

(async () => {
  const r = new Recorder('/opt/rec/out/10'); global.__r = r;
  const p = await r.launch(); await r.login();
  const fld = n => p.locator(`div[name=${n}]`).first();
  const box = t => p.locator(`.o_setting_box:has-text("${t}")`).first();
  const menu = t => p.locator(`.o_menu_sections a:has-text("${t}"), .o_menu_sections button:has-text("${t}")`).first();
  const btn = t => p.locator(`button:has-text("${t}")`).first();
  const SETTINGS = '/odoo/action-webship.webship_config_settings_action';
  const closeToasts = () => p.locator('.o_notification_close').evaluateAll(es => es.forEach(e => e.click())).catch(() => {});

  // s02: de drie menu's
  await r.goto('/odoo/action-webship.webship_orders_action');
  await r.startScene('s02');
  for (const m of ['Retours', 'Backorders', 'Voorraad']) await r.highlight(menu(m), 1.2);
  await r.endScene();

  // s03: een retour in Stoqflow = inkooporder "Retour S00012"
  ctl('retour', 'S00012', '--qty', 'WSS-BEANIE=1');
  const html = '/tmp/live10.html';
  live('po', 'Retour S00012', html, false);
  await r.startScene('s03');
  await r.page.goto('file://' + html); await r.wait(5.0);
  await r.endScene();

  // s04: retours ophalen
  await r.cut(async () => { await r.goto(SETTINGS); });
  await r.startScene('s04');
  const fetchR = btn('Retours ophalen uit Stoqflow');
  await fetchR.scrollIntoViewIfNeeded(); await r.wait(0.4);
  await r.clickCut(fetchR, { wait: 2500 });
  await r.highlight('.o_notification', 1.2);
  await closeToasts();
  await r.cut(async () => { await r.goto('/odoo/action-webship.webship_retour_and_backorder_action'); });
  await r.click(p.locator('.o_group_header').first(), { after: 700 });
  await r.highlight(p.locator('.o_data_row:has-text("S00012")').first(), 1.8);
  await r.endScene();

  // s05: retourlevering aanmaken
  await r.startScene('s05');
  await r.click(p.locator('.o_data_row:has-text("S00012") td').nth(1), { after: 900 });
  await r.highlight(fld('ws_original_order_link'), 1.4);
  await r.highlight(p.locator('.tab-pane.active, .o_notebook').last(), 1.6);
  await r.highlight(fld('return_picking_id'), 1.6);
  await r.highlight(fld('df_process_code'), 1.4);
  await r.clickCut(fld('return_picking_id').locator('a').first(), { wait: 1500 });
  await r.highlight(p.locator('.o_form_sheet').first(), 1.8);
  await r.endScene();

  // s06: retours automatisch verwerken
  await r.cut(async () => { await r.goto(SETTINGS); });
  await r.startScene('s06');
  const auto = box('Retours automatisch invoegen in Odoo');
  await auto.scrollIntoViewIfNeeded(); await r.wait(0.5);
  const cb = fld('webship_auto_sync_retours').locator('input');
  if (!(await cb.isChecked())) await r.click(cb, { after: 500 });
  await r.highlight(auto, 1.6);
  await r.clickCut('button.o_form_button_save');
  await r.endScene();

  // s08: backorders: koppelen of verwijderen in Stoqflow
  await r.startScene('s08');
  const link = box('Backorders koppelen');
  await link.scrollIntoViewIfNeeded(); await r.wait(0.4);
  await r.highlight(link, 2.2);
  const del = box('Backorders automatisch verwijderen in Stoqflow');
  await del.scrollIntoViewIfNeeded(); await r.wait(0.4);
  await r.highlight(del, 2.4);
  await r.endScene();

  // s09: Stoqflow -> Backorders
  await r.startScene('s09');
  const fetchB = btn('Backorders ophalen uit Stoqflow');
  await fetchB.scrollIntoViewIfNeeded(); await r.wait(0.4);
  await r.clickCut(fetchB, { wait: 2500 });
  await closeToasts();
  await r.cut(async () => { await r.goto('/odoo/action-webship.webship_backorders_action'); });
  const grp = p.locator('.o_group_header').first();
  if (await grp.isVisible().catch(() => false)) await r.click(grp, { after: 600 });
  await r.highlight(p.locator('.o_data_row').first(), 1.8);
  await r.click(p.locator('.o_data_row').first().locator('.o_list_record_selector input'), { after: 500 });
  await r.highlight(btn('Selectie verwijderen in Stoqflow'), 1.8);
  await r.click(p.locator('.o_data_row').first().locator('.o_list_record_selector input'), { after: 300 });
  await r.endScene();

  // s10: voorraad laden en vergelijken
  ctl('stock', 'WSS-SOCKS', '100');
  await r.cut(async () => { await r.goto(SETTINGS); });
  await r.startScene('s10');
  const load = btn('Voorraad laden uit Stoqflow');
  await load.scrollIntoViewIfNeeded(); await r.wait(0.4);
  await r.clickCut(load, { wait: 3000 });
  await closeToasts();
  await r.cut(async () => { await r.goto('/odoo/action-webship.webship_stock_action'); });
  await r.wait(0.6);
  await r.highlight(p.locator('table.o_list_table thead').first(), 2.0);
  await r.endScene();

  // s11: voorraad wijkt af -> toepassen
  await r.startScene('s11');
  await r.click('.o_searchview_dropdown_toggler', { after: 600 });
  await r.click(p.locator('.o-dropdown-item:has-text("Voorraad wijkt af"), .dropdown-item:has-text("Voorraad wijkt af")').first(), { after: 800 });
  await p.keyboard.press('Escape');
  const sock = p.locator('.o_data_row:has-text("Crew Socks")').first();
  await r.highlight(sock, 1.8);
  await r.click(sock.locator('.o_list_record_selector input'), { after: 500 });
  await r.clickCut(btn('Stoqflow-voorraad toepassen op Odoo'), { wait: 2500 });
  await r.wait(0.6);
  await r.endScene();

  // s12: overzicht van de drie menu's
  await r.startScene('s12');
  for (const m of ['Retours', 'Backorders', 'Voorraad']) await r.highlight(menu(m), 0.9);
  await r.endScene();
  await r.close();
})().catch(async e => { console.error(e); try { await global.__r.page.screenshot({ path: '/opt/rec/out/fail.png' }); } catch (x) {} process.exit(1); });
