{
    # App information
    'name': "Odoo Magento2 Integrator Customized",
    'version': '14.0.0.0',
    'category': 'Sales',
    'summary': """
        Odoo Magento 2.4 connector customization as per Smartino specific case""",
    'author': "White Label Sp. z o.o.",
    'website': "https://ffflabel.com/",

    # Dependencies
    'depends': ['odoo_magento2_ept'],

    # Views
    'data': [
        # 'security/ir.model.access.csv',
        'views/sale_order_view.xml',
        'views/magento_product_product_view.xml',
        'views/magento_product_template_view.xml',
        'views/product_template_view.xml',
        'views/product_view.xml',
        'views/product_category_view.xml',
        'views/res_config_settings.xml',
        'wizard_views/magento_import_export_operation_view.xml',
        'wizard_views/magento_cron_configuration_view.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],

    # Odoo Store Specific
    'installable': True,
    'auto_install': False,

}
