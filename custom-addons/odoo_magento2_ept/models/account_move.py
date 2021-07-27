# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods for account move
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .api_request import req
ACCOUNT_MOVE = 'account.move'

class AccountInvoice(models.Model):
    """
    Describes fields and methods to import and export invoices of Magento.
    """
    _inherit = ACCOUNT_MOVE

    magento_payment_method_id = fields.Many2one(
        'magento.payment.method',
        string="Magento Payment Method",
        help="Magento Payment Method"
    )
    is_magento_invoice = fields.Boolean(
        string="Magento Invoice?",
        help="If True, It is Magento Invoice"
    )
    is_exported_to_magento = fields.Boolean(
        string='Exported to Magento',
        help='Exported to Magento',
    )
    magento_instance_id = fields.Many2one(
        'magento.instance',
        string="Instance",
        help="This field relocates Magento Instance"
    )
    magento_invoice_id = fields.Char(string="Magento Invoice")
    max_no_of_attempts = fields.Integer(string='Max NO. of attempts', default = 0)
    magento_message = fields.Char(string="Invoice Message")


    def export_invoice_to_magento(self, magento_instance):
        """
        This method is used to export invoices into Magento.
        :param magento_instance: Instance of Magento.
        """
        common_log_book_obj = self.env['common.log.book.ept']
        common_log_lines_obj = self.env['common.log.lines.ept']
        invoices = self.search([
            ('is_magento_invoice', '=', True),
            ('is_exported_to_magento', '=', False),
            ('magento_instance_id', 'in', magento_instance.ids),
            ('state', 'in', ['posted']),
            ('max_no_of_attempts', '<=', 3)
        ])
        model_id = common_log_lines_obj.get_model_id(ACCOUNT_MOVE)
        log_book_id = common_log_book_obj.create({
            'type': 'export',
            'module': 'magento_ept',
            'model_id': model_id,
            'res_id': self.id,
            'magento_instance_id': magento_instance.id
        })
        for invoice in invoices:
            if (invoice.magento_payment_method_id.create_invoice_on == 'in_payment_paid' and invoice.payment_state in ['in_payment', 'paid']) or \
                    (invoice.magento_payment_method_id.create_invoice_on == 'open' and invoice.payment_state not in ['in_payment', 'paid']):
                self.call_export_invoice_api(invoice, log_book_id)
        if not log_book_id.log_lines:
            log_book_id.sudo().unlink()

    def export_invoice_in_magento(self):
        """
        Export specific invoice in Magento through API
        """
        self.ensure_one()
        common_log_book_obj = self.env['common.log.book.ept']
        common_log_lines_obj = self.env['common.log.lines.ept']
        instance = self.magento_instance_id
        model_id = common_log_lines_obj.get_model_id(ACCOUNT_MOVE)
        log_book_id = common_log_book_obj.create({
            'type': 'export',
            'module': 'magento_ept',
            'model_id': model_id,
            'res_id': self.id,
            'magento_instance_id': instance.id
        })
        if (self.magento_payment_method_id.create_invoice_on == 'in_payment_paid' and self.payment_state in ['in_payment', 'paid']) or \
                (self.magento_payment_method_id.create_invoice_on == 'open' and self.payment_state not in ['in_payment', 'paid']):
            invoice = self
            self.call_export_invoice_api(invoice, log_book_id)
        else:
            #Raise the UserError while the respected Payment method
            #configuration for Create Invoice on Magento
            #and invoice state both are different
            raise UserError("Can't Export Invoice \n"
                            "Your Configuration for the 'Create Invoice on Magento' is '%s' "
                            "For the '%s' payment method. And current invoice state is '%s'\n"
                            "Please check the Configuration and try it again" % (self.magento_payment_method_id.create_invoice_on,
                                                                                 self.magento_payment_method_id.payment_method_name,
                                                                                 self.state))
        if not log_book_id.log_lines:
            log_book_id.sudo().unlink()

    @staticmethod
    def call_export_invoice_api(invoice, log_book_id):
        """
        Export All invoices in Magento through API
        """
        sale_orders = invoice.invoice_line_ids.mapped('sale_line_ids').mapped('order_id')
        sale_order = sale_orders and sale_orders[0]
        order_item = []
        response = False
        for invoice_line in invoice.invoice_line_ids:
            item = {}
            sale_lines = invoice_line.sale_line_ids
            item_id = False
            if sale_lines:
                item_id = sale_lines[0].magento_sale_order_line_ref
            if item_id:
                item.setdefault("order_item_id", item_id)
                item.setdefault("qty", invoice_line.quantity)
                order_item.append(item)
        invoice_name = invoice.name
        data = {
            "items": order_item,
            "notify": invoice.magento_instance_id.invoice_done_notify_customer
        }
        try:
            api_url = '/V1/order/%s/invoice' % sale_order.magento_order_id
            response = req(invoice.magento_instance_id, api_url, 'POST', data)
        except Exception:
            invoice.write({
                "max_no_of_attempts" : invoice.max_no_of_attempts + 1,
                "magento_message" : _("The request could not be satisfied while export this invoice."
                                    "\nPlease check Process log %s") % (log_book_id.name)
            })
            message = _("The request could not be satisfied and an invoice couldn't be created in Magento for "
                        "Sale Order : %s & Invoice : %s due to any of the following reasons.\n"
                        "1. An invoice can't be created when an order has a status of 'On Hold/Canceled/Closed'\n"
                        "2. An invoice can't be created without products. Add products and try again. "
                        "The order does not allow an invoice to be created") % (sale_order.name, invoice_name)
            log_book_id.write({
                'log_lines': [(0, 0, {'message': message, 'order_ref': sale_order.name})]
            })
        if response:
            invoice.write({'magento_invoice_id': int(response), 'is_exported_to_magento': True})
