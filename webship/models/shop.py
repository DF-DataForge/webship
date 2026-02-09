from odoo import models, fields

class WebshipShop(models.Model):
    _name = 'webship.shop'
    _description = 'Webship Shop'

    shop_id = fields.Char(string='Shop ID', required=True)
    name = fields.Char(string='Shop Name', required=True)

    brand_id = fields.Many2one(comodel_name='webship.brand', string='Brand')