# Stoqflow Retour processing.
# Fetches purchase orders from the Stoqflow API and creates retour records
# for those with "Retour" in the supplier_reference field.
# Automatically creates return pickings in Odoo for matched sale orders.
import json
import re
import logging
from datetime import datetime

from odoo import models, fields, api
from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)


class WebshipRetourAndBackorder(models.Model):
    _name = 'webship.retour.and.backorder'
    _description = 'Stoqflow Retour and Backorder'
    _order = 'created desc'

    _sql_constraints = [
        ('stoqflow_id_unique', 'UNIQUE(df_stoqflow_id)', 'Stoqflow ID must be unique!'),
    ]

    df_stoqflow_id = fields.Char('Stoqflow ID', index=True)
    name = fields.Char('Order Number')
    status = fields.Selection([
        ('concept', 'Concept'),
        ('ordered', 'Ordered'),
        ('in-transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('unpacking', 'Unpacking'),
        ('on-hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status')
    order_or_po = fields.Selection([
        ('order', 'Order'),
        ('purchase_order', 'Purchase order'),
    ], string='Object in Stoqflow')
    company_id = fields.Char('Stoqflow Company ID')
    supplier_id = fields.Many2one('res.partner', string='Supplier')
    df_stoqflow_supplier_id = fields.Char('Stoqflow Supplier ID')
    df_stoqflow_supplier_code = fields.Char('Stoqflow Supplier Code')
    ws_supplier_link = fields.Html(
        'Supplier', compute='_compute_supplier_link',
    )
    supplier_reference = fields.Char('Supplier Reference')
    tracking_numbers = fields.Char('Tracking Numbers')
    warehouse_id = fields.Many2one('webship.warehouse', string='Warehouse')
    df_stoqflow_warehouse_id = fields.Char('Stoqflow Warehouse ID')
    notes = fields.Text('Notes')
    created = fields.Datetime('Created in Stoqflow')
    df_original_order_ref = fields.Char(
        'Original Order Ref', compute='_compute_original_order_ref', store=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order', string='Original Sale Order',
        compute='_compute_sale_order', store=True,
    )
    picking_id = fields.Many2one('stock.picking', string='Original Picking', readonly=True)
    original_picking_sale_order_id = fields.Many2one(
        'sale.order', string='Original Sale Order',
        related='picking_id.sale_id', readonly=True,
    )
    df_stoqflow_original_order_id = fields.Char('Original Order ID (Stoqflow)', readonly=True)
    ws_original_order_link = fields.Html(
        'Original Order in Stoqflow', compute='_compute_original_order_link',
    )
    return_picking_id = fields.Many2one('stock.picking', string='Return Picking')
    df_process_code = fields.Selection([
        ('P', 'Pending'),
        ('F', 'Return Picking Created'),
        ('E', 'Error'),
    ], string='Process Code', readonly=True)
    df_error_message = fields.Text(
        'Error Message', readonly=True,
        help="Set when df_process_code is 'E'. Explains why the return picking "
             "could not be created automatically.",
    )
    parent_order_id = fields.Char('Parent Order ID (Stoqflow)')
    line_ids = fields.One2many(
        'webship.retour.and.backorder.line', 'retour_id', string='Return Lines',
    )
    df_stoqflow_url = fields.Char('Stoqflow URL', compute='_compute_stoqflow_url')
    ws_stoqflow_link = fields.Html('Order link Stoqflow', compute='_compute_stoqflow_link')
    ws_order_json = fields.Text('Order JSON', readonly=True)

    @api.depends('supplier_reference')
    def _compute_original_order_ref(self):
        for rec in self:
            ref = ''
            if rec.supplier_reference:
                match = re.search(r'Retour\s+(S[O]?\d+)', rec.supplier_reference)
                if match:
                    ref = match.group(1)
            rec.df_original_order_ref = ref

    @api.depends('df_original_order_ref', 'picking_id')
    def _compute_sale_order(self):
        for rec in self:
            order = False
            if rec.df_original_order_ref:
                # Exact match only, and only accept a unique result. An 'ilike'
                # substring with limit=1 could match SO120/SO123/... for a ref
                # of "SO12" and pick an arbitrary (first-by-id) wrong order.
                # On 0 or multiple matches, fall through to picking_id.sale_id
                # rather than guessing between sale orders.
                orders = self.env['sale.order'].search(
                    [('name', '=', rec.df_original_order_ref)],
                )
                if len(orders) == 1:
                    order = orders
            if not order and rec.picking_id:
                order = rec.picking_id.sale_id
            rec.sale_order_id = order

    @api.depends('df_stoqflow_supplier_id', 'df_stoqflow_supplier_code')
    def _compute_supplier_link(self):
        base_app_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_app_url', '')
        for rec in self:
            if rec.df_stoqflow_supplier_code and rec.df_stoqflow_supplier_id and base_app_url:
                label = rec.df_stoqflow_supplier_code
                url = base_app_url + 'suppliers/' + rec.df_stoqflow_supplier_id
                rec.ws_supplier_link = (
                    '%s <a href="%s" target="_blank">'
                    '<img style="height:16px; width:16px" '
                    'src="/webship/static/src/img/stoqflow_16px.png"/></a>'
                ) % (label, url)
            else:
                rec.ws_supplier_link = ''

    def _compute_stoqflow_url(self):
        base_app_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_app_url', '')
        for rec in self:
            if rec.df_stoqflow_id and base_app_url:
                rec.df_stoqflow_url = base_app_url + 'purchase-orders/' + rec.df_stoqflow_id
            else:
                rec.df_stoqflow_url = False

    @api.depends('name', 'df_stoqflow_id')
    def _compute_stoqflow_link(self):
        base_app_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_app_url', '')
        for rec in self:
            if rec.df_stoqflow_id and base_app_url:
                label = rec.name or rec.df_stoqflow_id
                url = base_app_url + 'purchase-orders/' + rec.df_stoqflow_id
                rec.ws_stoqflow_link = (
                    '%s <a href="%s" target="_blank">'
                    '<img style="height:16px; width:16px" '
                    'src="/webship/static/src/img/stoqflow_16px.png"/></a>'
                ) % (label, url)
            else:
                rec.ws_stoqflow_link = rec.name or ''

    @api.depends('df_original_order_ref', 'df_stoqflow_original_order_id')
    def _compute_original_order_link(self):
        base_app_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_app_url', '')
        for rec in self:
            if rec.df_stoqflow_original_order_id and base_app_url:
                label = rec.df_original_order_ref or rec.df_stoqflow_original_order_id
                url = base_app_url + 'orders/' + rec.df_stoqflow_original_order_id
                rec.ws_original_order_link = (
                    '%s <a href="%s" target="_blank">'
                    '<img style="height:16px; width:16px" '
                    'src="/webship/static/src/img/stoqflow_16px.png"/></a>'
                ) % (label, url)
            elif rec.df_original_order_ref:
                rec.ws_original_order_link = rec.df_original_order_ref
            else:
                rec.ws_original_order_link = ''

    # ------------------------------------------------------------------
    # Sync logic
    # ------------------------------------------------------------------

    def _get_handler(self):
        """Create a WebShipHandler from stored configuration parameters."""
        icp = self.env['ir.config_parameter'].sudo()
        login = icp.get_param('webship.username')
        pw = icp.get_param('webship.password')
        base_url = icp.get_param('webship.base_url')
        handler = WebShipHandler(login, pw, base_url)
        handler.set_env(self.env)
        return handler

    def action_create_return_picking(self):
        """Manual button to create a return picking for this retour.
        Only allows creation for delivered retours; shows a warning otherwise."""
        self.ensure_one()
        if self.return_picking_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Return Picking',
                    'message': 'A return picking already exists: %s' % self.return_picking_id.name,
                    'type': 'warning',
                    'sticky': False,
                },
            }
        if self.status != 'delivered':
            return {
                'type': 'ir.actions.act_window',
                'name': 'Return not yet delivered',
                'res_model': 'webship.retour.confirm.return',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_retour_id': self.id,
                    'default_warning_message':
                        'This return is not yet delivered in Stoqflow (status: %s).\n\n'
                        'Do you wish to create a return picking in Odoo anyway?' % (self.status or 'unknown'),
                },
            }
        self.write({'df_process_code': 'P', 'df_error_message': False})
        self._create_return_picking(self)
        if self.return_picking_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Return Picking',
                    'message': 'Return picking %s created successfully.' % self.return_picking_id.name,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Return Picking',
                'message': 'Could not create return picking. Check that a matching sale order and done outgoing picking exist.',
                'type': 'warning',
                'sticky': False,
            },
        }

    def action_sync_retours(self):
        """Manual sync button action."""
        handler = self._get_handler()
        count = self._sync_retours_from_api(handler)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Stoqflow Retours',
                'message': 'Sync completed. %d retour(s) synced.' % count,
                'type': 'success',
                'sticky': False,
            },
        }

    def _sync_retours_from_api(self, wsHandler):
        """Fetch purchase orders from Stoqflow and process retours."""
        return self._process_purchase_orders(wsHandler)

    def _process_purchase_orders(self, wsHandler):
        """Fetch all purchase orders and create retour records for those with 'Retour' in supplier_reference."""
        result = wsHandler.fetchAll('purchase-orders', 'high')
        if result.get('status') != 'success':
            _logger.error('Failed to fetch purchase orders: %s', result.get('txt', ''))
            return 0

        total_pos = sum(len(page) for page in result['data'].values())
        _logger.info('Fetched %d purchase orders from Stoqflow (%d pages)',
                     total_pos, len(result['data']))

        count = 0
        for page in result['data'].values():
            for po in page:
                try:
                    supplier_ref = po.get('supplier_reference', '') or ''
                    is_retour = 'Retour' in supplier_ref

                    if is_retour:
                        self._sync_retour_record(po, wsHandler, 'purchase_order')
                        count += 1
                except Exception as e:
                    _logger.exception(
                        'Error processing PO %s: %s', po.get('_id', '?'), e,
                    )
        return count

    def _sync_retour_record(self, po, wsHandler, order_or_po):
        """Create or update a retour record from a Stoqflow purchase order."""
        existing = self.search([('df_stoqflow_id', '=', po['_id'])], limit=1)

        # Parse created datetime
        created_dt = False
        if po.get('created'):
            try:
                created_dt = datetime.strptime(po['created'], "%Y-%m-%dT%H:%M:%S.%fZ")
            except (ValueError, TypeError):
                _logger.warning('Could not parse created date: %s', po.get('created'))

        # Resolve supplier
        supplier = False
        supplier_code = ''
        if po.get('supplier_id'):
            supplier = self.env['res.partner'].search(
                [('df_supplier_id_webship', '=', po['supplier_id'])], limit=1,
            )
            try:
                result = wsHandler.performGet('suppliers', '/' + po['supplier_id'])
                if result.get('status') == 'success':
                    data = result.get('data', {})
                    if isinstance(data, list) and data:
                        data = data[0]
                    if isinstance(data, dict):
                        supplier_code = data.get('supplier_number', '') or ''
            except Exception as e:
                _logger.warning('Error fetching supplier %s: %s', po['supplier_id'], e)
                supplier_code = ''

        # Resolve warehouse
        warehouse = False
        if po.get('warehouse_id'):
            warehouse = self.env['webship.warehouse'].search(
                [('warehouse_id', '=', po['warehouse_id'])], limit=1,
            )

        # Store the raw JSON payload
        try:
            order_json = json.dumps(po, indent=2, default=str)
        except Exception:
            order_json = str(po)

        vals = {
            'df_stoqflow_id': po['_id'],
            'name': po.get('order_number', ''),
            'status': po.get('status', 'concept'),
            'order_or_po': order_or_po,
            'company_id': po.get('company_id', ''),
            'df_stoqflow_supplier_id': po.get('supplier_id', ''),
            'df_stoqflow_supplier_code': supplier_code,
            'supplier_id': supplier.id if supplier else False,
            'supplier_reference': po.get('supplier_reference', ''),
            'tracking_numbers': po.get('tracking_numbers', ''),
            'df_stoqflow_warehouse_id': po.get('warehouse_id', ''),
            'warehouse_id': warehouse.id if warehouse else False,
            'notes': po.get('notes', ''),
            'created': created_dt,
            'parent_order_id': po.get('parent_order_id', ''),
            'ws_order_json': order_json,
        }

        if existing:
            existing.write(vals)
            retour = existing
        else:
            retour = self.create(vals)

        # Process order items (lines)
        self._sync_retour_lines(retour, po.get('order_items', []))

        # Resolve original Stoqflow order and picking via order_number lookup
        if retour.df_original_order_ref:
            self._resolve_original_picking(retour, wsHandler)

        # Set process code for new retours without a return picking
        if not retour.return_picking_id and not retour.df_process_code:
            retour.df_process_code = 'P'

        # Create return picking if pending
        if retour.df_process_code == 'P':
            self._create_return_picking(retour)

    def _sync_retour_lines(self, retour, order_items):
        """Create or update retour lines from Stoqflow order_items."""
        existing_lines = {l.df_stoqflow_id: l for l in retour.line_ids if l.df_stoqflow_id}

        for item in order_items:
            item_id = item.get('_id', '')
            product = False
            if item.get('product_id'):
                product = self.env['product.product'].search(
                    [('df_product_id_webship', '=', item['product_id'])], limit=1,
                )
                if not product:
                    _logger.warning(
                        'Product not found in Odoo for Stoqflow product_id %s',
                        item['product_id'],
                    )

            line_vals = {
                'df_stoqflow_id': item_id,
                'df_stoqflow_product_id': item.get('product_id', ''),
                'product_id': product.id if product else False,
                'quantity': item.get('quantity', 0),
            }

            if item_id in existing_lines:
                existing_lines[item_id].write(line_vals)
            else:
                line_vals['retour_id'] = retour.id
                self.env['webship.retour.and.backorder.line'].create(line_vals)

    def _resolve_original_picking(self, retour, wsHandler):
        """Look up the original order in Stoqflow by order_number, then find the Odoo picking."""
        order_ref = retour.df_original_order_ref
        result = wsHandler.performGet('orders', '?order_number=' + order_ref)
        if result.get('status') != 'success' or not result.get('data'):
            _logger.info('No Stoqflow order found for order_number=%s', order_ref)
            return

        orders = result['data']
        if not isinstance(orders, list) or not orders:
            return

        # Find exact match by order_number
        stoqflow_order = None
        for order in orders:
            if order.get('order_number') == order_ref:
                stoqflow_order = order
                break
        if not stoqflow_order:
            _logger.warning(
                'No exact order_number match for %s in %d results, using first. order_numbers: %s',
                order_ref, len(orders), [o.get('order_number') for o in orders],
            )
            stoqflow_order = orders[0]

        stoqflow_order_id = stoqflow_order.get('_id', '')
        _logger.info(
            'Resolved Stoqflow order for %s: _id=%s, order_number=%s',
            order_ref, stoqflow_order_id, stoqflow_order.get('order_number'),
        )

        retour.df_stoqflow_original_order_id = stoqflow_order_id

        if stoqflow_order_id:
            picking = self.env['stock.picking'].search(
                [('df_picking_id_webship', '=', stoqflow_order_id)], limit=1,
            )
            if picking:
                retour.picking_id = picking.id
                _logger.info(
                    'Resolved original picking %s for retour %s via Stoqflow order %s',
                    picking.name, retour.name, stoqflow_order_id,
                )

    def _create_return_picking(self, retour):
        """Create a return picking in Odoo for a retour, linked to the original outbound picking."""
        # Lock the retour row and re-read to prevent duplicate return pickings
        self.env.cr.execute(
            "SELECT return_picking_id FROM webship_retour_and_backorder WHERE id = %s FOR UPDATE",
            (retour.id,),
        )
        row = self.env.cr.fetchone()
        if row and row[0]:
            _logger.info('Return picking already exists for retour %s, skipping', retour.name)
            retour.invalidate_recordset(['return_picking_id'])
            return

        if not retour.sale_order_id:
            msg = (
                "No matching sale order found in Odoo for reference '%s'. "
                "Either the sale order does not exist in this database or its "
                "name does not contain '%s'."
                % (retour.df_original_order_ref or retour.supplier_reference or '',
                   retour.df_original_order_ref or '')
            )
            _logger.warning(
                'Cannot create return picking for retour %s: %s', retour.name, msg,
            )
            retour.write({'df_process_code': 'E', 'df_error_message': msg})
            return

        # Find the original done outbound picking
        picking = retour.sale_order_id.picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'outgoing' and p.state == 'done'
        )
        if not picking:
            msg = (
                "Sale order %s has no completed (done) outgoing picking. "
                "The original delivery must be validated in Odoo before a "
                "return picking can be created."
                % retour.sale_order_id.name
            )
            _logger.warning(
                'Cannot create return picking for retour %s: %s', retour.name, msg,
            )
            retour.write({'df_process_code': 'E', 'df_error_message': msg})
            return

        # Use the first (most recent) done picking
        picking = picking[0]
        _logger.info(
            'Creating return picking for retour %s from picking %s (sale order %s)',
            retour.name, picking.name, retour.sale_order_id.name,
        )

        # Build product return moves from retour lines
        product_return_moves = [(5,)]
        line_fields = [f for f in self.env['stock.return.picking.line']._fields.keys()]
        product_return_moves_data_tmpl = self.env['stock.return.picking.line'].default_get(line_fields)

        # Map retour line products to quantities
        product_qty_map = {}
        for line in retour.line_ids:
            if line.product_id:
                product_qty_map[line.product_id.id] = (
                    product_qty_map.get(line.product_id.id, 0) + line.quantity
                )

        _logger.info(
            'Retour %s: %d products to return, picking has %d moves',
            retour.name, len(product_qty_map), len(picking.move_ids),
        )

        matched_moves = 0
        for move in picking.move_ids:
            if move.product_id.id not in product_qty_map:
                continue
            if move.state == 'cancel' or move.scrapped:
                _logger.info('Skipping move %s: state=%s, scrapped=%s', move.id, move.state, move.scrapped)
                continue

            product_return_moves_data = dict(product_return_moves_data_tmpl)
            return_line_vals = self.env['stock.return.picking']._prepare_stock_return_picking_line_vals_from_move(move)
            return_line_vals.update({'quantity': product_qty_map[move.product_id.id]})
            product_return_moves_data.update(return_line_vals)
            product_return_moves.append((0, 0, product_return_moves_data))
            matched_moves += 1
            _logger.info(
                'Matched move for product %s (qty: %s)',
                move.product_id.display_name, product_qty_map[move.product_id.id],
            )

        if matched_moves == 0:
            retour_products = [
                self.env['product.product'].browse(pid).display_name
                for pid in product_qty_map
            ]
            picking_products = sorted({m.product_id.display_name for m in picking.move_ids})
            msg = (
                "None of the products on this retour match a move on picking %s.\n"
                "Retour products: %s\n"
                "Picking products: %s"
                % (picking.name, ', '.join(retour_products) or '(none)',
                   ', '.join(picking_products) or '(none)')
            )
            _logger.warning(
                'No matching moves for return picking on retour %s: %s',
                retour.name, msg,
            )
            retour.write({'df_process_code': 'E', 'df_error_message': msg})
            return

        try:
            return_record = self.env['stock.return.picking'].with_context(
                active_id=picking.id, active_model='stock.picking',
            ).create({
                'picking_id': picking.id,
                'product_return_moves': product_return_moves,
            })
            _logger.info('Return picking wizard created with %d return lines', matched_moves)
            new_picking_id = return_record._create_return()
            retour.write({
                'return_picking_id': new_picking_id,
                'df_process_code': 'F',
                'df_error_message': False,
            })
            _logger.info(
                'Created return picking %s for retour %s (P -> F)',
                new_picking_id, retour.name,
            )
        except Exception as e:
            msg = "Failed to create return picking: %s" % e
            retour.write({'df_process_code': 'E', 'df_error_message': msg})
            _logger.exception(
                'Error creating return picking for retour %s (P -> E): %s', retour.name, e,
            )


