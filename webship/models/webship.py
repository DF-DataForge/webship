from odoo.addons.webship.models.ws import WebShipHandler
from odoo import models, fields, api

from datetime import datetime
import pprint

class WebshipProperty(models.Model):
    _name = "webship.property"
    _description = "Webship properties"
    _order = "id desc"

    # Basic
    name = fields.Char("Property name", required=True)
    description = fields.Text("Description")

class WebshipEvents(models.Model):
    _name = "webship.events"
    _description = "Webship events"
    _order = "id desc"

    model = fields.Many2one('ir.model', 'Webshipevent_model')

    model_translated = fields.Char('Object', compute="_compute_model_translated", store="True")

    status  = fields.Selection(
        selection=[
            ("P", "Pending"),
            ("E", "Error"),
            ("F", "Finished"),
            ("D", "Duplicate")
        ]
    )
    modelTableKey = fields.Integer()
    processTime = fields.Datetime()

    dbAction = fields.Selection(
        selection = [
            ("I", "Insert"),
            ("U", "Update"),
            ("D", "Delete"),
            ("IU", "InsertOrUpdate")
        ]
    )

    @api.depends("model")
    def _compute_model_translated(self):
        for r in self:
            if self.model.model == 'stock.picking':
                r.model_translated = 'Picking'

    def runSync(self):
        print('hi')

    product_id_webship = fields.Char()

    def webshipHandler(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')
        return WebShipHandler(login, pw, base_url)

    def performSync(self):
        self.syncPicking()

    def syncPicking(self):
        modl = self.env['ir.model'].search([('model', '=', 'stock.picking')])

        welines = self.env['webship.events'].search([('model', '=', modl.id),('status','=','P')], order='id asc')

        ws = self.webshipHandler()

        for w in welines:
            if w.dbAction == 'D':
                print('Deleting')
                w.status = 'F'
            elif w.dbAction == 'U':
                pickingObj = self.env['stock.picking'].search([('id','=',w.modelTableKey)])
                pickingObj.ws_sync_picking()

                if pickingObj.df_picking_syncresult_webship == 'Success':
                    w.status = 'F'
                else:
                    w.status = 'E'

class Product(models.Model):
    _inherit = 'product.template'

    #df_product_id_webship = fields.Char("Product id webship", readOnly=True)

    #brands = fields.Many2many('res.partner', 'Product_brands')

class Productvar(models.Model):
    _inherit = 'product.product'

    stockType = fields.Selection(
        selection=[
            ("fifo", "First in first out"),
            ("lifo", "Last in first out"),
            ("fefo", "First expired first out")
        ],
        string="Stock type"
    )

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

    #def create(self, values):
    #    modl = self.env['ir.model'].search([('model', '=', 'product.product')])
    #
    #    self.env['webship.events'].create(
    #       {'modelTableKey': self.id, 'model': modl.id, 'status': 'P', 'processTime': datetime.now(), 'dbAction': 'I'})

    #    result = super(Productvar, self).create(values)

    #    return result


class Partner(models.Model):
    _inherit = 'res.partner'

    df_supplier_id_webship = fields.Char("Supplier id webship", readOnly=True)
    df_is_supplier_in_webship = fields.Boolean("Supplier in Webship", default=False)
    df_client_id_webship = fields.Char("Client id webship", readOnly=True)
    df_is_client_in_webship = fields.Boolean("Client in Webship", default=True)
    df_last_webship_sync = fields.Datetime("Laatste wijziging gepusht naar webship op")
    df_partner_syncresult_webship = fields.Html("Resultaat laatste sync")

    wsUrlClient = fields.Html("Client id Webship", compute="_compute_html_client")

    @api.depends("df_client_id_webship")
    def _compute_html_client(self):
        for record in self:
            if record.df_client_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param('webship.base_app_url') + 'clients/' + record.df_client_id_webship
                record.wsUrlClient = record.df_client_id_webship +' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            else:
                record.wsUrlClient = ''

    def ws_sync_partner(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)

        sResult = wsHandler.sync_partner(self)

        if sResult == []:
            self.df_partner_syncresult_webship = 'Success'
        else:
            sOutput = '<p>Errors occured:</p>';
            sOutput = sOutput + '<ul>'
            for e in sResult:
                sOutput += '<li>' + e + '</li>'
            sOutput = sOutput + '</ul>'

            self.df_partner_syncresult_webship = sOutput

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    df_order_id_webship = fields.Char("Order id webship", readOnly=True)

    def write(self, values):
        if False:
            modl = self.env['ir.model'].search([('model','=','sale.order')])

            self.env['webship.events'].create({'modelTableKey':self.id, 'model':modl.id, 'status':'P', 'processTime':datetime.now(), 'dbAction':'U', 'product_id_webship':self.df_order_id_webship})

        result = super(SaleOrder, self).write(values)
        return result

class Warehouses(models.Model):
    _inherit = 'stock.warehouse'

    df_warehouse_id_webship = fields.Char("Warehouse id webship", readOnly=True)

class StockLocations(models.Model):
    _inherit = 'stock.location'

    df_warehouse_id_webship = fields.Char("Warehouse id webship", readOnly=True)

    df_shop_id_webship = fields.Char("Shop id webship", readOnly=True)

    df_is_webship_location = fields.Boolean("Is Webship locatie?", default=False)

class ProductCategory(models.Model):
    _inherit = 'product.category'

    df_cat_shop_id_webship = fields.Char("Shop id webship", readOnly=True)

class ProductPackaging(models.Model):
    _inherit = 'product.packaging'

    df_sku_webship = fields.Char("SKU webship")

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    df_shop_id_webship = fields.Char("Warehouse id webship")

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    df_picking_id_webship = fields.Char("Order id Webship", readOnly=True)
    df_picking_code_webship = fields.Char("Order code Webship")

    df_po_id_webship = fields.Char("Purchase order id Webship", readOnly=True)
    df_po_code_webship = fields.Char("Po code webship")

    df_picking_lastsync_webship = fields.Datetime("Last sync on", readOnly=True)

    df_picking_syncresult_webship = fields.Html("Result last sync", readOnly=True)

    df_status_webship = fields.Char('Status in Webship', readOnly=True)

    df_last_changedate_webship = fields.Datetime("Last change in Webship")

    wsUrlOrder = fields.Html('Order id webship', compute="_compute_html_picking")

    wsUrlPo = fields.Html('Order id webship', compute="_compute_html_po")

    showWebship = fields.Boolean('Show webship page', compute="_show_webship_page", store=True)

    isWebshipSource = fields.Boolean('is Webship source location', related='location_id.df_is_webship_location')
    isWebshipDestination = fields.Boolean('is Webship destination location', related='location_dest_id.df_is_webship_location')

    objectInWebship = fields.Char('Object in Webship')

    #isWebshipOrder = fields.Boolean('is Webship order', compute="_is_webship_order")

    #def _is_webship_order(self):
    #    for record in self:
    #        if  self.isWebshipSource == True or self.isWebshipDestination == True:
    #            record.isWebshipOrder = True

    @api.depends('df_picking_id_webship')
    def _fetch_picking_code(self):
        for record in self:
            print('In record: ' + str(record))
            if self.id != False:
                if self.df_picking_id_webship != False and self.df_picking_id_webship:
                    codeWs = record.fetch_picking_code()
                    if codeWs != None:
                        record.df_picking_code_webship = codeWs
                    else:
                        record.df_picking_code_webship = ''
                else:
                    record.df_picking_code_webship = ''

    @api.depends('location_id', 'location_dest_id')
    def _find_object_webship(self):
        for record in self:
            if record.location_dest_id.df_is_webship_location and not record.location_id.df_is_webship_location:
                record.objectInWebship = 'Purchase order'
            elif record.location_id.df_is_webship_location and not record.location_dest_id.df_is_webship_location:
                record.objectInWebship = 'Order'
            else:
                record.objectInWebship = 'Mutation'

    def _show_webship_page(self):
        b_showWebship = False
        for record in self:
            if record.location_id.df_is_webship_location == True or record.location_dest_id.df_is_webship_location == True:
                b_showWebship = True

        for record in self:
            record.showWebship = b_showWebship

    #@api.depends("df_picking_id_webship")

    @api.depends("df_picking_id_webship")
    def _compute_html_picking(self):
        for record in self:
            if record.df_picking_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'orders/' + record.df_picking_id_webship
                shownCode = record.df_picking_id_webship

                if record.df_picking_code_webship != False and record.df_picking_code_webship != '':
                    shownCode = record.df_picking_code_webship

                record.wsUrlOrder = shownCode + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            else:
                record.wsUrlOrder = ''

    @api.depends("df_po_id_webship")
    def _compute_html_po(self):
        for record in self:
            if record.df_po_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'purchase-orders/' + record.df_po_id_webship
                record.wsUrlPo = record.df_po_id_webship + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            else:
                record.wsUrlPo = ''


    def write(self, values):

        print(values)

        sync_orders = self.env['ir.config_parameter'].sudo().get_param('webship.sync_order')

        if sync_orders == 'True' and not ((len(values) == 1 and 'df_picking_syncresult_webship' in values.keys()) or (len(values) == 1 and 'df_picking_lastsync_webship' in values.keys()) or len(values)==0):

            #print('in function')

            modl = self.env['ir.model'].search([('model','=','stock.picking')])

            #print('write')

            if self.location_id.df_is_webship_location or self.location_dest_id.df_is_webship_location:
                #print('Write now')
                self.env['webship.events'].create({'modelTableKey':self.id, 'model':modl.id, 'status':'P', 'processTime':datetime.now(), 'dbAction':'U'})

            result = super(StockPicking, self).write(values)
            return result
        else:
            return super(StockPicking, self).write(values)

    def unlink(self):
        sync_orders = self.env['ir.config_parameter'].sudo().get_param('webship.sync_order')

        if sync_orders == 'True':
            modl = self.env['ir.model'].search([('model', '=', 'stock.picking')])

            if self.location_id.df_is_webship_location or self.location_dest_id.df_is_webship_location:
                self.env['webship.events'].create(
                {'modelTableKey': self.id, 'model': modl.id, 'status': 'P', 'processTime': datetime.now(),
                 'dbAction': 'D'})

            return super(StockPicking, self).unlink()
        else:
            return super(StockPicking, self).unlink()

    def test(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)

        #sOutput = wsHandler.picking_get_line_items(self)

        if self.objectInWebship == 'Order':
            sOutput = wsHandler.build_order_object(self)
        elif self.objectInWebship == 'Purchase order':
            sOutput = wsHandler.build_po_object(self)
        else:
            sOutput = {}

        formatted_output = pprint.pformat(sOutput)

        print (formatted_output)

        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Info',
                'type': 'warning',
                'message': str(formatted_output),
                'sticky': True,
            }
        }
        return notification
    
    def ws_sync_allpickings(self):
        for record in self:
            record.ws_sync_picking()

    def fetch_picking_code(self):
        if self.df_picking_id_webship != False and self.df_picking_id_webship != None:
            login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
            pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
            base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

            wsHandler = WebShipHandler(login, pw, base_url)

            pickingCode = wsHandler.get_picking_code(self.df_picking_id_webship)

            if pickingCode != None:
                self.df_picking_code_webship = pickingCode
            else:
                self.df_picking_code_webship = ''
        else:
            self.df_picking_code_webship = ''

    def fetch_po_code(self):
        if self.df_po_id_webship != False and self.df_po_id_webship != None:
            login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
            pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
            base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

            wsHandler = WebShipHandler(login, pw, base_url)

            poCode = wsHandler.get_po_code(self.df_po_id_webship)

            if poCode != None:
                self.df_po_code_webship = poCode
            else:
                self.df_po_code_webship = ''
        else:
            self.df_po_code_webship =''

    def ws_sync_picking(self):

        if self.objectInWebship == False:
            self._find_object_webship()

        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)

        sResult = wsHandler.sync_picking(self)

        self.df_picking_lastsync_webship = datetime.now()

        if sResult == []:
            self.df_picking_syncresult_webship = 'Success'

            if self.df_picking_id_webship != False and self.df_picking_id_webship != '':
                pickingCode = wsHandler.get_picking_code(self.df_picking_id_webship)

                if pickingCode != None:
                    self.df_picking_code_webship = pickingCode
                else:
                    self.df_picking_code_webship = ''
            else:
                self.df_picking_code_webship = ''

            if self.df_po_id_webship != False and self.df_po_id_webship != None:
                poCode = wsHandler.get_po_code(self.df_po_id_webship)

                if poCode != None:
                    self.df_po_code_webship = poCode
                else:
                    self.df_po_code_webship = ''
            else:
                self.df_po_code_webship = ''

        else:
            sOutput = '<p>Errors occured:</p>';
            sOutput = sOutput + '<ul>'
            for e in sResult:
                sOutput += '<li>' + e + '</li>'
            sOutput = sOutput + '</ul>'
            
            self.df_picking_syncresult_webship = sOutput

