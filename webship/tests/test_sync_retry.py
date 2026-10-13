# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking


class TestSyncRetry(TransactionCase):
    """Risk 17a: a failing picking is marked 'E', retried up to the configured
    count, then left for manual sync; an error e-mail is sent on every failed
    attempt and a mail failure never aborts the rest of the queue."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(StockPicking, 'fetch_picking_code', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.settings = self.env['res.config.settings']
        self.param = self.env['ir.config_parameter'].sudo()
        self.param.set_param('webship.sync_retry_count', '2')

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.customers = self.env.ref('stock.stock_location_customers')
        self.product = self.env['product.product'].create({'name': 'Widget', 'default_code': 'SKU1'})
        self.picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.ws_loc.id,
            'location_dest_id': self.customers.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'product_uom': self.product.uom_id.id,
                'location_id': self.ws_loc.id, 'location_dest_id': self.customers.id,
            })],
        })
        # Make sure it is a pending Webship picking.
        self.picking.df_process_code = 'P'

    def _run(self, push_return=None, email_side_effect=None):
        with mock.patch.object(StockPicking, '_ws_push_to_stoqflow', return_value=push_return), \
                mock.patch.object(type(self.settings), '_ws_send_error_email',
                                  side_effect=email_side_effect) as email:
            self.settings.ws_sync_all_pickings_statusP()
        return email

    def _emails_for_picking(self, email_mock):
        """Count error e-mails sent for THIS test's picking only. The cron
        processes every pending picking in the database, so the test DB may
        contain unrelated 'P' pickings that are also e-mailed - we assert only
        on ours (_ws_send_error_email is called with the picking name first)."""
        name = self.picking.name
        return sum(1 for c in email_mock.call_args_list if c.args and c.args[0] == name)

    def test_error_marks_E_retries_then_stops(self):
        # Attempt 1: fails -> E, count 1, email once.
        email = self._run(push_return=['boom'])
        self.assertEqual(self.picking.df_process_code, 'E')
        self.assertEqual(self.picking.df_sync_retry_count, 1)
        self.assertEqual(self._emails_for_picking(email), 1)

        # Attempt 2: still within budget (1 < 2) -> retried, count 2.
        email = self._run(push_return=['boom'])
        self.assertEqual(self.picking.df_sync_retry_count, 2)
        self.assertEqual(self._emails_for_picking(email), 1)

        # Attempt 3: count 2 is not < 2 -> no longer auto-processed, no e-mail.
        email = self._run(push_return=['boom'])
        self.assertEqual(self.picking.df_sync_retry_count, 2)
        self.assertEqual(self._emails_for_picking(email), 0)

    def test_success_resets_counter(self):
        self._run(push_return=['boom'])
        self.assertEqual(self.picking.df_sync_retry_count, 1)
        self.assertEqual(self.picking.df_process_code, 'E')
        # A successful push (handled inside _ws_push_to_stoqflow) clears the
        # counter; simulate it directly since the real method is patched here.
        self.picking.df_process_code = 'F'
        self.picking.df_sync_retry_count = 0
        # Back to pending, then a successful run leaves it alone (no email).
        self.picking.df_process_code = 'P'
        email = self._run(push_return=[])
        self.assertEqual(self.picking.df_sync_retry_count, 0)
        self.assertEqual(self._emails_for_picking(email), 0)

    def test_mail_failure_does_not_abort_queue(self):
        # Even if the error e-mail raises, the picking is still marked 'E' and
        # the cron does not propagate the exception.
        self._run(push_return=['boom'], email_side_effect=Exception('smtp down'))
        self.assertEqual(self.picking.df_process_code, 'E')
        self.assertEqual(self.picking.df_sync_retry_count, 1)

    def _done_receipt(self):
        # Inbound receipt validated to 'done' (supplier locations have infinite
        # availability, so no on-hand stock is needed) in Webship scope.
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'product_uom': self.product.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': self.ws_loc.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 1
        picking.move_ids.picked = True
        picking.button_validate()
        return picking

    def test_done_picking_marked_NA_not_errored(self):
        # A picking already validated in Odoo can never be synced. The cron must
        # mark it terminal ('NA') without pushing, without churning it as 'E',
        # and without e-mailing - see ws_sync_all_pickings_statusP.
        done = self._done_receipt()
        self.assertEqual(done.state, 'done')
        done.df_process_code = 'P'

        with mock.patch.object(
                StockPicking, '_ws_push_to_stoqflow',
                side_effect=AssertionError('done picking must not be pushed')) as push, \
                mock.patch.object(type(self.settings), '_ws_send_error_email') as email:
            self.settings.ws_sync_all_pickings_statusP()

        self.assertEqual(done.df_process_code, 'NA')
        self.assertEqual(done.df_sync_retry_count, 0)
        push.assert_not_called()
        self.assertFalse(
            any(c.args and c.args[0] == done.name for c in email.call_args_list),
            'no error e-mail should be sent for a done picking')
