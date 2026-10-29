# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestSyncPartnerDelivery(TransactionCase):
    """Risk 6: sync_partner must not crash when a contact has several delivery
    addresses. The shipping address is the one defined on the picking
    (delivery_partner); the manual path falls back to a single delivery child."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(WebShipHandler, 'fetchCode', return_value='CO1')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

        be = self.env.ref('base.be')
        self.company = self.env['res.partner'].create({
            'name': 'ACME NV', 'is_company': True,
            'street': 'Hoofdstraat 1', 'city': 'Gent', 'zip': '9000',
            'country_id': be.id, 'email': 'acme@example.com',
        })
        # Two delivery-address children — the case that used to crash.
        for i in (1, 2):
            self.env['res.partner'].create({
                'name': 'Delivery %s' % i, 'type': 'delivery', 'parent_id': self.company.id,
                'street': 'Kaai %s' % i, 'city': 'Antwerpen', 'zip': '2000', 'country_id': be.id,
            })

    def _sync(self, **kw):
        with mock.patch.object(self.handler, 'performPost',
                               return_value={'status': 'success', 'data': {'_id': 'C1'}}) as post, \
                mock.patch.object(self.handler, 'performPut',
                                  return_value={'status': 'success', 'data': {}}):
            result = self.handler.sync_partner(self.company, **kw)
        return result, post

    def test_multiple_delivery_children_does_not_crash(self):
        # Manual path (no picking): must pick a single child, never raise.
        result, post = self._sync()
        self.assertEqual(result, [])
        post.assert_called_once()
        sJson = post.call_args.args[1]
        # A shipping block is included, built from one of the delivery children.
        self.assertIn('shipping', sJson['addresses'])
        self.assertEqual(sJson['addresses']['shipping']['city'], 'Antwerpen')

    def test_picking_delivery_address_used_no_duplicate_shipping(self):
        # Order path: delivery address IS the picking partner -> no separate
        # shipping block (it would only duplicate billing), and no crash.
        result, post = self._sync(delivery_partner=self.company)
        self.assertEqual(result, [])
        post.assert_called_once()
        sJson = post.call_args.args[1]
        self.assertNotIn('shipping', sJson['addresses'])
        self.assertEqual(sJson['addresses']['billing']['city'], 'Gent')
