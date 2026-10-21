# -*- coding: utf-8 -*-
# Builds the "Woody's Skate Supply" demo company on install:
# master data (company, warehouses, partners, products, BoMs, routes) and
# a set of documents that walk through both Stoqflow flows:
#   1. clothing bought straight into the Stoqflow warehouse and sold from it
#   2. skateboard components bought into the own workshop, assembled into
#      complete boards, resupplied to Stoqflow and sold from there.
# The Odoo webshop sells from the Stoqflow warehouse, so every webshop
# order becomes a delivery out of Stoqflow (= a Stoqflow order).
import base64
import logging
from datetime import timedelta

from odoo import Command, fields
from odoo.tools.misc import file_open

_logger = logging.getLogger(__name__)

MODULE = 'webship_demo_skateshop'
COLOR_CODES = {'Black': 'BLK', 'White': 'WHT', 'Forest Green': 'GRN'}


def post_init_hook(env):
    company = _setup_company(env)
    _enable_features(env)
    _configure_stoqflow(env)
    wks, sqf = _setup_warehouses(env, company)
    partners = _setup_partners(env)
    products = _setup_products(env, partners, wks, sqf)
    _setup_images(env, company, products)
    website = _setup_webshop(env, company, products, sqf)
    products['website'] = website
    _run_clothing_flow(env, partners, products, sqf)
    _run_assembly_flow(env, partners, products, wks, sqf)
    _setup_orderpoints(env, products, wks, sqf)
    _set_process_codes(env)
    _logger.info("Woody's Skate Supply demo data installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xmlid(record, name):
    """Give a demo record an external ID so it can be found with env.ref()."""
    record.env['ir.model.data'].create({
        'module': MODULE,
        'name': name,
        'model': record._name,
        'res_id': record.id,
        'noupdate': True,
    })
    return record


def _image(name):
    """Base64 content of one of the demo illustrations (static/img)."""
    with file_open('%s/static/img/%s' % (MODULE, name), 'rb') as f:
        return base64.b64encode(f.read())


def _days_ago(days):
    return fields.Datetime.now() - timedelta(days=days)


def _validate(picking, date_done=None):
    """Process a picking in full, as if the warehouse handled every line."""
    picking.action_assign()
    for move in picking.move_ids:
        move.quantity = move.product_uom_qty
    picking.move_ids.picked = True
    picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
    if date_done:
        picking.date_done = date_done
        picking.move_ids.date = date_done
    return picking


def _purchase(env, vendor, lines, picking_type, days_ago=0, receive=False):
    po = env['purchase.order'].create({
        'partner_id': vendor.id,
        'user_id': env.ref('base.user_admin').id,
        'picking_type_id': picking_type.id,
        'date_order': _days_ago(days_ago),
        'order_line': [
            Command.create({'product_id': product.id, 'product_qty': qty})
            for product, qty in lines
        ],
    })
    po.button_confirm()
    if receive:
        for picking in po.picking_ids:
            _validate(picking, _days_ago(max(days_ago - 7, 0)))
    return po


def _sell(env, customer, lines, warehouse, days_ago=0, confirm=True, deliver=False, website=None):
    so = env['sale.order'].create({
        'partner_id': customer.id,
        # The hook runs as OdooBot; make the admin the salesperson so the
        # orders show up under the default "My Quotations" filter.
        'user_id': env.ref('base.user_admin').id,
        'warehouse_id': warehouse.id,
        'website_id': website.id if website else False,
        'date_order': _days_ago(days_ago),
        'order_line': [
            Command.create({'product_id': product.id, 'product_uom_qty': qty})
            for product, qty in lines
        ],
    })
    if confirm:
        so.action_confirm()
        so.date_order = _days_ago(days_ago)
    if deliver:
        for picking in so.picking_ids:
            _validate(picking, _days_ago(max(days_ago - 1, 0)))
    return so


def _manufacture(env, product, qty, warehouse, days_ago=0, produce=False):
    mo = env['mrp.production'].create({
        'product_id': product.id,
        'user_id': env.ref('base.user_admin').id,
        'product_qty': qty,
        'picking_type_id': warehouse.manu_type_id.id,
        'date_start': _days_ago(days_ago),
    })
    mo.action_confirm()
    mo.action_assign()
    if produce:
        mo.qty_producing = qty
        mo.move_raw_ids.picked = True
        mo.with_context(skip_backorder=True).button_mark_done()
        mo.date_finished = _days_ago(days_ago)
    return mo


# ---------------------------------------------------------------------------
# Company, features and Stoqflow settings
# ---------------------------------------------------------------------------

def _setup_company(env):
    company = env.ref('base.main_company')
    company.write({
        'name': "Woody's Skate Supply BV",
        'street': 'Kammenstraat 42',
        'zip': '2000',
        'city': 'Antwerpen',
        'country_id': env.ref('base.be').id,
        'phone': '+32 3 555 01 23',
        'email': 'hello@woodys-skate.example',
        'website': 'https://woodys-skate.example',
    })
    # Belgian chart of accounts and taxes (sets the company currency to EUR).
    # On a fresh database Odoo postpones loading the generic chart until the
    # registry is ready, which would overwrite this one: cancel that.
    if hasattr(env.registry, '_auto_install_template'):
        del env.registry._auto_install_template
    if company.chart_template != 'be_comp':
        env['account.chart.template'].try_loading('be_comp', company, install_demo=False)
    env['product.pricelist'].search([]).currency_id = env.ref('base.EUR')
    env.ref('base.user_admin').partner_id.write({'name': 'Woody Admin'})
    return company


def _enable_features(env):
    """Turn on the settings the demo relies on: variants, multi-warehouse
    with locations and routes, and manufacturing."""
    groups = [
        'product.group_product_variant',
        'stock.group_stock_multi_locations',
        'stock.group_stock_multi_warehouses',
        'stock.group_adv_location',
    ]
    env.ref('base.group_user').write({
        'implied_ids': [Command.link(env.ref(xid).id) for xid in groups],
    })


def _configure_stoqflow(env):
    """Fill in the non-secret Stoqflow settings. API credentials are left
    empty on purpose: enter your Stoqflow sandbox key in the settings."""
    params = env['ir.config_parameter'].sudo()
    for key, value in {
        'webship.base_url': 'https://api.stoqflow.com/',
        'webship.base_app_url': 'https://app.stoqflow.com/',
        'webship.sync_order': 'True',
        'webship.sync_products': 'True',
        'webship.sync_klanten': 'True',
        'webship.sync_leveranciers': 'True',
        'webship.default_status_order': 'ready-to-pick',
        'webship.default_status_po_order': 'ordered',
        'webship.show_parcels_tab': 'True',
        'webship.show_pick_analysis_tab': 'True',
    }.items():
        params.set_param(key, value)

    # Without credentials the sync crons would only flag errors; they are
    # switched off until a Stoqflow account is connected.
    for xid in ('ir_cron_sync_statussen', 'ir_cron_sync_statusP',
                'ir_cron_import_stock', 'ir_cron_daily_report'):
        cron = env.ref('webship.%s' % xid, raise_if_not_found=False)
        if cron:
            cron.active = False


def _setup_warehouses(env, company):
    """Skate Workshop: own warehouse where components are received and boards
    are assembled. Stoqflow Fulfilment: the e-fulfilment partner's warehouse,
    whose stock location is flagged as a Stoqflow location."""
    wks = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
    wks.write({'name': 'Skate Workshop H800', 'code': 'H800'})
    # Renaming the code does not rename existing sequences; align the MO prefix
    wks.manu_type_id.sequence_id.prefix = 'H800/MO/'
    _xmlid(wks, 'warehouse_workshop')

    stoqflow_partner = env['res.partner'].create({
        'name': 'Stoqflow Fulfilment Centre',
        'is_company': True,
        'comment': 'E-fulfilment partner that stores and ships our webshop orders.',
    })
    sqf = env['stock.warehouse'].create({
        'name': 'Stoqflow Fulfilment',
        'code': 'SQF',
        'company_id': company.id,
        'partner_id': stoqflow_partner.id,
        'manufacture_to_resupply': False,
        'resupply_wh_ids': [Command.link(wks.id)],
    })
    _xmlid(sqf, 'warehouse_stoqflow')
    # Pickings into this location become Stoqflow purchase orders,
    # pickings out of it become Stoqflow orders.
    sqf.lot_stock_id.df_is_webship_location = True
    # Sales are shipped by Stoqflow by default, also when entered in the backend
    env.ref('base.user_admin').property_warehouse_id = sqf
    return wks, sqf


# ---------------------------------------------------------------------------
# Partners
# ---------------------------------------------------------------------------

def _setup_partners(env):
    def country(code):
        return env.ref('base.%s' % code).id

    def company_partner(key, name, street, zip_code, city, code, email, **extra):
        partner = env['res.partner'].create(dict({
            'name': name, 'is_company': True, 'street': street, 'zip': zip_code,
            'city': city, 'country_id': country(code), 'email': email,
        }, **extra))
        return key, _xmlid(partner, 'partner_%s' % key)

    def person(key, name, street, zip_code, city, code, email, phone):
        partner = env['res.partner'].create({
            'name': name, 'street': street, 'zip': zip_code, 'city': city,
            'country_id': country(code), 'email': email, 'phone': phone,
        })
        return key, _xmlid(partner, 'partner_%s' % key)

    return dict([
        # Suppliers
        company_partner('threadworks', 'ThreadWorks Apparel Lda', 'Rua do Bonjardim 210', '4000-123',
                        'Porto', 'pt', 'orders@threadworks.example'),
        company_partner('maple', 'Baltic Maple Decks Sp. z o.o.', 'ul. Lesna 18', '80-001',
                        'Gdansk', 'pl', 'sales@balticmaple.example'),
        company_partner('truckline', 'Truckline Metalworks SL', 'Carrer de la Industria 77', '08025',
                        'Barcelona', 'es', 'orders@truckline.example'),
        company_partner('urethane', 'Urethane Roll Co. BV', 'Havenweg 5', '3011 AA',
                        'Rotterdam', 'nl', 'info@urethaneroll.example'),
        company_partner('gripgrit', 'Grip & Grit BV', 'Industrieweg 9', '9000',
                        'Gent', 'be', 'shop@gripgrit.example'),
        # Webshop customers
        person('lotte', 'Lotte Peeters', 'Oudaan 14', '2000', 'Antwerpen', 'be',
               'lotte.peeters@example.com', '+32 470 11 22 33'),
        person('jonas', 'Jonas de Vries', 'Bloemgracht 88', '1015 TL', 'Amsterdam', 'nl',
               'jonas.devries@example.com', '+31 6 1234 5678'),
        person('mia', 'Mia Schneider', 'Skalitzer Strasse 40', '10997', 'Berlin', 'de',
               'mia.schneider@example.com', '+49 151 2345 6789'),
        person('lucas', 'Lucas Martin', 'Rue de la Roquette 61', '75011', 'Paris', 'fr',
               'lucas.martin@example.com', '+33 6 12 34 56 78'),
        person('emma', 'Emma Janssens', 'Bondgenotenlaan 101', '3000', 'Leuven', 'be',
               'emma.janssens@example.com', '+32 485 66 77 88'),
        # B2B reseller
        company_partner('concrete', 'Concrete Wave Skateshop', 'Overpoortstraat 23', '9000',
                        'Gent', 'be', 'orders@concretewave.example', phone='+32 9 222 33 44'),
    ])


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def _setup_products(env, partners, wks, sqf):
    Category = env['product.category']
    root = Category.create({'name': 'Skateboarding'})
    cat_clothing = Category.create({'name': 'Clothing', 'parent_id': root.id})
    cat_components = Category.create({'name': 'Components', 'parent_id': root.id})
    cat_completes = Category.create({'name': 'Complete boards', 'parent_id': root.id})

    route_buy = env.ref('purchase_stock.route_warehouse0_buy')
    route_manufacture = env.ref('mrp.route_warehouse0_manufacture')
    route_resupply = env['stock.route'].search([
        ('supplied_wh_id', '=', sqf.id), ('supplier_wh_id', '=', wks.id),
    ], limit=1)

    size = env['product.attribute'].create({
        'name': 'Size',
        'value_ids': [Command.create({'name': s}) for s in ('S', 'M', 'L', 'XL')],
    })
    color = env['product.attribute'].create({
        'name': 'Color',
        'value_ids': [Command.create({'name': c}) for c in ('Black', 'White', 'Forest Green')],
    })

    def values(attribute, names):
        return attribute.value_ids.filtered(lambda v: v.name in names)

    def template(key, name, sku, category, cost, price, vendor, delay, weight, extra=None,
                 attributes=None):
        vals = {
            'name': name,
            'categ_id': category.id,
            'type': 'consu',
            'is_storable': True,
            'standard_price': cost,
            'list_price': price,
            'weight': weight,
            'seller_ids': [Command.create({
                'partner_id': vendor.id, 'price': cost, 'delay': delay, 'min_qty': 1,
            })],
        }
        if attributes:
            vals['attribute_line_ids'] = [
                Command.create({'attribute_id': attr.id, 'value_ids': [Command.set(vals_.ids)]})
                for attr, vals_ in attributes
            ]
        tmpl = env['product.template'].create(vals)
        _xmlid(tmpl, 'product_%s' % key)
        for variant in tmpl.product_variant_ids:
            attr_values = variant.product_template_attribute_value_ids.product_attribute_value_id
            suffix = '-'.join(
                [COLOR_CODES[v.name] for v in attr_values if v.attribute_id == color]
                + [v.name for v in attr_values if v.attribute_id == size]
            )
            variant.write(dict({'default_code': '%s-%s' % (sku, suffix) if suffix else sku},
                               **(extra or {})))
        return tmpl

    threadworks = partners['threadworks']
    clothing_flags = {
        'df_type': 'basic',
        'df_country_of_origin': 'PT',
    }
    tee = template('tee', "Woody's Logo Tee", 'WSS-TEE', cat_clothing, 6.50, 29.95, threadworks, 21, 0.18,
                   dict(clothing_flags, df_hs_code='61091000', df_length=30, df_width=25, df_height=2),
                   [(size, size.value_ids), (color, values(color, ('Black', 'White')))])
    hoodie = template('hoodie', 'Kickflip Hoodie', 'WSS-HOOD', cat_clothing, 18.00, 69.95, threadworks, 28, 0.65,
                      dict(clothing_flags, df_hs_code='61102000', df_length=35, df_width=30, df_height=6),
                      [(size, size.value_ids), (color, values(color, ('Black', 'Forest Green')))])
    beanie = template('beanie', "Woody's Beanie", 'WSS-BEANIE', cat_clothing, 4.20, 19.95, threadworks, 21, 0.08,
                      dict(clothing_flags, df_hs_code='65050090', df_length=22, df_width=20, df_height=3))
    socks = template('socks', "Woody's Crew Socks", 'WSS-SOCKS', cat_clothing, 2.10, 9.95, threadworks, 21, 0.06,
                     dict(clothing_flags, df_hs_code='61159500', df_length=25, df_width=10, df_height=2))

    # Components never enter the Stoqflow warehouse, so they are not synced
    component_flags = {'df_product_do_not_send_webship': True}
    comp = {}
    for key, name, sku, cost, vendor, delay, weight in [
        ('deck_80', 'Maple Deck 8.0" Street', 'WSS-DECK-80', 14.00, 'maple', 35, 1.30),
        ('deck_825', 'Maple Deck 8.25" Cruiser', 'WSS-DECK-825', 16.00, 'maple', 35, 1.40),
        ('truck_139', 'Truck 139 mm Raw', 'WSS-TRK-139', 11.50, 'truckline', 21, 0.36),
        ('truck_149', 'Truck 149 mm Black', 'WSS-TRK-149', 12.50, 'truckline', 21, 0.38),
        ('wheels_53', 'Street Wheels 53 mm 99A (set of 4)', 'WSS-WHL-53', 9.00, 'urethane', 14, 0.40),
        ('wheels_56', 'Cruiser Wheels 56 mm 85A (set of 4)', 'WSS-WHL-56', 11.00, 'urethane', 14, 0.48),
        ('bearings', 'ABEC-7 Bearings (set of 8)', 'WSS-BRG-7', 5.50, 'urethane', 14, 0.12),
        ('grip', 'Grip Tape Sheet 9 x 33"', 'WSS-GRIP', 2.80, 'gripgrit', 7, 0.10),
        ('hardware', 'Mounting Hardware 1" (set of 8)', 'WSS-HW-1', 0.90, 'gripgrit', 7, 0.05),
    ]:
        tmpl = template(key, name, sku, cat_components, cost, round(cost * 2.2, 2), partners[vendor],
                        delay, weight, component_flags)
        tmpl.write({'sale_ok': False, 'route_ids': [Command.set(route_buy.ids)]})
        comp[key] = tmpl.product_variant_id

    # Complete boards: manufactured in the workshop, resupplied to Stoqflow
    completes = {}
    for key, name, sku, price, parts in [
        ('street', 'Woody\'s Street Complete 8.0"', 'WSS-CMP-STREET-80', 119.95,
         [('deck_80', 1), ('truck_139', 2), ('wheels_53', 1), ('bearings', 1), ('grip', 1), ('hardware', 1)]),
        ('cruiser', 'Woody\'s Cruiser Complete 8.25"', 'WSS-CMP-CRUISER-825', 139.95,
         [('deck_825', 1), ('truck_149', 2), ('wheels_56', 1), ('bearings', 1), ('grip', 1), ('hardware', 1)]),
    ]:
        tmpl = env['product.template'].create({
            'name': name,
            'categ_id': cat_completes.id,
            'type': 'consu',
            'is_storable': True,
            'list_price': price,
            'weight': 3.2,
            'purchase_ok': False,
            'route_ids': [Command.set((route_manufacture | route_resupply).ids)],
            'description_sale': 'Assembled in our Antwerp workshop, ready to ride.',
        })
        _xmlid(tmpl, 'product_complete_%s' % key)
        tmpl.product_variant_id.write({
            'default_code': sku,
            'df_type': 'basic',
            'df_hs_code': '95069990',
            'df_country_of_origin': 'BE',
            'df_length': 82, 'df_width': 22, 'df_height': 12,
        })
        bom = env['mrp.bom'].create({
            'product_tmpl_id': tmpl.id,
            'product_qty': 1,
            'type': 'normal',
            'picking_type_id': wks.manu_type_id.id,
            'bom_line_ids': [
                Command.create({'product_id': comp[part].id, 'product_qty': qty})
                for part, qty in parts
            ],
        })
        _xmlid(bom, 'bom_complete_%s' % key)
        tmpl.button_bom_cost()
        completes[key] = tmpl.product_variant_id

    return {
        'tee': tee, 'hoodie': hoodie, 'beanie': beanie.product_variant_id,
        'socks': socks.product_variant_id, 'components': comp, 'completes': completes,
        'route_resupply': route_resupply,
    }


def _setup_webshop(env, company, products, sqf):
    """Odoo eCommerce webshop. It sells from the Stoqflow warehouse, so the
    stock shown online is the Stoqflow stock and every webshop order is
    delivered from Stoqflow."""
    website = env['website'].search([], limit=1)
    website.write({
        'name': "Woody's Skate Supply",
        'company_id': company.id,
        'warehouse_id': sqf.id,
    })
    _xmlid(website, 'website_shop')

    website.logo = _image('logo.png')
    _setup_theme(env)

    Category = env['product.public.category']
    boards = _xmlid(Category.create({
        'name': 'Complete skateboards', 'sequence': 1, 'image_1920': _image('banner_completes.jpg'),
    }), 'public_categ_boards')
    clothing = _xmlid(Category.create({
        'name': 'Clothing', 'sequence': 2, 'image_1920': _image('banner_clothing.jpg'),
    }), 'public_categ_clothing')
    for template in (products['tee'], products['hoodie'], products['beanie'].product_tmpl_id,
                     products['socks'].product_tmpl_id):
        template.write({'is_published': True, 'website_id': website.id,
                        'public_categ_ids': [Command.set(clothing.ids)]})
    for product in products['completes'].values():
        product.product_tmpl_id.write({'is_published': True, 'website_id': website.id,
                                       'public_categ_ids': [Command.set(boards.ids)]})

    _replace_placeholders(env, website, company)

    # Header menu: Home, Completes, Clothing, Shop, Contact
    Menu = env['website.menu']
    root = website.menu_id
    for sequence, name, url in [(15, 'Completes', '/shop/category/%s' % boards.id),
                                (16, 'Clothing', '/shop/category/%s' % clothing.id)]:
        Menu.create({'name': name, 'url': url, 'parent_id': root.id,
                     'website_id': website.id, 'sequence': sequence})
    return website


def _replace_placeholders(env, website, company):
    """Swap Odoo's placeholder contact details in header and footer templates
    for the company's own. Written as website-specific copies, like the
    website editor does."""
    replacements = {
        '+1 555-555-5556': company.phone,
        'info@yourcompany.example.com': company.email,
        'hello@mycompany.com': company.email,
        "We are a team of passionate people whose goal is to improve everyone's life through "
        "disruptive products. We build great products to solve your business problems.":
            "Woody's Skate Supply is a skate shop and workshop from Antwerp. We build complete "
            "skateboards by hand and design our own streetwear.",
        "Our products are designed for small to medium size companies willing to optimize "
        "their performance.":
            "Everything you order is stocked and shipped by our fulfilment partner Stoqflow, "
            "usually within 24 hours.",
        'Copyright &amp;copy; Company name': "Copyright &amp;copy; Woody's Skate Supply BV",
    }
    View = env['ir.ui.view']
    for placeholder in replacements:
        for view in View.search([('arch_db', 'ilike', placeholder), ('type', '=', 'qweb'),
                                 ('website_id', '=', False)]):
            arch = view.arch
            for old, new in replacements.items():
                arch = arch.replace(old, new)
            if arch != view.arch:
                view.with_context(website_id=website.id).write({'arch': arch})


def _setup_theme(env):
    """Brand colours, fonts and shapes, stored the same way the website
    editor stores them, so they can still be changed from the editor."""
    Assets = env['website.assets']
    Assets.make_scss_customization('/website/static/src/scss/options/colors/user_color_palette.scss', {
        'o-color-1': '#0A6CFF',  # primary: electric blue
        'o-color-2': '#00EEDD',  # secondary: cyan
        'o-color-3': '#F2F6FB',  # light background
        'o-color-4': '#FFFFFF',  # body background
        'o-color-5': '#0B1A7A',  # dark: navy
    })
    Assets.make_scss_customization('/website/static/src/scss/options/user_values.scss', {
        'google-fonts': "('Archivo Black', 'Space Grotesk')",
        'font': "'Space Grotesk'",
        'headings-font': "'Archivo Black'",
        'navbar-font': "'Space Grotesk'",
        'buttons-font': "'Space Grotesk'",
        'btn-border-radius': '2rem',
        'btn-border-radius-lg': '2rem',
        'btn-border-radius-sm': '2rem',
        'menu': '1',
        'footer': '5',
        'copyright': '5',
        'header-template': "'default'",
        'logo-height': '3.25rem',
    })


def _setup_images(env, company, products):
    """Attach the illustrations to the company and the products."""
    company.logo = _image('logo.png')

    def put(template, name):
        template.image_1920 = _image('%s.jpg' % name)

    put(products['tee'], 'tee_black')
    for variant in products['tee'].product_variant_ids:
        if 'White' in variant.product_template_attribute_value_ids.mapped('name'):
            variant.image_variant_1920 = _image('tee_white.jpg')
    put(products['hoodie'], 'hoodie_black')
    for variant in products['hoodie'].product_variant_ids:
        if 'Forest Green' in variant.product_template_attribute_value_ids.mapped('name'):
            variant.image_variant_1920 = _image('hoodie_green.jpg')
    put(products['beanie'].product_tmpl_id, 'beanie')
    put(products['socks'].product_tmpl_id, 'socks')
    for key, product in products['components'].items():
        put(product.product_tmpl_id, key)
    for key, product in products['completes'].items():
        put(product.product_tmpl_id, 'complete_%s' % key)


def _variant(template, *names):
    """Variant of a template matching all given attribute value names."""
    return template.product_variant_ids.filtered(
        lambda v: set(names) <= set(v.product_template_attribute_value_ids.mapped('name'))
    )[:1]


# ---------------------------------------------------------------------------
# Flow 1: clothing, bought and sold directly through Stoqflow
# ---------------------------------------------------------------------------

def _run_clothing_flow(env, partners, products, sqf):
    tee, hoodie = products['tee'], products['hoodie']
    beanie, socks = products['beanie'], products['socks']
    threadworks = partners['threadworks']

    # Opening stock: received in the Stoqflow warehouse a month ago
    opening = [(v, 12) for v in tee.product_variant_ids] \
        + [(v, 8) for v in hoodie.product_variant_ids] \
        + [(beanie, 40), (socks, 120)]
    _purchase(env, threadworks, opening, sqf.in_type_id, days_ago=40, receive=True)

    # Restock on its way: becomes a Stoqflow purchase order (inbound announcement)
    _purchase(env, threadworks, [
        (_variant(tee, 'Black', 'M'), 24),
        (_variant(tee, 'Black', 'L'), 24),
        (_variant(hoodie, 'Black', 'L'), 12),
        (socks, 240),
    ], sqf.in_type_id, days_ago=2)

    # Webshop orders shipped from Stoqflow
    _sell(env, partners['lotte'], [(_variant(tee, 'White', 'S'), 2), (beanie, 1)],
          sqf, days_ago=20, deliver=True, website=products['website'])
    _sell(env, partners['mia'], [(_variant(hoodie, 'Forest Green', 'M'), 1), (socks, 3)],
          sqf, days_ago=12, deliver=True, website=products['website'])
    _sell(env, partners['jonas'], [(_variant(hoodie, 'Black', 'L'), 1), (socks, 2)], sqf, days_ago=0,
          website=products['website'])
    # B2B order
    _sell(env, partners['concrete'], [
        (socks, 24),
        (_variant(tee, 'Black', 'M'), 6),
        (_variant(tee, 'Black', 'L'), 6),
        (beanie, 10),
    ], sqf, days_ago=1)
    # Quotation not yet confirmed
    _sell(env, partners['lucas'], [(_variant(tee, 'Black', 'XL'), 1)], sqf, confirm=False,
          website=products['website'])


# ---------------------------------------------------------------------------
# Flow 2: components bought, assembled into completes, sold through Stoqflow
# ---------------------------------------------------------------------------

def _run_assembly_flow(env, partners, products, wks, sqf):
    comp, completes = products['components'], products['completes']

    # Components received in the workshop
    for vendor, lines in [
        ('maple', [('deck_80', 30), ('deck_825', 20)]),
        ('truckline', [('truck_139', 60), ('truck_149', 40)]),
        ('urethane', [('wheels_53', 30), ('wheels_56', 20), ('bearings', 50)]),
        ('gripgrit', [('grip', 50), ('hardware', 50)]),
    ]:
        _purchase(env, partners[vendor], [(comp[k], q) for k, q in lines],
                  wks.in_type_id, days_ago=35, receive=True)
    # Reorder of trucks, still a request for quotation
    env['purchase.order'].create({
        'partner_id': partners['truckline'].id,
        'user_id': env.ref('base.user_admin').id,
        'picking_type_id': wks.in_type_id.id,
        'order_line': [Command.create({'product_id': comp['truck_139'].id, 'product_qty': 40})],
    })

    # Assembly in the workshop
    _manufacture(env, completes['street'], 20, wks, days_ago=25, produce=True)
    _manufacture(env, completes['cruiser'], 12, wks, days_ago=24, produce=True)
    _manufacture(env, completes['street'], 8, wks, days_ago=0)  # ready to produce

    # Resupply the Stoqflow warehouse: workshop -> transit -> Stoqflow
    _resupply(env, completes['street'], 15, sqf, products['route_resupply'], days_ago=22, receive=True)
    _resupply(env, completes['cruiser'], 10, sqf, products['route_resupply'], days_ago=22, receive=True)
    # Shipped from the workshop, still to be announced to Stoqflow
    _resupply(env, completes['cruiser'], 2, sqf, products['route_resupply'], days_ago=1, receive=False)

    # Webshop and B2B sales of complete boards, shipped by Stoqflow
    _sell(env, partners['emma'], [(completes['street'], 1), (products['beanie'], 1)],
          sqf, days_ago=15, deliver=True, website=products['website'])
    _sell(env, partners['lucas'], [(completes['cruiser'], 1)], sqf, days_ago=9, deliver=True,
          website=products['website'])
    _sell(env, partners['mia'], [(completes['cruiser'], 1), (products['socks'], 2)], sqf, days_ago=0,
          website=products['website'])
    _sell(env, partners['concrete'], [(completes['street'], 4), (completes['cruiser'], 2)], sqf, days_ago=1)


def _resupply(env, product, qty, sqf, route, days_ago=0, receive=False):
    """Replenish the Stoqflow warehouse from the workshop. The workshop leg is
    always shipped; the Stoqflow leg (the inbound announcement to Stoqflow) is
    only received when receive=True."""
    # A one-off manual orderpoint drives the resupply route; Odoo removes it
    # again once it has nothing left to order.
    orderpoint = env['stock.warehouse.orderpoint'].create({
        'product_id': product.id, 'warehouse_id': sqf.id, 'location_id': sqf.lot_stock_id.id,
        'product_min_qty': 0, 'product_max_qty': 0, 'trigger': 'manual',
        'route_id': route.id, 'qty_to_order_manual': qty,
    })
    existing = env['stock.picking'].search([])
    orderpoint.action_replenish()
    orderpoint.exists().unlink()
    pickings = env['stock.picking'].search([('id', 'not in', existing.ids)])
    outgoing = pickings.filtered(lambda p: not p.location_dest_id.df_is_webship_location)
    incoming = pickings - outgoing
    for picking in outgoing:
        _validate(picking, _days_ago(days_ago))
    if receive:
        for picking in incoming:
            _validate(picking, _days_ago(max(days_ago - 1, 0)))


def _setup_orderpoints(env, products, wks, sqf):
    """Replenishment rules with a manual trigger: they show up in the
    replenishment report but do not create orders by themselves."""
    Orderpoint = env['stock.warehouse.orderpoint']
    for product in products['completes'].values():
        Orderpoint.create({
            'product_id': product.id, 'warehouse_id': sqf.id, 'location_id': sqf.lot_stock_id.id,
            'product_min_qty': 4, 'product_max_qty': 12, 'trigger': 'manual',
            'route_id': products['route_resupply'].id,
        })
        # Workshop keeps a small buffer of assembled boards
        Orderpoint.create({
            'product_id': product.id, 'warehouse_id': wks.id, 'location_id': wks.lot_stock_id.id,
            'product_min_qty': 2, 'product_max_qty': 10, 'trigger': 'manual',
            'route_id': env.ref('mrp.route_warehouse0_manufacture').id,
        })
    for product in products['components'].values():
        Orderpoint.create({
            'product_id': product.id, 'warehouse_id': wks.id, 'location_id': wks.lot_stock_id.id,
            'product_min_qty': 10, 'product_max_qty': 40, 'trigger': 'manual',
            'route_id': env.ref('purchase_stock.route_warehouse0_buy').id,
        })
    # Clothing is bought straight into the Stoqflow warehouse
    clothing = products['tee'].product_variant_ids | products['hoodie'].product_variant_ids \
        | products['beanie'] | products['socks']
    for product in clothing:
        Orderpoint.create({
            'product_id': product.id, 'warehouse_id': sqf.id, 'location_id': sqf.lot_stock_id.id,
            'product_min_qty': 5, 'product_max_qty': 24, 'trigger': 'manual',
            'route_id': env.ref('purchase_stock.route_warehouse0_buy').id,
        })


def _set_process_codes(env):
    """Mark history as handled outside the integration so only the open
    documents are pending for Stoqflow."""
    Picking = env['stock.picking']
    for picking in Picking.search([]):
        involves_stoqflow = (picking.location_id.df_is_webship_location
                             or picking.location_dest_id.df_is_webship_location)
        if not involves_stoqflow:
            code = 'NA'
        elif picking.state in ('done', 'cancel'):
            code = 'M'
        else:
            code = 'P'
        if picking.df_process_code != code:
            picking.df_process_code = code
