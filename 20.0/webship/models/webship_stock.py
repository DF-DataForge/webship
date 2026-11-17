# One line per product and Stoqflow location for the "Stoqflow Stock" screen.
#
# Stoqflow reports stock per product, while Odoo keeps one stock.quant per
# product, location, lot and package. A product tracked by lot (Stoqflow
# batches become Odoo lots) therefore has several quants in the same Stoqflow
# location, and a list built directly on stock.quant showed that product on
# several lines, each carrying the full Stoqflow figures. This SQL view adds
# the quants up per product and location and keeps the Stoqflow figures
# (written identically on every quant of the product) once.
from odoo import fields, models, _
from odoo.exceptions import UserError


class WebshipStock(models.Model):
    _name = 'webship.stock'
    _description = 'Stoqflow Stock'
    _auto = False
    _rec_name = 'product_id'
    _order = 'product_id, location_id'

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    location_id = fields.Many2one('stock.location', string='Location', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    # Number of stock.quant records behind the line (one per lot / package)
    quant_count = fields.Integer(
        string='Stock Lines', readonly=True,
        help="Number of stock lines (lots, packages) behind this product in this location."
    )

    # Lots whose Odoo quantity differs from the Stoqflow stock of the same
    # batch. The product total can agree while the lots do not (stock booked
    # on another lot than the one Stoqflow holds).
    lot_diff_count = fields.Integer(
        string='Lots Out of Sync', readonly=True,
        help="Number of lots whose Odoo quantity differs from the Stoqflow stock of the same batch."
    )

    # The lots behind the line and the first expiry among them (expiry dates
    # exist when the product_expiry module is installed)
    lot_names = fields.Char(
        string='Lot Numbers', readonly=True,
        help="The lot numbers of the stock lines behind this product in this location."
    )
    expiration_date = fields.Datetime(
        string='Expiration Date', readonly=True,
        help="The earliest expiration date among the lots of this product in this location."
    )

    # Odoo stock: every lot / package of the product in this location added up
    quantity = fields.Float(
        string='Quantity', readonly=True,
        help="Odoo on-hand quantity: all lots and packages of the product in this location added up."
    )
    reserved_quantity = fields.Float(string='Reserved Quantity', readonly=True)
    available_quantity = fields.Float(string='Available Quantity', readonly=True)

    # Stoqflow stock (API filled, per product)
    df_webship_totalstock = fields.Float(
        string='Stoqflow Total Stock', readonly=True,
        help="Total stock in Stoqflow locations (filled by Stoqflow API)"
    )
    df_webship_reserved = fields.Float(
        string='Stoqflow Reserved Stock', readonly=True,
        help="Reserved stock in Stoqflow locations (filled by Stoqflow API)"
    )
    df_webship_available_stock = fields.Float(
        string='Stoqflow Available Stock', readonly=True,
        help="Available stock in Stoqflow locations (filled by Stoqflow API)"
    )
    df_last_check_webship = fields.Datetime(
        string='Last Stoqflow Check', readonly=True,
        help="Last datetime when stock was checked or synced with Stoqflow"
    )

    # Differences Odoo minus Stoqflow: non-zero means the two systems disagree
    df_webship_diff_total = fields.Float(
        string='Total Difference', readonly=True,
        help="Odoo quantity minus Stoqflow total stock. "
             "Non-zero means the two systems are out of sync."
    )
    df_webship_diff_reserved = fields.Float(
        string='Reserved Difference', readonly=True,
        help="Odoo reserved quantity minus Stoqflow reserved stock. "
             "Non-zero means the two systems are out of sync."
    )
    df_webship_diff_available = fields.Float(
        string='Available Difference', readonly=True,
        help="Odoo available quantity minus Stoqflow available stock. "
             "Non-zero means the two systems are out of sync."
    )

    def init(self):
        """Create the view: stock.quant added up per product and Stoqflow
        location. The Stoqflow figures are the same on every quant of a
        product in a location (the import writes them on all of them), so
        MAX() returns that figure once; a lot received after the last import
        still reads 0 and does not lower it. Expiry dates come from
        product_expiry, which this module does not depend on."""
        expiration = (
            "MIN(sl.expiration_date)"
            if 'expiration_date' in self.env['stock.lot']._fields
            else "NULL::timestamp"
        )
        self.env.cr.execute(f"""
            DROP VIEW IF EXISTS webship_stock;
            CREATE OR REPLACE VIEW webship_stock AS (
                SELECT
                    MIN(q.id) AS id,
                    q.product_id AS product_id,
                    q.location_id AS location_id,
                    q.company_id AS company_id,
                    STRING_AGG(DISTINCT sl.name, ', ' ORDER BY sl.name) AS lot_names,
                    {expiration} AS expiration_date,
                    COUNT(q.id) AS quant_count,
                    COUNT(q.id) FILTER (
                        WHERE q.lot_id IS NOT NULL
                          AND q.df_webship_lot_checked IS NOT NULL
                          AND ROUND((COALESCE(q.quantity, 0)
                                     - COALESCE(q.df_webship_lot_stock, 0))::numeric, 5) <> 0
                    ) AS lot_diff_count,
                    SUM(COALESCE(q.quantity, 0)) AS quantity,
                    SUM(COALESCE(q.reserved_quantity, 0)) AS reserved_quantity,
                    SUM(COALESCE(q.quantity, 0)) - SUM(COALESCE(q.reserved_quantity, 0))
                        AS available_quantity,
                    MAX(COALESCE(q.df_webship_totalstock, 0)) AS df_webship_totalstock,
                    MAX(COALESCE(q.df_webship_reserved, 0)) AS df_webship_reserved,
                    MAX(COALESCE(q.df_webship_available_stock, 0)) AS df_webship_available_stock,
                    MAX(q.df_last_check_webship) AS df_last_check_webship,
                    SUM(COALESCE(q.quantity, 0)) - MAX(COALESCE(q.df_webship_totalstock, 0))
                        AS df_webship_diff_total,
                    SUM(COALESCE(q.reserved_quantity, 0)) - MAX(COALESCE(q.df_webship_reserved, 0))
                        AS df_webship_diff_reserved,
                    SUM(COALESCE(q.quantity, 0)) - SUM(COALESCE(q.reserved_quantity, 0))
                        - MAX(COALESCE(q.df_webship_available_stock, 0))
                        AS df_webship_diff_available
                FROM stock_quant q
                JOIN stock_location l ON l.id = q.location_id
                LEFT JOIN stock_lot sl ON sl.id = q.lot_id
                WHERE l.df_is_webship_location = TRUE
                  AND l.usage = 'internal'
                GROUP BY q.product_id, q.location_id, q.company_id
            );
        """)

    def _get_quants(self):
        """The stock.quant records (one per lot / package) behind this line."""
        self.ensure_one()
        return self.env['stock.quant'].search([
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_id.id),
        ])

    def action_apply_webship_stock(self):
        """Stock per Product list button (multi-select): set every stock line
        of each selected product to its own Stoqflow figure, one to one (a lot
        to its batch quantity, the single line of a product without lots to
        the total; see stock.quant._df_webship_target_quantity). Lines without
        a figure, such as a line without lot on a lot-tracked product, are
        left alone and listed in a warning; the action stops with the reason
        when nothing can be applied."""
        Quant = self.env['stock.quant']
        touched = Quant
        skipped = []
        for line in self:
            if not line.df_last_check_webship:
                raise UserError(_(
                    "Webship stock has not been fetched yet for product %s."
                ) % line.product_id.display_name)
            done, left = line._get_quants()._df_apply_webship_stock(strict=False)
            touched |= done
            skipped += left
        return Quant._df_apply_feedback(touched, skipped)

    def action_open_product(self):
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

    def action_view_quants(self):
        """Row button: open the lots / packages that make up this line."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Stoqflow Stock Details"),
            'res_model': 'stock.quant',
            'view_mode': 'list',
            'views': [(self.env.ref('webship.df_webship_stock_quant_tree_view').id, 'list')],
            'search_view_id': [self.env.ref('webship.df_webship_stock_quant_search_view').id, 'search'],
            'domain': [
                ('product_id', '=', self.product_id.id),
                ('location_id', '=', self.location_id.id),
            ],
            'target': 'current',
        }
