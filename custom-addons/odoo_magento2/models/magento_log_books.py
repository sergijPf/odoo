# -*- coding: utf-8 -*-

from odoo import fields, models


class MagentoProductLogBook(models.Model):
    _name = 'magento.product.log.book'
    _description = 'Product Log Book'
    _rec_name = 'magento_sku'

    magento_log_message = fields.Char(string="Product Error Messages")
    magento_log_message_conf = fields.Char(string="Config.Product Error Messages")
    magento_product_id = fields.Many2one('magento.product.product', 'Magento Product', ondelete="cascade")
    magento_conf_prod_id = fields.Many2one(related="magento_product_id.magento_conf_product_id", string="Conf.Product")
    magento_sku = fields.Char(related="magento_product_id.magento_sku")
    magento_instance_id = fields.Many2one(related="magento_product_id.magento_instance_id")
    magento_status = fields.Selection(related="magento_product_id.magento_status")
    magento_export_date = fields.Datetime(related="magento_product_id.magento_export_date")
    magento_product_name = fields.Char(related="magento_product_id.magento_product_name")


class MagentoOrdersLogBook(models.Model):
    _name = 'magento.orders.log.book'
    _description = 'Magento Sales Order Errors Log Book'
    _rec_name = 'magento_order_ref'

    active = fields.Boolean("Active", default=True)
    processing_error = fields.Boolean("Error in Order Processing", default=False)
    log_message = fields.Char(string="Order Error Messages")
    sale_order_id = fields.Many2one('sale.order', 'Odoo Order', ondelete="cascade")
    magento_order_ref = fields.Char(string="Magento Order Ref.")
    magento_website_id = fields.Many2one("magento.website", string="Website")
    magento_instance_id = fields.Many2one("magento.instance", string="Magento Instance")


class MagentoInvoicesLogBook(models.Model):
    _name = 'magento.invoices.log.book'
    _description = 'Magento Invoice Export errors log book'
    _rec_name = 'invoice_name'

    active = fields.Boolean("Active", default=True)
    log_message = fields.Char(string="Invoice Error Messages")
    invoice_id = fields.Many2one('account.move', 'Odoo Invoices', ondelete="cascade")
    invoice_name = fields.Char(related="invoice_id.name")
    magento_instance_id = fields.Many2one(related="invoice_id.magento_instance_id")


class MagentoShipmentsLogBook(models.Model):
    _name = 'magento.shipments.log.book'
    _description = 'Magento Shipment Export errors log book'
    _rec_name = 'picking_id'

    active = fields.Boolean("Active", default=True)
    log_message = fields.Char(string="Shipment Error Messages")
    picking_id = fields.Many2one('stock.picking', 'Odoo Shipments', ondelete="cascade")
    picking_name = fields.Char(related="picking_id.name")
    magento_instance_id = fields.Many2one(related="picking_id.magento_instance_id")


class MagentoStockLogBook(models.Model):
    _name = 'magento.stock.log.book'
    _description = 'Stock Export Log Book'
    _rec_name = 'batch'
    _order = "create_date desc"

    magento_instance_id = fields.Many2one('magento.instance', string="Magento Instance")
    batch = fields.Char(string="Export batch")
    log_message = fields.Char(string="Stock Export Messages")
    active = fields.Boolean("Active", default=True)


class MagentoPricesLogBook(models.Model):
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
