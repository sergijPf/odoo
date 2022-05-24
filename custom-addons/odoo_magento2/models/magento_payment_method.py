# -*- coding: utf-8 -*-

from odoo import models, api, fields
from odoo.exceptions import UserError
from ..python_library.api_request import req


class MagentoPaymentMethod(models.Model):
    _name = 'magento.payment.method'
    _description = 'Magento Payment Method'
    _rec_name = 'payment_method_name'

    @api.model
    @api.returns('res.company')
    def _default_company_id(self):
        return self.env.company

    magento_instance_id = fields.Many2one('magento.instance', string='Magento Instance', ondelete="cascade")
    payment_method_code = fields.Char(string='Payments Method Code', help="Code received from Magento")
    payment_method_name = fields.Char(string='Payments Method Name')
    company_id = fields.Many2one('res.company', 'Company', default=_default_company_id, help="Magento Company Id.")
    import_rule = fields.Selection([
        ('always', 'Always'),
        ('never', 'Never'),
        ('paid', 'Paid')
    ], string="Import Rules", default='always', required=True,
        help="Import Rule for Sale Order.\n "
             "[Always] : This Payment Method's Order will always be imported\n "
             "[Paid]: If Order is Paid On Magento then Order will be imported\n "
             "[Never] : This Payment Method Order will never be imported\n ")
    active = fields.Boolean(string="Status", default=True)
    journal_id = fields.Many2one('account.journal', string='Payment Journal', domain=[('type', 'in', ['cash', 'bank'])])
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line',
        string="Payment Method Line",
        domain="[('payment_type', '=', 'inbound'), ('journal_id', '=', journal_id)]"
    )

    _sql_constraints = [('unique_payment_method_code', 'unique(magento_instance_id,payment_method_code)',
                         'This payment method code is already exist')]

    @api.onchange("journal_id")
    def onchange_journal_id(self):
        for record in self:
            record.payment_method_line_id = False

    @staticmethod
    def import_payment_methods(instance):
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
