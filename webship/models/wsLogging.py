from odoo import models, fields

class WSLogging(models.Model):
    _name = 'wslogging'
    _description = 'WebSocket Logging'
    _rec_name = 'object_name'

    object_id = fields.Integer(string="Object ID")
    object_name = fields.Char(string="Object Name")
    content = fields.Json(string="Content")