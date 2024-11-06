# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import requests
from requests.auth import HTTPBasicAuth

from . import ws
from odoo import fields, models
import json


class ResConfigSettings(models.TransientModel):
    _inherit = ['res.config.settings']

    webship_login = fields.Char(string='Webship username', config_parameter='webship.username')
    webship_password = fields.Char(string='Webship password', config_parameter='webship.password')
    webship_url = fields.Char(string='Webship base URL', config_parameter='webship.base_url')
    webship_app_url = fields.Char(string='Webship base URL', config_parameter='webship.base_app_url')
    webship_last_tested = fields.Char(string='Webship laatst getest', config_parameter='webship.last_tested')

    webship_modus = fields.Selection([('a','Sync nodig'),
                                   ('b','Sync niet nodig')
                                   ],string='Algemene modus', default='a', required=True)

    webship_sync_order = fields.Boolean(string="Orders syncen", config_parameter='webship.sync_order')
    webship_sync_producten = fields.Boolean(string="Producten syncen", config_parameter='webship.sync_products')
    webship_sync_klanten = fields.Boolean(string="Klanten syncen", config_parameter='webship.sync_klanten')
    webship_sync_leveranciers = fields.Boolean(string="Leveranciers syncen", config_parameter='webship.sync_leveranciers')

    webship_locations = fields.One2many('stock.location', 'id', string='Webship stock locaties')

    testSku = fields.Char(string="Voor sku in")

    def syncAll(self):
        print('hi')

    def ws_exp_sup_cl(self):
        return {'type': 'ir.actions.act_url', 'url': '/web/download/excel?p=partner', 'target': 'self'}

    def ws_fetch_warehouses(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        wsHandler = ws.WebShipHandler(login, pw)
        wsHandler.ws_fetch_warehouses(self.env)

    def ws_fetch_locations(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        wsHandler = ws.WebShipHandler(login, pw)
        wsHandler.ws_fetch_locations(self.env)
    def ws_syncall(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        wsHandler = ws.WebShipHandler(login, pw)

        wsHandler.sync_all(self.env)

    def ws_import_sup(self):
        wsHandler = ws.WebShipHandler(self.webship_login, self.webship_password)
        allSups = self.env['res.partner'].search([])

        for s in allSups:
            wsHandler.sync_sup(s)

    def ws_import_orders(self):
        wsHandler = ws.WebShipHandler(self.webship_login, self.webship_password)
        allOrders = self.env['sale.order'].search([])

        for o in allOrders:
            wsHandler.sync_order(o)

    def ws_import_prods(self):
        wsHandler = ws.WebShipHandler(self.webship_login, self.webship_password)
        allProds = self.env['product.product'].search([])

        for p in allProds:
            wsHandler.sync_prod(p)
    def ws_empty_db(self):
        wsHandler = ws.WebShipHandler(self.webship_login, self.webship_password)

        wsHandler.emptyOrders()
        wsHandler.emptyProducts()
        wsHandler.emptyClients()
        wsHandler.emptySuppliers()
    def ws_prod_to_ws(self):
        wsHandler = ws.WebShipHandler(self.webship_login, self.webship_password)

        #allProds =  self.env['product.product'].search([('default_code', '!=', False)])
        allProds = self.env['product.product'].search([('id', '=', 5)])

        for p in allProds:
            print(p.id)
            print(p.name)
            print(p.default_code)
            sValues = {'name':p.name, 'default_code':p.default_code, 'product_id_webship':p.product_id_webship}

            wsHandler.updateProduct(sValues)

    def ws_sync_orders(self):
        self.env['webship.events'].performSync()

    def ws_reset_codes(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = ws.WebShipHandler(login, pw, base_url)

        for r in self.env['stock.picking'].search([('df_picking_id_webship', '!=', False),('df_picking_id_webship', '!=', '')]):
            r.fetch_picking_code()

        for r in self.env['stock.picking'].search([('df_po_id_webship', '!=', False),('df_po_id_webship', '!=', '')]):
            r.fetch_po_code()


    def ws_test_verbinding(self):
        if self.webship_login == False or self.webship_password == False or self.webship_url == False:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Fout",
                    'type': 'danger',
                    'message': 'Login en wachtwoord zijn nodig om te testen'
                },
            }

        wsHandler = ws.WebShipHandler(self.webship_login, self.webship_password, self.webship_url)

        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw =  self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url =  self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        testRes = wsHandler.test()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Status webservice",
                'type': testRes[0],
                'message': testRes[1]
            },
        }

    def ws_check_sku(self):
        print(self.testSku)