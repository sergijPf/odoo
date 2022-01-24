# -*- coding: utf-8 -*-

from odoo import fields, models

class MagentoOrdersLogBook(models.Model):
    """
    Describes fields and methods for Magento Sales Order Errors
    """
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
    """
    Describes fields and methods for Magento Invoice Export Errors
    """
    _name = 'magento.invoices.log.book'
    _description = 'Magento Invoice Export errors log book'
    _rec_name = 'invoice_name'

    active = fields.Boolean("Active", default=True)
    log_message = fields.Char(string="Invoice Error Messages")
    invoice_id = fields.Many2one('account.move', 'Odoo Invoices', ondelete="cascade")
    invoice_name = fields.Char(related="invoice_id.name")
    magento_instance_id = fields.Many2one(related="invoice_id.magento_instance_id")


class MagentoShipmentsLogBook(models.Model):
    """
    Describes fields and methods for Magento Shipment Export Errors
    """
    _name = 'magento.shipments.log.book'
    _description = 'Magento Shipment Export errors log book'
    _rec_name = 'picking_id'

    active = fields.Boolean("Active", default=True)
    log_message = fields.Char(string="Shipment Error Messages")
    picking_id = fields.Many2one('stock.picking', 'Odoo Shipments', ondelete="cascade")
    picking_name = fields.Char(related="picking_id.name")
    magento_instance_id = fields.Many2one(related="picking_id.magento_instance_id")