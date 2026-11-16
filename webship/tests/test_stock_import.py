# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError

from odoo.addons.webship.models.ws import WebShipHandler


class TestStockImport(TransactionCase):
    """Risk 9: stock import writes each shop's stock to that shop's Webship
    location only (one Webship location per shop), and the manual apply button
    refuses to zero a quant that was never fetched."""

    def setUp(self):
        super().setUp()
        parent = self.env.ref('stock.stock_location_stock').location_id
        self.loc_a = self.env['stock.location'].create({
            'name': 'WS Shop A', 'usage': 'internal', 'location_id': parent.id,
            'df_is_webship_location': True, 'df_warehouse_id_webship': 'SHOP_A',
        })
        self.loc_b = self.env['stock.location'].create({
            'name': 'WS Shop B', 'usage': 'internal', 'location_id': parent.id,
            'df_is_webship_location': True, 'df_warehouse_id_webship': 'SHOP_B',
        })
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1', 'is_storable': True,
        })
        self.quant_a = self.env['stock.quant'].create({
            'product_id': self.product.id, 'location_id': self.loc_a.id, 'quantity': 0.0,
        })
        self.quant_b = self.env['stock.quant'].create({
            'product_id': self.product.id, 'location_id': self.loc_b.id, 'quantity': 0.0,
        })

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def test_stock_written_per_shop_location(self):
        # One inventory item per shop for the same SKU, different totals.
        inventory = {'status': 'success', 'data': {1: [
            {'sku': 'SKU1', 'type': 'basic', 'company_id': 'SHOP_A',
             'total': 10, 'reserved': 2, 'available': 8},
            {'sku': 'SKU1', 'type': 'basic', 'company_id': 'SHOP_B',
             'total': 5, 'reserved': 0, 'available': 5},
        ]}}
        with mock.patch.object(self.handler, 'fetchInventory', return_value=inventory):
            self.handler.importStock()

        # Each shop's total lands on its own location's quant - no cross-shop
        # overwrite (previously both ended up at the last-written value).
        self.assertEqual(self.quant_a.df_webship_totalstock, 10)
        self.assertEqual(self.quant_a.df_webship_available_stock, 8)
        self.assertEqual(self.quant_b.df_webship_totalstock, 5)
        self.assertEqual(self.quant_b.df_webship_available_stock, 5)

    def test_composed_products_skipped(self):
        inventory = {'status': 'success', 'data': {1: [
            {'sku': 'SKU1', 'type': 'composed', 'company_id': 'SHOP_A', 'total': 99},
        ]}}
        with mock.patch.object(self.handler, 'fetchInventory', return_value=inventory):
            self.handler.importStock()
        self.assertEqual(self.quant_a.df_webship_totalstock, 0.0)

    def test_apply_button_guards_unfetched_quant(self):
        # quant_a was never fetched (df_last_check_webship empty) -> the apply
        # button must refuse instead of zeroing real inventory.
        self.assertFalse(self.quant_a.df_last_check_webship)
        with self.assertRaises(UserError):
            self.quant_a.action_apply_webship_stock()

    def test_kit_product_skipped(self):
        # A kit (phantom BoM) product must be skipped before the quant lookup:
        # mrp forbids quants for kits, and the Stoqflow-side 'composed' check
        # does not cover a kit registered as a basic product in Stoqflow.
        if 'mrp.bom' not in self.env:
            self.skipTest('mrp is not installed')
        kit = self.env['product.product'].create({
            'name': 'Kit', 'default_code': 'KIT1', 'is_storable': True,
        })
        self.env['mrp.bom'].create({
            'product_tmpl_id': kit.product_tmpl_id.id, 'type': 'phantom',
        })
        inventory = {'status': 'success', 'data': {1: [
            {'sku': 'KIT1', 'type': 'basic', 'company_id': 'SHOP_A', 'total': 9},
            {'sku': 'SKU1', 'type': 'basic', 'company_id': 'SHOP_A',
             'total': 4, 'reserved': 0, 'available': 4},
        ]}}
        with mock.patch.object(self.handler, 'fetchInventory', return_value=inventory):
            self.handler.importStock()
        # The kit created no quant and did not abort the import: the plain
        # product after it in the same page still got its stock.
        self.assertFalse(self.env['stock.quant'].search(
            [('product_id', '=', kit.id)]))
        self.assertEqual(self.quant_a.df_webship_totalstock, 4)

    def test_one_bad_item_does_not_abort(self):
        # A failure while applying one item's stock is logged and skipped;
        # the remaining items still import.
        bad = self.env['product.product'].create({
            'name': 'Bad', 'default_code': 'BAD1', 'is_storable': True,
        })
        inventory = {'status': 'success', 'data': {1: [
            {'sku': 'BAD1', 'type': 'basic', 'company_id': 'SHOP_A', 'total': 7},
            {'sku': 'SKU1', 'type': 'basic', 'company_id': 'SHOP_A',
             'total': 4, 'reserved': 0, 'available': 4},
        ]}}
        Quant = type(self.env['stock.quant'])
        original_write = Quant.write

        def failing_write(recs, vals):
            if any(q.product_id == bad for q in recs):
                raise ValueError('boom')
            return original_write(recs, vals)

        with mock.patch.object(self.handler, 'fetchInventory', return_value=inventory), \
                mock.patch.object(Quant, 'write', failing_write):
            self.handler.importStock()
        self.assertEqual(self.quant_a.df_webship_totalstock, 4)
