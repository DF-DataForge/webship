from odoo import models, fields


class PickAnalysisLine(models.Model):
    _name = 'webship.pick.analysis.line'
    _description = 'Stoqflow Pick Analysis Line'
    _order = 'sequence, id'

    picking_id = fields.Many2one('stock.picking', string='Picking', ondelete='cascade')
    sequence = fields.Integer(string='#')

    # Raw Stoqflow IDs from the pick payload
    ws_product_id = fields.Char(string='Stoqflow Product ID')
    ws_parent_product_id = fields.Char(string='Stoqflow Parent Product ID')

    # The Stoqflow ID that was used for the counting lookup
    # (parent_product_id when present, otherwise product_id)
    ws_lookup_id = fields.Char(string='Stoqflow Lookup ID')

    # Resolved Odoo product (the base/parent product this line counts towards)
    odoo_product_id = fields.Many2one('product.product', string='Product')

    # Packaging info (only set when the lookup ID resolved to a packaging record)
    is_box = fields.Boolean(string='Is Box', default=False)
    packaging_id = fields.Many2one('product.packaging', string='Box')
    packaging_qty = fields.Float(string='Qty/Box')

    # Quantities
    quantity = fields.Float(string='Qty Picked')
    total_items = fields.Float(string='Total Items')
    fraction = fields.Float(string='Fraction')

    # Order info
    order_item_qty = fields.Float(string='Qty Ordered')
    is_substitution = fields.Boolean(string='Substitution')

    # Summary row marker
    is_total_line = fields.Boolean(string='Is Total', default=False)
