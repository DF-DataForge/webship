# Contains several small model extensions that add Webship-specific
# fields to existing Odoo models: properties, product categories,
# product packaging, and stock warehouses.
from odoo.addons.webship.models.ws import WebShipHandler
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


class ProductPackaging(models.Model):
    """Extends product.packaging with an alternative Webship SKU.
    Used when the packaging unit has a different SKU in Webship
    than the main product (e.g. a box of 12 units)."""
    _inherit = 'product.packaging'

    # Alternative SKU used in Webship for this packaging unit
    df_sku_webship = fields.Char("SKU Stoqflow")
    # Webship product ID corresponding to the packaging SKU (auto-populated)
    df_product_id_webship = fields.Char("Product id Stoqflow")

    def _get_ws_handler(self):
        """Create and return a WebShipHandler instance using the stored API credentials."""
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')
        return WebShipHandler(login, pw, base_url)

    def ws_match_packaging(self):
        """Fetch the Stoqflow product ID for this packaging record based on its SKU."""
        handler = self._get_ws_handler()
        handler.set_env(self.env)

        for pkg in self:
            sku = pkg.df_sku_webship
            if not sku:
                _logger.info("ws_match_packaging: packaging '%s' (id=%s) has no SKU, skipping", pkg.name, pkg.id)
                continue

            result = handler.findProductBySku(sku)
            if isinstance(result, dict) and 'id' in result:
                pkg.df_product_id_webship = result['id']
                _logger.info(
                    "ws_match_packaging: packaging '%s' SKU=%s -> matched Stoqflow ID %s",
                    pkg.name, sku, result['id'],
                )
            elif isinstance(result, dict) and 'error' in result:
                _logger.warning(
                    "ws_match_packaging: packaging '%s' SKU=%s -> error: %s",
                    pkg.name, sku, result['error'],
                )
            else:
                _logger.warning(
                    "ws_match_packaging: packaging '%s' SKU=%s -> not found in Stoqflow",
                    pkg.name, sku,
                )


class StockWarehouse(models.Model):
    """Extends stock.warehouse with Webship identifiers so Odoo warehouses
    can be mapped to their Webship counterparts."""
    _inherit = 'stock.warehouse'

    # Webship warehouse ID linked to this Odoo warehouse
    df_warehouse_id_webship = fields.Char("Warehouse id Stoqflow", readonly=True)
    # Webship shop ID linked to this Odoo warehouse
    df_shop_id_webship = fields.Char("Shop id Stoqflow")
