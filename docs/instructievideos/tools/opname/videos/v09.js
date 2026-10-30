// Video 09: bevoorraden vanuit het eigen magazijn (demo database + mock Stoqflow)
const { Recorder } = require('../rec');
const { execFileSync } = require('child_process');
const sh = (...a) => execFileSync(a[0], a.slice(1), { encoding: 'utf8' });
const ctl = (...a) => sh('python3', '/opt/stoqflow_mock/ctl.py', ...a);
const rpc = (...a) => sh('python3', '/opt/rec/odoo_rpc.py', ...a);
const live = (kind, ref, out, still) => sh('python3', '/opt/rec/live_slide.py', kind, ref, out, ...(still ? ['--still'] : []));
const SKU = 'WSS-CMP-CRUISER-825';

(async () => {
  const r = new Recorder('/opt/rec/out/09'); global.__r = r;
  const p = await r.launch(); await r.login();
  const fld = n => p.locator(`div[name=${n}]`).first();
  const tab = t => p.locator(`.nav-link:has-text("${t}")`).first();
  const openPicking = async name => {
    await r.goto('/odoo/action-stock.action_picking_tree_all');
    await p.locator('.o_searchview_input').fill(name); await p.keyboard.press('Enter'); await r.idle(700);
    await p.locator(`.o_data_row:has-text("${name}") td[name=name]`).first().click(); await r.idle(800);
  };

  // s03: de route op het product
  await r.goto('/odoo/action-stock.product_template_action_product/17');
  await r.startScene('s03');
  await r.click(tab('Voorraad'), { after: 600 });
  await r.highlight(fld('route_ids'), 2.6);
  await r.endScene();

  // s04: bevoorrading starten vanuit Aanvullen
  await r.cut(async () => { await r.goto('/odoo/action-stock.action_orderpoint_replenish'); });
  await r.startScene('s04');
  await r.type('.o_searchview_input', 'Cruiser', { delay: 80 });
  await p.keyboard.press('Enter'); await r.idle(800);
  const row = p.locator('.o_data_row:has-text("SQF")').first();
  await r.highlight(row, 1.4);
  await r.click(row.locator('td[name=qty_to_order], td[name=qty_to_order_manual]').first(), { after: 400 });
  await p.keyboard.press('Control+A'); await p.keyboard.type('10', { delay: 120 }); await r.wait(0.4);
  await r.click('button.o_list_button_save', { after: 900 });
  await r.clickCut(p.locator('.o_data_row:has-text("SQF") button:has-text("Bestellen")').first(), { wait: 2500 });
  await r.wait(0.8);
  await r.endScene();

  // de twee nieuwe overboekingen opzoeken
  const found = JSON.parse(rpc('call', 'stock.picking', 'search_read', JSON.stringify([
    [['product_id.default_code', '=', SKU], ['state', 'not in', ['done', 'cancel']]], ['name', 'location_dest_id']])));
  const out = found.find(x => x.name.startsWith('H800')), inn = found.find(x => x.name.startsWith('SQF/IN'));
  console.log('pickings', out && out.name, inn && inn.name);

  // s05: twee overboekingen
  await r.cut(async () => { await r.goto('/odoo/action-stock.action_picking_tree_all'); });
  await r.startScene('s05');
  await r.type('.o_searchview_input', 'Cruiser', { delay: 80 }); await r.wait(0.8);
  await r.click(p.locator('.o_searchview_autocomplete li:has-text("Product"), .o-dropdown-item:has-text("Product")').first(), { after: 900 });
  await r.highlight(p.locator(`.o_data_row:has-text("${out.name}")`).first(), 1.6);
  await r.highlight(p.locator(`.o_data_row:has-text("${inn.name}")`).first(), 1.6);
  await r.cut(async () => { await r.goto('/odoo/action-webship.webship_orders_action'); });
  await r.highlight(p.locator(`.o_data_row:has-text("${inn.name}")`).first(), 2.0);
  await r.endScene();

  // s06: stap 1 valideren in Odoo
  await r.cut(async () => { await openPicking(out.name); });
  await r.startScene('s06');
  await r.highlight(fld('location_dest_id'), 1.2);
  await r.clickCut('button[name=button_validate]', { wait: 2000 });
  const confirm = p.locator('.modal-footer button.btn-primary').first();
  if (await confirm.isVisible().catch(() => false)) await r.clickCut(confirm, { wait: 1500 });
  await r.highlight(p.locator('.o_statusbar_status').first(), 1.4);
  await r.endScene();

  // s07: stap 2 aankondigen in Stoqflow
  await r.cut(async () => { await openPicking(inn.name); await tab('Stoqflow').click(); await r.idle(300); });
  await r.startScene('s07');
  await r.highlight(fld('partner_id'), 1.4);
  await r.clickCut('button[name=ws_sync_picking]', { wait: 2500 });
  await p.locator('.o_notification_close').evaluateAll(es => es.forEach(e => e.click())).catch(() => {});
  await r.highlight(fld('df_url_po').or(fld('df_url_order')).first(), 1.2);
  await r.highlight(fld('df_status_webship'), 1.2);
  await r.endScene();

  // s08: ontvangen in Stoqflow, gevalideerd in Odoo
  const html = '/tmp/live09.html';
  ctl('po', 'advance', inn.name, '--to', 'unpacking');
  live('po', inn.name, html, false);
  await r.startScene('s08');
  await r.page.goto('file://' + html); await r.wait(3.0);
  ctl('po', 'receive', inn.name);
  live('po', inn.name, html, true); await r.page.goto('file://' + html); await r.wait(2.5);
  await r.cut(async () => { await new Promise(res => setTimeout(res, 1500)); rpc('fetch'); await openPicking(inn.name); });
  await r.highlight(p.locator('.o_statusbar_status').first(), 1.4);
  await r.highlight(fld('move_ids').or(fld('move_ids_without_package')).first(), 1.6);
  await r.endScene();
  await r.close();
})().catch(async e => { console.error(e); try { await global.__r.page.screenshot({ path: '/opt/rec/out/fail.png' }); } catch (x) {} process.exit(1); });
