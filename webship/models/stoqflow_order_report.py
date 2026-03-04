# SQL-based reporting model for Stoqflow order analytics.
# Provides data for graph and pivot views showing order counts
# broken down by Stoqflow status, sync state, and time period.
from odoo import models, fields


class StoqflowOrderReport(models.Model):
    _name = 'stoqflow.order.report'
    _description = 'Stoqflow Order Analysis'
    _auto = False
    _order = 'create_date desc'

    name = fields.Char(string="Picking Reference", readonly=True)
    create_date = fields.Datetime(string="Created On", readonly=True)
    partner_id = fields.Many2one('res.partner', string="Partner", readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting'),
        ('confirmed', 'Waiting'),
        ('assigned', 'Ready'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string="Odoo Status", readonly=True)
    stoqflow_status = fields.Char(string="Stoqflow Status", readonly=True)
    sync_state = fields.Selection([
        ('pending', 'Pending'),
        ('synced', 'Synced'),
        ('error', 'Error'),
        ('not_applicable', 'N/A'),
    ], string="Sync State", readonly=True)
    order_type = fields.Selection([
        ('order', 'Outbound Order'),
        ('purchase_order', 'Purchase Order'),
    ], string="Order Type", readonly=True)
    last_sync = fields.Datetime(string="Last Sync", readonly=True)
    order_count = fields.Integer(string="# Orders", readonly=True, default=1)

    def init(self):
        """Create a reporting view joining pickings with their Stoqflow location flags."""
        self.env.cr.execute("""
            DROP VIEW IF EXISTS stoqflow_order_report;
            CREATE OR REPLACE VIEW stoqflow_order_report AS (
                SELECT
                    sp.id AS id,
                    sp.name AS name,
                    sp.create_date AS create_date,
                    sp.partner_id AS partner_id,
                    sp.state AS state,
                    COALESCE(NULLIF(sp.df_status_webship, ''), 'not synced') AS stoqflow_status,
                    CASE
                        WHEN sp.df_process_code = 'P' THEN 'pending'
                        WHEN sp.df_picking_id_webship IS NOT NULL AND sp.df_picking_id_webship != ''
                             THEN 'synced'
                        WHEN sp.df_po_id_webship IS NOT NULL AND sp.df_po_id_webship != ''
                             THEN 'synced'
                        WHEN sp.df_picking_syncresult_webship IS NOT NULL
                             AND sp.df_picking_syncresult_webship != ''
                             AND sp.df_picking_syncresult_webship NOT LIKE '%%success%%'
                             THEN 'error'
                        ELSE 'not_applicable'
                    END AS sync_state,
                    CASE
                        WHEN sl_src.df_is_webship_location = TRUE THEN 'order'
                        WHEN sl_dst.df_is_webship_location = TRUE THEN 'purchase_order'
                    END AS order_type,
                    sp.df_picking_lastsync_webship AS last_sync,
                    1 AS order_count
                FROM stock_picking sp
                JOIN stock_location sl_src ON sl_src.id = sp.location_id
                JOIN stock_location sl_dst ON sl_dst.id = sp.location_dest_id
                WHERE (sl_src.df_is_webship_location = TRUE
                       OR sl_dst.df_is_webship_location = TRUE)
                  AND sp.state IN ('confirmed', 'assigned', 'done')
            );
        """)
