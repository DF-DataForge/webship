# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler

EDITED = '2026-07-10T13:26:06.030Z'


class TestStatusWsToOdoo(TransactionCase):
    """statusWsToOdoo on a completed order/PO must apply the ACTUAL picked or
    received quantities from the detail=high payload through
    setPickingQuantities. The previous bare button_validate() completed every
    line at its ordered quantity without ever looking at the picks."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            p = mock.patch.object(target, attr, return_value='X')
            p.start()
            self.addCleanup(p.stop)
        # Only quantity application is asserted here; validation behaviour is
        # covered by test_backorder_on_complete / test_po_received_validation.
        for name in ('_validate_completed_picking_native',
                     '_validate_completed_picking_legacy'):
            p = mock.patch.object(WebShipHandler, name, return_value=[])
            p.start()
            self.addCleanup(p.stop)

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.customers = self.env.ref('stock.stock_location_customers')
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.p1 = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1', 'df_product_id_webship': 'WS1'})
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _mock_get(self, payload):
        response = mock.Mock(status_code=200, json=lambda: payload)
        session = mock.Mock()
        session.get.return_value = response
        return mock.patch.object(self.handler, 'session', session)

    def test_completed_order_applies_picked_qty(self):
        # Outbound: 3 of 5 picked -> the move reflects 3, not the demand.
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.ws_loc.id, 'location_dest_id': self.customers.id,
            'move_ids': [(0, 0, {
                'product_id': self.p1.id, 'product_uom_qty': 5,
                'product_uom': self.p1.uom_id.id,
                'location_id': self.ws_loc.id, 'location_dest_id': self.customers.id,
            })],
        })
        picking.df_picking_id_webship = 'ORD1'
        self.assertEqual(picking.df_object_in_webship, 'Order')

        payload = {'status': 'completed', 'edited': EDITED,
                   'picks': [{'product_id': 'WS1', 'quantity': 3}]}
        with self._mock_get(payload):
            errors = self.handler.statusWsToOdoo(picking)

        self.assertFalse(errors, "errors: %s" % errors)
        self.assertEqual(picking.move_ids.quantity, 3.0,
                         "move.quantity=%s (expected picked 3, not ordered 5)"
                         % picking.move_ids.quantity)

    def test_completed_po_applies_received_qty(self):
        # Inbound: 6 of 10 received -> the move reflects 6, not the demand.
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': self.p1.id, 'product_uom_qty': 10,
                'product_uom': self.p1.uom_id.id,
                'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            })],
        })
        picking.df_po_id_webship = 'PO1'
        self.assertEqual(picking.df_object_in_webship, 'Purchase order')

        payload = {'status': 'completed', 'edited': EDITED,
                   'order_items': [{'product_id': 'WS1', 'quantity': 10, 'received': 6}]}
        with self._mock_get(payload):
            errors = self.handler.statusWsToOdoo(picking)

        self.assertFalse(errors, "errors: %s" % errors)
        self.assertEqual(picking.move_ids.quantity, 6.0,
                         "move.quantity=%s (expected received 6, not ordered 10)"
                         % picking.move_ids.quantity)


class TestPoPollNoForceValidate(TransactionCase):
    """sync_po_statusses_since_last called setPickingQuantities and then an
    unconditional button_validate() right after it, forcing a short receipt to
    done at its ordered quantities and defeating the backorder settings."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            p = mock.patch.object(target, attr, return_value='X')
            p.start()
            self.addCleanup(p.stop)

        param = self.env['ir.config_parameter'].sudo()
        # Native path with auto-backorder OFF: a short receipt records the
        # received quantity and stays open. The trailing button_validate()
        # used to force it done anyway.
        param.set_param('webship.auto_create_backorder', 'False')

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.p1 = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1', 'df_product_id_webship': 'WS1'})
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def test_po_poll_short_receipt_left_open(self):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': self.p1.id, 'product_uom_qty': 10,
                'product_uom': self.p1.uom_id.id,
                'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            })],
        })
        picking.df_po_id_webship = 'PO1'

        po_order = {'_id': 'PO1', 'status': 'completed', 'edited': EDITED,
                    'order_items': [{'product_id': 'WS1', 'quantity': 10, 'received': 6}]}
        fetched = {'status': 'success', 'data': {1: [po_order]}}
        with mock.patch.object(self.handler, 'fetchAll', return_value=fetched):
            self.handler.sync_po_statusses_since_last(None)

        self.assertEqual(picking.move_ids.quantity, 6.0,
                         "move.quantity=%s (expected received 6)" % picking.move_ids.quantity)
        self.assertNotEqual(picking.state, 'done',
                            "short receipt with auto-backorder off must stay open")
