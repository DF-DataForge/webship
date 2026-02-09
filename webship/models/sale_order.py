from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    df_order_id_webship = fields.Char("Order id webship", readOnly=True)

    def write(self, values):
        if False:
            modl = self.env['ir.model'].search([('model','=','sale.order')])

            self.env['webship.events'].create({'modelTableKey':self.id, 'model':modl.id, 'status':'P', 'processTime':datetime.now(), 'dbAction':'U', 'product_id_webship':self.df_order_id_webship})

        result = super(SaleOrder, self).write(values)
        return result

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('sale_id', '=', self.id)]
        action['context'] = {'default_sale_id': self.id}
        return action