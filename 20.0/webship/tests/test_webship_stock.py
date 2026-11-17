# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from unittest import mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError

from odoo.addons.webship.models.ws import WebShipHandler


# Trimmed GET /api/v2/products/{id}?detail=high answer as Stoqflow returns it
# for a product kept by batch: one backorder entry (no stock) and one batch.
PRODUCT_DETAIL = {
    "_id": "x672YfmmwbJcMAyvS",
    "type": "basic",
    "has_stock": True,
    "product_items": [
        {"_id": "qtEoCiYjLt4q9TBsE", "backorder": True},
        {"_id": "Nfyz2XpEAPQjRcH7p", "blocked": False, "quantity": 17,
         "batch": "06220123", "expiry_date": "2027-06-30T00:00:00.000Z",
         "delivery_date": "2026-09-22T12:14:19.371Z",
         "location_id": "MaxZnFppajWbcPjXm", "purchase_order_id": "MdYaxqWDGcZPWfW4v"},
    ],
    "sku": "B120GCBS16",
    "name": "Marshmallows Box (16x120g)",
    "checks": {"expiry_dates": True, "batches": True},
    "stock_type": "fefo",
}


def detail(batches=(), unbatched=0.0, tracks_batches=None):
    """What fetchProductBatches yields: the Stoqflow stock per batch of a
    product, plus its stock without batch and whether it keeps batches."""
    batches = [dict(b) for b in batches]
    if tracks_batches is None:
        tracks_batches = bool(batches)
    return {'tracks_batches': tracks_batches, 'batches': batches, 'unbatched': unbatched}


