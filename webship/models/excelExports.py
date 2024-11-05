import xlsxwriter
import io

from odoo import fields, models, http
from odoo.http import request, content_disposition

from . import ws

class MyExcelDownloadController(http.Controller):

    #http://localhost:8069/web/download/excel?p=partner
    #http://192.168.91.129:8069/web/download/excel?p=partner

    @http.route('/web/download/excel', type='http', auth='user')
    def download_excel(self, **kwargs):
        # Create an in-memory output file for the new Excel file.
        output = io.BytesIO()

        print(kwargs)

        if 'p' not in kwargs:
            print('missing p')
            return

        if kwargs['p'] == 'partner':
            print('hi')

        # Create an Excel workbook and worksheet using xlsxwriter.
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet("Suppliers Webship")

        #prods = http.request.env['product.product'].sudo().search([])

        login = http.request.env['ir.config_parameter'].sudo().get_param('webship.username')
        pw = http.request.env['ir.config_parameter'].sudo().get_param('webship.password')
        base_url = http.request.env['ir.config_parameter'].sudo().get_param('webship.base_url')

        wsHandler = ws.WebShipHandler(login, pw, base_url)

        sups = wsHandler.exportSups()

        e = 0

        bold_center_format = workbook.add_format({'bold': True, 'align': 'center'})
        light_green_format = workbook.add_format({'bg_color': '#CCFFCC'})

        worksheet.set_column('A:A', 20)
        worksheet.set_column('B:B', 30)
        worksheet.set_column('C:E', 20)
        worksheet.set_column('F:G', 30)
        worksheet.set_column('I:J', 20)
        worksheet.set_column('L:O', 20)
        worksheet.set_column('P:T', 30)

        worksheet.set_column('B:B', None, light_green_format)
        worksheet.set_column('D:E', None, light_green_format)

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

        i = 1
        for s in sups:
            e = 0

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

            foundPartner = http.request.env['res.partner'].sudo().search([('name','=ilike',s.get('name').strip())])

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

        clients = wsHandler.exportClients()

        e = 0
        worksheet = workbook.add_worksheet('Clients Webship')

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

        worksheet.set_column('B:B', 20, light_green_format)
        worksheet.set_column('D:E', 30, light_green_format)
        worksheet.set_column('L:R', 30, light_green_format)
        worksheet.set_column('S:S', 20, light_green_format)
        worksheet.set_column('T:T', 30, light_green_format)
        worksheet.set_column('U:W', 30, light_green_format)

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

        i = 1
        for c in clients:
            e = 0

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

            foundPartner = http.request.env['res.partner'].sudo().search([('name', '=ilike', c.get('name').strip())])

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

        worksheet = workbook.add_worksheet('Contacten Odoo')

        worksheet.set_column('C:D', 30)
        worksheet.set_column('F:G', 30)
        worksheet.set_column('I:L', 30)
        worksheet.set_column('M:Q', 30)

        partners = http.request.env['res.partner'].sudo().search([])

        e = 0

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

        i = 1
        for p in partners:
            e = 0

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

            worksheet.write(i, e, p.mobile)
            e = e + 1

            worksheet.write(i, e, p.email)
            e = e + 1

            worksheet.write(i, e, p.vat)
            e = e + 1

            nMatches = 0
            foundPers = None
            for pers in clients + sups:
                if p.name != False and pers.get('name').strip().lower() == p.name.strip().lower():
                    nMatches = nMatches + 1
                    foundPers = pers

            if nMatches == 1:
                print(foundPers)
                if foundPers.get('client_number') == None:
                    worksheet.write(i, e, foundPers.get('supplier_number'))
                    e = e + 1

                    worksheet.write(i, e, foundPers.get('address').get('address_1'))
                    e = e + 1

                    worksheet.write(i, e, foundPers.get('address').get('postal_code'))
                    e = e + 1

                    worksheet.write(i, e, foundPers.get('address').get('city'))
                    e = e + 1
                else:
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
                e = e + 4
                worksheet.write(i, e, nMatches)
                e = e + 1
            i = i + 1
        workbook.close()

        # Set up the HTTP response headers for file download
        output.seek(0)
        response = request.make_response(output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition('report.xlsx'))
            ]
        )

        # Return the response, which will trigger the download
        return response