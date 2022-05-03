# -*- coding: utf-8 -*-

from odoo import models, fields


class MagentoFinancialStatus(models.Model):
    _name = "magento.financial.status"
    _description = "Magento Orders Processing Gateway by Financial Status"

    financial_status = fields.Selection([
        ('pending', 'Pending Orders'),
        ('processing', 'Processing Orders')
    ], string="Magento Order Status", help="Allowed Orders to import with next statuses: pending, processing")
    auto_workflow_id = fields.Many2one("sale.workflow.process", "Order Auto Workflow", ondelete="restrict")
    payment_method_id = fields.Many2one("magento.payment.method", "Payment Method", ondelete="restrict")
    magento_instance_id = fields.Many2one("magento.instance", string="Magento Instance", ondelete="cascade")
    active = fields.Boolean("Active", default=True)

    _sql_constraints = [('_magento_workflow_unique_constraint',
                         'unique(financial_status,magento_instance_id,payment_method_id)',
                         "Financial status must be unique in the list")]
