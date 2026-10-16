# Extends res.partner with Webship client and supplier synchronization fields.
# Partners can be flagged as Webship clients, suppliers, or both,
# and synced/matched against the Webship API.
from odoo.addons.webship.models.ws import WebShipHandler
from odoo import models, fields, api

from datetime import datetime

class Partner(models.Model):
    _inherit = 'res.partner'

    # Webship supplier ID (set when the partner is synced as a supplier)
    df_supplier_id_webship = fields.Char("Supplier id Stoqflow", readonly=True)
    # Whether this partner should be treated as a supplier in Stoqflow
    df_is_supplier_in_webship = fields.Boolean("Supplier in Stoqflow", default=False)
    # Stoqflow client ID (set when the partner is synced as a client)
    df_client_id_webship = fields.Char("Client id Stoqflow", readonly=True)
    # Whether this partner should be treated as a client in Stoqflow
    df_is_client_in_webship = fields.Boolean("Client in Stoqflow", default=True)
    # Timestamp of the last push to Stoqflow
    df_last_webship_sync = fields.Datetime("Laatste wijziging gepusht naar Stoqflow op")
    # sha256 of the last client payload successfully pushed to Stoqflow.
    # WebShipHandler.sync_partner compares against this to skip redundant
    # PUT clients/{id} calls when nothing changed since the last push.
    df_webship_payload_hash = fields.Char(
        "Stoqflow client payload hash", readonly=True, copy=False)
    # HTML result message of the last sync attempt
    df_partner_syncresult_webship = fields.Html("Resultaat laatste sync")

    # Client code fetched from the Webship API (e.g. "CO0000123")
    df_client_code_webship = fields.Char("Client code Stoqflow", compute="_compute_code_client", store=True)

    # Supplier code fetched from the Webship API (e.g. "SO0000456")
    df_supplier_code_webship = fields.Char("Supplier code Stoqflow", compute="_compute_code_supplier", store=True)

    # Clickable HTML link to open the client in the Webship web app
    df_url_client = fields.Html("Client link Stoqflow", compute="_compute_html_client", sanitize=False)
    # Clickable HTML link to open the supplier in the Stoqflow web app
    df_url_supplier  = fields.Html('Supplier link Stoqflow', compute="_compute_html_supplier", sanitize=False)

    # Default internal note automatically added to every shipment for this partner
    df_standard_internal_note = fields.Text("Standaard interne notitie voor pakket", help="Deze notitie wordt automatisch toegevoegd aan elke zending voor deze klant.")

    @api.depends("df_client_id_webship")
    def _compute_code_client(self):
        """Fetch the human-readable client code from the Webship API
        whenever the Webship client ID changes."""
        wsHandler = self.getHandler()
        for record in self:
            if record.df_client_id_webship != False:
                record.df_client_code_webship = wsHandler.fetchCode('clients', str(record.df_client_id_webship))
            else:
                record.df_client_code_webship = ''

    @api.depends("df_supplier_id_webship")
    def _compute_code_supplier(self):
        """Fetch the human-readable supplier code from the Webship API
        whenever the Webship supplier ID changes."""
        wsHandler = self.getHandler()
        for record in self:
            if record.df_supplier_id_webship != False:
                record.df_supplier_code_webship = wsHandler.fetchCode('suppliers', str(record.df_supplier_id_webship))
            else:
                record.df_supplier_code_webship = ''

    @api.depends("df_client_id_webship")
    def _compute_html_client(self):
        """Build an HTML snippet with the client code and a clickable icon
        linking to the client page in the Webship web application."""
        for record in self:
            if record.df_client_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param('webship.base_app_url') + 'clients/' + record.df_client_id_webship
                record.df_url_client = record.df_client_code_webship +' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
            else:
                record.df_url_client = ''

    @api.depends("df_supplier_id_webship")
    def _compute_html_supplier(self):
        """Build an HTML snippet with the supplier code and a clickable icon
        linking to the supplier page in the Webship web application."""
        for record in self:
            if record.df_supplier_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'suppliers/' + record.df_supplier_id_webship
                record.df_url_supplier = record.df_supplier_code_webship + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
            else:
                record.df_url_supplier = ''

    def getHandler(self):
        """Create and return a WebShipHandler instance using the stored API credentials."""
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)

        return wsHandler

    def _open_select_client_wizard(self, record, match_result):
        """Open a wizard popup letting the user pick from multiple Stoqflow client matches."""
        line_vals = []
        for client in match_result['multiple']:
            line_vals.append((0, 0, {
                'stoqflow_id': client.get('_id', ''),
                'name': client.get('name', ''),
                'email': client.get('email', ''),
                'vat': client.get('vat', ''),
                'client_number': client.get('client_number', ''),
            }))
        wizard = self.env['webship.select.client'].create({
            'partner_id': record.id,
            'match_field': match_result['match_field'],
            'line_ids': line_vals,
        })
        return {
            'name': 'Multiple Stoqflow clients found',
            'type': 'ir.actions.act_window',
            'res_model': 'webship.select.client',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def ws_match_supplier(self):
        """Match this partner to a Stoqflow supplier using the configured matching sequence.
        Links the supplier ID without requiring the 'Sync as supplier' flag."""
        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        for record in self:
            match_result = wsHandler.match_supplier_by_sequence(record)
            sResult = match_result['errors']

            if sResult == []:
                record.df_partner_syncresult_webship = (
                    '<p>Successfully linked to Stoqflow supplier</p>'
                )
            else:
                sOutput = '<p>Errors occured:</p><ul>'
                for e in sResult:
                    sOutput += '<li>' + e + '</li>'
                sOutput += '</ul>'
                record.df_partner_syncresult_webship = sOutput

    def ws_match_partner(self):
        """Attempt to find this partner in Webship using the configured matching sequence.
        Searches as client, supplier, or both depending on the partner flags.
        If multiple Stoqflow clients match, opens a selection popup.
        Displays the result (success or errors) in the sync result field."""
        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        for record in self:
            sResult = None
            match_result = None

            # Try matching as client if flagged (uses the configured matching sequence)
            if record.df_is_client_in_webship:
                match_result = wsHandler.match_partner_by_sequence(record)
                # If multiple matches found, open wizard to let user select
                if match_result.get('multiple'):
                    record.df_partner_syncresult_webship = match_result['errors'][0] if match_result['errors'] else 'Multiple clients found'
                    return self._open_select_client_wizard(record, match_result)
                sResult = match_result['errors']

            # Try matching as supplier if flagged (uses the configured matching sequence)
            if record.df_is_supplier_in_webship:
                supplier_match_result = wsHandler.match_supplier_by_sequence(record)
                sResult = supplier_match_result['errors']

            # If neither flag is set, inform the user
            if record.df_is_client_in_webship == False and record.df_is_supplier_in_webship == False:
                sResult = ['Please set to client or supplier']

            # Display success or format errors as an HTML list
            if sResult == []:
                self.df_partner_syncresult_webship = 'Success'
            else:
                sOutput = '<p>Errors occured:</p>'
                sOutput = sOutput + '<ul>'
                for e in sResult:
                    sOutput += '<li>' + e + '</li>'
                sOutput = sOutput + '</ul>'

                self.df_partner_syncresult_webship = sOutput

    def ws_sync_partner(self):
        """Push this partner's data to Webship (create or update).
        Syncs as client, supplier, or both depending on the partner flags.
        Displays the result (success or errors) in the sync result field."""
        wsHandler = self.getHandler()

        for record in self:
            sResult = []
            # Sync as client to Webship if flagged. force=True: a manual
            # sync must always push, even when the payload hash says
            # nothing changed (e.g. to repair drift on the Stoqflow side).
            if record.df_is_client_in_webship:
                sResult += wsHandler.sync_partner(record, force=True)
            # Sync as supplier to Webship if flagged
            if record.df_is_supplier_in_webship:
                sResult += wsHandler.sync_supplier(record)

            # If neither flag is set, inform the user
            if record.df_is_client_in_webship == False and record.df_is_supplier_in_webship == False:
                sResult = ['Please set to client or supplier']

            # Display success or format errors as an HTML list
            if sResult == []:
                self.df_partner_syncresult_webship = 'Success'
            else:
                sOutput = '<p>Errors occured:</p>'
                sOutput = sOutput + '<ul>'
                for e in sResult:
                    sOutput += '<li>' + e + '</li>'
                sOutput = sOutput + '</ul>'

                self.df_partner_syncresult_webship = sOutput
