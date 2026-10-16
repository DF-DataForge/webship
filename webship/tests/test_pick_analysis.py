# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase


class TestPickAnalysisProductResolution(TransactionCase):
    """_populate_pick_analysis resolves product name/SKU from Odoo first and
    only calls GET /products?subset= for Stoqflow ids Odoo cannot resolve."""

    def setUp(self):
        super().setUp()
        self.product = self.env['product.product'].create({
            'name': 'Prod One', 'default_code': 'SKU1', 'df_product_id_webship': 'WSP1',
        })
        self.picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })

    def test_all_resolved_from_odoo_no_api_call(self):
        data = {
            'picks': [{'product_id': 'WSP1', 'quantity': 2}],
            'order_items': [{'product_id': 'WSP1', 'quantity': 2}],
        }
        handler = mock.MagicMock()
        self.picking._populate_pick_analysis(data, wsHandler=handler)

        handler.performGet.assert_not_called()
        line = self.picking.df_pick_analysis_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.ws_product_sku, 'SKU1')
        self.assertEqual(line.ws_product_name, 'Prod One')
        self.assertEqual(line.odoo_product_id, self.product)

    def test_missing_product_fetched_from_stoqflow(self):
        data = {
            'picks': [{'product_id': 'WSUNKNOWN', 'quantity': 1}],
            'order_items': [{'product_id': 'WSUNKNOWN', 'quantity': 1}],
        }
        handler = mock.MagicMock()
        handler.performGet.return_value = {
            'status': 'success',
            'data': [{'_id': 'WSUNKNOWN', 'sku': 'SKUX', 'name': 'From Stoqflow'}],
        }
        self.picking._populate_pick_analysis(data, wsHandler=handler)

        handler.performGet.assert_called_once()
        # Only the unresolved id is requested.
        called_params = handler.performGet.call_args.args[1]
        self.assertIn('WSUNKNOWN', called_params)
        line = self.picking.df_pick_analysis_ids
        self.assertEqual(line.ws_product_sku, 'SKUX')
        self.assertEqual(line.ws_product_name, 'From Stoqflow')
