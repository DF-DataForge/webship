# -*- coding: utf-8 -*-
# Module manifest for the Stoqflow integration module.
# This file declares the module metadata, dependencies, and data files
# that Odoo loads when installing or upgrading the module.
{
    'name': "Koppeling Stoqflow by Data Forge",

    'summary': "Koppeling met Stoqflow",

    'author': "Data Forge",
    'website': "https://www.data-forge.be",

    'category': 'Uncategorized',
    'version': '1.0',
    'description': """
Stoqflow Integration Module v1.0
=================================

This module provides a complete integration between Odoo and Stoqflow (Webship)
for managing e-commerce logistics and warehouse operations.

Features:
- Product synchronization with Stoqflow
- Partner and customer data exchange
- Stock picking and delivery management with parcel tracking
- Warehouse and location mapping
- Product packaging and category configuration
- Automated synchronization via scheduled cron jobs
- Dashboard and reporting for Stoqflow orders, products, and partners
- JSON history tracking for API communication logging
""",
    'license': 'AGPL-3',

    # Module dependencies: base Odoo modules required for this integration
    'depends': ['base', 'web', 'sale', 'product', 'purchase', 'stock', 'delivery'],

    # Data files loaded in order: menus, views, security rules, cron jobs
    'data': [
        'security/ir.model.access.csv',
        'views/stoqflow_dashboard_views.xml',
        'views/stoqflow_product_report_views.xml',
        'views/stoqflow_partner_report_views.xml',
        'views/webship_menus.xml',
        'views/product_views.xml',
        'views/product_category_views.xml',
        'views/picking_views.xml',
        'views/partner_views.xml',
        'views/webship_property_views.xml',
        'views/location_views.xml',
        'views/product_packaging.xml',
        'views/res_config_settings_views.xml',
        'views/cron.xml',
        'views/stock_quant_list.xml',
        'views/json_history_views.xml',
        'wizards/select_stoqflow_client_views.xml'
    ],

'application': True,
'installable': True,
'auto_install': False
}
