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
    magento_conf_prod_id = fields.Many2one(related="magento_product_id.magento_conf_product_id")


class MagentoStockLogBook(models.Model):
    """
    Describes fields and methods for Magento Stock Export
    """
    _name = 'magento.stock.log.book'
    _description = 'Stock Export Log Book'
    _rec_name = 'batch'
    _order = "create_date desc"

    magento_instance_id = fields.Many2one('magento.instance', string="Magento Instance")
    batch = fields.Char(string="Export batch")
    log_message = fields.Char(string="Stock Export Messages")
    active = fields.Boolean("Active", default=True)


class MagentoPricesLogBook(models.Model):
    """
    Describes fields and methods for Magento Product Prices Export
    """
    _name = 'magento.prices.log.book'
    _description = 'Magento Product Prices Export Log Book'
    _rec_name = 'magento_sku'
    _order = "create_date desc"

    magento_instance_id = fields.Many2one('magento.instance', string="Magento Instance")
    magento_storeview_id = fields.Many2one('magento.storeview', string="Magento Storeview")
    storeview_name = fields.Char(related='magento_storeview_id.name', string="Magento Storeview Name")
    magento_sku = fields.Char("Magento sku")
    log_message = fields.Char(string="Price Export Messages")
    batch = fields.Char(string="Export batch")
    active = fields.Boolean("Active", default=True)