# Contains several small model extensions that add Webship-specific
# fields to existing Odoo models: properties, product categories,
# and stock warehouses.
from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class WebshipProperty(models.Model):
    """Generic key-value property model for storing Webship configuration entries."""
    _name = "webship.property"
    _description = "Stoqflow properties"
    _order = "id desc"

    # Name identifying this property (e.g. a configuration key)
    name = fields.Char("Property name", required=True)
    # Free-text description of what this property controls
    description = fields.Text("Description")


class ProductCategory(models.Model):
    """Extends product.category with a Webship shop ID so products in
    this category are routed to the correct Webship shop."""
    _inherit = 'product.category'

    # Webship shop ID assigned to this product category
    df_cat_shop_id_webship = fields.Char("Shop id Stoqflow", readonly=True)


class StockWarehouse(models.Model):
    """Extends stock.warehouse with Webship identifiers so Odoo warehouses
    can be mapped to their Webship counterparts."""
    _inherit = 'stock.warehouse'

    # Webship warehouse ID linked to this Odoo warehouse
    df_warehouse_id_webship = fields.Char("Warehouse id Stoqflow", readonly=True)
    # Webship shop ID linked to this Odoo warehouse
    df_shop_id_webship = fields.Char("Shop id Stoqflow")
