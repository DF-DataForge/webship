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

from odoo import fields

from odoo.exceptions import UserError
from odoo.fields import Datetime

_logger = logging.getLogger(__name__)


class WebShipHandler:
    """Central handler for all Webship API communication.
    Manages authentication, CRUD operations, and data synchronization."""
    REQUEST_TIMEOUT = (10, 30)  # (connect, read) timeout in seconds

    def __init__(self, ws_login, ws_password, ws_base_url):
        """Initialize the handler with Webship API credentials and base URL."""
        self.ws_login = ws_login
        self.ws_password = ws_password
        self.baseUrl = ws_base_url
        self.sleepTime = 0.5  # Rate-limit delay between API calls (seconds)
        self.headers = {'x-addon-public-key':'kRTxA08bKieVQroS'}
        self.auth = HTTPBasicAuth(ws_login, ws_password)

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

    def set_env(self, env):
        """Inject the Odoo environment so the handler can access ORM models."""
        self.env = env

    def _log_json(self, picking, direction, method, endpoint, payload):
        """Log a JSON payload to webship.json.history if logging is enabled."""
        if not hasattr(self, 'env'):
            return
        log_enabled = self.env['ir.config_parameter'].sudo().get_param('webship.log_json')
        if log_enabled != 'True':
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

    def removeFalseVals(self, sDict):
        """Strip keys with False or None values from a dict before sending to the API."""
        filtered_data = {k: v for k, v in sDict.items() if v is not False and v is not None}

        return filtered_data

    def _truncate(self, value, max_len):
        """Truncate a string value to max_len characters if needed."""
        if value and isinstance(value, str) and len(value) > max_len:
            return value[:max_len]
        return value

    def _parse_error_response(self, response):
        """Parse an API error response, extracting field-level details from 400 errors."""
        error_text = response.text
        if response.status_code == 400:
            try:
                error_data = response.json()
                if isinstance(error_data, list):
                    error_text = '; '.join(
                        f"{e.get('field', '?')}: {e.get('message', str(e))}"
                        for e in error_data
                    )
                elif isinstance(error_data, dict) and 'errors' in error_data:
                    error_text = '; '.join(
                        f"{e.get('field', '?')}: {e.get('message', str(e))}"
                        for e in error_data['errors']
                    )
            except (ValueError, TypeError):
                pass
        return error_text

    def get_brand(self):
        """Return the first configured Webship brand ID."""
        return self.env['webship.brand'].search([], limit=1)[0].brand_id

    def get_default_shop(self):
        """Return the default Webship shop ID, falling back to the first available shop."""
        defaultShop = self.env['ir.config_parameter'].sudo().get_param('webship.default_shop')

        sh = self.env['webship.shop'].sudo().search([('shop_id', '=', defaultShop)], limit=1)
        if len(sh) > 0 and sh[0].shop_id != False:
            return sh[0].shop_id

        shops = self.env['webship.shop'].search([], limit=1)
        if len(shops) == 0:
            raise UserError("No shops present. Please load shops.")
            return None
        else:
            return shops[0].shop_id

    def get_default_status(self):
        """Return the configured default status for outbound orders."""
        wObj = self.env['ir.config_parameter'].sudo().get_param('webship.default_status_order')
        return wObj

    def get_default_po_status(self):
        """Return the configured default status for purchase orders."""
        wObj = self.env['ir.config_parameter'].sudo().get_param('webship.default_status_po_order')
        return wObj

    def get_need_stock_complete_order(self):
        """Return whether orders require full stock availability before syncing."""
        wObj = self.env['ir.config_parameter'].sudo().get_param('webship.default_order_available_condition')
        return wObj

    def get_default_auto_create_backorder(self):
        """Return whether backorders should be auto-created on partial fulfillment."""
        wObj = self.env['ir.config_parameter'].sudo().get_param('webship.auto_create_backorder')
        return wObj

    def test(self):
        """Test the API connection and return a (status, message) tuple."""
        response = self.session.get(self.baseUrl + 'products', timeout=self.REQUEST_TIMEOUT)

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

        url = self.baseUrl + 'clients?vat=' + vatNr

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

        url = self.baseUrl + 'suppliers?vat=' + vatNr

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
            if hasattr(p.product_id, "packaging_ids") and p.product_id.packaging_ids:
                for i in p.product_id.packaging_ids:
                    if i.df_sku_webship != False:
                        skus.append(i.df_sku_webship)

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

        # Store Webship product IDs on packaging records for quantity resolution
        for p in picking.move_ids:
            if hasattr(p.product_id, "packaging_ids") and p.product_id.packaging_ids:
                for pkg in p.product_id.packaging_ids:
                    if pkg.df_sku_webship and pkg.df_sku_webship in items:
                        pkg.df_product_id_webship = items[pkg.df_sku_webship]
                        _logger.info(
                            "findProductsBySku: stored Webship ID %s on packaging '%s' (SKU: %s) of product %s",
                            items[pkg.df_sku_webship], pkg.name, pkg.df_sku_webship, p.product_id.default_code
                        )

        return {'items': items}

    # ------------------------------------------------------------------
    # Partner / supplier sync methods
    # ------------------------------------------------------------------

    def match_partner(self, partner):
        """Match an Odoo partner to a Webship client by email address.
        Requires exactly one match to succeed, returns error if zero or multiple found."""
        if partner.email == False:
            return ['No e-mail address specified']

        sReq = self.performGet('clients', "?email=" + partner.email)

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

        return ['Error searching for client: ' + sReq.get('errorText', 'Unknown error')]

    def _match_client_by_vat(self, partner):
        """Try to match a partner to a Stoqflow client by VAT number.
        Returns (matched: bool, errors: list, data: list or None).
        When multiple matches are found, data contains the Stoqflow client dicts."""
        if not partner.vat:
            return False, ['No VAT number specified on the contact'], None

        sReq = self.performGet('clients', "?vat=" + partner.vat)

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
        return False, ['Error searching for client by VAT: ' + sReq.get('errorText', 'Unknown error')], None

    def _match_client_by_email(self, partner):
        """Try to match a partner to a Stoqflow client by e-mail address.
        Returns (matched: bool, errors: list, data: list or None).
        When multiple matches are found, data contains the Stoqflow client dicts."""
        if not partner.email:
            return False, ['No e-mail address specified on the contact'], None

        sReq = self.performGet('clients', "?email=" + partner.email)

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
        return False, ['Error searching for client by e-mail: ' + sReq.get('errorText', 'Unknown error')], None

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

        sequence = self.env['ir.config_parameter'].sudo().get_param(
            'webship.contact_match_sequence', 'email_only')

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

        sReq = self.performGet('suppliers', "?email=" + partner.email)

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

        if errors != []:
            return errors

        sSupplierNumber = f"SO{partner.id:07d}"

        sObject = {'name':partner.name, 'supplier_number':sSupplierNumber, 'email':partner.email, 'phone':partner.phone, 'vat':partner.vat,
                   'address':
                       {'address_1': partner.street, 'city': partner.city, 'postal_code': partner.zip, 'country': partner.country_code}
                   }

        for key, value in list(sObject.items()):
            if value is False or value == '\'false\'' or value == '':
                del sObject[key]

        if partner.df_supplier_id_webship == False:
            # Before creating, check if this email already exists in Webship
            if partner.email and partner.email != '':
                existing = self.performGet('suppliers', "?email=" + partner.email)
                if existing['status'] == 'success' and len(existing.get('data', [])) > 0:
                    return ['Email already exists in Stoqflow. Use the "Match" button to link this supplier.']

            del sObject['supplier_number']
            sRes = self.performPost('suppliers', sObject)
            if sRes['status'] == 'success':
                partner.df_supplier_id_webship = sRes['data']['_id']
        else:
            sRes = self.performPut('suppliers', sObject, partner.df_supplier_id_webship)

        if sRes['status'] == 'error':
            return ['Error while creating supplier: ' + sRes['errorText']]

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
            return {'status': 'error', 'errorCode':response.status_code, 'errorText':self._parse_error_response(response)}
        else:
            responseData = response.json()
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
            return {'status': 'error', 'errorCode':response.status_code, 'errorText':self._parse_error_response(response)}
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
            return {'status': 'error', 'errorCode':response.status_code, 'errorText':self._parse_error_response(response)}
        else:
            responseData = response.json()
            return {'status':'success', 'data':responseData}

    def sync_partner(self, partner):
        """Create or update a client in Webship from an Odoo partner.
        Uses billing address and, if present, a child delivery address.
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

        deliveryAdress = partner.env['res.partner'].sudo().search([('type', '=', 'delivery'),('parent_id','=',partner.id)])

        self.showDebugInfo(deliveryAdress.read())

        if deliveryAdress.id != False:
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
            sJson = {'name':generalName, 'contact':contactName, 'email':partner.email, 'phone':partner.phone, 'mobile':getattr(partner, 'mobile', None), 'vat':partner.vat, 'addresses': {'billing':{'address_1':partner.street, 'city':partner.city, 'postal_code':partner.zip, 'country':sCountryCode}}}

            sClientNumber = f"CO{partner.id:07d}"

            sJson['client_number'] = sClientNumber

            if deliveryAdress.id != False:
                sJson['addresses']['shipping'] = shippingAdress

            for key, value in list(sJson.items()):
                if value is False or value == '\'false\'' or value == '':
                    del sJson[key]

            if partner.df_client_id_webship == False:
                # Before creating, check if this email already exists in Webship
                if partner.email and partner.email != '':
                    existing = self.performGet('clients', "?email=" + partner.email)
                    if existing['status'] == 'success' and len(existing.get('data', [])) > 0:
                        return ['Email already exists in Stoqflow. Use the "Match" button to link this client.']

                result = self.performPost('clients', sJson)
                if result['status'] == 'success':
                    partner.df_client_id_webship = result['data']['_id']
            else:
                result = self.performPut('clients', sJson, partner.df_client_id_webship)

            if result['status'] == 'success':
                return []
            else:
                return ['Error: ' + result['errorText']]
        else:
            return errors

    # ------------------------------------------------------------------
    # Picking / order building and sync
    # ------------------------------------------------------------------

    def is_integer_float(self, value):
        """Check whether a float value is effectively a whole number."""
        return value % 1 == 0

    def picking_get_line_items(self, picking):
        """Extract line items from a picking, splitting by packaging SKUs when applicable."""
        output = []
        self._skipped_products = []
        _logger.debug("picking_get_line_items picking: %s", picking)
        for i in picking.move_ids:
            _logger.debug("Processing move product: %s", i.product_id.default_code)
            if i.product_id.df_product_do_not_send_webship == True:
                continue
            if i.product_id.default_code == False:
                self._skipped_products.append(i.product_id.name)
                _logger.warning("Skipping product '%s' (id=%s): no default_code (SKU) set", i.product_id.name, i.product_id.id)
                continue
            sOutput = {'productObj': i.product_id, 'type':i.product_id.type, 'default_code':i.product_id.default_code, 'product_id':i.product_id.id, 'quantity':i.product_uom_qty}

            divs = []
            sorted_skuList = []
            if hasattr(i.product_id, "packaging_ids") and i.product_id.packaging_ids:
                for j in i.product_id.packaging_ids:
                    if j.df_sku_webship != False and j.qty>0.0:
                        divs.append({'naam':j.name, 'Qty':j.qty, 'Sku':j.df_sku_webship})

            if divs != []:
                divs.append({'naam':'Hoofdproduct', 'Qty':1, 'Sku':i.product_id.default_code})

                sorted_skuList = sorted(divs, key=lambda d: list(d.values())[1], reverse=True)

                iterQ = i.product_uom_qty

                for z in sorted_skuList:
                    quotient, remainder = divmod(iterQ, z['Qty'])
                    z['OrderQty'] = quotient
                    iterQ = remainder

            sOutput['divides'] = sorted_skuList

            _logger.debug('Divides: %s', sOutput)

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
                                # pickingId.state = 'done'

                                self.setPickingQuantities(pickingId, po_order)

                                pickingId.button_validate()
                                _logger.info('Validate pressed for picking %s', pickingId.name)
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

    def setPickingQuantities(self, sPicking, order):
        """Apply picked/received quantities from a Webship order onto an Odoo picking.
        Handles move lines first, then falls back to moves for any remainder."""
        self.showDebugInfo('In picking quantites')
        warnings = []

        _logger.debug('Picking got: %s', sPicking.read())
        _logger.debug('Order got: %s', order)

        self.showDebugInfo(sPicking.read())

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

        if order.get('status') == 'completed':
            # ------------------------------------------------------------
            # Reset quantities first
            # ------------------------------------------------------------
            for m in sPicking.move_ids.filtered(lambda m: m.state not in ('cancel', 'done')):
                self.showDebugInfo('Reading move: ' + str(m.read()))
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

                # Ensure packaging records have their Webship product IDs
                if hasattr(m.product_id, 'packaging_ids') and m.product_id.packaging_ids:
                    for pkg in m.product_id.packaging_ids:
                        if pkg.df_sku_webship and not pkg.df_product_id_webship:
                            pkgId = self.findProductBySku(pkg.df_sku_webship)
                            if isinstance(pkgId, dict) and 'id' in pkgId:
                                pkg.df_product_id_webship = pkgId['id']
                                _logger.info(
                                    "setPickingQuantities: resolved packaging SKU %s -> Webship ID %s",
                                    pkg.df_sku_webship, pkgId['id']
                                )
                            else:
                                _logger.warning(
                                    "setPickingQuantities: could not resolve packaging SKU %s for product %s: %s",
                                    pkg.df_sku_webship, m.product_id.default_code, pkgId
                                )
                m.write({'quantity': 0.0})

            for pl in sPicking.move_line_ids.filtered(lambda pl: pl.state not in ('cancel', 'done')):
                self.showDebugInfo('Reading picking line: ' + str(pl.read()))
                self.showDebugInfo('Setting quantity for line: ' + str(pl.product_id.name))
                pl.write({'quantity': 0.0, 'quantity_product_uom': 0.0})

            # ------------------------------------------------------------
            # Build pMap (webship_product_id -> total_qty)
            # and batchMap (webship_product_id -> batch/lot)
            # ------------------------------------------------------------
            pMap = {}
            batchMap = {}

            # Normal outbound orders: use "picks"
            # Use parent_product_id when present (pick substitution via packaging/build order),
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

            # ------------------------------------------------------------
            # Resolve packaging Webship IDs → base product quantities
            # e.g. 4 boxes (ornpHrRxnHGTqkuYS, pkg qty 12) → 48 individual units
            # merged into the main product's pMap entry.
            # ------------------------------------------------------------
            packaging_map = {}  # packaging webship_pid -> (main product webship_pid, packaging qty, odoo product id)
            # Include ALL moves (even done/cancel) so the lookup table is
            # complete – this is read-only and does not modify any records.
            for m in sPicking.move_ids:
                if hasattr(m.product_id, 'packaging_ids') and m.product_id.packaging_ids:
                    for pkg in m.product_id.packaging_ids:
                        if pkg.df_product_id_webship:
                            packaging_map[pkg.df_product_id_webship] = (
                                m.product_id.df_product_id_webship,
                                pkg.qty if pkg.qty > 0 else 1,
                                m.product_id.id
                            )
            _logger.info(
                "setPickingQuantities: packaging_map built with %d entries from %d moves",
                len(packaging_map), len(sPicking.move_ids),
            )

            for ws_pid in list(pMap.keys()):
                if ws_pid in packaging_map:
                    main_ws_pid, pkg_qty, odoo_pid = packaging_map[ws_pid]
                    converted_qty = pMap[ws_pid] * pkg_qty
                    if main_ws_pid:
                        _logger.info(
                            "setPickingQuantities: packaging conversion - %s x '%s' (pkg qty %s) -> %s units of '%s'",
                            pMap[ws_pid], ws_pid, pkg_qty, converted_qty, main_ws_pid
                        )
                        if main_ws_pid in pMap:
                            pMap[main_ws_pid] += converted_qty
                        else:
                            pMap[main_ws_pid] = converted_qty
                        del pMap[ws_pid]
                    else:
                        # Product has no Stoqflow ID - convert qty in place, match via packaging later
                        _logger.info(
                            "setPickingQuantities: packaging qty conversion (no product Stoqflow ID) - %s x '%s' (pkg qty %s) -> %s units for Odoo product %s",
                            pMap[ws_pid], ws_pid, pkg_qty, converted_qty, odoo_pid
                        )
                        pMap[ws_pid] = converted_qty

            self.showDebugInfo('pMap after packaging resolution: ' + str(pMap))

            # ------------------------------------------------------------
            # 1) Allocate quantities across MOVE LINES (best practice)
            # ------------------------------------------------------------
            for webship_pid, total_qty in list(pMap.items()):

                # Only not done/cancel lines for this product
                # Match by product Stoqflow ID, or by packaging Stoqflow ID (fallback)
                _pkg_odoo_pid = packaging_map[webship_pid][2] if webship_pid in packaging_map else None
                lines = sPicking.move_line_ids.filtered(lambda l:
                                                        l.state not in ('cancel', 'done')
                                                        and (l.product_id.df_product_id_webship == webship_pid
                                                             or (_pkg_odoo_pid and l.product_id.id == _pkg_odoo_pid))
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

                _pkg_odoo_pid = packaging_map[webship_pid][2] if webship_pid in packaging_map else None
                moves = sPicking.move_ids.filtered(lambda m:
                                                   m.state not in ('cancel', 'done')
                                                   and (m.product_id.df_product_id_webship == webship_pid
                                                        or (_pkg_odoo_pid and m.product_id.id == _pkg_odoo_pid))
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

            # Report any Webship product IDs that could not be matched to Odoo moves
            if pMap:
                for webship_pid, remaining_qty in pMap.items():
                    # Check if the product exists on done/cancel moves (already processed)
                    _pkg_odoo_pid = packaging_map[webship_pid][2] if webship_pid in packaging_map else None
                    done_moves = sPicking.move_ids.filtered(lambda m:
                        m.state in ('cancel', 'done')
                        and (m.product_id.df_product_id_webship == webship_pid
                             or (_pkg_odoo_pid and m.product_id.id == _pkg_odoo_pid))
                    )
                    # Try to resolve the product name + SKU from the Stoqflow ID
                    product = self.env['product.product'].sudo().search(
                        [('df_product_id_webship', '=', webship_pid)], limit=1
                    )
                    if product:
                        sku = product.default_code or ''
                        product_label = "'%s' (SKU: %s)" % (product.name, sku) if sku else "'%s'" % product.name
                    elif _pkg_odoo_pid:
                        # Fallback: resolve from packaging-mapped Odoo product
                        pkg_product = self.env['product.product'].sudo().browse(_pkg_odoo_pid)
                        if pkg_product.exists():
                            sku = pkg_product.default_code or ''
                            product_label = "'%s' (SKU: %s)" % (pkg_product.name, sku) if sku else "'%s'" % pkg_product.name
                        else:
                            product_label = "Stoqflow ID '%s'" % webship_pid
                    else:
                        # Fallback: check if the Stoqflow ID belongs to a packaging record
                        pkg = self.env['product.packaging'].sudo().search(
                            [('df_product_id_webship', '=', webship_pid)], limit=1
                        )
                        if pkg and pkg.product_id:
                            sku = pkg.product_id.default_code or ''
                            product_label = "'%s' (SKU: %s)" % (pkg.product_id.name, sku) if sku else "'%s'" % pkg.product_id.name
                        else:
                            # Last resort: fetch from Stoqflow API to get the SKU
                            product_label = "Stoqflow ID '%s'" % webship_pid
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
            if self.get_default_auto_create_backorder() == 'True':
                self.showDebugInfo('Setting picking to done')

                try:
                    sPicking.make_backorder()

                    _logger.info('Calling _action_done for picking %s', sPicking.name)

                    sPicking.button_validate()

                    if sPicking.state != 'done':
                        sPicking._action_done()

                    _logger.info('Picking %s validated successfully', sPicking.name)

                except Exception as e:
                    error_msg = str(e)

                    _logger.exception(
                        "Error while validating picking %s from Webship",
                        sPicking.name
                    )

                    warnings.append("Validation error: %s" % error_msg)
            else:
                short_lines = sPicking.move_ids.filtered(
                    lambda m: m.state not in ('cancel', 'done') and m.quantity < m.product_uom_qty
                )
                if short_lines:
                    line_names = ', '.join(short_lines.mapped(lambda m: m.product_id.display_name))
                    msg = 'Quantities not met on lines: %s. Could not complete picking.' % line_names
                else:
                    msg = 'Auto-create backorder is disabled. Could not complete picking.'

                _logger.info(
                    'Picking %s: %s',
                    sPicking.name, msg
                )
                sPicking.df_picking_syncresult_webship = (
                    '<span style="color:red;">%s</span>' % msg
                )

        if oldStatus != newStatus:
            sPicking.df_status_webship = newStatus
            sPicking.df_last_changedate_webship = datetime.strptime(
                order['edited'],
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
            err = self.sync_partner(picking.partner_id)

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
                    sOutput['errors'].append(_('SKU missing on product %s') % product_name)
            else:
                sOutput['errors'].append(_('No syncable items found on this picking'))

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

            fallback_enabled = self.env['ir.config_parameter'].sudo().get_param('webship.fallback_sale_order_contact') == 'True'
            if fallback_enabled and picking.sale_id and picking.sale_id.partner_id:
                if not sEmail:
                    sEmail = picking.sale_id.partner_id.email
                    _logger.info("build_order_object: falling back to sale order contact email for picking %s", picking.name)
                if not sPhone:
                    sPhone = picking.sale_id.partner_id.phone
                    _logger.info("build_order_object: falling back to sale order contact phone for picking %s", picking.name)

            clientInfo = {
                'name':self._truncate(picking.partner_id.name, 100),
                'vat':picking.partner_id.vat,
                'address_1':self._truncate(picking.partner_id.street, 100),
                'address_2':self._truncate(picking.partner_id.street2 or ' ', 100),
                'city':self._truncate(picking.partner_id.city, 100),
                'postal_code':self._truncate(picking.partner_id.zip, 20),
                'country':sCountrCode,
                'email':sEmail,
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
                    sOutput['errors'].append(_('SKU missing on product %s') % product_name)
            else:
                sOutput['errors'].append(_('No syncable items found on this picking'))

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
        sOutput['webshipObj']['custom_fields'] = [
            {'key': 'odoo_picking_id', 'value': str(picking.id)},
            {'key': 'odoo_picking_name', 'value': self._truncate(picking.name or '', 500)},
        ]

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
        """Determine the Webship shop ID for a product based on its category hierarchy."""
        foundShop = None
        for a, b in allCatsMap.items():
            if productObj.categ_id.parent_path.startswith(a):
                foundShop = b
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

    # ------------------------------------------------------------------
    # Product sync
    # ------------------------------------------------------------------

    def match_product(self, product):
        """Link an Odoo product to its Webship counterpart by SKU."""
        foundProduct = self.findProductBySku(product.default_code)

        _logger.debug("match_product result: %s", foundProduct)

        if foundProduct == []:
            return ['Sku not found in Webship']
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
            'has_stock': product.detailed_type == 'product',
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
            result = self.performPut('products', productObj, product.df_product_id_webship )

        self.showDebugInfo(result)

        if result['status'] == 'success':
            return []
        else:
            return ['Error occured: ' + result['errorText']]

        return errors

    def sync_picking(self, picking):
        """Sync a picking (outbound order or purchase order) to Webship.
        Handles partner/supplier sync, validation, and POST/PUT as needed."""
        if picking.state in ['draft', 'cancel']:
            return ['Draft or cancelled orders cannot by synced']

        if picking.state == 'done':
            return ['Done pickings cannot be synced']

        #picking.merge_picking()

        #if getattr(picking, 'df_is_from_woocommerce', False):
        #    return ['WooCommerce orders cannot be synced']

        if picking.df_object_in_webship == 'Order':
            bDeliveryMode = True
            pickingUrl = self.baseUrl + 'orders'

            # If "match when order sync" is enabled and partner has no Stoqflow client ID,
            # attempt to match the contact to an existing Stoqflow client first
            if hasattr(self, 'env') and not picking.partner_id.df_client_id_webship:
                match_on_sync = self.env['ir.config_parameter'].sudo().get_param(
                    'webship.match_on_order_sync') == 'True'
                if match_on_sync:
                    _logger.info("sync_picking: attempting contact match for partner %s before sync",
                                 picking.partner_id.name)
                    match_result = self.match_partner_by_sequence(picking.partner_id)
                    if match_result.get('errors'):
                        _logger.info("sync_picking: contact match result for %s: %s",
                                     picking.partner_id.name, match_result['errors'])
                    if match_result.get('multiple'):
                        _logger.info("sync_picking: multiple Stoqflow clients found for %s, skipping auto-match",
                                     picking.partner_id.name)

            clientCode = picking.sale_id.partner_id.df_client_id_webship

            errors = []

            err = []

            err = self.sync_partner(picking.partner_id)
            _logger.debug("sync_partner errors: %s", err)

            if err != []:
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

            if picking.df_picking_id_webship == False:
                #perform post

                sResult = self.performPost('orders', sJson)
                self._log_json(picking, 'sent', 'POST', 'orders', sJson)

                if sResult['status'] == 'error':
                    errors.append('Error while performing post request: ' + sResult['errorText'])
                else:
                    webshipId = sResult['data']['_id']
                    picking.df_picking_id_webship = webshipId

                    errors = self.statusWsToOdoo(picking)

                    return errors

            else:
                #perform put - remove read-only fields
                for key in ['status', 'origin', 'shop_id']:
                    sJson.pop(key, None)

                sResult = self.performPut('orders', sJson, picking.df_picking_id_webship)
                self._log_json(picking, 'sent', 'PUT', 'orders/' + picking.df_picking_id_webship, sJson)

                if sResult['status'] == 'error':
                    errors.append('Error while performing put request: ' + sResult['errorText'])
                else:
                    errors = self.statusWsToOdoo(picking)

                    return errors

        elif picking.df_object_in_webship == 'Purchase order':
            self.showDebugInfo('Purchase order....')

            supplierCode = picking.purchase_id.partner_id.df_supplier_id_webship

            if supplierCode == False:
                supplierCode = picking.partner_id.df_supplier_id_webship

            self.showDebugInfo('Supplier code got: ' + str(supplierCode))
            errors = []

            if supplierCode == False:
                err = self.sync_supplier(picking.purchase_id.partner_id)

                if err != []:
                    errors.append('Could not fulfill request because of mandatory fields missing on customer')
                    errors = errors + err

            wsObject = self.build_po_object(picking)

            errors = errors + wsObject['errors']

            if errors != []:
                return errors

            sJson = wsObject['webshipObj']

            if picking.df_po_id_webship == False:
                # Deduplication: check if a PO with this supplier_reference already exists
                po_ref = sJson.get('supplier_reference', '')
                if po_ref:
                    existing = self.performGet('purchase-orders', '?supplier_reference=' + quote(po_ref))
                    if existing['status'] == 'success' and len(existing.get('data', [])) > 0:
                        existing_po = existing['data'][0]
                        picking.df_po_id_webship = existing_po['_id']
                        _logger.info("PO already exists in Stoqflow (supplier_reference=%s, id=%s), linking instead of creating", po_ref, existing_po['_id'])
                        errors = self.statusWsToOdoo(picking)
                        return errors

                sResult = self.performPost('purchase-orders', sJson)
                self._log_json(picking, 'sent', 'POST', 'purchase-orders', sJson)

                if sResult['status'] == 'error':
                    errors.append('Error while performing post request: ' + sResult['errorText'])
                else:
                    webshipPoId = sResult['data']['_id']
                    picking.df_po_id_webship = webshipPoId

                    errors = self.statusWsToOdoo(picking)

                    return errors
        else:
            errors = ['Cannot determine what type of picking it is']
            return errors

        return errors
    
    def statusWsToOdoo(self, picking):
        """Fetch the current status of an order/PO from Webship and apply it to the Odoo picking."""
        if picking.df_object_in_webship == 'Order':
            errors = []
            orderUrl = self.baseUrl + 'orders/' + picking.df_picking_id_webship + '?detail=high'

            response = self.session.get(orderUrl, timeout=self.REQUEST_TIMEOUT)

            if response.status_code == 200:
                responseData = response.json()

                picking.df_status_webship = responseData['status']

                if 'edited' in responseData:
                    latestChange = responseData['edited']
                else:
                    latestChange = responseData['created']

                date_object = datetime.strptime(latestChange, "%Y-%m-%dT%H:%M:%S.%fZ")

                picking.df_last_changedate_webship = date_object

                if responseData['status'] == 'completed':
                    try:
                        picking.button_validate()
                    except Exception as e:
                        _logger.exception("Error validating picking %s: %s", picking.name, e)
                        return ['Error while setting state to done on picking order: ' + str(e)]
                    #try:
                    #    picking.sale_id = 'done'
                    #except:
                    #    return ['Error while setting state to done on sale order']

                return []
            else:
                errors.append(response.text)
                return errors
        elif picking.df_object_in_webship == 'Purchase order':
            errors = []
            orderUrl = self.baseUrl + 'purchase-orders/' + picking.df_po_id_webship + '?detail=high'

            response = self.session.get(orderUrl, timeout=self.REQUEST_TIMEOUT)

            if response.status_code == 200:
                responseData = response.json()

                picking.df_status_webship = responseData['status']

                if 'edited' in responseData:
                    latestChange = responseData['edited']
                else:
                    latestChange = responseData['created']

                date_object = datetime.strptime(latestChange, "%Y-%m-%dT%H:%M:%S.%fZ")

                picking.df_last_changedate_webship = date_object

                if responseData['status'] == 'completed':
                    #picking.state = 'done'
                    picking.button_validate()

                return []
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

        sWJson = {'brand_id': 'stnj67jy9WZgETbak', 'type': 'basic', 'name': velden['name'],
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
        """Log debug information (replaces former print statements)."""
        _logger.info(str(sstr))

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

    def importStock(self):
        """Import inventory levels from Webship and write them to Odoo stock quants
        at locations flagged as Webship locations."""
        result = self.fetchInventory()

        if result.get("status") != "success":
            return False

        inventory_data = result.get("data", {})
        now = fields.Datetime.now()

        StockQuant = self.env["stock.quant"]
        Product = self.env["product.product"]

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
                    continue

                total = item.get("total", 0.0)
                reserved = item.get("reserved", 0.0)
                available = item.get("available", total - reserved)

                # Find existing Webship quants for this product
                quants = StockQuant.search([
                    ("product_id", "=", product.id),
                    ("location_id.df_is_webship_location", "=", True),
                    ("location_id.usage", "=", "internal"),
                ])

                if not quants:
                    # Only storable products can have stock.quant lines
                    if product.type != 'product':
                        continue

                    # Try to find a Webship location matching this company_id
                    domain = [
                        ("df_is_webship_location", "=", True),
                        ("usage", "=", "internal"),
                    ]
                    if company_id:
                        webship_location = self.env["stock.location"].search(
                            domain + [("df_warehouse_id_webship", "=", company_id)],
                            limit=1
                        )
                    else:
                        webship_location = None

                    # Fallback: any Webship internal location
                    if not webship_location:
                        webship_location = self.env["stock.location"].search(
                            domain, limit=1
                        )

                    if not webship_location:
                        continue

                    quants = StockQuant.create({
                        "product_id": product.id,
                        "location_id": webship_location.id,
                        "quantity": 0.0,
                    })

                quants.write({
                    "df_webship_totalstock": total,
                    "df_webship_reserved": reserved,
                    "df_webship_available_stock": available,
                    "df_last_check_webship": now,
                })

        return True
