# Stoqflow Backorder processing.
# Fetches orders and purchase orders created after the configured datetime
# pointers (one per type, stored on res.config.settings) and stores those
# carrying a parent_order_id as backorders. created_after (not edited_after)
# is used so newly created backorders that haven't been touched yet are
# picked up on the next run.
import logging
from datetime import datetime

import requests

from odoo import models, fields, api
from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)


class WebshipBackorder(models.Model):
    _name = 'webship.backorder'
    _description = 'Stoqflow Backorder'
    _order = 'ws_created desc'

    _ws_order_id_unique = models.Constraint(
        'UNIQUE(ws_order_id)',
        "Stoqflow order/PO id must be unique on backorder records.",
    )

    name = fields.Char('Order Number', readonly=True)
    order_or_po = fields.Selection([
        ('order', 'Order'),
        ('purchase_order', 'Purchase Order'),
    ], string='Type', readonly=True, default='order', required=True)
    ws_order_id = fields.Char('Stoqflow Order ID', readonly=True)
    ws_parent_order_id = fields.Char('Parent Order ID', readonly=True)
    parent_picking_id = fields.Many2one(
        'stock.picking', string='Parent Picking',
        compute='_compute_parent_picking', store=True,
    )
    odoo_backorder_picking_ids = fields.Many2many(
        'stock.picking', string='Backorder in Odoo',
        compute='_compute_odoo_backorder_pickings',
    )
    ws_status = fields.Char('Status', readonly=True)
    ws_client_name = fields.Char('Client', readonly=True)
    ws_product_sku = fields.Char('Product SKU', readonly=True)
    ws_backorder_qty = fields.Integer('Backorder Qty', readonly=True)
    ws_created = fields.Datetime('Created', readonly=True)
    ws_edited = fields.Datetime('Last Changed', readonly=True)
    process_code = fields.Selection([
        ('P', 'Pending'),
        ('F', 'Deleted in Stoqflow'),
        ('E', 'Error'),
    ], string='Process Code', readonly=True)
    deleted = fields.Boolean('Deleted', default=False, readonly=True)
    deleted_date = fields.Datetime('Deleted On', readonly=True)
    ws_order_json = fields.Text('Order JSON (snapshot)', readonly=True)
    ws_stoqflow_link = fields.Html(
        'Order link Stoqflow', compute='_compute_stoqflow_link',
    )
    ws_parent_stoqflow_link = fields.Html(
        'Parent Order link Stoqflow', compute='_compute_stoqflow_link',
    )

    @api.depends('name', 'ws_order_id', 'ws_parent_order_id', 'deleted', 'order_or_po')
    def _compute_stoqflow_link(self):
        base_app_url = self.env['ir.config_parameter'].sudo().get_str(
            'webship.base_app_url', '')
        for rec in self:
            path = 'purchase-orders/' if rec.order_or_po == 'purchase_order' else 'orders/'
            # Order link
            if not rec.ws_order_id:
                rec.ws_stoqflow_link = ''
            else:
                label = rec.name or rec.ws_order_id
                url = base_app_url + path + rec.ws_order_id
                if rec.deleted:
                    rec.ws_stoqflow_link = (
                        '<span style="color:#999">%s</span>' % label
                    )
                else:
                    rec.ws_stoqflow_link = (
                        '%s <a href="%s" target="_blank">'
                        '<img style="height:16px; width:16px" '
                        'src="/webship/static/src/img/stoqflow_16px.png"/></a>'
                    ) % (label, url)
            # Parent order link
            if not rec.ws_parent_order_id:
                rec.ws_parent_stoqflow_link = ''
            else:
                parent_url = base_app_url + path + rec.ws_parent_order_id
                parent_label = rec.ws_parent_order_id
                # Try to show the parent picking name instead of the raw ID
                if rec.parent_picking_id:
                    parent_label = rec.parent_picking_id.name
                rec.ws_parent_stoqflow_link = (
                    '%s <a href="%s" target="_blank">'
                    '<img style="height:16px; width:16px" '
                    'src="/webship/static/src/img/stoqflow_16px.png"/></a>'
                ) % (parent_label, parent_url)

    @api.depends('ws_parent_order_id', 'order_or_po')
    def _compute_parent_picking(self):
        order_parent_ids = [r.ws_parent_order_id for r in self
                            if r.ws_parent_order_id and r.order_or_po == 'order']
        po_parent_ids = [r.ws_parent_order_id for r in self
                         if r.ws_parent_order_id and r.order_or_po == 'purchase_order']
        order_map = {}
        if order_parent_ids:
            pickings = self.env['stock.picking'].search([
                ('df_picking_id_webship', 'in', order_parent_ids),
            ])
            order_map = {p.df_picking_id_webship: p.id for p in pickings}
        po_map = {}
        if po_parent_ids:
            pickings = self.env['stock.picking'].search([
                ('df_po_id_webship', 'in', po_parent_ids),
            ])
            po_map = {p.df_po_id_webship: p.id for p in pickings}
        for rec in self:
            if not rec.ws_parent_order_id:
                rec.parent_picking_id = False
            elif rec.order_or_po == 'purchase_order':
                rec.parent_picking_id = po_map.get(rec.ws_parent_order_id, False)
            else:
                rec.parent_picking_id = order_map.get(rec.ws_parent_order_id, False)

    @api.depends('parent_picking_id')
    def _compute_odoo_backorder_pickings(self):
        picking_ids = [r.parent_picking_id.id for r in self if r.parent_picking_id]
        bo_map = {}
        if picking_ids:
            backorders = self.env['stock.picking'].search([
                ('backorder_id', 'in', picking_ids),
            ])
            for bo in backorders:
                bo_map.setdefault(bo.backorder_id.id, []).append(bo.id)
        for rec in self:
            rec.odoo_backorder_picking_ids = bo_map.get(rec.parent_picking_id.id, [])

    @staticmethod
    def _parse_iso_datetime(value):
        """Convert ISO 8601 datetime string (e.g. '2026-03-31T19:46:57.223Z') to Odoo format."""
        if not value:
            return False
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, AttributeError):
            return False

    def _get_handler(self):
        login = self.env['ir.config_parameter'].sudo().get_str('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_str('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_str('webship.base_url')
        handler = WebShipHandler(login, pw, base_url)
        handler.set_env(self.env)
        return handler

    # Parameter keys for the incremental pointers exposed on the settings form.
    _POINTER_PARAM_ORDER = 'webship.last_check_date_backorder_order'
    _POINTER_PARAM_PO = 'webship.last_check_date_backorder_po'

    def action_fetch_backorders(self):
        """Fetch backorders incrementally using the datetime pointers from settings.

        For orders and purchase orders separately:
          1. Read the pointer from ir.config_parameter.
          2. GET /orders (or /purchase-orders) with created_after=<pointer>, detail=high.
             created_after is used (not edited_after) so freshly created backorders
             that haven't been edited yet are still included.
          3. Any record that has a parent_order_id is persisted as a backorder
             (upserted on ws_order_id).
          4. On success, advance the pointer to 'now'.
        """
        icp = self.env['ir.config_parameter'].sudo()
        handler = self._get_handler()
        auto_delete = icp.get_str('webship.auto_delete_backorders') == 'True'

        started_at = fields.Datetime.now()
        order_pointer = icp.get_str(self._POINTER_PARAM_ORDER) or None
        po_pointer = icp.get_str(self._POINTER_PARAM_PO) or None

        errors = []
        order_count, order_scanned = self._fetch_backorders_for(
            handler, 'orders', 'order', order_pointer, auto_delete, errors,
        )
        po_count, po_scanned = self._fetch_backorders_for(
            handler, 'purchase-orders', 'purchase_order', po_pointer, auto_delete, errors,
        )

        # Only advance a pointer if its fetch succeeded. Errors are reported to the user.
        started_str = fields.Datetime.to_string(started_at)
        if 'orders' not in errors:
            icp.set_str(self._POINTER_PARAM_ORDER, started_str)
        if 'purchase-orders' not in errors:
            icp.set_str(self._POINTER_PARAM_PO, started_str)

        if errors:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Backorders',
                    'type': 'warning',
                    'message': (
                        'Fetched %d order backorder(s) and %d PO backorder(s); '
                        'errors on: %s.' % (order_count, po_count, ', '.join(errors))
                    ),
                    'sticky': True,
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Backorders',
                'type': 'success',
                'message': (
                    'Fetched %d order backorder(s) (%d scanned) and '
                    '%d PO backorder(s) (%d scanned).'
                    % (order_count, order_scanned, po_count, po_scanned)
                ),
                'sticky': False,
            }
        }

    def _fetch_backorders_for(self, handler, endpoint, kind, pointer, auto_delete, errors):
        """Fetch one endpoint (orders or purchase-orders), upsert records that
        have a parent_order_id. Returns (created_or_updated, scanned)."""
        result = handler.fetchAll(endpoint, 'high', sCreatedAfter=pointer)
        if result.get('status') != 'success':
            _logger.error('Backorder fetch failed for %s: %s', endpoint, result.get('txt', ''))
            errors.append(endpoint)
            return 0, 0

        scanned = 0
        kept = 0
        for page in result['data'].values():
            for record in page:
                scanned += 1
                if not record.get('parent_order_id'):
                    continue
                self._upsert_backorder(record, kind, auto_delete)
                kept += 1
        return kept, scanned

    def _upsert_backorder(self, record, kind, auto_delete):
        """Create or update a backorder row from a Stoqflow order or PO payload."""
        order_id = record.get('_id')
        if not order_id:
            return

        client_info = record.get('client_info') or {}
        client_name = (
            client_info.get('client_name')
            or client_info.get('name')
            or record.get('supplier_reference', '')
            or ''
        )

        order_items = record.get('order_items') or []
        total_qty = sum(item.get('quantity', 0) or 0 for item in order_items)
        skus = self._collect_skus(order_items)

        vals = {
            'name': record.get('order_number') or order_id,
            'order_or_po': kind,
            'ws_parent_order_id': record.get('parent_order_id', ''),
            'ws_status': record.get('status', ''),
            'ws_client_name': client_name,
            'ws_product_sku': skus,
            'ws_backorder_qty': total_qty,
            'ws_created': self._parse_iso_datetime(record.get('created')),
            'ws_edited': self._parse_iso_datetime(record.get('edited')),
        }

        existing = self.search([('ws_order_id', '=', order_id)], limit=1)
        if existing:
            # Never resurrect a record the user already deleted in Stoqflow.
            if not existing.deleted:
                existing.write(vals)
        else:
            vals['ws_order_id'] = order_id
            if auto_delete:
                vals['process_code'] = 'P'
            self.create(vals)

    def _collect_skus(self, order_items):
        """Join SKUs for an order_items list. Uses the item's sku when present,
        otherwise falls back to the Odoo product linked via Stoqflow product_id."""
        product_ids = [i.get('product_id') for i in order_items if i.get('product_id') and not i.get('sku')]
        product_map = {}
        if product_ids:
            products = self.env['product.product'].search([
                ('df_product_id_webship', 'in', product_ids),
            ])
            product_map = {p.df_product_id_webship: p.default_code or '' for p in products}

        skus = []
        for item in order_items:
            sku = item.get('sku') or product_map.get(item.get('product_id'), '')
            if sku:
                skus.append(sku)
        return ', '.join(skus)

    def action_delete_in_webship(self):
        """Manual delete from the UI. When any selected record has no Odoo
        backorder picking, open a confirmation wizard so the user can decide
        whether to proceed."""
        records_to_delete = self.filtered(lambda r: r.ws_order_id and not r.deleted)
        if not records_to_delete:
            return

        no_odoo_bo = records_to_delete.filtered(lambda r: not r.odoo_backorder_picking_ids)
        if no_odoo_bo:
            names = ', '.join(no_odoo_bo.mapped('name'))
            return {
                'type': 'ir.actions.act_window',
                'name': 'Confirm Delete',
                'res_model': 'webship.backorder.confirm.delete',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_backorder_ids': records_to_delete.ids,
                    'default_warning_message':
                        'Warning no backorder exists in Odoo. Do you really '
                        'want to delete?\n\n'
                        'Affected records (no Odoo backorder): %s' % names,
                },
            }

        return self._execute_delete(records_to_delete)

    def _execute_delete(self, records=None, force=False):
        """Fetch order JSON from Stoqflow, then delete the backorders.

        Unless ``force=True``, any record without a corresponding Odoo
        backorder picking is filtered out. ``force=True`` is only set by the
        confirm-delete wizard after the user explicitly confirms.
        """
        if records is None:
            records = self.filtered(lambda r: r.ws_order_id and not r.deleted)

        if not force:
            records = records.filtered(lambda r: r.odoo_backorder_picking_ids)
        if not records:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Backorders',
                    'type': 'warning',
                    'message': 'Nothing deleted: no selected backorder has a '
                               'corresponding backorder picking in Odoo.',
                    'sticky': True,
                },
            }

        handler = self._get_handler()
        errors = []
        deleted_count = 0

        for record in records:
            endpoint = 'purchase-orders/' if record.order_or_po == 'purchase_order' else 'orders/'
            url = handler.baseUrl + endpoint + record.ws_order_id
            try:
                # Fetch full order info before deleting
                get_response = requests.get(
                    url, auth=handler.auth, headers=handler.headers,
                    timeout=handler.REQUEST_TIMEOUT,
                )
                if get_response.status_code == 200:
                    record.ws_order_json = get_response.text

                # Delete the order in Stoqflow
                del_response = requests.delete(
                    url, auth=handler.auth, headers=handler.headers,
                    timeout=handler.REQUEST_TIMEOUT,
                )
                if del_response.status_code == 200:
                    record.write({
                        'process_code': 'F',
                        'deleted': True,
                        'deleted_date': fields.Datetime.now(),
                    })
                    deleted_count += 1
                else:
                    errors.append('%s: HTTP %s' % (record.name, del_response.status_code))
            except Exception as e:
                _logger.exception("Failed to delete backorder %s from Stoqflow", record.name)
                errors.append('%s: %s' % (record.name, str(e)))

        if errors:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Errors',
                    'type': 'warning',
                    'message': 'Some backorders could not be deleted: ' + ', '.join(errors),
                    'sticky': True,
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'type': 'success',
                'message': '%d backorder(s) deleted from Stoqflow.' % deleted_count,
                'sticky': False,
            }
        }

    def cron_auto_delete_backorders(self):
        """Cron job: delete all backorders with process_code 'P' from Stoqflow.

        Records without a corresponding Odoo backorder picking are left alone
        (process_code stays 'P') so they can be picked up by a future run once
        an Odoo backorder exists.
        """
        pending = self.search([('process_code', '=', 'P'), ('deleted', '=', False)])
        eligible = pending.filtered(lambda r: r.odoo_backorder_picking_ids)
        skipped = pending - eligible
        if skipped:
            _logger.info(
                'Auto-delete: skipped %d backorder(s) with no Odoo backorder picking: %s',
                len(skipped), ', '.join(skipped.mapped('name')),
            )
        if not eligible:
            return

        handler = eligible[0]._get_handler()

        for record in eligible:
            if not record.ws_order_id:
                continue
            endpoint = 'purchase-orders/' if record.order_or_po == 'purchase_order' else 'orders/'
            url = handler.baseUrl + endpoint + record.ws_order_id
            try:
                # Fetch full order info before deleting
                get_response = requests.get(
                    url, auth=handler.auth, headers=handler.headers,
                    timeout=handler.REQUEST_TIMEOUT,
                )
                if get_response.status_code == 200:
                    record.ws_order_json = get_response.text

                # Delete the order in Stoqflow
                del_response = requests.delete(
                    url, auth=handler.auth, headers=handler.headers,
                    timeout=handler.REQUEST_TIMEOUT,
                )
                if del_response.status_code == 200:
                    record.write({
                        'process_code': 'F',
                        'deleted': True,
                        'deleted_date': fields.Datetime.now(),
                    })
                    _logger.info('Auto-deleted backorder %s from Stoqflow', record.name)
                else:
                    record.process_code = 'E'
                    _logger.error(
                        'Auto-delete backorder %s failed: HTTP %s',
                        record.name, del_response.status_code,
                    )
            except Exception as e:
                record.process_code = 'E'
                _logger.exception(
                    'Auto-delete backorder %s failed: %s', record.name, e,
                )
