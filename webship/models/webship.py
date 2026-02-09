from odoo import models, fields, api

from datetime import datetime
import pprint

from odoo.addons.webship.models.ws import WebShipHandler

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
                    
class Warehouses(models.Model):
    _inherit = 'stock.warehouse'

    df_warehouse_id_webship = fields.Char("Warehouse id webship", readOnly=True)

class ProductCategory(models.Model):
    _inherit = 'product.category'

    df_cat_shop_id_webship = fields.Char("Shop id webship", readOnly=True)

class ProductPackaging(models.Model):
    _inherit = 'product.packaging'

    df_sku_webship = fields.Char("SKU webship")

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    df_shop_id_webship = fields.Char("Warehouse id webship")
