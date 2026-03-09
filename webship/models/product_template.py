# Extends product.template to expose Webship fields from the product variant.
# Because Webship sync operates on product.product (variants), these related
# fields surface the variant's sync status on the template form view.
from odoo import models, fields

class Product(models.Model):
    _inherit = 'product.template'

    # HTML link to the product in the Webship web app (from variant)
    wsUrlProd = fields.Html(
        related='product_variant_id.wsUrlProd',
        string='Code Stoqflow',
        readonly=True,
        store=False
    )

    # Duplicate HTML link field (kept for backward compatibility with views)
    df_url_prod = fields.Html(
        related='product_variant_id.df_url_prod',
        string = 'Code Stoqflow',
        readonly=True,
        store=False
    )

    # Timestamp of the last successful sync to Webship (from variant)
    df_product_lastsync_webship = fields.Datetime(
        related='product_variant_id.df_product_lastsync_webship',
        string='Last sync on',
        readonly=True,
        store=False
    )

    # HTML result message of the last sync attempt (from variant)
    df_product_syncresult_webship = fields.Html(
        related='product_variant_id.df_product_syncresult_webship',
        string='Result last sync',
        readonly=True,
        store=False
    )

    # --- Stoqflow product fields (related to variant) ---
    df_type = fields.Selection(related='product_variant_id.df_type', string='Stoqflow type', readonly=False)
    df_brand_id = fields.Many2one(related='product_variant_id.df_brand_id', string='Stoqflow brand', readonly=False)
    df_stock_type = fields.Selection(related='product_variant_id.df_stock_type', string='Stock type', readonly=False)
    df_min_stock = fields.Integer(related='product_variant_id.df_min_stock', string='Min stock', readonly=False)
    df_max_stock = fields.Integer(related='product_variant_id.df_max_stock', string='Max stock', readonly=False)
    df_min_order = fields.Integer(related='product_variant_id.df_min_order', string='Min order qty', readonly=False)
    df_order_multiples = fields.Integer(related='product_variant_id.df_order_multiples', string='Order multiples', readonly=False)
    df_length = fields.Integer(related='product_variant_id.df_length', string='Length (mm)', readonly=False)
    df_width = fields.Integer(related='product_variant_id.df_width', string='Width (mm)', readonly=False)
    df_height = fields.Integer(related='product_variant_id.df_height', string='Height (mm)', readonly=False)
    df_hs_code = fields.Char(related='product_variant_id.df_hs_code', string='HS code', readonly=False)
    df_country_of_origin = fields.Char(related='product_variant_id.df_country_of_origin', string='Country of origin', readonly=False)
    df_economic_operator = fields.Char(related='product_variant_id.df_economic_operator', string='Economic operator', readonly=False)
    df_stock_bio = fields.Boolean(related='product_variant_id.df_stock_bio', string='Biological product', readonly=False)
    df_stock_foodstuff = fields.Boolean(related='product_variant_id.df_stock_foodstuff', string='Food product', readonly=False)
    df_flag_cold_chain = fields.Boolean(related='product_variant_id.df_flag_cold_chain', string='Cold chain', readonly=False)
    df_flag_fragile = fields.Boolean(related='product_variant_id.df_flag_fragile', string='Fragile', readonly=False)
    df_flag_hazardous = fields.Boolean(related='product_variant_id.df_flag_hazardous', string='Hazardous', readonly=False)
    df_check_expiry_dates = fields.Boolean(related='product_variant_id.df_check_expiry_dates', string='Expiry dates', readonly=False)
    df_check_batches = fields.Boolean(related='product_variant_id.df_check_batches', string='Batches', readonly=False)
    df_check_serial_numbers = fields.Boolean(related='product_variant_id.df_check_serial_numbers', string='Serial numbers', readonly=False)
    def ws_sync_product(self):
        """Sync this product template to Webship by delegating to its single variant.
        Raises an error if the template has multiple variants since Webship
        expects one-to-one product mapping."""
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.ws_sync_product()
            else:
                raise ValueError("Cannot sync: Product has multiple variants.")

    def ws_match_product(self):
        """Match this product template with a Webship product by SKU.
        Delegates to the single variant's match method.
        Raises an error if the template has multiple variants."""
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.ws_match_product()
            else:
                raise ValueError("Cannot match: Product has multiple variants.")
