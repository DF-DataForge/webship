# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler


class TestPoReceivedValidation(TransactionCase):
    """Scenario 21: a completed purchase order is applied to the Odoo receipt
    using the RECEIVED quantities, not the ordered ones. Uses the native
    validation path with auto-backorder OFF so the received quantities can be
    asserted on the moves without invoking Odoo's full validation machinery."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            patcher = mock.patch.object(target, attr, return_value='X')
            patcher.start()
            self.addCleanup(patcher.stop)

        param = self.env['ir.config_parameter'].sudo()
        # Native path (so received:0 lines are never force-completed) with
        # auto-backorder OFF (so a short receipt records a warning instead of
        # calling button_validate - keeps the assertion on move.quantity clean).
        param.set_param('webship.use_native_backorder', 'True')
        param.set_param('webship.auto_create_backorder', 'False')

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock',
            'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.p1 = self.env['product.product'].create({
            'name': 'Product One', 'default_code': 'SKU1', 'df_product_id_webship': 'WS1',
        })

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _receipt(self, demand):
        return self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id,
            'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': self.p1.id,
                'product_uom_qty': demand,
                'product_uom': self.p1.uom_id.id,
                'location_id': self.suppliers.id,
                'location_dest_id': self.ws_loc.id,
            })],
        })

    @staticmethod
    def _po(received):
        # Ordered 10, received per the argument; no 'picks' -> inbound branch.
        return {
            'status': 'completed',
            'edited': '2026-07-10T13:26:06.030Z',
            'order_items': [{'product_id': 'WS1', 'quantity': 10, 'received': received}],
        }

    def test_received_short_applies_received_quantity(self):
        picking = self._receipt(10)
        self.handler.setPickingQuantities(picking, self._po(9))
        move = picking.move_ids
        self.assertEqual(move.quantity, 9.0, "receipt must reflect received (9), not ordered (10)")
        self.assertNotEqual(picking.state, 'done')

    def test_received_zero_stays_zero_and_open(self):
        picking = self._receipt(10)
        self.handler.setPickingQuantities(picking, self._po(0))
        self.assertEqual(picking.move_ids.quantity, 0.0, "received 0 must not fill the ordered qty")
        self.assertNotEqual(picking.state, 'done')
        # The picking is left open with an explanatory sync result.
        self.assertTrue(picking.df_picking_syncresult_webship)
