{
    # App information
    'name': "Smartino Magento2 connector",
    'version': '15.0.1',
    'category': 'Sales',
    'summary': 'Odoo - Magento2 Connector',

    # Dependencies
    'depends': ['delivery', 'sale_stock', 'account', 'sale_management'],
    # 'depends': ['delivery', 'sale_stock', 'account', 'sale_management', 'smartino_common'],
    # Views
    'data': [
        'security/security.xml',
        'data/import_order_status.xml',
        'data/ir_cron_.xml',
        'data/magento_data_cron.xml',
        'views/magento_instance_view.xml',
        'views/magento_website_view.xml',
        'views/magento_storeview_view.xml',
        'views/magento_inventory_locations_view.xml',
        'views/magento_payment_method_view.xml',
        'views/delivery_carrier_view.xml',
        'wizard_views/magento_import_export_operation_view.xml',
        'wizard_views/magento_cron_configuration_view.xml',
        'wizard_views/res_config_magento_instance.xml',
        'wizard_views/res_config_settings.xml',
        'views/magento_product_product_view.xml',
        'views/magento_res_partner_view.xml',
        'views/sale_order_view.xml',
        'views/sale_order_cancel_view.xml',
        'views/stock_picking_view.xml',
        'views/account_move_view.xml',
        'views/financial_status_view.xml',
        'views/magento_delivery_carrier.xml',
        'views/magento_product_category_view.xml',
        'views/magento_orders_log_book_view.xml',
        'views/magento_product_log_book_view.xml',
        'views/magento_stock_log_book_view.xml',
        'views/magento_prices_log_book_view.xml',
        'views/magento_configurable_product_view.xml',
        'views/product_attribute_view.xml',
        'views/product_product_view.xml',
        'views/product_public_category_view.xml',
        'views/config_product_attribute_view.xml',
        'views/magento_customer_groups_view.xml',
        'views/magento_invoices_log_book_view.xml',
        'views/magento_shipments_log_book_view.xml',
        'views/account_fiscal_position.xml',
        'views/stock_quant_package_view.xml',
        'views/sale_workflow_process_view.xml',
        'views/product_template_view.xml',
        'views/product_category_view.xml',
        'wizard_views/magento_instance_configuration_wizard.xml',
        # 'wizard_views/magento_product_category_update_view.xml',
        'wizard_views/magento_product_categories_configuration_view.xml',
        'wizard_views/config_product_attributes_update_view.xml',
        'wizard_views/magento_customer_group_update_view.xml',
        'data/ecommerce_data.xml',
        'data/automatic_workflow_data_.xml',
        'security/ir.model.access.csv'
    ],

    "assets": {
      "web.assets_backend": [
          "odoo_magento2/static/src/js/magento_icon_view.js"
      ]
    },

    # Odoo Store Specific
    'images': ['static/description/Magento-2-v14.png'],
    'installable': True,
    'auto_install': False,
    'application': True
}
