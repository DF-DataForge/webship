# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler


class TestPartnerMatchBlankSequence(TransactionCase):
    """Risk 7: a blank matching sequence intentionally skips matching (so a new
    contact is created on order sync). The manual 'Match' button must NOT report
    'Success' in that case, because nothing was actually linked."""

    def setUp(self):
        super().setUp()
        # df_client_id_webship writes trigger fetchCode via a stored compute;
        # class-patch it so no real HTTP happens.
        patcher = mock.patch.object(WebShipHandler, 'fetchCode', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.param = self.env['ir.config_parameter'].sudo()
        self.partner = self.env['res.partner'].create({
            'name': 'Jan Client',
            'email': 'jan@example.com',
        })
        # Flagged as a client by default; make sure it is not a supplier.
        self.partner.df_is_client_in_webship = True
        self.partner.df_is_supplier_in_webship = False

    def test_blank_sequence_does_not_report_success(self):
        self.param.set_param('webship.contact_match_sequence', '')
        self.partner.ws_match_partner()
        result = self.partner.df_partner_syncresult_webship or ''
        self.assertNotEqual(result, 'Success')
        self.assertIn('nothing was linked', result)
        self.assertFalse(self.partner.df_client_id_webship)

    def test_actual_link_reports_success(self):
        def _fake_match(handler, partner):
            partner.df_client_id_webship = 'WSCLIENT'
            return {'errors': [], 'multiple': None, 'match_field': ''}

        with mock.patch.object(WebShipHandler, 'match_partner_by_sequence',
                               autospec=True, side_effect=_fake_match):
            self.partner.ws_match_partner()
        # df_partner_syncresult_webship is an Html field, so 'Success' comes
        # back wrapped/marked (e.g. Markup('<p>Success</p>')). Assert on content.
        result = self.partner.df_partner_syncresult_webship or ''
        self.assertIn('Success', result)
        self.assertNotIn('nothing was linked', result)
        self.assertEqual(self.partner.df_client_id_webship, 'WSCLIENT')
