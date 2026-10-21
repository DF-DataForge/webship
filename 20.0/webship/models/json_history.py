from odoo import models, fields


class JsonHistory(models.Model):
    _name = 'webship.json.history'
    _description = 'Webship JSON History'
    _order = 'create_date desc'

    picking_id = fields.Many2one('stock.picking', string='Picking', ondelete='cascade', index=True)
    direction = fields.Selection([
        ('sent', 'Sent'),
        ('received', 'Received'),
        ('trace', 'Trace'),
    ], string='Direction', required=True)
    endpoint = fields.Char(string='Endpoint')
    method = fields.Char(string='HTTP Method')
    json_payload = fields.Text(string='JSON Payload')
