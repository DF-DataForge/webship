# -*- coding: utf-8 -*-
from unittest import mock

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking


class TestSetTestError(TransactionCase):
    """The neutralized-DB-only testing action must put a picking into the
    expected error state, and must hard-refuse on a non-neutralized database."""

    def setUp(self):
        super().setUp()
        # Writing df_picking_id_webship arms the stored compute of
        # df_picking_code_webship, which fetches the code via the API
        # handler on the next flush - mock it like the other test files.
        patcher = mock.patch.object(StockPicking, 'fetch_picking_code', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.customers = self.env.ref('stock.stock_location_customers')
        self.stock = self.env.ref('stock.stock_location_stock')
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1',
        })
        self.picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.stock.id,
            'location_dest_id': self.customers.id,
            'df_sync_retry_count': 3,
        })
        # Set AFTER create: the module's create() override deliberately
        # resets every Stoqflow field on new pickings, so an id passed in
        # the create vals would be wiped immediately.
        self.picking.df_picking_id_webship = 'OLD1'

    def _set_neutralized(self, value):
        self.env['ir.config_parameter'].sudo().set_param(
            'database.is_neutralized', value)

    def test_unique_error_state_on_neutralized_db(self):
        self._set_neutralized('true')
        self.picking._webship_test_set_error_state('unique')
        self.assertEqual(self.picking.df_process_code, 'E')
        self.assertFalse(self.picking.df_picking_id_webship)
        self.assertFalse(self.picking.df_po_id_webship)
        self.assertEqual(self.picking.df_sync_retry_count, 0)
        self.assertIn('reference must be unique',
                      self.picking.df_picking_syncresult_webship)

    def test_no_id_error_state_on_neutralized_db(self):
        self._set_neutralized('true')
        self.picking._webship_test_set_error_state('no_id')
        self.assertEqual(self.picking.df_process_code, 'E')
        self.assertFalse(self.picking.df_picking_id_webship)
        self.assertEqual(self.picking.df_sync_retry_count, 0)
        # Html field: a plain-text write is sanitized into wrapped Markup
        # (<span>...</span> on Odoo 19), so compare content, not equality.
        self.assertIn('No Stoqflow order ID or PO ID set on this picking',
                      self.picking.df_picking_syncresult_webship)

    def test_refuses_on_non_neutralized_db(self):
        self._set_neutralized('false')
        with self.assertRaises(UserError):
            self.picking._webship_test_set_error_state('unique')
        # The picking is left untouched.
        self.assertEqual(self.picking.df_picking_id_webship, 'OLD1')

    def test_neutralized_flag_and_open_action(self):
        self._set_neutralized('true')
        self.picking.invalidate_recordset(['df_is_neutralized'])
        self.assertTrue(self.picking.df_is_neutralized)
        action = self.picking.action_open_test_set_error()
        self.assertEqual(action['res_model'], 'webship.test.set.error')
        self.assertEqual(action['context']['active_ids'], self.picking.ids)

    def test_open_action_refuses_on_non_neutralized_db(self):
        self._set_neutralized('false')
        self.picking.invalidate_recordset(['df_is_neutralized'])
        self.assertFalse(self.picking.df_is_neutralized)
        with self.assertRaises(UserError):
            self.picking.action_open_test_set_error()

    def test_clear_fields_resets_to_fresh(self):
        self._set_neutralized('true')
        self.picking.write({
            'df_po_id_webship': 'PO1',
            'df_status_webship': 'completed',
            'df_process_code': 'F',
            'df_picking_syncresult_webship': 'something',
            'df_sync_retry_count': 4,
        })
        self.picking.action_webship_test_clear_fields()
        self.assertFalse(self.picking.df_picking_id_webship)
        self.assertFalse(self.picking.df_po_id_webship)
        self.assertFalse(self.picking.df_status_webship)
        self.assertEqual(self.picking.df_process_code, 'P')
        self.assertEqual(self.picking.df_sync_retry_count, 0)
        self.assertFalse(self.picking.df_picking_syncresult_webship)

    def test_clear_fields_refuses_on_non_neutralized_db(self):
        self._set_neutralized('false')
        with self.assertRaises(UserError):
            self.picking.action_webship_test_clear_fields()
        self.assertEqual(self.picking.df_picking_id_webship, 'OLD1')

    def test_wizard_applies_to_active_ids(self):
        self._set_neutralized('true')
        wizard = self.env['webship.test.set.error'].with_context(
            active_ids=[self.picking.id]).create({'error_type': 'no_id'})
        wizard.action_apply()
        self.assertEqual(self.picking.df_process_code, 'E')
        # Html field: compare content, not equality (see above).
        self.assertIn('No Stoqflow order ID or PO ID set on this picking',
                      self.picking.df_picking_syncresult_webship)
