# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestRetourSaleOrderMatch(TransactionCase):
    """Risk 11b: a retour must resolve its original sale order by an EXACT,
    UNIQUE name match. The old 'ilike' + limit=1 could match SO123 for a ref of
    'SO12' (or pick an arbitrary order among several substring matches)."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Cust'})

    def _sale_order(self, name):
        so = self.env['sale.order'].create({'partner_id': self.partner.id})
        so.name = name
        return so

    def _retour(self, supplier_reference, sid):
        return self.env['webship.retour.and.backorder'].create({
            'df_stoqflow_id': sid,
            'supplier_reference': supplier_reference,
        })

    def test_exact_match_not_substring(self):
        target = self._sale_order('SO123')
        self._sale_order('SO1230')  # substring collision the old ilike would hit
        retour = self._retour('Retour SO123', 'WS1')
        self.assertEqual(retour.df_original_order_ref, 'SO123')
        self.assertEqual(retour.sale_order_id, target)

    def test_no_exact_match_does_not_guess(self):
        # Only substring-collision orders exist; an exact 'SO99' match is absent,
        # and there is no picking to fall back to -> no sale order is guessed.
        self._sale_order('SO990')
        self._sale_order('SO991')
        retour = self._retour('Retour SO99', 'WS2')
        self.assertEqual(retour.df_original_order_ref, 'SO99')
        self.assertFalse(retour.sale_order_id)
