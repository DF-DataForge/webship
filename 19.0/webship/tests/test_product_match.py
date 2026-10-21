# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestProductMatch(TransactionCase):
    """Scenario 5: match_product links by SKU, and never crashes when the
    SKU lookup reports more than one match (guarded even though SKUs are
    expected to be unique in Stoqflow)."""

    def setUp(self):
        super().setUp()
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1',
        })

    def test_single_match_links(self):
        with mock.patch.object(self.handler, 'findProductBySku', return_value={'id': 'WSX'}):
            result = self.handler.match_product(self.product)
        self.assertEqual(result, [])
        self.assertEqual(self.product.df_product_id_webship, 'WSX')

    def test_no_match_reports_not_found(self):
        with mock.patch.object(self.handler, 'findProductBySku', return_value=[]):
            result = self.handler.match_product(self.product)
        self.assertEqual(result, ['Sku not found in Webship'])
        self.assertFalse(self.product.df_product_id_webship)

    def test_multiple_match_reports_error_without_crashing(self):
        with mock.patch.object(self.handler, 'findProductBySku',
                               return_value={'error': '3 occurences found.'}):
            result = self.handler.match_product(self.product)
        self.assertEqual(result, ['Multiple SKU found in Stoqflow'])
        self.assertFalse(self.product.df_product_id_webship)
