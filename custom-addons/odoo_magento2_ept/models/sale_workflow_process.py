# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api


class SaleWorkflowProcess(models.Model):
    _name = "sale.workflow.process.ept"
    _description = "sale workflow process"

    @api.model
    def _default_journal(self):
        """
        It will return sales journal of company passed in context or user's company.
        """
        account_journal_obj = self.env['account.journal']
        company_id = self._context.get('company_id', self.env.company.id)
        domain = [('type', '=', "sale"), ('company_id', '=', company_id)]
        return account_journal_obj.search(domain, limit=1)

    name = fields.Char(size=64)
    validate_order = fields.Boolean("Confirm Quotation", default=False,
                                    help="If it's checked, Order will be Validated.")
    create_invoice = fields.Boolean('Create & Validate Invoice', default=False,
                                    help="If it's checked, Invoice for Order will be Created and Posted.")
    sale_journal_id = fields.Many2one('account.journal', string='Sales Journal', default=_default_journal,
                                      domain=[('type', '=', 'sale')])
    picking_policy = fields.Selection([('direct', 'Deliver each product when available'),
                                       ('one', 'Deliver all products at once')], string='Shipping Policy',
                                      default="one")
    magento_order_type = fields.Many2one('import.magento.order.status', 'Magento Order Status',
                                         help="Select order status for that you want to create auto workflow.")

    @api.onchange("validate_order")
    def onchange_validate_order(self):
        """
        Onchange of Confirm Quotation field.
        If 'Confirm Quotation' is unchecked, the 'Create & Validate Invoice' will be unchecked too.
        """
        for record in self:
            if not record.validate_order:
                record.create_invoice = False


    @api.model
    def auto_workflow_process(self, auto_workflow_process_id=False, order_ids=[]):
        """
        This method will find draft sale orders which are not having invoices yet, confirmed it and done the payment
        according to the auto invoice workflow configured in sale order
        :param auto_workflow_process_id: auto workflow process id
        :param order_ids: ids of sale orders
        """
        sale_order_obj = self.env['sale.order']
        if not auto_workflow_process_id:
            work_flow_process_records = self.search([])
        else:
            work_flow_process_records = self.browse(auto_workflow_process_id)

        if not order_ids:
            orders = sale_order_obj.search([('auto_workflow_process_id', 'in', work_flow_process_records.ids),
                                            ('state', 'not in', ('done', 'cancel', 'sale')),
                                            ('invoice_status', '!=', 'invoiced')])
        else:
            orders = sale_order_obj.search([('auto_workflow_process_id', 'in', work_flow_process_records.ids),
                                            ('id', 'in', order_ids)])
        try:
            orders.process_orders_and_invoices()
        except Exception as err:
            return err

        return ''
