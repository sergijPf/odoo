{
    # App information
    'name': "Odoo Magento 2 Connector customized",
    'version': '10.0',
    'category': 'Sales',
    'summary': 'Odoo Magento 2 Connector to integrate Magento 2.4 website with Odoo '
               'as per Smartino specifications',
    # Author
    'author': 'Emipro Technologies Pvt. Ltd. Customized by White Label',
    'website': 'http://www.emiprotechnologies.com/',
    'maintainer': 'White Label',

    # Dependencies
    'depends': ['common_connector_library'],
    # Views
    'data': [
        'security/security.xml',
        # 'security/security_rules.xml',
        'data/import_order_status.xml',
        'views/common_log_book_ept.xml',
        'views/magento_instance_view.xml',
        'views/magento_website_view.xml',
        'views/magento_storeview_view.xml',
        'views/magento_inventory_locations_view.xml',
        'views/magento_payment_method_view.xml',
        'views/delivery_carrier_view.xml',
        'views/view_magento_process_log.xml',
        'wizard_views/magento_import_export_operation_view.xml',
        'wizard_views/magento_cron_configuration_view.xml',
        'wizard_views/res_config_magento_instance.xml',
        'wizard_views/res_config_settings.xml',
        'data/ir_sequence_data.xml',
        'views/magento_product_product_view.xml',
        'views/magento_product_template_view.xml',
        'views/magento_product_image_view.xml',
        'wizard_views/magento_queue_process_wizard_view.xml',
        'views/res_partner_view.xml',
        'views/sale_order_view.xml',
        'views/sale_order_cancel_view.xml',
        'views/magento_order_data_queue_ept.xml',
        'views/magento_order_data_queue_line_ept.xml',
        # 'views/sync_import_magento_product_queue.xml',
        # 'views/sync_import_magento_product_queue_line.xml',
        'data/magento_data_cron.xml',
        'data/ir_cron_data.xml',
        'views/stock_picking_view.xml',
        'views/account_move_view.xml',
        'views/magento_dashboard_view.xml',
        'views/financial_status_view.xml',
        'views/magento_delivery_carrier.xml',
        # 'views/magento_instances_onboarding_panel_view.xml',
        'views/magento_product_category_view.xml',
        'views/magento_tax_class.xml',
        'views/magento_attribute_set.xml',
        'views/magento_attribute_group.xml',
        'views/magento_attribute_option.xml',
        'views/magento_product_attribute_view.xml',
        'views/product_category_view.xml',
        'views/magento_product_log_book_view.xml',
        'wizard_views/magento_instance_configuration_wizard.xml',
        # 'wizard_views/basic_configuration_onboarding.xml',
        # 'wizard_views/financial_status_onboarding_view.xml',
        # 'wizard_views/magento_onboarding_confirmation_ept.xml',
        # 'wizard_views/magento_export_product_ept.xml',
        'wizard_views/magento_product_category_update_view.xml',
        # 'data/ecommerce_data.xml',
        'security/ir.model.access.csv',
        'data/update_magento_partner.xml'
    ],
    'qweb': [
        'static/src/xml/*.xml',
    ],

    # Odoo Store Specific

    'images': ['static/description/Magento-2-v14.png'],
    'installable': True,
    'auto_install': False,
    'application': True
}
