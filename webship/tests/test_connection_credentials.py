# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestConnectionCredentials(TransactionCase):
    """Risk 14b / 14a: 'Test connection' must reject empty/whitespace
    credentials with a clean danger notification (not fall through to a real
    request with a blank URL), and WebShipHandler.test() must turn any request
    error into a danger tuple instead of a raw traceback."""

    def _settings(self, login, password, url):
        return self.env['res.config.settings'].create({
            'webship_login': login,
            'webship_password': password,
            'webship_url': url,
        })

    def test_empty_credentials_return_danger(self):
        res = self._settings('', 'secret', 'http://api/').ws_test_verbinding()
        self.assertEqual(res['params']['type'], 'danger')

    def test_valid_credentials_reach_test_call(self):
        # With all three filled the guard passes and test() is invoked; patch it
        # so the notification reflects the (mocked) success without real HTTP.
        with mock.patch.object(WebShipHandler, 'test', return_value=('success', 'ok')):
            res = self._settings('user', 'secret', 'http://api/').ws_test_verbinding()
        self.assertEqual(res['params']['type'], 'success')

    def test_test_handles_request_exception(self):
        # A blank/malformed base URL makes requests raise; test() must catch it
        # and return a danger tuple rather than propagating the exception.
        handler = WebShipHandler('u', 'p', '')
        status, message = handler.test()
        self.assertEqual(status, 'danger')
        self.assertTrue(message)
