from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    df_stoqflow_courier_id = fields.Many2one(
        'stoqflow.courier',
        string="Stoqflow Courier",
        help="Link this delivery carrier to a Stoqflow courier. "
             "When an order's preferred_courier matches, this carrier will be set on the picking.",
    )

    def stoqflow_find_delivery_carrier(self, courier_name):
        """Find a delivery.carrier linked to the given StoqFlow courier name.

        Returns the carrier record if found, False otherwise.
        Does NOT auto-create carriers — unlinked couriers are reported as warnings.
        """
        if not courier_name:
            return False
        courier_name = courier_name.strip()
        if not courier_name:
            return False

        # 1. Search by linked stoqflow courier code
        carrier = self.search([('df_stoqflow_courier_id.code', '=', courier_name)], limit=1)
        if carrier:
            return carrier

        # 2. Fallback: search by carrier name or stoqflow courier name
        carrier = self.search([
            '|',
            ('name', '=ilike', courier_name),
            ('df_stoqflow_courier_id.name', '=ilike', courier_name),
        ], limit=1)
        if carrier:
            return carrier

        return False
