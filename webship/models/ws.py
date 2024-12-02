from odoo import models
import time
from datetime import datetime
import requests
import logging
from requests.auth import HTTPBasicAuth
import math
from odoo.fields import Datetime

_logger = logging.getLogger(__name__)
#test test testr

class WebShipHandler:
    def __init__(self, ws_login, ws_password, ws_base_url):
        self.ws_login = ws_login
        self.ws_password = ws_password
        self.baseUrl = ws_base_url
        self.sleepTime = 0.5
        self.headers = {'x-addon-public-key':'kRTxA08bKieVQroS'}
        self.auth = HTTPBasicAuth(ws_login, ws_password)

    def set_env(self, env):
        self.env = env

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
            if p.product_id.code != False:
                skus.append(p.product_id.code)
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

        #sQuery = 'sku=5430002973203,5430002973272,5430002973296'

        url = self.baseUrl + 'products?' + sQuery

        print(url)

        response = requests.get(url, auth=self.auth, headers=self.headers)

        totalCount = response.headers.get('total-count')

        if int(totalCount) == 0:
            return {'error': 'Nothing is found.'}
        else:
            items = {}
            for i in response.json():
                items[i['sku']] = i['_id']
            for j in skus:
                if j not in items.keys():
                    items[j] = None

            _logger.info('Items sku found: ' + str(items))
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


    def ws_fetch_locations(self, env):
        locationsUrl = self.baseUrl + 'locations'

        response = requests.get(locationsUrl, auth=(self.ws_login, self.ws_password))

        if response.status_code != 200:
            print('Request failed with status code:', response.status_code)
            print(response)
            print(response.text)
            exit(0)
        else:
            responseData = response.json()

            for loc in responseData:
                print(loc)

                wh = env['stock.warehouse'].search([('warehouse_id_webship', '=', loc['warehouse_id'])])

                l = env['stock.location'].search([('location_id_webship', '=', loc['_id'])])

                if l.id == False:
                    sValues = {'name': loc['name'], 'complete_name':loc['name'], 'warehouse_id': wh.id, 'location_id':wh.lot_stock_id.id, 'location_id_webship':loc['_id']}
                    print(sValues)
                    env['stock.location'].create(sValues)

    def sync_all(self, env):
        print('start')
        allEvents = env['webship.events'].search([('status', '=', 'P')], order='id asc')

        for e in allEvents:
            print(e.model.model)

            if e.model.model == 'product.product':
                print(e.modelTableKey)

                prod = env['product.product'].search([('id', '=', e.modelTableKey)])

                print(prod)
                if prod.product_id_webship != False:
                    self.sync_prod(prod)

            if e.model.model == 'res.partner':
                part = env['res.partner'].search([('id', '=', e.modelTableKey)])

                self.sync_sup(part)

            if e.model.model == 'sale.order':
                print('detected sale order')
                ord = env['sale.order'].search([('id', '=', e.modelTableKey)])

                print(ord)

                self.sync_order(ord)

            e.write({'status':'F'})

    def sync_order(self, orderInfo):
        orderurl = self.baseUrl + 'orders'
        print(orderInfo)

        productsIns = []

        for ol in orderInfo.order_line:
            print(ol)

            if ol.product_id.product_id_webship != False:
                productsIns.append({'product_id':ol.product_id.product_id_webship,'quantity':ol.product_uom_qty})

        print(productsIns)

        if productsIns == []:
            return

        shopId = 'gnTXeqyuKT7nXXtbt'

        if orderInfo.partner_id.client_id_webship != False:
            output = {'shop_id': shopId, 'order_items': productsIns,
                  'client_id': orderInfo.partner_id.client_id_webship, 'status': 'ready-to-pick'}

            print(output)

            if  orderInfo.order_id_webship == False:
                time.sleep(self.sleepTime)

                response = requests.post(orderurl, json=output, auth=(self.ws_login, self.ws_password))

                if response.status_code != 200:
                    print('Request failed with status code:', response.status_code)
                    print(response)
                    print(response.text)
                    exit(0)
                else:
                    responseData = response.json()
                    print(responseData)
                    id = responseData['_id']

                    orderInfo.write({'order_id_webship': id})
            else:
                time.sleep(self.sleepTime)
                response = requests.put(orderurl + '/' + orderInfo.order_id_webship, json=output,
                                    auth=(self.ws_login, self.ws_password))

                if response.status_code != 200:
                    print('Request failed with status code:', response.status_code)
                    print(response)
                    print(response.text)
                    exit(0)

    def sync_supplier(self, partner):

        clientsUrl = self.baseUrl + 'suppliers'

        errors = []

        if partner.vat == False:
            return ['Supplier ' + str(partner.name) + ' has no VAT']

        if partner.df_supplier_id_webship == False:
            vatFound = self.findSupplierByVat(partner.vat)
            _logger.info('vat found: ' + str(vatFound))
            _logger.info('partner vat: ' + str(partner.vat))

            if 'id' in vatFound:
                partner.df_supplier_id_webship = vatFound['id']
                return []

        return ['Creation of suppliers not supported']

    def sync_partner(self, partner):

        clientsUrl = self.baseUrl + 'clients'

        errors = []

        if partner.df_client_id_webship == False:
            vatFound = self.findClientByVat(partner.vat)
            _logger.info('vat found: ' + str(vatFound))
            _logger.info('partner vat: ' + str(partner.vat))

            if 'id' in vatFound:
                partner.df_client_id_webship = vatFound['id']
                return []

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

        if deliveryAdress.id != False:
            shippingAdress = {'address_1': deliveryAdress.street, 'city': deliveryAdress.city, 'postal_code': deliveryAdress.zip, 'country': deliveryAdress.country_code}

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

            sJson = {'name':generalName, 'contact':contactName, 'email':partner.email, 'phone':partner.phone, 'mobile':partner.mobile, 'vat':partner.vat, 'addresses': {'billing':{'address_1':partner.street, 'city':partner.city, 'postal_code':partner.zip, 'country':partner.country_code}}}

            if deliveryAdress.id != False:
                sJson['addresses']['shipping'] = shippingAdress

            for key, value in list(sJson.items()):
                if value is False or value == '\'false\'' or value == '':
                    del sJson[key]

            print(sJson)
            _logger.info(str(sJson))

            if partner.df_client_id_webship == False:
                #CREATE, POST
                time.sleep(self.sleepTime)

                response = requests.post(clientsUrl, json=sJson, auth=self.auth, headers=self.headers)

                if response.status_code != 200:
                    print('Creation failed with status code: ' + str(response.status_code))
                    print(response)
                    print(response.text)
                    errors.append('Creation failed with status code:' + str(response.status_code) + ' [' + response.text + ']')
                else:
                    responseData = response.json()
                    print(responseData)
                    id = responseData['_id']
                    partner.df_client_id_webship = id
            else:
                #UPDATE, PUT
                time.sleep(self.sleepTime)

                response = requests.put(clientsUrl + '/' + partner.df_client_id_webship, json=sJson, auth=self.auth, headers=self.headers)

                if response.status_code != 200:
                    print('Update failed with status code: ' + str(response.status_code))
                    print(response)
                    print(response.text)
                    errors.append('Update failed with status code:' + str(response.status_code) + ' [' + response.text + ']')


        return errors

    def is_integer_float(self, value):
        return value % 1 == 0

    def picking_get_line_items(self, picking):
        output = []
        print(picking)
        for i in picking.move_ids:
            print(i)
            sOutput = {'productObj': i.product_id, 'detailed_type':i.product_id.detailed_type, 'default_code':i.product_id.default_code, 'product_id':i.product_id.id, 'quantity':i.product_uom_qty}

            divs = []
            sorted_skuList = []
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

    def sync_statusses_since_last(self, lastDate):
        print(lastDate)
        if lastDate == False or lastDate == None:
            url = self.baseUrl + 'orders?detail=high'
        else:
            dt_object = datetime.strptime(lastDate, "%Y-%m-%d %H:%M:%S")
            url = self.baseUrl + 'orders?detail=high&edited_after=' + self.convert_datetime(dt_object)

        print(url)

        page = 1

        while True:
            response = requests.get(url + '&page=' + str(page), auth=self.auth, headers=self.headers)

            responseData = response.json()
            totalCount = response.headers.get('total-count')
            totalPages = math.ceil(int(totalCount)/50)
            #print(responseData)

            maxEdited = None
            for order in responseData:
                print(order)
                print(order['_id'])
                print(order['status'])

                if order['status'] == 'completed':
                    pickingId = self.env['stock.picking'].search([('df_picking_id_webship','=',order['_id'])])
                    print(pickingId)
                    if pickingId:
                        if pickingId.state != 'done':
                            #pickingId.state = 'done'
                            pickingId.button_validate()
                            if 'edited' in order:
                                datum = order['edited']
                            else:
                                datum = order['created']

                            date_object = datetime.strptime(datum, "%Y-%m-%dT%H:%M:%S.%fZ")
                            date_object.replace(microsecond=0)
                            pickingId.df_last_changedate_webship = date_object


                if 'edited' in order:
                    if order['edited'] != None and maxEdited == None:
                        maxEdited = order['edited']
                    elif order['edited'] > maxEdited:
                        maxEdited = order['edited']
                else:
                    if order['created'] != None and maxEdited == None:
                        maxEdited = order['created']
                    elif order['created'] > maxEdited:
                        maxEdited = order['created']
                print('Max edited:' + maxEdited)
            self.sleep()
            page = page + 1

            if page > totalPages:
                break

        date_object = datetime.strptime(maxEdited, "%Y-%m-%dT%H:%M:%S.%fZ").replace(microsecond=0)
        dt_for_odoo = date_object.strftime("%Y-%m-%d %H:%M:%S")

        return date_object

    def build_order_object(self, picking):
        items = self.picking_get_line_items(picking)

        print(items)

        allCatShops = picking.env['product.category'].sudo().search([('df_cat_shop_id_webship', '!=', False)])

        allCatsMap = {}
        for ac in allCatShops:
            allCatsMap[ac.parent_path] = ac.df_cat_shop_id_webship

        skus = self.findProductsBySku(picking)

        print(skus)

        sOutput = {}

        sOutput['mainList'] = []
        for i in items:
            if i['divides'] == []:
                sOutput['mainList'].append({'name':i['productObj'].name, 'detailed_type':i['detailed_type'], 'default_code':i['default_code'], 'product_id':i['product_id'], 'quantity':i['quantity'], 'shopId':self.get_shop_for_product(i['productObj'], allCatsMap), 'WSku':self.get_webship_sku(i['default_code'], skus)})
            else:
                for j in i['divides']:
                    sOutput['mainList'].append({'name':i['productObj'].name, 'detailed_type':i['detailed_type'], 'default_code':j['Sku'], 'product_id':i['product_id'], 'quantity':j['OrderQty'], 'containerQty':j['Qty'],'shopId':self.get_shop_for_product(i['productObj'], allCatsMap), 'WSku':self.get_webship_sku(j['Sku'], skus)})

        clientCode = picking.sale_id.partner_id.df_client_id_webship

        print('Main client: ' + str(picking.sale_id.partner_id.name))
        print('Shipping client: ' + str(picking.sale_id.partner_shipping_id.name))

        err = []
        if clientCode == False:
            err = self.sync_partner(picking.sale_id.partner_id)

        if err == [] and clientCode == False:
            clientCode = picking.sale_id.partner_id.df_client_id_webship

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
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] == None:
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

        sOutput['webshipObj'] = {'shop_id': shopId, 'client_id': clientCode}

        if sOutput['sendScheduledDate']:
            sOutput['webshipObj']['status'] = 'on-hold'
            sOutput['webshipObj']['scheduled'] = sOutput['scheduledDateWs']
        else:
            sOutput['webshipObj']['status'] = 'ready-to-pick'
            sOutput['webshipObj']['scheduled'] = ''

        sOutput['webshipObj']['order_items'] =[]
        for i in sOutput['mainList']:
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] != None and i['detailed_type'] != 'service' and i['quantity'] != 0.0:
                sOutput['webshipObj']['order_items'].append({'product_id':i['WSku'], 'quantity':i['quantity']})

        print('Checking...')
        if picking.sale_id.id != False and picking.sale_id.partner_shipping_id != False:
            #print(picking.sale_id.partner_shipping_id)
            clientInfo = {
                'name':picking.sale_id.partner_id.name,
                'vat':picking.sale_id.partner_id.vat,
                'address_1':picking.sale_id.partner_shipping_id.street,
                'address_2':picking.sale_id.partner_shipping_id.street2 or ' ',
                'city':picking.sale_id.partner_shipping_id.city,
                'postal_code':picking.sale_id.partner_shipping_id.zip,
                'country':picking.sale_id.partner_shipping_id.country_code,
                'email':picking.sale_id.partner_id.email,
                'phone':picking.sale_id.partner_id.phone,
                          }
            print(clientInfo)
            #if clientInfo['email'] == False:
            #    clientInfo['email'] = picking.sale_id.partner_id.email

            keys_to_remove = [key for key, value in clientInfo.items() if not value]

            for key in keys_to_remove:
                clientInfo.pop(key)

            #if 'vat' not in clientInfo:
            #    sOutput['errors'].append('Vat not present in shipping address')

            if 'email' not in clientInfo and picking.sale_id.partner_id != picking.sale_id.partner_shipping_id:
                sOutput['errors'].append('E-mail address not present in shipping address. Is mandatory because shipping address is different from bill address')

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
            sOutput['mainList'].append({'name':i['productObj'].name, 'detailed_type':i['detailed_type'], 'default_code':i['default_code'], 'product_id':i['product_id'], 'quantity':i['quantity'], 'shopId':self.get_shop_for_product(i['productObj'], allCatsMap), 'WSku':self.get_webship_sku(i['default_code'], skus)})

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

        sOutput['webshipObj'] = {'supplier_id': supplierCode, 'warehouse_id':'GpXHfHSQNu29DEpE6'}

        if sOutput['sendScheduledDate']:
            sOutput['webshipObj']['status'] = 'on-hold'
            sOutput['webshipObj']['scheduled'] = sOutput['scheduledDateWs']
        else:
            sOutput['webshipObj']['status'] = 'ordered'

        sOutput['webshipObj']['order_items'] =[]
        for i in sOutput['mainList']:
            if i['default_code'] != False and i['default_code'] != None and i['WSku'] != None and i['detailed_type'] != 'service' and i['quantity'] != 0.0:
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

    def sync_picking(self, picking):
        if picking.objectInWebship == 'Order':
            bDeliveryMode = True
            pickingUrl = self.baseUrl + 'orders'

            clientCode = picking.sale_id.partner_id.df_client_id_webship

            errors = []

            err = []
            if clientCode == False:
                err = self.sync_partner(picking.sale_id.partner_id)

            if err != []:
                errors.append('Could not fulfill request because of mandatory fields missing on customer')
                errors = errors + err

            wsObject = self.build_order_object(picking)

            print(wsObject)

            errors = errors + wsObject['errors']

            if errors != []:
                return errors

            #wsObject['webshipObj'].pop('client_id')

            sJson = wsObject['webshipObj']

            print(sJson)

            _logger.info(str(sJson))

            if picking.df_picking_id_webship == False:
                time.sleep(self.sleepTime)

                pickingUrl = self.baseUrl + 'orders'

                _logger.info('Picking url called: ' + str(pickingUrl))

                response = requests.post(pickingUrl, json=sJson, auth=self.auth, headers=self.headers)

                if response.status_code != 200:
                    print('Request failed with status code: ' + str(response.status_code))
                    print(response)
                    print(response.text)
                    errors.append(
                        'Request failed with status code:' + str(response.status_code) + ' [' + response.text + ']')
                else:
                    responseData = response.json()
                    _logger.info(responseData)
                    webshipId = responseData['_id']
                    picking.df_picking_id_webship = webshipId

                    errors = self.statusWsToOdoo(picking)

                    return errors

            else:
                #perform put
                if 'status' in sJson:
                    sJson.pop('status')

                response = requests.put(pickingUrl + '/' + picking.df_picking_id_webship, json=sJson, auth=self.auth, headers=self.headers)

                if response.status_code != 200:
                    print('Request failed with status code: ' + str(response.status_code))
                    print(response)
                    print(response.text)
                    errors.append(
                        'Request failed with status code:' + str(response.status_code) + ' [' + response.text + ']')
                else:
                    responseData = response.json()
                    _logger.info(responseData)

                    errors = self.statusWsToOdoo(picking)

                    return errors
                    
                errors = self.statusWsToOdoo(picking)

                return errors

        elif picking.objectInWebship == 'Purchase order':
            pickingUrl = self.baseUrl + 'purchase-orders'
            #errors = ['No implementation for PO']

            supplierCode = picking.sale_id.partner_id.df_supplier_id_webship

            errors = []

            if supplierCode == False:
                err = self.sync_supplier(picking.sale_id.partner_id)

                if err != []:
                    errors.append('Could not fulfill request because of mandatory fields missing on customer')
                    errors = errors + err

            wsObject = self.build_po_object(picking)

            print(wsObject)

            errors = errors + wsObject['errors']

            if errors != []:
                return errors

            sJson = wsObject['webshipObj']

            _logger.info(str(sJson))

            if picking.df_po_id_webship == False:
                time.sleep(self.sleepTime)

                purchaseUrl = self.baseUrl + 'purchase-orders'

                _logger.info('Purchase url called: ' + str(purchaseUrl))

                response = requests.post(purchaseUrl, json=sJson, auth=self.auth, headers=self.headers)

                if response.status_code != 200:
                    print('Request failed with status code: ' + str(response.status_code))
                    print(response)
                    print(response.text)
                    errors.append(
                        'Request failed with status code:' + str(response.status_code) + ' [' + response.text + ']')
                else:
                    responseData = response.json()
                    _logger.info(responseData)
                    webshipPoId = responseData['_id']
                    picking.df_po_id_webship = webshipPoId

                    errors = self.statusWsToOdoo(picking)

                    return errors
        else:
            errors = ['Cannot determine what type of picking it is']
            return errors

        return errors
    
    def statusWsToOdoo(self, picking):
        if picking.objectInWebship == 'Order':
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
        elif picking.objectInWebship == 'Purchase order':
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

        sWJson = {'brand_id': 'stnj67jy9WZgETbak', 'type': 'basic', 'name': prodInfo.name, 'sku': prodInfo.default_code,
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
                exit(0)
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
