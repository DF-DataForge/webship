# -*- coding: utf-8 -*-
import logging
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)
EDITED = '2026-07-10T13:26:06.030Z'


class TestIgnoredSkus(TransactionCase):
    """The 'Ignored SKUs' setting only suppresses the 'no matching product
    found on picking' warning for Stoqflow-only products. It must never affect
    a product that legitimately is on the picking: filtering before allocation
    left such a line zeroed, and the backorder split then turned it into a
    phantom backorder that could never be fulfilled or linked."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            p = mock.patch.object(target, attr, return_value='X')
            p.start()
            self.addCleanup(p.stop)
        for name in ('_validate_completed_picking_native',
                     '_validate_completed_picking_legacy'):
            p = mock.patch.object(WebShipHandler, name, return_value=[])
            p.start()
            self.addCleanup(p.stop)

        self.param = self.env['ir.config_parameter'].sudo()
        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.customers = self.env.ref('stock.stock_location_customers')
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _product(self, sku, ws_id):
        return self.env['product.product'].create({
            'name': 'P-%s' % sku, 'default_code': sku, 'df_product_id_webship': ws_id})

    def _out(self, lines):
        moves = [(0, 0, {
            'product_id': p.id, 'product_uom_qty': qty, 'product_uom': p.uom_id.id,
            'location_id': self.ws_loc.id, 'location_dest_id': self.customers.id,
        }) for p, qty in lines]
        return self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.ws_loc.id, 'location_dest_id': self.customers.id,
            'move_ids': moves})

    def test_ignored_sku_on_picking_still_gets_quantities(self):
        # An ignored SKU that IS on the picking receives its real picked
        # quantity. Before the fix the ignore filter ran before allocation, so
        # the line stayed at the zero the reset loop wrote.
        p1 = self._product('SKU1', 'WS1')
        self.param.set_param('webship.ignored_skus', 'SKU1')
        picking = self._out([(p1, 5)])
        order = {'status': 'completed', 'edited': EDITED,
                 'picks': [{'product_id': 'WS1', 'quantity': 5}]}
        self.handler.setPickingQuantities(picking, order)
        self.assertEqual(picking.move_ids.quantity, 5.0,
                         "move.quantity=%s (expected 5)" % picking.move_ids.quantity)

    def test_stoqflow_only_ignored_sku_suppresses_warning(self):
        # A Stoqflow-only pick (product not on the picking) whose SKU is
        # ignored produces no warning and nothing else in Odoo.
        p1 = self._product('SKU1', 'WS1')
        self._product('SKU2', 'WS2')  # exists in Odoo, but not on the picking
        self.param.set_param('webship.ignored_skus', 'SKU2')
        picking = self._out([(p1, 5)])
        order = {'status': 'completed', 'edited': EDITED,
                 'picks': [{'product_id': 'WS1', 'quantity': 5},
                           {'product_id': 'WS2', 'quantity': 1}]}
        warnings = self.handler.setPickingQuantities(picking, order)
        self.assertFalse([w for w in warnings if 'no matching product' in w],
                         "unexpected warnings: %s" % warnings)
        self.assertEqual(picking.move_ids.quantity, 5.0)

    def test_unignored_stoqflow_only_sku_still_warns(self):
        # Without the ignore entry the same leftover keeps producing the
        # warning - the fix must not silence real mismatches.
        p1 = self._product('SKU1', 'WS1')
        self._product('SKU2', 'WS2')
        self.param.set_param('webship.ignored_skus', '')
        picking = self._out([(p1, 5)])
        order = {'status': 'completed', 'edited': EDITED,
                 'picks': [{'product_id': 'WS1', 'quantity': 5},
                           {'product_id': 'WS2', 'quantity': 1}]}
        warnings = self.handler.setPickingQuantities(picking, order)
        self.assertTrue([w for w in warnings if 'no matching product' in w],
                        "expected a 'no matching product' warning, got: %s" % warnings)

    def test_ignore_matching_case_and_space_insensitive(self):
        # ' sku2 ' in the setting must match Stoqflow SKU 'SKU2' - the compare
        # helper on stock.picking already matched case-insensitively, the pMap
        # filter did not.
        p1 = self._product('SKU1', 'WS1')
        self._product('SKU2', 'WS2')
        self.param.set_param('webship.ignored_skus', ' sku2 ')
        picking = self._out([(p1, 5)])
        order = {'status': 'completed', 'edited': EDITED,
                 'picks': [{'product_id': 'WS1', 'quantity': 5},
                           {'product_id': 'WS2', 'quantity': 1}]}
        warnings = self.handler.setPickingQuantities(picking, order)
        self.assertFalse([w for w in warnings if 'no matching product' in w],
                         "unexpected warnings: %s" % warnings)


class TestIgnoredSkusNoPhantomBackorder(TransactionCase):
    """End-to-end regression (validation NOT stubbed): a fully received
    receipt whose second product's SKU is on the ignore list completes with NO
    backorder. Before the fix that line was zeroed and never restored, and the
    legacy backorder sweep split it off into a phantom backorder."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            p = mock.patch.object(target, attr, return_value='X')
            p.start()
            self.addCleanup(p.stop)

        self.param = self.env['ir.config_parameter'].sudo()
        # The phantom backorders were produced by the legacy sweep; exercise
        # that exact path (the fallback since the native flip).
        self.param.set_param('webship.use_legacy_backorder', 'True')
        self.param.set_param('webship.auto_create_backorder', 'True')
        self.param.set_param('webship.ignored_skus', 'SKU2')

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.p1 = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1', 'df_product_id_webship': 'WS1'})
        self.p2 = self.env['product.product'].create({
            'name': 'Packaging', 'default_code': 'SKU2', 'df_product_id_webship': 'WS2'})
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def test_fully_received_ignored_line_no_backorder(self):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': p.id, 'product_uom_qty': qty,
                'product_uom': p.uom_id.id,
                'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            }) for p, qty in ((self.p1, 10), (self.p2, 5))],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True

        self.handler.setPickingQuantities(picking, {
            'status': 'completed', 'edited': EDITED,
            'order_items': [
                {'product_id': 'WS1', 'quantity': 10, 'received': 10},
                {'product_id': 'WS2', 'quantity': 5, 'received': 5},
            ]})

        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertEqual(picking.state, 'done',
                         "state=%s syncresult=%r" % (picking.state, picking.df_picking_syncresult_webship))
        ignored_move = picking.move_ids.filtered(lambda m: m.product_id == self.p2)
        self.assertEqual(ignored_move.quantity, 5.0,
                         "ignored-SKU line quantity=%s (expected 5)" % ignored_move.quantity)
        self.assertFalse(backorder,
                         "phantom backorder(s): %s" % backorder.mapped('name'))
