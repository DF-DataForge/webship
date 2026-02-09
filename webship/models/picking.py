from odoo.addons.webship.models.ws import WebShipHandler
from odoo import models, fields, api

from datetime import datetime
import pprint
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    df_picking_id_webship = fields.Char("Order id Webship", readOnly=True)
    df_picking_code_webship = fields.Char("Order code Webship", store=True, compute="_fetch_picking_code")

    df_po_id_webship = fields.Char("Purchase order id Webship", readOnly=True)
    df_po_code_webship = fields.Char("Po code webship")

    df_picking_lastsync_webship = fields.Datetime("Last sync on", readOnly=True)

    df_picking_syncresult_webship = fields.Html("Result last sync", readOnly=True)

    df_status_webship = fields.Char('Status in Webship', readOnly=True)

    df_last_changedate_webship = fields.Datetime("Last change in Webship")

    df_url_order = fields.Html('Order id webship', compute="_compute_html_picking")

    df_url_po = fields.Html('Purchase order id webship', compute="_compute_html_po")

    df_url_order_or_po = fields.Html('Order or Purchase order id webship', compute="_compute_html_order_or_po")

    df_show_webship_page = fields.Boolean('Show webship page', compute="_show_webship_page", store=True)

    df_is_webship_source = fields.Boolean('is Webship source location', related='location_id.df_is_webship_location')
    df_is_webship_destination = fields.Boolean('is Webship destination location',
                                          related='location_dest_id.df_is_webship_location')

    df_object_in_webship = fields.Char('Object in Webship', compute="_find_object_webship", store=False)

    df_process_code = fields.Char('Process code', default=lambda self: self._default_process_code())

    df_is_from_woocommerce = fields.Boolean(
        string='From WooCommerce',
        compute='_compute_is_from_woocommerce',
        store=True
    )

    df_ws_lastChangeDate = fields.Char(
        string='Last changedate Webship'
    )

    def recalcComputed(self):
        for picking in self:
            picking._compute_is_from_woocommerce()


    @api.depends('sale_id')
    def _compute_is_from_woocommerce(self):
        for picking in self:
            picking.df_is_from_woocommerce = False  # Default

            sale_order = picking.sale_id
            if not sale_order:
                continue

            # Check if mk_instance_id exists on sale.order and has the expected value
            if hasattr(sale_order, 'mk_instance_id') and sale_order.mk_instance_id:
                instance_name = sale_order.mk_instance_id.name
                if instance_name == "Woo Commerce":
                    picking.df_is_from_woocommerce = True

    def getHandler(self):
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)

        return wsHandler

    @api.model
    def _default_process_code(self):
        if self.df_is_from_woocommerce:
            return False
        # Read the webship_sync_order field from the settings
        webship_sync = self.env['ir.config_parameter'].sudo().get_param('webship.sync_order')
        if webship_sync == 'True':  # note: stored as string 'True' in ir.config_parameter
            return 'P'
        return False

    @api.model
    def create(self, vals):
        picking = super(StockPicking, self).create(vals)

        # Set fields to blank (empty or False) after creation
        picking.write({
            'df_picking_id_webship':False,
            'df_picking_code_webship':'',
            'df_po_id_webship':False,
            'df_po_code_webship':'',
            'df_picking_lastsync_webship':'',
            'df_picking_syncresult_webship':'',
            'df_status_webship':'',
            'df_last_changedate_webship':False
        })

        return picking

    def _schedule_merge_after_create(self):
        """Run merge_picking after the picking and moves are fully created."""
        for picking in self:
            if picking.location_dest_id.df_is_webship_location:
                # Use the Odoo job queue after flush to ensure moves exist
                picking.env.cr.after('commit', lambda: picking._safe_merge_picking())

    def _safe_merge_picking(self):
        """Helper to safely run merge_picking with error handling and logging."""
        try:
            if self.exists() and self.move_ids:
                _logger.info(f"Auto-merging moves for picking {self.name} (WebShip destination)")
                self.merge_picking()
            else:
                _logger.info(f"Skipping merge for {self.name}: no moves found yet.")
        except Exception as e:
            _logger.warning(f"Error while merging picking {self.name}: {e}")

    @api.depends('df_picking_id_webship')
    def _fetch_picking_code(self):
        for record in self:
            print('In record: ' + str(record))
            if record.id != False:
                if record.df_picking_id_webship != False and record.df_picking_id_webship:
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
                record.df_object_in_webship = 'Purchase order'
            elif record.location_id.df_is_webship_location and not record.location_dest_id.df_is_webship_location:
                record.df_object_in_webship = 'Order'
            else:
                record.df_object_in_webship = 'Mutation'

    def _show_webship_page(self):
        b_showWebship = False
        for record in self:
            if record.location_id.df_is_webship_location == True or record.location_dest_id.df_is_webship_location == True:
                b_showWebship = True

        for record in self:
            record.df_show_webship_page = b_showWebship

    # @api.depends("df_picking_id_webship")

    @api.depends("df_picking_id_webship")
    def _compute_html_picking(self):
        for record in self:
            if record.df_picking_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'orders/' + record.df_picking_id_webship
                shownCode = record.df_picking_id_webship

                if record.df_picking_code_webship != False and record.df_picking_code_webship != '':
                    shownCode = record.df_picking_code_webship

                record.df_url_order = shownCode + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            else:
                record.df_url_order = ''

    @api.depends("df_po_id_webship")
    def _compute_html_po(self):
        for record in self:
            if record.df_po_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'purchase-orders/' + record.df_po_id_webship
                record.df_url_po = record.df_po_code_webship + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            else:
                record.df_url_po = ''

    @api.depends("df_picking_id_webship", "df_po_id_webship")
    def _compute_html_order_or_po(self):
        for record in self:
            if record.df_picking_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'orders/' + record.df_picking_id_webship
                shownCode = record.df_picking_id_webship

                if record.df_picking_code_webship != False and record.df_picking_code_webship != '':
                    shownCode = record.df_picking_code_webship

                record.df_url_order_or_po = shownCode + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            elif record.df_po_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'purchase-orders/' + record.df_po_id_webship
                record.df_url_order_or_po = record.df_po_code_webship + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/webship_vk_16px.png"/></a>'
            else:
                record.df_url_order_or_po = ''

    def test(self):
        wsHandler = self.getHandler()

        # sOutput = wsHandler.picking_get_line_items(self)

        if self.df_object_in_webship == 'Order':
            sOutput = wsHandler.build_order_object(self)
        elif self.df_object_in_webship == 'Purchase order':
            sOutput = wsHandler.build_po_object(self)
        else:
            sOutput = {}

        formatted_output = pprint.pformat(sOutput)

        print(formatted_output)

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

    def setCompleted(self):
        for record in self:
            if record.state != 'done':
                record.button_validate()

    def ws_sync_allpickings(self):
        for record in self:
            record.ws_sync_picking()

    def fetch_picking_code(self):
        if self.df_picking_id_webship != False and self.df_picking_id_webship != None:
            wsHandler = self.getHandler()

            pickingCode = wsHandler.get_picking_code(self.df_picking_id_webship)

            if pickingCode != None:
                self.df_picking_code_webship = pickingCode
            else:
                self.df_picking_code_webship = ''
        else:
            self.df_picking_code_webship = ''

    def fetch_po_code(self):
        if self.df_po_id_webship != False and self.df_po_id_webship != None:
            wsHandler = self.getHandler()

            poCode = wsHandler.get_po_code(self.df_po_id_webship)

            if poCode != None:
                self.df_po_code_webship = poCode
            else:
                self.df_po_code_webship = ''
        else:
            self.df_po_code_webship = ''

    def has_all_items_in_stock(self):
        self.ensure_one()
        for move_line in self.move_line_ids:
            available_qty = move_line.product_id.with_context(
                location=move_line.location_id.id
            ).qty_available
            if available_qty < move_line.qty_done or available_qty < move_line.product_uom_qty:
                return False
        return True

    def ws_sync_picking(self):

        if self.df_object_in_webship == False:
            self._find_object_webship()

        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        sResult = wsHandler.sync_picking(self)

        self.df_picking_lastsync_webship = datetime.now()

        if sResult == []:
            self.df_picking_syncresult_webship = 'success'

            if self.df_process_code == 'P':
                self.df_process_code = 'F'

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
            sOutput = '<p>Errors occured:</p>'
            sOutput = sOutput + '<ul>'
            for e in sResult:
                sOutput += '<li>' + e + '</li>'
            sOutput = sOutput + '</ul>'

            self.df_picking_syncresult_webship = sOutput

    def check(self):
        for record in self:
            for m in record.move_ids:
                print(m.read())
            print()
            for ml in record.move_line_ids:
                print(ml.read())

    def fetchQuantities(self):
        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        for record in self:
            if record.df_picking_id_webship != False:
                wsOrder = wsHandler.fetchByKey('orders',record.df_picking_id_webship)
                sEdited = wsOrder.get('data').get('edited')
                if not sEdited:
                    sEdited = wsOrder.get('data').get('created')
                #print(sEdited)
                #print(wsOrder)
                if (
                        (record.df_ws_lastChangeDate == False and sEdited is not None)
                        or (record.df_ws_lastChangeDate != sEdited)
                ):
                    wsHandler.setPickingQuantities(record, wsOrder['data'])
                    record.df_ws_lastChangeDate = sEdited
            if record.df_po_id_webship != False:
                wsOrder = wsHandler.fetchByKey('purchase-orders', record.df_po_id_webship)
                sEdited = wsOrder.get('data').get('edited')
                if not sEdited:
                    sEdited = wsOrder.get('data').get('created')
                if (
                        (record.df_ws_lastChangeDate == False and sEdited is not None)
                        or (record.df_ws_lastChangeDate != sEdited)
                ):
                    wsHandler.setPickingQuantities(record, wsOrder['data'])
                    record.df_ws_lastChangeDate = sEdited

    def findProductsBySku(self):
        wsHandler = self.getHandler()
        for record in self:
            skus = wsHandler.findProductsBySku(record)
            print(skus)

    def make_backorder(self):
        for record in self:
            moves = record.move_ids.filtered(lambda m: m.state not in ('done', 'cancel') and m.quantity != 0)
            backorder_moves = moves._create_backorder()
            backorder_moves += record.move_ids.filtered(lambda m: m.quantity == 0)
            print(backorder_moves)
            if backorder_moves:
                record._create_backorder(backorder_moves=backorder_moves)

    def merge_picking(self):
        b = {}
        for mv in self.move_ids:
            tupel = (mv.product_id.id, mv.product_uom.id, mv.location_id.id, mv.location_dest_id.id)
            b[tupel] = b.get(tupel, 0) + 1

        for prod, q in b.items():
            if q > 1:
                totalUomQty = 0
                totalQuantity = 0
                labelString = None
                for mv in self.move_ids:
                    # mv.description_bom_line = ''
                    # mv.description_picking = ''
                    if mv.product_id.id == prod[0] and mv.product_uom.id == prod[1] and mv.location_id.id == prod[
                        2] and mv.location_dest_id.id == prod[3]:
                        totalQuantity = totalQuantity + mv.quantity
                        totalUomQty = totalUomQty + mv.product_uom_qty

                        #if labelString == None:
                        #    labelString = mv.description_bom_line or ''
                        #else:
                        #    labelString = labelString + ', ' + mv.description_bom_line or ''
                        mv.state = 'draft'
                        mv.unlink()

                #_logger.info('description_bom_line: ' + labelString)

                move = self.env['stock.move'].create({
                    'name': 'Merged product',
                    'picking_id': self.id,
                    'product_id': prod[0],
                    'product_uom': prod[1],
                    'product_uom_qty': totalUomQty,
                    'quantity': totalQuantity,
                    'location_id': prod[2],
                    'location_dest_id': prod[3],
                    'state': self.state
                })