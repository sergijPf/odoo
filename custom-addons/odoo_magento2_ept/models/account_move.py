# -*- coding: utf-8 -*-
"""
Describes methods for account move
"""
from odoo import models, fields, _
from odoo.exceptions import UserError
from .api_request import req
ACCOUNT_MOVE = 'account.move'

class AccountInvoice(models.Model):
    """
    Describes fields and methods to export invoice info to Magento
    """
    _inherit = ACCOUNT_MOVE

    magento_payment_method_id = fields.Many2one('magento.payment.method', string="Magento Payment Method")
    is_exported_to_magento = fields.Boolean(string='Exported to Magento')
    magento_instance_id = fields.Many2one('magento.instance', string="Magento Instance")
    magento_invoice_id = fields.Char(string="Magento Invoice Ref")

    def export_invoices_to_magento(self, magento_instance):
        """
        This method is used to export invoices to Magento by automatic cron-job or calling related action
        :param magento_instance: Instance of Magento.
        """
        invoices = self.search([
            ('is_exported_to_magento', '=', False),
            ('magento_instance_id', 'in', magento_instance.ids),
            ('state', 'in', ['posted'])
        ])
        for invoice in invoices:
            invoice.export_single_invoice_to_magento(False)

    def export_single_invoice_to_magento(self, is_single_call=True):
        """
        Export specific invoice to Magento through API
        :param is_single_call: If method called for single Invoice only from Frontend
        """
        self.ensure_one()
        res = True
        log_book_obj = self.env['magento.invoices.log.book']

        if (self.magento_payment_method_id.create_invoice_on == 'in_payment_paid' and
            self.payment_state in ['in_payment', 'paid']
        ) or (self.magento_payment_method_id.create_invoice_on == 'open' and
              self.payment_state not in ['in_payment', 'paid']):
            res = self.call_export_invoice_api(log_book_obj, is_single_call)

        else:
            message = "Can't Export Invoice \n Your Configuration for the 'Create Invoice on Magento' is '%s' " \
                      "For the '%s' payment method. And current invoice state is '%s'\n Please check the " \
                      "Configuration and try it again" % (self.magento_payment_method_id.create_invoice_on,
                                                          self.magento_payment_method_id.payment_method_name,
                                                          self.state)
            if is_single_call:
                raise UserError(message)
            else:
                self.log_invoice_export_error(log_book_obj, message)

        if is_single_call and not res:
            return {
                'name': 'Invoice Error Logs',
                'view_mode': 'tree,form',
                'res_model': 'magento.invoices.log.book',
                'type': 'ir.actions.act_window'
            }

    def call_export_invoice_api(self, log_book_obj, is_single_call):
        """
        Export All invoices in Magento through API
        :param log_book_obj: Invoice Errors log book object
        :param is_single_call: If method called for single Invoice only
        """
        sale_orders = self.invoice_line_ids.mapped('sale_line_ids').mapped('order_id')
        sale_order = sale_orders and sale_orders[0]
        order_item = []

        for invoice_line in self.invoice_line_ids:
            sale_lines = invoice_line.sale_line_ids
            if sale_lines:
                item = {}
                item_id = sale_lines[0].magento_sale_order_line_ref
                if item_id:
                    item.setdefault("order_item_id", item_id)
                    item.setdefault("qty", invoice_line.quantity)
                    order_item.append(item)
        data = {
            "items": order_item,
            "notify": self.magento_instance_id.invoice_done_notify_customer
        }

        try:
            api_url = '/V1/order/%s/invoice' % sale_order.magento_order_id
            response = req(self.magento_instance_id, api_url, 'POST', data)
        except Exception:
            message = _("The request could not be satisfied and an invoice couldn't be created in Magento for "
                        "Sale Order: %s & Invoice: %s due to any of the following reasons:\n"
                        "1. An invoice can't be created when an order has a status of 'On Hold/Canceled/Closed'\n"
                        "2. An invoice can't be created without products. Add products and try again.\n"
                        "The order does not allow an invoice to be created") % (sale_order.name, self.name)
            self.log_invoice_export_error(log_book_obj, message)
            return False

        if response:
            self.write({'magento_invoice_id': int(response), 'is_exported_to_magento': True})
            invoice_err = log_book_obj.search([('invoice_id', '=', self.id)])
            if invoice_err:
                invoice_err.write({'active': False})

            if is_single_call:
                return {
                    'effect': {
                        'fadeout': 'slow',
                        'message': "Process Completed Successfully!",
                        'img_url': '/web/static/src/img/smile.svg',
                        'type': 'rainbow_man',
                    }
                }

    def log_invoice_export_error(self, log_book_obj, message):
        data = {'invoice_id': self.id, 'log_message': message}
        invoice_err = log_book_obj.search([('invoice_id', '=', self.id)])
        invoice_err.write(data) if invoice_err else invoice_err.create(data)
