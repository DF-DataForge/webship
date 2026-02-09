from urllib.parse import urlencode

from odoo import models
import time
from datetime import datetime, timedelta
import requests
import logging
from requests.auth import HTTPBasicAuth
import math

from odoo import fields

from odoo.exceptions import UserError
from odoo.fields import Datetime

_logger = logging.getLogger(__name__)
#test test testr

class WebShipHandler:
    def __init__(self, ws_login, ws_password, ws_base_url):
        self.ws_login = ws_login
        self.ws_password = ws_password
        self.baseUrl = ws_base_url
        self.sleepTime = 1
        self.headers = {'x-addon-public-key':'kRTxA08bKieVQroS'}
        self.auth = HTTPBasicAuth(ws_login, ws_password)

    def set_env(self, env):
        self.env = env

    def removeFalseVals(self, sDict):
        filtered_data = {k: v for k, v in sDict.items() if v is not False}

        return filtered_data

    def get_product_stock(self):
        print('hi')

    def get_brand(self):
        return self.env['webship.brand'].search([], limit=1)[0].brand_id

    def get_default_shop(self):
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
        wObj = self.env['ir.config_parameter'].sudo().get_param('webship.default_status_order')
        return wObj

    def get_default_po_status(self):
        wObj = self.env['ir.config_parameter'].sudo().get_param('webship.default_status_po_order')
        return wObj

    def get_need_stock_complete_order(self):
        wObj = self.env['ir.config_parameter'].sudo().get_param('webship.default_order_available_condition')
        return wObj

    def get_default_auto_create_backorder(self):
        wObj = self.env['ir.config_parameter'].sudo().get_param('webship.auto_create_backorder')
        return wObj

    def test(self):
        response = requests.get(self.baseUrl + 'products', auth=self.auth, headers=self.headers)

        if response.status_code != 200:
            sStatus = 'danger'
            sMessage = 'Fout bij verbinden: ' + str(response.text)
        else:
            sStatus = 'success'
            sMessage = 'Verbinding gelukt!'

        return (sStatus, sMessage)

    def sleep(self):
        time.sleep(self.sleepTime)

    def fetchCompanies(self):
        sResult = self.fetchAll('company')

        return sResult

    def fetchWarehouses(self):
        sResult = self.fetchAll('warehouses')

        return sResult

    def fetchClients(self):
        sResult = self.fetchAll('clients', 'low')

        return sResult

    def fetchSuppliers(self):
        sResult = self.fetchAll('suppliers', 'low')

        return sResult

    def fetchProducts(self):
        sResult = self.fetchAll('products', 'low')

        return sResult

    def fetchInventory(self):
        sResult = self.fetchAll('inventory', 'low')

        return sResult

    def fetchCode(self, objectname, skey):
        if objectname == 'clients':
            response = self.fetchByKey('clients', skey)
            print(response)
            if response['status'] == 'success':
                return response['data']['client_number']
        if objectname == 'suppliers':
            response = self.fetchByKey('suppliers', skey)
            print(response)
            if response['status'] == 'success':
                return response['data']['supplier_number']
        return ['Not found']


    def fetchByKey(self, sUrl, skey):
        url = self.baseUrl + sUrl + '/' + skey

        response = requests.get(url, auth=self.auth, headers=self.headers)
        self.sleep()

        print(response.text)
        print(response.headers)

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
            return {'status': 'error', 'txt': response.text, 'code': response.status_code}
        else:
            return {'status': 'success', 'data':response.json()}

    def fetchByKeyDetail(self, sUrl, skey):
        url = self.baseUrl + sUrl + '/' + skey + '?detail=high'

        response = requests.get(url, auth=self.auth, headers=self.headers)
        self.sleep()

        print(response.text)
        print(response.headers)

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
            return {'status': 'error', 'txt': response.text, 'code': response.status_code}
        else:
            return {'status': 'success', 'data':response.json()}

    import requests
    from urllib.parse import urlencode

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
        url = f"{base_url}?{urlencode(params)}" if params else base_url
        print(url)

        # First page request
        response = requests.get(url, auth=self.auth, headers=self.headers)
        self.sleep()

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
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

                response = requests.get(paged_url, auth=self.auth, headers=self.headers)
                self.sleep()

                if response.status_code != 200:
                    print('Request failed with status code:', response.status_code)
                    print(response)
                    print(response.text)
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

    def findClientByVat(self, vatNr):

        if vatNr == False:
            return {'error': 'no vat number given'}

        self.sleep()

        url = self.baseUrl + 'clients?vat=' + vatNr

        print(url)

        response = requests.get(url, auth=self.auth, headers=self.headers)

        totalCount = response.headers.get('total-count')
        
        if totalCount == None:
            return []

        if int(totalCount) == 1:
            rJson = response.json()
            print(rJson)
            return {'id': rJson[0]['_id']}

        if int(totalCount) > 1:
            return {'error': str(totalCount) + ' occurences found.'}

        return []

    def findSupplierByVat(self, vatNr):

        if vatNr == False:
            return {'error': 'no vat number given'}

        self.sleep()

        url = self.baseUrl + 'suppliers?vat=' + vatNr

        print(url)

        response = requests.get(url, auth=self.auth, headers=self.headers)

        totalCount = response.headers.get('total-count')

        if int(totalCount) == 1:
            rJson = response.json()
            print(rJson)
            return {'id': rJson[0]['_id']}

        if int(totalCount) > 1:
            return {'error': str(totalCount) + ' occurences found.'}

        return []

    def findProductBySku(self, skuNr):

        if skuNr == False:
            return {'error': 'no sku given'}

        self.sleep()

        url = self.baseUrl + 'products?sku=' + skuNr

        print(url)

        response = requests.get(url, auth=self.auth, headers=self.headers)

        totalCount = response.headers.get('total-count')

        if totalCount == None:
            return []

        if int(totalCount) == 1:
            rJson = response.json()
            print(rJson)
            return {'id': rJson[0]['_id']}

        if int(totalCount) > 1:
            return {'error': str(totalCount) + ' occurences found.'}

        return []
       
    def findProductsBySku(self, picking):
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

        print('Looking for SKUS:')
        print(skus)

        _logger.info('Searching SKUS: ' + str(skus))

        if skus == []:
            return {'error': 'No codes given'}

        sQuery = None
        for s in skus:
            if sQuery == None:
                sQuery = 'sku='+str(s)
            else:
                sQuery = sQuery + ','+str(s)

        print(sQuery)

        _logger.info('Query for skus: ' + sQuery)


        allRecords = self.fetchAll('products?' + sQuery, 'low', None)
        print(allRecords)
        items = {}

        totalCount = allRecords['totalCount']
        if totalCount == None or int(totalCount) == 0:
            return {'error': 'Nothing is found.'}

        for page in allRecords['data'].values():
            print(page)
            for it in page:
                items[it['sku']] = it['_id']

        return {'items': items}

    def ws_fetch_warehouses(self, env):
        warehousesUrl =  self.baseUrl + 'warehouses'

        response = requests.get(warehousesUrl, auth=(self.ws_login, self.ws_password))

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
            exit(0)
        else:
            responseData = response.json()

            for warehouse in responseData:
                print(warehouse)

                wh = env['stock.warehouse'].search([('warehouse_id_webship', '=', warehouse['_id'])])

                if wh.id == False:
                    env['stock.warehouse'].create({'name':warehouse['name'], 'warehouse_id_webship':warehouse['_id'], 'code':warehouse['name']})

    def match_partner(self, partner):
        if partner.email == False:
            return ['No e-mail address specified']

        clientsUrl = self.baseUrl + 'clients'

        sReq = self.performGet('clients', "?email=" + partner.email)

        if sReq['status'] == 'success':
            print(sReq)
            partner.df_client_id_webship = sReq['data'][0]['_id']

        return []

    def sync_supplier(self, partner):

        clientsUrl = self.baseUrl + 'suppliers'

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
            if True:
                del sObject['supplier_number']
                sRes = self.performPost('suppliers', sObject)
                if sRes['status'] == 'success':
                    partner.df_supplier_id_webship = sRes['data']['_id']
            else:
                sRes = self.performPost('suppliers', sObject)
                if sRes['status'] == 'error' and sRes['errorText'] == '[{"error":"suppliers.add.no-unique-number","message":"supplier number must be unique"}]':
                    sObject['supplier_number'] = sObject['supplier_number'] + 'B'
                    sRes = self.performPost('suppliers', sObject)
        else:
            sRes = self.performPut('suppliers', sObject, partner.df_supplier_id_webship)

        if sRes['status'] == 'error':
            return ['Error while creating suppier: ' + sRes['errorText']]

        return []

    def performPost(self, url, sObject):
        url = self.baseUrl + url
        self.showDebugInfo('Url called: ' + url)

        cleanedObject = self.removeFalseVals(sObject)
        self.showDebugInfo('About to post: ' + str(cleanedObject))

        self.sleep()
        response = requests.post(url, json=cleanedObject, auth=self.auth, headers=self.headers)

        self.showDebugInfo('Response: ' + response.text)

        if response.status_code != 200:
            return {'status': 'error', 'errorCode':response.status_code, 'errorText':response.text}
        else:
            responseData = response.json()
            return {'status':'success', 'data':responseData}

    def performPut(self, url, sObject, sId):
        url = self.baseUrl + url + '/' + sId
        self.showDebugInfo('Url called: ' + url)

        cleanedObject = self.removeFalseVals(sObject)
        self.showDebugInfo('About to put: ' + str(cleanedObject))

        self.sleep()
        response = requests.put(url, json=cleanedObject, auth=self.auth, headers=self.headers)

        self.showDebugInfo('Response: ' + response.text)

        if response.status_code != 200:
            return {'status': 'error', 'errorCode':response.status_code, 'errorText':response.text}
        else:
            responseData = response.json()
            return {'status':'success', 'data':responseData}

    def performGet(self, url, sParams):
        url = self.baseUrl + url + sParams

        self.sleep()
        response = requests.get(url, auth=self.auth, headers=self.headers)

        self.showDebugInfo('Url called: ' + url)
        self.showDebugInfo('Response got: ' + response.text)
        self.showDebugInfo('Response code got: ' + str(response.status_code))


        if response.status_code != 200:
            return {'status': 'error', 'errorCode':response.status_code, 'errorText':response.text}
        else:
            responseData = response.json()
            return {'status':'success', 'data':responseData}

    def sync_partner(self, partner):

        clientsUrl = self.baseUrl + 'clients'

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
                if True:
                    del sJson['client_number']
                    result = self.performPost('clients', sJson)
                    if result['status'] == 'success':
                        partner.df_client_id_webship = result['data']['_id']
                else:
                    result = self.performPost('clients', sJson)
                    #print(result)
                    if result['status'] == 'success':
                        partner.df_client_id_webship = result['data']['_id']
                    elif result['status'] == 'error' and result['errorText'] == '[{"error":"clients.add.no-unique-number","message":"client number must be unique"}]':
                        sJson['client_number'] = sJson['client_number'] + 'B'
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

    def is_integer_float(self, value):
        return value % 1 == 0

    def picking_get_line_items(self, picking):
        output = []
        print(picking)
        for i in picking.move_ids:
            print(i.product_id.default_code)
            if i.product_id.df_product_do_not_send_webship == True or i.product_id.default_code == False:
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

            print('Divides: ' + str(sOutput))

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
        maxEdited = None

        if lastDate:
            orders = self.fetchAll('orders', 'high', self.add_seconds_to_odoo_datetime(lastDate),None)
        else:
            orders = self.fetchAll('orders', 'high', lastDate, None)

        allChangeDates = []

        allPickingsWS = set()

        print(orders)

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
                    print('Picking got: ' + str(pickingId))
                    if pickingId and len(pickingId) == 1  and pickingId.state!='cancel':
                        print('Setting quantities')
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

        print(allPickingsWS)

        return date_object

    def sync_po_statusses_since_last(self, lastDate):
        
        maxEdited = None
        if lastDate:
            orders = self.fetchAll('purchase-orders', 'high', self.add_seconds_to_odoo_datetime(lastDate))
        else:
            orders = self.fetchAll('purchase-orders', 'high', lastDate)

        allChangeDates = []

        if orders['status'] == 'success':
            for page in orders['data'].values():
                for order in page:
                    pickingId = self.env['stock.picking'].search([('df_picking_id_webship', '=', order['_id'])])
                    if pickingId and len(pickingId) == 1:
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

        if maxEdited:
            maxEdited = max(allChangeDates)

            date_object = datetime.strptime(maxEdited, "%Y-%m-%dT%H:%M:%S.%fZ").replace(microsecond=0)
            dt_for_odoo = date_object.strftime("%Y-%m-%d %H:%M:%S")

            return date_object
        else:
            return None

    def sync_po_statusses_since_last(self, lastDate):
        maxEdited = None
        orders = self.fetchAll('purchase-orders', 'high', lastDate)

        if orders['status'] == 'success':
            for page in orders['data'].values():
                for po_order in page:
                    print(po_order)
                    if po_order['status'] == 'completed':
                        pickingId = self.env['stock.picking'].search([('df_po_id_webship', '=', po_order['_id'])])
                        print(pickingId)
                        if pickingId and len(pickingId) == 1:
                            if pickingId.state != 'done':
                                print('Setting status to done')
                                # pickingId.state = 'done'

                                self.setPickingQuantities(pickingId, po_order)

                                pickingId.button_validate()
                                print('Validate pressed')
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
                    print('Max edited:' + maxEdited)
        
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

        self.showDebugInfo('In picking quantites')

        if sPicking.state == 'done':
            return

        print('Picking got: ' + str(sPicking.read()))
        print('Order got: ' + str(order))

        self.showDebugInfo(sPicking.read())

        tracking = order.get('tracking_numbers')
        if tracking and hasattr(sPicking, 'carrier_tracking_ref'):
            sPicking.carrier_tracking_ref = order['tracking_numbers']

        if order.get('status') == 'completed':
            # ------------------------------------------------------------
            # Reset quantities first
            # ------------------------------------------------------------
            for m in sPicking.move_ids.filtered(lambda m: m.state not in ('cancel', 'done')):
                self.showDebugInfo('Reading move: ' + str(m.read()))
                if m.product_id.df_product_id_webship == False:
                    pId = self.findProductBySku(m.product_id.default_code)
                    if 'error' not in pId:
                        m.product_id.df_product_id_webship = pId['id']
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
            for o in order.get('picks') or []:
                if o['product_id'] not in pMap:
                    pMap[o['product_id']] = o['quantity']
                    if o.get('batch'):
                        batchMap[o['product_id']] = o['batch']
                else:
                    pMap[o['product_id']] = pMap[o['product_id']] + o['quantity']

            # Purchase order / inbound style: use received from order_items
            if not order.get('picks'):
                for o in order.get('order_items') or []:
                    if o.get('received'):
                        if o['product_id'] not in pMap:
                            pMap[o['product_id']] = o['received']
                        else:
                            pMap[o['product_id']] = pMap[o['product_id']] + o['received']

            self.showDebugInfo('pMap obtained: ' + str(pMap))

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
        #END if new status = 'completed'

        # ------------------------------------------------------------
        # Status update + validation
        # ------------------------------------------------------------
        oldStatus = sPicking.df_status_webship or ''
        newStatus = order['status']

        if newStatus == 'completed' and sPicking.state != 'done':
            self.showDebugInfo('Setting picking to done')

            try:
                if self.get_default_auto_create_backorder() == 'True':
                    sPicking.make_backorder()

                print('_action_done')

                sPicking.button_validate()

                if sPicking.state != 'done':
                    sPicking._action_done()

                print('done pressed')

            except Exception as e:
                error_msg = str(e)

                _logger.exception(
                    "Error while validating picking %s from Webship",
                    sPicking.name
                )

                sPicking.df_picking_syncresult_webship = error_msg

        if oldStatus != newStatus:
            sPicking.df_status_webship = newStatus
            sPicking.df_last_changedate_webship = datetime.strptime(
                order['edited'],
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(microsecond=0)

            self.showDebugInfo('Status changed from ' + oldStatus + ' to ' + newStatus)

        sPicking.df_picking_syncresult_webship = 'success'

    def build_order_object(self, picking):
        items = self.picking_get_line_items(picking)

        print(items)

        allCatShops = picking.env['product.category'].sudo().search([('df_cat_shop_id_webship', '!=', False)])

        allCatsMap = {}
        for ac in allCatShops:
            allCatsMap[ac.parent_path] = ac.df_cat_shop_id_webship

        skus = self.findProductsBySku(picking)

        print('Skus: ')
        print(skus)

        sOutput = {}

        sOutput['mainList'] = []
        for i in items:
            if i['divides'] == []:
                sOutput['mainList'].append({'name':i['productObj'].name, 'type':i['type'], 'default_code':i['default_code'], 'product_id':i['product_id'], 'quantity':i['quantity'], 'shopId':self.get_default_shop(), 'WSku':self.get_webship_sku(i['default_code'], skus)})
            else:
                for j in i['divides']:
                    sOutput['mainList'].append({'name':i['productObj'].name, 'type':i['type'], 'default_code':j['Sku'], 'product_id':i['product_id'], 'quantity':j['OrderQty'], 'containerQty':j['Qty'],'shopId':self.get_default_shop(), 'WSku':self.get_webship_sku(j['Sku'], skus)})



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
            sOutput['errors'].append('There are items with zero quantity')

        #if clientCode == False:
        #    sOutput['errors'].append('Client does not exist in Webship')

        for i in sOutput['mainList']:
            if i['default_code'] == False or i['default_code'] == None:
                sOutput['errors'].append('No SKU in Odoo for product ' + i['name'])

        for i in sOutput['mainList']:
            print('--')
            print('*' + i['default_code'] + '*')
            print(i['WSku'])
            print('--')
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] == None:
                print('In error: ' + str(i))
                sOutput['errors'].append('No SKU in Webship for product ' + i['name'] + ' with code ' + i['default_code'])

        for i in sOutput['mainList']:
            if not self.is_integer_float(i['quantity']):
                sOutput['errors'].append('Product ' + i['name'] + ' has non integer value')

        allShops = set()
        for i in sOutput['mainList']:
            if i['shopId'] == None:
                sOutput['errors'].append('No shop Id for product ' + i['name'])
            else:
                allShops.add(i['shopId'])

        if len(list(allShops)) > 1:
            sOutput['errors'].append('More than one shop found in Order (' + str(allShops) + ')')

        shopId = None

        if allShops != set():
            shopId = list(allShops)[0]

        origin_number = (
            picking.sale_id.name[:50]
            if picking.sale_id
            else picking.name
        )

        sOutput['webshipObj'] = {'shop_id': shopId, 'client_id': clientCode, 'origin': {'id':picking.id, 'number':origin_number}}

        print(sOutput)

        if picking.note != False:
            sOutput['webshipObj']['notes'] = picking.note
        elif picking.sale_id != False and picking.sale_id.partner_id.df_standard_internal_note:
            sOutput['webshipObj']['notes'] = picking.sale_id.partner_id.df_standard_internal_note

        if sOutput['sendScheduledDate']:
            sOutput['webshipObj']['status'] = 'on-hold'
            sOutput['webshipObj']['scheduled'] = sOutput['scheduledDateWs']
        else:
            #sOutput['webshipObj']['status'] = 'ready-to-pick'
            sOutput['webshipObj']['status'] = self.get_default_status()
            sOutput['webshipObj']['scheduled'] = ''

        sOutput['webshipObj']['order_items'] =[]
        for i in sOutput['mainList']:
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] != None and i['type'] != 'service' and i['quantity'] != 0.0:
                sOutput['webshipObj']['order_items'].append({'product_id':i['WSku'], 'quantity':i['quantity']})

        print('Checking...')
        if True:
            #print(picking.sale_id.partner_shipping_id)

            sCountrCode = picking.partner_id.country_code
            if sCountrCode == False:
                sCountrCode = 'BE'

            clientInfo = {
                'name':picking.partner_id.name,
                'vat':picking.partner_id.vat,
                'address_1':picking.partner_id.street,
                'address_2':picking.partner_id.street2 or ' ',
                'city':picking.partner_id.city,
                'postal_code':picking.partner_id.zip,
                'country':sCountrCode,
                'email':picking.partner_id.email,
                'phone':picking.partner_id.phone,
                          }
            print(clientInfo)
            #if clientInfo['email'] == False:
            #    clientInfo['email'] = picking.sale_id.partner_id.email

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
        
        _logger.info('Builded object: ' + str(sOutput))
        print('Builded object: ' + str(sOutput))

        return sOutput

    def build_po_object(self, picking):
        items = self.picking_get_line_items(picking)

        print(items)

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
            sOutput['errors'].append('There are items with zero quantity')

        if supplierCode == False:
            sOutput['errors'].append('Supplier does not exist in Webship')

        for i in sOutput['mainList']:
            if i['default_code'] == False or i['default_code'] == None:
                sOutput['errors'].append('No SKU in Odoo for product ' + i['name'])

        for i in sOutput['mainList']:
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] == None:
                sOutput['errors'].append('No SKU in Webship for product ' + i['name'] + ' with code ' + i['default_code'])

        #print('Location dest id: ')
        #print(picking.location_dest_id.df_warehouse_id_webship)
        #sOutput['webshipObj'] = {'supplier_id': supplierCode, 'warehouse_id':self.get_warehouse()}
        sOutput['webshipObj'] = {'supplier_id': supplierCode, 'warehouse_id': picking.location_dest_id.df_warehouse_webship.warehouse_id}

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
        _logger.info('Looking for ' + str(code) + ' in SKUS: ' + str(webshipskus))
        
        if code != False and code != None and 'items' in webshipskus and code in webshipskus['items'].keys():
            _logger.info('Returning ' + str(webshipskus['items'][code]))
            return webshipskus['items'][code]
        else:
            return None

    def convert_datetime(self, date_time_object):
        if date_time_object == None or date_time_object == False:
            return None
        else:
            return date_time_object.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def get_shop_for_product(self, productObj, allCatsMap):
        foundShop = None
        for a, b in allCatsMap.items():
            if productObj.categ_id.parent_path.startswith(a):
                foundShop = b
        return foundShop

    def get_picking_code(self, pickingId):
        url = self.baseUrl + 'orders/' + pickingId

        self.sleep()
        response = requests.get(url, auth=self.auth, headers=self.headers)

        if response.status_code != 200:
            print('Request failed with status code: ' + str(response.status_code))
            print(response)
            print(response.text)
        else:
            responseData = response.json()
            _logger.info(responseData)
            if 'order_number' in responseData:
                webshipCode = responseData['order_number']
                return webshipCode
        return None

    def get_po_code(self, pickingId):
        url = self.baseUrl + 'purchase-orders/' + pickingId

        self.sleep()
        response = requests.get(url, auth=self.auth, headers=self.headers)

        if response.status_code != 200:
            print('Request failed with status code: ' + str(response.status_code))
            print(response)
            print(response.text)
        else:
            responseData = response.json()
            _logger.info(responseData)
            if 'order_number' in responseData:
                webshipCode = responseData['order_number']
                return webshipCode
        return None

    def setStatusOrder(self, orderId, sStatus):
        url = self.baseUrl + 'orders/' + orderId + '/status'

        sPayload = {'status':sStatus}
        self.sleep()

        response = requests.put(url, json=sPayload, auth=self.auth, headers=self.headers)

        if response.status_code != 200:
            print('Request failed with status code: ' + str(response.status_code))
            print(response)
            print(response.text)

    def match_product(self, product):
        foundProduct = self.findProductBySku(product.default_code)

        print(foundProduct)

        if foundProduct == []:
            return ['Sku not found in Webship']
        else:
            product.df_product_id_webship = foundProduct['id']

        return []

    def sync_product(self, product):
        errors = []

        if product.default_code == False or product.default_code == '':
            errors.append('No sku for product')

        brandId = self.get_brand()
        productObj = {'brand_id':brandId, 'sku':product.default_code, 'name':product.name, 'price':product.standard_price, 'retail_price':product.lst_price}

        if product.barcode:
            productObj['barcodes'] = [{'type':'ean13', 'code':product.barcode, 'main':True}]


        if product.df_product_id_webship == False:
            result = self.performPost('products', productObj)
            if result['status'] == 'success':
                product.df_product_id_webship = result['data']['_id']
        else:
            result = self.performPut('products', productObj, product.df_product_id_webship )

        self.showDebugInfo(result)

        if result['status'] == 'success':
            return []
        else:
            return ['Error occured: ' + result['errorText']]

        return errors

    def sync_picking(self, picking):

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

            clientCode = picking.sale_id.partner_id.df_client_id_webship

            errors = []

            err = []

            err = self.sync_partner(picking.partner_id)
            print(err)

            if err != []:
                errors.append('Could not fulfill request because of mandatory fields missing on customer')
                errors = errors + err

            self.showDebugInfo('All items in stock: ' + str(picking.products_availability_state))
            self.showDebugInfo('Need stock complete: ' + str(self.get_need_stock_complete_order()))
            self.showDebugInfo(type(self.get_need_stock_complete_order()))
            if picking.products_availability_state != 'available' and str(self.get_need_stock_complete_order()) == 'True':
                errors.append('Not all items are in stock')

            print(errors)

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

                if sResult['status'] == 'error':
                    errors.append('Error while performing post request: ' + sResult['errorText'])
                else:
                    webshipId = sResult['data']['_id']
                    picking.df_picking_id_webship = webshipId

                    errors = self.statusWsToOdoo(picking)

                    return errors

            else:
                #perform put
                if 'status' in sJson:
                    sJson.pop('status')

                sResult = self.performPut('orders', sJson, picking.df_picking_id_webship)

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
                sResult = self.performPost('purchase-orders', sJson)

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
        if picking.df_object_in_webship == 'Order':
            errors = []
            orderUrl = self.baseUrl + 'orders/' + picking.df_picking_id_webship + '&detail=high'

            response = requests.get(orderUrl, auth=self.auth, headers=self.headers)

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
                    except:
                        return ['Error while setting state to done on picking order']
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
            orderUrl = self.baseUrl + 'purchase-orders/' + picking.df_po_id_webship + '&detail=high'

            response = requests.get(orderUrl, auth=self.auth, headers=self.headers)

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
    

    def sync_prod(self, prodInfo):
        produrl = self.baseUrl + 'products'

        print(produrl)

        sWJson = {'brand_id': self.get_brand(), 'type': 'basic', 'name': prodInfo.name, 'sku': prodInfo.default_code,
                  'description': prodInfo.description, 'barcodes': [{'type': 'ean13', 'code': prodInfo.default_code}],
                  'price': prodInfo.standard_price, 'retail_price': prodInfo.list_price, 'stock_type': prodInfo.stockType}

        if sWJson['stock_type'] == False:
            sWJson.pop('stock_type')

        if prodInfo.barcode == False:
            sWJson.pop('barcodes')

        if prodInfo.product_id_webship == False:
            time.sleep(self.sleepTime)
            print(sWJson)
            response = requests.post(produrl, json=sWJson, auth=(self.ws_login, self.ws_password))

            if response.status_code != 200:
                print('Request failed with status code:', response.status_code)
                print(response)
                print(response.text)
                exit(0)
            else:
                responseData = response.json()
                print(responseData)
                id = responseData['_id']

                prodInfo.write({'product_id_webship':id})
        else:
            time.sleep(self.sleepTime)
            print(sWJson)
            print(produrl)
            response = requests.put(produrl + '/' + prodInfo.product_id_webship, json=sWJson, auth=(self.ws_login, self.ws_password))

            if response.status_code != 200:
                print('Request failed with status code:', response.status_code)
                print(response)
                print(response.text)


    def sync_sup(self, supInfo):
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
            print(sWJson)
            response = requests.post(sup_url, json=sWJson, auth=(self.ws_login, self.ws_password))

            if response.status_code != 200:
                print('Request failed with status code:', response.status_code)
                print(response)
                print(response.text)
                exit(0)
            else:
                responseData = response.json()
                print(responseData)
                id = responseData['_id']

                supInfo.write({'supplier_id_webship':id})
        else:
            time.sleep(self.sleepTime)
            print(sWJson)
            response = requests.put(sup_url + '/' + supInfo.supplier_id_webship, json=sWJson, auth=(self.ws_login, self.ws_password))

            if response.status_code != 200:
                print('Request failed with status code:', response.status_code)
                print(response)
                print(response.text)
                exit(0)

        if supInfo.client_id_webship == False:
            time.sleep(self.sleepTime)
            addressInfo = sWJson['address']

            sWJson.pop('address')
            sWJson['addresses'] = {}
            sWJson['addresses']['billing'] = addressInfo
            sWJson['addresses']['shipping'] = addressInfo
            print(sWJson)
            response = requests.post(client_url, json=sWJson, auth=(self.ws_login, self.ws_password))

            if response.status_code != 200:
                print('Request failed with status code:', response.status_code)
                print(response)
                print(response.text)
                exit(0)
            else:
                responseData = response.json()
                print(responseData)
                id = responseData['_id']

                supInfo.write({'client_id_webship':id})
        else:
            time.sleep(self.sleepTime)
            print(sWJson)
            response = requests.put(client_url + '/' + supInfo.client_id_webship, json=sWJson,
                                    auth=(self.ws_login, self.ws_password))

            if response.status_code != 200:
                print('Request failed with status code:', response.status_code)
                print(response)
                print(response.text)
                exit(0)





        #print(supInfo.supplier_id_webship)

        #print(supInfo.client_id_webship)


    def import_sup(self):
        print('hi')
    def emptyOrders(self):
        url = self.baseUrl + 'orders'

        time.sleep(self.sleepTime)
        response = requests.get(url, auth=(self.ws_login, self.ws_password))

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
            exit(0)
        else:
            for item in response.json():
                deleteUrl = self.baseUrl + 'orders/' + item['_id']
                time.sleep(self.sleepTime)
                response = requests.delete(deleteUrl, auth=(self.ws_login, self.ws_password))

    def emptyProducts(self):
        time.sleep(self.sleepTime)
        url = self.baseUrl + 'products'

        response = requests.get(url, auth=(self.ws_login, self.ws_password))

        #print(response)

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
            exit(0)
        else:
            for item in response.json():
                deleteUrl = self.baseUrl + 'products/' + item['_id']
                time.sleep(self.sleepTime)
                response = requests.delete(deleteUrl, auth=(self.ws_login, self.ws_password))

    def emptyClients(self):
        url = self.baseUrl + 'clients'

        time.sleep(self.sleepTime)
        response = requests.get(url, auth=(self.ws_login, self.ws_password))

        # print(response)

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
            exit(0)
        else:
            for item in response.json():
                deleteUrl = self.baseUrl + 'clients/' + item['_id']
                time.sleep(self.sleepTime)
                response = requests.delete(deleteUrl, auth=(self.ws_login, self.ws_password))

    def emptySuppliers(self):
        url = self.baseUrl + 'suppliers'

        time.sleep(self.sleepTime)
        response = requests.get(url, auth=(self.ws_login, self.ws_password))

        # print(response)

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
            exit(0)
        else:
            for item in response.json():
                deleteUrl = self.baseUrl + 'suppliers/' + item['_id']
                time.sleep(1)
                response = requests.delete(deleteUrl, auth=(self.ws_login, self.ws_password))

    def updateProduct(self, velden):
        url = self.baseUrl + 'products'

        sWJson = {'brand_id': 'stnj67jy9WZgETbak', 'type': 'basic', 'name': velden['name'],
                  'sku': velden['default_code']}

        if velden['product_id_webship'] == False:
            print('Inserting...')
            time.sleep(1)
            response = requests.post(url, json=sWJson, auth=(self.ws_login, self.ws_password))

            if response.status_code == 403:
                #sku non unique
                print('sku non uniue')
            elif response.status_code != 200:
                print('Request failed with status code:', response.status_code)
                print(response)
                print(response.text)
                exit(0)
            else:
                responseData = response.json()
                print(responseData)
                print(responseData['_id'])

                #self.odooDb.updateRecord('product.product', velden['id'], {'product_id_webship': responseData['_id']})
        else:
            print('Updating...')
            time.sleep(1)
            response = requests.put(url + '/' + str(velden['product_id_webship']), json=sWJson,
                                    auth=(self.Wsusername, self.Wspassword))

            if response.status_code != 200:
                print('Request failed with status code:', response.status_code)
                print(response)
                print(response.text)
                exit(0)

    def exportSups(self):
        response = requests.get(self.baseUrl + 'suppliers', auth=self.auth, headers=self.headers)

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
            exit(0)

        return response.json()

    def showDebugInfo(self, sstr):
        #print(sstr)
        _logger.info(str(sstr))

    def exportClients(self):
        output = []
        i = 50
        page = 1

        while True:
            self.sleep()

            response = requests.get(self.baseUrl + 'clients?page=' + str(page), auth=self.auth, headers=self.headers)

            totalCount = response.headers.get('total-count')

            #print(response.json())

            if response.status_code != 200:
                print('Request failed with status code:', response.status_code)
                print(response)
                print(response.text)
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
        result = self.fetchInventory()

        if result.get("status") != "success":
            return False

        inventory_data = result.get("data", {})
        now = fields.Datetime.now()

        StockQuant = self.env["stock.quant"]
        Product = self.env["product.product"]

        for company_id, items in inventory_data.items():
            for item in items:
                sku = item.get("sku")
                if not sku:
                    continue

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

                # Find all Webship quants for this product
                quants = StockQuant.search([
                    ("product_id", "=", product.id),
                    ("location_id.df_is_webship_location", "=", True),
                    ("location_id.usage", "=", "internal"),
                ])

                if not quants:
                    continue

                quants.write({
                    "df_webship_totalstock": total,
                    "df_webship_reserved": reserved,
                    "df_webship_available_stock": available,
                    "df_last_check_webship": now,
                })

        return True
