from odoo import models, fields

class WebshipBrand(models.Model):
    _name = 'webship.brand'
    _description = 'Webship Brand'

    brand_id = fields.Char(string='Brand ID', required=True)
    name = fields.Char(string='Brand Name', required=True)