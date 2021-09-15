# -*- coding: utf-8 -*-

from odoo import fields, models, _

class MagentoProductLogBook(models.Model):
    """
    Describes fields and methods for Magento products
    """
    _name = 'magento.product.log.book'
    _inherits = {'magento.product.product': 'magento_product_id'}
    _description = 'Product Log Book'
    _rec_name = 'magento_sku'

    magento_log_message = fields.Char(string="Product Error Messages")
    magento_log_message_conf = fields.Char(string="Product Category Error Messages")

    magento_product_id = fields.Many2one('magento.product.product', 'Magento Product', auto_join=True,
                                         ondelete="cascade")

