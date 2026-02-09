from odoo.addons.webship.models.ws import WebShipHandler
from odoo import http
from odoo.http import request
import io
import xlsxwriter

from odoo.tools import json


class ConfigReportController(http.Controller):

    @http.route('/custom/xlsx/download_xlsx_config_report', type='http', auth='user', website=True)
    def download_xlsx_config_report(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Settings Report')
        worksheet.write('A1', 'Example Header')
        worksheet.write('A2', 'Some Data')

        workbook.close()
        output.seek(0)

        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', 'attachment; filename="config_report.xlsx"'),
            ]
        )

    @http.route('/custom/xlsx/download_ws_prod_vergelijk', type='http', auth='user', website=True)
    def download_ws_prod_vergelijk(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Product Odoo Webship vergelijk')

        allPresentWsIds = []
        allOdooProds = []

        for p in request.env['product.product'].search([]):

            quant = 0.0

            for sq in p.stock_quant_ids:
                #print(sq.read())
                #print(sq.location_id.read())
                if sq.location_id.usage == 'internal':
                    quant = quant + sq.quantity

            allOdooProds.append({'name':p.display_name, 'quantity':quant, 'category':p.categ_id.name, 'webshipCode':p.df_product_id_webship, 'sku':p.default_code})

            allPresentWsIds.append(p.df_product_id_webship)

        print(allOdooProds)


        login = request.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = request.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = request.env['ir.config_parameter'].sudo().get_param('webship.base_url')


        wsHandler = WebShipHandler(login, pw, base_url)

        allWsProds = {}

        fetchedProds = wsHandler.fetchProducts()
        #print('Data: ')
        #print(fetchedProds['data'])

        for page in fetchedProds['data'].values():
            for product in page:
                #print(product)
                stock = 0
                for p in product.get('product_items'):
                    if 'quantity' in p.keys():
                        stock = stock + p['quantity']
                allWsProds[product['_id']] = {'sku':product['sku'], 'name':product.get('name'), 'stock':stock}


        sOutputList = []
        for p in allOdooProds:
            sArr = [p['category'], p['name'], p['sku'], p['quantity']]

            if p['webshipCode'] != False and p['webshipCode'] in allWsProds.keys():
                wsProd = allWsProds[p['webshipCode']]
                allWsProds.pop(p['webshipCode'])
                sArr = sArr + [wsProd['name'], wsProd['sku'], wsProd['stock']]
            else:
                sArr = sArr + [None, None, None]
            sOutputList.append(sArr)

        for wsp in allWsProds.values():
            sOutputList.append([None, None, None, None, wsp['name'], wsp['sku'], wsp['stock']])

        print(sOutputList)

        headers = ['Category', 'Name', 'SKU Odoo', 'Stock quantity Odoo', 'Description WS', 'Code WS', 'Stock quantity WS']

        # Write headers
        for col_num, header in enumerate(headers):
            worksheet.write(0, col_num, header)

        # Write data
        for row_num, row_data in enumerate(sOutputList, start=1):  # Start at row 1 because 0 is header
            for col_num, cell_data in enumerate(row_data):
                worksheet.write(row_num, col_num, cell_data)

        workbook.close()
        output.seek(0)


        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', 'attachment; filename="product_ws_vergelijk.xlsx"'),
            ]
        )