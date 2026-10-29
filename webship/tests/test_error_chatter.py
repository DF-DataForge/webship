# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestErrorChatter(TransactionCase):
    """webship.log_errors_chatter: when enabled, sync errors from a failed
    _ws_push_to_stoqflow are also posted to the picking chatter; when disabled,
    no chatter message is added (only the 'Result last sync' field is set)."""

    def setUp(self):
        super().setUp()
        self.param = self.env['ir.config_parameter'].sudo()

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.customers = self.env.ref('stock.stock_location_customers')
        self.product = self.env['product.product'].create(
            {'name': 'Widget', 'default_code': 'SKU1'})
        self.picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.ws_loc.id,
            'location_dest_id': self.customers.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'uom_id': self.product.uom_id.id,
                'location_id': self.ws_loc.id,
                'location_dest_id': self.customers.id,
            })],
        })

    def _push_with_errors(self, errors):
        """Run _ws_push_to_stoqflow with sync_picking returning the given errors,
        and return the number of new chatter messages on the picking."""
        before = len(self.picking.message_ids)
        with mock.patch.object(WebShipHandler, 'sync_picking', return_value=errors):
            result = self.picking._ws_push_to_stoqflow()
        self.assertEqual(result, errors)
        return len(self.picking.message_ids) - before

    def test_errors_posted_to_chatter_when_enabled(self):
        self.param.set_str('webship.log_errors_chatter', 'True')
        posted = self._push_with_errors(['Not all items are in stock',
                                         'SKU not found in Stoqflow for product Widget'])
        self.assertEqual(posted, 1)
        msg = self.picking.message_ids[0]
        self.assertIn('Stoqflow sync errors', msg.body)
        self.assertIn('Not all items are in stock', msg.body)
        self.assertIn('SKU not found in Stoqflow for product Widget', msg.body)
        # The result field is set regardless of the chatter setting.
        self.assertIn('Errors occured', self.picking.df_picking_syncresult_webship)

    def test_no_chatter_when_disabled(self):
        self.param.set_str('webship.log_errors_chatter', 'False')
        posted = self._push_with_errors(['Not all items are in stock'])
        self.assertEqual(posted, 0)
        self.assertIn('Errors occured', self.picking.df_picking_syncresult_webship)

    def test_no_chatter_on_success(self):
        self.param.set_str('webship.log_errors_chatter', 'True')
        with mock.patch.object(WebShipHandler, 'sync_picking', return_value=[]), \
                mock.patch.object(WebShipHandler, 'get_picking_code', return_value='X'), \
                mock.patch.object(WebShipHandler, 'get_po_code', return_value='X'):
            before = len(self.picking.message_ids)
            self.picking._ws_push_to_stoqflow()
        self.assertEqual(len(self.picking.message_ids) - before, 0)
