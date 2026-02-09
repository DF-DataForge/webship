# -*- coding: utf-8 -*-
{
    'name': "Koppeling Webship by Data Forge",

    'summary': "Koppeling met Webship",

    'author': "Data Forge",
    'website': "https://www.data-forge.be",


    'category': 'Uncategorized',
    'version': '1.0',
    'license': 'AGPL-3',
    #'post_init_hook': 'migrate',

    'depends': ['base', 'web', 'sale', 'product', 'purchase', 'stock'],
    'data': [
        'views/webship_menus.xml',
        'views/product_views.xml',
        'views/product_category_views.xml',
        'views/picking_views.xml',
        'views/partner_views.xml',
        'views/webship_property_views.xml',
        'views/location_views.xml',
        'views/product_packaging.xml',
        'views/res_config_settings_views.xml',
        'security/ir.model.access.csv',
        'views/cron.xml',
        'views/stock_quant_list.xml'
    ],

'application': True,
'installable': True,
'auto_install': False
}

