{
    'name': 'Smartino Common Customizations',
    'version': '2.69',
    'author': 'Trilab',
    'website': "https://trilab.pl",
    'description': 'Module for common customization',
    'depends': [
        'product',
        'delivery',
        'website_sale',
        'stock_request',
        'stock',
        'mrp',
        'website_sale'
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',

        'views/assets.xml',
        'views/product_views.xml',
        'views/res_partner_views.xml',
        'views/sale_portal_templates.xml',
        'views/sale_views.xml',
        'views/sale_order_line_views.xml',
        'views/stock_request_views.xml',
        'views/product_attribute_views.xml',
        'views/stock_views.xml',
        'views/gus_prodpol_views.xml',
        'views/website_templates.xml',
        'views/res_config_settings_views.xml',

        'report/product_sticker_report.xml',
        'report/location_barcode_report.xml',

        'wizard/change_category_wizard.xml',
        'wizard/change_product_status_wizard.xml',
        'wizard/change_picking_type_wizard.xml',
    ],
    'qweb': [
        'static/src/xml/menu.xml',
        'static/src/xml/quantity_validation_alert.xml',
        'static/src/xml/add_to_cart_popup.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
