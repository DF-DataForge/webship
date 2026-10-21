# Incremental status-update queue for the Stoqflow -> Odoo direction.
# Instead of polling GET /orders/{id} for every open picking, a cron
# fetches only the orders/purchase-orders changed since the last check
# (GET /orders?edited_after=... and GET /purchase-orders?edited_after=...),
# stores them in this table, and processes each entry with the existing
# fetchQuantities method on the matched picking. This reduces the request
# volume from one call per open picking to two list calls plus one call
# per actually-changed record.
from datetime import datetime, timedelta
import logging

from odoo import models, fields

from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)

# Timestamp formats returned by the Stoqflow API in 'edited'/'created'
STOQFLOW_DT_FORMATS = ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ')
# Format accepted by the edited_after query parameter (see API v2 spec)
STOQFLOW_EDITED_AFTER_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


class StatusUpdate(models.Model):
    _name = 'webship.status.update'
    _description = 'Stoqflow Status Update Queue'
    _order = 'create_date desc, id desc'

    df_webship_id = fields.Char("Stoqflow ID", required=True, index=True, readonly=True)
    df_object_type = fields.Selection([
        ('order', 'Order'),
        ('purchase-order', 'Purchase Order'),
    ], string="Type", required=True, readonly=True)
    df_code_webship = fields.Char("Stoqflow number", readonly=True)
    df_status_webship = fields.Char("Stoqflow status", readonly=True)
    df_edited = fields.Datetime("Edited in Stoqflow", readonly=True)
    # Full order/PO payload from the poll (detail=high), reused when processing
    # so no extra per-record GET is needed.
    df_order_payload = fields.Json("Stoqflow payload", readonly=True)
    picking_id = fields.Many2one('stock.picking', string="Picking",
                                 ondelete='set null', index=True, readonly=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('skipped', 'Skipped'),
        ('error', 'Error'),
    ], string="State", default='pending', required=True, index=True)
    df_result = fields.Text("Result")

    def getHandler(self):
        """Create and return a WebShipHandler instance using stored Stoqflow API credentials."""
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)
        wsHandler.set_env(self.env)

        return wsHandler

    @staticmethod
    def _parse_stoqflow_datetime(value):
        """Parse a Stoqflow 'edited'/'created' timestamp into a naive UTC datetime.
        Returns False when the value is missing or unparseable."""
        if not value:
            return False
        for fmt in STOQFLOW_DT_FORMATS:
            try:
                return datetime.strptime(value, fmt).replace(microsecond=0)
            except ValueError:
                continue
        _logger.warning("Could not parse Stoqflow timestamp: %s", value)
        return False

    def _find_picking(self):
        """Find the unique Odoo picking linked to this queue entry's Stoqflow record.
        Returns an empty recordset when there is no (unique) match."""
        self.ensure_one()
        if self.df_object_type == 'order':
            field = 'df_picking_id_webship'
        else:
            field = 'df_po_id_webship'
        pickings = self.env['stock.picking'].search([(field, '=', self.df_webship_id)])
        if len(pickings) == 1:
            return pickings
        if len(pickings) > 1:
            _logger.warning(
                "Multiple pickings (%s) match Stoqflow %s %s - skipping",
                len(pickings), self.df_object_type, self.df_webship_id)
        return self.env['stock.picking']

    def _queue_changed_records(self, wsHandler, endpoint, object_type, edited_after):
        """Fetch all records changed since ``edited_after`` from a Stoqflow list
        endpoint and upsert them as pending queue entries.
        Returns (success, max_edited_datetime)."""
        result = wsHandler.fetchAll(endpoint, 'high', edited_after, None)

        if result.get('status') != 'success':
            _logger.error(
                "Fetching changed %s failed: HTTP %s - %s",
                endpoint, result.get('code'), result.get('txt'))
            return False, False

        max_edited = False
        count = 0
        for page in result['data'].values():
            for record in page:
                edited = self._parse_stoqflow_datetime(
                    record.get('edited') or record.get('created'))
                if edited and (not max_edited or edited > max_edited):
                    max_edited = edited

                vals = {
                    'df_code_webship': record.get('order_number'),
                    'df_status_webship': record.get('status'),
                    'df_edited': edited,
                    # Keep the full detail=high payload so processing can apply
                    # it directly instead of GETting the record again.
                    'df_order_payload': record,
                }

                # One pending entry per Stoqflow record: refresh it if the
                # same order changed again before the queue was processed.
                existing = self.search([
                    ('df_webship_id', '=', record['_id']),
                    ('df_object_type', '=', object_type),
                    ('state', '=', 'pending'),
                ], limit=1)
                if existing:
                    existing.write(vals)
                    entry = existing
                else:
                    vals.update({
                        'df_webship_id': record['_id'],
                        'df_object_type': object_type,
                    })
                    entry = self.create(vals)
                if not entry.picking_id:
                    entry.picking_id = entry._find_picking()
                count += 1

        _logger.info("Queued %s changed %s from Stoqflow", count, endpoint)
        return True, max_edited

    def _process_pending(self):
        """Update every pending queue entry via the existing fetchQuantities
        method on its picking (fetches the latest quantities and status from
        Stoqflow and applies them). Errors are recorded per entry and never
        block the rest of the queue."""
        pending = self.search([('state', '=', 'pending')], order='df_edited asc, id asc')
        processed_picking_ids = set()

        for entry in pending:
            picking = entry.picking_id or entry._find_picking()

            if not picking:
                entry.write({
                    'state': 'skipped',
                    'df_result': 'No matching picking found in Odoo',
                })
                continue

            if picking.state == 'cancel':
                entry.write({
                    'state': 'skipped',
                    'picking_id': picking.id,
                    'df_result': 'Picking is cancelled in Odoo',
                })
                continue

            # A picking already validated in Odoo is terminal - there are no
            # more quantities to receive/pick, so re-fetching it only re-applies
            # quantities to done moves (a no-op that logs "already in 'done'
            # state" warnings) and spends an API call per record. Skip it.
            if picking.state == 'done':
                entry.write({
                    'state': 'skipped',
                    'picking_id': picking.id,
                    'df_result': 'Picking already done in Odoo - nothing to update',
                })
                continue

            # fetchQuantities updates both the order and the PO side of a
            # picking in one go - no need to run it twice when several queue
            # entries point to the same picking.
            if picking.id in processed_picking_ids:
                entry.write({
                    'state': 'done',
                    'picking_id': picking.id,
                    'df_result': 'Already updated in this run (same picking)',
                })
                continue

            try:
                # Reuse the payload the poll already fetched (detail=high) so no
                # extra GET is issued; apply_stoqflow_payload falls back to a
                # fetch-by-id if the stored payload is missing.
                endpoint = 'orders' if entry.df_object_type == 'order' else 'purchase-orders'
                picking.apply_stoqflow_payload(
                    endpoint, entry.df_webship_id, entry.df_order_payload)
                processed_picking_ids.add(picking.id)
                entry.write({
                    'state': 'done',
                    'picking_id': picking.id,
                    'df_result': picking.df_picking_syncresult_webship or 'Updated',
                })
            except Exception as e:
                _logger.exception(
                    "Error processing status update for %s %s (picking %s): %s",
                    entry.df_object_type, entry.df_webship_id, picking.name, str(e))
                entry.write({
                    'state': 'error',
                    'picking_id': picking.id,
                    'df_result': str(e),
                })

        return pending

    def cron_fetch_and_process(self):
        """Cron entry point. Only runs when the incremental flow is enabled
        (webship.use_status_update_queue) - otherwise the old full sync
        (ws_sync_statusses_since_last) is the active flow and this is a no-op,
        so both crons can stay active and the setting decides which one works."""
        if self.env['ir.config_parameter'].sudo().get_param(
                'webship.use_status_update_queue') != 'True':
            _logger.info(
                "Skipping incremental status updates: disabled in settings "
                "(webship.use_status_update_queue)")
            return
        self._fetch_and_process()

    def _fetch_and_process(self):
        """Fetch orders and purchase orders changed in Stoqflow since the last
        check (edited_after) into the queue, then process all pending entries
        with fetchQuantities.

        The checkpoint (webship.last_check_status_update) only advances to the
        newest 'edited' timestamp seen when BOTH list calls succeed, so a
        failed poll is simply retried on the next run - the pending-entry
        upsert keeps that idempotent."""
        param = self.env['ir.config_parameter'].sudo()

        last_check = fields.Datetime.from_string(
            param.get_param('webship.last_check_status_update'))
        if not last_check:
            # First run: look back one day rather than fetching all history.
            last_check = fields.Datetime.now() - timedelta(days=1)

        # +1 second: edited_after is inclusive, so without the offset the
        # newest record of the previous poll would be refetched every run.
        edited_after = (last_check + timedelta(seconds=1)).strftime(
            STOQFLOW_EDITED_AFTER_FORMAT)

        wsHandler = self.getHandler()

        orders_ok, orders_max = self._queue_changed_records(
            wsHandler, 'orders', 'order', edited_after)
        pos_ok, pos_max = self._queue_changed_records(
            wsHandler, 'purchase-orders', 'purchase-order', edited_after)

        if orders_ok and pos_ok:
            new_checkpoint = max(filter(None, [orders_max, pos_max]), default=False)
            if new_checkpoint:
                param.set_param('webship.last_check_status_update',
                                fields.Datetime.to_string(new_checkpoint))

        # Record when the incremental cron last ran, independent of whether any
        # changed records were found. Unlike the checkpoint (which only advances
        # to the newest 'edited' seen), this always updates, so the settings
        # screen can show the cron is alive even on empty runs.
        param.set_param('webship.last_run_status_update',
                        fields.Datetime.to_string(fields.Datetime.now()))

        self._process_pending()

    def action_process(self):
        """Manual action: (re-)process the selected queue entries."""
        self.write({'state': 'pending'})
        self._process_pending()
