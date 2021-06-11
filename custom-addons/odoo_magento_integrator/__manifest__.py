{
    # App information
    'name': "Odoo Magento2 Integrator Customized",
    'version': '14.0.0.0',
    'category': 'Sales',
    'summary': """
        Odoo Magento 2.4 connector customization as per Smartino specific needs""",
    'author': "White Label Sp. z o.o.",
    'website': "https://ffflabel.com/",

    # Dependencies
    'depends': ['odoo_magento2_ept'],

    # Views
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],

    # Odoo Store Specific
    'installable': True,
    'auto_install': False,

}
