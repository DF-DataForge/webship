# Voorbereiding video 09: 20 Cruiser-boards op voorraad in het eigen magazijn H800
p = env['product.product'].search([('default_code', '=', 'WSS-CMP-CRUISER-825')], limit=1)
loc = env['stock.warehouse'].search([('code', '=', 'H800')], limit=1).lot_stock_id
q = env['stock.quant'].with_context(inventory_mode=True).create({'product_id': p.id, 'location_id': loc.id, 'inventory_quantity': 20})
q.action_apply_inventory()
env.cr.commit()
print('H800 cruiser', p.with_context(location=loc.id).qty_available)
