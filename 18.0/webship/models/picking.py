# Extends stock.picking with Stoqflow/Webship synchronization capabilities.
# Handles creating/updating orders and purchase orders via the Stoqflow REST API
# (see https://api-documentation.stoqflow.com/), fetching status updates back,
# and merging duplicate move lines before sync.
#
# Stoqflow API context:
#   - Outbound pickings (source is Webship location) -> synced as "orders"
#     via POST/PUT /orders with statuses: concept, awaiting-payment, ready-to-pick,
#     picking, ready-to-pack, packing, ready-to-ship, on-hold, completed, cancelled
#   - Inbound pickings (destination is Webship location) -> synced as "purchase-orders"
#     via POST/PUT /purchase-orders with statuses: concept, ordered, completed
#   - Authentication: HTTP Basic Auth + x-addon-public-key header
#   - Pagination: 50 items/page, total-count response header, ?page=N query param
from odoo.addons.webship.models.ws import WebShipHandler
from odoo import models, fields, api
from markupsafe import Markup
from odoo.tools.safe_eval import safe_eval

from collections import defaultdict
from datetime import datetime
import pprint
import logging
import base64
import io
import xlsxwriter

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Stoqflow order ID (returned by POST /orders) assigned after syncing an outbound order
    df_picking_id_webship = fields.Char("Order id Stoqflow", readonly=True)
    # Human-readable order number (e.g. "ORD-00123") fetched from GET /orders/{id}.
    # Plain stored field (like df_po_code_webship): it is populated explicitly
    # wherever df_picking_id_webship is set (sync, fetchQuantities, compare).
    # It used to be a stored compute that re-fetched the code from the API on
    # every id change, which clobbered freshly-set values with '' whenever the
    # API throttled (notably during a bulk multi-select compare).
    df_picking_code_webship = fields.Char("Order code Stoqflow")

    # Stoqflow purchase order ID (returned by POST /purchase-orders) for inbound orders
    df_po_id_webship = fields.Char("Purchase order id Stoqflow", readonly=True)
    # Human-readable PO number fetched from GET /purchase-orders/{id}
    df_po_code_webship = fields.Char("Po code Stoqflow")

    # Timestamp of the last synchronization attempt to Stoqflow
    df_picking_lastsync_webship = fields.Datetime("Last sync on", readonly=True)

    # HTML result of the last sync (success message or error details)
    df_picking_syncresult_webship = fields.Html("Result last sync", readonly=True)

    # Result of the last comparison between this picking and its Stoqflow order
    # (see compare_with_stoqflow). 'Success' when all products and ordered
    # quantities match, otherwise a per-line list of the discrepancies found.
    df_compare_result_webship = fields.Html("Compare result", readonly=True)

    # Name of the customer the matching Stoqflow order is linked to, fetched
    # via fetch_client_name_webship. The value is read from the client the
    # Stoqflow order actually points to (its client_id), not from the address
    # snapshot Odoo sent, so showing it next to the Odoo customer (partner_id)
    # in the Stoqflow orders list reveals at a glance whether a picking is
    # linked to the right client in both systems.
    df_client_name_webship = fields.Char("Client name Stoqflow", readonly=True)

    # Current status of this picking in Stoqflow (e.g. 'ready-to-pick', 'completed')
    df_status_webship = fields.Selection([
        ('concept', 'Concept'),
        ('awaiting-payment', 'Awaiting Payment'),
        ('ordered', 'Ordered'),
        ('in-transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('unpacking', 'Unpacking'),
        ('on-hold', 'On Hold'),
        ('ready-to-pick', 'Ready to Pick'),
        ('picking', 'Picking'),
        ('ready-to-pack', 'Ready to Pack'),
        ('packing', 'Packing'),
        ('ready-to-ship', 'Ready to Ship'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status in Stoqflow', readonly=True)

    # Timestamp of the last status change reported by the Stoqflow API
    df_last_changedate_webship = fields.Datetime("Last change in Stoqflow")

    # Clickable HTML link to the order page in the Stoqflow web application
    df_url_order = fields.Html('Order link Stoqflow', compute="_compute_html_picking")

    # Clickable HTML link to the purchase order page in the Stoqflow web application
    df_url_po = fields.Html('Purchase order link Stoqflow', compute="_compute_html_po")

    # Clickable HTML link to whichever type (order or PO) applies to this picking
    df_url_order_or_po = fields.Html('Order or Purchase order id Stoqflow', compute="_compute_html_order_or_po")

    # Clickable link to the attached sale order's form view, so the Sales Order
    # column in the Stoqflow orders list navigates to the sale order on click.
    df_sale_order_link = fields.Html('Sales Order', compute="_compute_sale_order_link")

    # Whether the Webship tab should be visible on the picking form view
    df_show_webship_page = fields.Boolean('Show Stoqflow page', compute="_show_webship_page", store=True)

    # Related booleans indicating if source/destination locations are Webship-managed
    df_is_webship_source = fields.Boolean('is Stoqflow source location', related='location_id.df_is_webship_location')
    df_is_webship_destination = fields.Boolean('is Stoqflow destination location',
                                          related='location_dest_id.df_is_webship_location')

    # Whether the Stoqflow Parcels tab is enabled in settings
    df_show_parcels_tab = fields.Boolean('Show Parcels tab', compute="_compute_show_parcels_tab")

    # Whether the temporary Stoqflow compare feature is enabled (global setting).
    # Drives visibility of the Compare / Compare detail buttons and the compare
    # result field on the picking views.
    df_show_compare = fields.Boolean('Show Stoqflow compare', compute="_compute_show_compare")

    # Computed Stoqflow object type based on location directions:
    #   'Order' = outbound (source is Webship), 'Purchase order' = inbound (dest is Webship), 'Mutation' = other
    df_object_in_webship = fields.Char('Object in Stoqflow', compute="_find_object_webship", store=True)

    # Process code controlling the sync lifecycle:
    #   'P' = pending, 'F' = finished, 'E' = error, 'M' = manual,
    #   'C' = cancelled, 'NA' = not applicable
    df_process_code = fields.Selection([
        ('P', 'Pending'),
        ('F', 'Sent to Stoqflow'),
        ('E', 'Error'),
        ('M', 'Manual'),
        ('C', 'Cancelled'),
        ('NA', 'Not Applicable'),
    ], string='Process code', default=lambda self: self._default_process_code(), tracking=True)

    # Comma-separated tracking URLs from Webship parcels (parcel.tracking_url values)
    df_carrier_tracking_urls = fields.Char('Tracking Reference URLs')

    # Stores the 'edited' or 'created' date string from Stoqflow to detect updates
    df_ws_lastChangeDate = fields.Char(
        string='Last changedate Stoqflow'
    )

    # One2many link to Stoqflow parcels parsed from the API response
    df_parcel_ids = fields.One2many('webship.parcel', 'picking_id', string='Stoqflow Parcels')

    # Whether the Stoqflow Pick Analysis tab is enabled in settings
    df_show_pick_analysis_tab = fields.Boolean('Show Pick Analysis tab', compute="_compute_show_pick_analysis_tab")

    # Stored analysis lines populated during fetch quantities action
    df_pick_analysis_ids = fields.One2many(
        'webship.pick.analysis.line', 'picking_id',
        string='Pick Analysis'
    )

    def _compute_show_pick_analysis_tab(self):
        show = self.env['ir.config_parameter'].sudo().get_param('webship.show_pick_analysis_tab', 'False') == 'True'
        for record in self:
            record.df_show_pick_analysis_tab = show

    def _populate_pick_analysis(self, data, wsHandler=None):
        """Build pick analysis lines from a Stoqflow order JSON payload.
        Called after setPickingQuantities during fetch quantities.

        Counting logic per line:
        1. Determine lookup_id: parent_product_id if present, else product_id
        2. Look up the Odoo product by Stoqflow ID -> total = quantity (individual items)
        """
        self.ensure_one()
        self.df_pick_analysis_ids.unlink()

        picks = data.get('picks') or []
        order_items = data.get('order_items') or []

        _logger.info(
            "pick_analysis [%s]: START - %d picks, %d order_items",
            self.name, len(picks), len(order_items),
        )

        if not picks and not order_items:
            return

        self.env.flush_all()

        # ----- Fetch Stoqflow product info via GET /products?subset=... -----
        ws_product_info = {}  # ws_id -> {'sku': ..., 'name': ...}
        if wsHandler:
            all_ws_ids = set()
            for pick in picks:
                if pick.get('product_id'):
                    all_ws_ids.add(pick['product_id'])
                if pick.get('parent_product_id'):
                    all_ws_ids.add(pick['parent_product_id'])
            if all_ws_ids:
                subset_param = '?subset=%s&fields=sku,name' % ','.join(all_ws_ids)
                _logger.info(
                    "pick_analysis [%s]: fetching %d Stoqflow products via subset",
                    self.name, len(all_ws_ids),
                )
                try:
                    result = wsHandler.performGet('products', subset_param)
                    if result.get('status') == 'success' and isinstance(result.get('data'), list):
                        for prod in result['data']:
                            ws_product_info[prod['_id']] = {
                                'sku': prod.get('sku', ''),
                                'name': prod.get('name', ''),
                            }
                        _logger.info(
                            "pick_analysis [%s]: fetched %d Stoqflow products",
                            self.name, len(ws_product_info),
                        )
                    else:
                        _logger.warning(
                            "pick_analysis [%s]: failed to fetch Stoqflow products: %s",
                            self.name, result,
                        )
                except Exception:
                    _logger.exception(
                        "pick_analysis [%s]: error fetching Stoqflow products",
                        self.name,
                    )

        # ----- Build product lookup: Stoqflow ID -> product -----
        all_products = self.env['product.product'].sudo().search([
            ('df_product_id_webship', '!=', False)
        ])
        ws_id_to_product = {p.df_product_id_webship: p for p in all_products}
        _logger.info(
            "pick_analysis [%s]: product lookup - %d records",
            self.name, len(ws_id_to_product),
        )

        # ----- Build order_items qty map -----
        oi_qty_map = {}
        for oi in order_items:
            pid = oi.get('product_id')
            if pid:
                oi_qty_map[pid] = oi_qty_map.get(pid, 0) + (oi.get('quantity') or 0)

        lines = []
        for idx, pick in enumerate(picks, start=1):
            ws_pid = pick.get('product_id', '')
            ws_parent_pid = pick.get('parent_product_id', '')
            qty = pick.get('quantity', 0)
            fraction = pick.get('fraction', 0)

            # Step 1: determine lookup ID
            lookup_id = ws_parent_pid if ws_parent_pid else ws_pid

            # Step 2: look up the Odoo product by Stoqflow ID
            odoo_product_id = False
            total_items = qty

            product = ws_id_to_product.get(lookup_id)
            if product:
                odoo_product_id = product.id
                _logger.info(
                    "pick_analysis [%s]: pick #%d lookup_id=%s -> PRODUCT '%s' (SKU %s) -> %s items",
                    self.name, idx, lookup_id, product.name, product.default_code, qty,
                )
            else:
                _logger.warning(
                    "pick_analysis [%s]: pick #%d lookup_id=%s -> NOT FOUND "
                    "in %d products (product_id=%s, parent_product_id=%s)",
                    self.name, idx, lookup_id,
                    len(ws_id_to_product),
                    ws_pid, ws_parent_pid,
                )

            is_sub = bool(ws_parent_pid and ws_parent_pid != ws_pid)
            ordered_ws_id = ws_parent_pid if ws_parent_pid else ws_pid

            # Stoqflow product info from API
            product_info = ws_product_info.get(ws_pid, {})
            parent_info = ws_product_info.get(ws_parent_pid, {}) if ws_parent_pid else {}

            lines.append((0, 0, {
                'sequence': idx,
                'ws_product_id': ws_pid,
                'ws_product_sku': product_info.get('sku', ''),
                'ws_product_name': product_info.get('name', ''),
                'ws_parent_product_id': ws_parent_pid or '',
                'ws_parent_product_sku': parent_info.get('sku', ''),
                'ws_parent_product_name': parent_info.get('name', ''),
                'ws_lookup_id': lookup_id,
                'odoo_product_id': odoo_product_id,
                'quantity': qty,
                'total_items': total_items,
                'fraction': fraction,
                'is_substitution': is_sub,
                'order_item_qty': oi_qty_map.get(ordered_ws_id, 0),
            }))

        _logger.info(
            "pick_analysis [%s]: DONE - %d pick lines",
            self.name, len(lines),
        )
        self.df_pick_analysis_ids = lines

    def getHandler(self):
        """Create and return a WebShipHandler instance using stored Stoqflow API credentials.
        Reads username, password, and base URL from ir.config_parameter."""
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = WebShipHandler(login, pw, base_url)

        return wsHandler

    @api.model
    def _default_process_code(self):
        """Determine the default process code for new pickings.
        Defaults to 'P' (pending sync). When a domain filter is configured,
        create()/write() will further demote non-matching pickings to 'M'.
        Non-Stoqflow pickings (no Webship location) are harmless as 'P' —
        the cron marks them 'NA' on first run."""
        return 'P'

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to initialize all Webship fields to blank values and
        classify the picking up-front:
        - Out of Stoqflow scope -> 'NA' (cron skips it, no 'P' churn).
        - Backorder in Stoqflow scope -> 'M' (Manual, avoid re-sync).
        - Otherwise keep the default 'P' and apply the optional domain filter."""
        pickings = super(StockPicking, self).create(vals_list)

        for picking in pickings:
            # Clear all Stoqflow fields on newly created pickings to avoid stale data
            picking.write({
                'df_picking_id_webship':False,
                'df_picking_code_webship':'',
                'df_po_id_webship':False,
                'df_po_code_webship':'',
                'df_picking_lastsync_webship':'',
                'df_picking_syncresult_webship':'',
                'df_status_webship':'',
                'df_last_changedate_webship':False,
                'df_client_name_webship':''
            })

            in_webship_scope = (
                picking.location_id.df_is_webship_location
                or picking.location_dest_id.df_is_webship_location
            )

            # Pickings that don't involve a Stoqflow location never need to
            # be pushed to Stoqflow. Mark them 'NA' straight away so the
            # ws_sync_all_pickings_statusP cron doesn't have to iterate and
            # demote them on every run.
            if not in_webship_scope:
                picking.df_process_code = 'NA'
                picking._log_process_code("not in Stoqflow scope")
                continue

            # Odoo-created backorders in Stoqflow scope should stay Manual:
            # they inherit nothing from the original picking and we don't want
            # the cron to push them back to Stoqflow as new orders.
            if picking.backorder_id:
                picking.df_process_code = 'M'
                picking._log_process_code("backorder of %s in Stoqflow scope" % picking.backorder_id.name)
                continue

            # Log initial process code
            picking._log_process_code("initialized")

            # If auto-sync is enabled ('P'), evaluate the domain filter to exclude non-matching pickings
            if picking.df_process_code == 'P':
                self._apply_domain_filter(picking)

        return pickings

    def write(self, vals):
        """Re-evaluate the domain filter when mk_instance_id is set on a picking
        that was previously excluded because the field was not yet available."""
        res = super(StockPicking, self).write(vals)

        if 'mk_instance_id' in vals:
            for picking in self.filtered(lambda p: p.df_process_code == 'M'):
                picking._log_process_code("mk_instance_id changed to %s, re-evaluating" % vals['mk_instance_id'])
                self._apply_domain_filter(picking, promote=True)

        return res

    def _log_process_code(self, reason):
        """Log the current process code and relevant context to the picking chatter."""
        self.ensure_one()
        webship_sync = self.env['ir.config_parameter'].sudo().get_param('webship.sync_order')
        webship_domain = self.env['ir.config_parameter'].sudo().get_param('webship.domain')
        mk_id = self.mk_instance_id.id if hasattr(self, 'mk_instance_id') and self.mk_instance_id else 'not set'
        self.message_post(
            body=Markup("Stoqflow process code %s: <b>%s</b> (sync_order=%s, domain=%s, mk_instance_id=%s)") % (
                reason, self.df_process_code, webship_sync, webship_domain or 'none', mk_id,
            ),
            subtype_xmlid='mail.mt_note',
        )

    def _apply_domain_filter(self, picking, promote=False):
        """Evaluate the webship domain filter against a picking.
        If promote=False (create): demote P -> M when the picking does NOT match.
        If promote=True (write):  promote M -> P when the picking DOES match."""
        webship_domain = self.env['ir.config_parameter'].sudo().get_param('webship.domain')
        if not webship_domain:
            if promote:
                picking.df_process_code = 'P'
                picking._log_process_code("promoted (no domain filter)")
            return
        try:
            domain = safe_eval(webship_domain)
            # Flush to ensure all field values (especially mk_instance_id) are in the DB for search
            self.env.flush_all()
            match = self.env['stock.picking'].search([('id', '=', picking.id)] + domain, limit=1)
            if promote and match:
                picking.df_process_code = 'P'
                picking._log_process_code("promoted (matched domain filter)")
            elif not promote and not match:
                picking.df_process_code = 'M'
                picking._log_process_code("demoted (excluded by domain filter)")
            elif promote and not match:
                picking._log_process_code("stays M (did not match domain filter)")
        except Exception as e:
            _logger.warning("Invalid webship domain filter: %s (%s)", webship_domain, e)
            picking.message_post(
                body="Stoqflow: invalid domain filter: %s (%s)" % (webship_domain, e),
                subtype_xmlid='mail.mt_note',
            )

    def _schedule_merge_after_create(self):
        """Schedule a post-commit merge of duplicate move lines for Webship destination pickings.
        Runs after the transaction commits to ensure all stock.move records are fully created."""
        for picking in self:
            if picking.location_dest_id.df_is_webship_location:
                picking.env.cr.after('commit', lambda: picking._safe_merge_picking())

    def _safe_merge_picking(self):
        """Safely execute merge_picking with error handling to avoid breaking the commit."""
        try:
            if self.exists() and self.move_ids:
                _logger.info(f"Auto-merging moves for picking {self.name} (WebShip destination)")
                self.merge_picking()
            else:
                _logger.info(f"Skipping merge for {self.name}: no moves found yet.")
        except Exception as e:
            _logger.warning(f"Error while merging picking {self.name}: {e}")

    @api.depends('location_id', 'location_dest_id')
    def _find_object_webship(self):
        """Determine the Stoqflow object type based on source and destination locations:
        - 'Purchase order': destination is a Webship location (inbound goods -> POST /purchase-orders)
        - 'Order': source is a Webship location (outbound goods -> POST /orders)
        - 'Mutation': internal transfer, not synced to Stoqflow"""
        for record in self:
            if record.location_dest_id.df_is_webship_location and not record.location_id.df_is_webship_location:
                record.df_object_in_webship = 'Purchase order'
            elif record.location_id.df_is_webship_location and not record.location_dest_id.df_is_webship_location:
                record.df_object_in_webship = 'Order'
            else:
                record.df_object_in_webship = 'Mutation'

    @api.depends('location_id', 'location_dest_id')
    def _show_webship_page(self):
        """Show the Webship tab on the picking form if either the source or
        destination location is a Webship-managed location."""
        for record in self:
            record.df_show_webship_page = (
                record.location_id.df_is_webship_location
                or record.location_dest_id.df_is_webship_location
            )

    def _compute_show_parcels_tab(self):
        """Read the global setting to show/hide the Stoqflow Parcels tab."""
        show = self.env['ir.config_parameter'].sudo().get_param('webship.show_parcels_tab', 'False') == 'True'
        for record in self:
            record.df_show_parcels_tab = show

    def _compute_show_compare(self):
        """Read the global setting to show/hide the temporary Stoqflow compare
        buttons and result field. Defaults to enabled."""
        show = self.env['ir.config_parameter'].sudo().get_param('webship.show_compare', 'True') == 'True'
        for record in self:
            record.df_show_compare = show

    @api.depends("df_picking_id_webship", "df_picking_code_webship")
    def _compute_html_picking(self):
        """Build an HTML snippet with the order code and a clickable Stoqflow icon
        linking to the order detail page in the Stoqflow web application."""
        for record in self:
            if record.df_picking_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'orders/' + record.df_picking_id_webship
                shownCode = record.df_picking_id_webship

                # Prefer showing the human-readable order number over the raw API ID
                if record.df_picking_code_webship != False and record.df_picking_code_webship != '':
                    shownCode = record.df_picking_code_webship

                record.df_url_order = shownCode + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
            else:
                record.df_url_order = ''

    @api.depends("df_po_id_webship", "df_po_code_webship")
    def _compute_html_po(self):
        """Build an HTML snippet with the PO code and a clickable Stoqflow icon
        linking to the purchase order page in the Stoqflow web application."""
        for record in self:
            if record.df_po_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'purchase-orders/' + record.df_po_id_webship
                record.df_url_po = record.df_po_code_webship + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
            else:
                record.df_url_po = ''

    @api.depends("df_picking_id_webship", "df_po_id_webship",
                 "df_picking_code_webship", "df_po_code_webship")
    def _compute_html_order_or_po(self):
        """Build an HTML link for whichever Stoqflow reference exists on this picking.
        Prioritizes the outbound order link, falls back to the purchase order link."""
        for record in self:
            if record.df_picking_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'orders/' + record.df_picking_id_webship
                shownCode = record.df_picking_id_webship

                if record.df_picking_code_webship != False and record.df_picking_code_webship != '':
                    shownCode = record.df_picking_code_webship

                record.df_url_order_or_po = shownCode + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
            elif record.df_po_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.base_app_url') + 'purchase-orders/' + record.df_po_id_webship
                record.df_url_order_or_po = record.df_po_code_webship + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
            else:
                record.df_url_order_or_po = ''

    @api.depends('sale_id')
    def _compute_sale_order_link(self):
        """Render the attached sale order as a clickable link to its form view,
        so the Sales Order column navigates to the sale order when clicked."""
        for record in self:
            if record.sale_id:
                url = '/odoo/sales/%s' % record.sale_id.id
                record.df_sale_order_link = Markup('<a href="%s">%s</a>') % (
                    url, record.sale_id.display_name,
                )
            else:
                record.df_sale_order_link = ''

    def test(self):
        """Debug action: builds the Stoqflow order or PO JSON payload without sending it,
        and displays the result as a sticky notification for inspection."""
        wsHandler = self.getHandler()

        # Build the payload depending on the picking type (order vs purchase order)
        if self.df_object_in_webship == 'Order':
            sOutput = wsHandler.build_order_object(self)
        elif self.df_object_in_webship == 'Purchase order':
            sOutput = wsHandler.build_po_object(self)
        else:
            sOutput = {}

        formatted_output = pprint.pformat(sOutput)

        _logger.debug("Test output:\n%s", formatted_output)

        # Return a notification action to display the payload in the Odoo UI
        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Info',
                'type': 'warning',
                'message': str(formatted_output),
                'sticky': True,
            }
        }
        return notification

    def setCompleted(self):
        """Mark all selected pickings as done by triggering Odoo's standard validation."""
        for record in self:
            if record.state != 'done':
                record.button_validate()

    def ws_sync_allpickings(self):
        """Sync all selected pickings to Stoqflow one by one."""
        for record in self:
            record.ws_sync_picking()

    def export_stock_moves_xlsx(self):
        """Export pickings and their stock moves to an XLSX file.

        One row is written per stock move. Each row contains the picking
        reference, partner name and sale order name, together with the move's
        product name, product SKU/internal reference, demanded quantity
        (product_uom_qty) and done quantity (quantity).

        Operates on the selected pickings. When nothing is selected, it falls
        back to every picking shown in the Stoqflow orders view (outbound or
        inbound Stoqflow pickings that are confirmed, assigned or done)."""
        pickings = self
        if not pickings:
            pickings = self.env['stock.picking'].search([
                '&',
                    '|',
                        ('df_is_webship_source', '=', True),
                        ('df_is_webship_destination', '=', True),
                    ('state', 'in', ['confirmed', 'assigned', 'done']),
            ])

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Stock moves')

        bold = workbook.add_format({'bold': True})

        headers = [
            'Picking',
            'Partner',
            'Sale order',
            'Product',
            'SKU / Code',
            'Demand (product_uom_qty)',
            'Done (quantity)',
        ]
        worksheet.set_column('A:C', 25)
        worksheet.set_column('D:D', 40)
        worksheet.set_column('E:E', 20)
        worksheet.set_column('F:G', 22)
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, bold)

        row = 1
        for picking in pickings:
            for move in picking.move_ids:
                worksheet.write(row, 0, picking.name or '')
                worksheet.write(row, 1, picking.partner_id.name or '')
                worksheet.write(row, 2, picking.sale_id.name or '')
                worksheet.write(row, 3, move.product_id.name or '')
                worksheet.write(row, 4, move.product_id.default_code or '')
                worksheet.write(row, 5, move.product_uom_qty)
                worksheet.write(row, 6, move.quantity)
                row += 1

        workbook.close()
        output.seek(0)

        filename = 'stock_moves_export_%s.xlsx' % datetime.now().strftime('%Y%m%d_%H%M%S')
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def compare_with_stoqflow(self):
        """Compare each selected picking against its corresponding Stoqflow order.

        For every picking the matching Stoqflow order is looked up (by stored
        Stoqflow id, then by origin number, then by origin id) and its ordered
        products and quantities (order_items) are compared against the
        picking's stock moves (product + product_uom_qty).

        The outcome is written to df_compare_result_webship: 'Success' when
        every product and ordered quantity matches, otherwise a per-line list
        of the discrepancies found. Every lookup, query and comparison step is
        logged at INFO level so the full trace is available in the Odoo logs."""
        handler = self.getHandler()
        handler.set_env(self.env)
        for picking in self:
            _logger.info("compare_with_stoqflow: ===== picking %s (id=%s) =====", picking.name, picking.id)
            try:
                picking._compare_single_with_stoqflow(handler)
            except Exception as e:
                _logger.exception("compare_with_stoqflow: error comparing picking %s: %s", picking.name, e)
                picking.df_compare_result_webship = Markup(
                    '<span style="color:#d9534f;font-weight:bold;">FAIL: error during comparison: %s</span>'
                ) % str(e)
        return True

    def fetch_client_name_webship(self):
        """Fetch the Stoqflow customer name for each selected picking.

        For every picking the matching Stoqflow order is looked up (by stored
        Stoqflow id, then origin number, then origin id) and the name of the
        customer that order is linked to in Stoqflow is read back and stored on
        df_client_name_webship. Showing that name next to the Odoo customer
        (partner_id) in the Stoqflow orders list makes it easy to confirm a
        picking points to the right client in both systems.

        The name comes from the client the Stoqflow order actually references
        (its client_id), not from the address snapshot Odoo originally sent, so
        a wrong link surfaces as a mismatching name. Intended as a bulk action:
        select several pickings and run it from the list header."""
        handler = self.getHandler()
        handler.set_env(self.env)
        for picking in self:
            _logger.info("fetch_client_name_webship: ===== picking %s (id=%s) =====", picking.name, picking.id)
            try:
                order = handler.find_stoqflow_order_for_picking(picking)
                if not order:
                    picking.df_client_name_webship = 'No matching Stoqflow order found'
                    _logger.warning("fetch_client_name_webship: no Stoqflow order for picking %s", picking.name)
                    continue
                name = handler.get_order_client_name(order)
                picking.df_client_name_webship = name or 'No client name found in Stoqflow'
                _logger.info("fetch_client_name_webship: picking %s -> Stoqflow client %r", picking.name, name)
            except Exception as e:
                _logger.exception("fetch_client_name_webship: error for picking %s: %s", picking.name, e)
                picking.df_client_name_webship = 'Error: %s' % e
        return True

    def _compare_single_with_stoqflow(self, handler):
        """Run the Odoo<->Stoqflow comparison for a single picking and store
        the result on df_compare_result_webship. See compare_with_stoqflow."""
        self.ensure_one()
        result = self._build_stoqflow_comparison(handler)

        if not result['found']:
            self.df_compare_result_webship = Markup(
                '<span style="color:#d9534f;font-weight:bold;">FAIL: %s</span>'
            ) % result['error']
            return

        # An order was found, so connect the picking to it regardless of
        # whether the products/quantities match exactly - the link reflects
        # "this is the corresponding Stoqflow order", and discrepancies are
        # reported separately below.
        linked = self._link_matched_stoqflow_order(result['order'])
        link_html = Markup('')
        if linked:
            link_html = Markup(
                ' <span style="color:#5cb85c;">- linked to Stoqflow (%s = %s)</span>'
            ) % (linked[0], linked[1])

        problems = result['problems']
        if not problems:
            _logger.info("compare: picking %s SUCCESS - all products and quantities match", self.name)
            self.df_compare_result_webship = Markup(
                '<span style="color:#5cb85c;font-weight:bold;">Success</span>'
            ) + link_html
        else:
            _logger.warning("compare: picking %s FAIL - %s discrepancy(ies): %s", self.name, len(problems), problems)
            lines = Markup('').join(
                Markup('<li>Line %s: %s</li>') % (idx, problem)
                for idx, problem in enumerate(problems, start=1)
            )
            self.df_compare_result_webship = Markup(
                '<span style="color:#d9534f;font-weight:bold;">FAIL:</span>%s<ul>%s</ul>'
            ) % (link_html, lines)

    def _link_matched_stoqflow_order(self, order):
        """Connect the picking to its corresponding Stoqflow object by storing
        the Stoqflow id: df_picking_id_webship for outbound orders,
        df_po_id_webship for inbound purchase orders. Called whenever a
        Stoqflow order was found, even if products/quantities don't match
        exactly (the link records the correspondence; discrepancies are
        reported separately).

        Returns a (field_name, stoqflow_id) tuple when a link was written (or
        was already present), or None when nothing could be linked."""
        self.ensure_one()
        stoqflow_id = order.get('_id') if order else None
        if not stoqflow_id:
            _logger.warning("compare: picking %s matched but Stoqflow order has no _id; cannot link", self.name)
            return None

        # The order lookup queries the /orders endpoint, so the id is an order
        # id for outbound pickings. Inbound (purchase order) pickings store it
        # on df_po_id_webship instead.
        field = 'df_po_id_webship' if self.df_object_in_webship == 'Purchase order' else 'df_picking_id_webship'
        code_field = 'df_po_code_webship' if field == 'df_po_id_webship' else 'df_picking_code_webship'

        current = self[field]
        if current != stoqflow_id:
            _logger.info("compare: picking %s exact match -> linking %s = %s (was %s)", self.name, field, stoqflow_id, current or 'empty')
            self[field] = stoqflow_id
        else:
            _logger.info("compare: picking %s already linked via %s=%s", self.name, field, stoqflow_id)

        # Populate the human-readable order/PO number straight from the order
        # dict we already fetched, so the reference column shows the name and
        # not the raw Stoqflow id. Done even when the link already existed, so
        # pickings linked by an earlier run (which may have a blank code) get
        # backfilled. df_picking_code_webship is a plain stored field, so this
        # value sticks and avoids an extra API round-trip.
        order_number = order.get('order_number')
        if order_number and self[code_field] != order_number:
            self[code_field] = order_number
            _logger.info("compare: picking %s set human-readable code %s", self.name, order_number)
        elif not order_number:
            _logger.warning("compare: picking %s matched order %s has no order_number", self.name, stoqflow_id)
        return (field, stoqflow_id)

    def _build_stoqflow_comparison(self, handler):
        """Look up the matching Stoqflow order and compare it against this
        picking's moves. Shared by compare_with_stoqflow (which renders the
        summary onto df_compare_result_webship) and compare_detail (which
        renders a per-product table). Returns a dict::

            {
                'found':    bool,            # was a Stoqflow order found
                'error':    str | None,      # message when not found
                'order':    dict | None,     # the Stoqflow order
                'lines':    [ {product_name, sku, stoqflow_product_id,
                               odoo_qty, stoqflow_qty, status, message} ],
                'problems': [str],           # discrepancy descriptions
            }

        ``status`` is one of: 'match', 'mismatch', 'missing_in_stoqflow',
        'missing_in_odoo', 'unresolved'."""
        self.ensure_one()

        order = handler.find_stoqflow_order_for_picking(self)
        if not order:
            msg = "No matching Stoqflow order found (origin=%s, Stoqflow id=%s)" % (
                self.origin or '', self.df_picking_id_webship or '',
            )
            _logger.warning("compare: picking %s -> %s", self.name, msg)
            return {'found': False, 'error': msg, 'order': None, 'lines': [], 'problems': [msg]}

        # Products whose SKU is in the 'Ignored SKUs' setting are excluded from
        # the comparison on both sides (e.g. Stoqflow-only items like a thank-you
        # flyer or packaging that should never appear on the Odoo picking).
        ignored_skus = handler._get_ignored_skus()
        # Normalize for matching so trailing spaces / casing in the setting or
        # in the Stoqflow SKU don't defeat the ignore (a common cause of a
        # product still being flagged despite being on the ignore list).
        ignored_norm = {s.strip().casefold() for s in ignored_skus if s and s.strip()}
        _logger.info(
            "compare: picking %s ignored SKUs raw=%r normalized=%r",
            self.name, sorted(ignored_skus), sorted(ignored_norm),
        )

        def is_ignored(sku):
            """True when a SKU matches the ignore list (case/space insensitive)."""
            if not sku or not ignored_norm:
                return False
            return sku.strip().casefold() in ignored_norm

        # Cache for resolving a Stoqflow product id to (name, sku), so a product
        # is fetched from Stoqflow at most once during this comparison.
        ws_product_cache = {}

        def resolve_ws_product(pid):
            if pid not in ws_product_cache:
                ws_product_cache[pid] = self._stoqflow_product_name_sku(pid, handler)
            return ws_product_cache[pid]

        # --- Build the Stoqflow side: {stoqflow_product_id: ordered_qty} ---
        ws_qty = {}
        for item in order.get('order_items') or []:
            pid = str(item.get('product_id') or '')
            qty = item.get('quantity') or 0
            if not pid:
                _logger.warning("compare: picking %s order_item without product_id: %s", self.name, item)
                continue
            if ignored_norm:
                _, ws_sku = resolve_ws_product(pid)
                if is_ignored(ws_sku):
                    _logger.info("compare: picking %s IGNORING Stoqflow product_id=%s (SKU %r matches ignore list)", self.name, pid, ws_sku)
                    continue
                _logger.info("compare: picking %s Stoqflow product_id=%s SKU %r NOT in ignore list -> kept", self.name, pid, ws_sku)
            ws_qty[pid] = ws_qty.get(pid, 0) + qty
            _logger.info("compare: stoqflow order_item product_id=%s quantity=%s (running total %s)", pid, qty, ws_qty[pid])
        _logger.info("compare: picking %s stoqflow map built: %s", self.name, ws_qty)

        # --- Build the Odoo side: {stoqflow_product_id: odoo_qty} ---
        # Group the picking's moves by their product's Stoqflow id, resolving
        # the id via the product field, falling back to a SKU lookup. The
        # quantity compared is product_uom_qty (the demand) on each stock.move.
        odoo_qty = {}
        odoo_info = {}   # stoqflow_product_id -> {'name', 'sku'}
        unresolved = []  # products without a resolvable Stoqflow id
        all_moves = self.move_ids
        _logger.info(
            "compare: picking %s has %s stock.move(s): %s",
            self.name, len(all_moves),
            [(m.id, m.product_id.display_name, m.state, m.product_uom_qty) for m in all_moves],
        )
        for move in all_moves:
            product = move.product_id
            # Cancelled moves are intentionally NOT skipped: they still appear
            # on the picking's Operations tab (with their demand), so they must
            # be reflected in the comparison. Skipping them caused a product
            # visible on the picking to show Odoo qty 0.
            if ignored_norm and is_ignored(product.default_code):
                _logger.info("compare: picking %s IGNORING Odoo product '%s' (SKU %r matches ignore list)", self.name, product.name, product.default_code)
                continue
            ws_pid = product.df_product_id_webship
            if not ws_pid and product.default_code:
                _logger.info("compare: picking %s product '%s' has no Stoqflow id, looking up by SKU %s", self.name, product.name, product.default_code)
                found = handler.findProductBySku(product.default_code)
                if isinstance(found, dict) and found.get('id'):
                    ws_pid = str(found['id'])
                    _logger.info("compare: picking %s resolved SKU %s to Stoqflow id %s", self.name, product.default_code, ws_pid)
                else:
                    _logger.warning("compare: picking %s could not resolve SKU %s in Stoqflow: %s", self.name, product.default_code, found)

            _logger.info(
                "compare: odoo move product='%s' sku=%s stoqflow_id=%s product_uom_qty=%s",
                product.name, product.default_code, ws_pid, move.product_uom_qty,
            )

            if not ws_pid:
                unresolved.append({
                    'name': product.name or '',
                    'sku': product.default_code or '',
                    'qty': move.product_uom_qty,
                })
                continue

            ws_pid = str(ws_pid)
            odoo_qty[ws_pid] = odoo_qty.get(ws_pid, 0) + move.product_uom_qty
            odoo_info.setdefault(ws_pid, {'name': product.name or '', 'sku': product.default_code or ''})
        _logger.info("compare: picking %s odoo map built: %s (unresolved: %s)", self.name, odoo_qty, unresolved)

        # --- Compare both sides, building detail lines and problem messages ---
        lines = []
        problems = []

        for info in unresolved:
            label = "%s (SKU: %s)" % (info['name'], info['sku'] or 'N/A')
            problems.append("%s: could not be matched to a Stoqflow product (missing Stoqflow id / SKU)" % label)
            lines.append({
                'product_name': info['name'],
                'sku': info['sku'],
                'stoqflow_product_id': '',
                'odoo_qty': info['qty'],
                'stoqflow_qty': 0.0,
                'status': 'unresolved',
                'message': 'No Stoqflow product id / SKU match',
            })

        # Products on the Odoo picking, checked against the Stoqflow order
        for ws_pid, odoo_amount in odoo_qty.items():
            info = odoo_info.get(ws_pid, {'name': '', 'sku': ''})
            label = "%s (SKU: %s)" % (info['name'], info['sku'] or 'N/A')
            ws_amount = ws_qty.get(ws_pid, 0)
            if ws_pid not in ws_qty:
                _logger.info("compare: picking %s product %s not present in Stoqflow order", self.name, label)
                problems.append("%s: not present in the Stoqflow order" % label)
                status, message = 'missing_in_stoqflow', 'Not present in Stoqflow order'
            elif abs(float(odoo_amount) - float(ws_amount)) > 0.001:
                _logger.info("compare: picking %s quantity mismatch for %s: odoo=%s stoqflow=%s", self.name, label, odoo_amount, ws_amount)
                problems.append("%s: quantities not corresponding (Odoo %s vs Stoqflow %s)" % (label, odoo_amount, ws_amount))
                status, message = 'mismatch', 'Quantities not corresponding'
            else:
                status, message = 'match', 'OK'
            lines.append({
                'product_name': info['name'],
                'sku': info['sku'],
                'stoqflow_product_id': ws_pid,
                'odoo_qty': odoo_amount,
                'stoqflow_qty': ws_amount,
                'status': status,
                'message': message,
            })

        # Products on the Stoqflow order that are absent from the Odoo picking
        for ws_pid, ws_amount in ws_qty.items():
            if ws_pid not in odoo_qty:
                name, sku = resolve_ws_product(ws_pid)
                label = "%s (SKU: %s)" % (name, sku or 'N/A')
                _logger.info("compare: picking %s Stoqflow product %s (qty %s) absent from Odoo picking", self.name, label, ws_amount)
                problems.append("%s: present in Stoqflow (qty %s) but not on the Odoo picking" % (label, ws_amount))
                lines.append({
                    'product_name': name,
                    'sku': sku,
                    'stoqflow_product_id': ws_pid,
                    'odoo_qty': 0.0,
                    'stoqflow_qty': ws_amount,
                    'status': 'missing_in_odoo',
                    'message': 'Present in Stoqflow but not on the Odoo picking',
                })

        return {'found': True, 'error': None, 'order': order, 'lines': lines, 'problems': problems}

    def compare_detail(self):
        """Open a dialog listing every product of this picking with its Odoo
        ordered quantity next to the Stoqflow ordered quantity, so mismatches
        can be inspected at a glance."""
        self.ensure_one()
        _logger.info("compare_detail: ===== picking %s (id=%s) =====", self.name, self.id)
        handler = self.getHandler()
        handler.set_env(self.env)

        result = self._build_stoqflow_comparison(handler)

        # Connect the picking to its Stoqflow order/PO whenever one was found,
        # regardless of discrepancies - the link records the corresponding
        # order; mismatches are shown in the detail lines below.
        message = result['error'] or ''
        if result['found']:
            linked = self._link_matched_stoqflow_order(result['order'])
            if linked:
                prefix = 'Exact match' if not result['problems'] else 'Discrepancies found'
                message = '%s - linked to Stoqflow (%s = %s)' % (prefix, linked[0], linked[1])

        wizard = self.env['webship.compare.detail'].create({
            'picking_id': self.id,
            'order_found': result['found'],
            'message': message,
            'line_ids': [(0, 0, {
                'product_name': line['product_name'],
                'sku': line['sku'],
                'stoqflow_product_id': line['stoqflow_product_id'],
                'odoo_qty': line['odoo_qty'],
                'stoqflow_qty': line['stoqflow_qty'],
                'status': line['status'],
                'message': line['message'],
            }) for line in result['lines']],
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Compare detail: %s' % self.name,
            'res_model': 'webship.compare.detail',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _stoqflow_product_name_sku(self, stoqflow_product_id, handler=None):
        """Resolve a Stoqflow product id to (name, SKU).

        First tries the Odoo product (by df_product_id_webship). If that fails
        and a handler is supplied, fetches the product from Stoqflow
        (GET /products/{id}) so its real name and SKU are shown instead of the
        raw id. Falls back to a generic label when nothing resolves."""
        product = self.env['product.product'].search(
            [('df_product_id_webship', '=', stoqflow_product_id)], limit=1
        )
        if product:
            return product.name or '', product.default_code or ''
        if handler is not None:
            ws_product = handler.get_product_by_id(stoqflow_product_id)
            if ws_product:
                return ws_product.get('name') or '', ws_product.get('sku') or ''
        return "Stoqflow product %s" % stoqflow_product_id, ''

    def _stoqflow_product_label(self, stoqflow_product_id, handler=None):
        """Build a human-readable label for a Stoqflow product id, resolving it
        to a name/SKU (Odoo product or Stoqflow API) when possible. Falls back
        to the raw Stoqflow id."""
        name, sku = self._stoqflow_product_name_sku(stoqflow_product_id, handler)
        if sku:
            return "%s (SKU: %s)" % (name, sku)
        return name


    def fetch_picking_code(self):
        """Fetch the human-readable order number from GET /orders/{id}
        and store it on the picking record. Returns the fetched code (or '')
        so the _fetch_picking_code compute can persist it."""
        code = ''
        if self.df_picking_id_webship != False and self.df_picking_id_webship != None:
            wsHandler = self.getHandler()

            pickingCode = wsHandler.get_picking_code(self.df_picking_id_webship)

            if pickingCode != None:
                code = pickingCode

        self.df_picking_code_webship = code
        return code

    def fetch_po_code(self):
        """Fetch the human-readable PO number from GET /purchase-orders/{id}
        and store it on the picking record. Returns the fetched code (or '')
        for callers that want the value."""
        code = ''
        if self.df_po_id_webship != False and self.df_po_id_webship != None:
            wsHandler = self.getHandler()

            poCode = wsHandler.get_po_code(self.df_po_id_webship)

            if poCode != None:
                code = poCode

        self.df_po_code_webship = code
        return code

    def has_all_items_in_stock(self):
        """Check if all move lines have sufficient stock available at the source location.
        Returns False if any product lacks enough available quantity."""
        self.ensure_one()
        for move_line in self.move_line_ids:
            available_qty = move_line.product_id.with_context(
                location=move_line.location_id.id
            ).qty_available
            if available_qty < move_line.qty_done or available_qty < move_line.product_uom_qty:
                return False
        return True

    def action_cancel(self):
        """Cancel the picking in Odoo, then mirror the cancellation to Stoqflow
        for any attached order or purchase order when the setting is enabled."""
        res = super().action_cancel()

        icp = self.env['ir.config_parameter'].sudo()
        if icp.get_param('webship.cancel_on_picking_cancel') != 'True':
            return res

        to_cancel = self.filtered(
            lambda p: (p.df_picking_id_webship or p.df_po_id_webship)
                      and p.df_status_webship != 'cancelled'
        )
        if not to_cancel:
            return res

        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        for picking in to_cancel:
            targets = []
            if picking.df_picking_id_webship:
                targets.append(('order', picking.df_picking_id_webship))
            if picking.df_po_id_webship:
                targets.append(('purchase_order', picking.df_po_id_webship))

            messages = []
            all_ok = True
            for object_type, object_id in targets:
                ok, err = wsHandler.cancelInWebship(object_type, object_id)
                if ok:
                    messages.append('Cancelled %s %s in Stoqflow' % (object_type, object_id))
                else:
                    all_ok = False
                    messages.append('Cancel %s %s failed: %s' % (object_type, object_id, err))
                    _logger.error(
                        'Cancel in Stoqflow failed for picking %s (%s %s): %s',
                        picking.name, object_type, object_id, err,
                    )

            vals = {'df_picking_lastsync_webship': datetime.now()}
            if all_ok:
                vals['df_status_webship'] = 'cancelled'
                vals['df_process_code'] = 'C'
            vals['df_picking_syncresult_webship'] = Markup('<br/>').join(messages)
            picking.write(vals)

        return res

    def ws_sync_picking(self):
        """Main sync action: push this picking to Stoqflow as an order (POST /orders)
        or purchase order (POST /purchase-orders).
        On success, updates process code from 'P' to 'F' and fetches readable codes.
        Soft warnings (e.g. courier present on the Stoqflow order but not linked in
        Odoo) do not block success: they are surfaced in the sync result field.
        Only fatal errors leave the picking pending."""

        # Ensure the Stoqflow object type is computed before syncing
        if self.df_object_in_webship == False:
            self._find_object_webship()

        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        # Perform the actual sync via the Stoqflow API handler
        sResult = wsHandler.sync_picking(self)
        sync_warnings = list(getattr(wsHandler, '_sync_warnings', []) or [])

        # Record the sync timestamp
        self.df_picking_lastsync_webship = datetime.now()

        if sResult == []:
            if sync_warnings:
                warning_html = '<br/>'.join(sync_warnings)
                self.df_picking_syncresult_webship = (
                    '<span style="color:orange;">⚠ Completed with warnings:</span><br/>'
                    + warning_html
                )
            else:
                self.df_picking_syncresult_webship = 'success'

            # Mark as finished ('F') so the cron job does not re-sync this picking.
            # Applies to any pre-'F' state: a manual sync from 'M' or a retry from
            # 'E' should also land on 'F' after a successful push.
            if self.df_process_code != 'F':
                _logger.info(
                    "df_process_code [%s]: %s -> F (sync successful)",
                    self.name, self.df_process_code,
                )
                self.df_process_code = 'F'

            # Fetch the human-readable order number from Stoqflow
            if self.df_picking_id_webship != False and self.df_picking_id_webship != '':
                pickingCode = wsHandler.get_picking_code(self.df_picking_id_webship)

                if pickingCode != None:
                    self.df_picking_code_webship = pickingCode
                else:
                    self.df_picking_code_webship = ''
            else:
                self.df_picking_code_webship = ''

            # Fetch the human-readable PO number from Stoqflow
            if self.df_po_id_webship != False and self.df_po_id_webship != None:
                poCode = wsHandler.get_po_code(self.df_po_id_webship)

                if poCode != None:
                    self.df_po_code_webship = poCode
                else:
                    self.df_po_code_webship = ''
            else:
                self.df_po_code_webship = ''

        else:
            # Format sync errors as an HTML list for display in the form view
            sOutput = '<p>Errors occured:</p>'
            sOutput = sOutput + '<ul>'
            for e in sResult:
                sOutput += '<li>' + e + '</li>'
            sOutput = sOutput + '</ul>'

            self.df_picking_syncresult_webship = sOutput

    def fetchQuantities(self):
        """Fetch the latest order/PO data from GET /orders/{id} or GET /purchase-orders/{id}
        and update move quantities on this picking.
        When called manually (button action), always forces an update.
        When called from automated sync, only updates if the Stoqflow record
        has been modified since the last check (compares timestamps)."""
        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        for record in self:
            has_webship_id = record.df_picking_id_webship or record.df_po_id_webship
            if not has_webship_id:
                record.df_picking_syncresult_webship = 'No Stoqflow order ID or PO ID set on this picking'
                _logger.warning("fetchQuantities: picking %s has no Stoqflow ID", record.name)
                continue

            # Check outbound orders via GET /orders/{id}
            if record.df_picking_id_webship:
                self._fetch_and_update(record, wsHandler, 'orders', record.df_picking_id_webship, force=True)
            # Check inbound purchase orders via GET /purchase-orders/{id}
            if record.df_po_id_webship:
                self._fetch_and_update(record, wsHandler, 'purchase-orders', record.df_po_id_webship, force=True)

    def _fetch_and_update(self, record, wsHandler, endpoint, webship_id, force=False):
        """Fetch a single order/PO from Stoqflow and update quantities if changed."""
        _logger.info("fetchQuantities: %s fetching %s/%s", record.name, endpoint, webship_id)

        # Tag every HTTP exchange during this fetch + follow-up calls with the
        # picking so webship.json.history rows come out filtered per picking.
        previous_picking = getattr(wsHandler, '_current_picking', None)
        wsHandler._current_picking = record
        try:
            wsOrder = wsHandler.fetchByKey(endpoint, webship_id)

            # Handle API errors
            if wsOrder.get('status') == 'error':
                msg = "API error fetching %s/%s: HTTP %s - %s" % (endpoint, webship_id, wsOrder.get('code'), wsOrder.get('txt'))
                record.df_picking_syncresult_webship = msg
                _logger.error("fetchQuantities: %s", msg)
                return

            data = wsOrder.get('data')
            if not data:
                msg = "No data returned from %s/%s" % (endpoint, webship_id)
                record.df_picking_syncresult_webship = msg
                _logger.error("fetchQuantities: %s for %s", msg, record.name)
                return

            # The order/PO exists in Stoqflow (the GET succeeded), so the
            # picking is effectively "Sent to Stoqflow". Recover any pre-'F'
            # state — typically pickings stuck on 'P' because an earlier sync
            # bookkeeping step recorded a soft warning as a fatal error.
            if record.df_process_code != 'F':
                _logger.info(
                    "df_process_code [%s]: %s -> F (fetched from Stoqflow)",
                    record.name, record.df_process_code,
                )
                record.df_process_code = 'F'

            # Backfill the human-readable code from the same payload so the
            # dashboard stops showing the raw Stoqflow key.
            order_number = data.get('order_number')
            if order_number:
                if endpoint == 'orders' and not record.df_picking_code_webship:
                    record.df_picking_code_webship = order_number
                elif endpoint == 'purchase-orders' and not record.df_po_code_webship:
                    record.df_po_code_webship = order_number

            sEdited = data.get('edited') or data.get('created')
            stoqflow_status = data.get('status', 'unknown')
            _logger.info(
                "fetchQuantities: %s -> Stoqflow status=%s, edited=%s, lastChangeDate=%s",
                record.name, stoqflow_status, sEdited, record.df_ws_lastChangeDate
            )

            # Only update quantities if the Stoqflow record has been modified (skip check when forced)
            if not force and record.df_ws_lastChangeDate and record.df_ws_lastChangeDate == sEdited:
                msg = "No changes detected (Stoqflow status: %s, last edited: %s)" % (stoqflow_status, sEdited)
                record.df_picking_syncresult_webship = msg
                _logger.info("fetchQuantities: %s - %s", record.name, msg)
                return

            _logger.info("fetchQuantities: %s -> calling setPickingQuantities", record.name)
            wsHandler.setPickingQuantities(record, data)
            record._populate_pick_analysis(data, wsHandler=wsHandler)
            record.df_ws_lastChangeDate = sEdited
        finally:
            wsHandler._current_picking = previous_picking

    def make_backorder(self):
        """Create a backorder for partially fulfilled moves.
        Moves with zero quantity are included in the backorder picking."""
        for record in self:
            moves = record.move_ids.filtered(lambda m: m.state not in ('done', 'cancel') and m.quantity != 0)
            backorder_moves = moves._create_backorder()
            backorder_moves += record.move_ids.filtered(lambda m: m.quantity == 0)
            _logger.debug("Backorder moves: %s", backorder_moves)
            if backorder_moves:
                record._create_backorder(backorder_moves=backorder_moves)
    
    def open_website_url(self):
        """Override to open Stoqflow tracking URLs when available.
        If a single parcel has a tracking URL, opens it directly.
        If multiple parcels have tracking URLs, shows a list dialog to pick one.
        Falls back to the default carrier tracking behavior otherwise."""
        self.ensure_one()
        parcels_with_url = self.df_parcel_ids.filtered(lambda p: p.df_tracking_url)
        if len(parcels_with_url) == 1:
            return {
                'type': 'ir.actions.act_url',
                'name': "Shipment Tracking Page",
                'target': 'new',
                'url': parcels_with_url.df_tracking_url,
            }
        elif len(parcels_with_url) > 1:
            return {
                'type': 'ir.actions.act_window',
                'name': "Select Parcel to Track",
                'res_model': 'webship.parcel',
                'view_mode': 'list,form',
                'domain': [('id', 'in', parcels_with_url.ids)],
                'target': 'new',
            }
        # Fallback: try df_carrier_tracking_urls if no parcels but URLs exist
        if self.df_carrier_tracking_urls:
            first_url = self.df_carrier_tracking_urls.split(',')[0].strip()
            if first_url:
                return {
                    'type': 'ir.actions.act_url',
                    'name': "Shipment Tracking Page",
                    'target': 'new',
                    'url': first_url,
                }
        return super().open_website_url()

    def merge_picking(self):
        """Merge duplicate stock moves that share the same product, UoM, source, destination, and origin.
        Deletes the individual moves and creates a single consolidated move with summed quantities.
        This prevents duplicate line items when syncing orders to Stoqflow.
        Moves with different origins (e.g. from different sale order lines) are kept separate."""
        # Count how many moves exist for each unique (product, uom, source, dest, origin) combination
        b = {}
        for mv in self.move_ids:
            tupel = (mv.product_id.id, mv.product_uom_id.id, mv.location_id.id, mv.location_dest_id.id, mv.origin or '')
            b[tupel] = b.get(tupel, 0) + 1

        # Only merge groups that have more than one move (duplicates)
        for prod, q in b.items():
            if q > 1:
                totalUomQty = 0
                totalQuantity = 0
                labelString = None
                # Sum up quantities from all duplicate moves, then delete them
                for mv in self.move_ids:
                    if (mv.product_id.id == prod[0] and mv.product_uom_id.id == prod[1]
                            and mv.location_id.id == prod[2] and mv.location_dest_id.id == prod[3]
                            and (mv.origin or '') == prod[4]):
                        totalQuantity = totalQuantity + mv.quantity
                        totalUomQty = totalUomQty + mv.product_uom_qty

                        # Reset state to draft before unlinking so Odoo allows deletion
                        mv.state = 'draft'
                        mv.unlink()

                # Create a single consolidated move with the total quantities
                move = self.env['stock.move'].create({
                    'name': 'Merged product',
                    'picking_id': self.id,
                    'product_id': prod[0],
                    'product_uom_id': prod[1],
                    'product_uom_qty': totalUomQty,
                    'quantity': totalQuantity,
                    'location_id': prod[2],
                    'location_dest_id': prod[3],
                    'origin': prod[4] or False,
                    'state': self.state
                })
