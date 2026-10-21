# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking


class TestManualNoIdBlank(TransactionCase):
    """A Manual ('M') picking is deliberately never pushed to Stoqflow, so
    having no Stoqflow order/PO id is its normal state. fetchQuantities must
    leave the sync result blank for those - and clear a message an earlier run
    left there - while still reporting the missing id on pickings that are
    supposed to be in Stoqflow."""

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
            'df_picking_syncresult_webship':
                'No Stoqflow order ID or PO ID set on this picking',
        })
        self._fetch()
        self.assertFalse(self.picking.df_picking_syncresult_webship)

    def test_non_manual_picking_still_reports_missing_id(self):
        self.picking.df_process_code = 'P'
        self._fetch()
        self.assertIn(
            'No Stoqflow order ID or PO ID set on this picking',
            self.picking.df_picking_syncresult_webship)
