# Model representing a brand in the Webship system.
# Brands are fetched from the Webship API and stored locally
# for use in product synchronization and shop configuration.
from odoo import models, fields

class WebshipBrand(models.Model):
    _name = 'webship.brand'
    _description = 'Stoqflow Brand'

    # Unique brand identifier from the Webship API
    brand_id = fields.Char(string='Brand ID', required=True)
    # Human-readable brand name
    name = fields.Char(string='Brand Name', required=True)
