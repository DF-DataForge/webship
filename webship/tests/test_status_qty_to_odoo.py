# -*- coding: utf-8 -*-
import logging
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)
EDITED = '2026-07-10T13:26:06.030Z'


def dump_picking(picking, label):
    _logger.info("TRACE[%s] picking=%s state=%s process=%s syncresult=%r",
                 label, picking.name, picking.state,
                 picking.df_process_code, picking.df_picking_syncresult_webship)
    for m in picking.move_ids:
        _logger.info("TRACE[%s]   move id=%s sku=%s ws_id=%s demand=%s quantity=%s state=%s picked=%s",
                     label, m.id, m.product_id.default_code,
                     m.product_id.df_product_id_webship, m.product_uom_qty,
                     m.quantity, m.state, m.picked)
    for l in picking.move_line_ids:
        _logger.info("TRACE[%s]   line id=%s sku=%s quantity=%s state=%s",
                     label, l.id, l.product_id.default_code, l.quantity, l.state)


class TestStatusQtyToOdoo(TransactionCase):
    """Scenarios 2 & 8 (Stoqflow -> Odoo): a completed order/PO's quantities are
    applied back onto the picking's moves, a same-product quantity is divided
    across multiple Odoo lines, and an unchanged 'edited' timestamp skips the
    update. Validation is stubbed out here - only quantity mapping is asserted
    (completion/backorder behaviour is covered in test_backorder_on_complete)."""

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

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.customers = self.env.ref('stock.stock_location_customers')
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _product(self, sku, ws_id):
        return self.env['product.product'].create({
            'name': 'P-%s' % sku, 'default_code': sku, 'df_product_id_webship': ws_id})

    def _picking(self, ptype, src, dst, lines):
        moves = [(0, 0, {
            'product_id': p.id, 'product_uom_qty': qty, 'uom_id': p.uom_id.id,
            'location_id': src.id, 'location_dest_id': dst.id,
        }) for p, qty in lines]
        return self.env['stock.picking'].create({
            'picking_type_id': ptype.id, 'location_id': src.id,
            'location_dest_id': dst.id, 'move_ids': moves})

    def _out(self, lines):
        return self._picking(self.env.ref('stock.picking_type_out'),
                             self.ws_loc, self.customers, lines)

    def _in(self, lines):
        return self._picking(self.env.ref('stock.picking_type_in'),
                             self.suppliers, self.ws_loc, lines)

    def test_order_quantities_applied(self):
        # 2a: a completed order's picks are applied to the picking's move.
        p1 = self._product('SKU1', 'WS1')
        picking = self._out([(p1, 5)])
        order = {'status': 'completed', 'edited': EDITED,
                 'picks': [{'product_id': 'WS1', 'quantity': 5}]}
        _logger.info("TRACE[2a] order=%s", order)
        self.handler.setPickingQuantities(picking, order)
        dump_picking(picking, '2a after')
        self.assertEqual(picking.move_ids.quantity, 5.0,
                         "move.quantity=%s (expected 5)" % picking.move_ids.quantity)

    def test_order_quantity_divided_across_lines(self):
        # 2b: two moves of the SAME product; Stoqflow returns 4 and it is split
        # across the two Odoo lines (1 and 3), not dumped onto one.
        p1 = self._product('SKU1', 'WS1')
        picking = self._out([(p1, 1), (p1, 3)])
        _logger.info("TRACE[2b] moves at create: %s",
                     [(m.id, m.product_uom_qty) for m in picking.move_ids])
        order = {'status': 'completed', 'edited': EDITED,
                 'picks': [{'product_id': 'WS1', 'quantity': 1},
                           {'product_id': 'WS1', 'quantity': 3}]}
        self.handler.setPickingQuantities(picking, order)
        dump_picking(picking, '2b after')
        self.assertEqual(len(picking.move_ids), 2,
                         "expected 2 separate moves, got %s (merged?)" % len(picking.move_ids))
        by_demand = {m.product_uom_qty: m.quantity for m in picking.move_ids}
        self.assertEqual(by_demand.get(1.0), 1.0, "by_demand=%s" % by_demand)
        self.assertEqual(by_demand.get(3.0), 3.0, "by_demand=%s" % by_demand)
        self.assertEqual(sum(picking.move_ids.mapped('quantity')), 4.0,
                         "total quantity=%s" % sum(picking.move_ids.mapped('quantity')))

    def test_po_received_quantities_applied(self):
        # 8a: a completed PO's order_items[].received is applied to the move.
        p1 = self._product('SKU1', 'WS1')
        picking = self._in([(p1, 10)])
        order = {'status': 'completed', 'edited': EDITED,
                 'order_items': [{'product_id': 'WS1', 'quantity': 10, 'received': 7}]}
        _logger.info("TRACE[8a] order=%s", order)
        self.handler.setPickingQuantities(picking, order)
        dump_picking(picking, '8a after')
        self.assertEqual(picking.move_ids.quantity, 7.0,
                         "move.quantity=%s (expected 7)" % picking.move_ids.quantity)

    def test_unchanged_timestamp_skips_update(self):
        # 8b: when the Stoqflow 'edited' equals the last seen one, no update is
        # performed - setPickingQuantities is never called.
        p1 = self._product('SKU1', 'WS1')
        picking = self._out([(p1, 5)])
        picking.df_picking_id_webship = 'ORD1'
        picking.df_ws_lastChangeDate = EDITED
        data = {'status': 'picking', 'edited': EDITED}
        with mock.patch.object(WebShipHandler, 'fetchByKey',
                               return_value={'status': 'success', 'data': data}), \
                mock.patch.object(WebShipHandler, 'setPickingQuantities') as spq:
            picking._fetch_and_update(picking, self.handler, 'orders', 'ORD1', force=False)
        _logger.info("TRACE[8b] spq.called=%s syncresult=%r",
                     spq.called, picking.df_picking_syncresult_webship)
        self.assertFalse(spq.called,
                         "setPickingQuantities was called %s time(s)" % spq.call_count)
        self.assertIn('No changes detected', picking.df_picking_syncresult_webship or '',
                      "syncresult=%r" % picking.df_picking_syncresult_webship)
