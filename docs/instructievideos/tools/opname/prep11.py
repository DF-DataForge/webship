# Voorbereiding video 11: leveringen in fout, een vervoerder die niet gekoppeld is, JSON-logging aan.
# Uitvoeren met: odoo-bin shell -d woody < prep11.py
from odoo import Command

icp = env['ir.config_parameter'].sudo()
icp.set_str('webship.log_json', 'True')

sqf = env['stock.warehouse'].search([('code', '=', 'SQF')], limit=1)
P = env['res.partner']
lotte = P.search([('name', '=', 'Lotte Peeters')], limit=1)
emma = P.search([('name', '=', 'Emma Janssens')], limit=1)
beanie = env['product.product'].search([('default_code', '=', 'WSS-BEANIE')], limit=1)

# 1. product dat nog niet in Stoqflow bestaat
sticker = env['product.product'].search([('default_code', '=', 'WSS-STICKER')], limit=1)
if not sticker:
    sticker = env['product.product'].create({'name': "Woody's Sticker Pack", 'default_code': 'WSS-STICKER',
                                             'type': 'consu', 'is_storable': True, 'list_price': 4.95})
    env['stock.quant']._update_available_quantity(sticker, sqf.lot_stock_id, 50)

# 2. klant zonder straat
noah = P.search([('name', '=', 'Noah Maes')], limit=1) or P.create({
    'name': 'Noah Maes', 'zip': '9000', 'city': 'Gent', 'country_id': env.ref('base.be').id,
    'email': 'noah.maes@example.com'})

def sell(partner, product, qty=1):
    so = env['sale.order'].create({'partner_id': partner.id, 'warehouse_id': sqf.id,
                                   'order_line': [Command.create({'product_id': product.id, 'product_uom_qty': qty})]})
    so.action_confirm()
    return so

orders = [sell(lotte, sticker, 2), sell(noah, beanie), sell(emma, beanie)]
env.cr.commit()

# Wachtende orders verwerken tot de syncpogingen op zijn -> processcode Fout
settings = env['res.config.settings'].create({})
for _ in range(4):
    settings.ws_sync_all_pickings_statusP()
    env.cr.commit()
for so in orders:
    for pk in so.picking_ids:
        print(so.name, pk.name, pk.df_process_code, (pk.df_picking_syncresult_webship or '')[:120])
