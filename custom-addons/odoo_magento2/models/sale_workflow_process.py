# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleWorkflowProcess(models.Model):
    _name = "sale.workflow.process"
    _description = "sale workflow process"

    @api.model
    def _default_sales_journal(self):
        account_journal_obj = self.env['account.journal']
        company_id = self._context.get('company_id', self.env.company.id)
        domain = [('type', '=', "sale"), ('company_id', '=', company_id)]

        return account_journal_obj.search(domain, limit=1)

    name = fields.Char(size=64)
    validate_order = fields.Boolean("Confirm Quotation", default=False,
                                    help="If it's checked, Order will be Validated automatically.")
    create_invoice = fields.Boolean('Create & Validate Invoice', default=False,
                                    help="If it's checked, Invoice for Order will be Created and Posted automatically.")
    sale_journal_id = fields.Many2one('account.journal', string='Sales Journal', default=_default_sales_journal,
                                      domain=[('type', '=', 'sale')])
    picking_policy = fields.Selection([
        ('direct', 'Deliver each product when available'),
        ('one', 'Deliver all products at once')
    ], string='Shipping Policy', default="one")

    @api.onchange("validate_order")
    def onchange_validate_order(self):
        if not self.validate_order:
            self.create_invoice = False

    @api.model
    def auto_workflow_process(self, order_ids=[]):
        """
        This method will find draft sale orders which are not having invoices yet, confirmed it according to
        configured 'order auto workflow' settings
        """
        workflow_process = self if self else self.search([])

        if not order_ids:
            domain = [('auto_workflow_process_id', 'in', workflow_process.ids),
                      ('state', 'not in', ('done', 'cancel', 'sale')),
                      ('invoice_status', '!=', 'invoiced')]
        else:
            domain = [('auto_workflow_process_id', 'in', workflow_process.ids),
                      ('id', 'in', order_ids)]

        orders = self.env['sale.order'].search(domain)

        try:
            orders.process_orders_and_invoices()
        except Exception as e:
            return str(e)
