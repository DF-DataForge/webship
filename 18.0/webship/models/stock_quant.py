# Extends stock.quant with Webship stock level fields.
# These fields are populated by the Webship API during stock imports
# and can be applied to Odoo inventory via a manual action button.
from odoo import fields, models, api, _
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Total physical stock reported by Webship for this product/location
    df_webship_totalstock = fields.Float(
        string="Stoqflow Total Stock",
        help="Total stock in Stoqflow locations (filled by Stoqflow API)"
    )

    # Quantity reserved (allocated to open orders) in Stoqflow
    df_webship_reserved = fields.Float(
        string="Stoqflow Reserved Stock",
        help="Reserved stock in Stoqflow locations (filled by Stoqflow API)"
    )

    # Available stock in Stoqflow (total minus reserved)
    df_webship_available_stock = fields.Float(
        string="Stoqflow Available Stock",
        help="Available stock in Stoqflow locations (filled by Stoqflow API)"
    )

    # Timestamp of the last stock synchronization from Stoqflow
    df_last_check_webship = fields.Datetime(
        string="Last Stoqflow Check",
        help="Last datetime when stock was checked or synced with Stoqflow"
    )

    def action_apply_webship_stock(self):
        """Apply the Webship total stock values to Odoo inventory quantities.
        Can be triggered from a button on selected quant records.
        Only works on quants in Webship-managed locations."""
        for quant in self:
            # Ensure the quant belongs to a Webship-managed location
            if not quant.location_id.df_is_webship_location:
                raise UserError(_(
                    "You can only apply Webship stock on Webship locations."
                ))

            # Ensure Webship stock data has been fetched for this quant
            if quant.df_webship_totalstock is None:
                raise UserError(_(
                    "Webship total stock is not set for product %s."
                ) % quant.product_id.display_name)

            # Set the inventory adjustment quantity to the Webship total
            quant.inventory_quantity = quant.df_webship_totalstock

        # Apply inventory adjustment for all selected quants in one batch
        self._apply_inventory()

        return True
