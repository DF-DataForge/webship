# -*- coding: utf-8 -*-
import logging
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)
EDITED = '2026-07-10T13:26:06.030Z'


class TestBackorderOnComplete(TransactionCase):
    """Scenario 15 (Stoqflow -> Odoo): a completed order with partial quantities
    creates a backorder for the remainder when 'auto create backorder' is on,
    and creates none (leaving the picking open) when it is off. Uses the native
    validation path."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(StockPicking, 'fetch_picking_code', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.param = self.env['ir.config_parameter'].sudo()
        self.param.set_str('webship.use_native_backorder', 'True')

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1', 'df_product_id_webship': 'WS1'})

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _receipt(self, demand=10):
        return self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': demand,
                'uom_id': self.product.uom_id.id,
                'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            })],
        })

    @staticmethod
    def _po(received):
        return {'status': 'completed', 'edited': EDITED,
                'order_items': [{'product_id': 'WS1', 'quantity': 10, 'received': received}]}

    def _dump(self, picking, label):
        _logger.info("TRACE[%s] picking=%s state=%s syncresult=%r",
                     label, picking.name, picking.state, picking.df_picking_syncresult_webship)
        for m in picking.move_ids:
            _logger.info("TRACE[%s]   move id=%s demand=%s quantity=%s state=%s picked=%s",
                         label, m.id, m.product_uom_qty, m.quantity, m.state, m.picked)
        for l in picking.move_line_ids:
            _logger.info("TRACE[%s]   line id=%s quantity=%s state=%s",
                         label, l.id, l.quantity, l.state)
        bo = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        _logger.info("TRACE[%s]   backorders=%s demands=%s",
                     label, bo.mapped('name'), bo.move_ids.mapped('product_uom_qty'))

    def test_backorder_created_when_enabled(self):
        # 15a: auto-backorder ON -> partial receipt (6 of 10) validates the 6
        # and creates a backorder for the remaining 4.
        self.param.set_str('webship.auto_create_backorder', 'True')
        picking = self._receipt(10)
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        self._dump(picking, '15a before')

        self.handler.setPickingQuantities(picking, self._po(6))
        self._dump(picking, '15a after')

        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertEqual(picking.state, 'done',
                         "state=%s syncresult=%r" % (picking.state, picking.df_picking_syncresult_webship))
        self.assertEqual(len(backorder), 1,
                         "n_backorders=%s names=%s" % (len(backorder), backorder.mapped('name')))
        self.assertEqual(sum(backorder.move_ids.mapped('product_uom_qty')), 4.0,
                         "backorder demands=%s" % backorder.move_ids.mapped('product_uom_qty'))

    def test_no_backorder_when_disabled(self):
        # 15b: auto-backorder OFF -> the received qty is recorded but the
        # picking is left open and NO backorder is created.
        self.param.set_str('webship.auto_create_backorder', 'False')
        picking = self._receipt(10)

        self.handler.setPickingQuantities(picking, self._po(6))
        self._dump(picking, '15b after')

        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertEqual(picking.move_ids.quantity, 6.0,
                         "move.quantity=%s (expected 6)" % picking.move_ids.quantity)
        self.assertNotEqual(picking.state, 'done', "state=%s" % picking.state)
        self.assertFalse(backorder,
                         "unexpected backorder(s): %s" % backorder.mapped('name'))


class TestMakeBackorderLegacy(TransactionCase):
    """Legacy validation path (webship.use_native_backorder off):
    make_backorder must snapshot its zero-quantity moves BEFORE the split.
    A post-split re-read of move_ids collects the freshly split moves a second
    time and, without a state filter, sweeps done/cancelled moves into the
    backorder picking."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(StockPicking, 'fetch_picking_code', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.param = self.env['ir.config_parameter'].sudo()
        self.param.set_str('webship.use_native_backorder', 'False')
        self.param.set_str('webship.auto_create_backorder', 'True')

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1', 'df_product_id_webship': 'WS1'})
        self.product2 = self.env['product.product'].create({
            'name': 'Gadget', 'default_code': 'SKU2', 'df_product_id_webship': 'WS2'})

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _receipt(self, products):
        return self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': product.id, 'product_uom_qty': demand,
                'uom_id': product.uom_id.id,
                'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            }) for product, demand in products],
        })

    def test_legacy_partial_creates_single_clean_backorder(self):
        # Partial receipt (6 of 10) through the full legacy flow: the picking
        # validates at 6 and exactly one backorder carries the remaining 4.
        picking = self._receipt([(self.product, 10)])
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True

        self.handler.setPickingQuantities(picking, {
            'status': 'completed', 'edited': EDITED,
            'order_items': [{'product_id': 'WS1', 'quantity': 10, 'received': 6}]})

        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertEqual(picking.state, 'done',
                         "state=%s syncresult=%r" % (picking.state, picking.df_picking_syncresult_webship))
        self.assertEqual(len(backorder), 1,
                         "n_backorders=%s names=%s" % (len(backorder), backorder.mapped('name')))
        self.assertEqual(sum(backorder.move_ids.mapped('product_uom_qty')), 4.0,
                         "backorder demands=%s" % backorder.move_ids.mapped('product_uom_qty'))
        self.assertTrue(all(m.state not in ('done', 'cancel') for m in backorder.move_ids),
                        "backorder move states=%s" % backorder.move_ids.mapped('state'))

    def test_cancelled_move_not_dragged_into_backorder(self):
        # A cancelled move has quantity 0 but must never be swept into the
        # backorder: before the snapshot fix the post-split quantity==0 filter
        # had no state filter and moved it to a spurious backorder picking.
        picking = self._receipt([(self.product, 10), (self.product2, 5)])
        picking.action_confirm()
        cancelled = picking.move_ids.filtered(lambda m: m.product_id == self.product2)
        cancelled._action_cancel()
        kept = picking.move_ids - cancelled
        kept.quantity = 10.0

        picking.make_backorder()

        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertFalse(backorder,
                         "unexpected backorder(s): %s with moves %s" % (
                             backorder.mapped('name'), backorder.move_ids.mapped('state')))
        self.assertEqual(cancelled.picking_id, picking,
                         "cancelled move left its picking")
        self.assertEqual(cancelled.state, 'cancel')
