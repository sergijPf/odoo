# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes Magento Payment Methods
"""
from odoo import models, api, fields
from odoo.exceptions import UserError
from ..python_library.api_request import req


class MagentoPaymentMethod(models.Model):
    """
    Describes Magento Payment Methods
    """
    _name = 'magento.payment.method'
    _description = 'Magento Payment Method'
    _rec_name = 'payment_method_name'

    @api.model
    @api.returns('res.company')
    def _default_company_id(self):
        """
        Returns Default Company Id
        :return: Default company id
        """
        return self.env.company

    magento_instance_id = fields.Many2one('magento.instance', 'Instance', ondelete="cascade",
                                          help="This field relocates magento instance")
    payment_method_code = fields.Char(string='Payments Method Code', help='Payment Method Code')
    payment_method_name = fields.Char(string='Payments Method Name', help='Payment Method Name')
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term',
                                      help="Default payment term of a sale order using this method.")
    magento_workflow_process_id = fields.Many2one('sale.workflow.process.ept', string='Automatic Workflow',
                                                  help="Workflow for Order")
    company_id = fields.Many2one('res.company', 'Company', default=_default_company_id, help="Magento Company Id.")
    create_invoice_on = fields.Selection([
        ('open', 'Validate'),
        ('in_payment_paid', 'In-Payment/Paid')
    ], string='Create Invoice on action',
        help="Should the invoice be created in Magento when it is validated or when it is In-Payment/Paid in odoo?\n"
             "If it's blank then invoice will not exported in Magento for this Payment Method.")
    import_rule = fields.Selection([
        ('always', 'Always'),
        ('never', 'Never'),
        ('paid', 'Paid')
    ], string="Import Rules", default='always', required=True,
        help="Import Rule for Sale Order.\n \n "
             "[Always] : This Payment Method's Order will always import\n "
             "[Paid]: If Order is Paid On Magento then Order will import \n "
             "[Never] : This Payment Method Order will never be imported \n ")
    active = fields.Boolean(string="Status", default=True)

    _sql_constraints = [('unique_payment_method_code', 'unique(magento_instance_id,payment_method_code)',
                         'This payment method code is already exist')]

    @staticmethod
    def import_payment_method(instance):
        try:
            url = '/V1/paymentmethod'
            payment_methods = req(instance, url)
        except Exception as e:
            raise UserError(e)

        for pm in payment_methods:
            pm_code = pm.get('value')
            odoo_pm = instance.payment_method_ids.with_context(active_test=False).filtered(
                lambda x: x.payment_method_code == pm_code)

            if not odoo_pm:
                odoo_pm.create({
                    'payment_method_code': pm.get('value'),
                    'payment_method_name': pm.get('title'),
                    'magento_instance_id': instance.id
                })