# -*- coding: utf-8 -*-
"""LIVE Stoqflow integration tests - these hit the REAL Stoqflow API.

They create records in Stoqflow, verify the round-trip, and DELETE everything
they create in cleanup. Each delete is registered as soon as the record's id is
known (in a finally block), so nothing is left behind even if the sync raises or
a later assertion fails; a delete that fails is logged loudly for manual removal.

SAFETY
------
* Excluded from the standard test run (tagged '-standard'). The normal
  ``--test-tags /webship`` run does NOT execute these. Run them explicitly:

      ./odoo-bin -c <conf> -d <db> --test-tags webship_live --stop-after-init

* Skipped unless live credentials are configured
  (webship.username / webship.password / webship.base_url). Point these at a
  Stoqflow *sandbox/staging* account.

* Orders and purchase orders are created with status 'concept' only (the test
  forces webship.default_status_order / default_status_po_order to 'concept').

* The order/PO tests use whatever Webship (default warehouse) location and
  Stoqflow-linked product already exist in the database; they skip if none are
  found, rather than creating fixtures that might not match your Stoqflow setup.
"""
import logging
import uuid

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)


@tagged('-standard', 'webship_live', 'post_install')
class TestStoqflowLive(TransactionCase):

    def setUp(self):
        super().setUp()
        self.icp = self.env['ir.config_parameter'].sudo()
        login = self.icp.get_str('webship.username')
        pw = self.icp.get_str('webship.password')
        base_url = self.icp.get_str('webship.base_url')
        if not (login and pw and base_url):
            self.skipTest("Live Stoqflow credentials not configured "
                          "(webship.username / webship.password / webship.base_url)")
        self.handler = WebShipHandler(login, pw, base_url)
        self.handler.set_env(self.env)

        # Force safe, deterministic behaviour for the order/PO tests (rolled
        # back with the transaction): create only 'concept' orders/POs, don't
        # gate on stock, and don't take the auto-match side-trips.
        self.icp.set_str('webship.default_status_order', 'concept')
        self.icp.set_str('webship.default_status_po_order', 'concept')
        self.icp.set_str('webship.default_order_available_condition', 'False')
        self.icp.set_str('webship.match_on_order_sync', 'False')
        self.icp.set_str('webship.match_on_po_sync', 'False')

    def _register_delete(self, endpoint, record_id):
        """Delete a created record on teardown; log loudly (never silently) if
        it could not be removed so it can be cleaned up by hand."""
        def _cleanup():
            res = self.handler.performDelete(endpoint, record_id)
            if res.get('status') != 'success':
                _logger.error(
                    "LIVE TEST CLEANUP FAILED: could not delete %s/%s from Stoqflow "
                    "(%s) - please remove it manually", endpoint, record_id,
                    res.get('errorText'))
        self.addCleanup(_cleanup)

    def _new_partner(self, **extra):
        vals = {
            'name': 'ZZ Webship Live Test (delete me)',
            'street': 'Teststraat 1', 'city': 'Gent', 'zip': '9000',
            'country_id': self.env.ref('base.be').id,
            'email': 'zz-webship-test-%s@example.com' % uuid.uuid4().hex[:12],
        }
        vals.update(extra)
        return self.env['res.partner'].create(vals)

    def _webship_location(self):
        """The default Webship warehouse location, or skip if none is mapped."""
        loc = self.env['stock.location'].search(
            [('df_is_webship_location', '=', True)], limit=1)
        if not loc:
            self.skipTest("No Webship location (default warehouse) configured in this DB")
        return loc

    def _linked_product(self):
        """Any product already linked to Stoqflow, or skip if none exists."""
        product = self.env['product.product'].search(
            [('df_product_id_webship', '!=', False), ('default_code', '!=', False)], limit=1)
        if not product:
            self.skipTest("No product linked to Stoqflow (df_product_id_webship) in this DB")
        return product

    def _linked_products(self, n):
        """n distinct products already linked to Stoqflow, or skip."""
        prods = self.env['product.product'].search(
            [('df_product_id_webship', '!=', False), ('default_code', '!=', False)], limit=n)
        if len(prods) < n:
            self.skipTest("Need %d Stoqflow-linked products; found %d" % (n, len(prods)))
        return prods

    def _ensure_brand(self, product):
        """Give the product a Stoqflow brand so it can be created, or skip if
        none is configured (a brand is required to POST a product)."""
        if self.icp.get_str('webship.default_brand'):
            return
        brand = self.env['webship.brand'].search([], limit=1)
        if not brand:
            self.skipTest("No Stoqflow brand configured (webship.brand / webship.default_brand)")
        product.df_brand_id = brand.id

    # ------------------------------------------------------------------ client

    def test_client_create_update_delete(self):
        partner = self._new_partner(df_is_client_in_webship=True)

        errors = self.handler.sync_partner(partner, force=True)
        client_id = partner.df_client_id_webship
        if client_id:
            self._register_delete('clients', client_id)
        self.assertFalse(errors, "client create failed: %s" % errors)
        self.assertTrue(client_id, "no Stoqflow client id returned on create")

        # Update - force bypasses the unchanged-payload hash.
        partner.phone = '+32 9 000 00 00'
        errors = self.handler.sync_partner(partner, force=True)
        self.assertFalse(errors, "client update failed: %s" % errors)
        self.assertEqual(partner.df_client_id_webship, client_id,
                         "update must not create a second client")

    # ------------------------------------------------------------------- order

    def test_concept_order_create_delete(self):
        product = self._linked_product()
        ws_loc = self._webship_location()
        customers = self.env.ref('stock.stock_location_customers')
        partner = self._new_partner(df_is_client_in_webship=True)

        picking = self.env['stock.picking'].create({
            'partner_id': partner.id,
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': ws_loc.id,
            'location_dest_id': customers.id,
            'move_ids': [(0, 0, {
                'product_id': product.id, 'product_uom_qty': 1,
                'uom_id': product.uom_id.id,
                'location_id': ws_loc.id, 'location_dest_id': customers.id,
            })],
        })
        picking.action_confirm()  # leave state != draft/done for the sync gate

        try:
            errors = self.handler._sync_picking(picking)
        finally:
            # Register cleanup for whatever was created (order + the client the
            # order sync creates), even if _sync_picking raised. Order is
            # deleted before the client (addCleanup is LIFO).
            if partner.df_client_id_webship:
                self._register_delete('clients', partner.df_client_id_webship)
            if picking.df_picking_id_webship:
                self._register_delete('orders', picking.df_picking_id_webship)

        self.assertFalse(errors, "concept order sync failed: %s" % errors)
        self.assertTrue(picking.df_picking_id_webship, "no Stoqflow order id returned")

    # ---------------------------------------------------------- purchase order

    def test_concept_purchase_order_create_delete(self):
        product = self._linked_product()
        ws_loc = self._webship_location()
        suppliers = self.env.ref('stock.stock_location_suppliers')
        supplier = self._new_partner(df_is_supplier_in_webship=True,
                                     df_is_client_in_webship=False)

        picking = self.env['stock.picking'].create({
            'partner_id': supplier.id,
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': suppliers.id,
            'location_dest_id': ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': product.id, 'product_uom_qty': 1,
                'uom_id': product.uom_id.id,
                'location_id': suppliers.id, 'location_dest_id': ws_loc.id,
            })],
        })
        picking.action_confirm()

        try:
            errors = self.handler._sync_picking(picking)
        finally:
            # PO sync creates the supplier if it isn't linked yet; clean both.
            if supplier.df_supplier_id_webship:
                self._register_delete('suppliers', supplier.df_supplier_id_webship)
            if picking.df_po_id_webship:
                self._register_delete('purchase-orders', picking.df_po_id_webship)

        self.assertFalse(errors, "concept purchase order sync failed: %s" % errors)
        self.assertTrue(picking.df_po_id_webship, "no Stoqflow purchase order id returned")

    # -------------------------------------------------------------- connection

    def test_connection(self):
        # Scenario 14a: a GET against the API with valid credentials succeeds.
        status, message = self.handler.test()
        self.assertEqual(status, 'success', "connection failed: %s" % message)

    # ----------------------------------------------------------------- product

    def test_product_create_update_match_delete(self):
        # Scenarios 4a (create), 4b (update), 5a (match by SKU).
        sku = 'ZZTEST-%s' % uuid.uuid4().hex[:12]
        product = self.env['product.product'].create({
            'name': 'ZZ Webship Test Product (delete me)', 'default_code': sku,
        })
        self._ensure_brand(product)

        errors = self.handler.sync_product(product)
        product_id = product.df_product_id_webship
        if product_id:
            self._register_delete('products', product_id)
        self.assertFalse(errors, "product create failed: %s" % errors)
        self.assertTrue(product_id, "no Stoqflow product id returned")

        # Update (PUT) - the id must not change.
        product.name = 'ZZ Webship Test Product (updated, delete me)'
        errors = self.handler.sync_product(product)
        self.assertFalse(errors, "product update failed: %s" % errors)
        self.assertEqual(product.df_product_id_webship, product_id)

        # Match a second Odoo product with the same SKU -> links to the same id.
        other = self.env['product.product'].create({
            'name': 'ZZ Webship Test Product 2 (delete me)', 'default_code': sku,
        })
        errors = self.handler.match_product(other)
        self.assertFalse(errors, "product match failed: %s" % errors)
        self.assertEqual(other.df_product_id_webship, product_id,
                         "match must link to the same Stoqflow product")

    # -------------------------------------------------------- multi-line order

    def test_concept_order_multiline_matches(self):
        # Scenario 1a: a multi-line order comes through with products and
        # quantities matching (verified with the line-comparison method).
        products = self._linked_products(2)
        ws_loc = self._webship_location()
        customers = self.env.ref('stock.stock_location_customers')
        partner = self._new_partner(df_is_client_in_webship=True)

        moves = [(0, 0, {
            'product_id': p.id, 'product_uom_qty': qty, 'uom_id': p.uom_id.id,
            'location_id': ws_loc.id, 'location_dest_id': customers.id,
        }) for p, qty in zip(products, (2, 3))]
        picking = self.env['stock.picking'].create({
            'partner_id': partner.id,
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': ws_loc.id, 'location_dest_id': customers.id,
            'move_ids': moves,
        })
        picking.action_confirm()

        try:
            errors = self.handler._sync_picking(picking)
        finally:
            if partner.df_client_id_webship:
                self._register_delete('clients', partner.df_client_id_webship)
            if picking.df_picking_id_webship:
                self._register_delete('orders', picking.df_picking_id_webship)

        self.assertFalse(errors, "multi-line order sync failed: %s" % errors)
        self.assertTrue(picking.df_picking_id_webship)

        # The Stoqflow order contents must match the picking exactly.
        result = picking.compare_lines_with_stoqflow()
        self.assertTrue(result.get('found'), "order not found for comparison")
        self.assertEqual(result.get('problems'), [],
                         "order lines do not match: %s" % result.get('problems'))

    # ------------------------------------------------------------ client match

    def test_client_match_by_email(self):
        # Scenario 7a: a partner whose e-mail matches exactly one Stoqflow
        # client is linked to it.
        email = 'zz-webship-match-%s@example.com' % uuid.uuid4().hex[:12]
        partner_a = self._new_partner(email=email, df_is_client_in_webship=True)
        errors = self.handler.sync_partner(partner_a, force=True)
        client_id = partner_a.df_client_id_webship
        if client_id:
            self._register_delete('clients', client_id)
        self.assertFalse(errors, "client create failed: %s" % errors)
        self.assertTrue(client_id)

        # A different partner with the same e-mail must match that client.
        partner_b = self._new_partner(email=email)
        errors = self.handler.match_partner(partner_b)
        self.assertFalse(errors, "match by email failed: %s" % errors)
        self.assertEqual(partner_b.df_client_id_webship, client_id,
                         "match by email must link to the same Stoqflow client")
