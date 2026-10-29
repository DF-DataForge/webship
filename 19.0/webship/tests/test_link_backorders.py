# -*- coding: utf-8 -*-
from unittest import mock

from odoo import fields
from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler


class TestLinkBackorders(TransactionCase):
    """Scenario 23: a freshly created backorder is linked to the Stoqflow child
    order whose contents match; on a mismatch it is left unlinked with the
    differences recorded."""

    def setUp(self):
        super().setUp()
        for target, attr in ((StockPicking, 'fetch_picking_code'),
                             (WebShipHandler, 'fetchCode')):
            patcher = mock.patch.object(target, attr, return_value='X')
            patcher.start()
            self.addCleanup(patcher.stop)

        # The comparison needs an ignore list and product lookups; keep them
        # trivial (products carry df_product_id_webship, so no SKU lookup).
        for attr, ret in (('_get_ignored_skus', []), ('findProductBySku', {})):
            p = mock.patch.object(WebShipHandler, attr, return_value=ret)
            p.start()
            self.addCleanup(p.stop)

        # A Webship destination location makes df_object_in_webship == 'Purchase order'.
        self.ws_loc = self.env['stock.location'].create({
            'name': 'WS Stock',
            'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        self.suppliers = self.env.ref('stock.stock_location_suppliers')

        self.p1 = self._product('Product One', 'SKU1', 'WS1')
        self.p2 = self._product('Product Two', 'SKU2', 'WS2')

        # Original receipt, linked to the parent Stoqflow PO.
        self.original = self._po_picking([(self.p1, 100), (self.p2, 50)])
        self.original.df_po_id_webship = 'PARENT1'

    def _product(self, name, sku, ws_id):
        return self.env['product.product'].create({
            'name': name, 'default_code': sku, 'df_product_id_webship': ws_id,
        })

    def _po_picking(self, lines, backorder_of=None):
        moves = [(0, 0, {
            'product_id': p.id,
            'product_uom_qty': qty,
            'product_uom': p.uom_id.id,
            'location_id': self.suppliers.id,
            'location_dest_id': self.ws_loc.id,
        }) for p, qty in lines]
        vals = {
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': self.suppliers.id,
            'location_dest_id': self.ws_loc.id,
            'move_ids': moves,
        }
        if backorder_of:
            vals['backorder_id'] = backorder_of.id
        return self.env['stock.picking'].create(vals)

    def _order_picking(self, lines, backorder_of=None):
        """Outbound delivery (Webship source -> customer) so
        df_object_in_webship == 'Order', exercising the orders/df_picking_id
        branch of the backorder linking."""
        customers = self.env.ref('stock.stock_location_customers')
        moves = [(0, 0, {
            'product_id': p.id,
            'product_uom_qty': qty,
            'product_uom': p.uom_id.id,
            'location_id': self.ws_loc.id,
            'location_dest_id': customers.id,
        }) for p, qty in lines]
        vals = {
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': self.ws_loc.id,
            'location_dest_id': customers.id,
            'move_ids': moves,
        }
        if backorder_of:
            vals['backorder_id'] = backorder_of.id
        return self.env['stock.picking'].create(vals)

    @staticmethod
    def _child(child_id, number, items, status=None, edited=None):
        child = {'_id': child_id, 'order_number': number,
                 'order_items': [{'product_id': pid, 'quantity': qty} for pid, qty in items]}
        if status is not None:
            child['status'] = status
        if edited is not None:
            child['edited'] = edited
        return child

    def test_exact_match_links(self):
        backorder = self._po_picking([(self.p1, 40), (self.p2, 20)], backorder_of=self.original)
        child = self._child('CHILD1', 'PO-01', [('WS1', 40), ('WS2', 20)],
                            status='on-hold', edited='2026-07-14T13:21:52.301Z')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]):
            backorder._link_stoqflow_backorder()
        self.assertEqual(backorder.df_po_id_webship, 'CHILD1')
        self.assertEqual(backorder.df_po_code_webship, 'PO-01')
        self.assertIn('Linked', backorder.df_picking_syncresult_webship or '')
        # Sync metadata is populated straight from the child payload.
        self.assertEqual(backorder.df_status_webship, 'on-hold')
        self.assertTrue(backorder.df_picking_lastsync_webship)
        self.assertEqual(
            fields.Datetime.to_string(backorder.df_last_changedate_webship),
            '2026-07-14 13:21:52')

    def test_linking_sets_process_code_to_sent_to_stoqflow(self):
        """A backorder is created as 'M' (Manual) so the cron never pushes it as
        a new order. Once linked the order does exist in Stoqflow, so the code
        must become 'F' (Sent to Stoqflow)."""
        backorder = self._po_picking([(self.p1, 40)], backorder_of=self.original)
        backorder.df_process_code = 'M'
        child = self._child('CHILD1', 'PO00028-02', [('WS1', 40)], status='ordered')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]):
            backorder._link_stoqflow_backorder()
        self.assertEqual(backorder.df_po_id_webship, 'CHILD1')
        self.assertEqual(backorder.df_process_code, 'F')

    def test_process_code_stays_manual_when_not_linked(self):
        backorder = self._po_picking([(self.p1, 40)], backorder_of=self.original)
        backorder.df_process_code = 'M'
        child = self._child('CHILD1', 'PO00028-02', [('WS1', 99)], status='ordered')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]):
            backorder._link_stoqflow_backorder()
        self.assertFalse(backorder.df_po_id_webship)
        self.assertEqual(backorder.df_process_code, 'M')

    def test_exact_match_links_outbound_order(self):
        # Same as test_exact_match_links but for an outbound Order (uses
        # df_picking_id_webship), proving linking works for orders too.
        parent = self._order_picking([(self.p1, 100), (self.p2, 50)])
        parent.df_picking_id_webship = 'PARENTORD1'
        backorder = self._order_picking([(self.p1, 40), (self.p2, 20)], backorder_of=parent)
        child = self._child('CHILDORD1', 'SO-01', [('WS1', 40), ('WS2', 20)])
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]) as q:
            backorder._link_stoqflow_backorder()
        # Queried the orders endpoint (not purchase-orders) with the parent id.
        q.assert_called_once_with('orders', 'PARENTORD1')
        self.assertEqual(backorder.df_picking_id_webship, 'CHILDORD1')
        self.assertEqual(backorder.df_picking_code_webship, 'SO-01')
        self.assertIn('Linked', backorder.df_picking_syncresult_webship or '')

    def test_mismatch_not_linked_shows_differences(self):
        backorder = self._po_picking([(self.p1, 40), (self.p2, 20)], backorder_of=self.original)
        # Child quantities differ -> no exact match.
        child = self._child('CHILD1', 'PO-01', [('WS1', 99), ('WS2', 20)])
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]):
            backorder._link_stoqflow_backorder()
        self.assertFalse(backorder.df_po_id_webship)
        result = backorder.df_picking_syncresult_webship or ''
        self.assertIn('Not linked', result)
        self.assertIn('not corresponding', result)

    def test_correct_child_chosen_among_several(self):
        backorder = self._po_picking([(self.p1, 40), (self.p2, 20)], backorder_of=self.original)
        wrong = self._child('CHILD_A', 'PO-01', [('WS1', 100), ('WS2', 50)])   # the completed part
        right = self._child('CHILD_B', 'PO-02', [('WS1', 40), ('WS2', 20)])    # the remainder
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[wrong, right]):
            backorder._link_stoqflow_backorder()
        self.assertEqual(backorder.df_po_id_webship, 'CHILD_B')

    def test_already_linked_child_not_reused(self):
        # CHILD1 is already linked to another picking.
        other = self._po_picking([(self.p1, 40)])
        other.df_po_id_webship = 'CHILD1'
        backorder = self._po_picking([(self.p1, 40), (self.p2, 20)], backorder_of=self.original)
        child = self._child('CHILD1', 'PO-01', [('WS1', 40), ('WS2', 20)])
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]):
            backorder._link_stoqflow_backorder()
        self.assertFalse(backorder.df_po_id_webship)

    def test_no_stoqflow_ancestor_skips_query(self):
        # A backorder whose parent has no Stoqflow id must not query at all.
        unlinked_parent = self._po_picking([(self.p1, 40)])  # no df_po_id_webship
        backorder = self._po_picking([(self.p1, 40)], backorder_of=unlinked_parent)
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders') as q:
            backorder._link_stoqflow_backorder()
            q.assert_not_called()
        self.assertFalse(backorder.df_po_id_webship)

    # --- find_backorder: the search, without any write on the picking ---

    def test_find_backorder_returns_matching_child(self):
        backorder = self._po_picking([(self.p1, 40), (self.p2, 20)], backorder_of=self.original)
        child = self._child('CHILD1', 'PO-01', [('WS1', 40), ('WS2', 20)])
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]) as q:
            found = backorder.find_backorder()
        q.assert_called_once_with('purchase-orders', 'PARENT1')
        self.assertEqual(found['match'], child)
        self.assertEqual(found['parent_id'], 'PARENT1')
        self.assertEqual(found['endpoint'], 'purchase-orders')
        self.assertEqual(found['id_field'], 'df_po_id_webship')
        self.assertEqual(found['code_field'], 'df_po_code_webship')
        self.assertIsNone(found['closest'])
        # Searching must not write anything on the picking.
        self.assertFalse(backorder.df_po_id_webship)
        self.assertFalse(backorder.df_picking_syncresult_webship)

    def test_find_backorder_reports_closest_on_mismatch(self):
        backorder = self._po_picking([(self.p1, 40), (self.p2, 20)], backorder_of=self.original)
        child = self._child('CHILD1', 'PO-01', [('WS1', 99), ('WS2', 20)])
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]):
            found = backorder.find_backorder()
        self.assertIsNone(found['match'])
        self.assertEqual(found['closest']['child'], child)
        self.assertEqual(found['closest']['problems'], 1)
        self.assertTrue(found['reason'])

    def test_find_backorder_without_stoqflow_ancestor(self):
        unlinked_parent = self._po_picking([(self.p1, 40)])  # no df_po_id_webship
        backorder = self._po_picking([(self.p1, 40)], backorder_of=unlinked_parent)
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders') as q:
            found = backorder.find_backorder()
        q.assert_not_called()
        self.assertIsNone(found['match'])
        self.assertIsNone(found['parent_id'])

    def test_find_backorder_reuses_given_handler(self):
        backorder = self._po_picking([(self.p1, 40), (self.p2, 20)], backorder_of=self.original)
        child = self._child('CHILD1', 'PO-01', [('WS1', 40), ('WS2', 20)])
        handler = WebShipHandler('u', 'p', 'http://test/')
        handler.set_env(self.env)
        with mock.patch.object(StockPicking, 'getHandler') as get_handler, \
                mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]):
            found = backorder.find_backorder(handler=handler)
        get_handler.assert_not_called()
        self.assertEqual(found['match'], child)

    # --- find_backorder: picking the right child among the parent's children ---

    def test_find_backorder_real_payload_picks_open_remainder(self):
        """Real GET /purchase-orders?parent_order_id=<parent> payload: the parent
        was split into a completed child (what was received) and an open child
        (the remainder). The Odoo backorder must land on the open one."""
        received = self._product('Received Widget', 'SKU-R', 'mpjgaxDFPiX6EJtz5')
        missing = self._product('Missing Widget', 'SKU-M', 'atS776A2AgaKLaKtF')
        parent = self._po_picking([(received, 1), (missing, 1)])
        parent.df_po_id_webship = 'uNzpA6qPm3hqggo76'
        backorder = self._po_picking([(missing, 1)], backorder_of=parent)

        children = [
            {
                '_id': 'WPq4jcvP2cTkW2ADm',
                'status': 'completed',
                'order_number': 'PO00028-01',
                'parent_order_id': 'uNzpA6qPm3hqggo76',
                'delivered': '2026-08-17T07:19:27.471Z',
                'order_items': [
                    {'product_id': 'mpjgaxDFPiX6EJtz5', 'quantity': 1, 'received': 1},
                    {'product_id': 'atS776A2AgaKLaKtF', 'quantity': 1, 'received': 0},
                ],
                'received_product_items': [
                    {'_id': 'AdRMqWmFeDpBLShn7', 'quantity': 1,
                     'product_id': 'mpjgaxDFPiX6EJtz5'},
                ],
            },
            {
                '_id': '4LKrm4QP3mPrxW2DN',
                'status': 'ordered',
                'order_number': 'PO00028-02',
                'parent_order_id': 'uNzpA6qPm3hqggo76',
                'order_items': [{'product_id': 'atS776A2AgaKLaKtF', 'quantity': 1}],
            },
        ]
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=children):
            backorder._link_stoqflow_backorder()

        self.assertEqual(backorder.df_po_id_webship, '4LKrm4QP3mPrxW2DN')
        self.assertEqual(backorder.df_po_code_webship, 'PO00028-02')
        self.assertEqual(backorder.df_status_webship, 'ordered')
        self.assertIn('Linked', backorder.df_picking_syncresult_webship or '')

    def test_completed_child_loses_to_open_child_on_identical_contents(self):
        """When the processed child and the remainder hold the same contents,
        content matching alone is a coin flip: the completed one must never win."""
        backorder = self._po_picking([(self.p1, 1)], backorder_of=self.original)
        done = self._child('DONE1', 'PO00028-01', [('WS1', 1)], status='completed')
        done['delivered'] = '2026-08-17T07:19:27.471Z'
        done['order_items'][0]['received'] = 1
        open_child = self._child('OPEN1', 'PO00028-02', [('WS1', 1)], status='ordered')
        # Completed child first, so a first-match-wins scan would pick it.
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders',
                               return_value=[done, open_child]):
            backorder._link_stoqflow_backorder()
        self.assertEqual(backorder.df_po_id_webship, 'OPEN1')
        # The runner-up is named, so the choice is auditable.
        self.assertIn('PO00028-01', backorder.df_picking_syncresult_webship or '')

    def test_lowest_order_number_suffix_wins_between_open_children(self):
        backorder = self._po_picking([(self.p1, 1)], backorder_of=self.original)
        second = self._child('OPEN2', 'PO00028-03', [('WS1', 1)], status='ordered')
        first = self._child('OPEN1', 'PO00028-02', [('WS1', 1)], status='ordered')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders',
                               return_value=[second, first]):
            found = backorder.find_backorder()
        self.assertEqual(found['match']['_id'], 'OPEN1')
        self.assertEqual([c['_id'] for c in found['candidates']], ['OPEN1', 'OPEN2'])

    def test_not_linked_names_the_not_received_remainder(self):
        """No child matches the Odoo backorder, but one holds exactly what was
        not received - report it as the likely counterpart."""
        # The Odoo backorder holds 5, no child holds 5 -> nothing matches.
        backorder = self._po_picking([(self.p1, 5)], backorder_of=self.original)
        done = self._child('DONE1', 'PO00028-01', [('WS1', 2)], status='completed')
        done['order_items'][0]['received'] = 1          # 1 of 2 received -> remainder 1
        open_child = self._child('OPEN1', 'PO00028-02', [('WS1', 1)], status='ordered')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders',
                               return_value=[done, open_child]):
            found = backorder.find_backorder()
            backorder._link_stoqflow_backorder()
        self.assertIsNone(found['match'])
        self.assertEqual([c['_id'] for c in found['remainder_matches']], ['OPEN1'])
        self.assertEqual(found['expected']['_id'], 'OPEN1')
        self.assertFalse(backorder.df_po_id_webship)
        result = backorder.df_picking_syncresult_webship or ''
        self.assertIn('Not linked', result)
        # Chronology still names the child this backorder belongs to.
        self.assertIn('PO00028-02', result)

    def test_chronology_shifts_when_an_earlier_backorder_stayed_unlinked(self):
        """Odoo and Stoqflow create their backorders in the same order, so the
        second Odoo backorder takes the second unlinked child - even when both
        children have the same contents and the first backorder never linked."""
        first = self._po_picking([(self.p1, 2)], backorder_of=self.original)  # unlinked
        second = self._po_picking([(self.p1, 2)], backorder_of=first)
        children = [
            self._child('OPEN1', 'PO00028-02', [('WS1', 2)], status='ordered'),
            self._child('OPEN2', 'PO00028-03', [('WS1', 2)], status='ordered'),
        ]
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=children):
            second._link_stoqflow_backorder()
        self.assertEqual(second.df_po_id_webship, 'OPEN2')
        self.assertEqual(second.df_po_code_webship, 'PO00028-03')

    # --- Outbound orders: the split reports 'picks', not 'received' ---

    def test_outbound_split_picks_the_open_remainder(self):
        """An outbound order reports what was handled as 'picks' (with parcels),
        so the shipped half must be recognised as processed even though its
        contents also tie with the backorder."""
        parent = self._order_picking([(self.p1, 3)])
        parent.df_picking_id_webship = 'PARENTORD1'
        backorder = self._order_picking([(self.p1, 1)], backorder_of=parent)
        shipped = self._child('SHIPPED', 'SO00042-01', [('WS1', 1)], status='in-transit')
        shipped['picks'] = [{'product_id': 'WS1', 'quantity': 1}]
        shipped['parcels'] = [{'tracking_number': 'TRACK1'}]
        remainder = self._child('OPEN', 'SO00042-02', [('WS1', 1)], status='ready-to-pick')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders',
                               return_value=[shipped, remainder]) as q:
            backorder._link_stoqflow_backorder()
        q.assert_called_once_with('orders', 'PARENTORD1')
        self.assertEqual(backorder.df_picking_id_webship, 'OPEN')
        self.assertEqual(backorder.df_picking_code_webship, 'SO00042-02')

    def test_outbound_remainder_computed_from_picks(self):
        """quantity - picked is the outbound equivalent of quantity - received."""
        parent = self._order_picking([(self.p1, 3)])
        parent.df_picking_id_webship = 'PARENTORD1'
        backorder = self._order_picking([(self.p1, 2)], backorder_of=parent)
        shipped = self._child('SHIPPED', 'SO00042-01', [('WS1', 3)], status='completed')
        shipped['picks'] = [{'product_id': 'WS1', 'quantity': 1}]   # 1 of 3 -> remainder 2
        remainder = self._child('OPEN', 'SO00042-02', [('WS1', 2)], status='ready-to-pick')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders',
                               return_value=[shipped, remainder]):
            found = backorder.find_backorder()
        self.assertEqual(found['match']['_id'], 'OPEN')
        self.assertEqual([c['_id'] for c in found['remainder_matches']], ['OPEN'])

    def test_open_status_wins_over_leftover_pick_data(self):
        """A child that still has to be picked is the remainder even if the
        payload carries leftover picks."""
        picking = self.env['stock.picking']
        self.assertTrue(picking._stoqflow_child_is_open({
            'status': 'ready-to-pick', 'picks': [{'product_id': 'WS1', 'quantity': 1}]}))
        self.assertFalse(picking._stoqflow_child_is_open({
            'status': 'in-transit', 'picks': [{'product_id': 'WS1', 'quantity': 1}]}))

    def test_pick_substitution_counts_against_the_ordered_product(self):
        """A substituted pick reports the ordered product in parent_product_id,
        so the remainder must be computed against that one."""
        shipped = {'_id': 'S', 'order_number': 'SO00042-01', 'status': 'completed',
                   'order_items': [{'product_id': 'WS1', 'quantity': 5}],
                   'picks': [{'product_id': 'WS2', 'parent_product_id': 'WS1', 'quantity': 2}]}
        picking = self.env['stock.picking']
        self.assertEqual(picking._stoqflow_picked_map(shipped), {'WS1': 2})
        self.assertEqual(picking._stoqflow_remainder_map(shipped), {'WS1': 3})

    # --- Tracing ---

    def _traces(self, picking):
        return self.env['webship.json.history'].search([
            ('picking_id', '=', picking.id), ('direction', '=', 'trace'),
            ('endpoint', '=', 'link_backorder'),
        ])

    def test_verbose_logging_stores_the_decision_trace(self):
        self.env['ir.config_parameter'].sudo().set_param('webship.verbose_logging', 'True')
        backorder = self._po_picking([(self.p1, 40), (self.p2, 20)], backorder_of=self.original)
        wrong = self._child('CHILD_A', 'PO00028-01', [('WS1', 100), ('WS2', 50)], status='completed')
        right = self._child('CHILD_B', 'PO00028-02', [('WS1', 40), ('WS2', 20)], status='ordered')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders',
                               return_value=[wrong, right]):
            backorder.find_backorder()
        traces = self._traces(backorder)
        self.assertEqual(len(traces), 1)
        payload = traces.json_payload
        # The whole decision is in one block: what was queried, every candidate
        # with its comparison, the chronology and the outcome.
        for fragment in ('parents to query', 'GET purchase-orders?parent_order_id=PARENT1',
                         'candidate PO00028-01 (CHILD_A)', 'candidate PO00028-02 (CHILD_B)',
                         'chronology:', 'MATCH PO00028-02 (CHILD_B)',
                         'raw children payload'):
            self.assertIn(fragment, payload)

    def test_trace_not_stored_when_verbose_logging_is_off(self):
        self.env['ir.config_parameter'].sudo().set_param('webship.verbose_logging', 'False')
        backorder = self._po_picking([(self.p1, 40)], backorder_of=self.original)
        child = self._child('CHILD1', 'PO00028-02', [('WS1', 40)], status='ordered')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]):
            backorder.find_backorder()
        self.assertFalse(self._traces(backorder))

    def test_trace_records_why_nothing_was_linked(self):
        self.env['ir.config_parameter'].sudo().set_param('webship.verbose_logging', 'True')
        backorder = self._po_picking([(self.p1, 40)], backorder_of=self.original)
        child = self._child('CHILD1', 'PO00028-02', [('WS1', 99)], status='ordered')
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=[child]):
            backorder.find_backorder()
        payload = self._traces(backorder).json_payload
        self.assertIn('NO MATCH', payload)
        self.assertIn('closest was PO00028-02 (CHILD1)', payload)
        self.assertIn('chronology pointed at PO00028-02 (CHILD1)', payload)

    # --- Chains: one Odoo PO, two Odoo backorders ---

    def test_second_backorder_links_to_nested_grandchild(self):
        """PO00028 received in three rounds: the second Odoo backorder is a split
        of the first one, so its children hang under the first backorder's
        Stoqflow id."""
        first = self._po_picking([(self.p1, 5)], backorder_of=self.original)
        first.df_po_id_webship = 'CHILD_02'          # linked in the first round
        second = self._po_picking([(self.p1, 2)], backorder_of=first)

        by_parent = {
            'CHILD_02': [
                self._child('GC_03', 'PO00028-03', [('WS1', 5)], status='completed'),
                self._child('GC_04', 'PO00028-04', [('WS1', 2)], status='ordered'),
            ],
            'PARENT1': [
                self._child('CHILD_01', 'PO00028-01', [('WS1', 10)], status='completed'),
                self._child('CHILD_02', 'PO00028-02', [('WS1', 5)], status='ordered'),
            ],
        }
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders',
                               side_effect=lambda endpoint, parent: by_parent.get(parent, [])) as q:
            second._link_stoqflow_backorder()
        # The nearest linked ancestor is queried first and already answers.
        q.assert_called_once_with('purchase-orders', 'CHILD_02')
        self.assertEqual(second.df_po_id_webship, 'GC_04')
        self.assertEqual(second.df_po_code_webship, 'PO00028-04')

    def test_second_backorder_links_when_splits_are_flat_under_the_parent(self):
        """Same three rounds, but Stoqflow hangs every split off the original
        order: querying the first backorder's id returns nothing, so the lookup
        must fall back to the original parent and still pick the right child."""
        first = self._po_picking([(self.p1, 5)], backorder_of=self.original)
        first.df_po_id_webship = 'CHILD_02'
        second = self._po_picking([(self.p1, 2)], backorder_of=first)

        flat = [
            self._child('CHILD_01', 'PO00028-01', [('WS1', 10)], status='completed'),
            self._child('CHILD_02', 'PO00028-02', [('WS1', 5)], status='completed'),
            self._child('CHILD_03', 'PO00028-03', [('WS1', 2)], status='ordered'),
        ]
        by_parent = {'PARENT1': flat}
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders',
                               side_effect=lambda endpoint, parent: by_parent.get(parent, [])) as q:
            second._link_stoqflow_backorder()
        self.assertEqual(
            [call.args for call in q.call_args_list],
            [('purchase-orders', 'CHILD_02'), ('purchase-orders', 'PARENT1')])
        # CHILD_02 is already linked to the first backorder, so only CHILD_03 is
        # left - and it is the open one.
        self.assertEqual(second.df_po_id_webship, 'CHILD_03')
        self.assertEqual(second.df_po_code_webship, 'PO00028-03')

    def test_two_backorders_never_share_a_stoqflow_child(self):
        """Both Odoo backorders hold the same quantity: the second must not grab
        the child the first one is already linked to."""
        first = self._po_picking([(self.p1, 2)], backorder_of=self.original)
        second = self._po_picking([(self.p1, 2)], backorder_of=self.original)
        children = [
            self._child('CHILD_02', 'PO00028-02', [('WS1', 2)], status='ordered'),
            self._child('CHILD_03', 'PO00028-03', [('WS1', 2)], status='ordered'),
        ]
        with mock.patch.object(WebShipHandler, 'find_stoqflow_backorders', return_value=children):
            first._link_stoqflow_backorder()
            second._link_stoqflow_backorder()
        self.assertEqual(first.df_po_id_webship, 'CHILD_02')
        self.assertEqual(second.df_po_id_webship, 'CHILD_03')

    # --- The _create_backorder override must not change the standard flow ---

    def _partial_receipt_backorder(self):
        """Confirm a 10-unit receipt, receive 6, complete it so Odoo's own
        helper creates a backorder for the remaining 4. Returns (picking,
        link_spy) with _link_stoqflow_backorder patched to a spy so no real
        Stoqflow call happens and we can assert whether it was invoked."""
        picking = self._po_picking([(self.p1, 10)])
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.quantity = 6
        picking.move_ids.picked = True
        # Manual validation of a sync-owned ('P') picking is refused; mark it
        # Manual so this fixture can validate it by hand (the guard checks the
        # picking's process code, so the wizard's process() passes too).
        picking.df_process_code = 'M'
        with mock.patch.object(StockPicking, '_link_stoqflow_backorder') as spy:
            res = picking.button_validate()
            # Partial receipt -> Odoo asks to create a backorder; process it.
            if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
                self.env[res['res_model']].with_context(res.get('context', {})).create({}).process()
        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        return picking, backorder, spy

    def test_standard_backorder_unchanged_when_link_disabled(self):
        self.env['ir.config_parameter'].sudo().set_param('webship.link_backorders', 'False')
        picking, backorder, spy = self._partial_receipt_backorder()
        # Odoo's helper still creates exactly one backorder for the remaining 4.
        self.assertEqual(picking.state, 'done')
        self.assertEqual(len(backorder), 1)
        self.assertEqual(sum(backorder.move_ids.mapped('product_uom_qty')), 4.0)
        # And the linking hook is never invoked when the setting is off.
        spy.assert_not_called()

    def test_link_hook_invoked_when_enabled(self):
        self.env['ir.config_parameter'].sudo().set_param('webship.link_backorders', 'True')
        picking, backorder, spy = self._partial_receipt_backorder()
        # Same standard backorder is still created...
        self.assertEqual(len(backorder), 1)
        self.assertEqual(sum(backorder.move_ids.mapped('product_uom_qty')), 4.0)
        # ...and the linking hook runs for it.
        spy.assert_called()

    def test_find_stoqflow_backorders_filters_by_parent(self):
        """Stoqflow ignores ?parent_order_id= and returns the whole collection.
        find_stoqflow_backorders must keep only orders that actually carry the
        requested parent_order_id, otherwise the caller would content-match the
        backorder against every order in the shop."""
        handler = WebShipHandler('u', 'p', 'http://test/')
        handler.set_env(self.env)
        # Server "filter" is a no-op: returns children AND unrelated orders.
        full_list = [
            {'_id': 'A', 'parent_order_id': 'PARENT1', 'order_items': []},
            {'_id': 'B', 'parent_order_id': 'OTHER', 'order_items': []},
            {'_id': 'C', 'order_items': []},                       # no parent at all
            {'_id': 'D', 'parent_order_id': 'PARENT1', 'order_items': []},
        ]
        with mock.patch.object(WebShipHandler, 'performGet',
                               return_value={'status': 'success', 'data': full_list}):
            children = handler.find_stoqflow_backorders('orders', 'PARENT1')
        self.assertEqual([c['_id'] for c in children], ['A', 'D'])
