# -*- coding: utf-8 -*-

from odoo import models, fields


class IrCron(models.Model):
    _inherit = 'ir.cron'

    magento_instance_id = fields.Many2one('magento.instance', string="Cron Scheduler")
