# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestFullTraceChatter(TransactionCase):
    """The 'Log full trace in picking chatter' debug setting posts a chatter
    message listing every changed picking field, and stays silent when off."""

    def setUp(self):
        super().setUp()
        self.picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })

    def _set(self, value):
        self.env['ir.config_parameter'].sudo().set_param(
            'webship.log_full_trace_chatter', value)

    def _count(self):
        return len(self.picking.message_ids)

    def test_no_message_when_disabled(self):
        self._set('False')
        before = self._count()
        self.picking.write({'df_process_code': 'E'})
        self.assertEqual(self._count(), before)

    def test_message_lists_changed_fields_when_enabled(self):
        self._set('True')
        before = self._count()
        self.picking.write({'df_process_code': 'E', 'df_picking_id_webship': 'WS9'})
        self.assertEqual(self._count(), before + 1)
        body = self.picking.message_ids[0].body
        self.assertIn('Stoqflow full trace', body)
        self.assertIn('WS9', body)

    def test_no_message_while_a_picking_is_being_created(self):
        """Creating a picking resets the Stoqflow fields and decides the process
        code; that is initialization, not a change worth tracing."""
        self._set('True')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        self.assertFalse(
            [m for m in picking.message_ids if 'Stoqflow full trace' in (m.body or '')],
            "creation posted a full-trace note: %s" % picking.message_ids.mapped('body'))
        # Tracing still works for a real write afterwards.
        picking.write({'df_picking_id_webship': 'WS9'})
        self.assertTrue(
            [m for m in picking.message_ids if 'Stoqflow full trace' in (m.body or '')])

    def test_no_message_for_empty_to_empty_change(self):
        self._set('True')
        before = self._count()
        # False -> '' on a Char field is not a readable change.
        self.picking.write({'df_picking_code_webship': ''})
        self.assertEqual(self._count(), before)

    def test_no_message_when_value_unchanged(self):
        self.picking.write({'df_picking_id_webship': 'WS9'})
        self._set('True')
        before = self._count()
        # Writing the same value must not produce a trace message.
        self.picking.write({'df_picking_id_webship': 'WS9'})
        self.assertEqual(self._count(), before)
