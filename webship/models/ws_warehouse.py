from odoo import models, fields

class WebshipWarehouse(models.Model):
    _name = 'webship.warehouse'
    _description = 'Webship warehouse'

    warehouse_id = fields.Char(string='Warehouse ID', required=True)
    name = fields.Char(string='Warehouse Name', required=True)