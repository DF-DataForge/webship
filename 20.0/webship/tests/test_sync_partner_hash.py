# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestSyncPartnerHash(TransactionCase):
    """Test the payload-hash change detection in WebShipHandler.sync_partner:
    unchanged clients must not be re-PUT to Stoqflow on every order sync."""

    def setUp(self):
        super(TestSyncPartnerHash, self).setUp()
        # Writing df_client_id_webship triggers the stored compute
        # _compute_code_client, which builds its own handler and calls
        # fetchCode over the network - patch it out for all tests.
        patcher = mock.patch.object(
            WebShipHandler, 'fetchCode', return_value='CO0000001')
        patcher.start()
        self.addCleanup(patcher.stop)

        # Handler without set_env: all env-gated config lookups are skipped,
        # so the partner needs an email to pass validation.
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

    def _sync(self, post=None, put=None, force=False):
        """Run sync_partner with performPost/performPut mocked, returning
        (result, post_mock, put_mock)."""
        post = post or {'status': 'success', 'data': {'_id': 'abc123'}}
        put = put or {'status': 'success', 'data': {}}
        with mock.patch.object(self.handler, 'performPost', return_value=post) as post_mock, \
                mock.patch.object(self.handler, 'performPut', return_value=put) as put_mock:
            result = self.handler.sync_partner(self.partner, force=force)
        return result, post_mock, put_mock

    def test_new_client_posts_and_stores_hash(self):
        result, post_mock, put_mock = self._sync()

        self.assertEqual(result, [])
        post_mock.assert_called_once()
        put_mock.assert_not_called()
        self.assertEqual(self.partner.df_client_id_webship, 'abc123')
        self.assertTrue(self.partner.df_webship_payload_hash)
        self.assertTrue(self.partner.df_last_webship_sync)

    def test_unchanged_payload_skips_put(self):
        self.partner.df_client_id_webship = 'abc123'

        # First sync: no baseline hash yet, so the PUT happens.
        result, post_mock, put_mock = self._sync()
        self.assertEqual(result, [])
        post_mock.assert_not_called()
        put_mock.assert_called_once()
        self.assertTrue(self.partner.df_webship_payload_hash)

        # Second sync with identical data: PUT must be skipped.
        result, post_mock, put_mock = self._sync()
        self.assertEqual(result, [])
        put_mock.assert_not_called()

    def test_changed_payload_puts_and_updates_hash(self):
        self.partner.df_client_id_webship = 'abc123'
        self._sync()
        baseline_hash = self.partner.df_webship_payload_hash

        self.partner.phone = '+32 9 765 43 21'
        result, post_mock, put_mock = self._sync()

        self.assertEqual(result, [])
        put_mock.assert_called_once()
        self.assertNotEqual(self.partner.df_webship_payload_hash, baseline_hash)

    def test_failed_put_keeps_old_hash(self):
        self.partner.df_client_id_webship = 'abc123'
        self._sync()
        baseline_hash = self.partner.df_webship_payload_hash

        self.partner.phone = '+32 9 765 43 21'
        result, post_mock, put_mock = self._sync(
            put={'status': 'error', 'errorText': 'boom', 'url': 'http://test/clients/abc123'})

        self.assertTrue(result and result[0].startswith('Error:'))
        put_mock.assert_called_once()
        # Hash must stay at the old baseline so the next run retries the PUT.
        self.assertEqual(self.partner.df_webship_payload_hash, baseline_hash)

    def test_force_bypasses_hash(self):
        self.partner.df_client_id_webship = 'abc123'
        self._sync()

        # Unchanged payload, but force=True (manual sync button) must PUT.
        result, post_mock, put_mock = self._sync(force=True)

        self.assertEqual(result, [])
        put_mock.assert_called_once()
