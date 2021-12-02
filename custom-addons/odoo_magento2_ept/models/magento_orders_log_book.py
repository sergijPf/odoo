# -*- coding: utf-8 -*-

from odoo import fields, models

class MagentoOrdersLogBook(models.Model):
    """
    Describes fields and methods for Magento Sales Orders Logged errors
    """
    _name = 'magento.orders.log.book'
    _description = 'Magento Orders Log Book'
    _rec_name = 'magento_order_ref'

    active = fields.Boolean("Active", default=True)
    processing_error = fields.Boolean("Error in processing", default=False)
    log_message = fields.Char(string="Order Error Messages")
    sale_order_id = fields.Many2one('sale.order', 'Odoo Order', ondelete="cascade")
    magento_order_ref = fields.Char(string="Magento Order Ref.")
    magento_website_id = fields.Many2one("magento.website", string="Website")
    magento_instance_id = fields.Many2one("magento.instance", string="Magento Instance")

