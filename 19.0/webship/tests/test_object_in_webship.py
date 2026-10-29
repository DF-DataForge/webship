# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking


class TestObjectInWebship(TransactionCase):
    """'Object in Stoqflow' (df_object_in_webship) classification.

    Pickings were wrongly stored as 'Mutation' in two situations:
    - the location was flagged as a Stoqflow location only after the picking
      existed (the stored compute depended on the location ids, not the flag);
    - source and destination are both Stoqflow locations (e.g. an operation
      type defaulting both sides to the same Stoqflow stock location) while
      the picking fulfils a sale or purchase order."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(StockPicking, 'fetch_picking_code', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)

        parent = self.env.ref('stock.stock_location_stock').location_id
        self.plain_loc = self.env['stock.location'].create({
            'name': 'Plain Stock', 'usage': 'internal', 'location_id': parent.id,
        })
        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock', 'usage': 'internal', 'location_id': parent.id,
            'df_is_webship_location': True,
        })
        self.customers = self.env.ref('stock.stock_location_customers')
        self.suppliers = self.env.ref('stock.stock_location_suppliers')
        self.type_internal = self.env.ref('stock.picking_type_internal')
        self.type_out = self.env.ref('stock.picking_type_out')
        self.type_in = self.env.ref('stock.picking_type_in')
        self.product = self.env['product.product'].create({
            'name': 'Prod', 'default_code': 'SKU1', 'is_storable': True,
        })
        self.partner = self.env['res.partner'].create({'name': 'ACME'})

    def _picking(self, src, dest, picking_type, **extra):
        vals = {
            'partner_id': self.partner.id,
            'picking_type_id': picking_type.id,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'product_uom': self.product.uom_id.id,
                'location_id': src.id,
                'location_dest_id': dest.id,
            })],
        }
        vals.update(extra)
        return self.env['stock.picking'].create(vals)

    # -- direction from the locations (unchanged behaviour) -----------------

    def test_outbound_is_order(self):
        picking = self._picking(self.ws_loc, self.customers, self.type_out)
        self.assertEqual(picking.df_object_in_webship, 'Order')
        self.assertTrue(picking.df_show_webship_page)

    def test_inbound_is_purchase_order(self):
        picking = self._picking(self.suppliers, self.ws_loc, self.type_in)
        self.assertEqual(picking.df_object_in_webship, 'Purchase order')
        self.assertTrue(picking.df_show_webship_page)

    def test_no_stoqflow_location_is_mutation(self):
        picking = self._picking(self.plain_loc, self.customers, self.type_out)
        self.assertEqual(picking.df_object_in_webship, 'Mutation')
        self.assertFalse(picking.df_show_webship_page)

    # -- flagging a location afterwards reclassifies existing pickings -------

    def test_flagging_destination_later_reclassifies(self):
        # Transfer into a location that is not (yet) a Stoqflow location.
        picking = self._picking(self.plain_loc, self.ws_loc, self.type_internal)
        self.assertEqual(picking.df_object_in_webship, 'Purchase order')

        later_ws = self.env['stock.location'].create({
            'name': 'Later WS', 'usage': 'internal',
            'location_id': self.ws_loc.location_id.id,
        })
        picking = self._picking(self.plain_loc, later_ws, self.type_internal)
        self.assertEqual(picking.df_object_in_webship, 'Mutation')
        self.assertFalse(picking.df_show_webship_page)

        later_ws.df_is_webship_location = True
        self.assertEqual(picking.df_object_in_webship, 'Purchase order')
        self.assertTrue(picking.df_show_webship_page)

    def test_flagging_source_later_reclassifies(self):
        later_ws = self.env['stock.location'].create({
            'name': 'Later WS', 'usage': 'internal',
            'location_id': self.ws_loc.location_id.id,
        })
        picking = self._picking(later_ws, self.customers, self.type_out)
        self.assertEqual(picking.df_object_in_webship, 'Mutation')

        later_ws.df_is_webship_location = True
        self.assertEqual(picking.df_object_in_webship, 'Order')
        self.assertTrue(picking.df_show_webship_page)

    def test_unflagging_location_reverts_to_mutation(self):
        picking = self._picking(self.ws_loc, self.customers, self.type_out)
        self.assertEqual(picking.df_object_in_webship, 'Order')

        self.ws_loc.df_is_webship_location = False
        self.assertEqual(picking.df_object_in_webship, 'Mutation')
        self.assertFalse(picking.df_show_webship_page)

    # -- both sides Stoqflow: the document decides ----------------------------

    def test_both_sides_with_sale_order_is_order(self):
        sale = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': 1,
            })],
        })
        # procurement.group is gone since Odoo 19: the picking's sale order
        # comes from its moves' sale lines.
        picking = self._picking(self.ws_loc, self.ws_loc, self.type_internal,
                                origin=sale.name)
        picking.move_ids.sale_line_id = sale.order_line
        self.assertEqual(picking.sale_id, sale)
        self.assertEqual(picking.df_object_in_webship, 'Order')
        self.assertTrue(picking.df_show_webship_page)

    def test_both_sides_with_purchase_order_is_purchase_order(self):
        purchase = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id, 'product_qty': 1,
                'price_unit': 1.0,
            })],
        })
        picking = self._picking(self.ws_loc, self.ws_loc, self.type_internal)
        picking.move_ids.purchase_line_id = purchase.order_line
        self.assertEqual(picking.purchase_id, purchase)
        self.assertEqual(picking.df_object_in_webship, 'Purchase order')

    def test_both_sides_delivery_type_is_order(self):
        picking = self._picking(self.ws_loc, self.ws_loc, self.type_out)
        self.assertEqual(picking.df_object_in_webship, 'Order')

    def test_both_sides_receipt_type_is_purchase_order(self):
        picking = self._picking(self.ws_loc, self.ws_loc, self.type_in)
        self.assertEqual(picking.df_object_in_webship, 'Purchase order')

    def test_both_sides_plain_internal_is_mutation(self):
        picking = self._picking(self.ws_loc, self.ws_loc, self.type_internal)
        self.assertEqual(picking.df_object_in_webship, 'Mutation')
        self.assertTrue(picking.df_show_webship_page)

    # -- scheduled action: repair stale stored values --------------------------

    def _force_stale(self, picking):
        """Store the pre-fix values straight in the table, bypassing the ORM,
        the way pickings created before their location was flagged look."""
        picking.env.flush_all()
        picking.env.cr.execute(
            "UPDATE stock_picking SET df_object_in_webship = 'Mutation', "
            "df_show_webship_page = FALSE WHERE id = %s", (picking.id,))
        picking.invalidate_recordset(['df_object_in_webship', 'df_show_webship_page'])
        self.assertEqual(picking.df_object_in_webship, 'Mutation')
        self.assertFalse(picking.df_show_webship_page)

    def test_reclassify_cron_repairs_stale_pickings(self):
        inbound = self._picking(self.plain_loc, self.ws_loc, self.type_internal)
        outbound = self._picking(self.ws_loc, self.customers, self.type_out)
        untouched = self._picking(self.plain_loc, self.customers, self.type_out)
        self._force_stale(inbound)
        self._force_stale(outbound)
        notes_before = len(inbound.message_ids)

        examined, changed = self.env['stock.picking']._ws_reclassify_object_types()

        self.assertIn(inbound, examined)
        self.assertIn(outbound, examined)
        self.assertNotIn(untouched, examined)
        self.assertEqual(changed, inbound | outbound)
        self.assertEqual(inbound.df_object_in_webship, 'Purchase order')
        self.assertEqual(outbound.df_object_in_webship, 'Order')
        self.assertTrue(inbound.df_show_webship_page)
        self.assertTrue(outbound.df_show_webship_page)
        self.assertEqual(untouched.df_object_in_webship, 'Mutation')
        # The correction is explained in the chatter.
        self.assertEqual(len(inbound.message_ids), notes_before + 1)
        self.assertIn('Purchase order', inbound.message_ids[0].body)

    def test_reclassify_cron_is_idempotent(self):
        picking = self._picking(self.ws_loc, self.customers, self.type_out)
        notes_before = len(picking.message_ids)
        examined, changed = self.env['stock.picking']._ws_reclassify_object_types()
        self.assertIn(picking, examined)
        self.assertFalse(changed)
        self.assertEqual(len(picking.message_ids), notes_before)

    def test_reclassify_cron_entry_point(self):
        picking = self._picking(self.plain_loc, self.ws_loc, self.type_internal)
        self._force_stale(picking)
        changed = self.env['res.config.settings'].ws_reclassify_object_types()
        self.assertEqual(changed, picking)
        self.assertEqual(picking.df_object_in_webship, 'Purchase order')
        cron = self.env.ref('webship.ir_cron_reclassify_object_types')
        self.assertTrue(cron.active)
