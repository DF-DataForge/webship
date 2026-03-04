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
