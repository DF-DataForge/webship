# Verzendmethoden bpost en PostNL voor video 04 (en het verzonden order in video 07)
prod = env['product.product'].search([('name', '=', 'Verzending')], limit=1) or env['product.product'].create(
    {'name': 'Verzending', 'type': 'service', 'list_price': 0, 'sale_ok': False, 'purchase_ok': False})
for name in ('bpost', 'PostNL'):
    if not env['delivery.carrier'].search([('name', '=', name)]):
        env['delivery.carrier'].create({'name': name, 'delivery_type': 'fixed', 'fixed_price': 6.95, 'product_id': prod.id})
env.cr.commit()
print('carriers', env['delivery.carrier'].search([]).mapped('name'))
