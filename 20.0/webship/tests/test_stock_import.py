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
