# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestDropInvalidEmail(TransactionCase):
    """The 'Drop e-mail when not valid' setting omits an invalid e-mail from
    the payload sent to Stoqflow instead of letting the sync fail."""

    def setUp(self):
        super().setUp()
        self.param = self.env['ir.config_parameter'].sudo()
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def test_valid_email_always_kept(self):
        for setting in ('True', 'False'):
            self.param.set_param('webship.drop_invalid_email', setting)
            self.assertEqual(self.handler._clean_email('a@b.com'), 'a@b.com')

    def test_invalid_email_kept_when_setting_off(self):
        self.param.set_param('webship.drop_invalid_email', 'False')
        self.assertEqual(self.handler._clean_email('Jan met de pet'), 'Jan met de pet')

    def test_invalid_email_dropped_when_setting_on(self):
        self.param.set_param('webship.drop_invalid_email', 'True')
        self.assertFalse(self.handler._clean_email('Jan met de pet'))

    def test_empty_email_passthrough(self):
        self.param.set_param('webship.drop_invalid_email', 'True')
        self.assertEqual(self.handler._clean_email(False), False)
        self.assertEqual(self.handler._clean_email(''), '')
