// Video 05: producten klaarzetten voor Stoqflow (demo database)
const { Recorder } = require('../rec');
(async () => {
  const r = new Recorder('/opt/rec/out/05');
  const p = await r.launch(); await r.login();
  const fld = n => p.locator(`div[name=${n}]`).first();
  const tab = t => p.locator(`.nav-link:has-text("${t}")`).first();
  const btn = t => p.locator(`button:has-text("${t}")`).first();
  const TMPL = id => `/odoo/action-stock.product_template_action_product/${id}`;
  
  // s02: overzicht producten in Stoqflow (nog niets gesynchroniseerd)
  await r.goto('/odoo/action-webship.stoqflow_product_report_action');
  await r.startScene('s02');
  await r.wait(1.0);
  await r.highlight(p.locator('th[data-name=default_code]').first(), 1.6);
  await r.scroll(400, 1200);
  await r.endScene();

  // s03: de interne referentie is de SKU
  await r.cut(async () => { await r.goto(TMPL(5)); });
  await r.startScene('s03');
  await r.wait(0.6);
  await r.highlight(fld('default_code'), 2.6);
  await r.endScene();

  // s04: tabblad Stoqflow
  await r.startScene('s04');
  await r.click(tab('Stoqflow'), { after: 700 });
  await r.highlight(fld('df_product_do_not_send_webship'), 1.4);
  await r.highlight(p.locator('.tab-pane.active .o_horizontal_separator, .tab-pane.active .o_form_label').filter({ hasText: 'Productstatus' }).first(), 1.4);
  await r.endScene();

  // s05: productdetails voor het magazijn
  await r.startScene('s05');
  for (const n of ['df_brand_id', 'df_min_stock', 'df_length', 'df_hs_code', 'df_flag_fragile', 'df_check_batches']) {
    await r.highlight(fld(n), 0.9);
  }
  await r.endScene();

  // s06: bestaat al in Stoqflow -> matchen
  await r.startScene('s06');
  const match = btn('Matchen met Stoqflow');
  await match.scrollIntoViewIfNeeded();
  await r.click(match, { after: 1500 });
  await r.highlight(fld('df_url_prod'), 1.4);
  await r.highlight(fld('df_product_syncresult_webship'), 1.6);
  await r.endScene();

  // s07: nieuw -> synchroniseren (variant Black / M)
  const variants = async () => {
    await r.goto(TMPL(3));
    await p.locator('.oe_stat_button:has-text("Varianten")').first().click(); await r.idle(800);
  };
  await r.cut(async () => {
    await variants();
    await p.locator('.o_data_row').nth(1).locator('button:has-text("Bekijken")').first().click(); await r.idle(800);
    await tab('Stoqflow').click(); await r.idle(500);
  });
  await r.startScene('s07');
  await r.highlight(fld('default_code'), 1.0);
  const sync = btn('Synchroniseren met Stoqflow');
  await sync.scrollIntoViewIfNeeded();
  await r.click(sync, { after: 1500 });
  await r.highlight(fld('df_url_prod'), 1.2);
  await r.highlight(fld('df_product_lastsync_webship'), 1.2);
  await r.endScene();

  // s08: component nooit naar Stoqflow
  await r.cut(async () => { await r.goto(TMPL(9)); await tab('Stoqflow').click(); await r.idle(500); });
  await r.startScene('s08');
  await r.highlight(fld('df_product_do_not_send_webship'), 2.4);
  await r.endScene();

  // s09: varianten in bulk synchroniseren
  await r.cut(async () => { await r.goto(TMPL(3)); });
  await r.startScene('s09');
  await r.click(p.locator('.oe_stat_button:has-text("Varianten")').first(), { after: 900 });
  await r.click('thead .o_list_record_selector input', { after: 600 });
  await r.highlight(btn('Syncen met Stoqflow'), 1.2);
  await r.highlight(btn('Producten matchen met Stoqflow'), 1.0);
  await r.cut(async () => { await r.click(btn('Syncen met Stoqflow'), { after: 400 }); await p.waitForTimeout(8000); });
  await r.wait(1.0);
  await r.endScene();

  // s10: overzicht met filters
  await r.cut(async () => { await r.goto('/odoo/action-webship.stoqflow_product_report_action'); });
  await r.startScene('s10');
  await r.click('.o_searchview_dropdown_toggler, button.o_searchview_dropdown_toggler', { after: 700 });
  for (const f of ['Gesynchroniseerd', 'Synchronisatiefouten', 'Nooit gesynchroniseerd', 'Uitgesloten van synchronisatie']) {
    await r.highlight(p.locator(`.o_filter_menu .dropdown-item:has-text("${f}"), .o-dropdown-item:has-text("${f}")`).first(), 0.9);
  }
  await r.endScene();

  // s11: geen fouten
  await r.startScene('s11');
  await r.click(p.locator('.o-dropdown-item:has-text("Synchronisatiefouten"), .dropdown-item:has-text("Synchronisatiefouten")').first(), { after: 900 });
  await p.keyboard.press('Escape');
  await r.wait(1.6);
  await r.endScene();
  await r.close();
})().catch(e => { console.error(e); process.exit(1); });
