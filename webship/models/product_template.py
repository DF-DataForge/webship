from odoo import models, fields

class Product(models.Model):
    _inherit = 'product.template'

    wsUrlProd = fields.Html('Code webship', compute="_compute_html_product")

    df_url_prod = fields.Html(
        related='product_variant_id.df_url_prod',
        string = 'Code webship',
        readonly=True,
        store=False
    )

    df_product_lastsync_webship = fields.Datetime(
        related='product_variant_id.df_product_lastsync_webship',
        string='Last sync on',
        readonly=True,
        store=False
    )

    df_product_syncresult_webship = fields.Html(
        related='product_variant_id.df_product_syncresult_webship',
        string='Result last sync',
        readonly=True,
        store=False
    )

    def ws_sync_product(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.ws_sync_product()
            else:
                raise ValueError("Cannot sync: Product has multiple variants.")

    def ws_match_product(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.ws_match_product()
            else:
                raise ValueError("Cannot match: Product has multiple variants.")