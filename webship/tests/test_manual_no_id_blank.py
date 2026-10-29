# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking


NO_ID = 'No Stoqflow order ID or PO ID set on this picking'


class TestManualNoIdBlank(TransactionCase):
    """Having no Stoqflow order/PO id is only worth reporting on a picking
    that was actually sent to Stoqflow ('F') and lost its id. A Manual ('M')
    picking is deliberately never pushed, a Pending ('P') one is still queued
    for the push cron, and an Error ('E') one carries the real failure text.
    fetchQuantities must leave the sync result blank for those - and clear the
    placeholder an earlier run left there - while still reporting the missing
    id on a sent picking."""

    def setUp(self):
        super().setUp()
        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1',
        })
        # An inbound receipt, like the WS/IN purchase orders that showed the
        # message in the Stoqflow orders list.
        self.picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id,
            'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'uom_id': self.product.uom_id.id,
                'location_id': self.suppliers.id,
                'location_dest_id': self.ws_loc.id,
            })],
        })

    def _fetch(self):
        with mock.patch.object(StockPicking, 'getHandler',
                               return_value=mock.MagicMock()):
            self.picking.fetchQuantities()

    def test_manual_picking_keeps_result_blank(self):
        self.picking.df_process_code = 'M'
        self._fetch()
        self.assertFalse(self.picking.df_picking_syncresult_webship)

    def test_manual_picking_clears_previous_message(self):
        self.picking.write({
            'df_process_code': 'M',
            'df_picking_syncresult_webship': NO_ID,
        })
        self._fetch()
        self.assertFalse(self.picking.df_picking_syncresult_webship)

    def test_pending_picking_keeps_result_blank(self):
        # Not pushed yet: the push cron will give it an id later, so the
        # status cron must not flag the missing id in the meantime.
        self.picking.df_process_code = 'P'
        self._fetch()
        self.assertFalse(self.picking.df_picking_syncresult_webship)

    def test_pending_picking_clears_previous_placeholder(self):
        self.picking.write({
            'df_process_code': 'P',
            # Stored as the Html field wraps it.
            'df_picking_syncresult_webship': '<p>%s</p>' % NO_ID,
        })
        self._fetch()
        self.assertFalse(self.picking.df_picking_syncresult_webship)

    def test_not_applicable_picking_keeps_result_blank(self):
        self.picking.df_process_code = 'NA'
        self._fetch()
        self.assertFalse(self.picking.df_picking_syncresult_webship)

    def test_sent_picking_reports_missing_id(self):
        # Sent to Stoqflow but the id is gone: a real inconsistency.
        self.picking.df_process_code = 'F'
        self._fetch()
        # df_picking_syncresult_webship is an Html field: a plain-text write
        # comes back wrapped as Markup('<p>...</p>'), so compare content.
        self.assertIn(NO_ID, str(self.picking.df_picking_syncresult_webship or ''))

    def test_sent_picking_keeps_existing_message(self):
        self.picking.write({
            'df_process_code': 'F',
            'df_picking_syncresult_webship': 'Linked to Stoqflow backorder',
        })
        self._fetch()
        result = str(self.picking.df_picking_syncresult_webship or '')
        self.assertIn('Linked to Stoqflow backorder', result)
        self.assertNotIn('No Stoqflow order ID', result)

    def test_errored_picking_keeps_real_error_text(self):
        # An 'E' picking carries the real push-failure detail in its sync
        # result; the status cron's generic "no Stoqflow id" placeholder must
        # never overwrite it before anyone has read it.
        self.picking.write({
            'df_process_code': 'E',
            'df_picking_syncresult_webship': 'Not all items are in stock',
        })
        self._fetch()
        result = str(self.picking.df_picking_syncresult_webship or '')
        self.assertIn('Not all items are in stock', result)
        self.assertNotIn('No Stoqflow order ID', result)
