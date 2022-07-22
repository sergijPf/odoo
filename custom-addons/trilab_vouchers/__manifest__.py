{
    'name': 'Trilab Vouchers',
    'summary': 'Trilab Vouchers',
    'author': 'Trilab',
    'website': 'https://trilab.pl/',
    'category': 'Sales/Sales',
    'version': '1.2.1',
    'depends': [
        'pos_sale',
        'sale_coupon',
    ],

    'data': [
        'views/coupon_program_views.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'OPL-1',
}
