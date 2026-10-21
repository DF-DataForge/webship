# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler


class TestProductSync(TransactionCase):
    """Scenario 4d: a template with multiple variants cannot be synced.
    Scenario 4c: products flagged 'Never send this product to Stoqflow' are
    excluded from the Stoqflow SKU lookup. Scenario 24a/17b: SKUs containing
    spaces or special characters are URL-encoded in the products query."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            p = mock.patch.object(target, attr, return_value='X')
            p.start()
            self.addCleanup(p.stop)

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    # --- 4d: multiple variants -------------------------------------------

    def test_multiple_variants_cannot_sync(self):
        attribute = self.env['product.attribute'].create({'name': 'Color'})
        vals = self.env['product.attribute.value'].create([
            {'name': 'Red', 'attribute_id': attribute.id},
            {'name': 'Blue', 'attribute_id': attribute.id},
        ])
        template = self.env['product.template'].create({
            'name': 'Multi Variant',
            'attribute_line_ids': [(0, 0, {
                'attribute_id': attribute.id,
                'value_ids': [(6, 0, vals.ids)],
            })],
        })
        self.assertEqual(len(template.product_variant_ids), 2)
        with self.assertRaises(UserError):
            template.ws_sync_product()

    def test_single_variant_delegates(self):
        # A one-variant template delegates to its variant without raising.
        template = self.env['product.template'].create({
            'name': 'Single', 'default_code': 'SKU-ONE',
        })
        self.assertEqual(len(template.product_variant_ids), 1)
        with mock.patch.object(type(template.product_variant_ids),
                               'ws_sync_product') as variant_sync:
            template.ws_sync_product()
        variant_sync.assert_called_once()

    # --- 4c / 24a: SKU lookup exclusion and encoding ----------------------

    def _picking(self, products_qty):
        moves = [(0, 0, {
            'product_id': p.id, 'product_uom_qty': q, 'product_uom': p.uom_id.id,
            'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
        }) for p, q in products_qty]
        return self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            'move_ids': moves,
        })

    def test_never_send_product_excluded_from_sku_lookup(self):
        keep = self.env['product.product'].create({'name': 'Keep', 'default_code': 'KEEP'})
        skip = self.env['product.product'].create({
            'name': 'Skip', 'default_code': 'SKIP',
            'df_product_do_not_send_webship': True,
        })
        picking = self._picking([(keep, 1), (skip, 1)])

        captured = {}

        def fake_fetch_all(path, detail, extra):
            captured['path'] = path
            return {'totalCount': 1, 'data': {1: [{'sku': 'KEEP', '_id': 'WS_KEEP'}]}}

        with mock.patch.object(self.handler, 'fetchAll', side_effect=fake_fetch_all):
            result = self.handler.findProductsBySku(picking)

        # Only the non-excluded SKU is queried; the flagged one is left out.
        self.assertIn('KEEP', captured['path'])
        self.assertNotIn('SKIP', captured['path'])
        self.assertEqual(result, {'items': {'KEEP': 'WS_KEEP'}})

    def test_sku_with_space_is_url_encoded(self):
        spaced = self.env['product.product'].create({'name': 'Spaced', 'default_code': 'SKU 1'})
        picking = self._picking([(spaced, 1)])

        captured = {}

        def fake_fetch_all(path, detail, extra):
            captured['path'] = path
            return {'totalCount': 1, 'data': {1: [{'sku': 'SKU 1', '_id': 'WS1'}]}}

        with mock.patch.object(self.handler, 'fetchAll', side_effect=fake_fetch_all):
            self.handler.findProductsBySku(picking)

        # The space must be percent-encoded, never sent as a raw space.
        self.assertIn('SKU%201', captured['path'])
        self.assertNotIn('SKU 1', captured['path'])

    # --- 4c: 'Never send' flag also blocks the manual Sync button ---------

    def test_never_send_flag_blocks_manual_sync(self):
        flagged = self.env['product.product'].create({
            'name': 'Excluded', 'default_code': 'EXCL',
            'df_product_do_not_send_webship': True,
        })
        with mock.patch.object(WebShipHandler, 'sync_product') as sync:
            flagged.ws_sync_product()
        # The product is never pushed, and the result explains why.
        sync.assert_not_called()
        self.assertIn('Never send', flagged.df_product_syncresult_webship or '')

    def test_normal_product_manual_sync_runs(self):
        normal = self.env['product.product'].create({'name': 'Normal', 'default_code': 'NORM'})
        with mock.patch.object(WebShipHandler, 'sync_product', return_value=[]) as sync:
            normal.ws_sync_product()
        sync.assert_called_once()

    def test_template_flag_mirrors_variant(self):
        # Setting the flag on the template (single variant) writes through to
        # the variant, so the template form checkbox actually excludes it.
        template = self.env['product.template'].create({'name': 'Mirror', 'default_code': 'MIR'})
        self.assertEqual(len(template.product_variant_ids), 1)
        template.df_product_do_not_send_webship = True
        self.assertTrue(template.product_variant_ids.df_product_do_not_send_webship)
