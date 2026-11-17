# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestPackagingBarcodes(TransactionCase):
    """A product's packagings with a barcode (Sales tab > Packagings >
    Barcodes) go to Stoqflow as extra barcodes: named after the packaging,
    with the number of units as multiplier (1 scan = that many units)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['webship.brand'].create({'brand_id': 'B1', 'name': 'Brand'})
        unit = cls.env.ref('uom.product_uom_unit')
        Uom = cls.env['uom.uom']
        cls.pack50 = Uom.create({'name': 'Pack of 50', 'relative_factor': 50, 'relative_uom_id': unit.id})
        cls.pack250 = Uom.create({'name': 'Pack of 250', 'relative_factor': 250, 'relative_uom_id': unit.id})
        cls.half = Uom.create({'name': 'Half unit', 'relative_factor': 0.5, 'relative_uom_id': unit.id})
        cls.product = cls.env['product.product'].create({
            'name': 'Anti-static brush', 'default_code': 'VTBR3', 'barcode': '5410329000001',
        })
        cls.env['product.uom'].create([
            {'product_id': cls.product.id, 'uom_id': cls.pack50.id, 'barcode': '15410329000008'},
            {'product_id': cls.product.id, 'uom_id': cls.pack250.id, 'barcode': '25410329000005'},
        ])

    def setUp(self):
        super().setUp()
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _sent(self, product):
        with mock.patch.object(WebShipHandler, 'findProductBySku', return_value={}), \
                mock.patch.object(WebShipHandler, 'performPost',
                                  return_value={'status': 'success', 'data': {'_id': 'WS1'}}) as post:
            self.assertEqual(self.handler.sync_product(product), [])
        return post.call_args.args[1]

    def test_packagings_sent_as_named_barcodes_with_multiplier(self):
        barcodes = self._sent(self.product)['barcodes']
        self.assertEqual(barcodes, [
            {'type': 'ean13', 'code': '5410329000001', 'main': True},
            {'type': 'itf14', 'code': '15410329000008', 'main': False, 'name': 'Pack of 50', 'multiplier': 50},
            {'type': 'itf14', 'code': '25410329000005', 'main': False, 'name': 'Pack of 250', 'multiplier': 250},
        ])

    def test_packaging_without_whole_units_is_left_out(self):
        self.env['product.uom'].create(
            {'product_id': self.product.id, 'uom_id': self.half.id, 'barcode': 'HALF-1'})
        codes = [b['code'] for b in self._sent(self.product)['barcodes']]
        self.assertNotIn('HALF-1', codes)
        self.assertEqual(len(codes), 3)

    def test_product_without_own_barcode_still_sends_packagings(self):
        product = self.env['product.product'].create({'name': 'No barcode', 'default_code': 'NOBC'})
        self.env['product.uom'].create(
            {'product_id': product.id, 'uom_id': self.pack50.id, 'barcode': 'BOX-50'})
        self.assertEqual(self._sent(product)['barcodes'], [
            {'type': 'code128', 'code': 'BOX-50', 'main': False, 'name': 'Pack of 50', 'multiplier': 50},
        ])

    def test_product_without_any_barcode_sends_none(self):
        product = self.env['product.product'].create({'name': 'Plain', 'default_code': 'PLAIN'})
        self.assertNotIn('barcodes', self._sent(product))
