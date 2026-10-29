# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler


class TestSyncGates(TransactionCase):
    """Scenario 3e/3f: pickings in draft or cancelled state must not be synced
    ('Draft or cancelled orders cannot by synced'); pickings in done state must
    not be synced either ('Done pickings cannot be synced'). The state gate is
    the very first check in _sync_picking, before any Stoqflow call - so these
    tests never hit the network."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(StockPicking, 'fetch_picking_code', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1', 'df_product_id_webship': 'WS1',
        })

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _receipt(self, qty=1):
        # Inbound receipt so a full-quantity validation reaches 'done' without
        # needing on-hand stock (supplier locations have infinite availability).
        return self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id,
            'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': qty,
                'product_uom': self.product.uom_id.id,
                'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            })],
        })

    def test_draft_picking_not_synced(self):
        picking = self._receipt()
        self.assertEqual(picking.state, 'draft')
        self.assertEqual(self.handler._sync_picking(picking),
                         ['Draft or cancelled orders cannot by synced'])

    def test_cancelled_picking_not_synced(self):
        picking = self._receipt()
        picking.action_cancel()
        self.assertEqual(picking.state, 'cancel')
        self.assertEqual(self.handler._sync_picking(picking),
                         ['Draft or cancelled orders cannot by synced'])

    def test_done_picking_not_synced(self):
        picking = self._receipt()
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 1
        picking.move_ids.picked = True
        # Manual validation of a sync-owned ('P') picking is refused; mark it
        # Manual so this fixture can validate it by hand.
        picking.df_process_code = 'M'
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(self.handler._sync_picking(picking),
                         ['Done pickings cannot be synced'])
