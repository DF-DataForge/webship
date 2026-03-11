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
import logging
_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = ['res.config.settings']

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

    # General sync mode: 'a' = sync required, 'b' = sync not needed
    webship_modus = fields.Selection([('a','Sync nodig'),
                                   ('b','Sync niet nodig')
                                   ],string='Algemene modus', default='a', required=True,
                                   help="General synchronization mode. 'Sync required' enables automatic order syncing, 'Sync not required' disables it.")

    # --- Sync Toggle Flags ---
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
    # Matching sequence used to find existing Stoqflow clients before creating new ones
    webship_contact_match_sequence = fields.Selection(
        selection=[
            ('vat_then_email', 'VAT → E-mail'),
            ('vat_only', 'VAT only'),
            ('email_only', 'E-mail only'),
            ('email_then_vat', 'E-mail → VAT'),
        ],
        string='Contact matching sequence',
        default='email_only',
        config_parameter='webship.contact_match_sequence',
        help="Determines the order in which Stoqflow looks up an existing client when syncing a contact.\n\n"
             "• VAT → E-mail: first tries to find a client by VAT number; if no match is found, falls back to e-mail address.\n"
             "• VAT only: only looks up clients by VAT number. Contacts without a VAT will not be matched.\n"
             "• E-mail only: only looks up clients by e-mail address.\n"
             "• E-mail → VAT: first tries to find a client by e-mail address; if no match is found, falls back to VAT number."
    )
    # Automatically match (link) a client in Stoqflow when the order is synced
    webship_match_on_order_sync = fields.Boolean(
        string="Match client when order syncs",
        config_parameter='webship.match_on_order_sync',
        help="When enabled, the system automatically attempts to match (link) an Odoo contact to an existing Stoqflow client "
             "using the configured matching sequence every time an order is sent to Stoqflow. "
             "If a match is found, the Stoqflow client ID is stored on the contact so subsequent syncs skip the lookup."
    )
    # Automatically create backorders when Stoqflow marks an order as completed
    webship_auto_create_backorder = fields.Boolean(string="Auto create backorder on complete", config_parameter='webship.auto_create_backorder',
                                                   help="When enabled, a backorder is automatically created in Odoo when Stoqflow reports an order as completed with partial quantities.")
    # Log JSON payloads sent to and received from the Stoqflow API
    webship_log_json = fields.Boolean(string="Log JSON payloads", config_parameter='webship.log_json',
                                      help="When enabled, every JSON payload sent to and received from the Stoqflow API is saved in the JSON History log. Useful for debugging synchronization issues.")
    # Show the Stoqflow Parcels tab on the picking form view
    webship_show_parcels_tab = fields.Boolean(string="Show Parcels tab", config_parameter='webship.show_parcels_tab',
                                              help="When enabled, a 'Stoqflow Parcels' tab is shown on the picking form view displaying parcel details (tracking numbers, dimensions, shipping info) fetched from Stoqflow.")
    webship_show_pick_analysis_tab = fields.Boolean(string="Show Pick Analysis tab", config_parameter='webship.show_pick_analysis_tab',
                                                     help="When enabled, a 'Pick Analysis' tab is shown on the picking form view displaying a breakdown of picked items from Stoqflow, resolved to Odoo products.")
    # Fall back to sale order contact for missing phone/email on picking contact
    webship_fallback_sale_order_contact = fields.Boolean(string="Fallback to sale order contact for phone/email", config_parameter='webship.fallback_sale_order_contact',
                                                          help="When enabled, if the contact on the picking is missing a phone number or email address, the phone number or email address from the main contact on the attached sale order is used instead.")

    # --- Courier Settings ---
    # When enabled, the preferred_courier from Stoqflow orders is mapped to the carrier on the picking
    webship_fetch_courier = fields.Boolean(
        string="Map courier from Stoqflow",
        default=True,
        config_parameter='webship.fetch_courier',
        help="When enabled, the preferred_courier field from Stoqflow orders is used to "
             "automatically set the delivery carrier on Odoo pickings. If the courier is not "
             "linked to a delivery carrier in Odoo, a warning is shown in the sync result.",
    )

    # Test field for entering a product SKU (used for debugging)
    testSku = fields.Char(string="Enter SKU", help="Enter a product SKU for testing Stoqflow API calls.")

    # --- Default Values for Orders ---
    # Require full stock availability before syncing an order to Stoqflow
    webship_order_available_condition = fields.Boolean('Full availability required', config_parameter='webship.default_order_available_condition',
                                                       help="When enabled, orders are only synchronized to Stoqflow when all products have sufficient stock available at the source location. Orders with insufficient stock will remain pending.")
    # Default status for new outbound orders in Stoqflow (concept / ready-to-pick / on-hold)
    webship_default_status = fields.Selection(selection=[('concept', 'Concept'),('ready-to-pick', 'Ready to pick'),('on-hold', 'On hold')], string='Default Stoqflow order status', required=True, default='ready-to-pick', config_parameter="webship.default_status_order",
                                              help="The initial status assigned to outbound orders when they are created in Stoqflow. 'Concept' = draft, 'Ready to pick' = immediately available for warehouse picking, 'On hold' = paused.")
    # Default status for new purchase orders in Stoqflow (concept / ordered)
    webship_default_po_status = fields.Selection(selection=[('concept', 'Concept'),('ordered', 'Ordered')], string='Default Stoqflow PO status', requierd=True, default='ordered', config_parameter="webship.default_status_po_order",
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
    webship_cron_sync_statusP_interval_number = fields.Integer(string='Interval', default=30)
    webship_cron_sync_statusP_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Unit',
        default='minutes')

    webship_cron_sync_statussen = fields.Boolean(string='Fetch order info & quantities')
    webship_cron_sync_statussen_interval_number = fields.Integer(string='Interval', default=30)
    webship_cron_sync_statussen_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Unit',
        default='minutes')

    webship_cron_import_stock = fields.Boolean(string='Import stock from Stoqflow')
    webship_cron_import_stock_interval_number = fields.Integer(string='Interval', default=1)
    webship_cron_import_stock_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Unit',
        default='days')

    webship_cron_daily_report = fields.Boolean(string='Send daily report')
    webship_cron_daily_report_interval_number = fields.Integer(string='Interval', default=1)
    webship_cron_daily_report_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Unit',
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

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'webship.error_notify_user_ids',
            ','.join(str(i) for i in self.webship_error_notify_user_ids.ids)
        )
        self.env['ir.config_parameter'].sudo().set_param(
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
        }
        for xml_id, config in cron_config.items():
            cron = self._ws_get_cron(xml_id)
            if cron:
                cron.sudo().write(config)

    def get_values(self):
        res = super().get_values()
        sudo_param = self.env['ir.config_parameter'].sudo()

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
            ('ir_cron_import_stock', 'webship_cron_import_stock', 'webship_cron_import_stock_interval_number', 'webship_cron_import_stock_interval_type'),
            ('ir_cron_daily_report', 'webship_cron_daily_report', 'webship_cron_daily_report_interval_number', 'webship_cron_daily_report_interval_type'),
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
        fetches their latest data from the API, and updates the last check timestamps."""

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

    def ws_sync_all_pickings_statusP(self):
        """Cron job action: sync all pickings with process code 'P' (pending) to Stoqflow.
        Pickings without Webship locations are marked 'NA'; sync failures are marked 'E'."""
        for p in self.env['stock.picking'].search([('df_process_code','=','P')]):
            try:
                if p.location_id.df_is_webship_location == True or p.location_dest_id.df_is_webship_location:
                    p.ws_sync_picking()
                else:
                    # Mark as not applicable since it doesn't involve Webship locations
                    _logger.info(
                        "df_process_code [%s]: P -> NA (no Webship location)",
                        p.name,
                    )
                    p.write({'df_process_code': 'NA'})
            except Exception as e:
                # Mark picking as errored and log the exception, but continue processing
                _logger.exception("Error while syncing picking %s: %s", p.id, str(e))
                _logger.info(
                    "df_process_code [%s]: P -> E (sync error: %s)",
                    p.name, str(e),
                )
                p.write({
                    'df_process_code': 'E',
                    'df_picking_lastsync_webship': fields.Datetime.now(),
                    'df_picking_syncresult_webship': str(e),
                })
                self._ws_send_error_email(p.name, str(e))

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

        wsHandler.importStock()


    def ws_test_verbinding(self):
        """Test the Stoqflow API connection by performing a simple GET /products request.
        Displays a success or error notification in the Odoo UI."""
        # Validate that credentials are filled in before testing
        if self.webship_login == False or self.webship_password == False or self.webship_url == False:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Fout",
                    'type': 'danger',
                    'message': 'Login en wachtwoord zijn nodig om te testen'
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
