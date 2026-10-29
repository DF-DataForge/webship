# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler


class TestLineComparison(TransactionCase):
    """Scenario 22: _compare_picking_to_stoqflow_order classifies each line as
    match / mismatch / missing_in_stoqflow / missing_in_odoo / unresolved, and
    honours the Ignored SKUs setting."""

    def setUp(self):
        super().setUp()
        # Writing df_picking_id_webship triggers a stored compute that would
        # otherwise call the Stoqflow API - patch it out for all tests.
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            patcher = mock.patch.object(target, attr, return_value='X')
            patcher.start()
            self.addCleanup(patcher.stop)

        # A mock handler: the comparison only needs these three methods.
        self.handler = mock.Mock()
        self.handler._get_ignored_skus.return_value = []
        self.handler.findProductBySku.return_value = {}
        self.handler.get_product_by_id.side_effect = lambda pid: {
            'WS1': {'name': 'Product One', 'sku': 'SKU1'},
            'WS2': {'name': 'Product Two', 'sku': 'SKU2'},
            'WS3': {'name': 'Stoqflow Only', 'sku': 'SKU3'},
        }.get(pid)

        self.p1 = self._product('Product One', 'SKU1', 'WS1')
        self.p2 = self._product('Product Two', 'SKU2', 'WS2')

    def _product(self, name, sku, ws_id):
        return self.env['product.product'].create({
            'name': name,
            'default_code': sku,
            'df_product_id_webship': ws_id,
        })

    def _picking(self, lines):
        """lines: list of (product, qty)."""
        stock = self.env.ref('stock.stock_location_stock')
        customers = self.env.ref('stock.stock_location_customers')
        moves = [(0, 0, {
            'product_id': p.id,
            'product_uom_qty': qty,
            'uom_id': p.uom_id.id,
            'location_id': stock.id,
            'location_dest_id': customers.id,
        }) for p, qty in lines]
        return self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': stock.id,
            'location_dest_id': customers.id,
            'move_ids': moves,
        })

    @staticmethod
    def _order(*items):
        """items: list of (ws_product_id, qty)."""
        return {
            '_id': 'ORD1',
            'order_number': 'SO-1',
            'order_items': [{'product_id': pid, 'quantity': qty} for pid, qty in items],
        }

    def _status(self, picking, order):
        result = picking._compare_picking_to_stoqflow_order(order, self.handler)
        return {line['stoqflow_product_id'] or line['sku']: line['status']
                for line in result['lines']}, result

    def test_all_match(self):
        picking = self._picking([(self.p1, 10), (self.p2, 5)])
        order = self._order(('WS1', 10), ('WS2', 5))
        statuses, result = self._status(picking, order)
        self.assertEqual(statuses, {'WS1': 'match', 'WS2': 'match'})
        self.assertFalse(result['problems'])

    def test_quantity_mismatch(self):
        picking = self._picking([(self.p1, 10)])
        order = self._order(('WS1', 8))
        statuses, result = self._status(picking, order)
        self.assertEqual(statuses['WS1'], 'mismatch')
        self.assertTrue(any('not corresponding' in p for p in result['problems']))

    def test_missing_in_stoqflow(self):
        # p2 is on the picking but not in the Stoqflow order.
        picking = self._picking([(self.p1, 10), (self.p2, 5)])
        order = self._order(('WS1', 10))
        statuses, result = self._status(picking, order)
        self.assertEqual(statuses['WS2'], 'missing_in_stoqflow')

    def test_missing_in_odoo(self):
        # WS3 is in the Stoqflow order but not on the picking.
        picking = self._picking([(self.p1, 10)])
        order = self._order(('WS1', 10), ('WS3', 4))
        statuses, result = self._status(picking, order)
        self.assertEqual(statuses['WS3'], 'missing_in_odoo')

    def test_unresolved_product(self):
        # A product with no Stoqflow id and no SKU match cannot be resolved.
        orphan = self.env['product.product'].create({'name': 'Orphan'})
        self.handler.findProductBySku.return_value = {}
        picking = self._picking([(orphan, 3)])
        order = self._order(('WS1', 10))
        statuses, result = self._status(picking, order)
        self.assertIn('unresolved', [l['status'] for l in result['lines']])

    def test_ignored_sku_excluded_from_both_sides(self):
        self.handler._get_ignored_skus.return_value = ['SKU2']
        picking = self._picking([(self.p1, 10), (self.p2, 5)])
        order = self._order(('WS1', 10), ('WS2', 5))
        statuses, result = self._status(picking, order)
        # SKU2/WS2 must not appear at all, and the rest still matches.
        self.assertNotIn('WS2', statuses)
        self.assertEqual(statuses.get('WS1'), 'match')
        self.assertFalse(result['problems'])

    def test_not_found_returns_found_false(self):
        picking = self._picking([(self.p1, 10)])
        with mock.patch.object(self.handler, 'find_stoqflow_order_for_picking', return_value=None):
            result = picking._build_stoqflow_comparison(self.handler)
        self.assertFalse(result['found'])
        self.assertTrue(result['error'])
