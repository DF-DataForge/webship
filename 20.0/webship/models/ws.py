# Core API handler for integrating Odoo with the Webship warehouse management system.
# Provides methods to sync products, partners, pickings, and orders between Odoo and Webship.
from urllib.parse import urlencode, quote

from odoo import models, _
import time
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
import logging
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry
import math
import json
import hashlib

from odoo import fields

from odoo.exceptions import UserError
from odoo.fields import Datetime
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)

# Valid status values for df_status_webship on stock.picking.
# Must match the selection field definition in picking.py.
VALID_WEBSHIP_STATUSES = {
    'concept', 'awaiting-payment', 'ordered', 'in-transit', 'delivered',
    'unpacking', 'on-hold', 'ready-to-pick', 'picking', 'ready-to-pack',
    'packing', 'ready-to-ship', 'completed', 'cancelled',
}

# Statuses meaning a Stoqflow order is finished: it can no longer be the open
# remainder of a split, so it is never the counterpart of a fresh Odoo backorder.
CLOSED_WEBSHIP_STATUSES = {'completed', 'cancelled'}

# Statuses meaning the work still has to happen, in both directions. A child
# order in one of these is the open remainder of a split whatever else its
# payload carries.
OPEN_WEBSHIP_STATUSES = {
    'concept', 'awaiting-payment', 'ordered', 'on-hold', 'ready-to-pick',
}


