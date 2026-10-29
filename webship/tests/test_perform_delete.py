# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestPerformDelete(TransactionCase):
    """The targeted performDelete helper used to clean up live test data:
    it deletes exactly one record by id and is idempotent (404 = already gone),
    unlike the emptyX() helpers that wipe a whole endpoint."""

    def setUp(self):
        super().setUp()
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.sleepTime = 0  # no rate-limit delay in tests

    @staticmethod
    def _resp(code, text=''):
        return mock.Mock(status_code=code, text=text)

    def test_delete_hits_single_record_url(self):
        with mock.patch.object(self.handler.session, 'delete',
                               return_value=self._resp(200)) as d:
            res = self.handler.performDelete('clients', 'abc123')
        d.assert_called_once()
        self.assertEqual(d.call_args.args[0], 'http://test/clients/abc123')
        self.assertEqual(res['status'], 'success')

    def test_delete_404_is_idempotent_success(self):
        # An already-deleted record must not make cleanup fail.
        with mock.patch.object(self.handler.session, 'delete',
                               return_value=self._resp(404, 'not found')):
            res = self.handler.performDelete('clients', 'gone')
        self.assertEqual(res['status'], 'success')

    def test_delete_server_error_reported(self):
        with mock.patch.object(self.handler.session, 'delete',
                               return_value=self._resp(500, 'boom')):
            res = self.handler.performDelete('orders', 'x')
        self.assertEqual(res['status'], 'error')
        self.assertEqual(res['errorCode'], 500)
