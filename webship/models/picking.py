# Extends stock.picking with Stoqflow/Webship synchronization capabilities.
# Handles creating/updating orders and purchase orders via the Stoqflow REST API
# (see https://api-documentation.stoqflow.com/), fetching status updates back,
# and merging duplicate move lines before sync.
#
# Stoqflow API context:
#   - Outbound pickings (source is Webship location) -> synced as "orders"
#     via POST/PUT /orders with statuses: concept, ready-to-pick, on-hold, completed
#   - Inbound pickings (destination is Webship location) -> synced as "purchase-orders"
#     via POST/PUT /purchase-orders with statuses: concept, ordered, completed
#   - Authentication: HTTP Basic Auth + x-addon-public-key header
#   - Pagination: 50 items/page, total-count response header, ?page=N query param
from odoo.addons.webship.models.ws import WebShipHandler
from odoo import models, fields, api
from odoo.tools.safe_eval import safe_eval

from collections import defaultdict
from datetime import datetime
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

    # Current status of this picking in Stoqflow (e.g. 'ready-to-pick', 'completed')
    df_status_webship = fields.Selection([
        ('concept', 'Concept'),
        ('ordered', 'Ordered'),
        ('on-hold', 'On Hold'),
        ('ready-to-pick', 'Ready to Pick'),
        ('picking', 'Picking'),
        ('packing', 'Packing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status in Stoqflow', readonly=True)

    # Timestamp of the last status change reported by the Stoqflow API
    df_last_changedate_webship = fields.Datetime("Last change in Stoqflow")

    # Clickable HTML link to the order page in the Stoqflow web application
    df_url_order = fields.Html('Order id Stoqflow', compute="_compute_html_picking")

    # Clickable HTML link to the purchase order page in the Stoqflow web application
    df_url_po = fields.Html('Purchase order id Stoqflow', compute="_compute_html_po")

    # Clickable HTML link to whichever type (order or PO) applies to this picking
    df_url_order_or_po = fields.Html('Order or Purchase order id Stoqflow', compute="_compute_html_order_or_po")

    # Whether the Webship tab should be visible on the picking form view
    df_show_webship_page = fields.Boolean('Show Stoqflow page', compute="_show_webship_page", store=True)

    # Related booleans indicating if source/destination locations are Webship-managed
    df_is_webship_source = fields.Boolean('is Stoqflow source location', related='location_id.df_is_webship_location')
    df_is_webship_destination = fields.Boolean('is Stoqflow destination location',
                                          related='location_dest_id.df_is_webship_location')

    # Whether the Stoqflow Parcels tab is enabled in settings
    df_show_parcels_tab = fields.Boolean('Show Parcels tab', compute="_compute_show_parcels_tab")

    # Computed Stoqflow object type based on location directions:
    #   'Order' = outbound (source is Webship), 'Purchase order' = inbound (dest is Webship), 'Mutation' = other
    df_object_in_webship = fields.Char('Object in Stoqflow', compute="_find_object_webship", store=True)

    # Process code controlling the sync lifecycle:
    #   'P' = pending, 'F' = finished, 'E' = error, 'M' = manual, 'NA' = not applicable
    df_process_code = fields.Selection([
        ('P', 'Pending'),
        ('F', 'Finished'),
        ('E', 'Error'),
        ('M', 'Manual'),
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

    def _populate_pick_analysis(self, data):
        """Build pick analysis lines from a Stoqflow order JSON payload.
        Called after setPickingQuantities during fetch quantities.

        Counting logic per line:
        1. Determine lookup_id: parent_product_id if present, else product_id
        2. Check packaging first: if found -> it's a box -> total = pkg.qty * quantity
        3. If not in packaging, check products -> total = quantity (individual items)
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

        # ----- Build packaging lookup: Stoqflow ID -> (parent product, packaging record) -----
        pkg_ws_id_to_info = {}
        all_packaging = self.env['product.packaging'].sudo().search([
            ('df_product_id_webship', '!=', False)
        ])
        for pkg in all_packaging:
            if pkg.product_id:
                pkg_ws_id_to_info[pkg.df_product_id_webship] = (pkg.product_id, pkg)
        _logger.info(
            "pick_analysis [%s]: packaging lookup - %d records",
            self.name, len(pkg_ws_id_to_info),
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

            # Step 2: check packaging FIRST
            odoo_product_id = False
            is_box = False
            packaging_id = False
            packaging_qty = 0
            total_items = qty  # default: individual items

            pkg_info = pkg_ws_id_to_info.get(lookup_id)
            if pkg_info:
                # It's a box
                product, pkg = pkg_info
                odoo_product_id = product.id
                is_box = True
                packaging_id = pkg.id
                packaging_qty = pkg.qty if pkg.qty > 0 else 1
                total_items = packaging_qty * qty
                _logger.info(
                    "pick_analysis [%s]: pick #%d lookup_id=%s -> PACKAGING '%s' (qty %s) "
                    "-> product '%s' (SKU %s) -> %s x %s = %s items",
                    self.name, idx, lookup_id, pkg.name, packaging_qty,
                    product.name, product.default_code,
                    qty, packaging_qty, total_items,
                )
            else:
                # Step 3: check products
                product = ws_id_to_product.get(lookup_id)
                if product:
                    odoo_product_id = product.id
                    total_items = qty
                    _logger.info(
                        "pick_analysis [%s]: pick #%d lookup_id=%s -> PRODUCT '%s' (SKU %s) -> %s items",
                        self.name, idx, lookup_id, product.name, product.default_code, qty,
                    )
                else:
                    _logger.warning(
                        "pick_analysis [%s]: pick #%d lookup_id=%s -> NOT FOUND "
                        "in %d packaging or %d products (product_id=%s, parent_product_id=%s)",
                        self.name, idx, lookup_id,
                        len(pkg_ws_id_to_info), len(ws_id_to_product),
                        ws_pid, ws_parent_pid,
                    )

            is_sub = bool(ws_parent_pid and ws_parent_pid != ws_pid)
            ordered_ws_id = ws_parent_pid if ws_parent_pid else ws_pid

            lines.append((0, 0, {
                'sequence': idx,
                'ws_product_id': ws_pid,
                'ws_parent_product_id': ws_parent_pid or '',
                'ws_lookup_id': lookup_id,
                'odoo_product_id': odoo_product_id,
                'is_box': is_box,
                'packaging_id': packaging_id,
                'packaging_qty': packaging_qty,
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

    @api.model
    def create(self, vals):
        """Override create to initialize all Webship fields to blank values and
        evaluate the optional domain filter to decide if the picking should be auto-synced."""
        picking = super(StockPicking, self).create(vals)

        # Clear all Stoqflow fields on newly created pickings to avoid stale data
        picking.write({
            'df_picking_id_webship':False,
            'df_picking_code_webship':'',
            'df_po_id_webship':False,
            'df_po_code_webship':'',
            'df_picking_lastsync_webship':'',
            'df_picking_syncresult_webship':'',
            'df_status_webship':'',
            'df_last_changedate_webship':False
        })

        # Log initial process code
        picking._log_process_code("initialized")

        # If auto-sync is enabled ('P'), evaluate the domain filter to exclude non-matching pickings
        if picking.df_process_code == 'P':
            self._apply_domain_filter(picking)

        return picking

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
            body="Stoqflow process code %s: <b>%s</b> (sync_order=%s, domain=%s, mk_instance_id=%s)" % (
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
        show = self.env['ir.config_parameter'].sudo().get_param('webship.show_parcels_tab', 'False') == 'True'
        for record in self:
            record.df_show_parcels_tab = show

    @api.depends("df_picking_id_webship")
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

    @api.depends("df_po_id_webship")
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

    @api.depends("df_picking_id_webship", "df_po_id_webship")
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
        """Fetch the human-readable order number from GET /orders/{id}
        and store it on the picking record."""
        if self.df_picking_id_webship != False and self.df_picking_id_webship != None:
            wsHandler = self.getHandler()

            pickingCode = wsHandler.get_picking_code(self.df_picking_id_webship)

            if pickingCode != None:
                self.df_picking_code_webship = pickingCode
            else:
                self.df_picking_code_webship = ''
        else:
            self.df_picking_code_webship = ''

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

    def ws_sync_picking(self):
        """Main sync action: push this picking to Stoqflow as an order (POST /orders)
        or purchase order (POST /purchase-orders).
        On success, updates process code from 'P' to 'F' and fetches readable codes.
        On failure, displays errors in the sync result field."""

        # Ensure the Stoqflow object type is computed before syncing
        if self.df_object_in_webship == False:
            self._find_object_webship()

        wsHandler = self.getHandler()
        wsHandler.set_env(self.env)

        # Perform the actual sync via the Stoqflow API handler
        sResult = wsHandler.sync_picking(self)

        # Record the sync timestamp
        self.df_picking_lastsync_webship = datetime.now()

        if sResult == []:
            self.df_picking_syncresult_webship = 'success'

            # Mark as finished ('F') so the cron job does not re-sync this picking
            if self.df_process_code == 'P':
                _logger.info(
                    "df_process_code [%s]: P -> F (sync successful)",
                    self.name,
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

        wsOrder = wsHandler.fetchByKey(endpoint, webship_id)
        wsHandler._log_json(record, 'received', 'GET', endpoint + '/' + webship_id, wsOrder.get('data', wsOrder))

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
        record._populate_pick_analysis(data)
        record.df_ws_lastChangeDate = sEdited

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

    def merge_picking(self):
        """Merge duplicate stock moves that share the same product, UoM, source, and destination.
        Deletes the individual moves and creates a single consolidated move with summed quantities.
        This prevents duplicate line items when syncing orders to Stoqflow."""
        # Count how many moves exist for each unique (product, uom, source, dest) combination
        b = {}
        for mv in self.move_ids:
            tupel = (mv.product_id.id, mv.product_uom.id, mv.location_id.id, mv.location_dest_id.id)
            b[tupel] = b.get(tupel, 0) + 1

        # Only merge groups that have more than one move (duplicates)
        for prod, q in b.items():
            if q > 1:
                totalUomQty = 0
                totalQuantity = 0
                labelString = None
                # Sum up quantities from all duplicate moves, then delete them
                for mv in self.move_ids:
                    if mv.product_id.id == prod[0] and mv.product_uom.id == prod[1] and mv.location_id.id == prod[
                        2] and mv.location_dest_id.id == prod[3]:
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
                    'product_uom': prod[1],
                    'product_uom_qty': totalUomQty,
                    'quantity': totalQuantity,
                    'location_id': prod[2],
                    'location_dest_id': prod[3],
                    'state': self.state
                })
