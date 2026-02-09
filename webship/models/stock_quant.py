from odoo import fields, models, api, _
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    df_webship_totalstock = fields.Float(
        string="Webship Total Stock",
        help="Total stock in Webship locations (filled by Webship API)"
    )

    df_webship_reserved = fields.Float(
        string="Webship Reserved Stock",
        help="Reserved stock in Webship locations (filled by Webship API)"
    )

    df_webship_available_stock = fields.Float(
        string="Webship Available Stock",
        help="Available stock in Webship locations (filled by Webship API)"
    )

    df_last_check_webship = fields.Datetime(
        string="Last Webship Check",
        help="Last datetime when stock was checked or synced with Webship"
    )

    def action_apply_webship_stock(self):
        """
        Apply Webship total stock to Odoo quantity
        for selected quants (multi-select safe).
        """
        for quant in self:
            if not quant.location_id.df_is_webship_location:
                raise UserError(_(
                    "You can only apply Webship stock on Webship locations."
                ))

            if quant.df_webship_totalstock is None:
                raise UserError(_(
                    "Webship total stock is not set for product %s."
                ) % quant.product_id.display_name)

            # Set inventory quantity (this is the ONLY correct way)
            quant.inventory_quantity = quant.df_webship_totalstock

        # Apply inventory adjustment in batch
        self._apply_inventory()

        return True

