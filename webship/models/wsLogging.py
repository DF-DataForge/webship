# Model for logging Webship synchronization events.
# Stores the object ID, name, and JSON payload of each sync operation
# for debugging and audit purposes.
from odoo import models, fields

class WSLogging(models.Model):
    _name = 'wslogging'
    _description = 'WebSocket Logging'
    _rec_name = 'object_name'

    # The Odoo record ID of the synced object
    object_id = fields.Integer(string="Object ID")
    # Descriptive name of the synced object (e.g. product name, partner name)
    object_name = fields.Char(string="Object Name")
    # Full JSON payload sent or received during the sync operation
    content = fields.Json(string="Content")
