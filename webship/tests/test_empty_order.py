# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler


class TestEmptyOrder(TransactionCase):
    """When every picking line is an excluded product, the built order has no
    order_items. Such an order must NOT be sent to Stoqflow; instead a warning
    'All products excluded, so nothing sent to Stoqflow' is surfaced and the
    picking is treated as handled."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            patcher = mock.patch.object(target, attr, return_value='X')
            patcher.start()
            self.addCleanup(patcher.stop)

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.customers = self.env.ref('stock.stock_location_customers')
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.product = self.env['product.product'].create({
            'name': 'Excluded', 'default_code': 'SKU1',
        })
        self.partner = self.env['res.partner'].create({
            'name': 'ACME', 'df_supplier_id_webship': 'SUP1',
        })

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _picking(self, src, dest):
        picking = self.env['stock.picking'].create({
            'partner_id': self.partner.id,
            'picking_type_id': (self.env.ref('stock.picking_type_out').id
                                if dest == self.customers
                                else self.env.ref('stock.picking_type_in').id),
            'location_id': src.id,
            'location_dest_id': dest.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 5,
                'uom_id': self.product.uom_id.id,
                'location_id': src.id,
                'location_dest_id': dest.id,
            })],
        })
        picking.action_confirm()
        return picking

    def test_empty_outbound_order_not_sent(self):
        picking = self._picking(self.ws_loc, self.customers)   # -> 'Order'
        self.assertEqual(picking.df_object_in_webship, 'Order')
        with mock.patch.object(self.handler, 'sync_partner', return_value=[]), \
                mock.patch.object(self.handler, 'build_order_object',
                                  return_value={'errors': [], 'webshipObj': {'order_items': []}}), \
                mock.patch.object(self.handler, 'performPost') as post:
            result = self.handler._sync_picking(picking)
        self.assertEqual(result, [])
        post.assert_not_called()
        self.assertIn('All products excluded, so nothing sent to Stoqflow',
                      self.handler._sync_warnings)

    def test_empty_purchase_order_not_sent(self):
        picking = self._picking(self.suppliers, self.ws_loc)   # -> 'Purchase order'
        self.assertEqual(picking.df_object_in_webship, 'Purchase order')
        with mock.patch.object(self.handler, 'build_po_object',
                               return_value={'errors': [], 'webshipObj': {'order_items': []}}), \
                mock.patch.object(self.handler, 'performPost') as post:
            result = self.handler._sync_picking(picking)
        self.assertEqual(result, [])
        post.assert_not_called()
        self.assertIn('All products excluded, so nothing sent to Stoqflow',
                      self.handler._sync_warnings)
