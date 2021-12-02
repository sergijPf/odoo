# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""For Odoo Magento2 Connector Module"""
from odoo import models, fields


class IrCron(models.Model):
    """Inherited for identifying Magento's cron."""
    _inherit = 'ir.cron'

    # magento_product_import_cron = fields.Boolean('Magento Product Cron')
    # magento_import_order_cron = fields.Boolean('Magento Order Cron')
    magento_instance_id = fields.Many2one('magento.instance', string="Cron Scheduler")
