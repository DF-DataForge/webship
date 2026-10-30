// Video 03: magazijn, locatie en routes (demo database)
const { Recorder } = require('../rec');
(async () => {
  const r = new Recorder('/opt/rec/out/03');
  const p = await r.launch(); await r.login();
  const fld = n => p.locator(`div[name=${n}]`).first();
  const tab = t => p.locator(`.nav-link:has-text("${t}")`).first();

  // s03: voorraadinstellingen
  await r.goto('/odoo/action-stock.action_stock_config_settings');
  await r.startScene('s03');
  const box = t => p.locator(`.o_setting_box:has-text("${t}")`).first();
  await r.wait(0.6);
  await r.highlight(box('Opslaglocaties'), 1.6);
  await r.highlight(box('Routes met meerdere stappen'), 1.6);
  await r.moveTo('button.o_form_button_save'); await r.wait(0.6);
  await r.endScene();

  // s04: magazijnen, het Stoqflow-magazijn
  await r.goto('/odoo/action-stock.action_warehouse_form');
  await r.startScene('s04');
  await r.wait(0.6);
  await r.highlight('button.o_list_button_add', 1.2);
  await r.click('.o_data_row:has-text("Stoqflow Fulfilment") td[name=name]', { after: 900 });
  await r.highlight(fld('name'), 1.2);
  await r.highlight(fld('code'), 1.0);
  await r.highlight(fld('partner_id'), 1.2);
  await r.endScene();

  // s05: ontvangst en levering op 1 stap, bevoorraden vanuit
  await r.startScene('s05');
  await r.wait(0.4);
  await r.highlight(fld('reception_steps'), 2.0);
  await r.highlight(fld('delivery_steps'), 2.0);
  await r.highlight(fld('resupply_wh_ids'), 2.0);
  await r.endScene();

  // s06: locatie SQF/Voorraad aanvinken en aan het Stoqflow-magazijn koppelen
  await r.goto('/odoo/action-stock.action_location_form/16');
  await r.cut(async () => {
    const cb = fld('df_is_webship_location').locator('input');
    if (await cb.isChecked()) await cb.click();
    await p.waitForTimeout(400);
  });
  await r.startScene('s06');
  await r.wait(0.6);
  await r.highlight(p.locator('.o_breadcrumb, .o_last_breadcrumb_item').first(), 1.0);
  await r.click(fld('df_is_webship_location').locator('input'), { after: 500 });
  await r.type(fld('df_warehouse_webship').locator('input'), 'Stoqflow', { delay: 70 });
  await r.wait(0.8);
  await r.click(p.locator('.o-autocomplete--dropdown-item:has-text("Antwerpen")').first(), { after: 500 });
  await r.highlight(fld('df_warehouse_webship'), 1.4);
  await r.click('button.o_form_button_save', { after: 800 });
  await r.endScene();

  // s07: Stoqflow company ID
  await r.startScene('s07');
  await r.highlight(fld('df_warehouse_id_webship'), 2.4);
  await r.moveTo(fld('df_is_webship_location')); await r.wait(1.2);
  await r.endScene();

  // s08: verkoop vertrekt uit SQF — standaard magazijn, webshop, verkooporder
  await r.goto('/odoo/action-base.action_res_users/2');
  await r.startScene('s08');
  await r.click(tab('Voorkeuren'), { after: 600 });
  await r.highlight(fld('property_warehouse_id'), 1.8);
  await r.cut(async () => { await r.goto('/odoo/action-website.action_website_configuration'); });
  const wh = p.locator('.o_setting_box:has-text("Magazijn")').first();
  await wh.scrollIntoViewIfNeeded(); await r.wait(0.5);
  await r.highlight(wh, 1.8);
  await r.cut(async () => { await r.goto('/odoo/action-sale.action_quotations_with_onboarding/new'); });
  await r.type(fld('partner_id').locator('input'), 'Lotte', { delay: 70 });
  await r.wait(0.7);
  await r.click(p.locator('.o-autocomplete--dropdown-item:has-text("Lotte Peeters")').first(), { after: 700 });
  await r.click(tab('Overige info'), { after: 600 });
  await r.highlight(fld('warehouse_id'), 2.0);
  await r.endScene();

  // s09: aankoop — route Kopen, Leveren aan, aanvullen
  await r.cut(async () => { await r.goto('/odoo/action-stock.product_template_action_product/3'); });
  await r.startScene('s09');
  await r.click(tab('Voorraad'), { after: 600 });
  await r.highlight(fld('route_ids'), 1.8);
  await r.cut(async () => { await r.goto('/odoo/action-purchase.purchase_rfq/new'); });
  await r.click(tab('Overige info'), { after: 500 });
  await r.type(fld('picking_type_id').locator('input'), 'Stoqflow', { delay: 70 });
  await r.wait(0.7);
  await r.click(p.locator('.o-autocomplete--dropdown-item:has-text("Ontvangsten")').first(), { after: 500 });
  await r.highlight(fld('picking_type_id'), 1.6);
  await r.cut(async () => { await r.goto('/odoo/action-stock.action_orderpoint_replenish'); });
  await r.wait(1.0);
  await r.highlight(p.locator('.o_data_row:has-text("SQF")').first(), 2.0);
  await r.endScene();

  // s10: bevoorradingsroute op het product, daarna het schema
  await r.cut(async () => { await r.goto('/odoo/action-stock.product_template_action_product/16'); });
  await r.startScene('s10');
  await r.click(tab('Voorraad'), { after: 600 });
  await r.highlight(fld('route_ids'), 2.2);
  await r.page.goto('file:///opt/rec/slides/03_x10.html');
  await r.wait(5.5);
  await r.endScene();
  await r.close();
})().catch(e => { console.error(e); process.exit(1); });