class WebShipHandler:
    """Central handler for all Webship API communication.
    Manages authentication, CRUD operations, and data synchronization."""
    REQUEST_TIMEOUT = (10, 30)  # (connect, read) timeout in seconds

    # Field subsets used by _debug_dump. Debug traces must never read every
    # field on a record: a bare read() evaluates group-restricted fields too
    # (e.g. the Belgian localisation's forms_281_50 on res.partner) and raises
    # AccessError for users outside those groups, killing a sync on a log line.
    # (no 'mobile': the field was removed from res.partner in Odoo 19)
    PARTNER_DEBUG_FIELDS = ['name', 'type', 'parent_id', 'street', 'street2',
                            'city', 'zip', 'country_id', 'email', 'phone',
                            'vat']
    PICKING_DEBUG_FIELDS = ['name', 'state', 'partner_id', 'origin',
                            'picking_type_id', 'df_process_code',
                            'df_status_webship', 'df_object_in_webship',
                            'df_picking_id_webship', 'df_po_id_webship']
    MOVE_DEBUG_FIELDS = ['product_id', 'state', 'picked', 'product_uom_qty',
                         'quantity', 'location_id', 'location_dest_id']
    MOVE_LINE_DEBUG_FIELDS = ['product_id', 'state', 'quantity',
                              'quantity_product_uom', 'lot_id', 'lot_name',
                              'move_id', 'location_id', 'location_dest_id']

    def __init__(self, ws_login, ws_password, ws_base_url):
        """Initialize the handler with Webship API credentials and base URL."""
        self.ws_login = ws_login
        self.ws_password = ws_password
        self.baseUrl = ws_base_url
        self.sleepTime = 0.5  # Rate-limit delay between API calls (seconds)
        self.headers = {'x-addon-public-key':'kRTxA08bKieVQroS'}
        self.auth = HTTPBasicAuth(ws_login, ws_password)
        # Optional picking context for JSON logging. Set via _with_logging_picking
        # while a block of requests is executed so webship.json.history rows get
        # their picking_id filled in.
        self._current_picking = None

        # Soft warnings collected during the most recent sync_picking call.
        # statusWsToOdoo appends here for non-fatal issues (e.g. courier present
        # on the Stoqflow order but not linked in Odoo); the picking sync layer
        # surfaces them without treating the sync as failed.
        self._sync_warnings = []

        # Session with connection pooling and automatic retries on transient errors
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update(self.headers)
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,  # 1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503],
            allowed_methods=["GET", "POST", "PUT"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # Response hook: logs every HTTP exchange to webship.json.history
        # when the 'Log JSON payloads' setting is on. Covers all session.*
        # calls, not just the handful that call _log_json explicitly.
        self.session.hooks['response'] = [self._log_http_exchange]

    def set_env(self, env):
        """Inject the Odoo environment so the handler can access ORM models."""
        self.env = env

    def _verbose_enabled(self):
        """True when the 'Verbose logging' setting is on. In this mode the
        component records a full trace (every internal step via showDebugInfo
        plus every HTTP payload) to webship.json.history so it can be exported
        and shared for support."""
        if not hasattr(self, 'env'):
            return False
        return self.env['ir.config_parameter'].sudo().get_str('webship.verbose_logging') == 'True'

    def _http_logging_enabled(self):
        """HTTP request/response payloads are logged to webship.json.history
        when either 'Log JSON payloads' or the broader 'Verbose logging'
        setting is enabled (verbose is a superset)."""
        if not hasattr(self, 'env'):
            return False
        icp = self.env['ir.config_parameter'].sudo()
        return (icp.get_str('webship.log_json') == 'True'
                or icp.get_str('webship.verbose_logging') == 'True')

    def _log_json(self, picking, direction, method, endpoint, payload):
        """Log a JSON payload to webship.json.history if logging is enabled."""
        if not self._http_logging_enabled():
            return
        try:
            json_str = json.dumps(payload, indent=2, default=str)
        except Exception:
            json_str = str(payload)
        self.env['webship.json.history'].sudo().create({
            'picking_id': picking.id if picking else False,
            'direction': direction,
            'method': method,
            'endpoint': endpoint,
            'json_payload': json_str,
        })

    def _with_logging_picking(self, picking):
        """Context manager that tags every HTTP exchange logged via the
        response hook with the given picking_id until the block exits."""
        handler = self

        class _Ctx:
            def __enter__(self):
                self._previous = handler._current_picking
                handler._current_picking = picking
                return handler

            def __exit__(self, exc_type, exc, tb):
                handler._current_picking = self._previous
                return False

        return _Ctx()

    def _format_body_for_log(self, body):
        """Render a request/response body (str, bytes, or None) as a pretty
        JSON string when possible, otherwise as plain text."""
        if body is None:
            return ''
        if isinstance(body, bytes):
            try:
                body = body.decode('utf-8', errors='replace')
            except Exception:
                return str(body)
        if not isinstance(body, str):
            try:
                return json.dumps(body, indent=2, default=str)
            except Exception:
                return str(body)
        try:
            return json.dumps(json.loads(body), indent=2, default=str)
        except Exception:
            return body

    def _log_http_exchange(self, response, *args, **kwargs):
        """requests response hook: log both the sent request and the received
        response to webship.json.history when 'Log JSON payloads' is enabled.
        Runs for every call on self.session, so every POST/PUT/GET/DELETE
        against the Stoqflow API is captured automatically."""
        if not hasattr(self, 'env'):
            return
        try:
            if not self._http_logging_enabled():
                return

            req = response.request
            full_url = req.url or ''
            endpoint = full_url
            if self.baseUrl and full_url.startswith(self.baseUrl):
                endpoint = full_url[len(self.baseUrl):]

            picking_id = self._current_picking.id if self._current_picking else False

            History = self.env['webship.json.history'].sudo()
            History.create({
                'picking_id': picking_id,
                'direction': 'sent',
                'method': req.method or '',
                'endpoint': endpoint,
                'json_payload': self._format_body_for_log(req.body),
            })
            History.create({
                'picking_id': picking_id,
                'direction': 'received',
                'method': '%s %s' % (req.method or '', response.status_code),
                'endpoint': endpoint,
                'json_payload': self._format_body_for_log(response.content),
            })
        except Exception:
            # Never let logging break a real API call.
            _logger.exception("Failed to log Stoqflow HTTP exchange")

    def removeFalseVals(self, sDict):
        """Strip keys with False or None values from a dict before sending to the API."""
        filtered_data = {k: v for k, v in sDict.items() if v is not False and v is not None}

        return filtered_data

    def _truncate(self, value, max_len):
        """Truncate a string value to max_len characters if needed."""
        if value and isinstance(value, str) and len(value) > max_len:
            return value[:max_len]
        return value

    def _clean_email(self, email, context=''):
        """Return the e-mail to send to Stoqflow, dropping it when it is not a
        valid address and the 'Drop invalid e-mail' setting is enabled.

        Stoqflow rejects a client/order whose e-mail is not a valid address
        ("e-mail must be a valid e-mail address"). When the setting is on we
        omit the invalid e-mail instead so the client/order is still created."""
        if not email:
            return email
        if email_normalize(email):
            return email
        # Invalid e-mail. Only drop it when the setting explicitly allows it.
        drop = False
        if hasattr(self, 'env'):
            drop = self.env['ir.config_parameter'].sudo().get_str(
                'webship.drop_invalid_email', 'False') == 'True'
        if drop:
            _logger.info(
                "Dropping invalid e-mail %r%s (drop_invalid_email enabled)",
                email, (' for %s' % context) if context else '')
            return False
        return email

    # Known API error codes (e.g. MongoDB errors forwarded by Stoqflow)
    API_ERROR_CODES = {
        11000: 'Duplicate entry — this record already exists in Stoqflow',
    }

    def _format_api_error(self, e):
        """Format a single API error object into a readable string."""
        if not e:
            return None
        # Handle code-based errors like {"index": 0, "code": 11000}
        if 'code' in e and 'field' not in e and 'message' not in e:
            code = e['code']
            return self.API_ERROR_CODES.get(code, 'API error code %s' % code)
        # Handle field-validation errors like {"field": "name", "message": "required"}
        return f"{e.get('field', '?')}: {e.get('message', str(e))}"

    def _parse_error_response(self, response):
        """Parse an API error response, extracting field-level details from 400 errors."""
        error_text = response.text
        if response.status_code == 400:
            try:
                error_data = response.json()
                if isinstance(error_data, list):
                    parts = [
                        self._format_api_error(e)
                        for e in error_data
                        if e
                    ]
                    parts = [p for p in parts if p]
                    error_text = '; '.join(parts) if parts else 'API returned status 400 (no details provided)'
                elif isinstance(error_data, dict) and 'errors' in error_data:
                    parts = [
                        self._format_api_error(e)
                        for e in error_data['errors']
                        if e
                    ]
                    parts = [p for p in parts if p]
                    error_text = '; '.join(parts) if parts else 'API returned status 400 (no details provided)'
            except (ValueError, TypeError):
                pass
        return error_text

    def _is_stoqflow_not_found(self, result):
        """Return True when an API result describes a 404 / 'not found' reply
        (Stoqflow returns both the HTTP status and 'asset-not-found' / 'no such'
        variants). Used to detect stale resource ids stored in Odoo."""
        if not isinstance(result, dict) or result.get('status') != 'error':
            return False
        if result.get('errorCode') == 404:
            return True
        err = (result.get('errorText') or '').lower()
        return 'asset-not-found' in err or 'no such' in err

    def get_brand(self):
        """Return the Stoqflow brand_id to use when syncing a product.
        Reads 'webship.default_brand' from ir.config_parameter first (the
        value configured under Settings > Default Stoqflow brand) and falls
        back to the first webship.brand record only if no default is set."""
        if hasattr(self, 'env'):
            default_param = self.env['ir.config_parameter'].sudo().get_str('webship.default_brand')
            if default_param:
                # config_parameter on a Many2one stores the Odoo record id
                # as a string; resolve it back to a webship.brand.
                brand = self.env['webship.brand'].sudo()
                try:
                    brand = brand.browse(int(default_param)).exists()
                except (TypeError, ValueError):
                    brand = brand.browse()
                if not brand:
                    # Backwards-compat: some databases may have stored the
                    # Stoqflow brand_id string instead of the Odoo id.
                    brand = self.env['webship.brand'].sudo().search(
                        [('brand_id', '=', default_param)], limit=1,
                    )
                if brand and brand.brand_id:
                    return brand.brand_id

        brands = self.env['webship.brand'].search([], limit=1)
        if not brands:
            raise UserError("No brands present. Please load brands via Stoqflow settings.")
        return brands[0].brand_id

    def get_default_shop(self):
        """Return the Stoqflow shop_id to use when syncing an order.
        Reads 'webship.default_shop' from ir.config_parameter first (the
        value configured under Settings > Default Stoqflow shop) and falls
        back to the first webship.shop record only if no default is set."""
        if hasattr(self, 'env'):
            default_param = self.env['ir.config_parameter'].sudo().get_str('webship.default_shop')
            if default_param:
                # config_parameter on a Many2one stores the Odoo record id
                # as a string; resolve it back to a webship.shop.
                shop = self.env['webship.shop'].sudo()
                try:
                    shop = shop.browse(int(default_param)).exists()
                except (TypeError, ValueError):
                    shop = shop.browse()
                if not shop:
                    # Backwards-compat: some databases may have stored the
                    # Stoqflow shop_id string instead of the Odoo id.
                    shop = self.env['webship.shop'].sudo().search(
                        [('shop_id', '=', default_param)], limit=1,
                    )
                if shop and shop.shop_id:
                    return shop.shop_id

        shops = self.env['webship.shop'].search([], limit=1)
        if not shops:
            raise UserError("No shops present. Please load shops.")
        return shops[0].shop_id

    def get_default_status(self):
        """Return the configured default status for outbound orders."""
        wObj = self.env['ir.config_parameter'].sudo().get_str('webship.default_status_order')
        return wObj

    def get_default_po_status(self):
        """Return the configured default status for purchase orders."""
        wObj = self.env['ir.config_parameter'].sudo().get_str('webship.default_status_po_order')
        return wObj

    def get_need_stock_complete_order(self):
        """Return whether orders require full stock availability before syncing."""
        wObj = self.env['ir.config_parameter'].sudo().get_str('webship.default_order_available_condition')
        return wObj

    def get_default_auto_create_backorder(self):
        """Return whether backorders should be auto-created on partial fulfillment."""
        wObj = self.env['ir.config_parameter'].sudo().get_str('webship.auto_create_backorder')
        return wObj

    def test(self):
        """Test the API connection and return a (status, message) tuple."""
        try:
            response = self.session.get(self.baseUrl + 'products', timeout=self.REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            # A blank/whitespace or malformed URL, or an unreachable host,
            # raises here. Return a clean danger tuple instead of letting a
            # raw traceback surface in the UI.
            return ('danger', 'Fout bij verbinden: ' + str(e))

        if response.status_code != 200:
            sStatus = 'danger'
            sMessage = 'Fout bij verbinden: ' + str(response.text)
        else:
            sStatus = 'success'
            sMessage = 'Verbinding gelukt!'

        return (sStatus, sMessage)

    def sleep(self):
        """Rate-limit pause between consecutive API calls."""
        time.sleep(self.sleepTime)

    # ------------------------------------------------------------------
    # Convenience wrappers around fetchAll for specific resource types
    # ------------------------------------------------------------------

    def fetchCompanies(self):
        """Fetch all companies from Webship."""
        sResult = self.fetchAll('company')

        return sResult

    def fetchWarehouses(self):
        """Fetch all warehouses from Webship."""
        sResult = self.fetchAll('warehouses')

        return sResult

    def fetchCouriers(self):
        """Fetch all couriers from Stoqflow (GET /couriers)."""
        sResult = self.fetchAll('couriers')

        return sResult

    def fetchClients(self):
        """Fetch all clients from Webship (low detail)."""
        sResult = self.fetchAll('clients', 'low')

        return sResult

    def fetchSuppliers(self):
        """Fetch all suppliers from Webship (low detail)."""
        sResult = self.fetchAll('suppliers', 'low')

        return sResult

    def fetchProducts(self):
        """Fetch all products from Webship (low detail)."""
        sResult = self.fetchAll('products', 'low')

        return sResult

    def fetchInventory(self):
        """Fetch full inventory from Webship (low detail)."""
        sResult = self.fetchAll('inventory', 'low')

        return sResult

    def fetchCode(self, objectname, skey):
        """Retrieve the human-readable code (client_number / supplier_number) for a record."""
        if objectname == 'clients':
            response = self.fetchByKey('clients', skey)
            _logger.debug("fetchCode clients response: %s", response)
            if response['status'] == 'success':
                return response['data']['client_number']
        if objectname == 'suppliers':
            response = self.fetchByKey('suppliers', skey)
            _logger.debug("fetchCode suppliers response: %s", response)
            if response['status'] == 'success':
                return response['data']['supplier_number']
        return ['Not found']

    # ------------------------------------------------------------------
    # Low-level API request methods
    # ------------------------------------------------------------------

    def fetchByKey(self, sUrl, skey):
        """GET a single resource by its Webship ID."""
        url = self.baseUrl + sUrl + '/' + skey

        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
        self.sleep()

        _logger.debug("fetchByKey response: %s", response.text)
        _logger.debug("fetchByKey headers: %s", response.headers)

        if response.status_code != 200:
            _logger.error('fetchByKey failed with status code %s: %s', response.status_code, response.text)
            return {'status': 'error', 'txt': response.text, 'code': response.status_code}
        else:
            return {'status': 'success', 'data':response.json()}

    def fetchByKeyDetail(self, sUrl, skey):
        """GET a single resource by ID with high detail level."""
        url = self.baseUrl + sUrl + '/' + skey + '?detail=high'

        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
        self.sleep()

        _logger.debug("fetchByKeyDetail response: %s", response.text)
        _logger.debug("fetchByKeyDetail headers: %s", response.headers)

        if response.status_code != 200:
            _logger.error('fetchByKeyDetail failed with status code %s: %s', response.status_code, response.text)
            return {'status': 'error', 'txt': response.text, 'code': response.status_code}
        else:
            return {'status': 'success', 'data':response.json()}

    def get_product_by_id(self, product_id):
        """Fetch a single Stoqflow product by its id (GET /products/{id}).
        Returns the product dict (with 'name' and 'sku') or None. Used by the
        compare feature to label products that exist only in Stoqflow. Logged
        for tracing."""
        if not product_id:
            return None
        _logger.info("compare: get_product_by_id GET products/%s", product_id)
        result = self.performGet('products/' + quote(str(product_id), safe=''), '')
        if result.get('status') != 'success':
            _logger.warning("compare: get_product_by_id failed for %s: %s", product_id, result)
            return None
        data = result.get('data')
        if not isinstance(data, dict):
            _logger.warning("compare: get_product_by_id unexpected payload for %s: %s", product_id, data)
            return None
        _logger.info("compare: get_product_by_id resolved %s -> name=%s sku=%s", product_id, data.get('name'), data.get('sku'))
        return data

    def _get_order_by_id(self, order_id):
        """Fetch a single Stoqflow order (with full detail, so order_items are
        included) via GET /orders/{order_id}?detail=high. Returns the order
        dict or None. Every step is logged for tracing."""
        _logger.info("compare: _get_order_by_id GET orders/%s?detail=high", order_id)
        result = self.performGet('orders/' + quote(str(order_id), safe=''), '?detail=high')
        if result.get('status') != 'success':
            _logger.warning("compare: _get_order_by_id failed for %s: %s", order_id, result)
            return None
        order = result.get('data')
        if not isinstance(order, dict):
            _logger.warning("compare: _get_order_by_id unexpected payload for %s: %s", order_id, order)
            return None
        _logger.info(
            "compare: _get_order_by_id got order _id=%s status=%s order_items=%s picks=%s",
            order.get('_id'), order.get('status'),
            len(order.get('order_items') or []), len(order.get('picks') or []),
        )
        return order

    def _find_order_by_query(self, param, value, origin_field):
        """Query GET /orders?<param>=<value> and return the single matching
        order (fetched in full detail by id), or None.

        ``origin_field`` is the key inside the order's ``origin`` object that
        the value is validated against ('number' or 'id'). This guards against
        the API silently ignoring an unsupported filter and returning every
        order, which would otherwise match the wrong one."""
        _logger.info("compare: _find_order_by_query GET orders?%s=%s", param, value)
        result = self.performGet('orders', '?%s=%s' % (param, quote(str(value), safe='')))
        if result.get('status') != 'success':
            _logger.warning("compare: _find_order_by_query query failed for %s=%s: %s", param, value, result)
            return None

        orders = result.get('data') or []
        if not isinstance(orders, list):
            _logger.warning("compare: _find_order_by_query unexpected list payload for %s=%s: %s", param, value, orders)
            return None
        _logger.info("compare: _find_order_by_query %s order(s) returned for %s=%s", len(orders), param, value)

        # Validate the API actually filtered on the requested origin field.
        matching = [
            o for o in orders
            if str((o.get('origin') or {}).get(origin_field, '')) == str(value)
        ]
        if not matching:
            _logger.warning(
                "compare: _find_order_by_query no order had origin.%s == %s (API may have ignored the filter; %s returned)",
                origin_field, value, len(orders),
            )
            return None
        if len(matching) > 1:
            _logger.warning(
                "compare: _find_order_by_query multiple orders (%s) matched origin.%s == %s; using the first",
                len(matching), origin_field, value,
            )

        first = matching[0]
        order_id = first.get('_id')
        _logger.info("compare: _find_order_by_query matched order _id=%s via %s", order_id, param)
        full = self._get_order_by_id(order_id) if order_id else None
        return full or first

    def find_stoqflow_order_for_picking(self, picking):
        """Look up the Stoqflow order that corresponds to an Odoo picking.

        Lookup strategy, most reliable first, each step traced in the logs:
          1. The Stoqflow order id stored on the picking (df_picking_id_webship).
          2. The origin number (picking.origin) via GET /orders?origin_number=...
             (this is the order's REFERENCE on the platform of origin, e.g.
             the Shopify order number).
          3. The origin id (str(picking.id)) via GET /orders?origin_id=...

        Returns the full Stoqflow order dict (including order_items) or None."""
        _logger.info(
            "compare: find_stoqflow_order_for_picking START picking=%s id=%s origin=%s df_picking_id_webship=%s",
            picking.name, picking.id, picking.origin, picking.df_picking_id_webship,
        )

        if picking.df_picking_id_webship:
            _logger.info("compare: lookup step 1 - by stored Stoqflow id %s", picking.df_picking_id_webship)
            order = self._get_order_by_id(picking.df_picking_id_webship)
            if order:
                _logger.info("compare: FOUND order via stored id for picking %s", picking.name)
                return order
            _logger.warning("compare: stored id %s did not resolve, falling back", picking.df_picking_id_webship)

        if picking.origin:
            _logger.info("compare: lookup step 2 - by origin_number=%s", picking.origin)
            order = self._find_order_by_query('origin_number', picking.origin, 'number')
            if order:
                _logger.info("compare: FOUND order via origin_number for picking %s", picking.name)
                return order

        origin_id = str(picking.id)
        _logger.info("compare: lookup step 3 - by origin_id=%s", origin_id)
        order = self._find_order_by_query('origin_id', origin_id, 'id')
        if order:
            _logger.info("compare: FOUND order via origin_id for picking %s", picking.name)
            return order

        _logger.warning("compare: NO Stoqflow order found for picking %s", picking.name)
        return None

    def find_stoqflow_backorders(self, endpoint, parent_id):
        """Fetch the Stoqflow child orders of a parent order via
        GET /{endpoint}?parent_order_id=<parent_id>. ``endpoint`` is 'orders'
        or 'purchase-orders'. Returns a list of order dicts (with order_items)
        or an empty list."""
        if not parent_id:
            return []
        _logger.info("link_backorder: GET %s?parent_order_id=%s", endpoint, parent_id)
        result = self.performGet(endpoint, '?parent_order_id=' + quote(str(parent_id), safe=''))
        if result.get('status') != 'success':
            _logger.warning(
                "link_backorder: parent_order_id query failed for %s=%s: %s",
                endpoint, parent_id, result)
            return []
        data = result.get('data')
        if not isinstance(data, list):
            _logger.warning(
                "link_backorder: unexpected payload for %s parent_order_id=%s: %s",
                endpoint, parent_id, data)
            return []

        # parent_order_id is a documented server-side filter, so this normally
        # returns only the parent's children. Re-check it client-side anyway as
        # defense in depth: an unknown/malformed param would be ignored by
        # Stoqflow and bring back the whole collection (as the old 'origin.id'
        # typo did), which would make the caller content-match the backorder
        # against every order in the shop.
        children = [o for o in data if str(o.get('parent_order_id') or '') == str(parent_id)]
        if len(children) != len(data):
            _logger.warning(
                "link_backorder: server returned %s order(s) but only %s carry "
                "parent_order_id=%s; filtered client-side", len(data), len(children), parent_id)
        _logger.info("link_backorder: %s child order(s) for parent %s", len(children), parent_id)
        return children

    def fetchAll(self, sUrl, sDetail=None, sEditedAfter=None, sCreatedAfter=None):
        """
        Fetch all paginated data from the Webship API.
        Returns a dict of pages to remain compatible with existing code
        that uses orders['data'].values().
        """

        base_url = f"{self.baseUrl}{sUrl}"

        # Build query parameters
        params = {}
        if sDetail:
            params['detail'] = sDetail
        if sEditedAfter:
            params['edited_after'] = sEditedAfter
        if sCreatedAfter:
            params['created_after'] = sCreatedAfter

        # Construct URL for first request
        if params:
            separator = '&' if '?' in base_url else '?'
            url = f"{base_url}{separator}{urlencode(params)}"
        else:
            url = base_url
        _logger.debug("fetchAll URL: %s", url)

        # First page request
        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
        self.sleep()

        if response.status_code != 200:
            _logger.error('fetchAll failed with status code %s: %s', response.status_code, response.text)
            return {
                'status': 'error',
                'txt': response.text,
                'code': response.status_code
            }

        # Get total count if provided by API
        totalCount = int(response.headers.get('total-count', 0)) or None

        # Initialize container for paginated results
        allData = {}
        pageNumber = 1
        allData[pageNumber] = response.json()

        # If there are multiple pages, fetch the rest
        if totalCount and totalCount > 50:
            base_page_url = url  # Keep unmodified base URL
            while True:
                pageNumber += 1
                paged_url = f"{base_page_url}&page={pageNumber}"

                response = self.session.get(paged_url, timeout=self.REQUEST_TIMEOUT)
                self.sleep()

                if response.status_code != 200:
                    _logger.error('fetchAll page %s failed with status code %s: %s', pageNumber, response.status_code, response.text)
                    return {
                        'status': 'error',
                        'txt': response.text,
                        'code': response.status_code
                    }

                allData[pageNumber] = response.json()

                # Stop when we've reached the total count
                if totalCount <= pageNumber * 50:
                    break

        return {
            'status': 'success',
            'data': allData,
            'totalCount': totalCount
        }

    # ------------------------------------------------------------------
    # Lookup methods: find records by VAT or SKU
    # ------------------------------------------------------------------

    def findClientByVat(self, vatNr):
        """Search for a client in Webship by VAT number. Returns {'id': ...} or error."""
        if vatNr == False:
            return {'error': 'no vat number given'}

        self.sleep()

        url = self.baseUrl + 'clients?vat=' + quote(str(vatNr), safe='')

        _logger.debug("findClientByVat URL: %s", url)

        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        totalCount = response.headers.get('total-count')

        if totalCount == None:
            return []

        if int(totalCount) == 1:
            rJson = response.json()
            _logger.debug("findClientByVat result: %s", rJson)
            return {'id': rJson[0]['_id']}

        if int(totalCount) > 1:
            return {'error': str(totalCount) + ' occurences found.'}

        return []

    def findSupplierByVat(self, vatNr):
        """Search for a supplier in Webship by VAT number."""
        if vatNr == False:
            return {'error': 'no vat number given'}

        self.sleep()

        url = self.baseUrl + 'suppliers?vat=' + quote(str(vatNr), safe='')

        _logger.debug("findSupplierByVat URL: %s", url)

        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        totalCount = response.headers.get('total-count')

        if int(totalCount) == 1:
            rJson = response.json()
            _logger.debug("findSupplierByVat result: %s", rJson)
            return {'id': rJson[0]['_id']}

        if int(totalCount) > 1:
            return {'error': str(totalCount) + ' occurences found.'}

        return []

    def findProductBySku(self, skuNr):
        """Search for a single product in Webship by SKU."""
        if skuNr == False:
            return {'error': 'no sku given'}

        self.sleep()

        url = self.baseUrl + 'products?sku=' + quote(str(skuNr), safe='')

        _logger.debug("findProductBySku URL: %s", url)

        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        totalCount = response.headers.get('total-count')

        if totalCount == None:
            return []

        if int(totalCount) == 1:
            rJson = response.json()
            _logger.debug("findProductBySku result: %s", rJson)
            return {'id': rJson[0]['_id']}

        if int(totalCount) > 1:
            return {'error': str(totalCount) + ' occurences found.'}

        return []
       
    def findProductsBySku(self, picking):
        """Batch-lookup all SKUs from a picking's move lines in Webship.
        Returns {'items': {sku: webship_id}} or an error dict."""
        skus = []
        for p in picking.move_ids:
            if p.product_id.df_product_do_not_send_webship == True or p.product_id.default_code == False:
                continue
            if p.product_id.code != False:
                skus.append(p.product_id.code)

        _logger.info('Searching SKUS: %s', skus)

        if skus == []:
            return {'error': 'No codes given'}

        sQuery = None
        for s in skus:
            encoded_sku = quote(str(s), safe='')
            if sQuery == None:
                sQuery = 'sku=' + encoded_sku
            else:
                sQuery = sQuery + ',' + encoded_sku

        _logger.info('Query for skus: %s', sQuery)

        allRecords = self.fetchAll('products?' + sQuery, 'low', None)
        _logger.debug("findProductsBySku allRecords: %s", allRecords)
        items = {}

        totalCount = allRecords['totalCount']
        if totalCount == None or int(totalCount) == 0:
            return {'error': 'Nothing is found.'}

        for page in allRecords['data'].values():
            _logger.debug("findProductsBySku page: %s", page)
            for it in page:
                items[it['sku']] = it['_id']

        return {'items': items}

    # ------------------------------------------------------------------
    # Partner / supplier sync methods
    # ------------------------------------------------------------------

    def match_partner(self, partner):
        """Match an Odoo partner to a Webship client by email address.
        Requires exactly one match to succeed, returns error if zero or multiple found."""
        if partner.email == False:
            return ['No e-mail address specified']

        sReq = self.performGet('clients', "?email=" + quote(str(partner.email), safe=''))

        if sReq['status'] == 'success':
            _logger.debug("match_partner result: %s", sReq)

            # Check if exactly one client was found
            if len(sReq['data']) == 0:
                return ['No client found with this email in Stoqflow']
            elif len(sReq['data']) == 1:
                partner.df_client_id_webship = sReq['data'][0]['_id']
                return []
            else:
                return ['Multiple clients found with this email (' + str(len(sReq['data'])) + '). Cannot auto-link.']

        return ['Error searching for client: ' + sReq.get('errorText', 'Unknown error') + ' (url: ' + sReq.get('url', '?') + ')']

    def _match_client_by_vat(self, partner):
        """Try to match a partner to a Stoqflow client by VAT number.
        Returns (matched: bool, errors: list, data: list or None).
        When multiple matches are found, data contains the Stoqflow client dicts."""
        if not partner.vat:
            return False, ['No VAT number specified on the contact'], None

        sReq = self.performGet('clients', "?vat=" + quote(str(partner.vat), safe=''))

        if sReq['status'] == 'success':
            if len(sReq['data']) == 1:
                partner.df_client_id_webship = sReq['data'][0]['_id']
                _logger.info("match_client_by_vat: matched partner %s (VAT %s) to Stoqflow client %s",
                             partner.name, partner.vat, sReq['data'][0]['_id'])
                return True, [], None
            elif len(sReq['data']) > 1:
                _logger.info("match_client_by_vat: %d clients found for VAT %s", len(sReq['data']), partner.vat)
                return False, ['Multiple clients found with VAT %s (%d). Please select the correct one.' % (partner.vat, len(sReq['data']))], sReq['data']
            else:
                return False, [], None
        return False, ['Error searching for client by VAT: ' + sReq.get('errorText', 'Unknown error') + ' (url: ' + sReq.get('url', '?') + ')'], None

    def _match_client_by_email(self, partner):
        """Try to match a partner to a Stoqflow client by e-mail address.
        Returns (matched: bool, errors: list, data: list or None).
        When multiple matches are found, data contains the Stoqflow client dicts."""
        if not partner.email:
            return False, ['No e-mail address specified on the contact'], None

        sReq = self.performGet('clients', "?email=" + quote(str(partner.email), safe=''))

        if sReq['status'] == 'success':
            if len(sReq['data']) == 1:
                partner.df_client_id_webship = sReq['data'][0]['_id']
                _logger.info("match_client_by_email: matched partner %s (email %s) to Stoqflow client %s",
                             partner.name, partner.email, sReq['data'][0]['_id'])
                return True, [], None
            elif len(sReq['data']) > 1:
                _logger.info("match_client_by_email: %d clients found for email %s", len(sReq['data']), partner.email)
                return False, ['Multiple clients found with e-mail %s (%d). Please select the correct one.' % (partner.email, len(sReq['data']))], sReq['data']
            else:
                return False, [], None
        return False, ['Error searching for client by e-mail: ' + sReq.get('errorText', 'Unknown error') + ' (url: ' + sReq.get('url', '?') + ')'], None

    def match_partner_by_sequence(self, partner):
        """Match a partner to a Stoqflow client using the configured matching sequence.
        The sequence is read from ir.config_parameter 'webship.contact_match_sequence'.
        Returns a dict with keys:
          - 'errors': list of error strings (empty on success)
          - 'multiple': list of Stoqflow client dicts if multiple were found, else None
          - 'match_field': which field had the multiple matches ('VAT' or 'e-mail')"""
        result = {'errors': [], 'multiple': None, 'match_field': ''}

        if not hasattr(self, 'env'):
            errors = self.match_partner(partner)
            result['errors'] = errors
            return result

        sequence = self.env['ir.config_parameter'].sudo().get_str(
            'webship.contact_match_sequence', '')

        # Blank sequence = skip matching so a new client is created when the
        # partner has no df_client_id_webship yet.
        if not sequence:
            _logger.info("match_partner_by_sequence: sequence blank - skipping match for %s", partner.name)
            return result

        if sequence == 'vat_then_email':
            matched, errors, data = self._match_client_by_vat(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'VAT'
                return result
            # Fall back to e-mail
            matched, errors, data = self._match_client_by_email(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'e-mail'
                return result
            result['errors'] = errors if errors else ['No client found in Stoqflow by VAT or e-mail']

        elif sequence == 'vat_only':
            matched, errors, data = self._match_client_by_vat(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'VAT'
                return result
            result['errors'] = errors if errors else ['No client found in Stoqflow by VAT']

        elif sequence == 'email_then_vat':
            matched, errors, data = self._match_client_by_email(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'e-mail'
                return result
            # Fall back to VAT
            matched, errors, data = self._match_client_by_vat(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'VAT'
                return result
            result['errors'] = errors if errors else ['No client found in Stoqflow by e-mail or VAT']

        else:
            # Default: email_only
            matched, errors, data = self._match_client_by_email(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'e-mail'
                return result
            result['errors'] = errors if errors else ['No client found in Stoqflow by e-mail']

        return result

    def match_supplier(self, partner):
        """Match an Odoo partner to a Webship supplier by email address.
        Requires exactly one match to succeed, returns error if zero or multiple found."""
        if partner.email == False:
            return ['No e-mail address specified']

        sReq = self.performGet('suppliers', "?email=" + quote(str(partner.email), safe=''))

        if sReq['status'] == 'success':
            _logger.debug("match_supplier result: %s", sReq)

            # Check if exactly one supplier was found
            if len(sReq['data']) == 0:
                return ['No supplier found with this email in Stoqflow']
            elif len(sReq['data']) == 1:
                partner.df_supplier_id_webship = sReq['data'][0]['_id']
                return []
            else:
                return ['Multiple suppliers found with this email (' + str(len(sReq['data'])) + '). Cannot auto-link.']

        return ['Error searching for supplier: ' + sReq.get('errorText', 'Unknown error')]

    def _match_supplier_by_vat(self, partner):
        """Try to match a partner to a Stoqflow supplier by VAT number.
        Returns (matched: bool, errors: list, data: list or None)."""
        if not partner.vat:
            return False, ['No VAT number specified on the contact'], None

        sReq = self.performGet('suppliers', "?vat=" + quote(str(partner.vat), safe=''))

        if sReq['status'] == 'success':
            if len(sReq['data']) == 1:
                partner.df_supplier_id_webship = sReq['data'][0]['_id']
                _logger.info("match_supplier_by_vat: matched partner %s (VAT %s) to Stoqflow supplier %s",
                             partner.name, partner.vat, sReq['data'][0]['_id'])
                return True, [], None
            elif len(sReq['data']) > 1:
                _logger.info("match_supplier_by_vat: %d suppliers found for VAT %s", len(sReq['data']), partner.vat)
                return False, ['Multiple suppliers found with VAT %s (%d). Please select the correct one.' % (partner.vat, len(sReq['data']))], sReq['data']
            else:
                return False, [], None
        return False, ['Error searching for supplier by VAT: ' + sReq.get('errorText', 'Unknown error') + ' (url: ' + sReq.get('url', '?') + ')'], None

    def _match_supplier_by_email(self, partner):
        """Try to match a partner to a Stoqflow supplier by e-mail address.
        Returns (matched: bool, errors: list, data: list or None)."""
        if not partner.email:
            return False, ['No e-mail address specified on the contact'], None

        sReq = self.performGet('suppliers', "?email=" + quote(str(partner.email), safe=''))

        if sReq['status'] == 'success':
            if len(sReq['data']) == 1:
                partner.df_supplier_id_webship = sReq['data'][0]['_id']
                _logger.info("match_supplier_by_email: matched partner %s (email %s) to Stoqflow supplier %s",
                             partner.name, partner.email, sReq['data'][0]['_id'])
                return True, [], None
            elif len(sReq['data']) > 1:
                _logger.info("match_supplier_by_email: %d suppliers found for email %s", len(sReq['data']), partner.email)
                return False, ['Multiple suppliers found with e-mail %s (%d). Please select the correct one.' % (partner.email, len(sReq['data']))], sReq['data']
            else:
                return False, [], None
        return False, ['Error searching for supplier by e-mail: ' + sReq.get('errorText', 'Unknown error') + ' (url: ' + sReq.get('url', '?') + ')'], None

    def match_supplier_by_sequence(self, partner):
        """Match a partner to a Stoqflow supplier using the configured matching sequence.
        The sequence is read from ir.config_parameter 'webship.supplier_match_sequence'.
        Returns a dict with keys:
          - 'errors': list of error strings (empty on success)
          - 'multiple': list of Stoqflow supplier dicts if multiple were found, else None
          - 'match_field': which field had the multiple matches ('VAT' or 'e-mail')"""
        result = {'errors': [], 'multiple': None, 'match_field': ''}

        if not hasattr(self, 'env'):
            errors = self.match_supplier(partner)
            result['errors'] = errors
            return result

        sequence = self.env['ir.config_parameter'].sudo().get_str(
            'webship.supplier_match_sequence', '')

        # Blank sequence = skip matching so a new supplier is created when the
        # partner has no df_supplier_id_webship yet.
        if not sequence:
            _logger.info("match_supplier_by_sequence: sequence blank - skipping match for %s", partner.name)
            return result

        if sequence == 'vat_then_email':
            matched, errors, data = self._match_supplier_by_vat(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'VAT'
                return result
            matched, errors, data = self._match_supplier_by_email(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'e-mail'
                return result
            result['errors'] = errors if errors else ['No supplier found in Stoqflow by VAT or e-mail']

        elif sequence == 'vat_only':
            matched, errors, data = self._match_supplier_by_vat(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'VAT'
                return result
            result['errors'] = errors if errors else ['No supplier found in Stoqflow by VAT']

        elif sequence == 'email_then_vat':
            matched, errors, data = self._match_supplier_by_email(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'e-mail'
                return result
            matched, errors, data = self._match_supplier_by_vat(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'VAT'
                return result
            result['errors'] = errors if errors else ['No supplier found in Stoqflow by e-mail or VAT']

        else:
            # Default: email_only
            matched, errors, data = self._match_supplier_by_email(partner)
            if matched:
                return result
            if data:
                result['errors'] = errors
                result['multiple'] = data
                result['match_field'] = 'e-mail'
                return result
            result['errors'] = errors if errors else ['No supplier found in Stoqflow by e-mail']

        return result

        return ['Error searching for supplier: ' + sReq.get('errorText', 'Unknown error')]

    def sync_supplier(self, partner):
        """Create or update a supplier in Webship from an Odoo partner.
        Validates required address fields before sending.
        If creating new, checks that the email isn't already in use."""
        errors = []

        if partner.name == False:
            errors.append('Partner has no name')

        if partner.street == False:
            errors.append('Street is missing in billing address')

        if partner.city == False:
            errors.append('City is missing in billing address')

        if partner.zip == False:
            errors.append('Zip is missing in billing address')

        if partner.country_id.id == False:
            errors.append('Country is missing in billing address')

        if not partner.email and hasattr(self, 'env'):
            allow_no_email = self.env['ir.config_parameter'].sudo().get_str(
                'webship.allow_no_email_contact', 'False')
            if allow_no_email != 'True':
                errors.append("Contact has no e-mail address. Enable 'Allow to transfer contacts with no e-mail address' in the settings to bypass this.")

        if errors != []:
            return errors

        sSupplierNumber = f"SO{partner.id:07d}"

        sObject = {'name':partner.name, 'supplier_number':sSupplierNumber, 'email':self._clean_email(partner.email, context=partner.name), 'phone':partner.phone, 'vat':partner.vat,
                   'address':
                       {'address_1': partner.street, 'city': partner.city, 'postal_code': partner.zip, 'country': partner.country_code}
                   }

        for key, value in list(sObject.items()):
            if value is False or value == '\'false\'' or value == '':
                del sObject[key]

        if partner.df_supplier_id_webship == False:
            # Before creating, check if this email already exists in Webship.
            # Skip this pre-check when the supplier match sequence is left
            # blank: the user explicitly opted out of matching and just wants
            # a new supplier created.
            match_sequence = ''
            if hasattr(self, 'env'):
                match_sequence = self.env['ir.config_parameter'].sudo().get_str(
                    'webship.supplier_match_sequence', '') or ''
            if match_sequence and partner.email and partner.email != '':
                existing = self.performGet('suppliers', "?email=" + quote(str(partner.email), safe=''))
                if existing['status'] == 'success' and len(existing.get('data', [])) > 0:
                    return ['Email already exists in Stoqflow. Use the "Match" button to link this supplier.']

            del sObject['supplier_number']
            sRes = self.performPost('suppliers', sObject)
            if sRes['status'] == 'success':
                partner.df_supplier_id_webship = sRes['data']['_id']
        else:
            sRes = self.performPut('suppliers', sObject, partner.df_supplier_id_webship)

        if sRes['status'] == 'error':
            return ['Error while creating supplier: ' + sRes['errorText'] + ' (url: ' + sRes.get('url', '?') + ')']

        return []

    # ------------------------------------------------------------------
    # Generic HTTP helpers (POST / PUT / GET)
    # ------------------------------------------------------------------

    def performPost(self, url, sObject):
        """POST a JSON payload to the Webship API. Returns status + data or error."""
        url = self.baseUrl + url
        self.showDebugInfo('Url called: ' + url)

        cleanedObject = self.removeFalseVals(sObject)
        self.showDebugInfo('About to post: ' + str(cleanedObject))

        self.sleep()
        response = self.session.post(url, json=cleanedObject, timeout=self.REQUEST_TIMEOUT)

        self.showDebugInfo('Response: ' + response.text)

        if response.status_code != 200:
            return {'status': 'error', 'errorCode':response.status_code, 'errorText':self._parse_error_response(response), 'url': url}
        else:
            responseData = response.json()
            # Detect API-level errors returned with HTTP 200,
            # e.g. [{"index": 0, "code": 11000}] (duplicate key)
            if isinstance(responseData, list) and responseData and isinstance(responseData[0], dict) and 'code' in responseData[0]:
                parts = [self._format_api_error(e) for e in responseData if e]
                parts = [p for p in parts if p]
                error_text = '; '.join(parts) if parts else 'Unknown API error'
                return {'status': 'error', 'errorCode': responseData[0].get('code'), 'errorText': error_text, 'url': url}
            return {'status':'success', 'data':responseData}

    def performPut(self, url, sObject, sId):
        """PUT (update) a JSON payload for a specific resource by ID."""
        url = self.baseUrl + url + '/' + sId
        self.showDebugInfo('Url called: ' + url)

        cleanedObject = self.removeFalseVals(sObject)
        self.showDebugInfo('About to put: ' + str(cleanedObject))

        self.sleep()
        response = self.session.put(url, json=cleanedObject, timeout=self.REQUEST_TIMEOUT)

        self.showDebugInfo('Response: ' + response.text)

        if response.status_code != 200:
            return {'status': 'error', 'errorCode':response.status_code, 'errorText':self._parse_error_response(response), 'url': url}
        else:
            responseData = response.json()
            return {'status':'success', 'data':responseData}

    def performGet(self, url, sParams):
        """GET a resource with query parameters appended."""
        url = self.baseUrl + url + sParams

        self.sleep()
        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        self.showDebugInfo('Url called: ' + url)
        self.showDebugInfo('Response got: ' + response.text)
        self.showDebugInfo('Response code got: ' + str(response.status_code))


        if response.status_code != 200:
            return {'status': 'error', 'errorCode':response.status_code, 'errorText':self._parse_error_response(response), 'url': url}
        else:
            responseData = response.json()
            return {'status':'success', 'data':responseData}

    def performDelete(self, url, sId):
        """DELETE a single resource by id, e.g. performDelete('clients', _id).
        Targeted delete (never more than the one record identified by sId) -
        used to clean up records created during live integration tests. Goes
        through self.session so it shares the auth, retry and JSON-logging hook.
        Unlike the emptyX() helpers, this never deletes more than one record."""
        url = self.baseUrl + url + '/' + sId
        self.showDebugInfo('Url called (DELETE): ' + url)

        self.sleep()
        response = self.session.delete(url, timeout=self.REQUEST_TIMEOUT)

        self.showDebugInfo('Response: ' + response.text)

        # Stoqflow returns 200 on delete; treat 204 (No Content) and 404
        # (already gone) as success too so cleanup is idempotent.
        if response.status_code in (200, 204, 404):
            return {'status': 'success', 'errorCode': response.status_code}
        return {'status': 'error', 'errorCode': response.status_code,
                'errorText': self._parse_error_response(response), 'url': url}

    @staticmethod
    def _client_payload_hash(payload, client_id):
        """Deterministic sha256 fingerprint of a client payload plus the
        Stoqflow client id it targets. Used by sync_partner to detect
        whether a PUT clients/{id} would send anything new."""
        canonical = json.dumps(payload, sort_keys=True, default=str,
                               separators=(',', ':'))
        return hashlib.sha256(
            (canonical + '|' + (client_id or '')).encode('utf-8')
        ).hexdigest()

    def sync_partner(self, partner, fallback_partner=None, force=False, delivery_partner=None):
        """Create or update a client in Webship from an Odoo partner.
        Uses billing address and, if present, a child delivery address.
        If creating new, checks that the email isn't already in use.

        When ``fallback_partner`` is provided and the
        ``webship.fallback_sale_order_contact`` setting is enabled, missing
        email/phone on ``partner`` are taken from ``fallback_partner`` (the
        sale order's main contact) for both validation and the payload sent
        to Stoqflow.

        When updating an existing client, the PUT is skipped if the payload
        is identical to the last successfully pushed one (tracked via a
        sha256 hash on the partner) - this keeps recurring order syncs from
        re-pushing unchanged clients. Pass ``force=True`` to bypass the
        hash check and always push (used by the manual sync button)."""
        errors = []

        if partner.name == False:
            errors.append('Partner has no name')

        if partner.street == False:
            errors.append('Street is missing in billing address')

        if partner.city == False:
            errors.append('City is missing in billing address')

        if partner.zip == False:
            errors.append('Zip is missing in billing address')

        if partner.country_id.id == False:
            errors.append('Country is missing in billing address')

        effective_email = partner.email
        effective_phone = partner.phone
        if hasattr(self, 'env'):
            fallback_enabled = self.env['ir.config_parameter'].sudo().get_str(
                'webship.fallback_sale_order_contact') == 'True'
            if fallback_enabled:
                # Try the sale order's main contact first, then walk up to
                # the commercial entity (parent company / topmost contact)
                # of the picking partner. This covers both common setups:
                # the SO customer is the company, or the SO customer is
                # the delivery child contact whose parent holds the email.
                candidates = []
                if fallback_partner:
                    candidates.append(fallback_partner)
                commercial = partner.commercial_partner_id
                if commercial and commercial.id != partner.id:
                    candidates.append(commercial)
                for c in candidates:
                    if not effective_email and c.email:
                        effective_email = c.email
                    if not effective_phone and c.phone:
                        effective_phone = c.phone

        # The email was inherited from a fallback contact (the partner
        # itself has no email). Used below to skip the duplicate-email
        # pre-check: the fallback contact's own Stoqflow client is
        # expected to already use that address.
        email_from_fallback = bool(effective_email) and not partner.email

        if not effective_email and hasattr(self, 'env'):
            allow_no_email = self.env['ir.config_parameter'].sudo().get_str(
                'webship.allow_no_email_contact', 'False')
            if allow_no_email != 'True':
                errors.append("Contact has no e-mail address. Enable 'Allow to transfer contacts with no e-mail address' in the settings to bypass this.")

        # The delivery (shipping) address is the one defined on the picking,
        # passed in as ``delivery_partner``. A previous version searched for
        # delivery-type child contacts of the partner, which raised "Expected
        # singleton" when a contact had several delivery addresses. When no
        # picking delivery address is given (manual partner sync) fall back to
        # a single delivery child (limit=1 so it can never be a multi-record set).
        if delivery_partner is not None:
            deliveryAdress = delivery_partner
        else:
            deliveryAdress = partner.env['res.partner'].sudo().search(
                [('type', '=', 'delivery'), ('parent_id', '=', partner.id)], limit=1)

        # Only send a separate shipping block when the delivery address is a
        # different contact than the billing partner; otherwise it just
        # duplicates the billing address.
        has_delivery = bool(deliveryAdress) and deliveryAdress != partner

        self._debug_dump(deliveryAdress, self.PARTNER_DEBUG_FIELDS,
                         'Delivery address')

        if has_delivery:
            sCountryCode = deliveryAdress.country_id.code
            if sCountryCode == False:
                sCountryCode = 'BE'
            shippingAdress = {'address_1': deliveryAdress.street, 'city': deliveryAdress.city, 'postal_code': deliveryAdress.zip, 'country': sCountryCode}

            if deliveryAdress.street == False:
                errors.append('Street is missing in delivery address')

            if deliveryAdress.city == False:
                errors.append('City is missing in delivery address')

            if deliveryAdress.zip == False:
                errors.append('Zip is missing in delivery address')

            if deliveryAdress.country_id.id == False:
                errors.append('Country is missing in delivery address')

        if errors == []:

            contactName = None
            generalName = None
            if partner.commercial_company_name != False and partner.commercial_company_name != '':
                generalName = partner.commercial_company_name
                contactName = partner.name
            else:
                generalName = partner.name
                contactName = partner.name

            sCountryCode = partner.country_id.code
            if sCountryCode == False:
                sCountryCode = 'BE'
            # Drop an invalid e-mail (when the setting allows) so Stoqflow does
            # not reject the client on "e-mail must be a valid e-mail address".
            effective_email = self._clean_email(effective_email, context=partner.name)
            sJson = {'name':generalName, 'contact':contactName, 'email':effective_email, 'phone':effective_phone, 'mobile':getattr(partner, 'mobile', None), 'vat':partner.vat, 'addresses': {'billing':{'address_1':partner.street, 'city':partner.city, 'postal_code':partner.zip, 'country':sCountryCode}}}

            if has_delivery:
                sJson['addresses']['shipping'] = shippingAdress

            for key, value in list(sJson.items()):
                if value is False or value == '\'false\'' or value == '':
                    del sJson[key]

            if partner.df_client_id_webship == False:
                # Before creating, check if this email already exists in Webship.
                # Skip this pre-check when the contact match sequence is left
                # blank: the user explicitly opted out of matching and just
                # wants a new client created. Also skip when the email was
                # inherited via fallback - the fallback contact's own
                # Stoqflow client is expected to already use that email,
                # and we still want a separate Stoqflow client created
                # here for the picking partner's address.
                match_sequence = ''
                if hasattr(self, 'env'):
                    match_sequence = self.env['ir.config_parameter'].sudo().get_str(
                        'webship.contact_match_sequence', '') or ''
                if match_sequence and effective_email and effective_email != '' and not email_from_fallback:
                    existing = self.performGet('clients', "?email=" + quote(str(effective_email), safe=''))
                    if existing['status'] == 'success' and len(existing.get('data', [])) > 0:
                        return ['Email already exists in Stoqflow. Use the "Match" button to link this client.']

                result = self.performPost('clients', sJson)
                if result['status'] == 'success':
                    partner.df_client_id_webship = result['data']['_id']
            else:
                payload_hash = self._client_payload_hash(
                    sJson, partner.df_client_id_webship)
                if not force and partner.df_webship_payload_hash == payload_hash:
                    self.showDebugInfo(
                        'Client payload unchanged for partner %s (client %s) '
                        '- skipping PUT' % (partner.id, partner.df_client_id_webship))
                    return []
                result = self.performPut('clients', sJson, partner.df_client_id_webship)

            if result['status'] == 'success':
                # Baseline for the next change-detection pass. Recomputed here
                # (not reused from above) so the POST branch hashes with the
                # freshly assigned client id.
                partner.df_webship_payload_hash = self._client_payload_hash(
                    sJson, partner.df_client_id_webship)
                partner.df_last_webship_sync = fields.Datetime.now()
                return []
            else:
                return ['Error: ' + result['errorText'] + ' (url: ' + result.get('url', '?') + ')']
        else:
            return errors

    # ------------------------------------------------------------------
    # Picking / order building and sync
    # ------------------------------------------------------------------

    def is_integer_float(self, value):
        """Check whether a float value is effectively a whole number."""
        return value % 1 == 0

    def picking_get_line_items(self, picking):
        """Extract line items from a picking."""
        output = []
        self._skipped_products = []
        _logger.debug("picking_get_line_items picking: %s", picking)
        for i in picking.move_ids:
            _logger.debug("Processing move product: %s", i.product_id.default_code)
            if i.product_id.df_product_do_not_send_webship == True:
                continue
            if not i.product_id.default_code:
                self._skipped_products.append(i.product_id.name)
                _logger.warning("Product '%s' (id=%s) has no default_code (SKU)", i.product_id.name, i.product_id.id)
            sOutput = {'productObj': i.product_id, 'type':i.product_id.type, 'default_code':i.product_id.default_code, 'product_id':i.product_id.id, 'quantity':i.product_uom_qty}

            sOutput['divides'] = []

            output.append(sOutput)

        return output

    def add_seconds_to_odoo_datetime(self, dt_string, seconds=1):
        """
        Add seconds to an Odoo datetime string.

        :param dt_string: str in format 'YYYY-MM-DD HH:MM:SS'
        :param seconds: int, number of seconds to add (default 1)
        :return: str in format 'YYYY-MM-DD HH:MM:SS'
        """
        if not dt_string:
            return False

        dt = fields.Datetime.from_string(dt_string)
        dt = dt + timedelta(seconds=seconds)

        return fields.Datetime.to_string(dt)

    def sync_statusses_since_last(self, lastDate):
        """Poll Webship for orders edited/created since lastDate and update Odoo pickings accordingly."""
        maxEdited = None

        if lastDate:
            orders = self.fetchAll('orders', 'high', self.add_seconds_to_odoo_datetime(lastDate),None)
        else:
            orders = self.fetchAll('orders', 'high', lastDate, None)

        allChangeDates = []

        allPickingsWS = set()

        _logger.debug("sync_statusses_since_last orders: %s", orders)

        if orders['status'] == 'success' and orders['totalCount'] == None:
            orders = self.fetchAll('orders', 'high', None, lastDate)

        if orders['status'] == 'success' and orders['totalCount'] == None:
            date_object = datetime.now()
            return date_object.strftime("%Y-%m-%d %H:%M:%S")

        if orders['status'] == 'success':
            for page in orders['data'].values():
                for order in page:
                    allPickingsWS.add(order['_id'])
                    pickingId = self.env['stock.picking'].search([('df_picking_id_webship', '=', order['_id'])])
                    _logger.debug('Picking got: %s', pickingId)
                    if pickingId and len(pickingId) == 1  and pickingId.state!='cancel':
                        _logger.debug('Setting quantities for picking %s', pickingId)
                        self.setPickingQuantities(pickingId, order)

                        if 'edited' in order:
                            datum = order['edited']
                        else:
                            datum = order['created']

                        date_object = datetime.strptime(datum, "%Y-%m-%dT%H:%M:%S.%fZ")
                        date_object.replace(microsecond=0)
                        pickingId.df_last_changedate_webship = date_object

                    #print(order)

                    if 'edited' in order:
                        allChangeDates.append(order['edited'])
                    else:
                        allChangeDates.append(order['created'])

        #print(allChangeDates)
        maxEdited = max(allChangeDates)

        date_object = datetime.strptime(maxEdited, "%Y-%m-%dT%H:%M:%S.%fZ").replace(microsecond=0)
        dt_for_odoo = date_object.strftime("%Y-%m-%d %H:%M:%S")

        _logger.debug("All pickings from Webship: %s", allPickingsWS)

        return date_object

    def sync_po_statusses_since_last(self, lastDate):
        """Poll Webship for purchase orders changed since lastDate and validate completed ones in Odoo."""
        maxEdited = None
        orders = self.fetchAll('purchase-orders', 'high', lastDate)

        if orders['status'] == 'success':
            for page in orders['data'].values():
                for po_order in page:
                    _logger.debug("Processing PO order: %s", po_order)
                    if po_order['status'] == 'completed':
                        pickingId = self.env['stock.picking'].search([('df_po_id_webship', '=', po_order['_id'])])
                        _logger.debug("PO picking found: %s", pickingId)
                        if pickingId and len(pickingId) == 1:
                            if pickingId.state != 'done':
                                _logger.info('Setting PO picking %s status to done', pickingId.name)

                                # setPickingQuantities validates a completed PO
                                # itself (native/legacy backorder handling). Do
                                # not button_validate() again here: on an
                                # already-done picking, or one intentionally left
                                # open because nothing was received, a second
                                # validate can raise and abort the rest of the
                                # PO poll loop.
                                self.setPickingQuantities(pickingId, po_order)

                                if 'edited' in po_order:
                                    datum = po_order['edited']
                                else:
                                    datum = po_order['created']

                                date_object = datetime.strptime(datum, "%Y-%m-%dT%H:%M:%S.%fZ")
                                date_object.replace(microsecond=0)
                                pickingId.df_last_changedate_webship = date_object

                    if 'edited' in po_order:
                        if po_order['edited'] != None and maxEdited == None:
                            maxEdited = po_order['edited']
                        elif po_order['edited'] > maxEdited:
                            maxEdited = po_order['edited']
                    else:
                        if po_order['created'] != None and maxEdited == None:
                            maxEdited = po_order['created']
                        elif po_order['created'] > maxEdited:
                            maxEdited = po_order['created']
                    _logger.debug('Max edited: %s', maxEdited)
        
        if maxEdited:
            date_object = datetime.strptime(maxEdited, "%Y-%m-%dT%H:%M:%S.%fZ").replace(microsecond=0)
            dt_for_odoo = date_object.strftime("%Y-%m-%d %H:%M:%S")
    
            return date_object
        else:
            return None

    def _allocate_qty_over_records(self, records, qty_to_allocate, capacity_getter):
        """
        Distribute qty_to_allocate over records using capacity_getter(record) as max per record.
        Returns: list of tuples (record, allocated_qty) and remaining qty (float).
        """
        remaining = float(qty_to_allocate or 0.0)
        allocations = []

        for r in records:
            if remaining <= 0:
                break

            cap = float(capacity_getter(r) or 0.0)
            if cap <= 0:
                continue

            take = min(remaining, cap)
            allocations.append((r, take))
            remaining -= take

        return allocations, remaining

    def _get_move_line_capacity(self, move_line):
        """
        Capacity for a move line = planned quantity for its move.
        (Most stable choice across Odoo versions.)
        """
        return move_line.move_id.product_uom_qty or 0.0

    def _get_move_capacity(self, move):
        """Capacity for a move = planned quantity."""
        return move.product_uom_qty or 0.0

    def _get_ignored_skus(self):
        """Return the set of SKUs configured via the 'Ignored SKUs' setting.
        The setting accepts both commas and newlines as separators."""
        if not hasattr(self, 'env'):
            return set()
        raw = self.env['ir.config_parameter'].sudo().get_str('webship.ignored_skus', '') or ''
        skus = set()
        for part in raw.replace(',', '\n').splitlines():
            part = part.strip()
            if part:
                skus.add(part)
        return skus

    def _filter_pmap_by_ignored_skus(self, pMap, sPicking):
        """Drop entries from pMap whose SKU appears in the 'Ignored SKUs' setting.

        Called AFTER the allocation passes, on the leftover pMap only: at that
        point every product that exists on the picking has already consumed its
        entry, so what is filtered here are Stoqflow-only products (e.g.
        packaging the warehouse adds). They are dropped entirely - no 'not
        found on picking' warning, nothing sent back to Odoo. An ignored SKU
        that IS on the picking is unaffected: its quantities were applied
        normally before this runs.

        SKUs are resolved first via local Odoo products (df_product_id_webship),
        with a single batched Stoqflow GET /products?subset=... fallback for the
        remainder. Matching is case- and whitespace-insensitive."""
        ignored = {s.strip().casefold() for s in self._get_ignored_skus() if s and s.strip()}
        if not ignored or not pMap:
            return

        webship_pids = list(pMap.keys())
        sku_by_pid = {}

        if hasattr(self, 'env'):
            products = self.env['product.product'].sudo().search([
                ('df_product_id_webship', 'in', webship_pids),
            ])
            for p in products:
                if p.default_code:
                    sku_by_pid[p.df_product_id_webship] = p.default_code

        unresolved = [pid for pid in webship_pids if pid not in sku_by_pid]
        if unresolved:
            try:
                subset_param = '?subset=%s&fields=sku' % ','.join(unresolved)
                result = self.performGet('products', subset_param)
                if result.get('status') == 'success' and isinstance(result.get('data'), list):
                    for prod in result['data']:
                        pid = prod.get('_id')
                        sku = prod.get('sku')
                        if pid and sku:
                            sku_by_pid[pid] = sku
            except Exception:
                _logger.exception(
                    "setPickingQuantities: failed to resolve SKUs for ignore-list filter on %s",
                    sPicking.name,
                )

        removed = []
        for pid, sku in sku_by_pid.items():
            if sku and sku.strip().casefold() in ignored and pid in pMap:
                removed.append((sku, pMap[pid]))
                del pMap[pid]

        if removed:
            _logger.info(
                "setPickingQuantities: ignored %d product(s) by SKU on %s: %s",
                len(removed), sPicking.name,
                ', '.join("%s (qty %s)" % (sku, qty) for sku, qty in removed),
            )

    def _use_native_backorder(self):
        """Whether to validate completed pickings with Odoo's native backorder
        confirmation. This is the DEFAULT: only the quantities actually
        picked/received in Stoqflow are validated and a receipt with 0 received
        units is left open, instead of the legacy make_backorder/force-done
        flow that completed unreceived lines at their ordered quantities.

        The legacy flow remains available as a fallback via the
        webship.use_legacy_backorder setting (developer mode) or an explicit
        webship.use_native_backorder = 'False' system parameter (the pre-flip
        opt-out, kept for backward compatibility)."""
        if not hasattr(self, 'env'):
            return True
        get_param = self.env['ir.config_parameter'].sudo().get_str
        if get_param('webship.use_legacy_backorder') == 'True':
            return False
        if get_param('webship.use_native_backorder') == 'False':
            return False
        return True

    def _validate_completed_picking_native(self, sPicking):
        """Validate a completed picking honouring the RECEIVED quantities that
        setPickingQuantities already wrote onto the moves. Only the received
        quantities are validated; Odoo's backorder confirmation is processed so
        a backorder is created for the not-yet-received items. A receipt with 0
        received units is left open. Returns a list of warnings."""
        warnings = []

        # Total units actually received (moves were reset and re-populated from
        # order_items[].received, so this reflects RECEIVED, not ordered, qtys).
        received_total = sum(
            sPicking.move_ids
            .filtered(lambda m: m.state not in ('cancel', 'done'))
            .mapped('quantity')
        )

        if received_total <= 0:
            # Completed in Stoqflow but nothing received (every line received 0).
            # Validating here would wrongly mark the whole receipt done at the
            # ordered quantities, so leave the picking open and record why.
            msg = ('Stoqflow order completed but 0 units received; '
                   'picking left open (nothing to validate).')
            warnings.append(msg)
            _logger.info('setPickingQuantities: %s for %s', msg, sPicking.name)
            return warnings

        if self.get_default_auto_create_backorder() == 'True':
            self.showDebugInfo('Validating picking with received quantities')
            try:
                _logger.info('Calling button_validate for picking %s', sPicking.name)
                validate_result = sPicking._webship_validate()

                # When some lines were received short (or not at all), Odoo
                # returns a backorder confirmation wizard for the remainder.
                # Process it so a backorder picking is created for the
                # not-yet-received items, instead of forcing the whole receipt
                # done at the ordered quantities.
                if isinstance(validate_result, dict) and \
                        validate_result.get('res_model') == 'stock.backorder.confirmation':
                    # The wizard context REPLACES the current one and its
                    # process() re-enters button_validate, so the internal
                    # bypass flag must be merged in or the manual-validation
                    # guard would refuse the sync's own validation.
                    backorder_wizard = self.env['stock.backorder.confirmation'] \
                        .with_context(dict(validate_result.get('context') or {},
                                           webship_internal_validate=True)).create({})
                    backorder_wizard.process()
                    _logger.info(
                        'Backorder created for unreceived items of picking %s', sPicking.name)
                elif isinstance(validate_result, dict) and \
                        validate_result.get('type') == 'ir.actions.act_window':
                    wizard_name = validate_result.get('res_model', 'unknown wizard')
                    _logger.warning(
                        'button_validate for %s returned unexpected wizard action: %s',
                        sPicking.name, wizard_name
                    )
                    warnings.append(
                        "Validation blocked by wizard: %s. Manual validation required." % wizard_name
                    )

                _logger.info('Picking %s validated (state: %s)', sPicking.name, sPicking.state)

            except Exception as e:
                _logger.exception(
                    "Error while validating picking %s from Webship", sPicking.name)
                warnings.append("Validation error: %s" % str(e))

            # Surface any remaining mismatch. Do NOT force _action_done here:
            # that would complete the unreceived lines at their ordered
            # quantities (the bug this replaces).
            if sPicking.state != 'done':
                short_lines = sPicking.move_ids.filtered(
                    lambda m: m.state not in ('cancel', 'done') and m.quantity != m.product_uom_qty
                )
                if short_lines:
                    line_details = []
                    for m in short_lines:
                        line_details.append(
                            '%s: %s of %s %s' % (
                                m.product_id.display_name,
                                m.quantity, m.product_uom_qty,
                                m.uom_id.name
                            )
                        )
                    msg = 'Picking not set to done. Quantity mismatch on: %s' % '; '.join(line_details)
                else:
                    msg = 'Picking not set to done after validation (state: %s). Check move states: %s' % (
                        sPicking.state,
                        ', '.join('%s (%s)' % (m.product_id.display_name, m.state) for m in sPicking.move_ids)
                    )
                warnings.append(msg)
                _logger.warning('setPickingQuantities: %s for %s', msg, sPicking.name)
        else:
            short_lines = sPicking.move_ids.filtered(
                lambda m: m.state not in ('cancel', 'done') and m.quantity < m.product_uom_qty
            )
            if short_lines:
                line_names = ', '.join(short_lines.mapped(lambda m: m.product_id.display_name))
                msg = 'Quantities not met on lines: %s. Auto-create backorder is disabled, could not complete picking.' % line_names
                _logger.info('Picking %s: %s', sPicking.name, msg)
                sPicking.df_picking_syncresult_webship = (
                    '<span style="color:red;">%s</span>' % msg
                )
            else:
                try:
                    _logger.info('Calling button_validate for picking %s (no backorder needed)', sPicking.name)
                    validate_result = sPicking._webship_validate()
                    if isinstance(validate_result, dict) and validate_result.get('type') == 'ir.actions.act_window':
                        wizard_name = validate_result.get('res_model', 'unknown wizard')
                        _logger.warning(
                            'button_validate for %s returned wizard action: %s',
                            sPicking.name, wizard_name
                        )
                        warnings.append(
                            "Validation blocked by wizard: %s. Manual validation required." % wizard_name
                        )
                    _logger.info('Picking %s validated (state: %s)', sPicking.name, sPicking.state)
                except Exception as e:
                    _logger.exception(
                        "Error while validating picking %s from Webship", sPicking.name)
                    warnings.append("Validation error: %s" % str(e))

                if sPicking.state != 'done':
                    msg = 'Picking not set to done after validation (state: %s). Check move states: %s' % (
                        sPicking.state,
                        ', '.join('%s (%s)' % (m.product_id.display_name, m.state) for m in sPicking.move_ids)
                    )
                    warnings.append(msg)
                    _logger.warning('setPickingQuantities: %s for %s', msg, sPicking.name)

        return warnings

    def _validate_completed_picking_legacy(self, sPicking):
        """Legacy validation behaviour (make_backorder + forced _action_done),
        kept behind the webship.use_native_backorder setting so it can be used
        as a fallback. Returns a list of warnings."""
        warnings = []

        if self.get_default_auto_create_backorder() == 'True':
            self.showDebugInfo('Setting picking to done')

            try:
                sPicking.make_backorder()

                _logger.info('Calling button_validate for picking %s', sPicking.name)

                validate_result = sPicking._webship_validate()

                # button_validate may return a wizard action instead of actually validating
                if isinstance(validate_result, dict) and validate_result.get('type') == 'ir.actions.act_window':
                    wizard_name = validate_result.get('res_model', 'unknown wizard')
                    _logger.warning(
                        'button_validate for %s returned wizard action: %s',
                        sPicking.name, wizard_name
                    )
                    warnings.append(
                        "Validation blocked by wizard: %s. Manual validation required." % wizard_name
                    )

                if sPicking.state != 'done':
                    _logger.info('Calling _action_done for picking %s (state still %s)', sPicking.name, sPicking.state)
                    sPicking._action_done()

                _logger.info('Picking %s validated successfully (state: %s)', sPicking.name, sPicking.state)

            except Exception as e:
                error_msg = str(e)

                _logger.exception(
                    "Error while validating picking %s from Webship",
                    sPicking.name
                )

                warnings.append("Validation error: %s" % error_msg)

            # Check if picking is still not done after validation attempt
            if sPicking.state != 'done':
                short_lines = sPicking.move_ids.filtered(
                    lambda m: m.state not in ('cancel', 'done') and m.quantity != m.product_uom_qty
                )
                if short_lines:
                    line_details = []
                    for m in short_lines:
                        line_details.append(
                            '%s: %s of %s %s' % (
                                m.product_id.display_name,
                                m.quantity, m.product_uom_qty,
                                m.uom_id.name
                            )
                        )
                    msg = 'Picking not set to done. Quantity mismatch on: %s' % '; '.join(line_details)
                else:
                    msg = 'Picking not set to done after validation (state: %s). Check move states: %s' % (
                        sPicking.state,
                        ', '.join('%s (%s)' % (m.product_id.display_name, m.state) for m in sPicking.move_ids)
                    )
                warnings.append(msg)
                _logger.warning('setPickingQuantities: %s for %s', msg, sPicking.name)
        else:
            short_lines = sPicking.move_ids.filtered(
                lambda m: m.state not in ('cancel', 'done') and m.quantity < m.product_uom_qty
            )
            if short_lines:
                line_names = ', '.join(short_lines.mapped(lambda m: m.product_id.display_name))
                msg = 'Quantities not met on lines: %s. Auto-create backorder is disabled, could not complete picking.' % line_names

                _logger.info(
                    'Picking %s: %s',
                    sPicking.name, msg
                )
                sPicking.df_picking_syncresult_webship = (
                    '<span style="color:red;">%s</span>' % msg
                )
            else:
                # All quantities match demand - safe to validate without backorder
                try:
                    _logger.info('Calling button_validate for picking %s (no backorder needed)', sPicking.name)
                    validate_result = sPicking._webship_validate()

                    if isinstance(validate_result, dict) and validate_result.get('type') == 'ir.actions.act_window':
                        wizard_name = validate_result.get('res_model', 'unknown wizard')
                        _logger.warning(
                            'button_validate for %s returned wizard action: %s',
                            sPicking.name, wizard_name
                        )
                        warnings.append(
                            "Validation blocked by wizard: %s. Manual validation required." % wizard_name
                        )

                    if sPicking.state != 'done':
                        sPicking._action_done()

                    _logger.info('Picking %s validated successfully (state: %s)', sPicking.name, sPicking.state)

                except Exception as e:
                    error_msg = str(e)
                    _logger.exception(
                        "Error while validating picking %s from Webship",
                        sPicking.name
                    )
                    warnings.append("Validation error: %s" % error_msg)

                if sPicking.state != 'done':
                    msg = 'Picking not set to done after validation (state: %s). Check move states: %s' % (
                        sPicking.state,
                        ', '.join('%s (%s)' % (m.product_id.display_name, m.state) for m in sPicking.move_ids)
                    )
                    warnings.append(msg)
                    _logger.warning('setPickingQuantities: %s for %s', msg, sPicking.name)

        return warnings

    def setPickingQuantities(self, sPicking, order):
        """Apply picked/received quantities from a Webship order onto an Odoo picking.
        Handles move lines first, then falls back to moves for any remainder."""
        self.showDebugInfo('In picking quantites')
        warnings = []

        _logger.debug('Picking got: %s', sPicking)
        _logger.debug('Order got: %s', order)

        self._debug_dump(sPicking, self.PICKING_DEBUG_FIELDS, 'Picking')

        parcels = order.get('parcels', [])
        if parcels:
            tracking_numbers = ','.join(
                p['tracking_number'] for p in parcels if p.get('tracking_number')
            )
            tracking_urls = ','.join(
                p['tracking_url'] for p in parcels if p.get('tracking_url')
            )
            if tracking_numbers and hasattr(sPicking, 'carrier_tracking_ref'):
                sPicking.carrier_tracking_ref = tracking_numbers
            if tracking_urls and hasattr(sPicking, 'df_carrier_tracking_urls'):
                sPicking.df_carrier_tracking_urls = tracking_urls

            self._sync_parcels(sPicking, parcels)

        # Map StoqFlow preferred_courier -> Odoo carrier_id
        preferred_courier = order.get('preferred_courier')
        if preferred_courier and hasattr(self, 'env'):
            fetch_courier_enabled = self.env['ir.config_parameter'].sudo().get_str(
                'webship.fetch_courier', 'True'
            )
            if fetch_courier_enabled and fetch_courier_enabled != 'False':
                carrier = sPicking.env['delivery.carrier'].stoqflow_find_delivery_carrier(preferred_courier)
                if carrier:
                    if sPicking.carrier_id != carrier:
                        sPicking.carrier_id = carrier.id
                        _logger.info(
                            "setPickingQuantities: set carrier_id to '%s' for picking %s",
                            carrier.name, sPicking.name,
                        )
                else:
                    warnings.append(
                        "Courier '%s' present on Stoqflow order but not linked in Odoo" % preferred_courier
                    )
                    _logger.warning(
                        "setPickingQuantities: courier '%s' not linked in Odoo for picking %s",
                        preferred_courier, sPicking.name,
                    )

        if order.get('status') == 'completed':
            # ------------------------------------------------------------
            # Reset quantities first
            # ------------------------------------------------------------
            for m in sPicking.move_ids.filtered(lambda m: m.state not in ('cancel', 'done')):
                self._debug_dump(m, self.MOVE_DEBUG_FIELDS, 'Reading move')
                if m.product_id.df_product_id_webship == False:
                    sku = m.product_id.default_code
                    pId = self.findProductBySku(sku)
                    if isinstance(pId, dict) and 'id' in pId:
                        m.product_id.df_product_id_webship = pId['id']
                    elif isinstance(pId, dict) and 'error' in pId:
                        msg = "Product '%s' (SKU: %s): %s" % (m.product_id.name, sku or 'N/A', pId['error'])
                        warnings.append(msg)
                        _logger.warning("setPickingQuantities: %s", msg)
                    else:
                        msg = "Product '%s' (SKU: %s): not found in Stoqflow" % (m.product_id.name, sku or 'N/A')
                        warnings.append(msg)
                        _logger.warning("setPickingQuantities: %s", msg)

                m.write({'quantity': 0.0})

            for pl in sPicking.move_line_ids.filtered(lambda pl: pl.state not in ('cancel', 'done')):
                self._debug_dump(pl, self.MOVE_LINE_DEBUG_FIELDS,
                                 'Reading picking line')
                self.showDebugInfo('Setting quantity for line: ' + str(pl.product_id.name))
                pl.write({'quantity': 0.0, 'quantity_product_uom': 0.0})

            # ------------------------------------------------------------
            # Build pMap (webship_product_id -> total_qty)
            # and batchMap (webship_product_id -> batch/lot)
            # ------------------------------------------------------------
            pMap = {}
            batchMap = {}

            # Normal outbound orders: use "picks"
            # Use parent_product_id when present (pick substitution),
            # otherwise fall back to product_id (direct pick).
            _logger.info("setPickingQuantities: building pMap from %s picks", len(order.get('picks') or []))
            for o in order.get('picks') or []:
                ws_pid = o.get('parent_product_id') or o['product_id']
                if o.get('parent_product_id') and o['parent_product_id'] != o['product_id']:
                    _logger.info(
                        "setPickingQuantities: pick substitution - picked %s (qty %s, fraction %s) for ordered product %s",
                        o['product_id'], o['quantity'], o.get('fraction', 'N/A'), ws_pid
                    )
                else:
                    _logger.info(
                        "setPickingQuantities: direct pick - product %s qty %s",
                        ws_pid, o['quantity']
                    )
                if ws_pid not in pMap:
                    pMap[ws_pid] = o['quantity']
                    if o.get('batch'):
                        batchMap[ws_pid] = o['batch']
                else:
                    pMap[ws_pid] += o['quantity']

            # Purchase order / inbound style: use received from order_items
            if not order.get('picks'):
                _logger.info("setPickingQuantities: no picks found, using received from order_items")
                for o in order.get('order_items') or []:
                    if o.get('received'):
                        _logger.info(
                            "setPickingQuantities: order_item %s received %s",
                            o['product_id'], o['received']
                        )
                        if o['product_id'] not in pMap:
                            pMap[o['product_id']] = o['received']
                        else:
                            pMap[o['product_id']] = pMap[o['product_id']] + o['received']

            _logger.info('setPickingQuantities: pMap built: %s', pMap)

            self.showDebugInfo('pMap: ' + str(pMap))

            # ------------------------------------------------------------
            # 1) Allocate quantities across MOVE LINES (best practice)
            # ------------------------------------------------------------
            for webship_pid, total_qty in list(pMap.items()):

                # Only not done/cancel lines for this product
                lines = sPicking.move_line_ids.filtered(lambda l:
                                                        l.state not in ('cancel', 'done')
                                                        and l.product_id.df_product_id_webship == webship_pid
                                                        )

                if not lines:
                    continue

                # Deterministic ordering
                lines = lines.sorted(key=lambda l: (l.move_id.id, l.id))

                allocations, remaining = self._allocate_qty_over_records(
                    lines,
                    total_qty,
                    self._get_move_line_capacity
                )

                for line, take in allocations:
                    self.showDebugInfo(
                        f'Allocating {take} to move line {line.id} product {line.product_id.name}'
                    )

                    sValues = {
                        'quantity': take,
                        'quantity_product_uom': take,
                    }

                    if batchMap.get(webship_pid) is not None:
                        sValues['lot_name'] = batchMap.get(webship_pid)

                    line.write(sValues)

                # If fully allocated remove from map, otherwise keep remainder for moves
                if remaining <= 0:
                    del pMap[webship_pid]
                else:
                    pMap[webship_pid] = remaining

            # ------------------------------------------------------------
            # 2) Allocate any leftovers across MOVES (optional)
            # ------------------------------------------------------------
            for webship_pid, total_qty in list(pMap.items()):

                moves = sPicking.move_ids.filtered(lambda m:
                                                   m.state not in ('cancel', 'done')
                                                   and m.product_id.df_product_id_webship == webship_pid
                                                   )

                if not moves:
                    continue

                moves = moves.sorted(key=lambda m: m.id)

                allocations, remaining = self._allocate_qty_over_records(
                    moves,
                    total_qty,
                    self._get_move_capacity
                )

                for move, take in allocations:
                    self.showDebugInfo(
                        f'Allocating {take} to move {move.id} product {move.product_id.name}'
                    )
                    move.write({'quantity': take})

                if remaining <= 0:
                    del pMap[webship_pid]
                else:
                    pMap[webship_pid] = remaining

            # After both allocation passes, whatever is left in pMap is either
            # a Stoqflow-only product or overflow. Drop the entries whose SKU
            # is on the 'Ignored SKUs' setting HERE - not before allocation -
            # so an ignored SKU that legitimately is on the picking still gets
            # its real quantities applied (filtering earlier left such a line
            # zeroed, and the backorder split then turned it into a phantom
            # backorder that could never be fulfilled or linked). Ignored SKUs
            # never flow back into Odoo: no warning, no line, nothing.
            self._filter_pmap_by_ignored_skus(pMap, sPicking)

            # Report any Webship product IDs that could not be matched to Odoo moves
            if pMap:
                for webship_pid, remaining_qty in pMap.items():
                    # Check if the product exists on done/cancel moves (already processed)
                    done_moves = sPicking.move_ids.filtered(lambda m:
                        m.state in ('cancel', 'done')
                        and m.product_id.df_product_id_webship == webship_pid
                    )
                    # Try to resolve the product name + SKU from the Stoqflow ID
                    product_label = None
                    product = self.env['product.product'].sudo().search(
                        [('df_product_id_webship', '=', webship_pid)], limit=1
                    )
                    if product:
                        sku = product.default_code or ''
                        product_label = "'%s' (SKU: %s)" % (product.name, sku) if sku else "'%s'" % product.name
                    if not product_label:
                        # Last resort: fetch from Stoqflow API to get the SKU
                        try:
                            ws_result = self.performGet('products/', webship_pid)
                            if ws_result.get('status') == 'success' and ws_result.get('data'):
                                ws_sku = ws_result['data'].get('sku', '')
                                ws_name = ws_result['data'].get('name', '')
                                if ws_sku:
                                    product_label = "'%s' (SKU: %s)" % (ws_name, ws_sku) if ws_name else "(SKU: %s)" % ws_sku
                                elif ws_name:
                                    product_label = "'%s'" % ws_name
                        except Exception:
                            _logger.debug("Could not fetch product %s from Stoqflow API", webship_pid)
                    if not product_label:
                        product_label = "Stoqflow ID '%s'" % webship_pid

                    if done_moves:
                        msg = "%s (qty %s): product found on picking but move(s) already in '%s' state" % (
                            product_label, remaining_qty, done_moves[0].state)
                    else:
                        msg = "%s (qty %s): no matching product found on picking" % (product_label, remaining_qty)
                    warnings.append(msg)
                    _logger.warning("setPickingQuantities: %s on %s", msg, sPicking.name)
        #END if new status = 'completed'

        # ------------------------------------------------------------
        # Status update + validation
        # ------------------------------------------------------------
        oldStatus = sPicking.df_status_webship or ''
        newStatus = order['status']

        if newStatus == 'completed' and sPicking.state != 'done':
            # Two validation strategies, switched by a developer-mode setting:
            # - native (default): validate only the received quantities and let
            #   Odoo's backorder confirmation create a backorder for the
            #   not-yet-received items; a fully-unreceived receipt is left open.
            # - legacy (webship.use_legacy_backorder = True): the previous
            #   make_backorder + force-done flow, kept as a fallback.
            if self._use_native_backorder():
                warnings += self._validate_completed_picking_native(sPicking)
            else:
                warnings += self._validate_completed_picking_legacy(sPicking)

        if oldStatus != newStatus:
            if newStatus in VALID_WEBSHIP_STATUSES:
                sPicking.df_status_webship = newStatus
            else:
                _logger.warning(
                    'Unknown Stoqflow status %r for picking %s, skipping status update',
                    newStatus, sPicking.name,
                )
            # Use edited, falling back to created; guard against an order dict
            # that carries neither so the whole sync cannot crash on it.
            change_date = order.get('edited') or order.get('created')
            if change_date:
                sPicking.df_last_changedate_webship = datetime.strptime(
                    change_date,
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ).replace(microsecond=0)

            self.showDebugInfo('Status changed from ' + oldStatus + ' to ' + newStatus)

        if warnings:
            # Group warnings by type for a cleaner display
            done_warnings = [w for w in warnings if 'already in' in w]
            not_found_warnings = [w for w in warnings if 'no matching product' in w]
            other_warnings = [w for w in warnings if w not in done_warnings and w not in not_found_warnings]

            # If the only warnings are about done-state moves, treat as success
            if done_warnings and not not_found_warnings and not other_warnings:
                sPicking.df_picking_syncresult_webship = 'success'
            else:
                parts = []
                if not_found_warnings:
                    parts.append(
                        '<b>%d product(s) not found</b> on picking:<br/>%s'
                        % (len(not_found_warnings), '<br/>'.join(not_found_warnings))
                    )
                if other_warnings:
                    parts.append('<br/>'.join(other_warnings))

                warning_html = '<br/>'.join(parts)
                sPicking.df_picking_syncresult_webship = '<span style="color:orange;">\u26A0 Completed with warnings:</span><br/>' + warning_html

            _logger.info("setPickingQuantities warnings for %s: %s", sPicking.name, '; '.join(warnings))
        else:
            sPicking.df_picking_syncresult_webship = 'success'

        # The warnings are soft: the callers (statusWsToOdoo, the status
        # crons, tests) surface them via _sync_warnings or assertions without
        # treating the sync as failed.
        return warnings

    def _sync_parcels(self, picking, parcels):
        """Store Stoqflow parcel data on the picking as webship.parcel records.
        Existing parcels are deleted and recreated from the latest API response."""
        if not hasattr(self, 'env'):
            return
        Parcel = self.env['webship.parcel'].sudo()
        # Remove existing parcels for this picking to avoid duplicates
        Parcel.search([('picking_id', '=', picking.id)]).unlink()

        for p in parcels:
            addr = p.get('shipping_address', {})
            content_vals = []
            for c in p.get('contents', []):
                content_vals.append((0, 0, {
                    'df_stoqflow_product_id': c.get('product_id', ''),
                    'df_sku': c.get('sku', ''),
                    'df_description': c.get('description', ''),
                    'df_quantity': c.get('quantity', 0),
                    'df_weight': c.get('weight', 0),
                    'df_hs_code': c.get('hs_code', ''),
                    'df_origin_country': c.get('origin_country', ''),
                    'df_value': c.get('value', 0),
                }))
            resource_vals = []
            for r in p.get('resources', []):
                resource_vals.append((0, 0, {
                    'df_stoqflow_id': r.get('_id', ''),
                    'df_name': r.get('name', ''),
                    'df_quantity': r.get('quantity', 0),
                }))
            Parcel.create({
                'picking_id': picking.id,
                'df_stoqflow_id': p.get('_id', ''),
                'df_number': p.get('number', 0),
                'df_tracking_number': p.get('tracking_number', ''),
                'df_tracking_url': p.get('tracking_url', ''),
                'df_label_url': p.get('label_url', ''),
                'df_invoice_url': p.get('invoice_url', ''),
                'df_provider': p.get('provider', ''),
                'df_provider_id': p.get('provider_id', ''),
                'df_weight': p.get('weight', 0),
                'df_width': p.get('width', 0),
                'df_height': p.get('height', 0),
                'df_length': p.get('length', 0),
                'df_shipping_cost': p.get('shipping_cost', 0),
                'df_shipping_name': addr.get('name', ''),
                'df_shipping_company': addr.get('company', ''),
                'df_shipping_address': addr.get('address_1', ''),
                'df_shipping_postal_code': addr.get('postal_code', ''),
                'df_shipping_city': addr.get('city', ''),
                'df_shipping_country': addr.get('country', ''),
                'df_content_ids': content_vals,
                'df_resource_ids': resource_vals,
            })

    def build_order_object(self, picking):
        """Build the full Webship order payload from an outbound Odoo picking.
        Validates SKUs, client data, stock availability, and scheduled dates."""
        items = self.picking_get_line_items(picking)

        _logger.debug("build_order_object items: %s", items)

        allCatShops = picking.env['product.category'].sudo().search([('df_cat_shop_id_webship', '!=', False)])

        allCatsMap = {}
        for ac in allCatShops:
            allCatsMap[ac.parent_path] = ac.df_cat_shop_id_webship

        skus = self.findProductsBySku(picking)

        _logger.debug('SKUs found: %s', skus)

        sOutput = {}

        sOutput['mainList'] = []
        for i in items:
            if i['divides'] == []:
                sOutput['mainList'].append({'name':i['productObj'].name, 'type':i['type'], 'default_code':i['default_code'], 'product_id':i['product_id'], 'quantity':i['quantity'], 'shopId':self.get_shop_for_product(i['productObj'], allCatsMap), 'WSku':self.get_webship_sku(i['default_code'], skus)})
            else:
                for j in i['divides']:
                    sOutput['mainList'].append({'name':i['productObj'].name, 'type':i['type'], 'default_code':j['Sku'], 'product_id':i['product_id'], 'quantity':j['OrderQty'], 'containerQty':j['Qty'],'shopId':self.get_shop_for_product(i['productObj'], allCatsMap), 'WSku':self.get_webship_sku(j['Sku'], skus)})



        clientCode = picking.partner_id.df_client_id_webship

        err = []
        if clientCode == False:
            fallback_partner = picking.sale_id.partner_id if picking.sale_id else None
            err = self.sync_partner(picking.partner_id, fallback_partner=fallback_partner,
                                    delivery_partner=picking.partner_id)

        if err == [] and clientCode == False:
            clientCode = picking.partner_id.df_client_id_webship

        sOutput['clientCode'] = clientCode

        if picking.sale_id.id != False and picking.sale_id.commitment_date != False:
            sOutput['scheduledDateWs'] = self.convert_datetime(picking.sale_id.commitment_date)
            sOutput['sendScheduledDate'] = True
        else:
            sOutput['sendScheduledDate'] = False

        sOutput['errors'] = []

        if sOutput['sendScheduledDate'] == True:
            current_dateTime = datetime.now()
            if picking.sale_id.commitment_date < current_dateTime:
                sOutput['errors'].append('Shipping date cannot be in the past')

        if items == []:
            if hasattr(self, '_skipped_products') and self._skipped_products:
                for product_name in self._skipped_products:
                    sOutput['errors'].append(_('No SKU for line with product %s') % product_name)
            else:
                sOutput['errors'].append(_('No syncable items found on this picking'))
        elif hasattr(self, '_skipped_products') and self._skipped_products:
            for product_name in self._skipped_products:
                sOutput['errors'].append(_('No SKU for line with product %s') % product_name)

        #if clientCode == False:
        #    sOutput['errors'].append('Client does not exist in Webship')

        for i in sOutput['mainList']:
            if i['default_code'] == False or i['default_code'] == None:
                sOutput['errors'].append(_('SKU missing on product %s') % i['name'])

        for i in sOutput['mainList']:
            _logger.debug('Product code: %s, WSku: %s', i['default_code'], i['WSku'])
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] == None:
                _logger.warning('No Webship SKU for product: %s', i)
                sOutput['errors'].append(_('SKU not found in Stoqflow for product %s (code: %s)') % (i['name'], i['default_code']))

        for i in sOutput['mainList']:
            if not self.is_integer_float(i['quantity']):
                sOutput['errors'].append('Product ' + i['name'] + ' has non integer value')

        allShops = set()
        for i in sOutput['mainList']:
            if i['shopId'] is not None:
                allShops.add(i['shopId'])

        if len(allShops) > 1:
            sOutput['errors'].append('Different shop ids found in order (' + str(allShops) + ')')

        if len(allShops) == 1:
            shopId = list(allShops)[0]
        else:
            shopId = self.get_default_shop()

        origin_number = (
            picking.sale_id.name[:50]
            if picking.sale_id
            else picking.name
        )

        sOutput['webshipObj'] = {'shop_id': shopId, 'client_id': clientCode, 'origin': {'id':str(picking.id), 'number':origin_number}}

        # Testing-only escape hatch: omit 'origin' so Stoqflow's unique-origin
        # constraint doesn't block re-sending a picking.
        if hasattr(self, 'env') and self.env['ir.config_parameter'].sudo().get_str('webship.skip_origin') == 'True':
            sOutput['webshipObj'].pop('origin', None)

        _logger.debug("build_order_object output: %s", sOutput)

        if picking.note != False:
            sOutput['webshipObj']['notes'] = self._truncate(picking.note, 500)
        elif picking.sale_id != False and picking.sale_id.partner_id.df_standard_internal_note:
            sOutput['webshipObj']['notes'] = self._truncate(picking.sale_id.partner_id.df_standard_internal_note, 500)

        if sOutput['sendScheduledDate']:
            sOutput['webshipObj']['status'] = 'on-hold'
            sOutput['webshipObj']['scheduled'] = sOutput['scheduledDateWs']
        else:
            #sOutput['webshipObj']['status'] = 'ready-to-pick'
            sOutput['webshipObj']['status'] = self.get_default_status()

        sOutput['webshipObj']['order_items'] =[]
        for i in sOutput['mainList']:
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] != None and i['type'] != 'service' and i['quantity'] != 0.0:
                sOutput['webshipObj']['order_items'].append({'product_id':i['WSku'], 'quantity':i['quantity']})

        _logger.debug('Checking client info...')
        if True:
            #print(picking.sale_id.partner_shipping_id)

            sCountrCode = picking.partner_id.country_code
            if sCountrCode == False:
                sCountrCode = 'BE'

            sEmail = picking.partner_id.email
            sPhone = picking.partner_id.phone

            fallback_enabled = self.env['ir.config_parameter'].sudo().get_str('webship.fallback_sale_order_contact') == 'True'
            if fallback_enabled:
                candidates = []
                if picking.sale_id and picking.sale_id.partner_id:
                    candidates.append(picking.sale_id.partner_id)
                commercial = picking.partner_id.commercial_partner_id
                if commercial and commercial.id != picking.partner_id.id:
                    candidates.append(commercial)
                for c in candidates:
                    if not sEmail and c.email:
                        sEmail = c.email
                        _logger.info("build_order_object: falling back to %s for email on picking %s", c.name, picking.name)
                    if not sPhone and c.phone:
                        sPhone = c.phone
                        _logger.info("build_order_object: falling back to %s for phone on picking %s", c.name, picking.name)

            clientInfo = {
                'name':self._truncate(picking.partner_id.name, 100),
                'vat':picking.partner_id.vat,
                'address_1':self._truncate(picking.partner_id.street, 100),
                'address_2':self._truncate(picking.partner_id.street2 or ' ', 100),
                'city':self._truncate(picking.partner_id.city, 100),
                'postal_code':self._truncate(picking.partner_id.zip, 20),
                'country':sCountrCode,
                'email':self._clean_email(sEmail, context=picking.partner_id.name),
                'phone':self._truncate(sPhone, 100),
                          }
            _logger.debug("Client info: %s", clientInfo)

            keys_to_remove = [key for key, value in clientInfo.items() if not value]

            for key in keys_to_remove:
                clientInfo.pop(key)

            #if 'vat' not in clientInfo:
            #    sOutput['errors'].append('Vat not present in shipping address')

            #if 'email' not in clientInfo:
            #    sOutput['errors'].append('E-mail address not present in shipping address. Is mandatory because shipping address is different from bill address')

            if 'address_1' not in clientInfo:
                sOutput['errors'].append('Address not present in shipping address')

            if 'city' not in clientInfo:
                sOutput['errors'].append('City not present in shipping address')

            if 'postal_code' not in clientInfo:
                sOutput['errors'].append('Postal code not present in shipping address')

            if 'country' not in clientInfo:
                sOutput['errors'].append('Country not present in shipping address')

            if clientInfo != {}:
                sOutput['webshipObj']['client_info'] = clientInfo
        
        _logger.info('Built object: %s', sOutput)

        return sOutput

    def build_po_object(self, picking):
        """Build the Webship purchase order payload from an inbound Odoo picking."""
        items = self.picking_get_line_items(picking)

        _logger.debug("build_po_object items: %s", items)

        allCatShops = picking.env['product.category'].sudo().search([('df_cat_shop_id_webship', '!=', False)])

        allCatsMap = {}
        for ac in allCatShops:
            allCatsMap[ac.parent_path] = ac.df_cat_shop_id_webship

        skus = self.findProductsBySku(picking)

        sOutput = {}

        sOutput['mainList'] = []
        for i in items:
            sOutput['mainList'].append({'name':i['productObj'].name, 'type':i['type'], 'default_code':i['default_code'], 'product_id':i['product_id'], 'quantity':i['quantity'], 'shopId':self.get_default_shop(), 'WSku':self.get_webship_sku(i['default_code'], skus)})

        supplierCode = picking.purchase_id.partner_id.df_supplier_id_webship if picking.purchase_id else False
        if not supplierCode:
            supplierCode = picking.partner_id.df_supplier_id_webship

        sOutput['supplierCode'] = supplierCode
        sOutput['scheduledDate'] = picking.scheduled_date
        sOutput['scheduledDateWs'] = self.convert_datetime(picking.scheduled_date)
        if picking.scheduled_date != False and (picking.scheduled_date - datetime.now()).days > 1:
            sOutput['sendScheduledDate'] = True
        else:
            sOutput['sendScheduledDate'] = False

        sOutput['errors'] = []

        if items == []:
            if hasattr(self, '_skipped_products') and self._skipped_products:
                for product_name in self._skipped_products:
                    sOutput['errors'].append(_('No SKU for line with product %s') % product_name)
            else:
                sOutput['errors'].append(_('No syncable items found on this picking'))
        elif hasattr(self, '_skipped_products') and self._skipped_products:
            for product_name in self._skipped_products:
                sOutput['errors'].append(_('No SKU for line with product %s') % product_name)

        if supplierCode == False:
            sOutput['errors'].append(_('Supplier does not exist in Stoqflow'))

        for i in sOutput['mainList']:
            if i['default_code'] == False or i['default_code'] == None:
                sOutput['errors'].append(_('SKU missing on product %s') % i['name'])

        for i in sOutput['mainList']:
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] == None:
                sOutput['errors'].append(_('SKU not found in Stoqflow for product %s (code: %s)') % (i['name'], i['default_code']))

        #print('Location dest id: ')
        #print(picking.location_dest_id.df_warehouse_id_webship)
        #sOutput['webshipObj'] = {'supplier_id': supplierCode, 'warehouse_id':self.get_warehouse()}
        sOutput['webshipObj'] = {'supplier_id': supplierCode, 'warehouse_id': picking.location_dest_id.df_warehouse_webship.warehouse_id}

        # Supplier reference for deduplication: picking ID + order name
        po_ref = "%s-%s" % (picking.id, picking.name or '')
        sOutput['webshipObj']['supplier_reference'] = self._truncate(po_ref, 100)

        # Custom fields with picking ID and order name for traceability
        # Note: custom_fields omitted – the Stoqflow API requires an _id field
        # on each entry whose format is undocumented. The supplier_reference
        # already contains the picking ID and name for traceability.

        if sOutput['sendScheduledDate']:
            sOutput['webshipObj']['status'] = 'on-hold'
            sOutput['webshipObj']['scheduled'] = sOutput['scheduledDateWs']
        else:
            sOutput['webshipObj']['status'] = self.get_default_po_status()

        sOutput['webshipObj']['order_items'] =[]
        for i in sOutput['mainList']:
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] != None and i['type'] != 'service' and i['quantity'] != 0.0:
                sOutput['webshipObj']['order_items'].append({'product_id':i['WSku'], 'quantity':i['quantity']})

        return sOutput

    def get_webship_sku(self, code, webshipskus):
        """Resolve an Odoo SKU to its Webship product ID using the pre-fetched SKU map."""
        _logger.info('Looking for ' + str(code) + ' in SKUS: ' + str(webshipskus))
        
        if code != False and code != None and 'items' in webshipskus and code in webshipskus['items'].keys():
            _logger.info('Returning ' + str(webshipskus['items'][code]))
            return webshipskus['items'][code]
        else:
            return None

    def convert_datetime(self, date_time_object):
        """Convert an Odoo datetime to the ISO format expected by Webship."""
        if date_time_object == None or date_time_object == False:
            return None
        else:
            return date_time_object.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def get_shop_for_product(self, productObj, allCatsMap):
        """Return the Stoqflow shop_id for a product.
        Walks up the category hierarchy looking for a df_cat_shop_id_webship
        mapping; if none is configured, falls back to the configured default
        shop so every order item ends up with a concrete shop_id and Stoqflow
        does not return 'not all order items are related to the selected
        shop'."""
        foundShop = None
        for a, b in allCatsMap.items():
            if productObj.categ_id.parent_path.startswith(a):
                foundShop = b
        if not foundShop:
            foundShop = self.get_default_shop()
        return foundShop

    def get_picking_code(self, pickingId):
        """Fetch the human-readable order_number from Webship for an outbound order."""
        url = self.baseUrl + 'orders/' + pickingId

        self.sleep()
        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        if response.status_code != 200:
            _logger.error('get_picking_code failed with status code %s: %s', response.status_code, response.text)
        else:
            responseData = response.json()
            _logger.info(responseData)
            if 'order_number' in responseData:
                webshipCode = responseData['order_number']
                return webshipCode
        return None

    def get_po_code(self, pickingId):
        """Fetch the human-readable order_number from Webship for a purchase order."""
        url = self.baseUrl + 'purchase-orders/' + pickingId

        self.sleep()
        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        if response.status_code != 200:
            _logger.error('get_po_code failed with status code %s: %s', response.status_code, response.text)
        else:
            responseData = response.json()
            _logger.info(responseData)
            if 'order_number' in responseData:
                webshipCode = responseData['order_number']
                return webshipCode
        return None

    def setStatusOrder(self, orderId, sStatus):
        """Update the status of an outbound order in Webship."""
        url = self.baseUrl + 'orders/' + orderId + '/status'

        sPayload = {'status':sStatus}
        self.sleep()

        response = self.session.put(url, json=sPayload, timeout=self.REQUEST_TIMEOUT)

        if response.status_code != 200:
            _logger.error('setStatusOrder failed with status code %s: %s', response.status_code, response.text)

    def setStatusPO(self, poId, sStatus):
        """Update the status of an inbound purchase order in Webship."""
        url = self.baseUrl + 'purchase-orders/' + poId + '/status'

        sPayload = {'status': sStatus}
        self.sleep()

        response = self.session.put(url, json=sPayload, timeout=self.REQUEST_TIMEOUT)

        if response.status_code != 200:
            _logger.error('setStatusPO failed with status code %s: %s', response.status_code, response.text)

    def cancelInWebship(self, object_type, object_id):
        """Cancel an order ('order') or purchase order ('purchase_order') in Stoqflow.
        Returns (True, '') on success, (False, error_message) on failure."""
        if not object_id:
            return False, 'Missing Stoqflow id'

        if object_type == 'purchase_order':
            url = self.baseUrl + 'purchase-orders/' + object_id + '/status'
        else:
            url = self.baseUrl + 'orders/' + object_id + '/status'

        self.sleep()
        try:
            response = self.session.put(
                url, json={'status': 'cancelled'}, timeout=self.REQUEST_TIMEOUT,
            )
        except Exception as e:
            _logger.exception('cancelInWebship request failed: %s', e)
            return False, str(e)

        if response.status_code != 200:
            _logger.error(
                'cancelInWebship failed with status code %s: %s',
                response.status_code, response.text,
            )
            return False, 'HTTP %s: %s' % (response.status_code, response.text)

        return True, ''

    # ------------------------------------------------------------------
    # Product sync
    # ------------------------------------------------------------------

    def match_product(self, product):
        """Link an Odoo product to its Webship counterpart by SKU."""
        foundProduct = self.findProductBySku(product.default_code)

        _logger.debug("match_product result: %s", foundProduct)

        if foundProduct == []:
            return ['Sku not found in Webship']
        elif isinstance(foundProduct, dict) and 'error' in foundProduct:
            # SKUs are expected to be unique in Stoqflow, so this normally
            # cannot happen; guard it so a >1 match reports an error instead
            # of crashing on the missing 'id' key.
            return ['Multiple SKU found in Stoqflow']
        else:
            product.df_product_id_webship = foundProduct['id']

        return []

    def sync_product(self, product):
        """Create or update a product in Webship from an Odoo product record.
        If the product doesn't exist, checks that the SKU isn't already in use."""
        errors = []

        if product.default_code == False or product.default_code == '':
            errors.append('No sku for product')

        # Use product-level brand if set, otherwise fall back to global default
        if product.df_brand_id:
            brandId = product.df_brand_id.brand_id
        else:
            brandId = self.get_brand()

        productObj = {
            'brand_id': brandId,
            'sku': product.default_code,
            'name': product.name,
            'price': product.standard_price,
            'retail_price': product.lst_price,
            # Odoo 18+ dropped the 'product' type; storable goods are flagged
            # by is_storable. The old check was always False, so every product
            # was pushed to Stoqflow as has_stock=False.
            'has_stock': bool(product.is_storable),
        }

        # Description (from Odoo sale description)
        if product.description_sale:
            productObj['description'] = product.description_sale

        # Product type
        if product.df_type:
            productObj['type'] = product.df_type

        # Stock type
        if product.df_stock_type:
            productObj['stock_type'] = product.df_stock_type

        # Stock levels
        if product.df_min_stock:
            productObj['min_stock'] = product.df_min_stock
        if product.df_max_stock:
            productObj['max_stock'] = product.df_max_stock
        if product.df_min_order:
            productObj['min_order'] = product.df_min_order
        if product.df_order_multiples:
            productObj['order_multiples'] = product.df_order_multiples

        # Physical properties (weight from Odoo in kg, convert to grams)
        properties = {}
        if product.weight:
            properties['weight'] = int(product.weight * 1000)
        if product.df_length:
            properties['length'] = product.df_length
        if product.df_width:
            properties['width'] = product.df_width
        if product.df_height:
            properties['height'] = product.df_height
        if properties:
            properties['unit'] = {'value': 1, 'unit': 'item'}
            productObj['properties'] = properties

        # Trade / customs
        if product.df_hs_code:
            productObj['hs_code'] = product.df_hs_code
        if product.df_country_of_origin:
            productObj['country_of_origin'] = product.df_country_of_origin
        if product.df_economic_operator:
            productObj['economic_operator'] = product.df_economic_operator

        # Flags
        flags = {}
        if product.df_stock_bio:
            flags['bio'] = True
        if product.df_stock_foodstuff:
            flags['foodstuff'] = True
        if product.df_flag_cold_chain:
            flags['cold_chain'] = True
        if product.df_flag_fragile:
            flags['fragile'] = True
        if product.df_flag_hazardous:
            flags['hazardous'] = True
        if flags:
            productObj['flags'] = flags

        # Checks
        checks = {}
        if product.df_check_expiry_dates:
            checks['expiry_dates'] = True
        if product.df_check_batches:
            checks['batches'] = True
        if product.df_check_serial_numbers:
            checks['serial_numbers'] = True
        if checks:
            productObj['checks'] = checks

        # Barcodes
        if product.barcode:
            productObj['barcodes'] = [{'type':'ean13', 'code':product.barcode, 'main':True}]

        if product.df_product_id_webship == False:
            # Before creating, check if this SKU already exists in Webship
            existing_product = self.findProductBySku(product.default_code)

            # If a product with this SKU exists, return an error asking to use Match
            if isinstance(existing_product, dict) and 'id' in existing_product:
                return ['SKU already exists in Stoqflow. Use the "Match" button to link this product.']

            # If there was an error during lookup, return it
            if isinstance(existing_product, dict) and 'error' in existing_product:
                return ['Error checking if product exists: ' + existing_product['error']]

            # SKU doesn't exist, safe to create
            result = self.performPost('products', productObj)
            if result['status'] == 'success':
                product.df_product_id_webship = result['data']['_id']
        else:
            # Remove read-only fields before PUT
            for key in ['brand_id', 'sku']:
                productObj.pop(key, None)
            result = self.performPut('products', productObj, product.df_product_id_webship)

            # If the stored Stoqflow id no longer exists (product was deleted
            # in Stoqflow), clear it and retry as a create so the product is
            # re-pushed instead of surfacing the 404.
            if self._is_stoqflow_not_found(result):
                _logger.info(
                    "sync_product: stale df_product_id_webship %s on %s, clearing and re-creating",
                    product.df_product_id_webship, product.default_code or product.name,
                )
                product.df_product_id_webship = False
                return self.sync_product(product)

        self.showDebugInfo(result)

        if result['status'] == 'success':
            return []
        else:
            return ['Error occured: ' + result['errorText'] + ' (url: ' + result.get('url', '?') + ')']

        return errors

    def sync_picking(self, picking):
        """Sync a picking (outbound order or purchase order) to Webship.
        Handles partner/supplier sync, validation, and POST/PUT as needed.

        Returns the list of fatal errors. Soft warnings (e.g. courier not linked)
        are accumulated on self._sync_warnings for the caller to surface."""
        # Tag every HTTP exchange during the sync with this picking so
        # webship.json.history rows come out filtered per picking.
        previous_picking = self._current_picking
        self._current_picking = picking
        # Reset per-call warning bucket so each sync starts clean.
        self._sync_warnings = []
        try:
            return self._sync_picking(picking)
        finally:
            self._current_picking = previous_picking

    def _sync_picking(self, picking):
        if picking.state in ['draft', 'cancel']:
            return ['Draft or cancelled orders cannot by synced']

        if picking.state == 'done':
            return ['Done pickings cannot be synced']

        #if getattr(picking, 'df_is_from_woocommerce', False):
        #    return ['WooCommerce orders cannot be synced']

        if picking.df_object_in_webship == 'Order':
            bDeliveryMode = True
            pickingUrl = self.baseUrl + 'orders'

            # If "match when order sync" is enabled and partner has no Stoqflow client ID,
            # attempt to match the contact to an existing Stoqflow client first
            match_multiple = False
            if hasattr(self, 'env') and not picking.partner_id.df_client_id_webship:
                match_on_sync = self.env['ir.config_parameter'].sudo().get_str(
                    'webship.match_on_order_sync') == 'True'
                if match_on_sync:
                    _logger.info("sync_picking: attempting contact match for partner %s before sync",
                                 picking.partner_id.name)
                    match_result = self.match_partner_by_sequence(picking.partner_id)
                    if match_result.get('errors'):
                        _logger.info("sync_picking: contact match result for %s: %s",
                                     picking.partner_id.name, match_result['errors'])
                    if match_result.get('multiple'):
                        _logger.info("sync_picking: multiple Stoqflow clients found for %s, manual match required",
                                     picking.partner_id.name)
                        match_multiple = True

            clientCode = picking.sale_id.partner_id.df_client_id_webship

            errors = []

            # Several Stoqflow clients match this contact: do NOT fall through to
            # sync_partner, which would create a duplicate client. Block the sync
            # and ask the user to link the correct one manually (the Match button
            # on the contact opens a popup to pick the right client).
            if match_multiple:
                errors.append('Multiple Stoqflow clients match this contact. '
                              'Please link the correct one manually using the Match button on the contact.')
                return errors

            err = []

            fallback_partner = picking.sale_id.partner_id if picking.sale_id else None
            err = self.sync_partner(picking.partner_id, fallback_partner=fallback_partner,
                                    delivery_partner=picking.partner_id)
            _logger.debug("sync_partner errors: %s", err)

            if err:
                if any(e.startswith('Error: ') for e in err):
                    errors.append('Could not sync customer to Stoqflow')
                else:
                    errors.append('Could not fulfill request because of mandatory fields missing on customer')
                errors = errors + err

            self.showDebugInfo('All items in stock: ' + str(picking.products_availability_state))
            self.showDebugInfo('Need stock complete: ' + str(self.get_need_stock_complete_order()))
            self.showDebugInfo(type(self.get_need_stock_complete_order()))
            if picking.products_availability_state != 'available' and str(self.get_need_stock_complete_order()) == 'True':
                errors.append('Not all items are in stock')

            _logger.debug("sync_picking errors so far: %s", errors)

            wsObject = self.build_order_object(picking)

            self.showDebugInfo(wsObject)

            errors = errors + wsObject['errors']

            if errors != []:
                return errors

            sJson = wsObject['webshipObj']

            self.showDebugInfo(sJson)

            # Every line was excluded (products flagged "never send to
            # Stoqflow") or otherwise produced no order item. Do not send an
            # empty order (nor empty an existing one via PUT); surface a warning
            # and treat the picking as handled so it is not retried.
            if not sJson.get('order_items'):
                self._sync_warnings.append('All products excluded, so nothing sent to Stoqflow')
                _logger.info(
                    "sync_picking: picking %s has no order items to send (all excluded); skipping send",
                    picking.name)
                return []

            if picking.df_picking_id_webship == False:
                # Defensive deduplication: a previous POST may have created the
                # order in Stoqflow but the response never reached us (e.g.
                # ReadTimeout), leaving the order on the server but unlinked
                # locally. Look it up by origin.id first to avoid hitting a
                # unique-constraint error from the API on retry.
                existing_id = self._find_existing_order(picking)
                if existing_id:
                    picking.df_picking_id_webship = existing_id
                    _logger.info(
                        "Order for picking %s already exists in Stoqflow (id=%s), linking instead of POST",
                        picking.name, existing_id,
                    )
                    errors = self._safe_status_to_odoo(picking)
                    return errors

                #perform post
                try:
                    sResult = self.performPost('orders', sJson)
                except requests.exceptions.RequestException as e:
                    # The POST may have succeeded server-side despite the
                    # client-side network error (timeout while reading the
                    # response is the common case). Check by origin.id to
                    # recover and link instead of failing.
                    _logger.warning(
                        "POST /orders for picking %s raised %s: %s; checking if the order was created server-side",
                        picking.name, type(e).__name__, e,
                    )
                    recovered_id = self._find_existing_order(picking)
                    if recovered_id:
                        picking.df_picking_id_webship = recovered_id
                        _logger.info(
                            "Recovered: order for picking %s was created in Stoqflow (id=%s) despite client-side error",
                            picking.name, recovered_id,
                        )
                        errors = self._safe_status_to_odoo(picking)
                        return errors
                    errors.append('Error while performing post request: ' + str(e))
                    return errors

                if sResult['status'] == 'error':
                    # A "reference must be unique" (or similar) error means the
                    # order was actually created in Stoqflow by an earlier
                    # attempt and only the local link is missing. Look it up by
                    # origin.id and link it instead of leaving the picking errored.
                    recovered_id = self._find_existing_order(picking)
                    if recovered_id:
                        picking.df_picking_id_webship = recovered_id
                        _logger.info(
                            "Recovered: order for picking %s already existed in Stoqflow "
                            "(id=%s) after POST error %r; linking instead of failing",
                            picking.name, recovered_id, sResult.get('errorText'),
                        )
                        return self._safe_status_to_odoo(picking)
                    errors.append('Error while performing post request: ' + sResult['errorText'] + ' (url: ' + sResult.get('url', '?') + ')')
                else:
                    webshipId = sResult['data']['_id']
                    picking.df_picking_id_webship = webshipId

                    # Persist the ID even if the follow-up status fetch fails:
                    # the order exists in Stoqflow and re-POSTing would create
                    # a duplicate.
                    errors = self._safe_status_to_odoo(picking)

                    return errors

            else:
                #perform put - remove read-only fields
                for key in ['status', 'origin', 'shop_id']:
                    sJson.pop(key, None)

                sResult = self.performPut('orders', sJson, picking.df_picking_id_webship)

                if sResult['status'] == 'error':
                    errors.append('Error while performing put request: ' + sResult['errorText'] + ' (url: ' + sResult.get('url', '?') + ')')
                else:
                    errors = self._safe_status_to_odoo(picking)

                    return errors

        elif picking.df_object_in_webship == 'Purchase order':
            self.showDebugInfo('Purchase order....')

            supplier_partner = picking.purchase_id.partner_id or picking.partner_id

            supplierCode = supplier_partner.df_supplier_id_webship
            if not supplierCode:
                supplierCode = picking.partner_id.df_supplier_id_webship
                if supplierCode:
                    supplier_partner = picking.partner_id

            self.showDebugInfo('Supplier code got: ' + str(supplierCode))
            errors = []

            # If "match when PO sync" is enabled and partner has no Stoqflow supplier ID,
            # attempt to match the partner to an existing Stoqflow supplier first
            if not supplierCode and hasattr(self, 'env'):
                match_on_sync = self.env['ir.config_parameter'].sudo().get_str(
                    'webship.match_on_po_sync') == 'True'
                if match_on_sync:
                    _logger.info("sync_picking: attempting supplier match for partner %s before sync",
                                 supplier_partner.name)
                    match_result = self.match_supplier_by_sequence(supplier_partner)
                    if not match_result.get('errors'):
                        supplierCode = supplier_partner.df_supplier_id_webship
                    else:
                        _logger.info("sync_picking: supplier match result for %s: %s",
                                     supplier_partner.name, match_result['errors'])

            if not supplierCode:
                err = self.sync_supplier(supplier_partner)

                if err:
                    if any(e.startswith('Error: ') for e in err):
                        errors.append('Could not sync supplier to Stoqflow')
                    else:
                        errors.append('Could not fulfill request because of mandatory fields missing on supplier')
                    errors = errors + err

            wsObject = self.build_po_object(picking)

            errors = errors + wsObject['errors']

            if errors != []:
                return errors

            sJson = wsObject['webshipObj']

            # As with orders: if every line was excluded, do not send an empty
            # purchase order - warn and treat the picking as handled.
            if not sJson.get('order_items'):
                self._sync_warnings.append('All products excluded, so nothing sent to Stoqflow')
                _logger.info(
                    "sync_picking: PO picking %s has no order items to send (all excluded); skipping send",
                    picking.name)
                return []

            if picking.df_po_id_webship == False:
                # Deduplication: check if a PO with this supplier_reference already exists
                po_ref = sJson.get('supplier_reference', '')
                if po_ref:
                    existing = self.performGet('purchase-orders', '?supplier_reference=' + quote(po_ref))
                    if existing['status'] == 'success' and len(existing.get('data', [])) > 0:
                        existing_po = existing['data'][0]
                        picking.df_po_id_webship = existing_po['_id']
                        _logger.info("PO already exists in Stoqflow (supplier_reference=%s, id=%s), linking instead of creating", po_ref, existing_po['_id'])
                        errors = self._safe_status_to_odoo(picking)
                        return errors

                try:
                    sResult = self.performPost('purchase-orders', sJson)
                except requests.exceptions.RequestException as e:
                    # See sync_picking 'Order' branch: the POST may have
                    # succeeded server-side despite the client-side error.
                    _logger.warning(
                        "POST /purchase-orders for picking %s raised %s: %s; checking if the PO was created server-side",
                        picking.name, type(e).__name__, e,
                    )
                    if po_ref:
                        try:
                            recovered = self.performGet('purchase-orders', '?supplier_reference=' + quote(po_ref))
                        except Exception as e2:
                            _logger.warning("Recovery lookup for PO %s failed: %s", po_ref, e2)
                            recovered = {'status': 'error'}
                        if recovered.get('status') == 'success' and recovered.get('data'):
                            recovered_po = recovered['data'][0]
                            picking.df_po_id_webship = recovered_po['_id']
                            _logger.info(
                                "Recovered: PO for picking %s was created in Stoqflow (id=%s) despite client-side error",
                                picking.name, recovered_po['_id'],
                            )
                            errors = self._safe_status_to_odoo(picking)
                            return errors
                    errors.append('Error while performing post request: ' + str(e))
                    return errors

                if sResult['status'] == 'error':
                    # Same recovery as the order branch: a supplier_reference
                    # conflict means the PO already exists in Stoqflow and only
                    # the local link is missing - look it up and link it.
                    if po_ref:
                        try:
                            recovered = self.performGet('purchase-orders', '?supplier_reference=' + quote(po_ref))
                        except Exception as e2:
                            _logger.warning("Recovery lookup for PO %s failed: %s", po_ref, e2)
                            recovered = {'status': 'error'}
                        if recovered.get('status') == 'success' and recovered.get('data'):
                            recovered_po = recovered['data'][0]
                            picking.df_po_id_webship = recovered_po['_id']
                            _logger.info(
                                "Recovered: PO for picking %s already existed in Stoqflow "
                                "(id=%s) after POST error %r; linking instead of failing",
                                picking.name, recovered_po['_id'], sResult.get('errorText'),
                            )
                            return self._safe_status_to_odoo(picking)
                    errors.append('Error while performing post request: ' + sResult['errorText'] + ' (url: ' + sResult.get('url', '?') + ')')
                else:
                    webshipPoId = sResult['data']['_id']
                    picking.df_po_id_webship = webshipPoId

                    errors = self._safe_status_to_odoo(picking)

                    return errors
        else:
            errors = ['Cannot determine what type of picking it is']
            return errors

        return errors
    
    def _find_existing_order(self, picking):
        """Look up an existing Stoqflow order matching this picking's origin.id.
        Returns the Stoqflow order ID if found, else None.

        Used to recover from the scenario where a prior POST /orders succeeded
        server-side but the response was not received locally (e.g.,
        ReadTimeout), leaving the order created in Stoqflow but unlinked in
        Odoo. On retry, this avoids re-POSTing and hitting a unique-constraint
        error from the API."""
        origin_id = str(picking.id)
        try:
            # Stoqflow's documented filter is 'origin_id' (underscore). An
            # unknown param (the old 'origin.id') is silently ignored and the
            # whole order collection comes back, so use the real one to get a
            # targeted, server-side filtered result.
            result = self.performGet('orders', '?origin_id=' + quote(origin_id))
        except Exception as e:
            _logger.warning(
                "Lookup for existing Stoqflow order with origin_id=%s failed: %s",
                origin_id, e,
            )
            return None

        if result.get('status') != 'success':
            return None

        for order in (result.get('data') or []):
            # Defensive: confirm the returned order really carries this origin id
            # (response nests it as origin.id) before linking, so an unexpected
            # unfiltered payload can never cause us to link the wrong order.
            order_origin = order.get('origin') or {}
            if str(order_origin.get('id', '')) == origin_id:
                return order.get('_id')

        return None

    def _safe_status_to_odoo(self, picking):
        """Call statusWsToOdoo, swallowing exceptions so they cannot mask a
        successful order/PO creation. The Stoqflow ID is already persisted on
        the picking before this is called; a transient failure here must not
        cause us to re-POST on the next sync attempt."""
        try:
            return self.statusWsToOdoo(picking)
        except Exception as e:
            _logger.exception(
                "Error fetching Stoqflow status after sync for picking %s: %s",
                picking.name, e,
            )
            return ['Error fetching Stoqflow status after sync: ' + str(e)]

    def statusWsToOdoo(self, picking):
        """Fetch the current status of an order/PO from Webship and apply it to the Odoo picking."""
        if picking.df_object_in_webship == 'Order':
            errors = []
            orderUrl = self.baseUrl + 'orders/' + picking.df_picking_id_webship + '?detail=high'

            response = self.session.get(orderUrl, timeout=self.REQUEST_TIMEOUT)

            if response.status_code == 200:
                responseData = response.json()

                # The detail=high payload already carries the human-readable
                # order number, so capture it here instead of issuing a second
                # GET /orders/{id} just to read it (see get_picking_code).
                order_number = responseData.get('order_number')
                if order_number:
                    picking.df_picking_code_webship = order_number

                api_status = responseData['status']
                if api_status in VALID_WEBSHIP_STATUSES:
                    picking.df_status_webship = api_status
                else:
                    _logger.warning(
                        'Unknown Stoqflow status %r for order picking %s, skipping status update',
                        api_status, picking.name,
                    )

                # Map StoqFlow preferred_courier -> Odoo carrier_id.
                # When the courier exists on the Stoqflow order but isn't linked
                # in Odoo, treat it as a soft warning, not a sync failure: the
                # POST/PUT itself succeeded and the order is in Stoqflow.
                preferred_courier = responseData.get('preferred_courier')
                if preferred_courier and hasattr(self, 'env'):
                    fetch_courier_enabled = self.env['ir.config_parameter'].sudo().get_str(
                        'webship.fetch_courier', 'True'
                    )
                    if fetch_courier_enabled and fetch_courier_enabled != 'False':
                        carrier = picking.env['delivery.carrier'].stoqflow_find_delivery_carrier(preferred_courier)
                        if carrier:
                            if picking.carrier_id != carrier:
                                picking.carrier_id = carrier.id
                        else:
                            self._sync_warnings.append(
                                "Courier '%s' present on Stoqflow order but not linked in Odoo" % preferred_courier
                            )
                            _logger.warning(
                                "statusWsToOdoo: courier '%s' not linked in Odoo for picking %s",
                                preferred_courier, picking.name,
                            )

                if 'edited' in responseData:
                    latestChange = responseData['edited']
                else:
                    latestChange = responseData['created']

                date_object = datetime.strptime(latestChange, "%Y-%m-%dT%H:%M:%S.%fZ")

                picking.df_last_changedate_webship = date_object

                if responseData['status'] == 'completed':
                    try:
                        if responseData.get('picks') or responseData.get('order_items'):
                            # Apply the ACTUAL picked quantities from the
                            # payload; setPickingQuantities validates internally
                            # according to the backorder settings. A bare
                            # button_validate() completed every line at its
                            # ordered quantity without looking at the picks.
                            # Its return values are soft warnings - surface
                            # them via _sync_warnings so they never mark the
                            # sync itself as failed.
                            self._sync_warnings.extend(
                                self.setPickingQuantities(picking, responseData))
                        elif picking.state != 'done':
                            # Defensive fallback: a completed payload without
                            # pick detail - keep the previous plain validation.
                            picking._webship_validate()
                    except Exception as e:
                        _logger.exception("Error validating picking %s: %s", picking.name, e)
                        return ['Error while setting state to done on picking order: ' + str(e)]

                return errors
            else:
                errors.append(response.text)
                return errors
        elif picking.df_object_in_webship == 'Purchase order':
            errors = []
            orderUrl = self.baseUrl + 'purchase-orders/' + picking.df_po_id_webship + '?detail=high'

            response = self.session.get(orderUrl, timeout=self.REQUEST_TIMEOUT)

            if response.status_code == 200:
                responseData = response.json()

                # The detail=high payload already carries the human-readable PO
                # number, so capture it here instead of issuing a second
                # GET /purchase-orders/{id} just to read it (see get_po_code).
                order_number = responseData.get('order_number')
                if order_number:
                    picking.df_po_code_webship = order_number

                api_status = responseData['status']
                if api_status in VALID_WEBSHIP_STATUSES:
                    picking.df_status_webship = api_status
                else:
                    _logger.warning(
                        'Unknown Stoqflow status %r for PO picking %s, skipping status update',
                        api_status, picking.name,
                    )

                if 'edited' in responseData:
                    latestChange = responseData['edited']
                else:
                    latestChange = responseData['created']

                date_object = datetime.strptime(latestChange, "%Y-%m-%dT%H:%M:%S.%fZ")

                picking.df_last_changedate_webship = date_object

                if responseData['status'] == 'completed':
                    if responseData.get('picks') or responseData.get('order_items'):
                        # Apply the ACTUAL received quantities from the payload;
                        # setPickingQuantities validates internally according to
                        # the backorder settings. A bare button_validate()
                        # completed every line at its ordered quantity. Its
                        # return values are soft warnings - surface them via
                        # _sync_warnings so they never mark the sync as failed.
                        self._sync_warnings.extend(
                            self.setPickingQuantities(picking, responseData))
                    elif picking.state != 'done':
                        picking._webship_validate()

                return errors
            else:
                errors.append(response.text)
                return errors
    

    # ------------------------------------------------------------------
    # Legacy / bulk sync helpers
    # ------------------------------------------------------------------

    def sync_prod(self, prodInfo):
        """Legacy product sync: create or update a product in Webship (uses direct auth)."""
        produrl = self.baseUrl + 'products'

        _logger.debug("sync_prod URL: %s", produrl)

        sWJson = {'brand_id': self.get_brand(), 'type': 'basic', 'name': prodInfo.name, 'sku': prodInfo.default_code,
                  'description': prodInfo.description, 'barcodes': [{'type': 'ean13', 'code': prodInfo.default_code}],
                  'price': prodInfo.standard_price, 'retail_price': prodInfo.list_price, 'stock_type': prodInfo.stockType}

        if sWJson['stock_type'] == False:
            sWJson.pop('stock_type')

        if prodInfo.barcode == False:
            sWJson.pop('barcodes')

        if prodInfo.product_id_webship == False:
            time.sleep(self.sleepTime)
            _logger.debug("sync_prod POST payload: %s", sWJson)
            response = self.session.post(produrl, json=sWJson, timeout=self.REQUEST_TIMEOUT)

            if response.status_code != 200:
                _logger.error('sync_prod POST failed with status code %s: %s', response.status_code, response.text)
                exit(0)
            else:
                responseData = response.json()
                _logger.debug("sync_prod POST response: %s", responseData)
                id = responseData['_id']

                prodInfo.write({'product_id_webship':id})
        else:
            time.sleep(self.sleepTime)
            _logger.debug("sync_prod PUT payload: %s, URL: %s", sWJson, produrl)
            response = self.session.put(produrl + '/' + prodInfo.product_id_webship, json=sWJson, timeout=self.REQUEST_TIMEOUT)

            if response.status_code != 200:
                _logger.error('sync_prod PUT failed with status code %s: %s', response.status_code, response.text)


    def sync_sup(self, supInfo):
        """Legacy supplier sync: create/update both supplier and client records in Webship."""
        sup_url = self.baseUrl + 'suppliers'
        client_url = self.baseUrl + 'clients'

        sWJson = {'name': supInfo.name, 'contact': supInfo.name, 'email': supInfo.email,
                           'address': {'address_1':supInfo.street, 'city':supInfo.city,
                                       'postal_code':supInfo.zip, 'country' : supInfo.country_code}}

        if supInfo.street == False or supInfo.city == False or supInfo.zip == False or supInfo.country_code == False:
            return

        if sWJson['email'] == False:
            sWJson.pop('email')

        if sWJson['address']['country'] == False:
            sWJson['address'].pop('country')

        if sWJson['address']['postal_code'] == False:
            sWJson['address'].pop('postal_code')

        if sWJson['address']['city'] == False:
            sWJson['address'].pop('city')

        if sWJson['address']['address_1'] == False:
            sWJson['address'].pop('address_1')

        if supInfo.supplier_id_webship == False:
            time.sleep(self.sleepTime)
            _logger.debug("sync_sup POST supplier payload: %s", sWJson)
            response = self.session.post(sup_url, json=sWJson, timeout=self.REQUEST_TIMEOUT)

            if response.status_code != 200:
                _logger.error('sync_sup POST supplier failed with status code %s: %s', response.status_code, response.text)
                exit(0)
            else:
                responseData = response.json()
                _logger.debug("sync_sup POST supplier response: %s", responseData)
                id = responseData['_id']

                supInfo.write({'supplier_id_webship':id})
        else:
            time.sleep(self.sleepTime)
            _logger.debug("sync_sup PUT supplier payload: %s", sWJson)
            response = self.session.put(sup_url + '/' + supInfo.supplier_id_webship, json=sWJson, timeout=self.REQUEST_TIMEOUT)

            if response.status_code != 200:
                _logger.error('sync_sup PUT supplier failed with status code %s: %s', response.status_code, response.text)
                exit(0)

        if supInfo.client_id_webship == False:
            time.sleep(self.sleepTime)
            addressInfo = sWJson['address']

            sWJson.pop('address')
            sWJson['addresses'] = {}
            sWJson['addresses']['billing'] = addressInfo
            sWJson['addresses']['shipping'] = addressInfo
            _logger.debug("sync_sup POST client payload: %s", sWJson)
            response = self.session.post(client_url, json=sWJson, timeout=self.REQUEST_TIMEOUT)

            if response.status_code != 200:
                _logger.error('sync_sup POST client failed with status code %s: %s', response.status_code, response.text)
                exit(0)
            else:
                responseData = response.json()
                _logger.debug("sync_sup POST client response: %s", responseData)
                id = responseData['_id']

                supInfo.write({'client_id_webship':id})
        else:
            time.sleep(self.sleepTime)
            _logger.debug("sync_sup PUT client payload: %s", sWJson)
            response = self.session.put(client_url + '/' + supInfo.client_id_webship, json=sWJson,
                                    timeout=self.REQUEST_TIMEOUT)

            if response.status_code != 200:
                _logger.error('sync_sup PUT client failed with status code %s: %s', response.status_code, response.text)
                exit(0)





        #print(supInfo.supplier_id_webship)

        #print(supInfo.client_id_webship)


    # ------------------------------------------------------------------
    # Destructive helpers (development / testing only)
    # ------------------------------------------------------------------

    def emptyOrders(self):
        """Delete all orders from Webship. USE WITH CAUTION."""
        url = self.baseUrl + 'orders'

        time.sleep(self.sleepTime)
        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        if response.status_code != 200:
            _logger.error('emptyOrders failed with status code %s: %s', response.status_code, response.text)
            exit(0)
        else:
            for item in response.json():
                deleteUrl = self.baseUrl + 'orders/' + item['_id']
                time.sleep(self.sleepTime)
                response = requests.delete(deleteUrl, auth=(self.ws_login, self.ws_password))

    def emptyProducts(self):
        """Delete all products from Webship. USE WITH CAUTION."""
        time.sleep(self.sleepTime)
        url = self.baseUrl + 'products'

        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        if response.status_code != 200:
            _logger.error('emptyProducts failed with status code %s: %s', response.status_code, response.text)
            exit(0)
        else:
            for item in response.json():
                deleteUrl = self.baseUrl + 'products/' + item['_id']
                time.sleep(self.sleepTime)
                response = requests.delete(deleteUrl, auth=(self.ws_login, self.ws_password))

    def emptyClients(self):
        """Delete all clients from Webship. USE WITH CAUTION."""
        url = self.baseUrl + 'clients'

        time.sleep(self.sleepTime)
        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        if response.status_code != 200:
            _logger.error('emptyClients failed with status code %s: %s', response.status_code, response.text)
            exit(0)
        else:
            for item in response.json():
                deleteUrl = self.baseUrl + 'clients/' + item['_id']
                time.sleep(self.sleepTime)
                response = requests.delete(deleteUrl, auth=(self.ws_login, self.ws_password))

    def emptySuppliers(self):
        """Delete all suppliers from Webship. USE WITH CAUTION."""
        url = self.baseUrl + 'suppliers'

        time.sleep(self.sleepTime)
        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)

        if response.status_code != 200:
            _logger.error('emptySuppliers failed with status code %s: %s', response.status_code, response.text)
            exit(0)
        else:
            for item in response.json():
                deleteUrl = self.baseUrl + 'suppliers/' + item['_id']
                time.sleep(1)
                response = requests.delete(deleteUrl, auth=(self.ws_login, self.ws_password))

    def updateProduct(self, velden):
        """Legacy: insert or update a single product using a raw field dict."""
        url = self.baseUrl + 'products'

        sWJson = {'brand_id': self.get_brand(), 'type': 'basic', 'name': velden['name'],
                  'sku': velden['default_code']}

        if velden['product_id_webship'] == False:
            _logger.info('Inserting product...')
            time.sleep(1)
            response = self.session.post(url, json=sWJson, timeout=self.REQUEST_TIMEOUT)

            if response.status_code == 403:
                _logger.warning('SKU non-unique for product %s', velden.get('default_code'))
            elif response.status_code != 200:
                _logger.error('updateProduct POST failed with status code %s: %s', response.status_code, response.text)
                exit(0)
            else:
                responseData = response.json()
                _logger.debug("updateProduct response: %s, id: %s", responseData, responseData['_id'])

                #self.odooDb.updateRecord('product.product', velden['id'], {'product_id_webship': responseData['_id']})
        else:
            _logger.info('Updating product...')
            time.sleep(1)
            response = self.session.put(url + '/' + str(velden['product_id_webship']), json=sWJson,
                                    timeout=self.REQUEST_TIMEOUT)

            if response.status_code != 200:
                _logger.error('updateProduct PUT failed with status code %s: %s', response.status_code, response.text)
                exit(0)

    # ------------------------------------------------------------------
    # Export / import helpers
    # ------------------------------------------------------------------

    def exportSups(self):
        """Export all suppliers from Webship as a JSON list."""
        response = self.session.get(self.baseUrl + 'suppliers', timeout=self.REQUEST_TIMEOUT)

        if response.status_code != 200:
            _logger.error('exportSups failed with status code %s: %s', response.status_code, response.text)
            exit(0)

        return response.json()

    def showDebugInfo(self, sstr):
        """Log debug information (replaces former print statements).

        Always emitted to the server log. When 'Verbose logging' is enabled the
        message is also stored as a 'trace' row in webship.json.history, tagged
        with the current picking, so the full component trace (interleaved with
        the HTTP payload rows) can be exported from the UI and shared."""
        _logger.info(str(sstr))
        if not hasattr(self, 'env'):
            return
        try:
            if not self._verbose_enabled():
                return
            self.env['webship.json.history'].sudo().create({
                'picking_id': self._current_picking.id if self._current_picking else False,
                'direction': 'trace',
                'method': 'TRACE',
                'endpoint': '',
                'json_payload': str(sstr),
            })
        except Exception:
            # Never let verbose tracing break a real operation.
            _logger.exception("Failed to record Stoqflow verbose trace")

    def _debug_dump(self, records, fields=None, label=''):
        """Verbose-trace a compact read() of records.

        Unlike showDebugInfo(records.read()) - whose read() argument is
        evaluated eagerly on every call - the read here only happens after the
        verbose check, so it can never cost anything (or raise AccessError)
        in normal operation. Only the given field subset is read, and any
        failure (an AccessError on a restricted field first and foremost)
        degrades to id/display_name instead of raising: debug output must
        never decide whether a sync may run."""
        if not self._verbose_enabled():
            return
        try:
            data = records.read(fields) if fields else records.read()
        except Exception:
            try:
                data = [{'id': r.id, 'display_name': r.display_name}
                        for r in records]
            except Exception:
                data = str(records)
        self.showDebugInfo(('%s: ' % label if label else '') + str(data))

    def exportClients(self):
        """Export all clients from Webship, paginating through 50-record pages."""
        output = []
        i = 50
        page = 1

        while True:
            self.sleep()

            response = self.session.get(self.baseUrl + 'clients?page=' + str(page), timeout=self.REQUEST_TIMEOUT)

            totalCount = response.headers.get('total-count')

            #print(response.json())

            if response.status_code != 200:
                _logger.error('exportClients failed with status code %s: %s', response.status_code, response.text)
                exit(0)

            for c in response.json():
                output.append(c)

            #print (i)
            #print (totalCount)

            if i > int(totalCount):
                break

            i = i + 50
            page = page + 1

        return output

    def _resolve_stock_location(self, company_id, locations):
        """Return the Stoqflow location that holds the stock of Stoqflow
        company ``company_id``, or an empty recordset when it can't be told.

        A location linked to the company id (Stoqflow company ID on the
        location form) wins. Without such a link the only Stoqflow location is
        used; when there are several, nothing is guessed: picking the first
        one wrote stock into an unrelated location (and company)."""
        if company_id:
            match = locations.filtered(lambda l: l.df_warehouse_id_webship == company_id)
            if match:
                return match[:1]
        if len(locations) == 1:
            return locations
        return locations.browse()

    def importStock(self):
        """Import inventory levels from Webship and write them to Odoo stock quants
        at locations flagged as Webship locations.

        Stoqflow reports one figure per product. When the product has several
        quants at the location (lots, packages) every quant shows that same
        product figure, and the stock is never adjusted automatically: how it
        splits over the lots is unknown.

        Returns a summary dict (also logged), or False when the API call failed."""
        adjust_odoo_stock = self.env['ir.config_parameter'].sudo().get_str(
            'webship.adjust_odoo_stock', 'False') == 'True'

        result = self.fetchInventory()

        if result.get("status") != "success":
            _logger.error("importStock: fetching the Stoqflow inventory failed: %s",
                          result.get('txt') or result)
            return False

        inventory_data = result.get("data", {})
        now = fields.Datetime.now()

        StockQuant = self.env["stock.quant"]
        Product = self.env["product.product"]
        locations = self.env["stock.location"].search([
            ("df_is_webship_location", "=", True),
            ("usage", "=", "internal"),
        ])
        summary = {
            'updated': 0,
            'created': 0,
            'adjusted': 0,
            'locations': set(),
            'unknown_skus': [],
            'unmatched_companies': set(),
            'multi_quant_skus': [],
            'missing_reserved': False,
            'errors': [],
        }

        # Kit products (phantom BoM) can never carry a stock.quant: mrp's
        # _check_kits constraint forbids it, and one kit in the Stoqflow
        # inventory would abort the whole import. The Stoqflow-side "composed"
        # check below does not cover them (a kit can be a plain basic product
        # in Stoqflow) and is_storable does not either (kits are storable
        # products with a phantom BoM). Resolve the kit ids once up front -
        # only when mrp is installed; this module does not depend on it.
        kit_product_ids = set()
        kit_template_ids = set()
        if 'mrp.bom' in self.env:
            phantom_boms = self.env['mrp.bom'].sudo().search([('type', '=', 'phantom')])
            kit_product_ids = set(phantom_boms.product_id.ids)
            kit_template_ids = set(
                phantom_boms.filtered(lambda b: not b.product_id).product_tmpl_id.ids)

        # fetchAll returns paginated data: {page_nr: page_json, ...}
        # Each page is a list of inventory items.
        for page in inventory_data.values():
            for item in page:
                sku = item.get("sku")
                if not sku:
                    continue

                # Skip composed products — only basic products carry physical stock
                if item.get("type") == "composed":
                    continue

                company_id = item.get("company_id")

                # Find product by SKU
                product = Product.search(
                    [("default_code", "=", sku)],
                    limit=1
                )
                if not product:
                    summary['unknown_skus'].append(sku)
                    continue

                if (product.id in kit_product_ids
                        or product.product_tmpl_id.id in kit_template_ids):
                    _logger.info(
                        "importStock: skipping kit product %s (phantom BoM) - "
                        "quants cannot be created for kits", sku)
                    continue

                if "reserved" not in item:
                    summary['missing_reserved'] = True
                total = item.get("total", 0.0)
                reserved = item.get("reserved", 0.0)
                available = item.get("available", total - reserved)

                webship_location = self._resolve_stock_location(company_id, locations)
                if not webship_location:
                    summary['unmatched_companies'].add(company_id or '(none)')
                    continue

                # One bad product (a kit the guard missed, a constraint
                # violation, an apply failure) must not abort the whole
                # import: roll back that item's writes and continue. The
                # savepoint keeps the cursor usable after SQL-level errors.
                try:
                    with self.env.cr.savepoint():
                        quants = StockQuant.search([
                            ("product_id", "=", product.id),
                            ("location_id", "=", webship_location.id),
                        ])

                        if not quants:
                            # Nothing to compare against: only create a quant
                            # when Stoqflow actually holds stock. Only storable
                            # products can carry a stock.quant line.
                            # (Odoo 19 no longer uses type == 'product'; use is_storable.)
                            if not total or not product.is_storable:
                                continue
                            quants = StockQuant.create({
                                "product_id": product.id,
                                "location_id": webship_location.id,
                                "quantity": 0.0,
                            })
                            summary['created'] += 1

                        quants.write({
                            "df_webship_totalstock": total,
                            "df_webship_reserved": reserved,
                            "df_webship_available_stock": available,
                            "df_last_check_webship": now,
                        })
                        summary['updated'] += 1
                        summary['locations'].add(webship_location.complete_name)
                        if len(quants) > 1:
                            summary['multi_quant_skus'].append(sku)

                        if adjust_odoo_stock and len(quants) == 1:
                            quants.inventory_quantity = total
                            quants._apply_inventory()
                            summary['adjusted'] += 1
                except Exception as e:
                    _logger.exception(
                        "importStock: failed to apply stock for SKU %s; "
                        "continuing with the next item", sku)
                    summary['errors'].append('%s: %s' % (sku, e))
                    continue

        _logger.info(
            "importStock: %d products updated (%d new quants, %d adjusted) at %s; "
            "unknown SKUs: %s; unmatched Stoqflow companies: %s; "
            "products with several quants (not adjusted): %s; "
            "reserved missing in payload: %s; errors: %s",
            summary['updated'], summary['created'], summary['adjusted'],
            ', '.join(sorted(summary['locations'])) or '-',
            ', '.join(summary['unknown_skus']) or '-',
            ', '.join(sorted(summary['unmatched_companies'])) or '-',
            ', '.join(summary['multi_quant_skus']) or '-',
            summary['missing_reserved'], '; '.join(summary['errors']) or '-')
        return summary
