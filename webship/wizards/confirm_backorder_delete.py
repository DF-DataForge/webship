# -*- coding: utf-8 -*-
from odoo import models, fields


class WebshipBackorderConfirmDelete(models.TransientModel):
    _name = 'webship.backorder.confirm.delete'
    _description = 'Confirm Backorder Deletion'

    backorder_ids = fields.Many2many('webship.backorder', string='Backorders')
    warning_message = fields.Text('Warning', readonly=True)

    def action_confirm(self):
        """User confirmed deletion despite the missing Odoo backorder."""
        return self.backorder_ids._execute_delete(self.backorder_ids, force=True)
