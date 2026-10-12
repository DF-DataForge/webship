from odoo import fields, models


class StoqflowCourier(models.Model):
    _name = 'stoqflow.courier'
    _description = 'Stoqflow Courier'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True)

    _code_unique = models.Constraint('UNIQUE(code)', 'Courier code must be unique!')
