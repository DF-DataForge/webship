# -*- coding: utf-8 -*-
{
    'name': "Stoqflow demo: Woody's Skate Supply",
    'summary': "Demo company: a skateboard shop that uses Stoqflow (Webship) for e-fulfilment",
    'author': "Data Forge",
    'website': "https://www.data-forge.be",
    'category': 'Hidden',
    'version': '20.0.1.0',
    'description': """
Demo data for the Stoqflow integration (webship module)
========================================================

Installs a complete demo company, **Woody's Skate Supply BV**, a skateboard
shop that outsources warehousing and webshop fulfilment to Stoqflow.

Two flows are set up:

1. **Clothing - direct to Stoqflow.** Apparel (tees, hoodies, beanies,
   socks) is bought from the apparel supplier and delivered straight into the
   *Stoqflow Fulfilment* warehouse. Webshop sales ship from that warehouse.
2. **Complete skateboards - assembly flow.** Decks, trucks, wheels,
   bearings, grip tape and hardware are bought into the own *Skate Workshop*
   warehouse, assembled into complete boards with a manufacturing order,
   resupplied to the Stoqflow warehouse and sold through the webshop.

Do not install this on a production database: it changes the main company
and creates warehouses, products, partners and orders.
""",
    'license': 'AGPL-3',
    'depends': ['webship', 'sale_management', 'sale_stock', 'purchase_stock', 'mrp', 'website_sale', 'website_sale_stock', 'l10n_be'],
    'data': [
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'webship_demo_skateshop/static/src/scss/woody.scss',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
