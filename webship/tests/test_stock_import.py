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

    def _import(self, items):
        inventory = {'status': 'success', 'data': {1: items}}
        with mock.patch.object(self.handler, 'fetchInventory', return_value=inventory):
            return self.handler.importStock()

    def test_no_guess_between_several_locations(self):
        # An unknown Stoqflow company with several Stoqflow locations must not
        # be written to an arbitrary one (it used to land in the first location,
        # possibly of another company): nothing is written and it is reported.
        summary = self._import([{'sku': 'SKU1', 'type': 'basic', 'company_id': 'OTHER',
                                 'total': 6, 'reserved': 0, 'available': 6}])
        self.assertEqual(summary['unmatched_companies'], {'OTHER'})
        self.assertEqual(summary['updated'], 0)
        self.assertFalse((self.quant_a | self.quant_b).filtered('df_last_check_webship'))

    def test_single_location_used_without_company_link(self):
        # With one Stoqflow location there is nothing to choose: it is used
        # even when the company id is not linked to it.
        self.loc_b.df_is_webship_location = False
        self.loc_a.df_warehouse_id_webship = False
        summary = self._import([{'sku': 'SKU1', 'type': 'basic', 'company_id': 'OTHER',
                                 'total': 6, 'reserved': 1, 'available': 5}])
        self.assertEqual(summary['updated'], 1)
        self.assertEqual(self.quant_a.df_webship_totalstock, 6)
        self.assertEqual(self.quant_a.df_webship_diff_total, -6)

    def test_no_quant_created_for_zero_stock(self):
        other = self.env['product.product'].create({
            'name': 'Empty', 'default_code': 'SKU0', 'is_storable': True})
        summary = self._import([
            {'sku': 'SKU0', 'type': 'basic', 'company_id': 'SHOP_A', 'total': 0},
            {'sku': 'NOPE', 'type': 'basic', 'company_id': 'SHOP_A', 'total': 3},
        ])
        self.assertFalse(self.env['stock.quant'].search([('product_id', '=', other.id)]))
        self.assertEqual(summary['unknown_skus'], ['NOPE'])
        self.assertTrue(summary['missing_reserved'])

    def test_lots_share_product_total_and_are_not_adjusted(self):
        # Two lots of one product at the location: each row shows the product
        # total from Stoqflow, the difference compares it with the sum of both
        # lots, and neither the automatic adjustment nor the button sets every
        # lot to the product total (that would double the stock).
        product = self.env['product.product'].create({
            'name': 'Lotted', 'default_code': 'LOT1', 'is_storable': True, 'tracking': 'lot'})
        Lot = self.env['stock.lot']
        Quant = self.env['stock.quant']
        for name, qty in (('L1', 25), ('L2', 25)):
            lot = Lot.create({'name': name, 'product_id': product.id})
            Quant._update_available_quantity(product, self.loc_a, qty, lot_id=lot)
        self.env['ir.config_parameter'].sudo().set_str('webship.adjust_odoo_stock', 'True')

        summary = self._import([{'sku': 'LOT1', 'type': 'basic', 'company_id': 'SHOP_A',
                                 'total': 25, 'reserved': 0, 'available': 25}])

        quants = Quant.search([('product_id', '=', product.id), ('location_id', '=', self.loc_a.id)])
        self.assertEqual(len(quants), 2)
        self.assertEqual(summary['multi_quant_skus'], ['LOT1'])
        self.assertEqual(summary['adjusted'], 0)
        self.assertEqual(quants.mapped('quantity'), [25, 25])
        self.assertEqual(quants.mapped('df_webship_totalstock'), [25, 25])
        self.assertEqual(quants.mapped('df_webship_diff_total'), [25, 25])
        with self.assertRaises(UserError):
            quants[0].action_apply_webship_stock()

    def test_unchecked_quant_has_no_difference(self):
        Quant = self.env['stock.quant']
        Quant._update_available_quantity(self.product, self.loc_a, 7)
        self.assertFalse(self.quant_a.df_last_check_webship)
        self.assertEqual(self.quant_a.df_webship_diff_total, 0)
