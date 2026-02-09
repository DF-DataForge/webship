from odoo.addons.webship.models.ws import WebShipHandler
from odoo import models, fields, api

from datetime import datetime
import pprint

class Partner(models.Model):
    _inherit = 'res.partner'
    #vat_label = fields.Char("VAT label",  store=True)
    #company_registry_label = fields.Char("Company registry label",  store=True)
    #is_coa_installed = fields.Boolean("Is COA installed",  store=True)

    df_supplier_id_webship = fields.Char("Supplier id webship", readOnly=True)
    df_is_supplier_in_webship = fields.Boolean("Supplier in Webship", default=False)
    df_client_id_webship = fields.Char("Client id webship", readOnly=True)
    df_is_client_in_webship = fields.Boolean("Client in Webship", default=True)
    df_last_webship_sync = fields.Datetime("Laatste wijziging gepusht naar webship op")
    df_partner_syncresult_webship = fields.Html("Resultaat laatste sync")

    df_client_code_webship = fields.Char("Client code webship", compute="_compute_code_client", store=True)

    df_supplier_code_webship = fields.Char("Supplier code webship", compute="_compute_code_supplier", store=True)


    df_url_client = fields.Html("Client id Webship", compute="_compute_html_client")
    df_url_supplier  = fields.Html('Supplier id Webship', compute="_compute_html_supplier")

    df_standard_internal_note = fields.Text("Standaard interne notitie voor pakket", help="Deze notitie wordt automatisch toegevoegd aan elke zending voor deze klant.")

    wsUrlClient = fields.Html("Client id Webship")
    wsUrlSupplier = fields.Html('Supplier id Webship')

    @api.depends("df_client_id_webship")
    def _compute_code_client(self):
        wsHandler = self.getHandler()
        for record in self:
            if record.df_client_id_webship != False:
                record.df_client_code_webship = wsHandler.fetchCode('clients', str(record.df_client_id_webship))
            else:
                record.df_client_code_webship = ''

    @api.depends("df_supplier_id_webship")
    def _compute_code_supplier(self):
        wsHandler = self.getHandler()
        for record in self:
            if record.df_supplier_id_webship != False:
                record.df_supplier_code_webship = wsHandler.fetchCode('suppliers', str(record.df_supplier_id_webship))
            else:
                record.df_supplier_code_webship = ''

    @api.depends("df_client_id_webship")
    def _compute_html_client(self):
        for record in self:
            if record.df_client_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param('webship.base_app_url') + 'clients/' + record.df_client_id_webship
                record.df_url_client = record.df_client_code_webship +' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            else:
                record.df_url_client = ''

    @api.depends("df_supplier_id_webship")
    def _compute_html_supplier(self):
        for record in self:
            if record.df_supplier_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'suppliers/' + record.df_supplier_id_webship
                record.df_url_supplier = record.df_supplier_code_webship + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            else:
                record.df_url_supplier = ''

    def getHandler(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)

        return wsHandler

    def ws_match_partner(self):
        wsHandler = self.getHandler()

        for record in self:
            if record.df_is_client_in_webship:
                sResult = wsHandler.match_partner(record)
            if record.df_is_supplier_in_webship:
                sResult = wsHandler.match_supplier(record)

            if record.df_is_client_in_webship == False and record.df_is_supplier_in_webship == False:
                sResult = ['Please set to client or supplier']

            if sResult == []:
                self.df_partner_syncresult_webship = 'Success'
            else:
                sOutput = '<p>Errors occured:</p>'
                sOutput = sOutput + '<ul>'
                for e in sResult:
                    sOutput += '<li>' + e + '</li>'
                sOutput = sOutput + '</ul>'

                self.df_partner_syncresult_webship = sOutput

    def ws_sync_partner(self):
        wsHandler = self.getHandler()

        for record in self:
            if record.df_is_client_in_webship:
                sResult = wsHandler.sync_partner(record)
            if record.df_is_supplier_in_webship:
                sResult = wsHandler.sync_supplier(record)

            if record.df_is_client_in_webship == False and record.df_is_supplier_in_webship == False:
                sResult = ['Please set to client or supplier']

            if sResult == []:
                self.df_partner_syncresult_webship = 'Success'
            else:
                sOutput = '<p>Errors occured:</p>'
                sOutput = sOutput + '<ul>'
                for e in sResult:
                    sOutput += '<li>' + e + '</li>'
                sOutput = sOutput + '</ul>'

                self.df_partner_syncresult_webship = sOutput