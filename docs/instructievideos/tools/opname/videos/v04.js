// Video 04: synchronisatieregels — orders, klanten en vervoerders (demo database)
const { Recorder } = require('../rec');
(async () => {
  const r = new Recorder('/opt/rec/out/04');
  const p = await r.launch(); await r.login();
  const SETTINGS = '/odoo/action-webship.webship_config_settings_action';
  const fld = n => p.locator(`div[name=${n}]`).first();
  const box = t => p.locator(`.o_setting_box:has-text("${t}")`).first();
  const check = async (n, on = true) => {
    const cb = fld(n).locator('input');
    await cb.scrollIntoViewIfNeeded();
    if ((await cb.isChecked()) !== on) await r.click(cb, { after: 400 });
    else { await r.moveTo(cb); await r.wait(0.4); }
  };
  const select = async (n, label) => {
    await r.click(fld(n).locator('input'), { after: 500 });
    await r.click(p.locator('.o_select_menu_item, .o_select_menu_menu .dropdown-item').filter({ hasText: label }).first(), { after: 400 });
  };
  const save = () => r.click('button.o_form_button_save', { after: 900 });

  await r.goto(SETTINGS);
  // s02: overzicht van de instellingen
  await r.startScene('s02');
  await r.wait(0.8); await r.scroll(1400, 2500); await r.wait(0.6); await r.scroll(-1400, 1200);
  await r.endScene();

  // s03: ordersynchronisatie
  await r.startScene('s03');
  await r.highlight(box('Ordersynchronisatie'), 1.2);
  await r.highlight(fld('webship_sync_order'), 1.4);
  await r.highlight(fld('webship_order_available_condition'), 1.6);
  await r.endScene();

  // s04: backorder, contactgegevens, annuleren
  await r.startScene('s04');
  for (const n of ['webship_auto_create_backorder', 'webship_fallback_sale_order_contact', 'webship_cancel_on_picking_cancel']) {
    await check(n); await r.wait(0.5);
  }
  await r.endScene();

  // s05: standaardstatussen
  await r.startScene('s05');
  await r.highlight(box('Standaardstatussen'), 1.2);
  await select('webship_default_status', 'Klaar om te picken');
  await r.highlight(fld('webship_default_po_status'), 1.4);
  await r.endScene();

  // s06: domeinfilter (getoond, niet bewaard)
  await r.startScene('s06');
  await r.highlight(box('Domeinfilter'), 1.2);
  await r.type(fld('webship_domain_text').locator('input, textarea'), '[("sale_id.website_id", "!=", False)]', { delay: 35 });
  await r.wait(1.5);
  await r.cut(async () => {
    const i = fld('webship_domain_text').locator('input, textarea');
    await i.fill(''); await i.press('Tab'); await p.waitForTimeout(300);
  });
  await r.endScene();

  // s07: weergave en genegeerde SKU's
  await r.startScene('s07');
  await r.highlight(box('Weergave'), 1.6);
  await r.type(fld('webship_ignored_skus').locator('textarea, input'), 'VERPAKKING-A', { delay: 70 });
  await r.wait(0.8);
  await r.endScene();

  // s08: vervoerders laden en beheren
  await r.startScene('s08');
  await check('webship_fetch_courier');
  await save();
  const load = p.locator('button:has-text("Vervoerders laden uit Stoqflow")').first();
  await load.scrollIntoViewIfNeeded();
  await r.click(load, { after: 1300 });
  await r.highlight('.o_notification', 1.6);
  await r.click(p.locator('button:has-text("Stoqflow-vervoerders beheren")').first(), { after: 900 });
  await r.wait(1.6);
  await r.endScene();

  // s09: verzendmethode bpost koppelen
  await r.cut(async () => { await r.goto('/odoo/action-delivery.action_delivery_carrier_form'); });
  await r.startScene('s09');
  await r.click(p.locator('.o_data_row:has-text("bpost") td[name=name]').first(), { after: 900 });
  await r.type(fld('df_stoqflow_courier_id').locator('input'), 'bpost', { delay: 80 });
  await r.wait(0.7);
  await r.click(p.locator('.o-autocomplete--dropdown-item:has-text("bpost")').first(), { after: 500 });
  await r.highlight(fld('df_stoqflow_courier_id'), 1.2);
  await r.click('button.o_form_button_save', { after: 800 });
  await r.endScene();
  await r.cut(async () => {   // PostNL ook koppelen (niet in beeld)
    await r.goto('/odoo/action-delivery.action_delivery_carrier_form');
    await p.locator('.o_data_row:has-text("PostNL") td[name=name]').first().click(); await r.idle(600);
    await fld('df_stoqflow_courier_id').locator('input').fill('PostNL'); await p.waitForTimeout(900);
    await p.locator('.o-autocomplete--dropdown-item:has-text("PostNL")').first().click(); await r.idle(300);
    await p.locator('button.o_form_button_save').first().click(); await r.idle(600);
  });

  // s10: klanten matchen
  await r.cut(async () => { await r.goto(SETTINGS); });
  await r.startScene('s10');
  await fld('webship_contact_match_sequence').scrollIntoViewIfNeeded(); await r.wait(0.6);
  await r.highlight(box('Matchingsequentie'), 1.4);
  await select('webship_contact_match_sequence', 'Btw → e-mail');
  await check('webship_match_on_order_sync');
  await r.wait(0.8);
  await r.endScene();

  // s11: leveranciers matchen
  await r.startScene('s11');
  await fld('webship_supplier_match_sequence').scrollIntoViewIfNeeded();
  await select('webship_supplier_match_sequence', 'Btw → e-mail');
  await check('webship_match_on_po_sync');
  await r.endScene();

  // s12: contacten zonder of met ongeldig e-mailadres
  await r.startScene('s12');
  await r.highlight(box('Contacten zonder e-mail toelaten'), 1.6);
  await check('webship_drop_invalid_email');
  await r.wait(0.8);
  await r.endScene();

  // s13: opslaan
  await r.startScene('s13');
  await save();
  await r.wait(1.2);
  await r.endScene();
  await r.close();
})().catch(e => { console.error(e); process.exit(1); });
