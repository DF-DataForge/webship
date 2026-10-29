# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler

EDITED = '2026-07-10T13:26:06.030Z'


class TestManualValidationGuard(TransactionCase):
    """button_validate refuses MANUAL validation of transfers the Stoqflow
    sync owns ('P' waiting to be pushed, 'F' pushed/being picked): validating
    those by hand makes Odoo and Stoqflow diverge. 'M', 'E', 'C' and 'NA'
    stay validatable, and the sync itself goes through _webship_validate()."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            p = mock.patch.object(target, attr, return_value='X')
            p.start()
            self.addCleanup(p.stop)

        self.param = self.env['ir.config_parameter'].sudo()
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

    def _ready_receipt(self, demand=1):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': demand,
                'uom_id': self.product.uom_id.id,
                'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = demand
        picking.move_ids.picked = True
        return picking

    def test_pushed_picking_refuses_manual_validation(self):
        picking = self._ready_receipt()
        picking.df_process_code = 'F'
        with self.assertRaises(UserError) as err:
            picking.button_validate()
        self.assertIn('F', str(err.exception))
        self.assertIn('Manual', str(err.exception))
        self.assertNotEqual(picking.state, 'done')

    def test_pending_picking_refuses_manual_validation(self):
        picking = self._ready_receipt()
        picking.df_process_code = 'P'
        with self.assertRaises(UserError):
            picking.button_validate()

    def test_manual_picking_validates(self):
        picking = self._ready_receipt()
        picking.df_process_code = 'M'
        picking.button_validate()
        self.assertEqual(picking.state, 'done')

    def test_out_of_scope_picking_validates(self):
        # A picking with no Webship location involved ('NA' at create) is
        # outside Stoqflow scope and validates normally.
        stock = self.env.ref('stock.stock_location_stock')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id, 'location_dest_id': stock.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': 1,
                'uom_id': self.product.uom_id.id,
                'location_id': self.suppliers.id, 'location_dest_id': stock.id,
            })],
        })
        self.assertEqual(picking.df_process_code, 'NA')
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 1
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')

    def test_webship_validate_bypasses_guard(self):
        picking = self._ready_receipt()
        picking.df_process_code = 'F'
        picking._webship_validate()
        self.assertEqual(picking.state, 'done')

    def test_set_completed_bypasses_guard(self):
        picking = self._ready_receipt()
        picking.df_process_code = 'F'
        picking.setCompleted()
        self.assertEqual(picking.state, 'done')

    def test_sync_partial_receipt_wizard_bypasses_guard(self):
        # End-to-end: the native completed-picking flow on a pushed ('F')
        # receipt processes the backorder wizard without tripping the guard -
        # the wizard's context replaces the current one, so the bypass flag
        # must be merged in explicitly.
        self.param.set_str('webship.auto_create_backorder', 'True')
        picking = self._ready_receipt(demand=10)
        picking.df_process_code = 'F'

        warnings = self.handler.setPickingQuantities(picking, {
            'status': 'completed', 'edited': EDITED,
            'order_items': [{'product_id': 'WS1', 'quantity': 10, 'received': 6}]})

        self.assertFalse([w for w in warnings if 'Validation error' in w],
                         "unexpected warnings: %s" % warnings)
        self.assertEqual(picking.state, 'done',
                         "state=%s warnings=%s" % (picking.state, warnings))
        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertEqual(len(backorder), 1)
        self.assertEqual(sum(backorder.move_ids.mapped('product_uom_qty')), 4.0)
