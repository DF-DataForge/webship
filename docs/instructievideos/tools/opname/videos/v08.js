// Video 08: van inkooporder tot inkomende levering (demo database + mock Stoqflow)
const { Recorder } = require('../rec');
const { execFileSync } = require('child_process');
const sh = (...a) => execFileSync(a[0], a.slice(1), { encoding: 'utf8' });
const ctl = (...a) => sh('python3', '/opt/stoqflow_mock/ctl.py', ...a);
const rpc = (...a) => sh('python3', '/opt/rec/odoo_rpc.py', ...a);
const live = (kind, ref, out, still) => sh('python3', '/opt/rec/live_slide.py', kind, ref, out, ...(still ? ['--still'] : []));

(async () => {
  const r = new Recorder('/opt/rec/out/08'); global.__r = r;
  const p = await r.launch(); await r.login();
  const fld = n => p.locator(`div[name=${n}]`).first();
  const tab = t => p.locator(`.nav-link:has-text("${t}")`).first();
  const pick = async (n, text, item) => {
    await r.type(fld(n).locator('input'), text, { delay: 70 }); await r.wait(0.8);
    await r.click(p.locator(`.o-autocomplete--dropdown-item:has-text("${item || text}")`).first(), { after: 500 });
  };
  const addLine = async (product, qty, visible = true) => {
    const add = p.getByText('Product toevoegen', { exact: true }).or(p.getByText('Regel toevoegen', { exact: true })).first();
    await r.click(add, { after: 500 });
    const inp = p.locator('.o_selected_row [name=product_id] input, .o_selected_row [name=product_and_description] input').first();
    await r.type(inp, product, { delay: visible ? 60 : 5 });
    await r.wait(0.9);
    await r.click(p.locator(`.o-autocomplete--dropdown-item:has-text("${product}")`).first(), { after: 600 });
    await r.type(p.locator('.o_selected_row [name=product_qty] input').first(), String(qty), { delay: 90 });
  };
  const newPO = async (lines, visible) => {
    await pick('partner_id', 'ThreadWorks', 'ThreadWorks Apparel');
    for (const [prod, q] of lines) await addLine(prod, q, visible);
    await r.click(tab('Overige info'), { after: 500 });
    await pick('picking_type_id', 'Stoqflow', 'Ontvangsten');
  };
  const title = async () => (await p.locator('.o_last_breadcrumb_item, .o_breadcrumb .active').last().innerText()).trim();

  // s03: inkooporder bij ThreadWorks, leveren aan Stoqflow Fulfilment
  await r.goto('/odoo/action-webship.webship_orders_action');
  await r.openApp('Inkoop', { create: true });
  await r.startScene('s03');
  await newPO([['WSS-TEE-BLK-M', 24], ['WSS-SOCKS', 120]], true);
  await r.highlight(fld('picking_type_id'), 1.4);
  await r.click('button[name=button_confirm]', { after: 1300 });
  await r.endScene();
  const po = await title(); console.log('PO', po);

  // s04: de ontvangst, object Inkooporder
  await r.startScene('s04');
  await r.click('button[name=action_view_picking]', { after: 1000 });
  await r.highlight(fld('location_dest_id'), 1.4);
  await r.click(tab('Stoqflow'), { after: 500 });
  const receiptUrl = p.url();
  const receipt = await title(); console.log('receipt', receipt);
  await r.cut(async () => { await r.goto('/odoo/action-webship.webship_orders_action'); });
  await r.highlight(p.locator(`.o_data_row:has-text("${receipt}")`).first(), 2.2);
  await r.endScene();

  // s05: doorsturen; de leverancier wordt aangemaakt in Stoqflow
  await r.cut(async () => { await r.goto(receiptUrl); await tab('Stoqflow').click(); await r.idle(400); });
  await r.startScene('s05');
  await r.clickCut('button[name=ws_sync_picking]', { wait: 2500 });
  await p.locator('.o_notification_close').evaluateAll(es => es.forEach(e => e.click())).catch(() => {});
  await r.highlight(fld('df_url_po').or(fld('df_url_order')).first(), 1.2);
  await r.highlight(fld('df_status_webship'), 1.2);
  await r.cut(async () => { await r.goto('/odoo/action-webship.stoqflow_partner_report_action'); });
  await r.highlight(p.locator('.o_data_row:has-text("ThreadWorks")').first(), 2.0);
  await r.endScene();

  // s06: in Stoqflow: onderweg, geleverd, uitpakken, voltooid
  const html = '/tmp/live08.html';
  live('po', receipt, html, false);
  await r.startScene('s06');
  await r.page.goto('file://' + html); await r.wait(3.0);
  for (let i = 0; i < 3; i++) {
    ctl('po', 'advance', receipt);
    live('po', receipt, html, true); await r.page.goto('file://' + html); await r.wait(2.0);
  }
  ctl('po', 'receive', receipt);
  live('po', receipt, html, true); await r.page.goto('file://' + html); await r.wait(3.0);
  await r.endScene();

  // s07: terug in Odoo: ontvangst gevalideerd, ontvangen aantallen, voorraad
  await r.cut(async () => { await new Promise(res => setTimeout(res, 1500)); rpc('fetch'); await r.goto(receiptUrl); });
  await r.startScene('s07');
  await r.highlight(p.locator('.o_statusbar_status').first(), 1.4);
  await r.highlight(fld('move_ids').or(fld('move_ids_without_package')).first(), 1.8);
  await r.cut(async () => {
    await r.openApp('Inkoop');
    await p.locator(`.o_data_row:has-text("${po}") td[name=name]`).first().click(); await r.idle(900);
  });
  await r.highlight(fld('order_line'), 2.2);
  await r.endScene();

  // s08: minder ontvangen dan besteld -> backorder (hoodies, 20 van 24)
  await r.cut(async () => {
    await p.locator('.o_list_button_add, .o_form_button_create').first().click().catch(() => {}); await r.idle(600);
    if (!p.url().includes('new')) { await r.openApp('Inkoop', { create: true }); }
    await newPO([['WSS-HOOD-BLK-L', 24]], false);
    await p.locator('button[name=button_confirm]').first().click(); await r.idle(1200);
    await p.locator('button[name=action_view_picking]').first().click(); await r.idle(900);
    await tab('Stoqflow').click(); await r.idle(300);
    await p.locator('button[name=ws_sync_picking]').first().click(); await p.waitForTimeout(2500); await r.idle(400);
  });
  const receipt2 = await title(); console.log('receipt2', receipt2);
  ctl('po', 'receive', receipt2, '--qty', 'WSS-HOOD-BLK-L=20', '--backorder');
  await r.cut(async () => { await new Promise(res => setTimeout(res, 1500)); rpc('fetch'); await p.reload(); await r.idle(900); });
  await r.startScene('s08');
  await r.highlight(fld('move_ids').or(fld('move_ids_without_package')).first(), 2.0);
  const boMsg = p.locator('.o-mail-Message:has-text("backorder")').first();
  await r.highlight(boMsg, 1.8);
  await r.highlight(p.locator('.o-mail-Message:has-text("Quantity")').first(), 1.4);
  await r.endScene();
  await r.close();
})().catch(async e => { console.error(e); try { await global.__r.page.screenshot({ path: '/opt/rec/out/fail.png' }); } catch (x) {} process.exit(1); });
