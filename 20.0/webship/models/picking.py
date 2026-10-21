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
from odoo.addons.webship.models.ws import (
    WebShipHandler, VALID_WEBSHIP_STATUSES, CLOSED_WEBSHIP_STATUSES,
    OPEN_WEBSHIP_STATUSES,
)
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from markupsafe import Markup, escape
from odoo.tools.safe_eval import safe_eval

from collections import defaultdict
from datetime import datetime
import json
import pprint
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Stoqflow order ID (returned by POST /orders) assigned after syncing an outbound order
    df_picking_id_webship = fields.Char("Order id Stoqflow", readonly=True)
    # Human-readable order number (e.g. "ORD-00123") fetched from GET /orders/{id}
    df_picking_code_webship = fields.Char("Order code Stoqflow", store=True, compute="_fetch_picking_code")

    # Stoqflow purchase order ID (returned by POST /purchase-orders) for inbound orders
    df_po_id_webship = fields.Char("Purchase order id Stoqflow", readonly=True)
    # Human-readable PO number fetched from GET /purchase-orders/{id}
    df_po_code_webship = fields.Char("Po code Stoqflow")

    # Timestamp of the last synchronization attempt to Stoqflow
    df_picking_lastsync_webship = fields.Datetime("Last sync on", readonly=True)

    # HTML result of the last sync (success message or error details)
    df_picking_syncresult_webship = fields.Html("Result last sync", readonly=True)
    # Number of consecutive failed auto-sync attempts. The status cron retries a
    # failed picking up to webship.sync_retry_count times, then stops auto-
    # processing it (manual sync required). Reset to 0 on a successful sync.
    df_sync_retry_count = fields.Integer("Stoqflow sync retry count", default=0,
                                         readonly=True, copy=False)

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

    # Clickable HTML links opening the related Odoo Sale/Purchase order, used as
    # navigable columns on the Stoqflow orders list.
    df_sale_order_link = fields.Html('Sales Order', compute="_compute_df_sale_order_link")
    df_purchase_order_link = fields.Html('Purchase Order', compute="_compute_df_purchase_order_link")

    # Whether the Webship tab should be visible on the picking form view
    df_show_webship_page = fields.Boolean('Show Stoqflow page', compute="_show_webship_page", store=True)

    # Related booleans indicating if source/destination locations are Webship-managed
    df_is_webship_source = fields.Boolean('is Stoqflow source location', related='location_id.df_is_webship_location')
    df_is_webship_destination = fields.Boolean('is Stoqflow destination location',
                                          related='location_dest_id.df_is_webship_location')

    # Whether the Stoqflow Parcels tab is enabled in settings
    df_show_parcels_tab = fields.Boolean('Show Parcels tab', compute="_compute_show_parcels_tab")

    # Whether the "Copy full Stoqflow trace" button should be shown. The trace
    # is only captured while verbose logging is enabled, so the button is only
    # useful then; it is further restricted to developer mode in the view.
    df_show_trace_button = fields.Boolean('Show Stoqflow trace button', compute="_compute_show_trace_button")

    # Whether the database is neutralized. Used together with developer mode to
    # gate the testing-only 'Debug' tab (set-error-state helper).
    df_is_neutralized = fields.Boolean('Database is neutralized', compute="_compute_df_is_neutralized")

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
        show = self.env['ir.config_parameter'].sudo().get_str('webship.show_pick_analysis_tab', 'False') == 'True'
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

        # ----- Build product lookup: Stoqflow ID -> Odoo product -----
        all_products = self.env['product.product'].sudo().search([
            ('df_product_id_webship', '!=', False)
        ])
        ws_id_to_product = {p.df_product_id_webship: p for p in all_products}
        _logger.info(
            "pick_analysis [%s]: product lookup - %d records",
            self.name, len(ws_id_to_product),
        )

        # ----- Resolve product name/SKU: Odoo first, Stoqflow only for the rest -----
        # Every product the picking touches is normally already synced in Odoo,
        # so resolve names/SKUs from there and only call GET /products?subset= for
        # the ids Odoo cannot resolve (usually none), saving an API request.
        ws_product_info = {}  # ws_id -> {'sku': ..., 'name': ...}
        all_ws_ids = set()
        for pick in picks:
            if pick.get('product_id'):
                all_ws_ids.add(pick['product_id'])
            if pick.get('parent_product_id'):
                all_ws_ids.add(pick['parent_product_id'])

        missing_ws_ids = set()
        for ws_id in all_ws_ids:
            product = ws_id_to_product.get(ws_id)
            if product:
                ws_product_info[ws_id] = {
                    'sku': product.default_code or '',
                    'name': product.name or '',
                }
            else:
                missing_ws_ids.add(ws_id)

        if wsHandler and missing_ws_ids:
            subset_param = '?subset=%s&fields=sku,name' % ','.join(missing_ws_ids)
            _logger.info(
                "pick_analysis [%s]: %d/%d product(s) not in Odoo, fetching from Stoqflow via subset",
                self.name, len(missing_ws_ids), len(all_ws_ids),
            )
            try:
                result = wsHandler.performGet('products', subset_param)
                if result.get('status') == 'success' and isinstance(result.get('data'), list):
                    for prod in result['data']:
                        ws_product_info[prod['_id']] = {
                            'sku': prod.get('sku', ''),
                            'name': prod.get('name', ''),
                        }
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
        elif all_ws_ids:
            _logger.info(
                "pick_analysis [%s]: all %d product(s) resolved from Odoo, no Stoqflow call",
                self.name, len(all_ws_ids),
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
        login = self.env['ir.config_parameter'].sudo().get_str('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_str('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_str('webship.base_url')

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

        # Everything below is initialization: the Stoqflow fields are reset and
        # the process code is decided for the first time. Those writes say
        # nothing a reader could act on, so they must not produce a 'Stoqflow
        # full trace' note in the chatter of every new picking.
        for picking in pickings.with_context(webship_skip_trace_log=True):
            # Clear all Stoqflow fields on newly created pickings to avoid stale data
            picking.write({
                'df_picking_id_webship':False,
                'df_picking_code_webship':'',
                'df_po_id_webship':False,
                'df_po_code_webship':'',
                'df_picking_lastsync_webship': False,
                'df_picking_syncresult_webship':'',
                'df_status_webship': False,
                'df_last_changedate_webship':False
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
        that was previously excluded because the field was not yet available.

        When the 'Log full trace in picking chatter' debug setting is enabled,
        also post a chatter message listing every field this write changed."""
        trace = (
            not self.env.context.get('webship_skip_trace_log')
            and self.env['ir.config_parameter'].sudo().get_str(
                'webship.log_full_trace_chatter') == 'True'
        )
        old_values = self._webship_capture_trace(vals) if trace else None

        res = super(StockPicking, self).write(vals)

        if 'mk_instance_id' in vals:
            for picking in self.filtered(lambda p: p.df_process_code == 'M'):
                picking._log_process_code("mk_instance_id changed to %s, re-evaluating" % vals['mk_instance_id'])
                self._apply_domain_filter(picking, promote=True)

        if old_values is not None:
            self._webship_post_trace(old_values)

        return res

    def _webship_capture_trace(self, vals):
        """Snapshot the pre-write value of every writable, non-relational field
        present in vals, per record. Used by the full-trace chatter debug log."""
        fields_to_track = [
            name for name in vals
            if name in self._fields and self._fields[name].type not in ('one2many', 'many2many')
        ]
        return {rec.id: {name: rec[name] for name in fields_to_track} for rec in self}

    def _webship_post_trace(self, old_values):
        """Post a chatter note per record listing the fields whose value actually
        changed during the write, as 'Label: old -> new'."""
        for rec in self:
            snapshot = old_values.get(rec.id, {})
            changes = []
            for name, old in snapshot.items():
                field = self._fields[name]
                new = rec[name]
                if old == new:
                    continue
                # False -> '' and friends are not a change worth reading; they
                # would render as an empty 'Field:  ->  ' line.
                if self._webship_trace_is_empty(old) and self._webship_trace_is_empty(new):
                    continue
                changes.append("<li>%s: %s &#8594; %s</li>" % (
                    escape(field.string or name),
                    escape(self._webship_fmt_trace(field, old)),
                    escape(self._webship_fmt_trace(field, new)),
                ))
            if changes:
                rec.with_context(webship_skip_trace_log=True).message_post(
                    body=Markup("<strong>Stoqflow full trace</strong><ul>%s</ul>")
                    % Markup("".join(changes)),
                    subtype_xmlid='mail.mt_note',
                )

    @staticmethod
    def _webship_trace_is_empty(value):
        """Whether a field value is 'nothing' for the full-trace chatter log.
        False, None and '' all render as an empty cell, so a move between them
        is not a change a reader can act on."""
        return value is False or value is None or value == ''

    def _webship_fmt_trace(self, field, value):
        """Render a field value for the full-trace chatter log."""
        if value in (False, None, ''):
            return ''
        if field.type == 'many2one':
            return value.display_name or ''
        return str(value)

    def _log_process_code(self, reason):
        """Log the current process code and relevant context to the picking chatter."""
        self.ensure_one()
        webship_sync = self.env['ir.config_parameter'].sudo().get_str('webship.sync_order')
        webship_domain = self.env['ir.config_parameter'].sudo().get_str('webship.domain')
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
        webship_domain = self.env['ir.config_parameter'].sudo().get_str('webship.domain')
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

    @api.depends('df_picking_id_webship')
    def _fetch_picking_code(self):
        """Fetch the human-readable order number from GET /orders/{id}
        whenever the Stoqflow order ID changes."""
        for record in self:
            _logger.debug('In record: %s', record)
            if record.id != False:
                if record.df_picking_id_webship != False and record.df_picking_id_webship:
                    codeWs = record.fetch_picking_code()
                    if codeWs != None:
                        record.df_picking_code_webship = codeWs
                    else:
                        record.df_picking_code_webship = ''
                else:
                    record.df_picking_code_webship = ''

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
        show = self.env['ir.config_parameter'].sudo().get_str('webship.show_parcels_tab', 'False') == 'True'
        for record in self:
            record.df_show_parcels_tab = show

    def _compute_show_trace_button(self):
        """Show the 'Copy full Stoqflow trace' button only when verbose logging
        is enabled (that setting is what captures the trace in the first place).
        The view additionally restricts the button to developer mode."""
        show = self.env['ir.config_parameter'].sudo().get_str('webship.verbose_logging', 'False') == 'True'
        for record in self:
            record.df_show_trace_button = show

    @api.depends("df_picking_id_webship", "df_picking_code_webship")
    def _compute_html_picking(self):
        """Build an HTML snippet with the order code and a clickable Stoqflow icon
        linking to the order detail page in the Stoqflow web application."""
        for record in self:
            if record.df_picking_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_str(
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
                url = self.env['ir.config_parameter'].sudo().get_str(
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
                url = self.env['ir.config_parameter'].sudo().get_str(
                    'webship.base_app_url') + 'orders/' + record.df_picking_id_webship
                shownCode = record.df_picking_id_webship

                if record.df_picking_code_webship != False and record.df_picking_code_webship != '':
                    shownCode = record.df_picking_code_webship

                record.df_url_order_or_po = shownCode + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
            elif record.df_po_id_webship != False:
                url = self.env['ir.config_parameter'].sudo().get_str(
                    'webship.base_app_url') + 'purchase-orders/' + record.df_po_id_webship
                record.df_url_order_or_po = record.df_po_code_webship + ' <a href="' + url + '" target="_blank"><img style="height:16px; width:16px" src="/webship/static/src/img/stoqflow_16px.png"/></a>'
            else:
                record.df_url_order_or_po = ''

    @api.depends("sale_id")
    def _compute_df_sale_order_link(self):
        """Build a clickable link to the related Odoo sale order, for use as a
        navigable column on the Stoqflow orders list."""
        for record in self:
            if record.sale_id:
                record.df_sale_order_link = Markup(
                    '<a href="/odoo/sales/%s">%s</a>'
                ) % (record.sale_id.id, record.sale_id.name)
            else:
                record.df_sale_order_link = ''

    @api.depends("purchase_id")
    def _compute_df_purchase_order_link(self):
        """Build a clickable link to the related Odoo purchase order, for use as
        a navigable column on the Stoqflow orders list."""
        for record in self:
            if record.purchase_id:
                record.df_purchase_order_link = Markup(
                    '<a href="/odoo/purchase/%s">%s</a>'
                ) % (record.purchase_id.id, record.purchase_id.name)
            else:
                record.df_purchase_order_link = ''

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

    def fetch_picking_code(self):
        """Fetch the human-readable order number from GET /orders/{id},
        store it on the picking record and return it (the _fetch_picking_code
        compute uses the return value)."""
        if self.df_picking_id_webship != False and self.df_picking_id_webship != None:
            wsHandler = self.getHandler()

            pickingCode = wsHandler.get_picking_code(self.df_picking_id_webship)

            if pickingCode != None:
                self.df_picking_code_webship = pickingCode
            else:
                self.df_picking_code_webship = ''
        else:
            self.df_picking_code_webship = ''
        return self.df_picking_code_webship

    def fetch_po_code(self):
        """Fetch the human-readable PO number from GET /purchase-orders/{id}
        and store it on the picking record."""
        if self.df_po_id_webship != False and self.df_po_id_webship != None:
            wsHandler = self.getHandler()

            poCode = wsHandler.get_po_code(self.df_po_id_webship)

            if poCode != None:
                self.df_po_code_webship = poCode
            else:
                self.df_po_code_webship = ''
        else:
            self.df_po_code_webship = ''

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
        if icp.get_str('webship.cancel_on_picking_cancel') != 'True':
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
        """Button/batch entry point: push this picking to Stoqflow and surface
        the result on the picking. Returns None so it is safe as a button action."""
        self._ws_push_to_stoqflow()

    def _compute_df_is_neutralized(self):
        """True when Odoo has neutralized this database (a copy/test DB). Odoo
        stores database.is_neutralized as the lowercase string 'true', so match
        tolerantly. Drives the visibility of the testing-only 'Debug' tab."""
        icp = self.env['ir.config_parameter'].sudo()
        neutralized = (icp.get_str('database.is_neutralized') or '').lower() in ('true', '1')
        for record in self:
            record.df_is_neutralized = neutralized

    def action_open_test_set_error(self):
        """Open the 'set Stoqflow error state' wizard for this picking (Debug tab
        button). Neutralized databases only; the guard is enforced when the wizard
        applies via _webship_test_set_error_state."""
        self.ensure_one()
        self._webship_assert_neutralized()
        return {
            'type': 'ir.actions.act_window',
            'name': _('TEST: set Stoqflow error state'),
            'res_model': 'webship.test.set.error',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_ids': self.ids, 'active_model': 'stock.picking'},
        }

    def action_webship_test_clear_fields(self):
        """Debug tab button: wipe every Stoqflow field on this picking so it
        looks exactly like a fresh picking that has never been sent to Stoqflow.
        Resets the process code to its default, clears the sync metadata/ids, and
        removes fetched parcels and pick-analysis lines. Neutralized DBs only."""
        self.ensure_one()
        self._webship_assert_neutralized()
        self.write({
            'df_picking_id_webship': False,
            'df_picking_code_webship': '',
            'df_po_id_webship': False,
            'df_po_code_webship': '',
            'df_picking_lastsync_webship': False,
            'df_picking_syncresult_webship': '',
            'df_status_webship': False,
            'df_last_changedate_webship': False,
            'df_ws_lastChangeDate': False,
            'df_sync_retry_count': 0,
            'df_carrier_tracking_urls': False,
            'df_process_code': self._default_process_code(),
        })
        self.df_parcel_ids.unlink()
        self.df_pick_analysis_ids.unlink()

    def _webship_assert_neutralized(self):
        """Refuse to run testing-only helpers unless the database is neutralized.

        Odoo stores ``database.is_neutralized`` as the lowercase string ``'true'``
        (not the webship ``'True'`` convention), so match tolerantly. This is the
        hard code guard that backs the developer-mode-only visibility of the
        'set Stoqflow error state' testing action."""
        icp = self.env['ir.config_parameter'].sudo()
        if (icp.get_str('database.is_neutralized') or '').lower() not in ('true', '1'):
            raise UserError(_(
                "This testing action only runs on a neutralized database."))

    def _webship_test_set_error_state(self, error_type):
        """Testing helper: put the selected picking(s) back into one of the two
        known Stoqflow error states so the sync/recovery paths can be reproduced.

        - 'unique': the "reference must be unique" POST error, i.e. the order was
          created in Stoqflow but the local link is missing. Clears the Stoqflow
          ids and sets the same HTML the sync error wrapper produces.
        - 'no_id': the "No Stoqflow order ID or PO ID set" state.

        Neutralized databases only (see _webship_assert_neutralized)."""
        self._webship_assert_neutralized()

        if error_type == 'unique':
            syncresult = Markup(
                '<p>Errors occured:</p><ul><li>'
                'Error while performing post request: reference must be unique '
                '(url: ?)</li></ul>')
        elif error_type == 'no_id':
            syncresult = 'No Stoqflow order ID or PO ID set on this picking'
        else:
            raise UserError(_("Unknown test error type: %s") % error_type)

        self.write({
            'df_picking_id_webship': False,
            'df_po_id_webship': False,
            'df_process_code': 'E',
            'df_sync_retry_count': 0,
            'df_picking_syncresult_webship': syncresult,
        })

    def action_webship_show_trace(self):
        """Gather every logged Stoqflow exchange and internal trace line for this
        picking into a single, copy-pasteable text blob and show it in a dialog,
        so it can be shared for support. Requires 'Verbose logging' (or at least
        'Log JSON payloads') to have been enabled while reproducing the problem;
        the internal step-by-step trace is only captured under verbose logging."""
        self.ensure_one()
        rows = self.env['webship.json.history'].sudo().search(
            [('picking_id', '=', self.id)], order='create_date asc, id asc')
        if not rows:
            raise UserError(_(
                "No Stoqflow trace has been recorded for this picking yet.\n\n"
                "Enable 'Verbose logging' in the Stoqflow settings, reproduce the "
                "problem (e.g. click 'Manueel synchroniseren'), then open this again."))

        lines = []
        for r in rows:
            stamp = fields.Datetime.to_string(r.create_date) if r.create_date else ''
            header = '[%s] %s %s %s' % (
                stamp, (r.direction or '').upper(), r.method or '', r.endpoint or '')
            lines.append(header.strip())
            if r.json_payload:
                lines.append(r.json_payload)
            lines.append('')  # blank line between entries

        wizard = self.env['webship.trace.export'].create({
            'trace_text': '\n'.join(lines),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stoqflow trace'),
            'res_model': 'webship.trace.export',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _ws_push_to_stoqflow(self):
        """Push this picking to Stoqflow as an order (POST /orders) or purchase
        order (POST /purchase-orders). On success, updates process code from 'P'
        to 'F' and fetches readable codes. Soft warnings (e.g. courier present on
        the Stoqflow order but not linked in Odoo) do not block success: they are
        surfaced in the sync result field.

        Returns the list of sync errors ([] on success) so the cron can decide
        whether to retry (leave 'P') or mark the picking errored ('E')."""

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

            # A successful sync clears the failed-attempt counter.
            if self.df_sync_retry_count:
                self.df_sync_retry_count = 0

            # Human-readable order number: statusWsToOdoo already captured it from
            # the detail=high payload it fetched, so only fall back to an extra
            # GET /orders/{id} when it is still missing (e.g. the payload had no
            # order_number). Avoids a redundant second round-trip per sync.
            if self.df_picking_id_webship != False and self.df_picking_id_webship != '':
                if not self.df_picking_code_webship:
                    pickingCode = wsHandler.get_picking_code(self.df_picking_id_webship)
                    self.df_picking_code_webship = pickingCode or ''
            else:
                self.df_picking_code_webship = ''

            # Human-readable PO number: same as above, statusWsToOdoo captures it
            # from the detail=high payload; only fall back to a GET if missing.
            if self.df_po_id_webship != False and self.df_po_id_webship != None:
                if not self.df_po_code_webship:
                    poCode = wsHandler.get_po_code(self.df_po_id_webship)
                    self.df_po_code_webship = poCode or ''
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

        return sResult

    def compare_lines_with_stoqflow(self):
        """Compare this picking's lines against its corresponding Stoqflow order
        and return the structured result (see _build_stoqflow_comparison).

        Backend only: this returns data, persists nothing and opens no UI - the
        frontend/rendering is intentionally left to the caller. Result dict::

            {
                'found':    bool,
                'error':    str | None,
                'order':    dict | None,
                'lines':    [ {product_name, sku, stoqflow_product_id,
                               odoo_qty, stoqflow_qty, status, message} ],
                'problems': [str],
            }
        """
        self.ensure_one()
        handler = self.getHandler()
        handler.set_env(self.env)
        return self._build_stoqflow_comparison(handler)

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

    def _build_stoqflow_comparison(self, handler):
        """Look up the matching Stoqflow order and compare it against this
        picking's moves. Returns a dict::

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

        return self._compare_picking_to_stoqflow_order(order, handler)

    def _compare_picking_to_stoqflow_order(self, order, handler):
        """Compare this picking's lines against a specific, already-fetched
        Stoqflow order dict (e.g. a backorder candidate). Returns the same dict
        shape as _build_stoqflow_comparison, always with found=True."""
        self.ensure_one()

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

    def _create_backorder(self, *args, **kwargs):
        """Link newly created backorders to their Stoqflow child order when the
        'Link backorders' setting is enabled.

        Standard Odoo backorder creation is left completely unchanged: the
        backorders are created by ``super()`` and its result is returned as-is.
        The optional Stoqflow linking runs *after* super() and is entirely
        additive (it only writes Stoqflow metadata onto the created backorder);
        the whole block is guarded so nothing here - not even reading the
        setting - can alter or block the standard 'old way' backorder creation."""
        backorders = super()._create_backorder(*args, **kwargs)
        try:
            enabled = self.env['ir.config_parameter'].sudo().get_str(
                'webship.link_backorders') == 'True'
            _logger.info(
                "link_backorder: Odoo created backorder(s) %s from %s; "
                "'Link backorders' setting is %s",
                backorders.mapped('name'), self.mapped('name'),
                'ON' if enabled else 'OFF')
            if enabled:
                for backorder in backorders:
                    try:
                        backorder._link_stoqflow_backorder()
                    except Exception as e:
                        _logger.exception(
                            "link_backorder: error linking backorder %s: %s", backorder.name, e)
        except Exception:
            _logger.exception("link_backorder: post-backorder linking step failed")
        return backorders

    def _apply_stoqflow_child_metadata(self, child):
        """Fill the Stoqflow sync metadata fields from an already-fetched order
        dict: last sync timestamp, Stoqflow status and last-change date. Used
        when linking a backorder so its Stoqflow tab is complete immediately."""
        self.df_picking_lastsync_webship = datetime.now()

        status = child.get('status')
        if status:
            if status in VALID_WEBSHIP_STATUSES:
                self.df_status_webship = status
            else:
                _logger.warning(
                    "link_backorder: unknown Stoqflow status %r for %s, not stored",
                    status, self.name)

        change_date = child.get('edited') or child.get('created')
        if change_date:
            try:
                self.df_last_changedate_webship = datetime.strptime(
                    change_date, "%Y-%m-%dT%H:%M:%S.%fZ").replace(microsecond=0)
            except (ValueError, TypeError):
                _logger.warning(
                    "link_backorder: could not parse change date %r for %s",
                    change_date, self.name)

    @staticmethod
    def _stoqflow_child_is_open(child):
        """Whether a Stoqflow child order is still an open remainder.

        When a parent order is partially handled, Stoqflow splits it into a
        child holding what was processed and a child holding the remainder
        (still 'ordered'/'on-hold'/...). Only the latter can be the counterpart
        of a freshly created Odoo backorder. The processed half is recognised by
        its status ('completed'/'cancelled') or, when the status does not settle
        it, by the traces of the work itself: a purchase order carries
        'delivered' and 'received_product_items', an outbound order carries
        'picks' and 'parcels'. A status that means the work still has to happen
        wins over those traces, so a remainder carrying leftover data is not
        mistaken for the processed half."""
        status = child.get('status') or ''
        if status in CLOSED_WEBSHIP_STATUSES:
            return False
        if status in OPEN_WEBSHIP_STATUSES:
            return True
        return not (child.get('delivered') or child.get('received_product_items')
                    or child.get('picks') or child.get('parcels'))

    @staticmethod
    def _stoqflow_picked_map(child):
        """{product_id: picked qty} from an outbound order's 'picks'.

        A pick substitution reports the product that was ordered in
        parent_product_id and the one actually picked in product_id, so the
        quantity counts against the parent (same rule as setPickingQuantities)."""
        picked = {}
        for pick in child.get('picks') or []:
            pid = str(pick.get('parent_product_id') or pick.get('product_id') or '')
            if pid:
                picked[pid] = picked.get(pid, 0) + (pick.get('quantity') or 0)
        return picked

    @staticmethod
    def _stoqflow_order_qty_map(child):
        """{product_id: ordered qty} for a Stoqflow order/PO payload."""
        qty = {}
        for item in child.get('order_items') or []:
            pid = str(item.get('product_id') or '')
            if pid:
                qty[pid] = qty.get(pid, 0) + (item.get('quantity') or 0)
        return qty

    def _stoqflow_remainder_map(self, child):
        """{product_id: unfulfilled qty} for a processed Stoqflow child.

        What was ordered but not fulfilled is exactly what Stoqflow moved to the
        backorder, so this map is the expected content of the backorder child.
        A purchase order reports fulfilment as 'received' on each order item; an
        outbound order reports it as 'picks'. Returns an empty map when the
        payload carries neither, since assuming nothing was fulfilled would turn
        the whole order into a bogus remainder."""
        items = child.get('order_items') or []
        if any('received' in item for item in items):
            fulfilled = {}
            for item in items:
                pid = str(item.get('product_id') or '')
                if pid:
                    fulfilled[pid] = fulfilled.get(pid, 0) + (item.get('received') or 0)
        elif child.get('picks'):
            fulfilled = self._stoqflow_picked_map(child)
        else:
            return {}

        remainder = {}
        for pid, ordered in self._stoqflow_order_qty_map(child).items():
            missing = ordered - fulfilled.get(pid, 0)
            if missing > 0:
                remainder[pid] = missing
        return remainder

    @staticmethod
    def _stoqflow_order_sequence(child):
        """Chronological sort key of a Stoqflow child order.

        Stoqflow numbers the children of a parent in creation order
        ('PO00028-02' -> 2), which is the order the matching Odoo backorders are
        created in as well. Falls back to the creation timestamp, then to the id,
        so the key stays total and deterministic when there is no numeric
        suffix."""
        number = child.get('order_number') or ''
        _, _, suffix = number.rpartition('-')
        try:
            sequence = int(suffix)
        except (TypeError, ValueError):
            sequence = 10 ** 9
        return (sequence, str(child.get('created') or ''), str(child.get('_id') or ''))

    def _link_backorder_verbose(self):
        """True when 'Verbose logging' is on: the backorder lookup then records
        its full decision trace (every candidate, every comparison, the raw
        Stoqflow payloads) instead of a summary."""
        try:
            return self.env['ir.config_parameter'].sudo().get_str(
                'webship.verbose_logging') == 'True'
        except Exception:
            return False

    def _emit_link_backorder_trace(self, trace, linked):
        """Dump the trace collected by find_backorder as one block.

        The block always goes to the server log - at WARNING when the backorder
        was not linked, so it stands out in the error log. With 'Verbose logging'
        enabled it is also stored as a 'trace' row in webship.json.history tagged
        with this picking, so it can be exported from the UI and shared."""
        block = "link_backorder TRACE %s (id=%s)\n  %s" % (
            self.name, self.id, "\n  ".join(trace))
        if linked:
            _logger.info("%s", block)
        else:
            _logger.warning("%s", block)
        if not self._link_backorder_verbose():
            return
        try:
            self.env['webship.json.history'].sudo().create({
                'picking_id': self.id,
                'direction': 'trace',
                'method': 'TRACE',
                'endpoint': 'link_backorder',
                'json_payload': block,
            })
        except Exception:
            # Never let tracing break the linking or the validation behind it.
            _logger.exception("link_backorder: could not store the trace of %s", self.name)

    @staticmethod
    def _stoqflow_child_label(child):
        """Short, log-friendly label of a Stoqflow child order."""
        if not child:
            return 'none'
        return '%s (%s)' % (child.get('order_number') or '?', child.get('_id') or '?')

    def _stoqflow_backorder_position(self, id_field, parent_stoqflow_id):
        """0-based position of this backorder among the not-yet-linked backorders
        hanging under ``parent_stoqflow_id``.

        Odoo and Stoqflow create their backorders in the same order, so the
        oldest unlinked Odoo backorder belongs to the oldest unlinked Stoqflow
        child. Ancestors that are already linked took their own child, so they
        do not shift this picking's position; ancestors that were left unlinked
        do."""
        position = 0
        ancestor = self.backorder_id
        while ancestor and ancestor[id_field] != parent_stoqflow_id:
            if not ancestor[id_field]:
                position += 1
            ancestor = ancestor.backorder_id
        return position

    def find_backorder(self, handler=None):
        """Find the Stoqflow backorder matching this Odoo backorder picking.

        When a parent order is partially completed, Stoqflow creates child orders
        carrying parent_order_id = <parent Stoqflow id>: one for the part that
        was processed and one for the remainder. This looks those children up
        and decides which one *is* this Odoo backorder, in this order:

          1. query the children of the nearest linked ancestor and, when that
             yields no match, of the ancestors above it - a second backorder in
             a chain is a split of the first backorder, but Stoqflow may also
             number every split off the original order;
          2. drop children already linked to another Odoo picking - that alone
             keeps a second backorder off the child the first one took;
          3. compare every remaining child against this picking's lines (the
             same comparison as the compare feature); only children whose
             contents match exactly can be linked;
          4. rank the exact matches so the right one is picked when several
             match: both systems create their backorders in the same order, so
             the child at this backorder's position among the still-unlinked
             open children wins; then an open child (not completed/cancelled,
             no delivery data) over the processed half of a split; then a child
             whose contents equal the not-received remainder of a processed
             sibling (quantity - received); then the oldest child.

        It only searches and never writes anything on the picking; applying the
        outcome is the caller's job (see _link_stoqflow_backorder).

        ``handler`` may be passed to reuse an existing Stoqflow handler; when
        omitted one is built here.

        Returns a dict:
            {
                'endpoint':   'orders' | 'purchase-orders' | None,
                'id_field':   picking field holding the Stoqflow id | None,
                'code_field': picking field holding the Stoqflow number | None,
                'parent_id':  parent Stoqflow id the match came from, or the
                              nearest linked ancestor when nothing matched | None,
                'match':      Stoqflow child dict matching exactly | None,
                'candidates': every exactly matching child, best first,
                'remainder_matches': open children holding exactly the
                              not-received quantities of a processed sibling,
                'expected':   the child chronology points at | None,
                'closest':    {'child': dict, 'result': dict, 'problems': int}
                              - closest non-matching candidate | None,
                'reason':     short explanation when 'match' is None | None,
            }

        Every step is recorded in a trace that is dumped to the server log when
        the lookup is done (WARNING when nothing was linked) and, with 'Verbose
        logging' enabled, stored on the picking as an exportable
        webship.json.history row."""
        self.ensure_one()
        trace = []
        found = self._find_backorder(handler, trace)
        self._emit_link_backorder_trace(trace, linked=bool(found['match']))
        return found

    def _find_backorder(self, handler, trace):
        """Implementation of find_backorder, appending its decisions to ``trace``."""
        verbose = self._link_backorder_verbose()

        found = {
            'endpoint': None, 'id_field': None, 'code_field': None,
            'parent_id': None, 'match': None, 'candidates': [],
            'remainder_matches': [], 'expected': None, 'closest': None,
            'reason': None,
        }

        trace.append('picking %s: state=%s object_in_stoqflow=%r backorder_of=%s' % (
            self.name, self.state, self.df_object_in_webship,
            self.backorder_id.name or 'none'))
        trace.append('lines: %s' % [
            (move.product_id.display_name, move.product_id.default_code,
             move.product_id.df_product_id_webship, move.product_uom_qty)
            for move in self.move_ids
        ])

        if self.df_object_in_webship == 'Purchase order':
            endpoint, id_field, code_field = 'purchase-orders', 'df_po_id_webship', 'df_po_code_webship'
        elif self.df_object_in_webship == 'Order':
            endpoint, id_field, code_field = 'orders', 'df_picking_id_webship', 'df_picking_code_webship'
        else:
            found['reason'] = 'not a Stoqflow order or purchase order'
            trace.append('STOP: %s' % found['reason'])
            return found
        found.update(endpoint=endpoint, id_field=id_field, code_field=code_field)

        # Parent Stoqflow ids to query, nearest ancestor first: the direct parent
        # of this backorder is the Stoqflow order its own picking is linked to,
        # but a second backorder in a chain may have to fall back on the original
        # order when Stoqflow numbers every split off the original parent instead
        # of nesting them (both layouts are handled by trying the chain in order).
        parent_ids = []
        ancestor = self.backorder_id
        while ancestor:
            value = ancestor[id_field]
            trace.append('ancestor %s: %s=%s' % (ancestor.name, id_field, value or 'not linked'))
            if value and value not in parent_ids:
                parent_ids.append(value)
            ancestor = ancestor.backorder_id
        if not parent_ids:
            found['reason'] = 'no linked Stoqflow ancestor'
            trace.append('STOP: %s' % found['reason'])
            return found
        found['parent_id'] = parent_ids[0]
        trace.append('parents to query on %s, nearest first: %s' % (endpoint, parent_ids))

        if handler is None:
            handler = self.getHandler()
            handler.set_env(self.env)

        # Never link a Stoqflow child that is already linked to another picking:
        # this is what keeps a second backorder off the child the first one took.
        already_linked = set(
            self.env['stock.picking'].search([(id_field, '!=', False)]).mapped(id_field)
        )
        trace.append('%s Stoqflow id(s) already linked to a picking%s' % (
            len(already_linked), ': %s' % sorted(already_linked) if verbose else ''))

        queried = False
        for parent_stoqflow_id in parent_ids:
            children = handler.find_stoqflow_backorders(endpoint, parent_stoqflow_id)
            trace.append('GET %s?parent_order_id=%s -> %s child(ren)%s' % (
                endpoint, parent_stoqflow_id, len(children),
                ': %s' % [self._stoqflow_child_label(c) for c in children] if children else ''))
            if verbose and children:
                try:
                    trace.append('raw children payload: %s' % json.dumps(children, default=str))
                except (TypeError, ValueError):
                    trace.append('raw children payload: %r' % (children,))
            if not children:
                continue
            queried = True
            position = self._stoqflow_backorder_position(id_field, parent_stoqflow_id)
            matches, best, remainder_matches, expected = self._rank_stoqflow_children(
                children, already_linked, handler, position, trace)
            if not found['remainder_matches']:
                found['remainder_matches'] = remainder_matches
            if found['expected'] is None:
                found['expected'] = expected
            if found['closest'] is None and best:
                found['closest'] = {'child': best[1], 'result': best[2], 'problems': best[0]}
            if not matches:
                trace.append('no exact content match under parent %s' % parent_stoqflow_id)
                continue

            found['parent_id'] = parent_stoqflow_id
            found['candidates'] = [child for _, child in matches]
            found['match'] = matches[0][1]
            found['expected'] = expected
            found['closest'] = None
            trace.append('MATCH %s (parent %s)' % (
                self._stoqflow_child_label(found['match']), parent_stoqflow_id))
            if len(matches) > 1:
                trace.append('runner-up(s) with the same contents: %s' % [
                    self._stoqflow_child_label(child) for _, child in matches[1:]])
            return found

        if found['closest']:
            found['reason'] = 'contents differ from the closest Stoqflow child'
        elif queried:
            found['reason'] = 'no unlinked Stoqflow child candidates'
        else:
            found['reason'] = 'no Stoqflow children for parent %s' % ', '.join(parent_ids)
        trace.append('NO MATCH: %s' % found['reason'])
        if found['closest']:
            trace.append('closest was %s with %s problem(s): %s' % (
                self._stoqflow_child_label(found['closest']['child']),
                found['closest']['problems'], found['closest']['result']['problems']))
        if found['expected']:
            trace.append('chronology pointed at %s' % self._stoqflow_child_label(found['expected']))
        return found

    def _rank_stoqflow_children(self, children, already_linked, handler, position=0, trace=None):
        """Rank the Stoqflow children of one parent against this picking.

        ``position`` is this backorder's 0-based rank in the Odoo backorder
        chain; since both systems create their backorders in the same order, the
        child at that position among the still-unlinked open children is the one
        chronology points at.

        Returns ``(matches, best, remainder_matches, expected)`` where ``matches``
        is the list of ``(rank, child)`` whose contents match this picking
        exactly, best first; ``best`` is ``(num_problems, child, result)`` for the
        closest non-matching child; ``remainder_matches`` are the open children
        holding exactly the not-received quantities of a processed sibling; and
        ``expected`` is the chronologically expected child (or None)."""
        # Expected backorder contents, computed from the siblings that were
        # processed: whatever was ordered but not received on them is what
        # Stoqflow moved to the backorder child. Computed over ALL children
        # (linked ones included), since the processed sibling is usually the one
        # already linked to the picking this backorder came from.
        remainders = [
            self._stoqflow_remainder_map(child) for child in children
            if not self._stoqflow_child_is_open(child)
        ]
        remainders = [r for r in remainders if r]
        if trace is None:
            trace = []
        trace.append('not-received remainder(s) of the processed sibling(s): %s' % remainders)

        # Chronology: Odoo and Stoqflow create their backorders in the same
        # order, so the still-unlinked open children, oldest first, line up with
        # the still-unlinked Odoo backorders. The one at this picking's position
        # is the child chronology points at.
        chronological = sorted(
            (child for child in children
             if child.get('_id') and child['_id'] not in already_linked
             and self._stoqflow_child_is_open(child)),
            key=self._stoqflow_order_sequence,
        )
        expected = chronological[position] if position < len(chronological) else None
        trace.append('chronology: unlinked open children oldest first %s, this backorder is #%s '
                     '-> expected %s' % (
                         [self._stoqflow_child_label(c) for c in chronological],
                         position, self._stoqflow_child_label(expected)))

        matches = []            # (rank, child) - children whose contents match exactly
        best = None             # (num_problems, child, result) - closest non-matching child
        remainder_matches = []
        for child in children:
            child_id = child.get('_id')
            if not child_id:
                trace.append('skip child without _id: %r' % (child,))
                continue
            if child_id in already_linked:
                trace.append('skip %s: already linked to another picking'
                             % self._stoqflow_child_label(child))
                continue
            is_open = self._stoqflow_child_is_open(child)
            is_remainder = self._stoqflow_order_qty_map(child) in remainders
            is_expected = expected is not None and child_id == expected.get('_id')
            if is_open and is_remainder:
                remainder_matches.append(child)
            result = self._compare_picking_to_stoqflow_order(child, handler)
            problems = result.get('problems') or []
            trace.append('candidate %s: status=%r open=%s qty=%s remainder=%s expected=%s '
                         'problems=%s' % (
                             self._stoqflow_child_label(child), child.get('status'), is_open,
                             self._stoqflow_order_qty_map(child), is_remainder, is_expected,
                             problems or 'none (exact match)'))
            for line in result.get('lines') or []:
                trace.append('    %s (sku=%s stoqflow_id=%s): odoo=%s stoqflow=%s -> %s' % (
                    line['product_name'], line['sku'] or '-', line['stoqflow_product_id'] or '-',
                    line['odoo_qty'], line['stoqflow_qty'], line['message']))
            if problems:
                if best is None or len(problems) < best[0]:
                    best = (len(problems), child, result)
                continue
            # Exact content match: rank it against the other exact matches. The
            # child chronology points at wins, then an open child over the
            # processed half of a split, then the not-received remainder, and
            # finally the oldest child.
            rank = (0 if is_expected else 1,
                    0 if is_open else 1,
                    0 if is_remainder else 1,
                    self._stoqflow_order_sequence(child))
            matches.append((rank, child))

        matches.sort(key=lambda m: m[0])
        if matches:
            trace.append('ranked exact match(es) [expected, open, remainder, age]: %s' % [
                (rank, self._stoqflow_child_label(child)) for rank, child in matches])
        if matches and expected is not None and matches[0][1].get('_id') != expected.get('_id'):
            trace.append('WARNING: the content match %s is NOT the chronologically expected '
                         'child %s' % (self._stoqflow_child_label(matches[0][1]),
                                       self._stoqflow_child_label(expected)))
            _logger.warning(
                "link_backorder: %s content match %s is NOT the chronologically "
                "expected child %s", self.name,
                matches[0][1].get('order_number') or matches[0][1].get('_id'),
                expected.get('order_number') or expected.get('_id'))
        return matches, best, remainder_matches, expected

    def _link_stoqflow_backorder(self):
        """Link this freshly created backorder to its matching Stoqflow child
        order (gated by the 'Link backorders' setting).

        The search itself lives in ``find_backorder``; this method only applies
        its outcome:
          - links the child whose contents match exactly (stores its Stoqflow id
            + number on the backorder);
          - otherwise leaves the backorder unlinked and records the differences
            on df_picking_syncresult_webship, so it is clear the picking was NOT
            linked and why."""
        self.ensure_one()

        found = self.find_backorder()
        id_field, code_field = found['id_field'], found['code_field']
        child = found['match']

        if child:
            child_id = child.get('_id')
            self[id_field] = child_id
            code = child.get('order_number')
            if code and self[code_field] != code:
                self[code_field] = code
            # Populate the sync metadata straight from the child payload we
            # already fetched, so the Stoqflow tab is complete without needing
            # a separate "set picking quantities" round-trip.
            self._apply_stoqflow_child_metadata(child)
            # A backorder starts as 'M' (Manual) because Odoo created it and it
            # must not be pushed to Stoqflow as a new order. Now that it is
            # linked, the order does exist in Stoqflow: 'F' (Sent to Stoqflow).
            if self.df_process_code != 'F':
                _logger.info(
                    "df_process_code [%s]: %s -> F (linked to Stoqflow backorder %s)",
                    self.name, self.df_process_code, code or child_id,
                )
                self.df_process_code = 'F'
                self._log_process_code(
                    "linked to Stoqflow backorder %s" % (code or child_id))
            message = Markup(
                '<span style="color:#5cb85c;font-weight:bold;">Linked to Stoqflow backorder %s</span>'
            ) % (code or child_id)
            others = found['candidates'][1:]
            if others:
                # Several children have the same contents; say which one was
                # picked and what it was picked over, so the choice is auditable.
                message += Markup(
                    '<br/><span style="color:#f0ad4e;">Other Stoqflow child order(s) with the '
                    'same contents were not linked: %s</span>'
                ) % ', '.join(
                    str(other.get('order_number') or other.get('_id')) for other in others
                )
            self.df_picking_syncresult_webship = message
            _logger.info(
                "link_backorder: %s LINKED -> %s=%s %s=%s status=%s (parent %s)",
                self.name, id_field, child_id, code_field, code,
                self.df_status_webship, found['parent_id'])
            return

        # No exact match: leave unlinked and surface the differences so it is
        # visible the picking was NOT linked and exactly why.
        closest = found['closest']
        if closest:
            child = closest['child']
            child_label = child.get('order_number') or child.get('_id')
            lines_html = Markup('').join(
                Markup('<li>%s</li>') % problem for problem in closest['result']['problems']
            )
            message = Markup(
                '<span style="color:#d9534f;font-weight:bold;">Not linked to Stoqflow: '
                'contents differ from backorder %s</span><ul>%s</ul>'
            ) % (child_label, lines_html)
            expected = found['expected']
            if expected:
                # Nothing matched, but chronology says which child this backorder
                # is - name it so the mismatch can be settled by hand.
                message += Markup(
                    '<span style="color:#f0ad4e;">By chronology this backorder is Stoqflow '
                    'child order %s, whose contents differ as listed above.</span><br/>'
                ) % (expected.get('order_number') or expected.get('_id'))
            hints = [
                hint for hint in found['remainder_matches']
                if not expected or hint.get('_id') != expected.get('_id')
            ]
            if hints:
                # A child holds exactly what Stoqflow did not receive - also a
                # likely counterpart, so name it.
                message += Markup(
                    '<span style="color:#f0ad4e;">Stoqflow child order(s) %s hold exactly the '
                    'quantities that were not received, so they are the likely counterpart; '
                    'the Odoo backorder contents differ from them.</span>'
                ) % ', '.join(
                    str(hint.get('order_number') or hint.get('_id')) for hint in hints
                )
            self.df_picking_syncresult_webship = message
            _logger.warning(
                "link_backorder: %s NOT linked - %s difference(s) vs closest child %s",
                self.name, closest['problems'], child_label)
        else:
            _logger.info(
                "link_backorder: %s not linked - %s", self.name, found['reason'])

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
                if record.df_process_code == 'M':
                    # Manual pickings are deliberately never pushed to Stoqflow,
                    # so having no Stoqflow id is their normal state, not an
                    # error. Leave the result column blank (and clear a message
                    # a previous run left behind) so it only ever shows real
                    # problems.
                    if record.df_picking_syncresult_webship:
                        record.df_picking_syncresult_webship = ''
                    _logger.debug(
                        "fetchQuantities: skipping manual picking %s (no Stoqflow ID)",
                        record.name)
                    continue
                record.df_picking_syncresult_webship = 'No Stoqflow order ID or PO ID set on this picking'
                _logger.warning("fetchQuantities: picking %s has no Stoqflow ID", record.name)
                continue

            # Check outbound orders via GET /orders/{id}
            if record.df_picking_id_webship:
                self._fetch_and_update(record, wsHandler, 'orders', record.df_picking_id_webship, force=True)
            # Check inbound purchase orders via GET /purchase-orders/{id}
            if record.df_po_id_webship:
                self._fetch_and_update(record, wsHandler, 'purchase-orders', record.df_po_id_webship, force=True)

    def apply_stoqflow_payload(self, endpoint, webship_id, data):
        """Apply an already-fetched Stoqflow order/PO payload to this picking,
        without issuing another GET. Used by the incremental status-update queue,
        which already pulled the full record (detail=high) during its poll, so
        the per-record fetch is redundant. Falls back to fetching by id when the
        payload is missing/empty, so nothing regresses if it is ever incomplete."""
        self.ensure_one()
        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)
        # data or None -> _fetch_and_update fetches by id as a fallback.
        self._fetch_and_update(self, wsHandler, endpoint, webship_id,
                               force=True, data=data or None)

    def _fetch_and_update(self, record, wsHandler, endpoint, webship_id, force=False, data=None):
        """Fetch a single order/PO from Stoqflow and update quantities if changed.

        When ``data`` is supplied (e.g. the payload the incremental poll already
        fetched), it is used as-is and no GET is issued; otherwise the record is
        fetched by id."""
        # Tag every HTTP exchange during this fetch + follow-up calls with the
        # picking so webship.json.history rows come out filtered per picking.
        previous_picking = getattr(wsHandler, '_current_picking', None)
        wsHandler._current_picking = record
        try:
            if data is None:
                _logger.info("fetchQuantities: %s fetching %s/%s", record.name, endpoint, webship_id)
                wsOrder = wsHandler.fetchByKey(endpoint, webship_id)

                # Handle API errors
                if wsOrder.get('status') == 'error':
                    msg = "API error fetching %s/%s: HTTP %s - %s" % (endpoint, webship_id, wsOrder.get('code'), wsOrder.get('txt'))
                    record.df_picking_syncresult_webship = msg
                    _logger.error("fetchQuantities: %s", msg)
                    return

                data = wsOrder.get('data')
            else:
                _logger.info("fetchQuantities: %s using pre-fetched %s/%s payload (no extra GET)",
                             record.name, endpoint, webship_id)

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
            # Building the Pick Analysis breakdown makes its own GET /products
            # call. Skip it entirely when the Pick Analysis tab is disabled -
            # otherwise every fetch spends an API request on data nobody sees.
            if record.df_show_pick_analysis_tab:
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
