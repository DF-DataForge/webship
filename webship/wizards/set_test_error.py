# -*- coding: utf-8 -*-
from odoo import models, fields


class WebshipTestSetError(models.TransientModel):
    _name = 'webship.test.set.error'
    _description = 'TEST: set Stoqflow error state on picking'

    # Which known error state to reproduce on the selected picking(s).
    error_type = fields.Selection([
        ('unique', 'Reference must be unique (POST error)'),
        ('no_id', 'No Stoqflow order ID or PO ID set'),
    ], string='Error to set', required=True, default='unique')

    def action_apply(self):
        """Put the pickings selected in the Action menu into the chosen error
        state. Neutralized databases only (enforced in the model helper)."""
        self.ensure_one()
        pickings = self.env['stock.picking'].browse(
            self.env.context.get('active_ids', []))
        pickings._webship_test_set_error_state(self.error_type)
        return {'type': 'ir.actions.act_window_close'}
