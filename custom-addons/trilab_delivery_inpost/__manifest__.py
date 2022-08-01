# noinspection PyStatementEffect
{
    'name': "InPost Shipping (PL)",

    'summary': """
        Send packages by InPost service (PL)
        """,

    'description': """
        Delivery carrier interface for InPost (https://inpost.pl)
    """,

    'author': "Trilab",
    'website': "https://trilab.pl",

    'category': 'Warehouse',
    'version': '1.15',
    'depends': ['trilab_delivery_base'],

    'data': [
        'security/ir.model.access.csv',
        'data/delivery_inpost_data.xml',
        'views/res_config_settings_views.xml',
        'views/delivery_carrier.xml',
        'views/inpost_service.xml',
        'views/delivery_pickup.xml',
        'views/sale_views.xml',
        'views/stock_picking.xml',
        'views/website_sale.xml',
        'views/inpost_service.xml',
        'wizard/organization_views.xml'
    ],
    'images': [
        'static/description/banner.png'
    ],

    'assets': {
        'web.assets_frontend': [
            '/trilab_delivery_inpost/static/src/js/website_delivery_inpost.js',
        ],
    },

    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'OPL-1',
    'price': 150.0,
    'currency': 'EUR'
}
