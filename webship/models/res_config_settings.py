# -*- coding: utf-8 -*-
# Module settings page for the Stoqflow/Webship integration.
# Provides configuration fields for API credentials, sync toggles, default statuses,
# and batch operations like matching partners/products by email/SKU.
# API reference: https://api-documentation.stoqflow.com/
import requests
from requests.auth import HTTPBasicAuth
from datetime import timedelta

from . import ws
from odoo import api, fields, models
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = ['res.config.settings']

    webship_allow_write_requests = fields.Boolean(
        string='Perform PUT, POST, DELETE requests',
        default=True,
        help="When unchecked, the Stoqflow integration will not perform any write operations "
             "(PUT, POST, DELETE) against the API. Disabled by default on sandbox databases.",
    )
    # Testing flag: omit the 'origin' block from the order payload sent to
    # Stoqflow. Useful to bypass the unique-origin constraint when creating
    # duplicate test orders in a sandbox. Not recommended in production.
    webship_skip_origin = fields.Boolean(
        string="Do not add origin when sending picking to Stoqflow (not recommended)",
        config_parameter='webship.skip_origin',
        help="When enabled, the 'origin' block (picking id + name) is omitted from the order "
             "payload sent to Stoqflow. This removes the unique-origin constraint and allows "
             "creating duplicate test orders in Stoqflow. Intended for testing only — leave "
             "disabled in production.",
    )

    # --- API Connection Settings ---
    # Stoqflow API username for HTTP Basic Auth
    webship_login = fields.Char(string='Stoqflow username', config_parameter='webship.username',
                                help="API key used for HTTP Basic Auth when connecting to the Stoqflow REST API.")
    # Stoqflow API password for HTTP Basic Auth
    webship_password = fields.Char(string='Stoqflow password', config_parameter='webship.password',
                                   help="API secret used for HTTP Basic Auth when connecting to the Stoqflow REST API.")
    # Base URL of the Stoqflow REST API (e.g. https://api.stoqflow.com/)
    webship_url = fields.Char(string='Stoqflow API URL', config_parameter='webship.base_url',
                              help="Base URL of the Stoqflow REST API, e.g. https://api.stoqflow.com/. All API calls are sent to this address.")
    # Base URL of the Stoqflow web application (used for building clickable links)
    webship_app_url = fields.Char(string='Stoqflow App URL', config_parameter='webship.base_app_url',
                                  help="Base URL of the Stoqflow web application, e.g. https://app.stoqflow.com/. Used to build clickable links to orders and products in Stoqflow.")
    # Timestamp of the last successful API connection test
    webship_last_tested = fields.Char(string='Stoqflow last tested', config_parameter='webship.last_tested',
                                      help="Timestamp of the last successful API connection test.")
    # Timestamp of the last order status sync from Stoqflow
    webship_last_check_date_status = fields.Datetime(string="Order status last check date", config_parameter='webship.last_check_date_status',
                                                     help="Timestamp of the last time outbound order statuses were fetched from Stoqflow. Used by the cron job to avoid re-processing unchanged orders.")
    # Timestamp of the last purchase order status sync from Stoqflow
    webship_last_check_po_date_status = fields.Datetime(string="PO status last check date", config_parameter='webship.last_check_po_date_status',
                                                        help="Timestamp of the last time purchase order statuses were fetched from Stoqflow. Used by the cron job to avoid re-processing unchanged purchase orders.")
    # Checkpoint of the incremental status-update queue (Stoqflow -> Odoo).
    webship_last_check_status_update = fields.Datetime(
        string="Status updates last check",
        config_parameter='webship.last_check_status_update',
        help="Checkpoint of the incremental status-update queue. Only orders and purchase orders "
             "edited in Stoqflow after this timestamp are fetched (edited_after). Advanced to the "
             "newest 'edited' timestamp seen after each successful poll. Editable so you can re-run "
             "the fetch over a wider window.",
    )
    # When the incremental status-update cron last ran (advances every run,
    # even when no changed records were found), so the settings screen can
    # confirm the cron is alive independently of the change checkpoint above.
    webship_last_run_status_update = fields.Datetime(
        string="Status updates last run",
        config_parameter='webship.last_run_status_update',
        readonly=True,
        help="When the incremental status-update cron last executed. Unlike the checkpoint, "
             "this updates on every run - including empty ones - so you can confirm the cron "
             "is running even when there were no changed orders to process.")
    # Datetime pointer used by the backorder fetch: orders created after this date are pulled and any with a parent_order_id are stored as backorders.
    webship_last_check_date_backorder_order = fields.Datetime(
        string="Backorder (orders) pointer",
        config_parameter='webship.last_check_date_backorder_order',
        help="Datetime pointer for the order backorder fetch. Only orders created after this timestamp are fetched; those with a parent_order_id are stored as backorders. The pointer is advanced to 'now' after each successful fetch. Editable so you can re-run the fetch over a wider window.",
    )
    # Datetime pointer used by the backorder fetch for purchase orders.
    webship_last_check_date_backorder_po = fields.Datetime(
        string="Backorder (purchase orders) pointer",
        config_parameter='webship.last_check_date_backorder_po',
        help="Datetime pointer for the purchase-order backorder fetch. Only purchase orders created after this timestamp are fetched; those with a parent_order_id are stored as backorders. The pointer is advanced to 'now' after each successful fetch. Editable so you can re-run the fetch over a wider window.",
    )

    # General sync mode: 'a' = sync required, 'b' = sync not needed
    webship_modus = fields.Selection([('a','Sync nodig'),
                                   ('b','Sync niet nodig')
                                   ],string='Algemene modus', default='a', required=True,
                                   help="General synchronization mode. 'Sync required' enables automatic order syncing, 'Sync not required' disables it.")

    # --- Sync Toggle Flags ---
    # Developer-only fallback: validate completed pickings with the legacy
    # make_backorder/force-done flow instead of Odoo's native backorder
    # confirmation (the default since 19.0.2.35). The legacy flow completed
    # unreceived lines at their ordered quantities when it force-validated.
    webship_use_legacy_backorder = fields.Boolean(
        string="Legacy backorder validation (fallback)",
        config_parameter='webship.use_legacy_backorder',
        help="Technical (developer mode). By default, completed orders and purchase-order receipts "
             "are validated with Odoo's native backorder confirmation: only the quantities actually "
             "picked/received in Stoqflow are validated, a backorder is created for the rest, and a "
             "receipt with 0 received units is left open. Enable this only to fall back to the "
             "previous (legacy) validation flow, which could complete unreceived lines at their "
             "ordered quantities when it force-validated a picking.")
    # Use the incremental status-update queue (edited_after) instead of polling every open picking
    webship_use_status_update_queue = fields.Boolean(
        string="Incremental status updates (edited_after)",
        config_parameter='webship.use_status_update_queue',
        help="When enabled, statuses and quantities are fetched from Stoqflow incrementally: a cron "
             "polls only the orders/purchase orders changed since the last check (edited_after) and "
             "updates the matched pickings via the status update queue. The old method (one API call "
             "per open picking on every run) is skipped while this is enabled. Disable to fall back "
             "to the old method.")
    # Link an Odoo backorder to its matching Stoqflow child order on creation
    webship_link_backorders = fields.Boolean(
        string="Link backorders",
        config_parameter='webship.link_backorders',
        help="When enabled, the moment a backorder is created in Odoo the matching Stoqflow child "
             "order is looked up (GET /{orders|purchase-orders}?parent_order_id=<parent Stoqflow id>) "
             "and compared line by line against the Odoo backorder. If the contents match exactly the "
             "backorder is linked to that Stoqflow order; if they differ, the backorder is left "
             "unlinked and the differences are shown on its sync result so it is clear why it was "
             "not linked.")
    # Enable automatic order sync (sets process code 'P' on new pickings)
    webship_sync_order = fields.Boolean(string="Sync orders", config_parameter='webship.sync_order',
                                        help="When enabled, new delivery orders are automatically marked for synchronization with Stoqflow (process code 'P'). The cron job will then push them to the Stoqflow API.")
    # Enable product sync
    webship_sync_producten = fields.Boolean(string="Sync products", config_parameter='webship.sync_products',
                                            help="When enabled, products can be synchronized with Stoqflow. Product data (SKU, name, prices, barcode) will be pushed to the Stoqflow API.")
    # Enable client sync
    webship_sync_klanten = fields.Boolean(string="Sync clients", config_parameter='webship.sync_klanten',
                                          help="When enabled, customer/client data from Odoo partners will be synchronized with the Stoqflow API.")
    # Enable supplier sync
    webship_sync_leveranciers = fields.Boolean(string="Sync suppliers", config_parameter='webship.sync_leveranciers',
                                               help="When enabled, supplier data from Odoo partners will be synchronized with the Stoqflow API.")
    # Skip matching existing Stoqflow clients before creating new ones
    webship_do_not_match_client_before_create = fields.Boolean(string="Do not match client before create", config_parameter='webship.not_match_client_before_create',
                                                               help="When enabled, Stoqflow will always create a new client instead of trying to match an existing one first. Use this if you experience duplicate matching issues.")

    # --- Contact Matching Settings ---
    # Matching sequence used to find existing Stoqflow clients before creating new ones.
    # When left blank the match step is skipped and a new client is created whenever the
    # Odoo partner has no df_client_id_webship yet.
    webship_contact_match_sequence = fields.Selection(
        selection=[
            ('vat_then_email', 'VAT → E-mail'),
            ('vat_only', 'VAT only'),
            ('email_only', 'E-mail only'),
            ('email_then_vat', 'E-mail → VAT'),
        ],
        string='Contact matching sequence',
        config_parameter='webship.contact_match_sequence',
        help="Determines the order in which Stoqflow looks up an existing client when syncing a contact.\n\n"
             "• VAT → E-mail: first tries to find a client by VAT number; if no match is found, falls back to e-mail address.\n"
             "• VAT only: only looks up clients by VAT number. Contacts without a VAT will not be matched.\n"
             "• E-mail only: only looks up clients by e-mail address.\n"
             "• E-mail → VAT: first tries to find a client by e-mail address; if no match is found, falls back to VAT number.\n"
             "• Leave blank: matching is skipped. A new Stoqflow client is created whenever the Odoo partner has no df_client_id_webship yet."
    )
    # --- Supplier Matching Settings ---
    # Matching sequence used to find existing Stoqflow suppliers before creating new ones.
    # When left blank the match step is skipped and a new supplier is created whenever the
    # Odoo partner has no df_supplier_id_webship yet.
    webship_supplier_match_sequence = fields.Selection(
        selection=[
            ('vat_then_email', 'VAT → E-mail'),
            ('vat_only', 'VAT only'),
            ('email_only', 'E-mail only'),
            ('email_then_vat', 'E-mail → VAT'),
        ],
        string='Supplier matching sequence',
        config_parameter='webship.supplier_match_sequence',
        help="Determines the order in which Stoqflow looks up an existing supplier when syncing a purchase order.\n\n"
             "• VAT → E-mail: first tries to find a supplier by VAT number; if no match is found, falls back to e-mail address.\n"
             "• VAT only: only looks up suppliers by VAT number. Partners without a VAT will not be matched.\n"
             "• E-mail only: only looks up suppliers by e-mail address.\n"
             "• E-mail → VAT: first tries to find a supplier by e-mail address; if no match is found, falls back to VAT number.\n"
             "• Leave blank: matching is skipped. A new Stoqflow supplier is created whenever the Odoo partner has no df_supplier_id_webship yet."
    )
    # Automatically match (link) a supplier in Stoqflow when the purchase order is synced.
    # NOTE: no config_parameter here — Odoo's set_param deletes the row when the value is
    # False, which makes get_param fall back to the field default (True) and re-checks the
    # box. Persisted manually as a 'True'/'False' string in set_values/get_values.
    webship_match_on_po_sync = fields.Boolean(
        string="Match supplier when purchase order syncs",
        default=True,
        help="When enabled, the system automatically attempts to match (link) an Odoo partner to an existing Stoqflow supplier "
             "using the configured supplier matching sequence every time a purchase order is sent to Stoqflow. "
             "If a match is found, the Stoqflow supplier ID is stored on the partner so subsequent syncs skip the lookup."
    )

    # Allow contacts (clients or suppliers) without an e-mail address to be transferred to Stoqflow.
    # When disabled, syncing a contact with no e-mail returns an error so the missing data can be fixed.
    webship_allow_no_email_contact = fields.Boolean(
        string="Allow to transfer contacts with no e-mail address",
        config_parameter='webship.allow_no_email_contact',
        help="When enabled, contacts (clients or suppliers) without an e-mail address can be transferred to Stoqflow. "
             "When disabled, the sync returns an error if the contact has no e-mail address."
    )
    webship_drop_invalid_email = fields.Boolean(
        string="Drop e-mail when not valid",
        config_parameter='webship.drop_invalid_email',
        help="When enabled, a contact's e-mail address is omitted from the client/order/supplier "
             "sent to Stoqflow if it is not a valid e-mail address, so Stoqflow does not reject "
             "it with 'e-mail must be a valid e-mail address'. When disabled, the invalid e-mail "
             "is sent as-is and the sync fails."
    )

    # Automatically match (link) a client in Stoqflow when the order is synced.
    # See webship_match_on_po_sync for why config_parameter is not used here.
    webship_match_on_order_sync = fields.Boolean(
        string="Match client when order syncs",
        default=True,
        help="When enabled, the system automatically attempts to match (link) an Odoo contact to an existing Stoqflow client "
             "using the configured matching sequence every time an order is sent to Stoqflow. "
             "If a match is found, the Stoqflow client ID is stored on the contact so subsequent syncs skip the lookup."
    )
    # Automatically create backorders when Stoqflow marks an order as completed
    webship_auto_create_backorder = fields.Boolean(string="Auto create backorder on complete", config_parameter='webship.auto_create_backorder',
                                                   help="When enabled, a backorder is automatically created in Odoo when Stoqflow reports an order as completed with partial quantities.")
    webship_cancel_on_picking_cancel = fields.Boolean(
        string="Cancel order/PO in Stoqflow when picking is cancelled",
        config_parameter='webship.cancel_on_picking_cancel',
        help="When enabled, cancelling a picking in Odoo also sets the corresponding "
             "order or purchase order status to 'cancelled' in Stoqflow. "
             "Pickings without a Stoqflow id are ignored.",
    )
    webship_auto_delete_backorders = fields.Boolean(
        string="Auto delete backorders in Stoqflow",
        config_parameter='webship.auto_delete_backorders',
        help="When enabled, newly fetched backorders get process code 'P' and are "
             "automatically deleted from Stoqflow by the scheduled cron job.",
    )
    webship_auto_sync_retours = fields.Boolean(
        string="Auto insert retours in Odoo",
        config_parameter='webship.auto_sync_retours',
        help="When enabled, retours are automatically synced from Stoqflow "
             "and return pickings are created in Odoo.",
    )
    # Log JSON payloads sent to and received from the Stoqflow API
    webship_log_json = fields.Boolean(string="Log JSON payloads", config_parameter='webship.log_json',
                                      help="When enabled, every JSON payload sent to and received from the Stoqflow API is saved in the JSON History log. Useful for debugging synchronization issues.")
    # Verbose logging: capture a full trace of everything the Stoqflow
    # component does (internal steps + every HTTP payload) in the JSON History
    # log, so it can be exported and shared for support.
    webship_verbose_logging = fields.Boolean(string="Verbose logging", config_parameter='webship.verbose_logging',
                                             help="When enabled, the component records a full trace of everything that happens "
                                                  "(every internal step plus every HTTP request/response payload) in the JSON History log. "
                                                  "This implies 'Log JSON payloads'. Use the 'Copy full Stoqflow trace' button on a picking to "
                                                  "get the whole trace as one copy-pasteable text for support. Turn this off again once the "
                                                  "problem is captured, as it produces a lot of log rows.")
    # Log every changed picking field in the chatter (debug tracing).
    webship_log_full_trace_chatter = fields.Boolean(
        string="Log full trace in picking chatter",
        config_parameter='webship.log_full_trace_chatter',
        help="When enabled, every write on a picking posts a chatter message listing "
             "each changed field with its old and new value. Useful for tracing what "
             "changed a picking, but noisy - leave it off in normal use.")
    # Show the Stoqflow Parcels tab on the picking form view
    webship_show_parcels_tab = fields.Boolean(string="Show Parcels tab", config_parameter='webship.show_parcels_tab',
                                              help="When enabled, a 'Stoqflow Parcels' tab is shown on the picking form view displaying parcel details (tracking numbers, dimensions, shipping info) fetched from Stoqflow.")
    webship_show_pick_analysis_tab = fields.Boolean(string="Show Pick Analysis tab", config_parameter='webship.show_pick_analysis_tab',
                                                     help="When enabled, a 'Pick Analysis' tab is shown on the picking form view displaying a breakdown of picked items from Stoqflow, resolved to Odoo products.")
    # Fall back to sale order contact for missing phone/email on picking contact
    webship_fallback_sale_order_contact = fields.Boolean(string="Fallback to sale order contact for phone/email", config_parameter='webship.fallback_sale_order_contact',
                                                          help="When enabled, if the contact on the picking is missing a phone number or email address, the phone number or email address from the main contact on the attached sale order is used instead.")

    # --- Courier Settings ---
    # When enabled, the preferred_courier from Stoqflow orders is mapped to the carrier on the picking.
    # See webship_match_on_po_sync for why config_parameter is not used here.
    webship_fetch_courier = fields.Boolean(
        string="Map courier from Stoqflow",
        default=True,
        help="When enabled, the preferred_courier field from Stoqflow orders is used to "
             "automatically set the delivery carrier on Odoo pickings. If the courier is not "
             "linked to a delivery carrier in Odoo, a warning is shown in the sync result.",
    )

    # Test field for entering a product SKU (used for debugging)
    testSku = fields.Char(string="Enter SKU", help="Enter a product SKU for testing Stoqflow API calls.")

    # List of SKUs to ignore when fetching orders from Stoqflow.
    # Products whose SKU matches an entry here are skipped during quantity
    # allocation, so they don't show up as "not found on picking" warnings.
    # Must be Char (not Text): res.config.settings only allows boolean/integer/
    # float/char/selection/many2one/datetime fields with config_parameter.
    webship_ignored_skus = fields.Char(
        string='Ignored SKUs',
        config_parameter='webship.ignored_skus',
        help="Comma-separated or newline-separated list of product SKUs to ignore when orders "
             "are fetched from Stoqflow. Use this for products that exist in Stoqflow but should "
             "not appear in Odoo (e.g. Stoqflow-only packaging items). Matching products are "
             "skipped silently and do not generate 'no matching product found on picking' warnings.",
    )

    # --- Default Values for Orders ---
    # Require full stock availability before syncing an order to Stoqflow
    webship_order_available_condition = fields.Boolean('Full availability required', config_parameter='webship.default_order_available_condition',
                                                       help="When enabled, orders are only synchronized to Stoqflow when all products have sufficient stock available at the source location. Orders with insufficient stock will remain pending.")
    # Default status for new outbound orders in Stoqflow (concept / ready-to-pick / on-hold)
    webship_default_status = fields.Selection(selection=[('concept', 'Concept'),('ready-to-pick', 'Ready to pick'),('on-hold', 'On hold')], string='Default Stoqflow order status', required=True, default='ready-to-pick', config_parameter="webship.default_status_order",
                                              help="The initial status assigned to outbound orders when they are created in Stoqflow. 'Concept' = draft, 'Ready to pick' = immediately available for warehouse picking, 'On hold' = paused.")
    # Default status for new purchase orders in Stoqflow (concept / ordered)
    webship_default_po_status = fields.Selection(selection=[('concept', 'Concept'),('ordered', 'Ordered')], string='Default Stoqflow PO status', required=True, default='ordered', config_parameter="webship.default_status_po_order",
                                                 help="The initial status assigned to purchase orders (inbound goods) when they are created in Stoqflow. 'Concept' = draft, 'Ordered' = goods expected at the warehouse.")
    # Default brand to assign to products synced to Stoqflow
    webship_default_brand = fields.Many2one(comodel_name='webship.brand', string='Default Stoqflow brand', config_parameter='webship.default_brand',
                                            help="The brand assigned to orders sent to Stoqflow. Brands are loaded from the Stoqflow API using the 'Load companies/brands/warehouses' button.")
    # Default shop to assign to orders synced to Stoqflow
    webship_default_shop = fields.Many2one(comodel_name='webship.shop', string='Default Stoqflow shop', config_parameter='webship.default_shop',
                                           help="The shop assigned to orders sent to Stoqflow. Shops belong to a brand and are loaded from the Stoqflow API using the 'Load companies/brands/warehouses' button.")
    # Optional domain filter to restrict which pickings are auto-synced (e.g. "[('mk_instance_id','in',[2,3])]")
    webship_domain = fields.Char(string='Stoqflow domain filter', config_parameter='webship.domain',
                                 help="Optional Odoo domain filter to restrict which pickings are automatically synced to Stoqflow. Only pickings matching this filter will be synced. Example: [('mk_instance_id','in',[2,3])] to only sync orders from specific marketplace instances.")
    webship_domain_text = fields.Char(
        string='Domain rule (text)',
        compute='_compute_webship_domain_text',
        inverse='_inverse_webship_domain_text',
        help="Editable text representation of the domain filter above.")

    # --- Error Notification Settings ---
    # Users who receive an email when a queue processing error occurs
    webship_error_notify_user_ids = fields.Many2many(
        'res.users',
        'webship_config_error_notify_users_rel',
        string='Error notification users',
        help="Users who will receive an email when an error occurs during queue processing.")
    # Additional raw email addresses (comma-separated) for error notifications
    webship_error_notify_emails = fields.Char(
        string='Additional notification emails',
        config_parameter='webship.error_notify_emails',
        help="Comma-separated list of additional email addresses to notify on queue errors.")
    # Post the sync errors of a picking to its chatter, so the failure detail
    # (the same list shown in "Result last sync") is kept in the message history.
    webship_log_errors_chatter = fields.Boolean(
        string='Log sync errors in picking chatter',
        config_parameter='webship.log_errors_chatter',
        help="When enabled, whenever a picking fails to sync to Stoqflow the list of "
             "errors is also posted as a message in the picking's chatter, so the failure "
             "detail stays in the message history instead of only in the 'Result last sync' "
             "field (which is overwritten on the next sync).")
    # How many times the status cron retries a failed picking before it stops
    # auto-processing it (a manual sync is then required).
    webship_sync_retry_count = fields.Integer(
        string='Sync retry count',
        config_parameter='webship.sync_retry_count',
        default=5,
        help="Number of times the status cron retries a picking that fails to sync to Stoqflow. "
             "After this many failed attempts the picking is left in the 'E' (error) state and is no "
             "longer auto-processed; a manual sync is required to retry it.")

    # --- Daily Report Settings ---
    # Users who receive the daily processing report
    webship_report_notify_user_ids = fields.Many2many(
        'res.users',
        'webship_config_report_notify_users_rel',
        string='Daily report users',
        help="Users who will receive the daily Webship processing report.")
    # Additional raw email addresses for the daily report
    webship_report_notify_emails = fields.Char(
        string='Additional report emails',
        config_parameter='webship.report_notify_emails',
        help="Comma-separated list of additional email addresses for the daily report.")

    # --- Scheduled Task Toggles and Intervals ---
    webship_cron_sync_statusP = fields.Boolean(string='Process pending orders')
    webship_cron_sync_statusP_interval_number = fields.Integer(string='Pending orders interval', default=30)
    webship_cron_sync_statusP_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Pending orders unit',
        default='minutes')

    webship_cron_sync_statussen = fields.Boolean(string='Fetch order info & quantities')
    webship_cron_sync_statussen_interval_number = fields.Integer(string='Order sync interval', default=30)
    webship_cron_sync_statussen_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Order sync unit',
        default='minutes')

    webship_cron_status_updates = fields.Boolean(string='Fetch changed orders (incremental)')
    webship_cron_status_updates_interval_number = fields.Integer(string='Changed-orders interval', default=10)
    webship_cron_status_updates_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Changed-orders unit',
        default='minutes')

    webship_cron_import_stock = fields.Boolean(string='Import stock from Stoqflow')
    webship_cron_import_stock_interval_number = fields.Integer(string='Stock import interval', default=1)
    webship_cron_import_stock_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Stock import unit',
        default='days')
    webship_adjust_odoo_stock = fields.Boolean(
        string='Adjust Odoo stock automatically',
        config_parameter='webship.adjust_odoo_stock',
        help="When enabled, importing stock from Stoqflow will also update the actual Odoo inventory quantity on the Stoqflow location.")

    webship_cron_daily_report = fields.Boolean(string='Send daily report')
    webship_cron_daily_report_interval_number = fields.Integer(string='Daily report interval', default=1)
    webship_cron_daily_report_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Daily report unit',
        default='days')
    webship_cron_sync_retours = fields.Boolean(string='Sync retours')
    webship_cron_sync_retours_interval_number = fields.Integer(string='Sync retours interval', default=30)
    webship_cron_sync_retours_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Sync retours unit',
        default='minutes')
    webship_cron_auto_delete_backorders = fields.Boolean(string='Auto delete backorders')
    webship_cron_auto_delete_backorders_interval_number = fields.Integer(string='Auto delete backorders interval', default=30)
    webship_cron_auto_delete_backorders_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Auto delete backorders unit',
        default='minutes')
    webship_cron_reclassify_object_types = fields.Boolean(string='Reclassify Stoqflow object types')
    webship_cron_reclassify_object_types_interval_number = fields.Integer(string='Reclassify object types interval', default=1)
    webship_cron_reclassify_object_types_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Reclassify object types unit',
        default='days')

    @api.depends('webship_domain')
    def _compute_webship_domain_text(self):
        for rec in self:
            rec.webship_domain_text = rec.webship_domain or '[]'

    def _inverse_webship_domain_text(self):
        for rec in self:
            rec.webship_domain = rec.webship_domain_text

    def _ws_get_cron(self, xml_id):
        """Return the ir.cron record for the given module-local xml_id, or None."""
        return self.env.ref('webship.%s' % xml_id, raise_if_not_found=False)

    def ws_run_cron_manually(self):
        """Run the cron identified by context['cron_xml_id'] immediately.
        Fired by the 'Run manually' button next to each cron row in settings."""
        xml_id = self.env.context.get('cron_xml_id')
        if not xml_id:
            raise UserError("Missing cron_xml_id in button context.")
        cron = self._ws_get_cron(xml_id)
        if not cron:
            raise UserError("Cron job '%s' was not found." % xml_id)
        cron.sudo().method_direct_trigger()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cron Job',
                'message': 'Cron "%s" ran successfully.' % (cron.name or xml_id),
                'type': 'success',
                'sticky': False,
            }
        }

    def set_values(self):
        super().set_values()
        # Boolean settings whose default is True must be persisted as explicit
        # 'True'/'False' strings — using config_parameter on the field would let
        # set_param delete the row when unchecked, and the next read would fall
        # back to the field default and silently re-enable the option.
        sudo_param = self.env['ir.config_parameter'].sudo()
        sudo_param.set_param(
            'webship.allow_write_requests',
            'True' if self.webship_allow_write_requests else 'False',
        )
        sudo_param.set_param(
            'webship.fetch_courier',
            'True' if self.webship_fetch_courier else 'False',
        )
        sudo_param.set_param(
            'webship.match_on_order_sync',
            'True' if self.webship_match_on_order_sync else 'False',
        )
        sudo_param.set_param(
            'webship.match_on_po_sync',
            'True' if self.webship_match_on_po_sync else 'False',
        )
        sudo_param.set_param(
            'webship.error_notify_user_ids',
            ','.join(str(i) for i in self.webship_error_notify_user_ids.ids)
        )
        sudo_param.set_param(
            'webship.report_notify_user_ids',
            ','.join(str(i) for i in self.webship_report_notify_user_ids.ids)
        )
        # Persist cron active states and intervals directly on the ir.cron records
        cron_config = {
            'ir_cron_sync_statusP': {
                'active': self.webship_cron_sync_statusP,
                'interval_number': self.webship_cron_sync_statusP_interval_number,
                'interval_type': self.webship_cron_sync_statusP_interval_type,
            },
            'ir_cron_sync_statussen': {
                'active': self.webship_cron_sync_statussen,
                'interval_number': self.webship_cron_sync_statussen_interval_number,
                'interval_type': self.webship_cron_sync_statussen_interval_type,
            },
            'ir_cron_status_updates': {
                'active': self.webship_cron_status_updates,
                'interval_number': self.webship_cron_status_updates_interval_number,
                'interval_type': self.webship_cron_status_updates_interval_type,
            },
            'ir_cron_import_stock': {
                'active': self.webship_cron_import_stock,
                'interval_number': self.webship_cron_import_stock_interval_number,
                'interval_type': self.webship_cron_import_stock_interval_type,
            },
            'ir_cron_daily_report': {
                'active': self.webship_cron_daily_report,
                'interval_number': self.webship_cron_daily_report_interval_number,
                'interval_type': self.webship_cron_daily_report_interval_type,
            },
            'ir_cron_sync_retours_and_backorders': {
                'active': self.webship_cron_sync_retours,
                'interval_number': self.webship_cron_sync_retours_interval_number,
                'interval_type': self.webship_cron_sync_retours_interval_type,
            },
            'ir_cron_auto_delete_backorders': {
                'active': self.webship_cron_auto_delete_backorders,
                'interval_number': self.webship_cron_auto_delete_backorders_interval_number,
                'interval_type': self.webship_cron_auto_delete_backorders_interval_type,
            },
            'ir_cron_reclassify_object_types': {
                'active': self.webship_cron_reclassify_object_types,
                'interval_number': self.webship_cron_reclassify_object_types_interval_number,
                'interval_type': self.webship_cron_reclassify_object_types_interval_type,
            },
        }
        for xml_id, config in cron_config.items():
            cron = self._ws_get_cron(xml_id)
            if cron:
                cron.sudo().write(config)

    def get_values(self):
        res = super().get_values()
        sudo_param = self.env['ir.config_parameter'].sudo()

        res['webship_allow_write_requests'] = sudo_param.get_param(
            'webship.allow_write_requests', 'True'
        ) == 'True'
        res['webship_fetch_courier'] = sudo_param.get_param(
            'webship.fetch_courier', 'True'
        ) == 'True'
        res['webship_match_on_order_sync'] = sudo_param.get_param(
            'webship.match_on_order_sync', 'True'
        ) == 'True'
        res['webship_match_on_po_sync'] = sudo_param.get_param(
            'webship.match_on_po_sync', 'True'
        ) == 'True'

        error_param = sudo_param.get_param('webship.error_notify_user_ids', '')
        if error_param:
            ids = [int(i) for i in error_param.split(',') if i.strip().isdigit()]
            res['webship_error_notify_user_ids'] = [(6, 0, ids)]
        else:
            res['webship_error_notify_user_ids'] = [(5,)]

        report_param = sudo_param.get_param('webship.report_notify_user_ids', '')
        if report_param:
            ids = [int(i) for i in report_param.split(',') if i.strip().isdigit()]
            res['webship_report_notify_user_ids'] = [(6, 0, ids)]
        else:
            res['webship_report_notify_user_ids'] = [(5,)]

        # Read cron states and intervals directly from the ir.cron records
        cron_field_map = [
            ('ir_cron_sync_statusP', 'webship_cron_sync_statusP', 'webship_cron_sync_statusP_interval_number', 'webship_cron_sync_statusP_interval_type'),
            ('ir_cron_sync_statussen', 'webship_cron_sync_statussen', 'webship_cron_sync_statussen_interval_number', 'webship_cron_sync_statussen_interval_type'),
            ('ir_cron_status_updates', 'webship_cron_status_updates', 'webship_cron_status_updates_interval_number', 'webship_cron_status_updates_interval_type'),
            ('ir_cron_import_stock', 'webship_cron_import_stock', 'webship_cron_import_stock_interval_number', 'webship_cron_import_stock_interval_type'),
            ('ir_cron_daily_report', 'webship_cron_daily_report', 'webship_cron_daily_report_interval_number', 'webship_cron_daily_report_interval_type'),
            ('ir_cron_sync_retours_and_backorders', 'webship_cron_sync_retours', 'webship_cron_sync_retours_interval_number', 'webship_cron_sync_retours_interval_type'),
            ('ir_cron_auto_delete_backorders', 'webship_cron_auto_delete_backorders', 'webship_cron_auto_delete_backorders_interval_number', 'webship_cron_auto_delete_backorders_interval_type'),
            ('ir_cron_reclassify_object_types', 'webship_cron_reclassify_object_types', 'webship_cron_reclassify_object_types_interval_number', 'webship_cron_reclassify_object_types_interval_type'),
        ]
        for xml_id, active_field, interval_num_field, interval_type_field in cron_field_map:
            cron = self._ws_get_cron(xml_id)
            if cron:
                res[active_field] = cron.active
                res[interval_num_field] = cron.interval_number
                res[interval_type_field] = cron.interval_type
            else:
                res[active_field] = False
                res[interval_num_field] = 1
                res[interval_type_field] = 'days'

        return res

    def _ws_send_error_email(self, picking_name, error_message):
        """Send an error notification email to all configured recipients."""
        user_ids_param = self.env['ir.config_parameter'].sudo().get_param('webship.error_notify_user_ids', '')
        extra_emails_param = self.env['ir.config_parameter'].sudo().get_param('webship.error_notify_emails', '')

        email_list = []
        if user_ids_param:
            ids = [int(i) for i in user_ids_param.split(',') if i.strip().isdigit()]
            users = self.env['res.users'].browse(ids)
            email_list += [u.email for u in users if u.email]
        if extra_emails_param:
            email_list += [e.strip() for e in extra_emails_param.split(',') if e.strip()]

        if not email_list:
            # A silent skip here means nobody ever learns a sync is failing.
            # Leave a clear trail in the server log at least.
            _logger.warning(
                "Stoqflow error on picking %s but no error notification "
                "recipients are configured (Settings > Stoqflow); e-mail not "
                "sent. Error: %s", picking_name, error_message)
            return

        self.env['mail.mail'].sudo().create({
            'subject': 'Webship queue error on picking %s' % picking_name,
            'body_html': (
                '<p>An error occurred while processing picking <strong>%s</strong>:</p>'
                '<pre>%s</pre>' % (picking_name, error_message)
            ),
            'email_to': ','.join(email_list),
        }).send()

    def ws_send_daily_report(self):
        """Send a daily summary email of all pickings processed in the last 24 hours."""
        sudo_param = self.env['ir.config_parameter'].sudo()
        user_ids_param = sudo_param.get_param('webship.report_notify_user_ids', '')
        extra_emails_param = sudo_param.get_param('webship.report_notify_emails', '')

        email_list = []
        if user_ids_param:
            ids = [int(i) for i in user_ids_param.split(',') if i.strip().isdigit()]
            users = self.env['res.users'].browse(ids)
            email_list += [u.email for u in users if u.email]
        if extra_emails_param:
            email_list += [e.strip() for e in extra_emails_param.split(',') if e.strip()]

        if not email_list:
            return

        since = fields.Datetime.now() - timedelta(hours=24)
        pickings = self.env['stock.picking'].search(
            [('df_picking_lastsync_webship', '>=', since)],
            order='df_picking_lastsync_webship desc'
        )

        successful = pickings.filtered(lambda p: p.df_process_code == 'F')
        errored = pickings.filtered(lambda p: p.df_process_code == 'E')
        report_date = fields.Datetime.now().strftime('%Y-%m-%d')

        body = '<h2>Webship Daily Processing Report — %s</h2>' % report_date
        body += '<h3>Summary</h3><ul>'
        body += '<li>Successfully synced: <strong>%d</strong></li>' % len(successful)
        body += '<li>Errors: <strong>%d</strong></li>' % len(errored)
        body += '<li>Total processed: <strong>%d</strong></li>' % len(pickings)
        body += '</ul>'

        if pickings:
            body += '<h3>Details</h3>'
            body += (
                '<table border="1" cellpadding="6" cellspacing="0" '
                'style="border-collapse:collapse;width:100%;font-family:sans-serif;font-size:13px">'
                '<tr style="background:#e9ecef">'
                '<th align="left">Picking</th>'
                '<th align="left">Code</th>'
                '<th align="left">Last sync</th>'
                '<th align="left">Result</th>'
                '</tr>'
            )
            for p in pickings:
                row_color = '#d4edda' if p.df_process_code == 'F' else '#f8d7da'
                lastsync = p.df_picking_lastsync_webship.strftime('%Y-%m-%d %H:%M') if p.df_picking_lastsync_webship else '-'
                result = p.df_picking_syncresult_webship or '-'
                body += (
                    '<tr style="background:%s">'
                    '<td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                    '</tr>'
                ) % (row_color, p.name, dict(p._fields['df_process_code'].selection).get(p.df_process_code, '-'), lastsync, result)
            body += '</table>'
        else:
            body += '<p>No pickings were processed in the last 24 hours.</p>'

        self.env['mail.mail'].sudo().create({
            'subject': 'Webship daily report — %s' % report_date,
            'body_html': body,
            'email_to': ','.join(email_list),
        }).send()

    def ws_exp_sup_cl(self):
        """Trigger download of the supplier/client comparison Excel report
        via the /web/download/excel?p=partner HTTP endpoint."""
        return {'type': 'ir.actions.act_url', 'url': '/web/download/excel?p=partner', 'target': 'self'}

    def ws_fetch_companies_and_warehouses(self):
        """Fetch all companies, brands, shops, and warehouses from the Stoqflow API
        (GET /company and GET /warehouses) and create/update local Odoo records.
        This populates the webship.brand, webship.shop, and webship.warehouse models."""
        wsHandler = self.getHandler()
        # Fetch companies which contain nested brands and shops
        sData = wsHandler.fetchCompanies()

        if sData['status'] == 'success':
            for p in sData['data'].values():
                for b in p['brands']:
                    # Create the brand if it does not exist yet
                    sResult = self.env['webship.brand'].search([('brand_id','=',b['_id'])])

                    if not sResult:
                        self.env['webship.brand'].create({'brand_id':b['_id'], 'name':b['name']})
                        sResult = self.env['webship.brand'].search([('brand_id', '=', b['_id'])])

                    # Create each shop under this brand if it does not exist yet
                    for s in b['shops']:
                        sRes = self.env['webship.shop'].search([('shop_id','=',s['_id'])])
                        if not sRes:
                            self.env['webship.shop'].create({'shop_id': s['_id'], 'name': s['name'], 'brand_id': sRes.id})

        # Fetch warehouses separately from GET /warehouses
        sData = wsHandler.fetchWarehouses()

        if sData['status'] == 'success':
            for p in sData['data'].values():
                for w in p:
                    # Create the warehouse if it does not exist yet
                    sResult = self.env['webship.warehouse'].search([('warehouse_id','=',w['_id'])])

                    if not sResult:
                        self.env['webship.warehouse'].create({'warehouse_id':w['_id'], 'name':w['name']})

    def ws_fetch_couriers(self):
        """Fetch all couriers from Stoqflow (GET /couriers) and create/update stoqflow.courier records.
        This populates the stoqflow.courier model so couriers can be linked to Odoo delivery carriers."""
        wsHandler = self.getHandler()
        sData = wsHandler.fetchCouriers()

        count_created = 0
        count_existing = 0

        if sData['status'] == 'success':
            for page in sData['data'].values():
                # API may return a dict (keyed by courier id) or a list
                items = page.values() if isinstance(page, dict) else page
                for courier in items:
                    if isinstance(courier, dict):
                        courier_name = courier.get('name', '')
                        courier_code = courier.get('courier', '') or courier.get('_id', '')
                    elif isinstance(courier, str):
                        courier_name = courier
                        courier_code = courier
                    else:
                        continue

                    if not courier_code:
                        continue

                    existing = self.env['stoqflow.courier'].search([('code', '=', courier_code)], limit=1)
                    if existing:
                        if courier_name and existing.name != courier_name:
                            existing.name = courier_name
                        count_existing += 1
                    else:
                        self.env['stoqflow.courier'].create({
                            'name': courier_name or courier_code,
                            'code': courier_code,
                        })
                        count_created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Stoqflow Couriers',
                'message': '%d couriers loaded (%d new, %d already existed).' % (
                    count_created + count_existing, count_created, count_existing,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def ws_match_clients_email(self):
        """Batch match Stoqflow clients to Odoo partners by email address (and/or VAT).
        Fetches all clients from GET /clients, finds unique email/VAT matches in Odoo,
        and writes the Stoqflow client _id onto the matching res.partner record."""
        wsHandler = self.getHandler()

        sData = wsHandler.fetchClients()

        # Collect all clients with their ID and email
        allClients = []
        if sData['status'] == 'success':
            for c in sData['data'].values():
                for client in c:
                    if 'email' in client.keys():
                        allClients.append([client['_id'], client['email']])

        _logger.debug("All clients fetched: %s", allClients)

        # Count how many Stoqflow clients share each email to find unique ones
        email_counts = {}
        for _, email in allClients:
            if email not in email_counts:
                email_counts[email] = 1
            else:
                email_counts[email] += 1

        # Only keep clients with a unique email (avoid ambiguous matches)
        unique_email_items = []
        for item in allClients:
            email = item[1]
            if email_counts[email] == 1:
                unique_email_items.append(item)

        # For each unique email, find the matching Odoo partner and link the Stoqflow ID
        for item in unique_email_items:
            resP = self.env['res.partner'].search([('email','=',item[1])])

            if len(resP) == 1:
                resP.write({'df_client_id_webship':item[0]})

    def ws_match_suppliers_email(self):
        """Batch match Stoqflow suppliers to Odoo partners by email address.
        Fetches all suppliers from GET /suppliers, finds unique email matches in Odoo,
        and writes the Stoqflow supplier _id onto the matching res.partner record."""
        wsHandler = self.getHandler()

        sData = wsHandler.fetchSuppliers()

        _logger.debug("Suppliers data: %s", sData)

        # Collect all suppliers with their ID and email
        allSuppliers = []
        if sData['status'] == 'success':
            for c in sData['data'].values():
                for sup in c:
                    if 'email' in sup.keys():
                        allSuppliers.append([sup['_id'], sup['email']])

        _logger.debug("All suppliers fetched: %s", allSuppliers)

        # Count email occurrences to find unique ones
        email_counts = {}
        for _, email in allSuppliers:
            if email not in email_counts:
                email_counts[email] = 1
            else:
                email_counts[email] += 1

        unique_email_items = []
        for item in allSuppliers:
            email = item[1]
            if email_counts[email] == 1:
                unique_email_items.append(item)

        # For each unique email, find the matching Odoo partner and link the Stoqflow ID
        for item in unique_email_items:
            resP = self.env['res.partner'].search([('email','=',item[1])])

            if len(resP) == 1:
                resP.write({'df_supplier_id_webship':item[0]})

    def ws_match_products_sku(self):
        """Batch match Stoqflow products to Odoo products by SKU.
        Fetches all products from GET /products, finds unique SKU matches in Odoo,
        and writes the Stoqflow product _id onto the matching product.product record."""
        wsHandler = self.getHandler()

        sData = wsHandler.fetchProducts()

        if sData['status'] == 'success':
            for p in sData['data'].values():
                for prod in p:
                    # Search for an Odoo product with the same default_code (SKU)
                    resP = self.env['product.product'].search([('default_code', '=', prod['sku'])])

                    # Only link if exactly one match is found (avoid ambiguity)
                    if len(resP) == 1:
                        resP.write({'df_product_id_webship': prod['_id']})


    def getHandler(self):
        """Create a WebShipHandler using the current settings form values."""
        wsHandler = ws.WebShipHandler(self.webship_login, self.webship_password, self.webship_url)
        return wsHandler

    def ws_sync_statusses_since_last(self):
        """Cron job action: fetch updated quantities from Stoqflow for all open Webship pickings.
        Queries all confirmed/assigned pickings with Webship source or destination locations,
        fetches their latest data from the API, and updates the last check timestamps.

        This is the full-sweep sync (one API call per open picking). It always
        runs when triggered - whether on its own schedule or via "Run manually" -
        so it stays available as a fallback when the incremental status-update
        queue (webship.use_status_update_queue) is enabled but not keeping
        pickings up to date. Because it is heavier than the incremental flow,
        keep its cron inactive in normal operation and only enable/run it when
        the incremental sync needs a full catch-up."""
        # Find all open pickings that involve Webship locations
        pickings = self.env['stock.picking'].search([
            ('state', 'in', ['confirmed', 'assigned']),
            '|',
            ('df_is_webship_source', '=', True),
            ('df_is_webship_destination', '=', True),
        ])

        # Fetch updated quantities for each picking, handling errors individually
        for p in pickings:
            try:
                p.fetchQuantities()
            except Exception as e:
                _logger.exception("Error while fetching quantities for picking %s: %s", p.id, str(e))
                p.write({'df_picking_syncresult_webship': str(e)})
                self._ws_send_error_email(p.name, str(e))

        # Update the last check timestamps for both orders and purchase orders
        lastDate = fields.Datetime.to_string(fields.Datetime.now())

        self.env['ir.config_parameter'].sudo().set_param('webship.last_check_date_status', lastDate)
        self.env['ir.config_parameter'].sudo().set_param('webship.last_check_po_date_status', lastDate)

    def ws_reclassify_object_types(self):
        """Cron job action: correct the 'Object in Stoqflow' type (Order /
        Purchase order / Mutation) and the Stoqflow tab flag on pickings whose
        stored value no longer matches their locations and documents, e.g.
        pickings created before their location was flagged as a Stoqflow
        location. Only a transfer between two Stoqflow locations without a
        sale or purchase order remains a 'Mutation'."""
        pickings, changed = self.env['stock.picking']._ws_reclassify_object_types()
        _logger.info(
            "ws_reclassify_object_types: examined %d picking(s), corrected %d",
            len(pickings), len(changed))
        return changed

    def ws_fetch_status_updates(self):
        """Manual action: run the incremental status-update queue once.
        Fetches orders/purchase-orders changed in Stoqflow since the last check
        (edited_after) and updates the matched pickings via fetchQuantities.
        Bypasses the enable toggle: a manual click is explicit intent (e.g.
        testing the flow before switching the cron over)."""
        self.env['webship.status.update']._fetch_and_process()

    def _ws_safe_send_error_email(self, picking_name, error_message):
        """Send the sync error e-mail, never letting a mail failure abort the
        surrounding cron loop."""
        try:
            self._ws_send_error_email(picking_name, error_message)
        except Exception:
            _logger.exception("Failed to send Stoqflow error e-mail for picking %s", picking_name)

    def ws_sync_all_pickings_statusP(self):
        """Cron job action: push pending pickings to Stoqflow.

        Pickings without Webship locations are marked 'NA'. A picking that fails
        to sync is marked 'E' and retried on later runs up to the configured
        retry count (webship.sync_retry_count, default 5); after that it stays
        'E' and is no longer auto-processed - a manual sync is required. An error
        e-mail with the failure detail is sent on every failed attempt, and the
        rest of the queue keeps processing regardless of any single failure."""
        param = self.env['ir.config_parameter'].sudo()
        try:
            max_retries = int(param.get_param('webship.sync_retry_count') or 5)
        except (TypeError, ValueError):
            max_retries = 5

        # Process fresh pickings ('P') and errored ones still within the retry
        # budget ('E' with fewer than max_retries failed attempts).
        pickings = self.env['stock.picking'].search([
            '|',
            ('df_process_code', '=', 'P'),
            '&', ('df_process_code', '=', 'E'), ('df_sync_retry_count', '<', max_retries),
        ])

        for p in pickings:
            if not (p.location_id.df_is_webship_location or p.location_dest_id.df_is_webship_location):
                # Not applicable: doesn't involve Webship locations.
                _logger.info("df_process_code [%s]: -> NA (no Webship location)", p.name)
                p.write({'df_process_code': 'NA'})
                continue

            # A picking already validated or cancelled in Odoo can never be
            # pushed to Stoqflow (the sync rejects done/cancelled pickings).
            # This is not an error condition - it is simply out of scope now -
            # so mark it terminal ('NA') instead of churning it as 'E', which
            # would retry it every run and e-mail the "cannot be synced" detail
            # on each attempt until the retry limit is hit.
            if p.state in ('done', 'cancel'):
                reason = 'done' if p.state == 'done' else 'cancelled'
                _logger.info(
                    "df_process_code [%s]: -> NA (picking already %s, cannot sync)",
                    p.name, reason)
                p.write({
                    'df_process_code': 'NA',
                    'df_picking_syncresult_webship':
                        'Picking already %s in Odoo - not sent to Stoqflow' % reason,
                })
                continue

            # Only Ready pickings are announced to Stoqflow. A picking still
            # waiting for stock or an earlier operation (draft/waiting/
            # confirmed) is not a failure - it simply is not ready yet - so it
            # stays 'P' with an untouched retry counter and is picked up on a
            # later run, the moment Odoo's reservation flow makes it Ready.
            # Announcing it anyway burned one retry per run on refusals like
            # "Not all items are in stock" until the picking silently dropped
            # out of this domain for good.
            if p.state != 'assigned':
                _logger.info(
                    "df_process_code [%s]: stays %s (state %s, not Ready yet)",
                    p.name, p.df_process_code, p.state)
                continue

            try:
                result = p._ws_push_to_stoqflow()
                error_detail = ' / '.join(result) if result else ''
            except Exception as e:
                _logger.exception("Error while syncing picking %s: %s", p.id, str(e))
                p.df_picking_syncresult_webship = str(e)
                result = [str(e)]
                error_detail = str(e)

            if not result:
                # Success: _ws_push_to_stoqflow marked it 'F' and reset the counter.
                continue

            # Failure: mark 'E', count the attempt, and always e-mail the detail.
            new_count = p.df_sync_retry_count + 1
            p.write({
                'df_process_code': 'E',
                'df_sync_retry_count': new_count,
                'df_picking_lastsync_webship': fields.Datetime.now(),
            })
            _logger.info("df_process_code [%s]: -> E (attempt %s/%s): %s",
                         p.name, new_count, max_retries, error_detail)
            if new_count >= max_retries:
                _logger.warning(
                    "Picking %s reached the sync retry limit (%s); auto-processing stopped, "
                    "manual sync required", p.name, max_retries)
            self._ws_safe_send_error_email(p.name, error_detail)

    def ws_reset_codes(self):
        """Re-fetch all human-readable order and PO codes from the Stoqflow API
        for every picking that has a Stoqflow ID. Useful after data migrations."""
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = ws.WebShipHandler(login, pw, base_url)

        # Re-fetch order codes from GET /orders/{id} for all linked pickings
        for r in self.env['stock.picking'].search([('df_picking_id_webship', '!=', False),('df_picking_id_webship', '!=', '')]):
            r.fetch_picking_code()

        # Re-fetch PO codes from GET /purchase-orders/{id} for all linked pickings
        for r in self.env['stock.picking'].search([('df_po_id_webship', '!=', False),('df_po_id_webship', '!=', '')]):
            r.fetch_po_code()

    def ws_import_stock(self):
        """Import stock levels from the Stoqflow API (GET /inventory) and update
        the Webship stock fields on matching stock.quant records in Odoo."""
        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = ws.WebShipHandler(login, pw, base_url)
        wsHandler.set_env(self.env)

        summary = wsHandler.importStock()
        if not summary:
            raise UserError("Fetching the stock from Stoqflow failed. Check the server log.")
        lines = ["%d products updated at %s." % (
            summary['updated'], ', '.join(sorted(summary['locations'])) or '-')]
        if summary['adjusted']:
            lines.append("Odoo stock adjusted for %d products." % summary['adjusted'])
        if summary['unmatched_companies']:
            lines.append(
                "Not imported: no Stoqflow location linked to Stoqflow company %s. "
                "Fill in 'Stoqflow company ID' on the location, or keep a single "
                "Stoqflow location." % ', '.join(sorted(summary['unmatched_companies'])))
        if summary['unknown_skus']:
            lines.append("SKUs not found in Odoo: %s" % ', '.join(summary['unknown_skus'][:20])
                         + (' …' if len(summary['unknown_skus']) > 20 else ''))
        if summary['multi_quant_skus']:
            lines.append("Several stock lines (lots), not adjusted: %s"
                         % ', '.join(summary['multi_quant_skus'][:20]))
        if summary['missing_reserved']:
            lines.append("Stoqflow sent no reserved quantity.")
        if summary['errors']:
            lines.append("Errors: %s" % '; '.join(summary['errors'][:5]))
        problems = (summary['unmatched_companies'] or summary['unknown_skus']
                    or summary['errors'])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Stock import from Stoqflow',
                'message': '\n'.join(lines),
                'type': 'warning' if problems else 'success',
                'sticky': bool(problems),
            },
        }

    def ws_sync_retours_and_backorders(self):
        """Cron job action: fetch retours from Stoqflow."""
        icp = self.env['ir.config_parameter'].sudo()
        if icp.get_param('webship.auto_sync_retours') != 'True':
            return

        login = icp.get_param('webship.username')
        pw = icp.get_param('webship.password')
        base_url = icp.get_param('webship.base_url')

        wsHandler = ws.WebShipHandler(login, pw, base_url)
        wsHandler.set_env(self.env)

        self.env['webship.retour.and.backorder']._sync_retours_from_api(wsHandler)

    def ws_fetch_retours(self):
        """Settings button: manually fetch retours from Stoqflow purchase orders."""
        return self.env['webship.retour.and.backorder'].action_sync_retours()

    def ws_fetch_backorders(self):
        """Fetch backorders from Stoqflow inventory and load corresponding orders."""
        return self.env['webship.backorder'].action_fetch_backorders()

    def ws_auto_delete_backorders(self):
        """Cron job action: delete backorders with process code 'P' from Stoqflow."""
        self.env['webship.backorder'].cron_auto_delete_backorders()

    def ws_cron_backorders(self):
        """Cron job action backing the 'Fetch backorders from Stoqflow' schedule.
        Always fetches backorders since the configured pointers; the
        auto-delete step only touches rows that already carry process_code='P',
        which are the ones the fetch marked when 'Auto delete backorders in
        Stoqflow' is enabled."""
        BO = self.env['webship.backorder']
        BO.action_fetch_backorders()
        BO.cron_auto_delete_backorders()

    def ws_test_verbinding(self):
        """Test the Stoqflow API connection by performing a simple GET /products request.
        Displays a success or error notification in the Odoo UI."""
        # Validate that credentials are filled in before testing. Use a
        # strip()-based truthiness check, not '== False': an empty string or a
        # whitespace-only value is not == False and would otherwise fall
        # through to a real request with a blank URL (raising a raw traceback).
        if not (self.webship_login or '').strip() \
                or not (self.webship_password or '').strip() \
                or not (self.webship_url or '').strip():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Fout",
                    'type': 'danger',
                    'message': 'Login, wachtwoord en URL zijn nodig om te testen'
                },
            }

        wsHandler = ws.WebShipHandler(self.webship_login, self.webship_password, self.webship_url)

        login = self.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw =  self.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url =  self.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        # Perform the test call and return the result as a notification
        testRes = wsHandler.test()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Status webservice",
                'type': testRes[0],
                'message': testRes[1]
            },
        }

    def download_xlsx_report(self):
        """Trigger download of the configuration settings XLSX report."""
        return {
            'type': 'ir.actions.act_url',
            'url': '/custom/xlsx/download_xlsx_config_report',
            'target': 'self',
        }

    def download_ws_prod_vergelijk(self):
        """Trigger download of the Odoo vs Webship product comparison XLSX report."""
        return {
            'type': 'ir.actions.act_url',
            'url': '/custom/xlsx/download_ws_prod_vergelijk',
            'target': 'self',
        }
