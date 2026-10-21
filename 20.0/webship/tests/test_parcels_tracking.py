# -*- coding: utf-8 -*-
import logging
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)
EDITED = '2026-07-10T13:26:06.030Z'

PARCEL = {
    '_id': 'PARCEL1', 'number': 1,
    'tracking_number': 'TRACK123', 'tracking_url': 'https://track/1',
    'width': 10, 'height': 20, 'length': 30, 'weight': 1.5,
    'shipping_address': {'name': 'John', 'address_1': 'Main 1',
                         'postal_code': '1000', 'city': 'Brussels', 'country': 'BE'},
    'contents': [{'sku': 'ABC', 'quantity': 2}],
    'resources': [],
}


class TestParcelsTracking(TransactionCase):
    """Scenario 10 (Stoqflow -> Odoo): parcels from a Stoqflow order are stored
    as webship.parcel records, tracking number/URL are written on the picking,
    and the tracking button opens one URL directly or a selection list."""

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

    def _dump(self, picking, label):
        _logger.info("TRACE[%s] carrier_tracking_ref=%r df_carrier_tracking_urls=%r n_parcels=%s",
                     label, picking.carrier_tracking_ref,
                     picking.df_carrier_tracking_urls, len(picking.df_parcel_ids))
        for pc in picking.df_parcel_ids:
            _logger.info("TRACE[%s]   parcel id=%s number=%s track=%r url=%r "
                         "w/h/l=%s/%s/%s city=%r contents=%s",
                         label, pc.id, pc.df_number, pc.df_tracking_number,
                         pc.df_tracking_url, pc.df_width, pc.df_height, pc.df_length,
                         pc.df_shipping_city, len(pc.df_content_ids))

    def test_parcels_synced_to_records(self):
        # 10a: parcel details stored on webship.parcel with content sublines.
        picking = self._picking()
        order = {'status': 'ready-to-ship', 'edited': EDITED, 'parcels': [PARCEL]}
        self.handler.setPickingQuantities(picking, order)
        self._dump(picking, '10a')

        self.assertEqual(len(picking.df_parcel_ids), 1,
                         "n_parcels=%s" % len(picking.df_parcel_ids))
        parcel = picking.df_parcel_ids
        self.assertEqual(parcel.df_tracking_number, 'TRACK123',
                         "df_tracking_number=%r" % parcel.df_tracking_number)
        self.assertEqual(parcel.df_tracking_url, 'https://track/1',
                         "df_tracking_url=%r" % parcel.df_tracking_url)
        self.assertEqual(parcel.df_width, 10, "df_width=%r" % parcel.df_width)
        self.assertEqual(parcel.df_shipping_city, 'Brussels',
                         "df_shipping_city=%r" % parcel.df_shipping_city)
        self.assertEqual(len(parcel.df_content_ids), 1,
                         "n_contents=%s" % len(parcel.df_content_ids))

    def test_tracking_written_to_picking(self):
        # 10b: tracking number/URL written to the picking fields.
        picking = self._picking()
        order = {'status': 'ready-to-ship', 'edited': EDITED, 'parcels': [PARCEL]}
        self.handler.setPickingQuantities(picking, order)
        self._dump(picking, '10b')
        self.assertEqual(picking.carrier_tracking_ref, 'TRACK123',
                         "carrier_tracking_ref=%r" % picking.carrier_tracking_ref)
        self.assertEqual(picking.df_carrier_tracking_urls, 'https://track/1',
                         "df_carrier_tracking_urls=%r" % picking.df_carrier_tracking_urls)

    def test_single_parcel_opens_url_directly(self):
        # 10c: one parcel with a tracking URL -> the button opens that URL.
        picking = self._picking()
        self.env['webship.parcel'].create({
            'picking_id': picking.id, 'df_number': 1,
            'df_tracking_url': 'https://track/only'})
        action = picking.open_website_url()
        _logger.info("TRACE[10c] action=%s", action)
        self.assertEqual(action.get('type'), 'ir.actions.act_url', "action=%s" % action)
        self.assertEqual(action.get('url'), 'https://track/only', "action=%s" % action)

    def test_multiple_parcels_open_selection_list(self):
        # 10d: several parcels with URLs -> the button opens a selection list.
        picking = self._picking()
        self.env['webship.parcel'].create([
            {'picking_id': picking.id, 'df_number': 1, 'df_tracking_url': 'https://track/1'},
            {'picking_id': picking.id, 'df_number': 2, 'df_tracking_url': 'https://track/2'},
        ])
        action = picking.open_website_url()
        _logger.info("TRACE[10d] action=%s", action)
        self.assertEqual(action.get('type'), 'ir.actions.act_window', "action=%s" % action)
        self.assertEqual(action.get('res_model'), 'webship.parcel', "action=%s" % action)
