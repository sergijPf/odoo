{
    # App information
    'name': "Smartino customization",
    'version': '14.0.0.1',
    'category': 'Sales',
    'summary': """
        Customization""",
    'author': "White Label Sp. z o.o.",
    'website': "https://ffflabel.com/",

    # Dependencies
    'depends': ['product', 'website_sale'],

    # Views
    'data': [

        'views/product_public_category_view.xml',
        'views/product_template_view.xml',
        'security/ir.model.access.csv',
    ],

    # Odoo Store Specific
    'installable': True,
    'auto_install': False,

}

