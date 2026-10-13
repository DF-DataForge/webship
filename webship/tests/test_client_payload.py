# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestClientPayload(TransactionCase):
    """Scenario 18: creating a client must never set client_number (Stoqflow
    assigns it). Scenario 6d: a partner flagged neither client nor supplier
    reports 'Please set to client or supplier'."""

    def setUp(self):
        super().setUp()
        # Writing df_client_id_webship triggers the stored compute
        # _compute_code_client, which builds its own handler and calls
        # fetchCode over the network - patch it out for all tests.
        patcher = mock.patch.object(WebShipHandler, 'fetchCode', return_value='CO0000001')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.handler = WebShipHandler('user', 'pw', 'http://test/')
        self.partner = self.env['res.partner'].create({
            'name': 'Test Klant',
            'street': 'Teststraat 1',
            'city': 'Gent',
            'zip': '9000',
            'country_id': self.env.ref('base.be').id,
            'email': 'klant@example.com',
            'phone': '+32 9 123 45 67',
        })

    def test_create_client_never_sets_client_number(self):
        captured = {}

        def fake_post(url, payload):
            captured['url'] = url
            captured['payload'] = payload
            return {'status': 'success', 'data': {'_id': 'abc123'}}

        with mock.patch.object(self.handler, 'performPost', side_effect=fake_post) as post_mock:
            result = self.handler.sync_partner(self.partner)

        self.assertEqual(result, [])
        post_mock.assert_called_once()
        self.assertEqual(captured['url'], 'clients')
        # The create payload carries the client's data but never a
        # client_number - Stoqflow generates that itself.
        self.assertNotIn('client_number', captured['payload'])
        self.assertEqual(captured['payload'].get('name'), 'Test Klant')
        self.assertEqual(captured['payload'].get('email'), 'klant@example.com')

    def test_partner_neither_client_nor_supplier(self):
        self.partner.df_is_client_in_webship = False
        self.partner.df_is_supplier_in_webship = False
        self.partner.ws_sync_partner()
        self.assertIn('Please set to client or supplier',
                      self.partner.df_partner_syncresult_webship or '')
