# Alle verkoopbare producten met SKU naar de (nagebootste) Stoqflow sturen, behalve uitgesloten
prods = env['product.product'].search([('default_code', '!=', False), ('df_product_do_not_send_webship', '=', False)])
ok = 0
for p in prods:
    if p.df_product_id_webship:
        continue
    p.ws_sync_product()
    ok += 1
env.cr.commit()
print('synced', ok, 'linked', len(prods.filtered('df_product_id_webship')), 'of', len(prods))
