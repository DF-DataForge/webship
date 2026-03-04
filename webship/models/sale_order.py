# Extends sale.order with a Webship order reference field
# and adds a helper action to view related stock pickings.
from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Webship order ID linked to this sale order (set during sync)
    df_order_id_webship = fields.Char("Order id Stoqflow", readOnly=True)

    def action_view_pickings(self):
        """Open a list view of all stock pickings related to this sale order.
        Triggered from a button on the sale order form."""
        self.ensure_one()
        # Load the stock picking tree action and filter by this sale order
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('sale_id', '=', self.id)]
        action['context'] = {'default_sale_id': self.id}
        return action
