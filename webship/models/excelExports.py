# HTTP controller for generating a comprehensive Excel (XLSX) report comparing
# Stoqflow suppliers, clients, and Odoo contacts side by side.
# Fetches all suppliers via GET /suppliers and all clients via GET /clients,
# then matches them against Odoo res.partner records by name.
# The report contains three worksheets:
#   1. "Suppliers Webship" - Stoqflow suppliers with matched Odoo partner data
#   2. "Clients Webship" - Stoqflow clients (billing + shipping addresses) with Odoo matches
#   3. "Contacten Odoo" - All Odoo partners with matched Stoqflow data
import xlsxwriter
import io
import logging

from odoo import fields, models, http
from odoo.http import request, content_disposition

from . import ws

_logger = logging.getLogger(__name__)

class MyExcelDownloadController(http.Controller):

    @http.route('/web/download/excel', type='http', auth='user')
    def download_excel(self, **kwargs):
        """Generate and return a multi-sheet XLSX report as a file download.
        Requires query parameter ?p=partner to indicate the report type."""
        # Create an in-memory buffer to hold the Excel file
        output = io.BytesIO()

        _logger.debug("download_excel kwargs: %s", kwargs)

        # Validate the required 'p' parameter
        if 'p' not in kwargs:
            _logger.warning('Missing parameter p in download_excel')
            return

        if kwargs['p'] == 'partner':
            _logger.debug('Partner export requested')

        # Create an Excel workbook with xlsxwriter
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet("Suppliers Webship")

        # Retrieve Stoqflow API credentials from system parameters
        login = http.request.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = http.request.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = http.request.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = ws.WebShipHandler(login, pw, base_url)

        # Fetch all suppliers from Stoqflow via GET /suppliers (paginated)
        sups = wsHandler.exportSups()

        e = 0

        # Define cell formatting styles
        bold_center_format = workbook.add_format({'bold': True, 'align': 'center'})
        light_green_format = workbook.add_format({'bg_color': '#CCFFCC'})

        # Set column widths for better readability
        worksheet.set_column('A:A', 20)
        worksheet.set_column('B:B', 30)
        worksheet.set_column('C:E', 20)
        worksheet.set_column('F:G', 30)
        worksheet.set_column('I:J', 20)
        worksheet.set_column('L:O', 20)
        worksheet.set_column('P:T', 30)

        # Highlight Stoqflow-specific columns with light green background
        worksheet.set_column('B:B', None, light_green_format)
        worksheet.set_column('D:E', None, light_green_format)

        # --- Sheet 1: Suppliers from Stoqflow ---
        # Write header row for supplier data
        worksheet.write(0, e, 'Naam', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Supplier Code', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'BTW nr', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Supplier Id', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Company Id', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Straat 1', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Straat 2', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Postcode', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Stad', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Staat', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Land', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Contact', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Naam', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Telefoon', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'E-mail', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Odoo Id', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Odoo Address', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Odoo ZIP', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Odoo City', bold_center_format)
        e = e + 1

        worksheet.write(0, e, '# matches found', bold_center_format)
        e = e + 1

        # Write supplier data rows and attempt to match each supplier to an Odoo partner by name
        i = 1
        for s in sups:
            e = 0

            # Write Stoqflow supplier fields
            worksheet.write(i, e, s.get('name'))
            e = e + 1

            worksheet.write(i, e, s.get('supplier_number'))
            e = e + 1

            worksheet.write(i, e, s.get('vat'))
            e = e + 1

            worksheet.write(i, e, s.get('_id'))
            e = e + 1

            worksheet.write(i, e, s.get('company_id'))
            e = e + 1

            # Write supplier address fields from the Stoqflow API response
            worksheet.write(i, e, s.get('address').get('address_1'))
            e = e + 1

            worksheet.write(i, e, s.get('address').get('address_2'))
            e = e + 1

            worksheet.write(i, e, s.get('address').get('postal_code'))
            e = e + 1

            worksheet.write(i, e, s.get('address').get('city'))
            e = e + 1

            worksheet.write(i, e, s.get('address').get('province_state'))
            e = e + 1

            worksheet.write(i, e, s.get('address').get('country'))
            e = e + 1

            worksheet.write(i, e, s.get('contact'))
            e = e + 1

            worksheet.write(i, e, s.get('name'))
            e = e + 1

            worksheet.write(i, e, s.get('phone'))
            e = e + 1

            worksheet.write(i, e, s.get('email'))
            e = e + 1

            # Search Odoo for a partner with the same name (case-insensitive)
            foundPartner = http.request.env['res.partner'].sudo().search([('name','=ilike',s.get('name').strip())])

            # If exactly one match found, write the Odoo partner data alongside
            if len(foundPartner) == 1:
                worksheet.write(i, e, foundPartner.id)
                e = e + 1

                worksheet.write(i, e, foundPartner.contact_address)
                e = e + 1

                worksheet.write(i, e, foundPartner.zip)
                e = e + 1

                worksheet.write(i, e, foundPartner.city)
                e = e + 1

                worksheet.write(i, e, len(foundPartner))
                e = e + 1
            else:
                # Skip Odoo columns and just write the match count
                e = e + 4

                worksheet.write(i, e, len(foundPartner))

            i = i + 1

        # --- Sheet 2: Clients from Stoqflow ---
        # Fetch all clients via GET /clients (paginated)
        clients = wsHandler.exportClients()

        e = 0
        worksheet = workbook.add_worksheet('Clients Webship')

        # Set column widths for the clients sheet
        worksheet.set_column('A:A', 20)
        worksheet.set_column('B:B', 30)
        worksheet.set_column('C:C', 20)
        worksheet.set_column('D:E', 30)
        worksheet.set_column('F:G', 30)
        worksheet.set_column('H:J', 20)
        worksheet.set_column('L:M', 20)
        worksheet.set_column('N:O', 30)
        worksheet.set_column('P:R', 20)
        worksheet.set_column('T:X', 20)
        worksheet.set_column('Y:AC', 30)

        # Highlight Stoqflow-specific columns with light green
        worksheet.set_column('B:B', 20, light_green_format)
        worksheet.set_column('D:E', 30, light_green_format)
        worksheet.set_column('L:R', 30, light_green_format)
        worksheet.set_column('S:S', 20, light_green_format)
        worksheet.set_column('T:T', 30, light_green_format)
        worksheet.set_column('U:W', 30, light_green_format)

        # Write header row: client info, billing address (BA), shipping address (SA), contact, matching
        worksheet.write(0, e, 'Client naam', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Client code', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'BTW nr', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Client Id', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Company Id', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'BA Straat 1', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'BA Straat 2', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'BA Postcode', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'BA Stad', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'BA Staat', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'BA Land', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'SA Naam', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'SA Company', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'SA Straat 1', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'SA Straat 2', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'SA Postcode', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'SA Stad', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'SA Staat', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'SA Land', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'SA Contact', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Contact naam', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Telefoon', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Mobile', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'E-mail', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Odoo Id', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Odoo Address', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Odoo ZIP', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Odoo City', bold_center_format)
        e = e + 1

        worksheet.write(0, e, '# matches found', bold_center_format)
        e = e + 1

        # Write client data rows with billing and optional shipping addresses
        i = 1
        for c in clients:
            e = 0

            # Write basic client fields from the Stoqflow API response
            worksheet.write(i, e, c.get('name'))
            e = e + 1

            worksheet.write(i, e, c.get('client_number'))
            e = e + 1

            worksheet.write(i, e, c.get('vat'))
            e = e + 1

            worksheet.write(i, e, c.get('_id'))
            e = e + 1

            worksheet.write(i, e, c.get('company_id'))
            e = e + 1

            # Write billing address (BA) fields
            worksheet.write(i, e, c.get('addresses').get('billing').get('address_1'))
            e = e + 1

            worksheet.write(i, e, c.get('addresses').get('billing').get('address_2'))
            e = e + 1

            worksheet.write(i, e, c.get('addresses').get('billing').get('postal_code'))
            e = e + 1

            worksheet.write(i, e, c.get('addresses').get('billing').get('city'))
            e = e + 1

            worksheet.write(i, e, c.get('addresses').get('billing').get('province_state'))
            e = e + 1

            worksheet.write(i, e, c.get('addresses').get('billing').get('country'))
            e = e + 1

            # Write shipping address (SA) fields if present
            if 'shipping' in c.get('addresses'):
                worksheet.write(i, e, c.get('addresses').get('shipping').get('name'))
            e = e + 1

            if 'shipping' in c.get('addresses'):
                worksheet.write(i, e, c.get('addresses').get('shipping').get('company'))
            e = e + 1

            if 'shipping' in c.get('addresses'):
                worksheet.write(i, e, c.get('addresses').get('shipping').get('address_1'))
            e = e + 1

            if 'shipping' in c.get('addresses'):
                worksheet.write(i, e, c.get('addresses').get('shipping').get('address_2'))
            e = e + 1

            if 'shipping' in c.get('addresses'):
                worksheet.write(i, e, c.get('addresses').get('shipping').get('postal_code'))
            e = e + 1

            if 'shipping' in c.get('addresses'):
                worksheet.write(i, e, c.get('addresses').get('shipping').get('city'))
            e = e + 1

            if 'shipping' in c.get('addresses'):
                worksheet.write(i, e, c.get('addresses').get('shipping').get('province_state'))
            e = e + 1

            if 'shipping' in c.get('addresses'):
                worksheet.write(i, e, c.get('addresses').get('shipping').get('country'))
            e = e + 1

            # Write contact info
            worksheet.write(i, e, c.get('contact'))
            e = e + 1

            worksheet.write(i, e, c.get('name'))
            e = e + 1

            worksheet.write(i, e, c.get('phone'))
            e = e + 1

            worksheet.write(i, e, c.get('mobile'))
            e = e + 1

            worksheet.write(i, e, c.get('email'))
            e = e + 1

            # Search Odoo for a partner with the same name (case-insensitive)
            foundPartner = http.request.env['res.partner'].sudo().search([('name', '=ilike', c.get('name').strip())])

            # If exactly one match, write the Odoo partner data alongside
            if len(foundPartner) == 1:
                worksheet.write(i, e, foundPartner.id)
                e = e + 1

                worksheet.write(i, e, foundPartner.contact_address)
                e = e + 1

                worksheet.write(i, e, foundPartner.zip)
                e = e + 1

                worksheet.write(i, e, foundPartner.city)
                e = e + 1

                worksheet.write(i, e, len(foundPartner))
                e = e + 1
            else:
                e = e + 4

                worksheet.write(i, e, len(foundPartner))

            i = i + 1

        # --- Sheet 3: Odoo Contacts ---
        # Lists all Odoo partners and tries to find matching Stoqflow records by name
        worksheet = workbook.add_worksheet('Contacten Odoo')

        worksheet.set_column('C:D', 30)
        worksheet.set_column('F:G', 30)
        worksheet.set_column('I:L', 30)
        worksheet.set_column('M:Q', 30)

        # Load all Odoo partners
        partners = http.request.env['res.partner'].sudo().search([])

        e = 0

        # Write header row for Odoo partner data
        worksheet.write(0, e, 'Id Odoo', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Is company', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Name', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Address', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Zip', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'City', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'State', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Country code', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Country', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Phone', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Mobile', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Email', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'VAT', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Webship code', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Webship address', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Webship zip', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching Webship city', bold_center_format)
        e = e + 1

        worksheet.write(0, e, 'Matching found', bold_center_format)
        e = e + 1

        # Write Odoo partner data and attempt to match each to a Stoqflow client or supplier
        i = 1
        for p in partners:
            e = 0

            # Write Odoo partner fields
            worksheet.write(i, e, p.id)
            e = e + 1

            worksheet.write(i, e, p.is_company)
            e = e + 1

            worksheet.write(i, e, p.name)
            e = e + 1

            worksheet.write(i, e, p.contact_address)
            e = e + 1

            worksheet.write(i, e, p.zip)
            e = e + 1

            worksheet.write(i, e, p.city)
            e = e + 1

            worksheet.write(i, e, p.state_id.name)
            e = e + 1

            worksheet.write(i, e, p.country_code)
            e = e + 1

            worksheet.write(i, e, p.country_id.name)
            e = e + 1

            worksheet.write(i, e, p.phone)
            e = e + 1

            worksheet.write(i, e, getattr(p, 'mobile', None))
            e = e + 1

            worksheet.write(i, e, p.email)
            e = e + 1

            worksheet.write(i, e, p.vat)
            e = e + 1

            # Search the previously fetched Stoqflow clients and suppliers for a name match
            nMatches = 0
            foundPers = None
            for pers in clients + sups:
                if p.name != False and pers.get('name').strip().lower() == p.name.strip().lower():
                    nMatches = nMatches + 1
                    foundPers = pers

            # If exactly one match, write the Stoqflow data (supplier or client format)
            if nMatches == 1:
                _logger.debug("Found matching person: %s", foundPers)
                if foundPers.get('client_number') == None:
                    # It's a supplier (uses 'address' dict, not 'addresses')
                    worksheet.write(i, e, foundPers.get('supplier_number'))
                    e = e + 1

                    worksheet.write(i, e, foundPers.get('address').get('address_1'))
                    e = e + 1

                    worksheet.write(i, e, foundPers.get('address').get('postal_code'))
                    e = e + 1

                    worksheet.write(i, e, foundPers.get('address').get('city'))
                    e = e + 1
                else:
                    # It's a client (uses 'addresses.billing' dict)
                    worksheet.write(i, e, foundPers.get('client_number'))
                    e = e + 1

                    worksheet.write(i, e, foundPers.get('addresses').get('billing').get('address_1'))
                    e = e + 1

                    worksheet.write(i, e, foundPers.get('addresses').get('billing').get('postal_code'))
                    e = e + 1

                    worksheet.write(i, e, foundPers.get('addresses').get('billing').get('city'))
                    e = e + 1

                worksheet.write(i, e, nMatches)
                e = e + 1
            else:
                # No unique match: skip address columns and just write the count
                e = e + 4
                worksheet.write(i, e, nMatches)
                e = e + 1
            i = i + 1
        workbook.close()

        # Return the completed Excel file as a downloadable HTTP response
        output.seek(0)
        response = request.make_response(output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition('report.xlsx'))
            ]
        )

        return response
