# -*- coding: utf-8 -*-

from odoo import models, fields


class ImportMagentoOrderStatus(models.Model):
    _name = "import.magento.order.status"
    _description = 'Order Status'

    name = fields.Char(string="Magento Status Name")
    status = fields.Char(string="Magento Order Status")
