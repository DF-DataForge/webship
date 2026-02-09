from odoo import models, fields

class StockLocations(models.Model):
    _inherit = 'stock.location'

    df_warehouse_id_webship = fields.Char("Warehouse id webship")

    df_shop_id_webship = fields.Char("Shop id webship", readOnly=True)

    df_is_webship_location = fields.Boolean("Is Webship locatie?", default=False)

    df_warehouse_webship = fields.Many2one(comodel_name='webship.warehouse', string='Webship warehouse')