class WebshipRetourAndBackorderLine(models.Model):
    _name = 'webship.retour.and.backorder.line'
    _description = 'Stoqflow Retour and Backorder Line'

    retour_id = fields.Many2one(
        'webship.retour.and.backorder', string='Retour',
        required=True, ondelete='cascade', index=True,
    )
    df_stoqflow_id = fields.Char('Stoqflow Item ID')
    product_id = fields.Many2one('product.product', string='Product')
    product_display = fields.Char(
        'Product', compute='_compute_product_display',
    )
    df_stoqflow_product_id = fields.Char('Stoqflow Product ID')
    stoqflow_product_link = fields.Html(
        'Stoqflow Product', compute='_compute_stoqflow_product_link',
    )
    quantity = fields.Float('Quantity')

    @api.depends('product_id', 'df_stoqflow_product_id')
    def _compute_product_display(self):
        for rec in self:
            if rec.product_id:
                rec.product_display = rec.product_id.display_name
            elif rec.df_stoqflow_product_id:
                rec.product_display = 'Product not found in Odoo'
            else:
                rec.product_display = ''

    @api.depends('df_stoqflow_product_id', 'product_id')
    def _compute_stoqflow_product_link(self):
        base_app_url = self.env['ir.config_parameter'].sudo().get_param(
            'webship.base_app_url', '')
        for rec in self:
            if rec.df_stoqflow_product_id and base_app_url:
                url = base_app_url + 'products/' + rec.df_stoqflow_product_id
                # Show product code/SKU if found, otherwise the raw Stoqflow ID
                label = rec.df_stoqflow_product_id
                if rec.product_id and rec.product_id.default_code:
                    label = rec.product_id.default_code
                rec.stoqflow_product_link = (
                    '%s <a href="%s" target="_blank">'
                    '<img style="height:16px; width:16px" '
                    'src="/webship/static/src/img/stoqflow_16px.png"/></a>'
                ) % (label, url)
            else:
                rec.stoqflow_product_link = rec.df_stoqflow_product_id or ''
