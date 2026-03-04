# Extends product.product (variants) with Webship synchronization fields.
# Products can be matched by SKU or fully synced (created/updated) to the
# Webship platform through the API handler.
from odoo.addons.webship.models.ws import WebShipHandler
from odoo import models, fields, api

from datetime import datetime

class Productvar(models.Model):
    _inherit = 'product.product'

    # HTML link to the product in the Webship web app (legacy field name)
    wsUrlProd = fields.Html('Code Stoqflow', compute="_compute_html_product", sanitize=False)

    # HTML link to the product in the Stoqflow web app
    df_url_prod = fields.Html('Code Stoqflow', compute="_compute_html_product", sanitize=False)

    # Webship product ID (set when the product is synced or matched)
    df_product_id_webship = fields.Char("Product id Stoqflow", readOnly=True)

    # Webship-specific product type classification determining how the product
    # is handled in the warehouse (basic, virtual, composite, derivative)
    df_productType = fields.Selection(
        selection=[
            ("basic", "Basic product"),
            ("virtual", "Virtual product - non pysical, eg. e-book"),
            ("compositionAhead", "Composite product - the composition product is assembled ahead of time and stored in the warehouse on its own warehouse location(s)."),
            ("compositionPicking", "Composite product - the underlying products of the composition are picked from their respective warehouse locations during the picking stage."),
            ("derivativeAhead", "Derivative product - the parent product is broken up ahead of time and stored in the warehouse on its own warehouse location(s)."),
            ("derivativePicking", "Derivative product - the parent product will be broken up during the picking stage leaving a rest/leftover at the parent products warehouse location.")
        ],
        string="Product type",
        default="basic"
    )

    # Flag indicating this is a biological product (for warehouse handling)
    df_stock_bio = fields.Boolean(string="Biological product", default=False)
    # Flag indicating this is a food product (for warehouse handling)
    df_stock_foodstuff = fields.Boolean(string="Food product", default=False)

    # Timestamp of the last synchronization to Webship
    df_product_lastsync_webship = fields.Datetime("Last sync on", readOnly=True)

    # HTML result message of the last sync attempt (success or error details)
    df_product_syncresult_webship = fields.Html("Result last sync", readOnly=True)

    # When True, this product is excluded from all Webship synchronizations
    df_product_do_not_send_webship = fields.Boolean("Never send this product to Stoqflow", default=False)

    @api.depends("default_code")
    def _compute_html_product(self):
        """Build an HTML snippet showing the product SKU with a clickable icon
        linking to the product page in the Webship web application."""
        for record in self:
            if record.default_code != False and record.df_product_id_webship != False:
                # Construct the direct URL to the product in Webship
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'products/' + record.df_product_id_webship

                html = record.default_code + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
                record.df_url_prod = html
                record.wsUrlProd = html
            else:
                record.df_url_prod = ''
                record.wsUrlProd = ''

    def getHandler(self):
        """Create and return a WebShipHandler instance using the stored API credentials."""
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)

        return wsHandler

    def ws_match_product(self):
        """Search Webship for a product matching this product's SKU and store
        the Webship product ID on the Odoo record if a unique match is found.
        Displays the result in the sync result field."""
        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        for record in self:
            # Require an SKU before attempting to match
            if record.default_code == False:
                sResult = ['Please provide an SKU in Odoo']
            else:
                sResult = wsHandler.match_product(record)

            # Display success or format errors as an HTML list
            if sResult == []:
                self.df_product_syncresult_webship = 'success'
            else:
                sOutput = '<p>Errors occured:</p>'
                sOutput = sOutput + '<ul>'
                for e in sResult:
                    sOutput += '<li>' + e + '</li>'
                sOutput = sOutput + '</ul>'

                self.df_product_syncresult_webship = sOutput



    def ws_sync_product(self):
        """Push this product's data (SKU, name, prices, barcode) to Webship.
        Creates a new product in Webship if no ID exists, otherwise updates.
        Displays the result in the sync result field."""
        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        for record in self:
            sResult = wsHandler.sync_product(record)

            # Record the sync timestamp
            self.df_product_lastsync_webship = datetime.now()

            # Display success or format errors as an HTML list
            if sResult == []:
                self.df_product_syncresult_webship = 'success'
            else:
                sOutput = '<p>Errors occured:</p>'
                sOutput = sOutput + '<ul>'
                for e in sResult:
                    sOutput += '<li>' + e + '</li>'
                sOutput = sOutput + '</ul>'

                self.df_product_syncresult_webship = sOutput

    def write(self, values):
        """Override write to allow future extensibility for Webship-specific logic."""
        return super(Productvar, self).write(values)

    def unlink(self):
        """Override unlink to allow future extensibility for Webship cleanup."""
        return super(Productvar, self).unlink()
