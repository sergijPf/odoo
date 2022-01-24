# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""For Odoo Magento2 Connector Module"""
from odoo import models, fields


class IrCron(models.Model):
    """Inherited for identifying Magento's cron."""
    _inherit = 'ir.cron'

    magento_instance_id = fields.Many2one('magento.instance', string="Cron Scheduler")
