# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import requests
from requests.auth import HTTPBasicAuth

from odoo.http import request
from . import ws
from odoo import fields, models
import json
import logging
_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = ['res.config.settings']

    webship_login = fields.Char(string='Webship username', config_parameter='webship.username')
    webship_password = fields.Char(string='Webship password', config_parameter='webship.password')
    webship_url = fields.Char(string='Webship base URL', config_parameter='webship.base_url')
    webship_app_url = fields.Char(string='Webship base URL', config_parameter='webship.base_app_url')
    webship_last_tested = fields.Char(string='Webship laatst getest', config_parameter='webship.last_tested')
    webship_last_check_date_status = fields.Datetime(string="Order status last check date", config_parameter='webship.last_check_date_status')
    webship_last_check_po_date_status = fields.Datetime(string="Po order status last check date", config_parameter='webship.last_check_po_date_status')

    webship_modus = fields.Selection([('a','Sync nodig'),
                                   ('b','Sync niet nodig')
                                   ],string='Algemene modus', default='a', required=True)

    webship_sync_order = fields.Boolean(string="Sync orders", config_parameter='webship.sync_order')
    webship_sync_producten = fields.Boolean(string="Sync products", config_parameter='webship.sync_products')
    webship_sync_klanten = fields.Boolean(string="Sync clients", config_parameter='webship.sync_klanten')
    webship_sync_leveranciers = fields.Boolean(string="Sync suppliers", config_parameter='webship.sync_leveranciers')
    webship_do_not_match_client_before_create = fields.Boolean(string="Do not match client before create", config_parameter='webship.not_match_client_before_create')
    webship_auto_create_backorder = fields.Boolean(string="Auto create backorder on complete", config_parameter='webship.auto_create_backorder')

    testSku = fields.Char(string="Voor sku in")

    webship_order_available_condition = fields.Boolean('Volle beschikbaarheid nodig', config_parameter='webship.default_order_available_condition')
    webship_default_status = fields.Selection(selection=[('concept', 'Concept'),('ready-to-pick', 'Ready to pick'),('on-hold', 'On hold')], string='Standaard status Webship order', required=True, default='ready-to-pick', config_parameter="webship.default_status_order")
    webship_default_po_status = fields.Selection(selection=[('concept', 'Concept'),('ordered', 'Ordered')], string='Standaard status Webship po order', requierd=True, default='ordered', config_parameter="webship.default_status_po_order")
    webship_default_brand = fields.Many2one(comodel_name='webship.brand', string='Default Webship brand', config_parameter='webship.default_brand')
    webship_default_shop = fields.Many2one(comodel_name='webship.shop', string='Default Webship shop', config_parameter='webship.default_shop')

    def syncAll(self):
        print('hi')

    def ws_exp_sup_cl(self):
        return {'type': 'ir.actions.act_url', 'url': '/web/download/excel?p=partner', 'target': 'self'}

    def ws_fetch_companies_and_warehouses(self):
        wsHandler = self.getHandler()
        sData = wsHandler.fetchCompanies()

        if sData['status'] == 'success':
            for p in sData['data'].values():
                for b in p['brands']:

                    sResult = self.env['webship.brand'].search([('brand_id','=',b['_id'])])

                    if not sResult:
                        self.env['webship.brand'].create({'brand_id':b['_id'], 'name':b['name']})
                        sResult = self.env['webship.brand'].search([('brand_id', '=', b['_id'])])

                    for s in b['shops']:
                        sRes = self.env['webship.shop'].search([('shop_id','=',s['_id'])])
                        if not sRes:
                            self.env['webship.shop'].create({'shop_id': s['_id'], 'name': s['name'], 'brand_id': sRes.id})


        sData = wsHandler.fetchWarehouses()

        if sData['status'] == 'success':
            for p in sData['data'].values():
                for w in p:
                    sResult = self.env['webship.warehouse'].search([('warehouse_id','=',w['_id'])])

                    if not sResult:
                        self.env['webship.warehouse'].create({'warehouse_id':w['_id'], 'name':w['name']})

    def ws_match_clients_email(self):
        wsHandler = self.getHandler()

        sData = wsHandler.fetchClients()

        allClients = []
        if sData['status'] == 'success':
            for c in sData['data'].values():
                for client in c:
                    if 'email' in client.keys():
                        allClients.append([client['_id'], client['email']])

        print(allClients)

        email_counts = {}
        for _, email in allClients:
            if email not in email_counts:
                email_counts[email] = 1
            else:
                email_counts[email] += 1

        unique_email_items = []
        for item in allClients:
            email = item[1]
            if email_counts[email] == 1:
                unique_email_items.append(item)

        for item in unique_email_items:
            resP = self.env['res.partner'].search([('email','=',item[1])])

            if len(resP) == 1:
                #print('Unique match')
                resP.write({'df_client_id_webship':item[0]})

    def ws_match_suppliers_email(self):
        wsHandler = self.getHandler()

        sData = wsHandler.fetchSuppliers()

        print(sData)

        allSuppliers = []
        if sData['status'] == 'success':
            for c in sData['data'].values():
                for sup in c:
                    if 'email' in sup.keys():
                        allSuppliers.append([sup['_id'], sup['email']])

        print(allSuppliers)

        email_counts = {}
        for _, email in allSuppliers:
            if email not in email_counts:
                email_counts[email] = 1
            else:
                email_counts[email] += 1

        unique_email_items = []
        for item in allSuppliers:
            email = item[1]
            if email_counts[email] == 1:
                unique_email_items.append(item)

        for item in unique_email_items:
            resP = self.env['res.partner'].search([('email','=',item[1])])

            if len(resP) == 1:
                #print('Unique match')
                resP.write({'df_supplier_id_webship':item[0]})

    def ws_match_products_sku(self):
        wsHandler = self.getHandler()

        sData = wsHandler.fetchProducts()

        if sData['status'] == 'success':
            for p in sData['data'].values():
                for prod in p:

                    resP = self.env['product.product'].search([('default_code', '=', prod['sku'])])

                    if len(resP) == 1:
                        # print('Unique match')
                        resP.write({'df_product_id_webship': prod['_id']})


    def getHandler(self):
        wsHandler = ws.WebShipHandler(self.webship_login, self.webship_password, self.webship_url)
        return wsHandler

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

    def ws_sync_statusses_since_last(self):

        pickings = self.env['stock.picking'].search([
            ('state', 'in', ['confirmed', 'assigned']),
            '|',
            ('df_is_webship_source', '=', True),
            ('df_is_webship_destination', '=', True),
        ])

        for p in pickings:
            try:
                p.fetchQuantities()
            except Exception:
                _logger.exception("Error while fetching quantities for pickings: %s", pickings.ids)

        lastDate = fields.Datetime.to_string(fields.Datetime.now())

        self.env['ir.config_parameter'].sudo().set_param('webship.last_check_date_status', lastDate)
        self.env['ir.config_parameter'].sudo().set_param('webship.last_check_po_date_status', lastDate)

    def ws_sync_all_pickings_statusP(self):
        for p in self.env['stock.picking'].search([('df_process_code','=','P')]):
            if p.location_id.df_is_webship_location == True or p.location_dest_id.df_is_webship_location:
                p.ws_sync_picking()
            else:
                p.write({'df_process_code','=','E'})

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

    def ws_import_stock(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = ws.WebShipHandler(login, pw, base_url)
        wsHandler.set_env(self.env)

        wsHandler.importStock()


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

    def download_xlsx_report(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/custom/xlsx/download_xlsx_config_report',
            'target': 'self',
        }

    def download_ws_prod_vergelijk(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/custom/xlsx/download_ws_prod_vergelijk',
            'target': 'self',
        }