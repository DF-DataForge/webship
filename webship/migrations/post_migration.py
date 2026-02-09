from odoo import api, SUPERUSER_ID


def migrate(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Migrate product.product fields
    Product = env['product.product']
    products = Product.search([])

    for product in products:
        # Copy old field values to new fields, if old field has data
        None