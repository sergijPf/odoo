# noinspection PyStatementEffect
{
    'name': "Trilab Delivery Base Module",

    'summary': """
        Required for all shipping modules
        """,

    'description': """
        used by Trilab's shipping modules:
        * DPD
        * DHL24
        * Inpost
    """,

    'author': "Trilab",
    'website': "https://trilab.pl",

    'category': 'Inventory/Delivery',
    'version': '1.22',
    'depends': ['stock', 'sale', 'sale_stock', 'delivery', 'mail'],

    'data': [
        # 'data/payment_acquirer_data.xml',
        'security/ir.model.access.csv',
        'views/stock_picking.xml',
        'views/delivery_label.xml',
        'views/delivery_pickup.xml',
        'views/delivery_carrier.xml',
        'views/stock_package_type.xml',
        'report/report_cmr.xml',
    ],
    'images': [
        'static/description/banner.png'
    ],
    'assets': {
        'web.report_assets_common': [
            '/trilab_delivery_base/static/src/scss/cmr_report.scss'
        ]
    },
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'OPL-1',
    'price': 50.0,
    'currency': 'EUR'
}
