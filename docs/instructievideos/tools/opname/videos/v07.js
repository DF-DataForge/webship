// Video 07: van verkooporder tot uitgaande levering (demo database + mock Stoqflow)
const { Recorder } = require('../rec');
const { execFileSync } = require('child_process');
const sh = (...a) => execFileSync(a[0], a.slice(1), { encoding: 'utf8' });
const ctl = (...a) => sh('python3', '/opt/stoqflow_mock/ctl.py', ...a);
const rpc = (...a) => sh('python3', '/opt/rec/odoo_rpc.py', ...a);
const live = (kind, ref, out, still) => sh('python3', '/opt/rec/live_slide.py', kind, ref, out, ...(still ? ['--still'] : []));

(async () => {
  const r = new Recorder('/opt/rec/out/07'); global.__r = r;
  const p = await r.launch(); await r.login();
  const fld = n => p.locator(`div[name=${n}]`).first();
  const tab = t => p.locator(`.nav-link:has-text("${t}")`).first();
  const SO_NEW = '/odoo/sales/new';
  const pick = async (n, text, item) => {
    await r.type(fld(n).locator('input'), text, { delay: 70 }); await r.wait(0.7);
    await r.click(p.locator(`.o-autocomplete--dropdown-item:has-text("${item || text}")`).first(), { after: 500 });
  };
  const addLine = async (product, qty) => {
    await r.click(p.getByText('Regel toevoegen', { exact: true }).first(), { after: 500 });
    const row = p.locator('.o_selected_row').first();
    await r.type(row.locator('[name=product_and_description] input, [name=product_template_id] input').first(), product, { delay: 60 });
    await r.wait(0.8);
    await r.click(p.locator(`.o-autocomplete--dropdown-item:has-text("${product}")`).first(), { after: 600 });
    await r.type(p.locator('.o_selected_row [name=product_uom_qty] input').first(), String(qty), { delay: 90 });
  };
  const soName = async () => (await p.locator('.o_breadcrumb .active, .o_last_breadcrumb_item').last().innerText()).trim();

  // s03: verkooporder voor Lotte Peeters
  await r.goto('/odoo/action-webship.webship_orders_action');
  await r.openApp('Verkoop', { create: true });
  await r.startScene('s03');
  await pick('partner_id', 'Lotte', 'Lotte Peeters');
  await addLine("Woody's Crew Socks", 2);
  await addLine("Woody's Beanie", 1);
  await r.click(tab('Overige info'), { after: 500 });
  await r.highlight(fld('warehouse_id'), 1.4);
  await r.click('button[name=action_confirm]', { after: 1200 });
  await r.endScene();
  const so = await soName();
  console.log('SO', so);

  // s04: de levering en de processcode
  await r.startScene('s04');
  await r.click('button[name=action_view_delivery]', { after: 1000 });
  await r.highlight(fld('location_id'), 1.2);
  await r.click(tab('Stoqflow'), { after: 600 });
  await r.highlight(p.locator('.tab-pane.active').first(), 1.6);
  const deliveryUrl = p.url();
  await r.cut(async () => { await r.goto('/odoo/action-webship.webship_orders_action'); });
  await r.highlight(p.locator('.o_data_row').first(), 2.0);
  await r.highlight(p.locator('th[data-name=df_process_code]').first(), 1.2);
  await r.endScene();

  // s05: doorsturen met Manueel synchroniseren
  await r.cut(async () => { await r.goto(deliveryUrl); await tab('Stoqflow').click(); await r.idle(400); });
  await r.startScene('s05');
  await r.clickCut('button[name=ws_sync_picking]', { wait: 2500 });
  await r.wait(0.6);
  await r.endScene();

  // s06: resultaat op het tabblad Stoqflow
  await r.startScene('s06');
  await p.locator('.o_notification_close').evaluateAll(es => es.forEach(e => e.click())).catch(() => {});
  for (const n of ['df_url_order', 'df_picking_lastsync_webship', 'df_picking_syncresult_webship', 'df_status_webship']) {
    await r.highlight(fld(n), 1.1);
  }
  await r.endScene();

  // s07: in Stoqflow: picken, inpakken, verzenden (live toestand van de nagebootste Stoqflow)
  const html = '/tmp/live07.html';
  live('order', so, html, false);
  await r.startScene('s07');
  await r.page.goto('file://' + html); await r.wait(3.0);
  for (const step of ['picking', 'packing']) {
    ctl('order', 'advance', so, '--to', step);
    live('order', so, html, true); await r.page.goto('file://' + html); await r.wait(2.2);
  }
  ctl('order', 'ship', so, '--courier', 'bpost');
  live('order', so, html, true); await r.page.goto('file://' + html); await r.wait(3.5);
  await r.endScene();

  // s08: terug in Odoo: automatisch gevalideerd, pakketten, pickanalyse, geleverd op de verkooporder
  await r.cut(async () => { await new Promise(res => setTimeout(res, 1500)); rpc('fetch'); await r.goto(deliveryUrl); });
  await r.startScene('s08');
  await r.highlight(p.locator('.o_statusbar_status').first(), 1.4);
  await r.click(tab('Stoqflow'), { after: 400 });
  await r.highlight(fld('df_status_webship'), 1.2);
  await r.click(tab('Stoqflow-pakketten'), { after: 500 });
  await r.highlight(p.locator('.tab-pane.active').first(), 1.8);
  await r.click(tab('Pickanalyse'), { after: 500 });
  await r.highlight(p.locator('.tab-pane.active').first(), 1.4);
  await r.cut(async () => {
    await r.openApp('Verkoop');
    await p.locator(`.o_data_row:has-text("${so}") td[name=name]`).first().click(); await r.idle(900);
  });
  await r.highlight(fld('order_line'), 2.2);
  await r.endScene();

  // s09: niet zelf valideren
  await r.cut(async () => {
    await r.goto('/odoo/action-webship.webship_orders_action');
    await p.locator('.o_data_row:has-text("SQF/OUT/00003") td[name=name]').first().click(); await r.idle(800);
  });
  await r.startScene('s09');
  await r.click('button[name=button_validate]', { after: 1000 });
  await r.highlight(p.locator('.modal-content').first(), 2.6);
  await r.click(p.locator('.modal-footer button').first(), { after: 500 });
  await r.endScene();

  // s10: gedeeltelijke levering -> backorder (Concrete Wave, 20 van 24 sokken)
  ctl('order', 'ship', 'S00004', '--qty', 'WSS-SOCKS=20', '--courier', 'postnl', '--backorder');
  await r.cut(async () => {
    await new Promise(res => setTimeout(res, 1500)); rpc('fetch');
    await r.goto('/odoo/action-webship.webship_orders_action');
    await p.locator('.o_data_row:has-text("SQF/OUT/00004") td[name=name]').first().click(); await r.idle(800);
  });
  await r.startScene('s10');
  await r.highlight(p.locator('.o_field_widget[name=move_ids_without_package], div[name=move_ids]').first(), 2.2);
  const boMsg = p.locator('.o-mail-Message:has-text("backorder")').first();
  await r.highlight(boMsg, 1.6);
  await r.clickCut(boMsg.locator('a').first());
  await r.click(tab('Stoqflow'), { after: 500 });
  await r.highlight(p.locator('.tab-pane.active').first(), 2.2);
  await r.highlight(p.locator('.o-mail-Chatter, .o_mail_thread').first(), 1.6);
  await r.endScene();

  // s11: een order annuleren
  await r.cut(async () => { await r.openApp('Verkoop', { create: true }); });
  await r.cut(async () => {
    await fld('partner_id').locator('input').fill('Jonas'); await p.waitForTimeout(900);
    await p.locator('.o-autocomplete--dropdown-item:has-text("Jonas de Vries")').first().click(); await r.idle(500);
    await p.getByText('Regel toevoegen', { exact: true }).first().click(); await r.idle(400);
    await p.locator('.o_selected_row [name=product_and_description] input').first().fill("Woody's Beanie");
    await p.waitForTimeout(900);
    await p.locator(`.o-autocomplete--dropdown-item:has-text("Woody's Beanie")`).first().click(); await r.idle(500);
    await p.locator('button[name=action_confirm]').first().click(); await r.idle(1200);
    await p.locator('button[name=action_view_delivery]').first().click(); await r.idle(900);
    await tab('Stoqflow').click(); await r.idle(300);
    await p.locator('button[name=ws_sync_picking]').first().click(); await p.waitForTimeout(2500); await r.idle(500);
    await p.locator('.o_notification_close').evaluateAll(es => es.forEach(e => e.click())).catch(() => {});
    await p.locator('.o_breadcrumb a').first().click(); await r.idle(900);
  });
  await r.startScene('s11');
  await r.click('button[name=action_cancel]', { after: 900 });
  const confirmCancel = p.locator('.modal-footer button:has-text("Annuleren"), .modal-footer button.btn-primary').first();
  if (await confirmCancel.isVisible().catch(() => false)) await r.click(confirmCancel, { after: 1200 });
  await r.click('button[name=action_view_delivery]', { after: 900 });
  await r.click(tab('Stoqflow'), { after: 500 });
  await r.highlight(fld('df_status_webship'), 1.6);
  await r.highlight(fld('df_picking_syncresult_webship'), 1.6);
  await r.endScene();
  await r.close();
})().catch(async e => { console.error(e); try { await global.__r.page.screenshot({ path: '/opt/rec/out/fail.png' }); } catch (x) {} process.exit(1); });
