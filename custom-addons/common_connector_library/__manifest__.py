# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
{
    'name': 'Common Connector Library customized',
    'version': '10.0',
    'category': 'Sales',
    'author': 'Emipro Technologies Pvt. Ltd. customized by White Label',
    'website': 'http://www.emiprotechnologies.com',
    'summary': """Develop generalize method to process different operations & auto workflow process to manage
    order process automatically.""",
    'depends': ['delivery', 'sale_stock', 'account', 'sale_management'],
    'data': ['security/ir.model.access.csv',
             'data/ir_sequence.xml',
             'data/ir_cron.xml',
             'view/stock_quant_package_view.xml',
             'view/common_log_book_view.xml',
             'view/account_fiscal_position.xml',
             'view/common_product_brand_view.xml',
             'view/common_product_image_ept.xml',
             'view/product_view.xml',
             'view/sale_order_view.xml',
             'view/sale_workflow_process_view.xml',
             'data/automatic_workflow_data.xml',
             'view/common_log_lines_ept.xml',
             'view/assets.xml',
    ],
    'qweb': [
        'static/src/xml/dashboard_widget.xml',
    ],
    'installable': True,
    'images': ['static/description/Common-Connector-Library-Cover.jpg'],
    #cloc settings
    'cloc_exclude': ['**/*.xml',],
}
