# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestQueryEncoding(TransactionCase):
    """Risk 24a / 7: the client & supplier match lookups must URL-encode the
    vat/email query params, just like the SKU paths. A '+' in an email (decoded
    server-side as a space) or a space/'&'/'#' in a vat must be percent-encoded
    so the query stays well-formed and matches the right record."""

    def setUp(self):
        super().setUp()
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)
        self.handler.sleepTime = 0
        # Class-patch fetchCode so any incidental df_*_id_webship write does not
        # fire a real HTTP call.
        patcher = mock.patch.object(WebShipHandler, 'fetchCode', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.partner = self.env['res.partner'].create({
            'name': 'Jan Client',
            'email': 'jan+tag@example.com',
            'vat': 'BE 0123 456',
        })

    def _mock_get(self):
        """Patch the session GET to a 200/empty-list response and return the
        mock so the caller can inspect the URL that was built."""
        resp = mock.Mock()
        resp.status_code = 200
        resp.text = '[]'
        resp.json.return_value = []
        resp.headers = {'total-count': '0'}
        get = mock.Mock(return_value=resp)
        self.handler.session.get = get
        return get

    def _called_url(self, get):
        # performGet / findClientByVat call session.get(url, timeout=...)
        return get.call_args.args[0]

    def test_client_email_is_encoded(self):
        get = self._mock_get()
        self.handler._match_client_by_email(self.partner)
        url = self._called_url(get)
        self.assertIn('%2B', url, "'+' must be percent-encoded")
        self.assertIn('%40', url, "'@' must be percent-encoded")
        self.assertNotIn('jan+tag@example.com', url, "raw email must not appear")

    def test_client_vat_is_encoded(self):
        get = self._mock_get()
        self.handler._match_client_by_vat(self.partner)
        url = self._called_url(get)
        self.assertIn('%20', url, "spaces in the vat must be percent-encoded")
        self.assertNotIn('BE 0123 456', url, "raw vat with spaces must not appear")

    def test_supplier_email_is_encoded(self):
        get = self._mock_get()
        self.handler._match_supplier_by_email(self.partner)
        url = self._called_url(get)
        self.assertIn('%2B', url)
        self.assertNotIn('jan+tag@example.com', url)

    def test_supplier_vat_is_encoded(self):
        get = self._mock_get()
        self.handler._match_supplier_by_vat(self.partner)
        url = self._called_url(get)
        self.assertIn('%20', url)
        self.assertNotIn('BE 0123 456', url)

    def test_find_client_by_vat_is_encoded(self):
        resp = mock.Mock()
        resp.status_code = 200
        resp.text = '[]'
        resp.json.return_value = []
        resp.headers = {'total-count': None}
        get = mock.Mock(return_value=resp)
        self.handler.session.get = get
        self.handler.findClientByVat('BE 0123 456')
        url = self._called_url(get)
        self.assertIn('%20', url)
        self.assertNotIn('BE 0123 456', url)
