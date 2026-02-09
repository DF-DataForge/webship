from odoo.addons.webship.models.ws import WebShipHandler
from odoo import models, fields, api

from datetime import datetime
import pprint

class Productvar(models.Model):
    _inherit = 'product.product'

    wsUrlProd = fields.Html('Code webship', compute="_compute_html_product")

    df_url_prod = fields.Html('Code webship', compute="_compute_html_product")

    df_product_id_webship = fields.Char("Product id webship", readOnly=True)

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

    df_stock_bio = fields.Boolean(string="Biological product", default=False)
    df_stock_foodstuff = fields.Boolean(string="Food product", default=False)

    df_product_lastsync_webship = fields.Datetime("Last sync on", readOnly=True)

    df_product_syncresult_webship = fields.Html("Result last sync", readOnly=True)

    df_product_do_not_send_webship = fields.Boolean("Never send this product to Webship", default=False)

    @api.depends("default_code")
    def _compute_html_product(self):
        for record in self:
            if record.default_code != False and record.df_product_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'products/' + record.df_product_id_webship

                record.df_url_prod = record.default_code + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            else:
                record.df_url_prod = ''

    def getHandler(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)

        return wsHandler

    def ws_match_product(self):
        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        for record in self:
            if record.default_code == False:
                sResult = ['Please provide an SKU in Odoo']
            else:
                sResult = wsHandler.match_product(record)

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
        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        for record in self:
            sResult = wsHandler.sync_product(record)

            self.df_product_lastsync_webship = datetime.now()

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

        sync_products = self.env['ir.config_parameter'].sudo().get_param('webship.sync_products')

        if sync_products == True:
            modl = self.env['ir.model'].search([('model','=','product.product')])

            self.env['webship.events'].create({'modelTableKey':self.id, 'model':modl.id, 'status':'P', 'processTime':datetime.now(), 'dbAction':'U', 'product_id_webship':self.df_product_id_webship})

            result = super(Productvar, self).write(values)
            return result
        else:
            return super(Productvar, self).write(values)

    def unlink(self):
        sync_products = self.env['ir.config_parameter'].sudo().get_param('webship.sync_products')

        if sync_products == True:
            modl = self.env['ir.model'].search([('model', '=', 'product.product')])

            self.env['webship.events'].create(
                {'modelTableKey': self.id, 'model': modl.id, 'status': 'P', 'processTime': datetime.now(),
                 'dbAction': 'D', 'product_id_webship':self.df_product_id_webship})

            return super(Productvar, self).unlink()
        else:
            return super(Productvar).unlink()