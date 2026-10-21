# -*- coding: utf-8 -*-
import logging

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.ws import WebShipHandler

_logger = logging.getLogger(__name__)


class TestRetours(TransactionCase):
    """Scenario 11 (Stoqflow -> Odoo): a Stoqflow purchase order flagged as a
    retour is stored as a webship.retour.and.backorder record (11a); a duplicate
    (same Stoqflow id) updates the existing record instead of creating a new one
    (11d); and a retour with no matching Odoo sale order is left in error with a
    clear message and no return picking (11c)."""

    def setUp(self):
        super().setUp()
        self.Retour = self.env['webship.retour.and.backorder']
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)
        self.product = self.env['product.product'].create({
            'name': 'Widget', 'default_code': 'SKU1', 'df_product_id_webship': 'WS1'})

    @staticmethod
    def _po(stoqflow_id='RET1', number='PO-RET-1'):
        # No supplier_id (skips the supplier GET) and a supplier_reference that
        # contains 'Retour' but no 'SO<n>' (so no original-order lookup fires).
        return {
            '_id': stoqflow_id, 'order_number': number, 'status': 'concept',
            'supplier_reference': 'Retour zonder order',
            'order_items': [{'_id': 'L1', 'product_id': 'WS1', 'quantity': 2}],
        }

    def _dump(self, retour, label):
        _logger.info("TRACE[%s] retour id=%s stoqflow_id=%r name=%r order_or_po=%r "
                     "process=%r original_ref=%r sale_order=%s return_picking=%s error=%r",
                     label, retour.id, retour.df_stoqflow_id, retour.name,
                     retour.order_or_po, retour.df_process_code,
                     retour.df_original_order_ref, retour.sale_order_id.id,
                     retour.return_picking_id.id, retour.df_error_message)

    def test_retour_detected_and_stored_no_so_errors(self):
        # 11a: the retour record is created; 11c: no matching sale order ->
        # error status with an explanatory message, and no return picking.
        self.Retour._sync_retour_record(self._po(), self.handler, 'purchase_order')

        retour = self.Retour.search([('df_stoqflow_id', '=', 'RET1')])
        self.assertEqual(len(retour), 1, "n_retours=%s" % len(retour))
        self._dump(retour, '11a/11c')
        self.assertEqual(retour.name, 'PO-RET-1', "name=%r" % retour.name)
        self.assertEqual(retour.order_or_po, 'purchase_order',
                         "order_or_po=%r" % retour.order_or_po)
        self.assertEqual(retour.supplier_reference, 'Retour zonder order',
                         "supplier_reference=%r" % retour.supplier_reference)
        self.assertEqual(retour.df_process_code, 'E',
                         "process_code=%r error=%r" % (retour.df_process_code, retour.df_error_message))
        self.assertIn('No matching sale order', retour.df_error_message or '',
                      "error=%r" % retour.df_error_message)
        self.assertFalse(retour.return_picking_id,
                         "unexpected return_picking=%s" % retour.return_picking_id.id)

    def test_duplicate_retour_updates_existing(self):
        # 11d: same Stoqflow id -> the existing record is updated, not duplicated.
        self.Retour._sync_retour_record(self._po(number='PO-RET-1'),
                                        self.handler, 'purchase_order')
        self.Retour._sync_retour_record(self._po(number='PO-RET-2'),
                                        self.handler, 'purchase_order')

        retours = self.Retour.search([('df_stoqflow_id', '=', 'RET1')])
        _logger.info("TRACE[11d] n_retours=%s names=%s",
                     len(retours), retours.mapped('name'))
        self.assertEqual(len(retours), 1,
                         "duplicate retour created %s records: %s"
                         % (len(retours), retours.mapped('name')))
        self.assertEqual(retours.name, 'PO-RET-2',
                         "name=%r (expected updated to PO-RET-2)" % retours.name)
