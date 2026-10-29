# Extends product.product (variants) with Webship synchronization fields.
# Products can be matched by SKU or fully synced (created/updated) to the
# Webship platform through the API handler.
from odoo.addons.webship.models.ws import WebShipHandler
from odoo import models, fields, api

from datetime import datetime

class Productvar(models.Model):
    _inherit = 'product.product'

    # HTML link to the product in the Webship web app (legacy field name)
    wsUrlProd = fields.Html('Product link Stoqflow', compute="_compute_html_product", sanitize=False)

    # HTML link to the product in the Stoqflow web app
    df_url_prod = fields.Html('Code Stoqflow', compute="_compute_html_product", sanitize=False)

    # Webship product ID (set when the product is synced or matched)
    df_product_id_webship = fields.Char("Product id Stoqflow", readonly=True)

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

    # --- Stoqflow product fields ---
    # Product type as per Stoqflow API (basic, composition, derivative)
    df_type = fields.Selection(
        selection=[
            ("basic", "Basic"),
            ("composition", "Composition"),
            ("derivative", "Derivative"),
        ],
        string="Stoqflow type",
        default="basic",
    )

    # Brand linked to this product in Stoqflow
    df_brand_id = fields.Many2one(
        comodel_name='webship.brand',
        string="Stoqflow brand",
    )

    # Stock type determines FIFO/LIFO/FEFO handling
    df_stock_type = fields.Selection(
        selection=[
            ("fifo", "FIFO"),
            ("lifo", "LIFO"),
            ("fefo", "FEFO"),
        ],
        string="Stock type",
    )

    # Stock levels
    df_min_stock = fields.Integer(string="Min stock", default=0)
    df_max_stock = fields.Integer(string="Max stock")
    df_min_order = fields.Integer(string="Min order qty", default=1)
    df_order_multiples = fields.Integer(string="Order multiples", default=1)

    # Physical properties (mm)
    df_length = fields.Integer(string="Length (mm)")
    df_width = fields.Integer(string="Width (mm)")
    df_height = fields.Integer(string="Height (mm)")

    # Trade / customs
    df_hs_code = fields.Char(string="HS code")
    df_country_of_origin = fields.Char(string="Country of origin", help="ISO 3166-1 alpha-2 code, e.g. NL, DE, CN")
    df_economic_operator = fields.Char(string="Economic operator")
    # Flags
    df_stock_bio = fields.Boolean(string="Biological product", default=False)
    df_stock_foodstuff = fields.Boolean(string="Food product", default=False)
    df_flag_cold_chain = fields.Boolean(string="Cold chain", default=False)
    df_flag_fragile = fields.Boolean(string="Fragile", default=False)
    df_flag_hazardous = fields.Boolean(string="Hazardous", default=False)

    # Checks
    df_check_expiry_dates = fields.Boolean(string="Expiry dates", default=False)
    df_check_batches = fields.Boolean(string="Batches", default=False)
    df_check_serial_numbers = fields.Boolean(string="Serial numbers", default=False)

    # Timestamp of the last synchronization to Webship
    df_product_lastsync_webship = fields.Datetime("Last sync on", readonly=True)

    # HTML result message of the last sync attempt (success or error details)
    df_product_syncresult_webship = fields.Html("Result last sync", readonly=True)

    # When True, this product is excluded from all Webship synchronizations
    df_product_do_not_send_webship = fields.Boolean("Never send this product to Stoqflow", default=False)

    @api.depends("default_code")
    def _compute_html_product(self):
        """Build an HTML snippet showing the product SKU with a clickable icon
        linking to the product page in the Webship web application."""
        for record in self:
            if record.default_code != False and record.df_product_id_webship != False:
                # Construct the direct URL to the product in Webship
                url = self.env['ir.config_parameter'].sudo().get_str(
                    'webship.base_app_url') + 'products/' + record.df_product_id_webship

                html = record.default_code + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
                record.df_url_prod = html
                record.wsUrlProd = html
            else:
                record.df_url_prod = ''
                record.wsUrlProd = ''

    def getHandler(self):
        """Create and return a WebShipHandler instance using the stored API credentials."""
        login = self.env['ir.config_parameter'].sudo().get_str('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_str('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_str('webship.base_url')

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
            # Honour the exclusion flag: a product marked "Never send this
            # product to Stoqflow" must not be pushed, even from the manual
            # Sync button (it is already skipped in the order/PO picking sync).
            if record.df_product_do_not_send_webship:
                record.df_product_syncresult_webship = (
                    "This product is flagged 'Never send this product to Stoqflow' "
                    "and was not synced. Uncheck the flag to sync it.")
                continue

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
