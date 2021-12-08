# -*- coding: utf-8 -*-

from odoo import fields, models

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
                                         ondelete="cascade", required=True)
    magento_conf_prod = fields.Many2one(related="magento_product_id.magento_conf_product")


class MagentoStockLogBook(models.Model):
    """
    Describes fields and methods for Magento Stock Export
    """
    _name = 'magento.stock.log.book'
    _description = 'Stock Export Log Book'
    # _rec_name = 'magento_sku'

    magento_instance_id = fields.Many2one('magento.instance', string="Magento Instance")
    log_message = fields.Char(string="Stock Export Messages")
    active = fields.Boolean("Active", default=True)