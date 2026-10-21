# -*- coding: utf-8 -*-
# Transient wizard that shows, per picking, every product with its Odoo
# ordered quantity next to the Stoqflow ordered quantity. Populated by
# stock.picking.compare_detail (see models/picking.py).
from odoo import models, fields


class WebshipCompareDetailLine(models.TransientModel):
    _name = 'webship.compare.detail.line'
    _description = 'Stoqflow Compare Detail Line'

    wizard_id = fields.Many2one('webship.compare.detail', string='Wizard', ondelete='cascade')
    product_name = fields.Char(string='Product', readonly=True)
    sku = fields.Char(string='SKU / Code', readonly=True)
    stoqflow_product_id = fields.Char(string='Stoqflow product id', readonly=True)
    odoo_qty = fields.Float(string='Odoo qty', readonly=True)
    stoqflow_qty = fields.Float(string='Stoqflow qty', readonly=True)
    status = fields.Selection([
        ('match', 'Match'),
        ('mismatch', 'Quantity mismatch'),
        ('missing_in_stoqflow', 'Missing in Stoqflow'),
        ('missing_in_odoo', 'Missing in Odoo'),
        ('unresolved', 'Unmatched product'),
    ], string='Status', readonly=True)
    message = fields.Char(string='Detail', readonly=True)


class WebshipCompareDetail(models.TransientModel):
    _name = 'webship.compare.detail'
    _description = 'Stoqflow Compare Detail'

    picking_id = fields.Many2one('stock.picking', string='Picking', readonly=True)
    order_found = fields.Boolean(string='Stoqflow order found', readonly=True)
    message = fields.Char(string='Message', readonly=True)
    line_ids = fields.One2many('webship.compare.detail.line', 'wizard_id', string='Products')
