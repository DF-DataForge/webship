# -*- coding: utf-8 -*-
import logging
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)
EDITED = '2026-07-10T13:26:06.030Z'


class TestCourierMapping(TransactionCase):
    """Scenario 16 (Stoqflow -> Odoo): a Stoqflow order's preferred_courier is
    mapped to the matching Odoo delivery carrier on the picking; an unmatched
    courier is surfaced as a warning on the sync result."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            p = mock.patch.object(target, attr, return_value='X')
            p.start()
            self.addCleanup(p.stop)
        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.customers = self.env.ref('stock.stock_location_customers')
        # The courier -> carrier mapping in setPickingQuantities is gated by
        # this setting; enable it so the feature under test actually runs
        # (the Test DB may have it disabled).
        self.env['ir.config_parameter'].sudo().set_str('webship.fetch_courier', 'True')
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _picking(self):
        product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'S1', 'df_product_id_webship': 'WS1'})
        return self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.ws_loc.id, 'location_dest_id': self.customers.id,
            'move_ids': [(0, 0, {
                'product_id': product.id, 'product_uom_qty': 1,
                'uom_id': product.uom_id.id,
                'location_id': self.ws_loc.id, 'location_dest_id': self.customers.id,
            })],
        })

    def test_courier_matched_sets_carrier(self):
        # 16a: preferred_courier matches a linked carrier -> carrier_id is set.
        courier = self.env['stoqflow.courier'].create({'name': 'DPD', 'code': 'DPD'})
        delivery_product = self.env['product.product'].create({
            'name': 'Delivery', 'type': 'service'})
        carrier = self.env['delivery.carrier'].create({
            'name': 'DPD NL', 'delivery_type': 'fixed',
            'product_id': delivery_product.id, 'df_stoqflow_courier_id': courier.id})
        _logger.info("TRACE[16a] created courier=%s carrier=%s (linked=%s)",
                     courier.code, carrier.name, carrier.df_stoqflow_courier_id.code)

        # Sanity-check the matcher directly, so the log shows whether the lookup
        # itself works independently of setPickingQuantities.
        found = self.env['delivery.carrier'].stoqflow_find_delivery_carrier('DPD')
        _logger.info("TRACE[16a] stoqflow_find_delivery_carrier('DPD') -> %s", found)

        picking = self._picking()
        order = {'status': 'ready-to-ship', 'edited': EDITED, 'preferred_courier': 'DPD'}
        self.handler.setPickingQuantities(picking, order)
        _logger.info("TRACE[16a] picking.carrier_id=%s expected=%s syncresult=%r",
                     picking.carrier_id, carrier, picking.df_picking_syncresult_webship)
        self.assertEqual(picking.carrier_id, carrier,
                         "carrier_id=%s (id %s), expected %s (id %s); matcher returned %s"
                         % (picking.carrier_id.name, picking.carrier_id.id,
                            carrier.name, carrier.id, found))

    def test_courier_not_linked_warns(self):
        # 16b: preferred_courier without a linked carrier -> warning on result.
        picking = self._picking()
        order = {'status': 'ready-to-ship', 'edited': EDITED, 'preferred_courier': 'NOPE'}
        self.handler.setPickingQuantities(picking, order)
        _logger.info("TRACE[16b] syncresult=%r", picking.df_picking_syncresult_webship)
        self.assertIn(
            "Courier 'NOPE' present on Stoqflow order but not linked in Odoo",
            picking.df_picking_syncresult_webship or '',
            "syncresult=%r" % picking.df_picking_syncresult_webship)
