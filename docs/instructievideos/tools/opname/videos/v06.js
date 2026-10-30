// Video 06: automatisering en bewaking (demo database)
const { Recorder } = require('../rec');
(async () => {
  const r = new Recorder('/opt/rec/out/06');
  const p = await r.launch(); await r.login();
  const SETTINGS = '/odoo/action-webship.webship_config_settings_action';
  const fld = n => p.locator(`div[name=${n}]`).first();
  const box = t => p.locator(`.o_setting_box:has-text("${t}")`).first();
  const check = async (n, on = true) => {
    const cb = fld(n).locator('input').first();
    await cb.scrollIntoViewIfNeeded();
    if ((await cb.isChecked()) !== on) await r.click(cb, { after: 400 });
    else { await r.moveTo(cb); await r.wait(0.4); }
  };
  const num = async (n, v) => { await r.type(fld(n).locator('input'), String(v), { delay: 90 }); };
  const save = () => r.clickCut('button.o_form_button_save');
  const tags = async (n, text, pick) => {
    await r.type(fld(n).locator('input'), text, { delay: 80 });
    await r.wait(0.7);
    await r.click(p.locator(`.o-autocomplete--dropdown-item:has-text("${pick}")`).first(), { after: 500 });
  };

  await r.goto(SETTINGS);
  // s02: naar Geplande taken
  await r.startScene('s02');
  await r.wait(0.6);
  const cron = box('Geplande acties');
  await cron.scrollIntoViewIfNeeded(); await r.wait(1.0);
  await r.highlight(cron, 1.4);
  await r.endScene();

  // s03: incrementele statusupdates aanzetten, daarna het schema
  await r.startScene('s03');
  await check('webship_use_status_update_queue');
  await r.highlight(box('Incrementele statusupdates'), 1.6);
  await r.cut(async () => {   // backorders koppelen (komt aan bod in video 10) en bewaren
    const cb = fld('webship_link_backorders').locator('input');
    if (!(await cb.isChecked())) await cb.click();
    await p.locator('button.o_form_button_save').first().click();
    await p.waitForTimeout(1500); await r.idle(600);
  });
  await r.page.goto('file:///opt/rec/slides/06_x03.html');
  await r.wait(7.5);
  await r.endScene();
  await r.cut(async () => { await r.goto(SETTINGS); });

  // s04: wachtende orders verwerken, om het kwartier
  await r.startScene('s04');
  await cron.scrollIntoViewIfNeeded(); await r.wait(0.5);
  await check('webship_cron_sync_statusP');
  await num('webship_cron_sync_statusP_interval_number', 15);
  await r.highlight(p.locator('.row:has(div[name=webship_cron_sync_statusP])').last(), 1.4);
  await r.endScene();

  // s05: gewijzigde orders om de 10 minuten; de zware methode uit
  await r.startScene('s05');
  await check('webship_cron_status_updates');
  await num('webship_cron_status_updates_interval_number', 10);
  await r.highlight(p.locator('.row:has(div[name=webship_cron_status_updates])').last(), 1.2);
  await check('webship_cron_sync_statussen', false);
  await r.highlight(p.locator('.row:has(div[name=webship_cron_sync_statussen])').last(), 1.4);
  await r.endScene();

  // s06: de andere taken
  await r.startScene('s06');
  for (const n of ['webship_cron_import_stock', 'webship_cron_daily_report', 'webship_cron_sync_retours',
                   'webship_cron_auto_delete_backorders', 'webship_cron_reclassify_object_types']) {
    await check(n);
    await r.highlight(p.locator(`.row:has(div[name=${n}])`).last(), 0.8);
  }
  await r.endScene();

  // s07: manueel uitvoeren
  await r.startScene('s07');
  await save();
  const run = fld('webship_cron_sync_statusP').locator('xpath=ancestor::div[contains(@class,"row")][1]').locator('button:has-text("Manueel uitvoeren")').first();
  await run.scrollIntoViewIfNeeded();
  await r.click(run, { after: 800 });
  await r.wait(0.8);
  await r.clickCut(p.locator('.modal-footer button.btn-primary').first(), { wait: 2500 });
  await r.wait(1.5);
  await r.endScene();

  // s08: foutnotificaties
  await r.cut(async () => { await r.goto(SETTINGS); });
  await r.startScene('s08');
  await fld('webship_error_notify_user_ids').scrollIntoViewIfNeeded(); await r.wait(0.6);
  await r.highlight(box('Ontvangers van notificaties'), 1.2);
  await tags('webship_error_notify_user_ids', 'Woody', 'Woody Admin');
  await r.type(fld('webship_error_notify_emails').locator('input'), 'logistiek@woodys.example', { delay: 45 });
  await r.wait(0.6);
  await r.endScene();

  // s09: syncpogingen en fouten in de chatter
  await r.startScene('s09');
  await num('webship_sync_retry_count', 3);
  await check('webship_log_errors_chatter');
  await r.highlight(box('Fouten loggen in de chatter'), 1.6);
  await r.endScene();

  // s10: dagelijks rapport
  await r.startScene('s10');
  await fld('webship_report_notify_user_ids').scrollIntoViewIfNeeded(); await r.wait(0.5);
  await tags('webship_report_notify_user_ids', 'Woody', 'Woody Admin');
  await save();
  const send = p.locator('button:has-text("Rapport nu versturen")').first();
  await send.scrollIntoViewIfNeeded();
  await r.click(send, { after: 1500 });
  await r.wait(1.0);
  await r.endScene();

  // s11: opslaan en laatste controle
  await r.startScene('s11');
  await save();
  const last = box('Tijdstippen laatste controle');
  await last.scrollIntoViewIfNeeded(); await r.wait(0.5);
  await r.highlight(last, 2.0);
  await r.endScene();
  await r.close();
})().catch(e => { console.error(e); process.exit(1); });
