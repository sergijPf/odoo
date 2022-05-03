# -*- coding: utf-8 -*-

from odoo import fields, models
from ..python_library.api_request import req


class AccountTaxCode(models.Model):
    _inherit = 'account.tax'

    def get_tax_from_rate(self, rate, is_tax_included=False):
        tax_ids = self.with_context(active_test=False).search(
            [('price_include', '=', is_tax_included),
             ('type_tax_use', 'in', ['sale']),
             ('amount', '>=', rate - 0.001),
             ('amount', '<=', rate + 0.001)])
        if tax_ids:
            return tax_ids[0]

        # try to find a tax with less precision
        tax_ids = self.with_context(active_test=False).search(
            [('price_include', '=', is_tax_included),
             ('type_tax_use', 'in', ['sale']),
             ('amount', '>=', rate - 0.01),
             ('amount', '<=', rate + 0.01)])
        if tax_ids:
            return tax_ids[0]

        return False


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    magento_payment_method_id = fields.Many2one('magento.payment.method', string="Magento Payment Method")
    is_in_magento = fields.Boolean(string='Is in Magento?', default=False)
    magento_instance_id = fields.Many2one('magento.instance', string="Magento Instance")

    def export_invoices_to_magento(self, magento_instances, is_cron_call):
        invoices = self.search([
            ('is_in_magento', '=', False),
            ('magento_instance_id', 'in', magento_instances.ids),
            ('state', 'in', ['posted'])
        ])

        for invoice in invoices:
            resp = invoice.export_single_invoice_to_magento(is_cron_call)
            if resp and not resp.get("effect"):
                return resp

    def export_single_invoice_to_magento(self, is_cron_call=False):
        self.ensure_one()
        res = False

        if self.payment_state in ['in_payment', 'paid']:
            res = self.call_export_invoice_api()

        if not is_cron_call:
            if res:
                return {
                    'effect': {
                        'fadeout': 'slow',
                        'message': "Process Completed Successfully!",
                        'img_url': '/web/static/img/smile.svg',
                        'type': 'rainbow_man',
                    }
                }
            else:
                return {
                    'name': 'Invoice Error Logs',
                    'view_mode': 'tree,form',
                    'res_model': 'magento.invoices.log.book',
                    'type': 'ir.actions.act_window'
                }

    def call_export_invoice_api(self):
        order_item = []
        log_book_rec = self.env['magento.invoices.log.book'].search([('invoice_id', '=', self.id)])

        sale_orders = self.invoice_line_ids.sale_line_ids.order_id
        sale_order = sale_orders and sale_orders[0]

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
            if response:
                self.write({'is_in_magento': True})
                if log_book_rec:
                    log_book_rec.write({'active': False})

                return True
            else:
                message = "Error while exporting invoice to Magento."
                data = {'invoice_id': self.id, 'log_message': message}
                log_book_rec.write(data) if log_book_rec else log_book_rec.create(data)

        except Exception as e:
            message = "The request could not be satisfied and invoice couldn't be created in Magento for " \
                      "Sale Order: '%s' due to following reason: %s" % (sale_order.name, str(e))

            data = {'invoice_id': self.id, 'log_message': message}
            log_book_rec.write(data) if log_book_rec else log_book_rec.create(data)
