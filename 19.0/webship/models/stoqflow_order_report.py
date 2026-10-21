# SQL-based reporting model for Stoqflow connector analytics.
# Shows orders processed by the connector per day with sale/cost prices and margins.
from odoo import models, fields


class StoqflowOrderReport(models.Model):
    _name = 'stoqflow.order.report'
    _description = 'Stoqflow Connector Report'
    _auto = False
    _order = 'date desc'

    date = fields.Date(string="Date", readonly=True)
    name = fields.Char(string="Picking", readonly=True)
    partner_id = fields.Many2one('res.partner', string="Customer", readonly=True)
    order_type = fields.Selection([
        ('order', 'Outbound Order'),
        ('purchase_order', 'Purchase Order'),
    ], string="Type", readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting'),
        ('confirmed', 'Waiting'),
        ('assigned', 'Ready'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string="Status", readonly=True)
    stoqflow_status = fields.Char(string="Stoqflow Status", readonly=True)
    sale_price = fields.Float(string="Sale Price", readonly=True)
    cost_price = fields.Float(string="Cost Price", readonly=True)
    margin = fields.Float(string="Margin", readonly=True)
    margin_percent = fields.Float(string="Margin %", readonly=True)
    order_count = fields.Integer(string="# Orders", readonly=True, default=1)

    def init(self):
        """Create a reporting view with sale/cost prices and margins for Stoqflow orders."""
        self.env.cr.execute("""
            DROP VIEW IF EXISTS stoqflow_order_report;
            CREATE OR REPLACE VIEW stoqflow_order_report AS (
                SELECT
                    sp.id AS id,
                    sp.date_done::date AS date,
                    sp.name AS name,
                    sp.partner_id AS partner_id,
                    sp.state AS state,
                    COALESCE(NULLIF(sp.df_status_webship, ''), 'not synced') AS stoqflow_status,
                    CASE
                        WHEN sl_src.df_is_webship_location = TRUE THEN 'order'
                        WHEN sl_dst.df_is_webship_location = TRUE THEN 'purchase_order'
                    END AS order_type,
                    COALESCE(line_totals.sale_total, 0) AS sale_price,
                    COALESCE(line_totals.cost_total, 0) AS cost_price,
                    COALESCE(line_totals.sale_total, 0) - COALESCE(line_totals.cost_total, 0) AS margin,
                    CASE
                        WHEN COALESCE(line_totals.sale_total, 0) > 0
                        THEN ROUND(
                            ((line_totals.sale_total - COALESCE(line_totals.cost_total, 0))
                             / line_totals.sale_total * 100)::numeric, 1)
                        ELSE 0
                    END AS margin_percent,
                    1 AS order_count
                FROM stock_picking sp
                JOIN stock_location sl_src ON sl_src.id = sp.location_id
                JOIN stock_location sl_dst ON sl_dst.id = sp.location_dest_id
                LEFT JOIN (
                    SELECT
                        sm.picking_id,
                        SUM(sm.quantity * COALESCE(sol.price_unit, 0)) AS sale_total,
                        SUM(sm.quantity * COALESCE((pp.standard_price->>'1')::numeric, 0)) AS cost_total
                    FROM stock_move sm
                    LEFT JOIN sale_order_line sol ON sol.id = sm.sale_line_id
                    LEFT JOIN product_product pp ON pp.id = sm.product_id
                    LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    WHERE sm.state = 'done'
                    GROUP BY sm.picking_id
                ) line_totals ON line_totals.picking_id = sp.id
                WHERE (sl_src.df_is_webship_location = TRUE
                       OR sl_dst.df_is_webship_location = TRUE)
                  AND sp.state = 'done'
                  AND (sp.df_picking_id_webship IS NOT NULL AND sp.df_picking_id_webship != ''
                       OR sp.df_po_id_webship IS NOT NULL AND sp.df_po_id_webship != '')
            );
        """)
