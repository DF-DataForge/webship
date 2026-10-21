from odoo import models, fields


class WebshipParcel(models.Model):
    _name = 'webship.parcel'
    _description = 'Stoqflow Parcel'
    _order = 'df_number'

    picking_id = fields.Many2one('stock.picking', string='Picking', required=True, ondelete='cascade', index=True)
    df_stoqflow_id = fields.Char('Stoqflow Parcel ID')
    df_number = fields.Integer('Parcel #')
    df_tracking_number = fields.Char('Tracking Number')
    df_tracking_url = fields.Char('Tracking URL')
    df_label_url = fields.Char('Label URL')
    df_invoice_url = fields.Char('Invoice URL')
    df_provider = fields.Char('Provider')
    df_provider_id = fields.Char('Provider ID')
    df_weight = fields.Float('Weight (kg)')
    df_width = fields.Float('Width (cm)')
    df_height = fields.Float('Height (cm)')
    df_length = fields.Float('Length (cm)')
    df_shipping_cost = fields.Float('Shipping Cost', digits=(12, 4))

    # Shipping address fields
    df_shipping_name = fields.Char('Ship To Name')
    df_shipping_company = fields.Char('Ship To Company')
    df_shipping_address = fields.Char('Ship To Address')
    df_shipping_postal_code = fields.Char('Ship To Postal Code')
    df_shipping_city = fields.Char('Ship To City')
    df_shipping_country = fields.Char('Ship To Country')

    df_content_ids = fields.One2many('webship.parcel.content', 'parcel_id', string='Contents')
    df_resource_ids = fields.One2many('webship.parcel.resource', 'parcel_id', string='Resources')


class WebshipParcelContent(models.Model):
    _name = 'webship.parcel.content'
    _description = 'Stoqflow Parcel Content Line'

    parcel_id = fields.Many2one('webship.parcel', string='Parcel', required=True, ondelete='cascade', index=True)
    df_stoqflow_product_id = fields.Char('Stoqflow Product ID')
    df_sku = fields.Char('SKU')
    df_description = fields.Char('Description')
    df_quantity = fields.Float('Quantity')
    df_weight = fields.Float('Weight (kg)')
    df_hs_code = fields.Char('HS Code')
    df_origin_country = fields.Char('Origin Country')
    df_value = fields.Float('Value')


class WebshipParcelResource(models.Model):
    _name = 'webship.parcel.resource'
    _description = 'Stoqflow Parcel Resource'

    parcel_id = fields.Many2one('webship.parcel', string='Parcel', required=True, ondelete='cascade', index=True)
    df_stoqflow_id = fields.Char('Stoqflow Resource ID')
    df_name = fields.Char('Name')
    df_quantity = fields.Float('Quantity')
