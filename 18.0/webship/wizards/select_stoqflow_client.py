# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SelectStoqflowClientLine(models.TransientModel):
    _name = 'webship.select.client.line'
    _description = 'Stoqflow Client Match Line'

    wizard_id = fields.Many2one('webship.select.client', string='Wizard', ondelete='cascade')
    stoqflow_id = fields.Char(string='Stoqflow ID', readonly=True)
    name = fields.Char(string='Name', readonly=True)
    email = fields.Char(string='E-mail', readonly=True)
    vat = fields.Char(string='VAT', readonly=True)
    client_number = fields.Char(string='Client Number', readonly=True)

    def action_select(self):
        """Link the chosen Stoqflow client to the Odoo partner and close the wizard."""
        self.ensure_one()
        partner = self.wizard_id.partner_id
        if partner:
            partner.df_client_id_webship = self.stoqflow_id
            partner.df_partner_syncresult_webship = (
                'Manually linked to Stoqflow client %s (%s)' % (self.client_number or self.stoqflow_id, self.name)
            )
        return {'type': 'ir.actions.act_window_close'}


class SelectStoqflowClient(models.TransientModel):
    _name = 'webship.select.client'
    _description = 'Select Stoqflow Client'

    partner_id = fields.Many2one('res.partner', string='Contact', readonly=True)
    match_field = fields.Char(string='Matched by', readonly=True,
                              help="The field used to find these matches (e-mail or VAT).")
    line_ids = fields.One2many('webship.select.client.line', 'wizard_id', string='Matching Clients')