class TestWebshipStock(TransactionCase):
    """The Stoqflow Stock screen (webship.stock) shows one line per product
    and Stoqflow location whatever the number of lots behind it. For a product
    Odoo tracks by lot ("Suivre l'inventaire: par lots") the stock per batch
    is fetched from Stoqflow and each Odoo lot is matched to the batch with
    the same number. Applying Stoqflow stock is always one to one: a line is
    set to its own figure, and one figure is never spread over or duplicated
    on several lines; a line without exactly one counterpart is left alone.

    Background: products tracked by lot get one stock.quant per lot (Stoqflow
    batches become Odoo lots), so the screen built on stock.quant listed the
    same product several times, and setting every lot quant to the product
    total multiplied the Odoo stock by the number of lots."""

    def setUp(self):
        super().setUp()
        parent = self.env.ref('stock.stock_location_stock').location_id
        self.loc = self.env['stock.location'].create({
            'name': 'WS Shop', 'usage': 'internal', 'location_id': parent.id,
            'df_is_webship_location': True, 'df_warehouse_id_webship': 'SHOP',
        })
        self.product = self.env['product.product'].create({
            'name': 'Guimauves', 'default_code': 'B120GV16', 'is_storable': True,
            'tracking': 'lot', 'df_product_id_webship': 'WS1',
        })
        Lot = self.env['stock.lot']
        self.lot_old = Lot.create({
            'name': 'OLD', 'product_id': self.product.id, 'company_id': self.env.company.id})
        self.lot_new = Lot.create({
            'name': 'NEW', 'product_id': self.product.id, 'company_id': self.env.company.id})
        Quant = self.env['stock.quant']
        now = datetime.now()
        Quant._update_available_quantity(
            self.product, self.loc, 15, lot_id=self.lot_old, in_date=now - timedelta(days=30))
        Quant._update_available_quantity(
            self.product, self.loc, 16, lot_id=self.lot_new, in_date=now)

        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _import(self, total, reserved=0, extra_items=None, detail=None):
        """Run the stock import with a stubbed inventory feed. ``detail`` is
        what GET products/{id}?detail=high yields for lot-tracked products
        (None = call failed / not available)."""
        items = [{'sku': 'B120GV16', 'type': 'basic', 'company_id': 'SHOP',
                  'total': total, 'reserved': reserved, 'available': total - reserved}]
        items += extra_items or []
        inventory = {'status': 'success', 'data': {1: items}}
        with mock.patch.object(self.handler, 'fetchInventory', return_value=inventory), \
                mock.patch.object(self.handler, 'fetchProductBatches', return_value=detail):
            self.handler.importStock()

    def _stock_line(self, product):
        """The product's line on the Stoqflow Stock screen. The screen is a
        SQL view: pending ORM writes must reach the database first, and
        values cached from an earlier read of the view are stale."""
        self.env.flush_all()
        self.env.invalidate_all()
        return self.env['webship.stock'].search([
            ('product_id', '=', product.id), ('location_id', '=', self.loc.id)])

    def _line(self):
        return self._stock_line(self.product)

    def _quants(self):
        return self.env['stock.quant'].search([
            ('product_id', '=', self.product.id), ('location_id', '=', self.loc.id)])

    def _by_lot(self):
        """Quantity per lot name; a stock line without lot is under False."""
        return {q.lot_id.name: q.quantity for q in self._quants()}

    def _add_line_without_lot(self, qty):
        """Stock of the lot-tracked product booked without lot, as found on
        the client's database: Odoo has one line with a lot and one without,
        Stoqflow has one batch."""
        self.env['stock.quant']._update_available_quantity(self.product, self.loc, qty)
        return self._quants().filtered(lambda q: not q.lot_id)

    # ------------------------------------------------------------------
    # One line per product
    # ------------------------------------------------------------------

    def test_one_line_per_product(self):
        # Two lot quants in the Stoqflow location -> one line, lots added up.
        self.assertEqual(len(self._quants()), 2)
        self._import(31)
        line = self._line()
        self.assertEqual(len(line), 1)
        self.assertEqual(line.quant_count, 2)
        self.assertEqual(line.quantity, 31)
        self.assertEqual(line.available_quantity, 31)
        self.assertEqual(line.df_webship_totalstock, 31)
        self.assertEqual(line.df_webship_diff_total, 0)

    def test_difference_is_per_product_not_per_lot(self):
        # Odoo 31 (15 + 16) vs Stoqflow 30 -> one difference of 1, not
        # 15 - 30 and 16 - 30 on two lines.
        self._import(30)
        line = self._line()
        self.assertEqual(line.df_webship_totalstock, 30)
        self.assertEqual(line.df_webship_diff_total, 1)
        self.assertTrue(line.df_last_check_webship)

    def test_new_lot_after_import_keeps_figures(self):
        # A lot received after the last import carries no Stoqflow figures
        # yet; the product line must still show the imported figure.
        self._import(31)
        lot = self.env['stock.lot'].create({
            'name': 'LATER', 'product_id': self.product.id, 'company_id': self.env.company.id})
        self.env['stock.quant']._update_available_quantity(
            self.product, self.loc, 4, lot_id=lot)
        line = self._line()
        self.assertEqual(line.quant_count, 3)
        self.assertEqual(line.quantity, 35)
        self.assertEqual(line.df_webship_totalstock, 31)
        self.assertEqual(line.df_webship_diff_total, 4)

    # ------------------------------------------------------------------
    # Stock per batch (GET products/{id}?detail=high)
    # ------------------------------------------------------------------

    def test_fetch_product_batches_reads_detail_payload(self):
        with mock.patch.object(self.handler, 'fetchByKeyDetail',
                               return_value={'status': 'success', 'data': PRODUCT_DETAIL}) as get:
            result = self.handler.fetchProductBatches('x672YfmmwbJcMAyvS')
        get.assert_called_once_with('products', 'x672YfmmwbJcMAyvS')
        # The backorder entry carries no stock and is skipped.
        self.assertEqual(result, {
            'tracks_batches': True,
            'batches': [{'batch': '06220123', 'quantity': 17.0,
                         'expiry_date': '2027-06-30T00:00:00.000Z'}],
            'unbatched': 0.0,
        })

    def test_fetch_product_batches_without_batches(self):
        # A product Stoqflow keeps without batches: its stock items carry
        # no batch, checks.batches is off.
        data = {'has_stock': True, 'checks': {'batches': False},
                'product_items': [{'quantity': 4}, {'quantity': 3}]}
        with mock.patch.object(self.handler, 'fetchByKeyDetail',
                               return_value={'status': 'success', 'data': data}):
            self.assertEqual(self.handler.fetchProductBatches('x'),
                             {'tracks_batches': False, 'batches': [], 'unbatched': 7.0})
        # Batches on and stock without batch next to the batches.
        data = {'has_stock': True, 'checks': {'batches': True},
                'product_items': [{'quantity': 4}, {'quantity': 3, 'batch': 'B1'}]}
        with mock.patch.object(self.handler, 'fetchByKeyDetail',
                               return_value={'status': 'success', 'data': data}):
            self.assertEqual(self.handler.fetchProductBatches('x'), {
                'tracks_batches': True, 'unbatched': 4.0,
                'batches': [{'batch': 'B1', 'quantity': 3.0, 'expiry_date': None}]})

    def test_fetch_product_batches_unknown_is_none(self):
        with mock.patch.object(self.handler, 'fetchByKeyDetail',
                               return_value={'status': 'error', 'code': 500, 'txt': ''}):
            self.assertIsNone(self.handler.fetchProductBatches('x672YfmmwbJcMAyvS'))
        self.assertIsNone(self.handler.fetchProductBatches(False))
        # No product_items: fine for a product without stock, unknown otherwise.
        with mock.patch.object(self.handler, 'fetchByKeyDetail',
                               return_value={'status': 'success',
                                             'data': {'has_stock': False, 'checks': {'batches': True}}}):
            self.assertEqual(self.handler.fetchProductBatches('x'),
                             {'tracks_batches': True, 'batches': [], 'unbatched': 0.0})
        with mock.patch.object(self.handler, 'fetchByKeyDetail',
                               return_value={'status': 'success', 'data': {'has_stock': True}}):
            self.assertIsNone(self.handler.fetchProductBatches('x'))

    def test_lot_figures_matched_by_lot_number(self):
        # Stoqflow holds the whole 31 on batch OLD: the product total agrees
        # with Odoo (15 + 16) while both lots are off.
        self._import(31, detail=detail([{'batch': 'OLD', 'quantity': 31, 'expiry_date': None}]))
        by_name = {q.lot_id.name: q for q in self._quants()}
        self.assertEqual(by_name['OLD'].df_webship_lot_stock, 31)
        self.assertEqual(by_name['OLD'].df_webship_lot_diff, -16)
        self.assertEqual(by_name['NEW'].df_webship_lot_stock, 0)
        self.assertEqual(by_name['NEW'].df_webship_lot_diff, 16)
        self.assertTrue(by_name['OLD'].df_webship_lot_checked)
        self.assertTrue(by_name['NEW'].df_webship_lot_checked)
        line = self._line()
        self.assertEqual(line.df_webship_diff_total, 0)
        self.assertEqual(line.lot_diff_count, 2)

    def test_lots_in_sync(self):
        self._import(31, detail=detail([{'batch': 'OLD', 'quantity': 15},
                                        {'batch': 'NEW', 'quantity': 16}]))
        self.assertEqual(self._line().lot_diff_count, 0)
        self.assertEqual(set(self._quants().mapped('df_webship_lot_diff')), {0.0})

    def test_unknown_batch_gets_lot_and_empty_quant(self):
        self._import(36, detail=detail([
            {'batch': 'OLD', 'quantity': 15}, {'batch': 'NEW', 'quantity': 16},
            {'batch': 'X1', 'quantity': 5, 'expiry_date': '2027-06-30T00:00:00.000Z'}]))
        lot = self.env['stock.lot'].search([
            ('name', '=', 'X1'), ('product_id', '=', self.product.id)])
        self.assertEqual(len(lot), 1)
        if 'expiration_date' in lot._fields:
            self.assertEqual(lot.expiration_date, datetime(2027, 6, 30))
        quant = self._quants().filtered(lambda q: q.lot_id == lot)
        self.assertEqual(len(quant), 1)
        self.assertEqual(quant.quantity, 0)
        self.assertEqual(quant.df_webship_lot_stock, 5)
        self.assertEqual(quant.df_webship_lot_diff, -5)
        line = self._line()
        self.assertEqual(line.quant_count, 3)
        self.assertEqual(line.lot_diff_count, 1)
        self.assertEqual(line.df_webship_diff_total, -5)

    def test_batch_fetch_failure_keeps_product_figures(self):
        # Per-batch call failed: the product figures are still imported and
        # the lots are simply not compared this run.
        self._import(30, detail=None)
        line = self._line()
        self.assertEqual(line.df_webship_totalstock, 30)
        self.assertEqual(line.lot_diff_count, 0)
        self.assertFalse(any(self._quants().mapped('df_webship_lot_checked')))

    def test_line_without_lot_is_unmatched(self):
        # Odoo: one line with lot OLD, one without; Stoqflow: one batch OLD
        # and no stock without batch. The line without lot has no
        # counterpart: it is not matched (no lot check) and keeps showing
        # its quantity as difference.
        no_lot = self._add_line_without_lot(9)
        self._import(7, detail=detail([{'batch': 'OLD', 'quantity': 7}]))
        self.assertFalse(no_lot.df_webship_lot_checked)
        self.assertEqual(no_lot.df_webship_lot_stock, 0)
        self.assertEqual(no_lot.df_webship_lot_diff, 9)
        self.assertEqual(self._line().quantity, 40)
        self.assertEqual(self._line().lot_diff_count, 2)

    def test_line_without_lot_matches_stock_without_batch(self):
        # Stoqflow holds 3 without batch next to batch OLD: that figure is
        # the counterpart of the Odoo line without lot.
        no_lot = self._add_line_without_lot(9)
        self._import(10, detail=detail([{'batch': 'OLD', 'quantity': 7}], unbatched=3))
        self.assertTrue(no_lot.df_webship_lot_checked)
        self.assertEqual(no_lot.df_webship_lot_stock, 3)
        self.assertEqual(no_lot.df_webship_lot_diff, 6)

    def test_stoqflow_without_batches_single_line(self):
        # Odoo tracks by lot, Stoqflow keeps no batches for the product and
        # Odoo has exactly one line: the product figure is that line's.
        nougat = self.env['product.product'].create({
            'name': 'Nougat', 'default_code': 'NOUG1', 'is_storable': True,
            'tracking': 'lot', 'df_product_id_webship': 'WS2',
        })
        lot = self.env['stock.lot'].create({
            'name': 'N1', 'product_id': nougat.id, 'company_id': self.env.company.id})
        self.env['stock.quant']._update_available_quantity(nougat, self.loc, 4, lot_id=lot)
        inventory = {'status': 'success', 'data': {1: [
            {'sku': 'NOUG1', 'type': 'basic', 'company_id': 'SHOP',
             'total': 6, 'reserved': 0, 'available': 6}]}}
        with mock.patch.object(self.handler, 'fetchInventory', return_value=inventory), \
                mock.patch.object(self.handler, 'fetchProductBatches',
                                  return_value=detail(unbatched=6, tracks_batches=False)):
            self.handler.importStock()
        quant = self.env['stock.quant'].search([('product_id', '=', nougat.id)])
        self.assertEqual(quant.df_webship_lot_stock, 6)
        self.assertTrue(quant.df_webship_lot_checked)
        self._stock_line(nougat).action_apply_webship_stock()
        self.assertEqual(quant.quantity, 6)

    def test_stoqflow_without_batches_several_lines_unmatched(self):
        # Odoo has two lots, Stoqflow one figure for the product: there is no
        # one-to-one match, nothing is applied.
        self._import(30, detail=detail(unbatched=30, tracks_batches=False))
        self.assertFalse(any(self._quants().mapped('df_webship_lot_checked')))
        self.assertEqual(self._line().lot_diff_count, 0)
        self.assertEqual(self._line().df_webship_diff_total, 1)
        with self.assertRaises(UserError):
            self._line().action_apply_webship_stock()
        self.assertEqual(self._by_lot(), {'OLD': 15.0, 'NEW': 16.0})

    # ------------------------------------------------------------------
    # Apply Stoqflow stock to Odoo: one to one, matched by lot
    # ------------------------------------------------------------------

    def test_apply_sets_each_lot_to_its_batch(self):
        # Stoqflow: 17 on OLD, nothing on NEW -> Odoo gets exactly that.
        self._import(17, detail=detail([{'batch': 'OLD', 'quantity': 17}]))
        self._line().action_apply_webship_stock()
        by_lot = self._by_lot()
        self.assertEqual(by_lot['OLD'], 17.0)
        self.assertEqual(by_lot.get('NEW', 0.0), 0.0)
        self.assertEqual(sum(self._quants().mapped('quantity')), 17)
        self.assertEqual(self._line().lot_diff_count, 0)

    def test_apply_creates_stock_on_new_batch(self):
        self._import(36, detail=detail([
            {'batch': 'OLD', 'quantity': 15}, {'batch': 'NEW', 'quantity': 16},
            {'batch': 'X1', 'quantity': 5}]))
        self._line().action_apply_webship_stock()
        self.assertEqual(self._by_lot(), {'OLD': 15.0, 'NEW': 16.0, 'X1': 5.0})

    def test_apply_never_touches_unmatched_line_without_lot(self):
        # Odoo: lot OLD 15, lot NEW 16, no lot 9; Stoqflow: batch OLD 7.
        # Only the lot lines get their own figure; the line without lot is
        # left alone, the figure is never spread over two lines.
        no_lot = self._add_line_without_lot(9)
        self._import(7, detail=detail([{'batch': 'OLD', 'quantity': 7}]))
        self._line().action_apply_webship_stock()
        by_lot = self._by_lot()
        self.assertEqual(by_lot['OLD'], 7.0)
        self.assertEqual(by_lot.get('NEW', 0.0), 0.0)
        self.assertEqual(no_lot.quantity, 9.0)
        self.assertEqual(sum(self._quants().mapped('quantity')), 16)

    def test_apply_matched_line_without_lot(self):
        no_lot = self._add_line_without_lot(9)
        self._import(10, detail=detail([{'batch': 'OLD', 'quantity': 7}], unbatched=3))
        self._line().action_apply_webship_stock()
        self.assertEqual(no_lot.quantity, 3.0)
        self.assertEqual(self._by_lot()['OLD'], 7.0)

    def test_apply_refuses_without_lot_figures(self):
        # The product total alone is never applied to a product with several
        # lot lines: no spreading, no duplicating. Nothing changes.
        self._import(30, detail=None)
        with self.assertRaises(UserError):
            self._line().action_apply_webship_stock()
        self.assertEqual(self._by_lot(), {'OLD': 15.0, 'NEW': 16.0})

    def test_apply_ignores_stale_lot_figures(self):
        # Lot figures from an earlier import must not be applied after a
        # later import whose per-batch call failed.
        self._import(31, detail=detail([{'batch': 'OLD', 'quantity': 31}]))
        self._import(30, detail=None)
        with self.assertRaises(UserError):
            self._line().action_apply_webship_stock()
        self.assertEqual(self._by_lot(), {'OLD': 15.0, 'NEW': 16.0})

    def test_apply_in_sync_changes_nothing(self):
        self._import(31, detail=detail([{'batch': 'OLD', 'quantity': 15},
                                        {'batch': 'NEW', 'quantity': 16}]))
        self._line().action_apply_webship_stock()
        self.assertEqual(self._by_lot(), {'OLD': 15.0, 'NEW': 16.0})

    def test_apply_refuses_unfetched_product(self):
        self.assertFalse(self._line().df_last_check_webship)
        with self.assertRaises(UserError):
            self._line().action_apply_webship_stock()
        self.assertEqual(self._by_lot(), {'OLD': 15.0, 'NEW': 16.0})

    def test_details_apply_selected_line_only(self):
        # In the details list only the selected lot is set to its figure.
        self._import(7, detail=detail([{'batch': 'OLD', 'quantity': 7}]))
        self._quants().filtered(lambda q: q.lot_id == self.lot_new).action_apply_webship_stock()
        self.assertEqual(self._by_lot().get('NEW', 0.0), 0.0)
        self.assertEqual(self._by_lot()['OLD'], 15.0)

    def test_details_apply_unmatched_line_refuses(self):
        no_lot = self._add_line_without_lot(9)
        self._import(7, detail=detail([{'batch': 'OLD', 'quantity': 7}]))
        with self.assertRaises(UserError):
            no_lot.action_apply_webship_stock()
        self.assertEqual(no_lot.quantity, 9.0)

    def test_auto_adjust_per_lot(self):
        self.env['ir.config_parameter'].sudo().set_str('webship.adjust_odoo_stock', 'True')
        self._import(17, detail=detail([{'batch': 'OLD', 'quantity': 17}]))
        by_lot = self._by_lot()
        self.assertEqual(by_lot['OLD'], 17.0)
        self.assertEqual(by_lot.get('NEW', 0.0), 0.0)

    def test_auto_adjust_skips_unmatched_lines(self):
        # Automatic adjustment never spreads the total either: lot lines get
        # their figure, the line without lot stays, the import goes on.
        no_lot = self._add_line_without_lot(9)
        self.env['ir.config_parameter'].sudo().set_str('webship.adjust_odoo_stock', 'True')
        self._import(7, detail=detail([{'batch': 'OLD', 'quantity': 7}]))
        self.assertEqual(self._by_lot()['OLD'], 7.0)
        self.assertEqual(no_lot.quantity, 9.0)
        # Without per-batch figures nothing is applied at all.
        self._import(5, detail=None)
        self.assertEqual(self._by_lot()['OLD'], 7.0)
        self.assertEqual(no_lot.quantity, 9.0)

    def test_untracked_product_set_exactly(self):
        # A product without lots has a single quant: it is set to the total
        # and its line figure is the product total. No per-batch call.
        widget = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1', 'is_storable': True,
        })
        self.env['stock.quant']._update_available_quantity(widget, self.loc, 5)
        self.env['ir.config_parameter'].sudo().set_str('webship.adjust_odoo_stock', 'True')
        with mock.patch.object(self.handler, 'fetchProductBatches') as fetch:
            inventory = {'status': 'success', 'data': {1: [
                {'sku': 'SKU1', 'type': 'basic', 'company_id': 'SHOP',
                 'total': 9, 'reserved': 0, 'available': 9}]}}
            with mock.patch.object(self.handler, 'fetchInventory', return_value=inventory):
                self.handler.importStock()
        fetch.assert_not_called()
        quant = self.env['stock.quant'].search([
            ('product_id', '=', widget.id), ('location_id', '=', self.loc.id)])
        self.assertEqual(len(quant), 1)
        self.assertEqual(quant.quantity, 9)
        self.assertEqual(quant.df_webship_lot_stock, 9)
        self.assertEqual(quant.df_webship_lot_diff, 0)
        line = self._stock_line(widget)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.quantity, 9)
        self.assertEqual(line.df_webship_diff_total, 0)
        self.assertEqual(line.lot_diff_count, 0)

    def test_details_action_opens_the_lots(self):
        action = self._line().action_view_quants()
        self.assertEqual(action['res_model'], 'stock.quant')
        quants = self.env['stock.quant'].search(action['domain'])
        self.assertEqual(quants, self._quants())

    def test_row_click_opens_the_product(self):
        # Both the stock-line list and the per-product list open the product.
        for action in (self._line().action_open_product(),
                       self._quants()[0].action_df_open_product()):
            self.assertEqual(action['res_model'], 'product.product')
            self.assertEqual(action['res_id'], self.product.id)
            self.assertEqual(action['view_mode'], 'form')

    def test_apply_selection_with_unmatched_line_warns(self):
        # Selecting every line of the product, the no-lot one included: the
        # lot lines get their figure, the no-lot line is left alone and the
        # user gets a warning naming it, after which the list reloads.
        no_lot = self._add_line_without_lot(9)
        self._import(7, detail=detail([{'batch': 'OLD', 'quantity': 7}]))
        result = self._quants().action_apply_webship_stock()
        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(result['params']['type'], 'warning')
        self.assertIn('without lot', result['params']['message'])
        self.assertEqual(result['params']['next'], {'type': 'ir.actions.act_window_close'})
        self.assertEqual(self._by_lot()['OLD'], 7.0)
        self.assertEqual(no_lot.quantity, 9.0)
        # All selected lines applied: no warning.
        self.assertTrue(self._quants().filtered('lot_id').action_apply_webship_stock() is True)

    def test_lot_numbers_and_expiry_on_the_line(self):
        line = self._line()
        self.assertEqual(line.lot_names, 'NEW, OLD')
        Lot = self.env['stock.lot']
        if 'expiration_date' not in Lot._fields:
            self.assertFalse(line.expiration_date)
            self.assertFalse(self._quants().mapped('df_webship_expiration_date')[0])
            return
        self.lot_old.expiration_date = datetime(2027, 1, 31)
        self.lot_new.expiration_date = datetime(2027, 6, 30)
        # The line shows the first expiry; each stock line shows its lot's.
        self.assertEqual(self._line().expiration_date, datetime(2027, 1, 31))
        by_name = {q.lot_id.name: q.df_webship_expiration_date for q in self._quants()}
        self.assertEqual(by_name, {'OLD': datetime(2027, 1, 31), 'NEW': datetime(2027, 6, 30)})
