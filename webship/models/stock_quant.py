# Extends stock.quant with Webship stock level fields.
# These fields are populated by the Webship API during stock imports
# and can be applied to Odoo inventory via a manual action button.
#
# Stoqflow reports stock per product and, for lot-tracked products, per batch,
# while Odoo keeps one quant per product, location, lot and package. The import
# writes the product figures on every quant of the product in the Stoqflow
# location and the batch figure on the quant of that lot. The "Stoqflow Stock"
# screen adds the quants up per product (see models/webship_stock.py).
#
# Applying Stoqflow stock to Odoo is always one to one: a stock line is set to
# its own Stoqflow figure, matched by lot. One figure is never spread over or
# duplicated on several lines, and a line without a figure is left alone.
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


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

    # Stock Stoqflow reports for this stock line's batch (lot), fetched with
    # GET products/{id}?detail=high. For a product without lots this is the
    # product total, so the line difference below is meaningful on every line.
    df_webship_lot_stock = fields.Float(
        string="Stoqflow Lot Stock",
        help="Stock Stoqflow reports for this lot (batch) in this location. "
             "For a product without lots this is the Stoqflow total stock."
    )

    # Timestamp of the last fetch of this line's figure. Empty when the line
    # was not compared on the last import: lot received since, or the
    # per-batch call (GET products/{id}?detail=high) failed, in which case the
    # import clears it so an older lot figure is never applied.
    df_webship_lot_checked = fields.Datetime(
        string="Last Stoqflow Lot Check",
        help="Last datetime when the Stoqflow stock of this line (lot) was fetched. "
             "Empty when the lots were not compared on the last import."
    )

    # Difference Odoo minus Stoqflow for this lot
    df_webship_lot_diff = fields.Float(
        string="Lot Difference",
        compute="_compute_df_webship_lot_diff",
        store=True,
        help="Odoo quantity of this lot minus the Stoqflow stock of the same batch. "
             "Non-zero means the two systems disagree on this lot."
    )

    # Expiry of the lot, read from product_expiry when it is installed (this
    # module does not depend on it, so the field cannot be a plain related)
    df_webship_expiration_date = fields.Datetime(
        string="Expiration Date",
        compute="_compute_df_webship_expiration_date",
        help="Expiration date of the lot of this stock line (product_expiry module)."
    )

    @api.depends("quantity", "df_webship_lot_stock")
    def _compute_df_webship_lot_diff(self):
        for quant in self:
            quant.df_webship_lot_diff = quant.quantity - quant.df_webship_lot_stock

    @api.depends("lot_id")
    def _compute_df_webship_expiration_date(self):
        has_expiry = 'expiration_date' in self.env['stock.lot']._fields
        for quant in self:
            quant.df_webship_expiration_date = (
                quant.lot_id.expiration_date if has_expiry and quant.lot_id else False)

    def _df_set_counted_quantity(self, qty):
        """Set the counted quantity of this quant to ``qty`` for
        ``_apply_inventory``. The stored difference is written explicitly:
        Odoo only recomputes it when the counted quantity changes, so a count
        equal to the previous one (0 after every apply) would otherwise apply
        nothing."""
        self.ensure_one()
        self.write({
            'inventory_quantity': qty,
            'inventory_diff_quantity': qty - self.quantity,
        })

    def _df_webship_target_quantity(self):
        """The Stoqflow figure this stock line must be set to, matched one to
        one, or ``None`` with the reason when there is no such figure.

        - product tracked by lot in Odoo: the figure the last import matched
          to this line (see WebShipHandler._import_product_lots): the stock
          of the batch with the same number, 0 when Stoqflow no longer holds
          that batch, the stock Stoqflow holds without batch for the line
          without lot, or the product figure when Stoqflow keeps no batches
          and this is the product's only line. A line the import could not
          match one to one has no figure;
        - product without lots: the Stoqflow total, provided it is the only
          stock line of the product in the location."""
        self.ensure_one()
        product = self.product_id
        if product.tracking == 'none':
            if not self.df_last_check_webship:
                return None, _(
                    "Webship stock has not been fetched yet for product %s."
                ) % product.display_name
            siblings = self.search([
                ("product_id", "=", product.id),
                ("location_id", "=", self.location_id.id),
            ])
            if len(siblings) > 1:
                return None, _(
                    "Product %s has several stock lines without lot in %s. Stoqflow "
                    "gives one figure for the product, so it cannot be applied to one line."
                ) % (product.display_name, self.location_id.display_name)
            return self.df_webship_totalstock, None
        if self.df_webship_lot_checked:
            return self.df_webship_lot_stock, None
        if not self.lot_id:
            return None, _(
                "The stock line of %s without lot has no Stoqflow counterpart: "
                "Stoqflow holds no stock without batch for this product. Assign "
                "the lot or adjust the line by hand."
            ) % product.display_name
        return None, _(
            "Lot %s of %s has no Stoqflow figure to apply: the last import could "
            "not match it one to one (no stock per batch fetched from Stoqflow, "
            "or one Stoqflow figure for several Odoo lines)."
        ) % (self.lot_id.name, product.display_name)

    def _df_apply_webship_stock(self, strict=True):
        """Set each of these stock lines to its own Stoqflow figure (see
        ``_df_webship_target_quantity``), one to one. One figure is never
        spread over or duplicated on several lines.

        A line without a figure raises when ``strict`` (the user asked for
        that line) and is skipped with a log line otherwise (automatic
        adjustment, whole-product button). Returns the adjusted quants and
        the list of (quant, reason) skipped."""
        touched = self.browse()
        skipped = []
        for quant in self:
            target, reason = quant._df_webship_target_quantity()
            if target is None:
                if strict:
                    raise UserError(reason)
                _logger.warning("Apply Stoqflow stock: stock line %s skipped: %s", quant.id, reason)
                skipped.append((quant, reason))
                continue
            rounding = quant.product_id.uom_id.rounding
            if float_compare(target, quant.quantity, precision_rounding=rounding) != 0:
                quant._df_set_counted_quantity(target)
                touched |= quant
        if touched:
            touched._apply_inventory()
        return touched, skipped

    @api.model
    def _df_apply_feedback(self, touched, skipped):
        """What a button returns after ``_df_apply_webship_stock``: an error
        when nothing could be applied, a sticky warning listing the lines
        left alone when some could not, True otherwise. The notification
        chains an act_window_close so the list reloads."""
        if skipped and not touched:
            raise UserError("\n".join(reason for _quant, reason in skipped))
        if skipped:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Stoqflow stock applied"),
                    'message': _(
                        "%(done)s stock line(s) set to their Stoqflow figure. "
                        "%(skipped)s line(s) left alone:\n%(reasons)s"
                    ) % {
                        'done': len(touched),
                        'skipped': len(skipped),
                        'reasons': "\n".join(reason for _quant, reason in skipped),
                    },
                    'type': 'warning',
                    'sticky': True,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
        return True

    def action_apply_webship_stock(self):
        """Stoqflow Stock list button (multi-select): set each selected stock
        line to its own Stoqflow figure, one to one. Lines without a figure
        (no lot on a lot-tracked product, lot not compared on the last
        import) are left alone and listed in a warning; the action stops with
        the reason when none of the selected lines can be applied. Only works
        on quants in Webship-managed locations."""
        for quant in self:
            # Ensure the quant belongs to a Webship-managed location
            if not quant.location_id.df_is_webship_location:
                raise UserError(_(
                    "You can only apply Webship stock on Webship locations."
                ))
        touched, skipped = self._df_apply_webship_stock(strict=False)
        return self._df_apply_feedback(touched, skipped)

    def action_df_open_product(self):
        """Row click (list ``action`` attribute): open the product form."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }
