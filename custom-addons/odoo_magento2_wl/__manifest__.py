{
    # App information
    'name': "Odoo Magento2 Integrator Customized",
    'version': '14.0.0.3',
    'category': 'Sales',
    'summary': """
        Odoo Magento 2.4 connector customization as per Smartino specific case""",
    'author': "White Label Sp. z o.o.",
    'website': "https://ffflabel.com/",

    # Dependencies
    'depends': ['odoo_magento2_ept'],

    # Views
    'data': [
        'security/security_rules.xml',
        'views/sale_order_view.xml',
        'views/magento_product_product_view.xml',
        'views/magento_product_template_view.xml',
        'views/product_template_view.xml',
        'views/product_view.xml',
        'views/product_log_book_view.xml',
        'views/product_category_view.xml',
        'views/res_config_settings.xml',
        'views/magento_instance_view.xml',
        'wizard/magento_product_category_update_view.xml',
        'wizard/magento_cron_configuration_view.xml',
        'security/ir.model.access.csv',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],

    # Odoo Store Specific
    'installable': True,
    'auto_install': False,

}

