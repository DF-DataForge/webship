# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler


class TestOrderAutoMatch(TransactionCase):
    """Risk 7g: when auto-match on order sync finds multiple Stoqflow clients,
    the sync must be blocked with a 'match manually' error instead of falling
    through to sync_partner and creating a duplicate client."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            patcher = mock.patch.object(target, attr, return_value='X')
            patcher.start()
            self.addCleanup(patcher.stop)

        self.env['ir.config_parameter'].sudo().set_str('webship.match_on_order_sync', 'True')

        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.customers = self.env.ref('stock.stock_location_customers')
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1',
        })
        self.partner = self.env['res.partner'].create({'name': 'ACME'})  # no df_client_id_webship

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

        self.picking = self.env['stock.picking'].create({
            'partner_id': self.partner.id,
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.ws_loc.id,
            'location_dest_id': self.customers.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'uom_id': self.product.uom_id.id,
                'location_id': self.ws_loc.id,
                'location_dest_id': self.customers.id,
            })],
        })
        self.picking.action_confirm()

    def test_multiple_matches_blocks_and_requires_manual_match(self):
        multiple = {'errors': [], 'match_field': 'e-mail',
                    'multiple': [{'_id': 'C1', 'name': 'ACME'}, {'_id': 'C2', 'name': 'ACME BV'}]}
        with mock.patch.object(self.handler, 'match_partner_by_sequence', return_value=multiple), \
                mock.patch.object(self.handler, 'sync_partner') as sync, \
                mock.patch.object(self.handler, 'performPost') as post:
            result = self.handler._sync_picking(self.picking)

        # Sync is blocked with a manual-match error...
        self.assertTrue(result)
        self.assertTrue(any('Multiple Stoqflow clients match' in e for e in result))
        # ...and no duplicate client is created (sync_partner never runs).
        sync.assert_not_called()
        post.assert_not_called()

    def test_single_match_does_not_block(self):
        # No multiple -> the auto-match block does not raise the manual error;
        # sync proceeds to sync_partner (stubbed to succeed with no order items
        # so nothing is actually posted).
        single = {'errors': [], 'match_field': '', 'multiple': None}
        with mock.patch.object(self.handler, 'match_partner_by_sequence', return_value=single), \
                mock.patch.object(self.handler, 'sync_partner', return_value=[]) as sync, \
                mock.patch.object(self.handler, 'build_order_object',
                                  return_value={'errors': [], 'webshipObj': {'order_items': [
                                      {'product_id': 'WS1', 'quantity': 1}]}}), \
                mock.patch.object(self.handler, 'performPost',
                                  return_value={'status': 'success', 'data': {'_id': 'O1'}}), \
                mock.patch.object(self.handler, '_safe_status_to_odoo', return_value=[]), \
                mock.patch.object(self.handler, '_find_existing_order', return_value=None):
            result = self.handler._sync_picking(self.picking)

        self.assertFalse(any('Multiple Stoqflow clients match' in e for e in result))
        sync.assert_called()

    def test_reference_unique_post_error_recovers_by_linking(self):
        # The POST returns "reference must be unique": the order already exists
        # in Stoqflow from an earlier attempt and only the local link is missing.
        # The sync must look it up by origin.id and link it instead of failing.
        single = {'errors': [], 'match_field': '', 'multiple': None}
        with mock.patch.object(self.handler, 'match_partner_by_sequence', return_value=single), \
                mock.patch.object(self.handler, 'sync_partner', return_value=[]), \
                mock.patch.object(self.handler, 'build_order_object',
                                  return_value={'errors': [], 'webshipObj': {'order_items': [
                                      {'product_id': 'WS1', 'quantity': 1}]}}), \
                mock.patch.object(self.handler, 'performPost',
                                  return_value={'status': 'error',
                                                'errorText': 'reference must be unique'}) as post, \
                mock.patch.object(self.handler, '_safe_status_to_odoo', return_value=[]), \
                mock.patch.object(self.handler, '_find_existing_order',
                                  side_effect=[None, 'RECOVERED1']):
            result = self.handler._sync_picking(self.picking)

        # Recovered: no sync error, the existing order is linked, no re-POST.
        self.assertEqual(result, [])
        self.assertEqual(self.picking.df_picking_id_webship, 'RECOVERED1')
        post.assert_called_once()

    def test_post_error_without_existing_order_still_fails(self):
        # A genuine POST failure with no existing order in Stoqflow must still
        # surface the error (recovery only links when the order actually exists).
        single = {'errors': [], 'match_field': '', 'multiple': None}
        with mock.patch.object(self.handler, 'match_partner_by_sequence', return_value=single), \
                mock.patch.object(self.handler, 'sync_partner', return_value=[]), \
                mock.patch.object(self.handler, 'build_order_object',
                                  return_value={'errors': [], 'webshipObj': {'order_items': [
                                      {'product_id': 'WS1', 'quantity': 1}]}}), \
                mock.patch.object(self.handler, 'performPost',
                                  return_value={'status': 'error', 'errorText': 'boom'}), \
                mock.patch.object(self.handler, '_find_existing_order', return_value=None):
            result = self.handler._sync_picking(self.picking)

        self.assertTrue(any('boom' in e for e in result))
        self.assertFalse(self.picking.df_picking_id_webship)
