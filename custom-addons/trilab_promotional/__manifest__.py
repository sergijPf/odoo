{
    'name': 'Trilab Promotional',

    'summary': 'Trilab Promotional Customizations',

    'author': 'Trilab',
    'website': 'https://trilab.pl/',
    'category': 'Sales/Sales',
    'version': '1.2',

    'depends': [
        'sale_coupon',
    ],

    'data': [
        'security/ir.model.access.csv',

        'wizard/select_promotion_wizard.xml',

        'views/coupon_program_views.xml',
        'views/sale_order_views.xml',
    ],
    'license': 'OPL-1',
    'installable': True,
    'auto_install': False,
    'application': True,
}
