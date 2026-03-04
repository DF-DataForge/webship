# Model representing a warehouse in the Webship system.
# Warehouses are fetched from the Webship API and linked to
# Odoo stock locations for routing purchase orders to the correct warehouse.
from odoo import models, fields

class WebshipWarehouse(models.Model):
    _name = 'webship.warehouse'
    _description = 'Stoqflow warehouse'

    # Unique warehouse identifier from the Webship API
    warehouse_id = fields.Char(string='Warehouse ID', required=True)
    # Human-readable warehouse name
    name = fields.Char(string='Warehouse Name', required=True)
