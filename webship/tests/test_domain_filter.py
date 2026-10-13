# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking


class TestDomainFilter(TransactionCase):
    """Scenario 12: the configured domain filter classifies new pickings into
    process code 'P' (auto-sync) or 'M' (manual); a demoted picking is promoted
    back to 'P' when it later matches (the re-evaluation the write() override
    triggers when mk_instance_id changes); an invalid filter never crashes and
    the picking keeps its current process code."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(StockPicking, 'fetch_picking_code', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.param = self.env['ir.config_parameter'].sudo()
        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1',
        })

    def _picking(self, origin=False):
        # In Stoqflow scope (dest is a webship location), not a backorder, so
        # create() keeps the default 'P' and then applies the domain filter.
        return self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id,
            'location_dest_id': self.ws_loc.id,
            'origin': origin,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'product_uom': self.product.uom_id.id,
                'location_id': self.suppliers.id, 'location_dest_id': self.ws_loc.id,
            })],
        })

    def test_matching_domain_gets_P(self):
        self.param.set_param('webship.domain', "[('origin', '=', 'WEBSHOP')]")
        picking = self._picking(origin='WEBSHOP')
        self.assertEqual(picking.df_process_code, 'P')

    def test_non_matching_domain_gets_M(self):
        self.param.set_param('webship.domain', "[('origin', '=', 'WEBSHOP')]")
        picking = self._picking(origin='SOMETHING_ELSE')
        self.assertEqual(picking.df_process_code, 'M')

    def test_no_domain_stays_P(self):
        self.param.set_param('webship.domain', '')
        picking = self._picking(origin='ANYTHING')
        self.assertEqual(picking.df_process_code, 'P')

    def test_demoted_picking_promoted_when_now_matches(self):
        self.param.set_param('webship.domain', "[('origin', '=', 'WEBSHOP')]")
        picking = self._picking(origin='NOT_YET')  # does not match -> demoted to M
        self.assertEqual(picking.df_process_code, 'M')

        # It now matches the filter; re-evaluating with promote=True (exactly
        # what write() does when mk_instance_id becomes available) promotes it
        # back to 'P'.
        picking.origin = 'WEBSHOP'
        picking._apply_domain_filter(picking, promote=True)
        self.assertEqual(picking.df_process_code, 'P')

    def test_invalid_domain_does_not_crash(self):
        self.param.set_param('webship.domain', "this is not a valid domain (((")
        # Must not raise; the picking keeps its default pending code.
        picking = self._picking(origin='WHATEVER')
        self.assertEqual(picking.df_process_code, 'P')
