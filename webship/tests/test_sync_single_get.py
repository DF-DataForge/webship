# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking


class TestSyncSingleGet(TransactionCase):
    """After a successful push, statusWsToOdoo already fetches the order with
    ?detail=high - a payload that carries order_number. _ws_push_to_stoqflow
    must therefore NOT issue a second GET (get_picking_code) just to read that
    number; it only falls back to one when the code is still missing."""

    def setUp(self):
        super().setUp()
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
                'uom_id': self.product.uom_id.id,
                'location_id': self.ws_loc.id, 'location_dest_id': self.customers.id,
            })],
        })

    def _handler_mock(self, code_after_sync):
        """A stub handler whose sync_picking succeeds and, like the real
        statusWsToOdoo, sets df_picking_code_webship to `code_after_sync`."""
        handler = mock.MagicMock()
        handler._sync_warnings = []

        def _sync(picking):
            picking.df_picking_id_webship = 'O1'
            if code_after_sync is not None:
                picking.df_picking_code_webship = code_after_sync
            return []
        handler.sync_picking.side_effect = _sync
        handler.get_picking_code.return_value = 'FALLBACK'
        handler.get_po_code.return_value = None
        return handler

    def test_no_second_get_when_code_already_captured(self):
        handler = self._handler_mock(code_after_sync='SO00049')
        with mock.patch.object(StockPicking, 'getHandler', return_value=handler):
            self.picking._ws_push_to_stoqflow()

        handler.get_picking_code.assert_not_called()
        self.assertEqual(self.picking.df_picking_code_webship, 'SO00049')

    def test_fallback_get_when_code_missing(self):
        handler = self._handler_mock(code_after_sync=None)
        with mock.patch.object(StockPicking, 'getHandler', return_value=handler):
            self.picking._ws_push_to_stoqflow()

        handler.get_picking_code.assert_called_once_with('O1')
        self.assertEqual(self.picking.df_picking_code_webship, 'FALLBACK')
