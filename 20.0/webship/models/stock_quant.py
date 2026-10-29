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

    # Difference between Odoo total quantity and Stoqflow total stock.
    # A non-zero value means Odoo and Stoqflow disagree on physical stock.
    df_webship_diff_total = fields.Float(
        string="Total Difference",
        compute="_compute_df_webship_diffs",
        store=True,
        help="Odoo quantity minus Stoqflow total stock. "
             "Non-zero means the two systems are out of sync."
    )

    # Difference between Odoo reserved quantity and Stoqflow reserved stock.
    df_webship_diff_reserved = fields.Float(
        string="Reserved Difference",
        compute="_compute_df_webship_diffs",
        store=True,
        help="Odoo reserved quantity minus Stoqflow reserved stock. "
             "Non-zero means the two systems are out of sync."
    )

    # Difference between Odoo available quantity and Stoqflow available stock.
    df_webship_diff_available = fields.Float(
        string="Available Difference",
        compute="_compute_df_webship_diffs",
        store=True,
        help="Odoo available quantity minus Stoqflow available stock. "
             "Non-zero means the two systems are out of sync."
    )

    # Stoqflow reports one figure per product, so the Odoo side is the sum of
    # all quants of the product at the location (lots, packages). Depending on
    # the product's quants keeps every sibling row in step when one changes.
    @api.depends(
        "quantity", "reserved_quantity",
        "product_id.stock_quant_ids.quantity",
        "product_id.stock_quant_ids.reserved_quantity",
        "df_webship_totalstock", "df_webship_reserved",
        "df_webship_available_stock",
    )
    def _compute_df_webship_diffs(self):
        """Compute the stock discrepancies between Odoo and Stoqflow.
        Each difference is the Odoo value of the product at the location minus
        the matching Stoqflow value, so a positive number means Odoo holds more
        and a negative number means Stoqflow holds more. Zero means the two
        systems agree. Quants never checked against Stoqflow get no difference."""
        checked = self.filtered('df_last_check_webship')
        (self - checked).update({
            'df_webship_diff_total': 0.0,
            'df_webship_diff_reserved': 0.0,
            'df_webship_diff_available': 0.0,
        })
        if not checked:
            return
        groups = self.env['stock.quant'].sudo()._read_group(
            [('product_id', 'in', checked.product_id.ids),
             ('location_id', 'in', checked.location_id.ids)],
            ['product_id', 'location_id'],
            ['quantity:sum', 'reserved_quantity:sum'],
        )
        totals = {(product.id, location.id): (qty, reserved)
                  for product, location, qty, reserved in groups}
        for quant in checked:
            qty, reserved = totals.get(
                (quant.product_id.id, quant.location_id.id),
                (quant.quantity, quant.reserved_quantity))
            quant.df_webship_diff_total = qty - quant.df_webship_totalstock
            quant.df_webship_diff_reserved = reserved - quant.df_webship_reserved
            quant.df_webship_diff_available = (
                (qty - reserved) - quant.df_webship_available_stock
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

            # Ensure Webship stock data has actually been fetched for this quant.
            # df_webship_totalstock is a Float (never None), so an unfetched quant
            # reads 0.0 and would silently zero real inventory; gate on the last
            # check timestamp instead, which is empty until the first import.
            if not quant.df_last_check_webship:
                raise UserError(_(
                    "Webship stock has not been fetched yet for product %s."
                ) % quant.product_id.display_name)

            # Stoqflow gives one total per product: with several quants (lots,
            # packages) setting each of them to that total would multiply the
            # stock, and how the total splits over them is unknown.
            siblings = self.search_count([
                ('product_id', '=', quant.product_id.id),
                ('location_id', '=', quant.location_id.id),
            ])
            if siblings > 1:
                raise UserError(_(
                    "Product %(product)s has %(count)s stock lines (lots or packages) "
                    "at %(location)s. Stoqflow only reports the product total, so "
                    "adjust these lines manually.",
                    product=quant.product_id.display_name, count=siblings,
                    location=quant.location_id.display_name))

            # Set the inventory adjustment quantity to the Webship total
            quant.inventory_quantity = quant.df_webship_totalstock

        # Apply inventory adjustment for all selected quants in one batch
        self._apply_inventory()

        return True
