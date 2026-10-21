# Model representing a shop in the Webship system.
# Shops belong to a brand and are used to determine which Webship shop
# an order or product should be assigned to during synchronization.
from odoo import models, fields

class WebshipShop(models.Model):
    _name = 'webship.shop'
    _description = 'Stoqflow Shop'

    # Unique shop identifier from the Webship API
    shop_id = fields.Char(string='Shop ID', required=True)
    # Human-readable shop name
    name = fields.Char(string='Shop Name', required=True)
    # Link to the parent brand this shop belongs to
    brand_id = fields.Many2one(comodel_name='webship.brand', string='Brand')
