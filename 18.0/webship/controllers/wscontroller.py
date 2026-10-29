# HTTP controllers for generating and downloading Excel (XLSX) reports
# that compare Odoo data with Webship data.
from odoo.addons.webship.models.ws import WebShipHandler
from odoo import http
from odoo.http import request
import io
import logging
import xlsxwriter

from odoo.tools import json

_logger = logging.getLogger(__name__)


class ConfigReportController(http.Controller):
    """Controller providing downloadable XLSX reports via HTTP endpoints."""

    @http.route('/custom/xlsx/download_xlsx_config_report', type='http', auth='user', website=True)
    def download_xlsx_config_report(self):
        """Generate and return a basic configuration report as an XLSX download."""
        # Create an in-memory buffer to hold the Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Settings Report')

        # Write placeholder content
        worksheet.write('A1', 'Example Header')
        worksheet.write('A2', 'Some Data')

        workbook.close()
        output.seek(0)

        # Return the file as a downloadable HTTP response
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', 'attachment; filename="config_report.xlsx"'),
            ]
        )

    @http.route('/custom/xlsx/download_ws_prod_vergelijk', type='http', auth='user', website=True)
    def download_ws_prod_vergelijk(self):
        """Generate an XLSX report comparing Odoo products with Webship products.
        Matches are made by the Webship product ID stored on each Odoo product.
        Unmatched products from either system appear in separate rows."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Product Odoo Webship vergelijk')

        # Collect all Webship IDs present on Odoo products for matching later
        allPresentWsIds = []
        allOdooProds = []

        # Loop through every Odoo product and sum internal stock quantities
        for p in request.env['product.product'].search([]):

            quant = 0.0

            for sq in p.stock_quant_ids:
                # Only count stock in internal (physical warehouse) locations
                if sq.location_id.usage == 'internal':
                    quant = quant + sq.quantity

            allOdooProds.append({'name':p.display_name, 'quantity':quant, 'category':p.categ_id.name, 'webshipCode':p.df_product_id_webship, 'sku':p.default_code})

            allPresentWsIds.append(p.df_product_id_webship)

        _logger.debug("All Odoo products: %s", allOdooProds)

        # Retrieve Webship API credentials from system parameters
        login = request.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = request.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = request.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        # Initialize the Webship API handler and fetch all products from Webship
        wsHandler = WebShipHandler(login, pw, base_url)

        allWsProds = {}

        fetchedProds = wsHandler.fetchProducts()

        # Iterate through paginated Webship products and calculate total stock per product
        for page in fetchedProds['data'].values():
            for product in page:
                stock = 0
                for p in product.get('product_items'):
                    if 'quantity' in p.keys():
                        stock = stock + p['quantity']
                allWsProds[product['_id']] = {'sku':product['sku'], 'name':product.get('name'), 'stock':stock}

        # Build the output list: match Odoo products with Webship products side by side
        sOutputList = []
        for p in allOdooProds:
            sArr = [p['category'], p['name'], p['sku'], p['quantity']]

            # If the Odoo product has a matching Webship ID, append Webship data and remove it from the pool
            if p['webshipCode'] != False and p['webshipCode'] in allWsProds.keys():
                wsProd = allWsProds[p['webshipCode']]
                allWsProds.pop(p['webshipCode'])
                sArr = sArr + [wsProd['name'], wsProd['sku'], wsProd['stock']]
            else:
                # No match found: leave Webship columns empty
                sArr = sArr + [None, None, None]
            sOutputList.append(sArr)

        # Append remaining unmatched Webship products (no corresponding Odoo product)
        for wsp in allWsProds.values():
            sOutputList.append([None, None, None, None, wsp['name'], wsp['sku'], wsp['stock']])

        _logger.debug("Output list: %s", sOutputList)

        headers = ['Category', 'Name', 'SKU Odoo', 'Stock quantity Odoo', 'Description WS', 'Code WS', 'Stock quantity WS']

        # Write column headers to the first row
        for col_num, header in enumerate(headers):
            worksheet.write(0, col_num, header)

        # Write each product comparison row starting from row 1
        for row_num, row_data in enumerate(sOutputList, start=1):
            for col_num, cell_data in enumerate(row_data):
                worksheet.write(row_num, col_num, cell_data)

        workbook.close()
        output.seek(0)

        # Return the comparison report as a downloadable XLSX file
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', 'attachment; filename="product_ws_vergelijk.xlsx"'),
            ]
        )
