# Post-migration script that runs after the module is installed or upgraded.
# Intended for migrating legacy field values to new field names on products.
from odoo import api, SUPERUSER_ID


def migrate(cr, registry):
    """Iterate over all products and copy legacy field values to the
    new Webship-prefixed fields. Currently a placeholder with no active migration."""
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Load all product records for field migration
    Product = env['product.product']
    products = Product.search([])

    for product in products:
        # Placeholder: copy old field values to new fields when needed
        None
