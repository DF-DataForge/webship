# -*- coding: utf-8 -*-
from odoo import models, fields


class WebshipRetourConfirmReturn(models.TransientModel):
    _name = 'webship.retour.confirm.return'
    _description = 'Confirm Return Picking Creation'

    retour_id = fields.Many2one('webship.retour.and.backorder', string='Retour')
    warning_message = fields.Text('Warning', readonly=True)

    def action_confirm(self):
        """User confirmed creating a return picking despite the retour not being delivered."""
        self.retour_id.df_process_code = 'P'
        self.retour_id._create_return_picking(self.retour_id)
        if self.retour_id.return_picking_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Return Picking',
                    'message': 'Return picking %s created successfully.' % self.retour_id.return_picking_id.name,
                    'type': 'success',
                    'sticky': False,
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Return Picking',
                'message': 'Could not create return picking. Check that a matching sale order and done outgoing picking exist.',
                'type': 'warning',
                'sticky': False,
            },
        }
