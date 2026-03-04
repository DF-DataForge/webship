# Extends stock.location with Webship-specific fields.
# Allows marking a stock location as a "Webship location" so the module
# knows which pickings should be synchronized with the Webship API.
from odoo import models, fields

class StockLocations(models.Model):
    _inherit = 'stock.location'

    # Legacy field: Webship warehouse ID stored directly on the location
    df_warehouse_id_webship = fields.Char("Warehouse id Stoqflow")

    # Stoqflow shop ID associated with this location
    df_shop_id_webship = fields.Char("Shop id Stoqflow", readOnly=True)

    # Flag indicating whether this location is managed by Stoqflow.
    # Pickings going to/from Stoqflow locations trigger synchronization.
    df_is_webship_location = fields.Boolean("Is Stoqflow locatie?", default=False)

    # Link to the webship.warehouse record for this location
    df_warehouse_webship = fields.Many2one(comodel_name='webship.warehouse', string='Stoqflow warehouse')
