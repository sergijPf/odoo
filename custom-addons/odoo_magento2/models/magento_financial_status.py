# -*- coding: utf-8 -*-

from odoo import models, fields


class MagentoFinancialStatus(models.Model):
    _name = "magento.financial.status"
    _description = 'Magento Financial Status'

    def _default_payment_term(self):
        payment_term = self.env.ref("account.account_payment_term_immediate")

        return payment_term.id if payment_term else False

    financial_status = fields.Selection([
        ('not_paid', 'Pending Orders'),
        ('processing_paid', 'Processing orders with paid Invoice')
    ], default="processing_paid")
    auto_workflow_id = fields.Many2one("sale.workflow.process", "Auto Workflow", ondelete="restrict")
    payment_method_id = fields.Many2one("magento.payment.method", "Payment Method", ondelete="restrict")
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term', default=_default_payment_term,
                                      ondelete="restrict")
    magento_instance_id = fields.Many2one("magento.instance", string="Magento Instance", ondelete="cascade")
    active = fields.Boolean("Active Financial Status", default=True)

    _sql_constraints = [('_magento_workflow_unique_constraint',
                         'unique(financial_status,magento_instance_id,payment_method_id)',
                         "Financial status must be unique in the list")]

    # def create_financial_status(self, magento_instance):
    #     for payment_method in magento_instance.payment_method_ids:
    #         for status in ['not_paid', 'processing_paid']:
    #             domain = [('magento_instance_id', '=', magento_instance.id),
    #                       ('payment_method_id', '=', payment_method.id),
    #                       ('financial_status', '=', status)]
    #
    #             fin_status = self.with_context(active_test=False).search(domain)
    #
    #             if fin_status:
    #                 fin_status.active = True
    #                 continue
    #
    #             workflow = payment_method.magento_workflow_process_id
    #             auto_workflow_record = workflow if workflow else self.env.ref("odoo_magento2.automatic_validation")
    #
    #             paym_term = payment_method.payment_term_id
    #             payment_term_id = paym_term if paym_term else self.env.ref("account.account_payment_term_immediate")
    #
    #             self.create({
    #                 'magento_instance_id': magento_instance.id,
    #                 'auto_workflow_id': auto_workflow_record.id,
    #                 'payment_method_id': payment_method.id,
    #                 'financial_status': status,
    #                 'payment_term_id': payment_term_id.id
    #             })
