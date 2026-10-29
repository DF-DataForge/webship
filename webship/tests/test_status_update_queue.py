# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler


def _order(order_id, edited, status='completed', number=None):
    return {
        '_id': order_id,
        'status': status,
        'edited': edited,
        'order_number': number or order_id,
        'order_items': [],
    }


def _pages(*orders):
    return {'status': 'success', 'data': {1: list(orders)}, 'totalCount': None}


class TestStatusUpdateQueue(TransactionCase):
    """Test the incremental status-update queue: changed orders fetched with
    edited_after are queued and processed via fetchQuantities, instead of
    polling every open picking."""

    def setUp(self):
        super(TestStatusUpdateQueue, self).setUp()
        self.param = self.env['ir.config_parameter'].sudo()
        self.queue = self.env['webship.status.update']

        # Stored computes on stock.picking call the Stoqflow API when the
        # Stoqflow id changes - patch them out for all tests.
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            patcher = mock.patch.object(target, attr, return_value='ORD-1')
            patcher.start()
            self.addCleanup(patcher.stop)

        picking_type = self.env.ref('stock.picking_type_out')
        self.picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        self.picking.df_picking_id_webship = 'WSORDER1'

        self.param.set_str('webship.use_status_update_queue', 'True')
        self.param.set_str('webship.last_check_status_update', '2026-07-01 00:00:00')

    def test_cron_queues_and_processes_changed_orders(self):
        """A poll queues each changed order, updates matched pickings once via
        fetchQuantities, skips unknown ones, and advances the checkpoint."""
        orders = _pages(
            _order('WSORDER1', '2026-07-08T10:00:00.123Z'),
            _order('WSUNKNOWN', '2026-07-08T10:05:00.456Z'),
        )
        pos = _pages()

        with mock.patch.object(WebShipHandler, 'fetchAll',
                               side_effect=[orders, pos]) as fetch_mock, \
                mock.patch.object(StockPicking, 'apply_stoqflow_payload',
                                  autospec=True) as fq_mock:
            self.queue.cron_fetch_and_process()

        # edited_after = checkpoint + 1s, in the API's ISO format
        self.assertEqual(fetch_mock.call_args_list[0].args,
                         ('orders', 'high', '2026-07-01T00:00:01Z', None))
        self.assertEqual(fetch_mock.call_args_list[1].args,
                         ('purchase-orders', 'high', '2026-07-01T00:00:01Z', None))

        matched = self.queue.search([('df_webship_id', '=', 'WSORDER1')])
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched.state, 'done')
        self.assertEqual(matched.picking_id, self.picking)
        self.assertEqual(fq_mock.call_count, 1)

        unknown = self.queue.search([('df_webship_id', '=', 'WSUNKNOWN')])
        self.assertEqual(unknown.state, 'skipped')

        # Checkpoint advanced to the newest 'edited' seen (microseconds dropped)
        self.assertEqual(self.param.get_str('webship.last_check_status_update'),
                         '2026-07-08 10:05:00')

    def test_pending_entries_are_upserted_not_duplicated(self):
        """The same order changing again before the queue is processed must
        refresh the pending entry, not create a duplicate."""
        handler = mock.Mock()
        handler.fetchAll.return_value = _pages(
            _order('WSORDER1', '2026-07-08T10:00:00.000Z', status='picking'))
        self.queue._queue_changed_records(handler, 'orders', 'order', 'x')

        handler.fetchAll.return_value = _pages(
            _order('WSORDER1', '2026-07-08T11:00:00.000Z', status='completed'))
        self.queue._queue_changed_records(handler, 'orders', 'order', 'x')

        entries = self.queue.search([('df_webship_id', '=', 'WSORDER1')])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries.state, 'pending')
        self.assertEqual(entries.df_status_webship, 'completed')

    def _done_receipt(self):
        stock = self.env.ref('stock.stock_location_stock')
        suppliers = self.env.ref('stock.stock_location_suppliers')
        product = self.env['product.product'].create({'name': 'Widget2', 'default_code': 'SKU2'})
        p = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': suppliers.id,
            'location_dest_id': stock.id,
            'move_ids': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': 1,
                'uom_id': product.uom_id.id,
                'location_id': suppliers.id, 'location_dest_id': stock.id,
            })],
        })
        p.action_confirm()
        p.action_assign()
        p.move_ids.quantity = 1
        p.move_ids.picked = True
        p.button_validate()
        return p

    def test_done_picking_skipped_not_refetched(self):
        """A queue entry whose picking is already done in Odoo must be skipped
        without an API call - re-fetching a done picking is a no-op."""
        done = self._done_receipt()
        self.assertEqual(done.state, 'done')
        entry = self.queue.create({
            'df_webship_id': 'WSDONE1',
            'df_object_type': 'order',
            'picking_id': done.id,
        })
        with mock.patch.object(StockPicking, 'apply_stoqflow_payload', autospec=True) as ap:
            self.queue._process_pending()
        ap.assert_not_called()
        self.assertEqual(entry.state, 'skipped')
        self.assertIn('already done', entry.df_result or '')

    def test_last_run_timestamp_updates_even_when_empty(self):
        """The 'last run' checkpoint must advance on every run, including a run
        that finds no changed records (so the UI can confirm the cron is alive)."""
        self.param.set_str('webship.last_run_status_update', '')
        with mock.patch.object(WebShipHandler, 'fetchAll', side_effect=[_pages(), _pages()]):
            self.queue.cron_fetch_and_process()
        self.assertTrue(self.param.get_str('webship.last_run_status_update'))

    def test_process_error_is_recorded_per_entry(self):
        """A processing failure marks only that entry as error."""
        entry = self.queue.create({
            'df_webship_id': 'WSORDER1',
            'df_object_type': 'order',
            'picking_id': self.picking.id,
        })
        with mock.patch.object(StockPicking, 'apply_stoqflow_payload', autospec=True,
                               side_effect=Exception('boom')):
            self.queue._process_pending()

        self.assertEqual(entry.state, 'error')
        self.assertIn('boom', entry.df_result)

    def test_same_picking_updated_once_per_run(self):
        """Several queue entries for the same picking trigger one update."""
        self.picking.df_po_id_webship = 'WSPO1'
        self.queue.create({
            'df_webship_id': 'WSORDER1',
            'df_object_type': 'order',
            'picking_id': self.picking.id,
        })
        self.queue.create({
            'df_webship_id': 'WSPO1',
            'df_object_type': 'purchase-order',
            'picking_id': self.picking.id,
        })
        with mock.patch.object(StockPicking, 'apply_stoqflow_payload',
                               autospec=True) as fq_mock:
            self.queue._process_pending()

        self.assertEqual(fq_mock.call_count, 1)
        states = self.queue.search([]).mapped('state')
        self.assertEqual(states, ['done', 'done'])

    def test_cron_is_noop_when_toggle_disabled(self):
        """With the setting off, the incremental cron must not call the API."""
        self.param.set_str('webship.use_status_update_queue', 'False')
        with mock.patch.object(WebShipHandler, 'fetchAll') as fetch_mock:
            self.queue.cron_fetch_and_process()
        fetch_mock.assert_not_called()

    def test_full_sweep_runs_even_when_toggle_enabled(self):
        """The full-sweep sync stays available as a fallback: even with the
        incremental toggle on, running it no longer early-returns - it sweeps
        the open pickings and advances the checkpoint. This lets it be triggered
        manually (or on its own cron) when the incremental queue is not keeping
        pickings up to date. The advancing checkpoint (which the old early-return
        left untouched) proves the method ran through instead of being skipped."""
        self.param.set_str('webship.use_status_update_queue', 'True')
        self.param.set_str('webship.last_check_date_status', '2026-07-01 00:00:00')
        self.param.set_str('webship.last_check_po_date_status', '2026-07-01 00:00:00')
        with mock.patch.object(StockPicking, 'fetchQuantities',
                               autospec=True):
            self.env['res.config.settings'].ws_sync_statusses_since_last()
        self.assertNotEqual(self.param.get_str('webship.last_check_date_status'),
                            '2026-07-01 00:00:00')
        self.assertNotEqual(self.param.get_str('webship.last_check_po_date_status'),
                            '2026-07-01 00:00:00')

    def test_settings_control_incremental_cron(self):
        """The incremental status-update cron is a first-class row in the
        Scheduled Tasks list: its Active checkbox and interval must be written
        to ir_cron_status_updates on save (and read back into the form)."""
        cron = self.env.ref('webship.ir_cron_status_updates')

        cron.active = False
        self.env['res.config.settings'].create({
            'webship_cron_status_updates': True,
            'webship_cron_status_updates_interval_number': 15,
            'webship_cron_status_updates_interval_type': 'minutes',
        }).execute()
        self.assertTrue(cron.active)
        self.assertEqual(cron.interval_number, 15)
        self.assertEqual(cron.interval_type, 'minutes')

        # And the toggle round-trips back into the settings form via get_values.
        self.assertTrue(
            self.env['res.config.settings'].create({}).webship_cron_status_updates)

        self.env['res.config.settings'].create({
            'webship_cron_status_updates': False,
        }).execute()
        self.assertFalse(cron.active)
