# -*- coding: utf-8 -*-
from unittest import mock

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.webship.models.ws import WebShipHandler


class TestStoqflowAccess(TransactionCase):
    """Access levels: every internal user reads the Stoqflow configuration,
    Inventory users are Stoqflow users (read the API history, work with
    backorders), only Stoqflow administrators change the configuration and
    delete history, and only Inventory administrators apply Stoqflow stock."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.internal = new_test_user(cls.env, login='sf_internal', groups='base.group_user')
        cls.stock_user = new_test_user(cls.env, login='sf_stock', groups='stock.group_stock_user')
        cls.admin = new_test_user(cls.env, login='sf_admin', groups='base.group_system,stock.group_stock_manager')
        cls.brand = cls.env['webship.brand'].create({'brand_id': 'B1', 'name': 'Brand'})
        cls.history = cls.env['webship.json.history'].sudo().create({'direction': 'sent'})

    def test_groups_follow_inventory_and_settings_rights(self):
        self.assertFalse(self.internal.has_group('webship.group_webship_user'))
        self.assertTrue(self.stock_user.has_group('webship.group_webship_user'))
        self.assertFalse(self.stock_user.has_group('webship.group_webship_manager'))
        self.assertTrue(self.admin.has_group('webship.group_webship_manager'))

    def test_configuration_read_only_for_users(self):
        for user in (self.internal, self.stock_user):
            brand = self.brand.with_user(user)
            self.assertEqual(brand.name, 'Brand')
            with self.assertRaises(AccessError):
                brand.write({'name': 'Changed'})
        self.brand.with_user(self.admin).write({'name': 'Changed'})

    def test_api_history_for_stoqflow_users_only(self):
        with self.assertRaises(AccessError):
            self.history.with_user(self.internal).read(['id'])
        self.history.with_user(self.stock_user).read(['id'])
        with self.assertRaises(AccessError):
            self.history.with_user(self.stock_user).unlink()
        self.history.with_user(self.admin).unlink()

    def test_apply_stock_needs_inventory_administrator(self):
        quant = self.env['stock.quant'].search([], limit=1) or self.env['stock.quant']
        with self.assertRaises(UserError):
            quant.with_user(self.stock_user).action_apply_webship_stock()


class TestStoqflowLinkEscaping(TransactionCase):
    """The Stoqflow link fields are not sanitized, so the codes in them must be
    escaped: an internal reference must not become live HTML for other users."""

    def test_product_code_is_escaped(self):
        product = self.env['product.product'].create({
            'name': 'P', 'default_code': '<img src=x onerror=alert(1)>',
            'df_product_id_webship': 'WS1',
        })
        self.assertNotIn('<img src=x', str(product.df_url_prod))
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', str(product.df_url_prod))
        self.assertIn('<a href="', str(product.df_url_prod))

    def test_partner_codes_are_escaped(self):
        # The code is fetched from Stoqflow, i.e. external input.
        with mock.patch.object(WebShipHandler, 'fetchCode', return_value='<script>x</script>'):
            partner = self.env['res.partner'].create({
                'name': 'C', 'df_supplier_id_webship': 'S1', 'df_client_id_webship': 'C1'})
            for html in (partner.df_url_supplier, partner.df_url_client):
                self.assertNotIn('<script>', str(html))
                self.assertIn('&lt;script&gt;x&lt;/script&gt;', str(html))


@tagged('post_install', '-at_install')
class TestStoqflowExportRoutes(HttpCase):
    """The XLSX exports read Stoqflow data with the company's API login and all
    Odoo contacts with sudo: portal/webshop customers and ordinary internal
    users get 403, before any Stoqflow call is made."""

    def test_exports_refused_without_stoqflow_admin(self):
        new_test_user(self.env, login='sf_portal', groups='base.group_portal')
        new_test_user(self.env, login='sf_internal2', groups='base.group_user')
        for login in ('sf_portal', 'sf_internal2'):
            self.authenticate(login, login)
            for url in ('/web/download/excel?p=partner',
                        '/custom/xlsx/download_ws_prod_vergelijk',
                        '/custom/xlsx/download_xlsx_config_report'):
                response = self.url_open(url)
                self.assertEqual(response.status_code, 403, '%s as %s' % (url, login))
