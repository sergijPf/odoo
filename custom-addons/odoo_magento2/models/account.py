# -*- coding: utf-8 -*-
"""For Odoo Magento2 Connector Module"""
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from ..python_library.api_request import req


class AccountTaxCode(models.Model):
    """Inherited account tax model to calculate tax."""
    _inherit = 'account.tax'

    def get_tax_from_rate(self, rate, is_tax_included=False):
        """
        This method base on tax rate it'll find in Odoo
        :return: Tax_ids
        """
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


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    origin_country_ = fields.Many2one('res.country', string='Origin Country',
                                         help="Warehouse country based on sales order warehouse country system will "
                                              "apply fiscal position")

    @api.model
    def _get_fpos_by_region(self, country_id=False, state_id=False, zipcode=False, vat_required=False):
        """
        Inherited this method for selecting fiscal position based on warehouse (origin country).
        """
        origin_country_id = self._context.get('origin_country_', False)
        if not origin_country_id:
            return super(AccountFiscalPosition, self)._get_fpos_by_region(country_id=country_id, state_id=state_id,
                                                                          zipcode=zipcode, vat_required=vat_required)
        return self.search_fiscal_position_based_on_origin_country(origin_country_id, country_id, state_id, zipcode,
                                                                   vat_required)

    @api.model
    def search_fiscal_position_based_on_origin_country(self, origin_country_id, country_id, state_id, zipcode,
                                                       vat_required):
        """
        Search fiscal position based on origin country
        Updated by twinkalc on 11 sep 2020 - [changes related to the pass domain of company and is_amazon_fpos]
        [UPD] Check all base conditions for search fiscal position as per base and with origin country
        """
        if not country_id:
            return False
        base_domain = [('vat_required', '=', vat_required), ('company_id', 'in', [self.env.company.id, False]),
                       ('origin_country_', 'in', [origin_country_id, False])]
        null_state_dom = state_domain = [('state_ids', '=', False)]
        null_zip_dom = zip_domain = [('zip_from', '=', False), ('zip_to', '=', False)]
        null_country_dom = [('country_id', '=', False), ('country_group_id', '=', False)]

        if zipcode:
            zip_domain = [('zip_from', '<=', zipcode), ('zip_to', '>=', zipcode)]
        if state_id:
            state_domain = [('state_ids', '=', state_id)]

        domain_country = base_domain + [('country_id', '=', country_id)]
        domain_group = base_domain + [('country_group_id.country_ids', '=', country_id)]
        # Build domain to search records with exact matching criteria
        fpos = self.search(domain_country + state_domain + zip_domain, limit=1)
        # return records that fit most the criteria, and fallback on less specific fiscal positions if any can be found
        if not fpos and state_id:
            fpos = self.search(domain_country + null_state_dom + zip_domain, limit=1)
        if not fpos and zipcode:
            fpos = self.search(domain_country + state_domain + null_zip_dom, limit=1)
        if not fpos and state_id and zipcode:
            fpos = self.search(domain_country + null_state_dom + null_zip_dom, limit=1)
        # fallback: country group with no state/zip range
        if not fpos:
            fpos = self.search(domain_group + null_state_dom + null_zip_dom, limit=1)
        if not fpos:
            # Fallback on catchall (no country, no group)
            fpos = self.search(base_domain + null_country_dom, limit=1)
        return fpos


class AccountInvoice(models.Model):
    """
    Describes fields and methods to export invoice info to Magento
    """
    _inherit = 'account.move'

    magento_payment_method_id = fields.Many2one('magento.payment.method', string="Magento Payment Method")
    is_exported_to_magento = fields.Boolean(string='Exported to Magento')
    magento_instance_id = fields.Many2one('magento.instance', string="Magento Instance")
    magento_invoice_id = fields.Char(string="Magento Invoice Ref")

    def export_invoices_to_magento(self, magento_instance):
        """
        This method is used to export invoices to Magento by automatic cron-job or by calling an action
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
