# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields and methods for create/ update sale order
"""
# import json
# import pytz
# import time
# from datetime import datetime, timedelta
from odoo import models, fields
from odoo.exceptions import UserError
from .api_request import req
# from ..python_library.php import Php
# from dateutil import parser
# utc = pytz.utc

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
SALE_ORDER_LINE = 'sale.order.line'


class SaleOrder(models.Model):
    """
    Describes fields and methods for create/ update sale order
    """
    _inherit = 'sale.order'

    def _get_magento_order_status(self):
        """
        Compute updated_in_magento of order from the pickings.
        """
        for order in self:
            if order.magento_instance_id:
                pickings = order.picking_ids.filtered(lambda x: x.state != "cancel")
                stock_moves = order.order_line.move_ids.filtered(lambda x: not x.picking_id and x.state == 'done')
                if pickings:
                    outgoing_picking = pickings.filtered(
                        lambda x: x.location_dest_id.usage == "customer")
                    if all(outgoing_picking.mapped("is_exported_to_magento")):
                        order.updated_in_magento = True
                        continue
                if stock_moves:
                    order.updated_in_magento = True
                    continue
                order.updated_in_magento = False
                continue
            order.updated_in_magento = False

    def _search_magento_order_ids(self, operator, value):
        query = """select so.id from stock_picking sp
                    inner join sale_order so on so.procurement_group_id=sp.group_id                   
                    inner join stock_location on stock_location.id=sp.location_dest_id and stock_location.usage='customer'
                    where sp.is_exported_to_magento %s true and sp.state != 'cancel'
                    """ % operator
        if operator == '=':
            query += """union all
                    select so.id from sale_order as so
                    inner join sale_order_line as sl on sl.order_id = so.id
                    inner join stock_move as sm on sm.sale_line_id = sl.id
                    where sm.picking_id is NULL and sm.state = 'done' and so.magento_instance_id notnull"""
        self._cr.execute(query)
        results = self._cr.fetchall()
        order_ids = []
        for result_tuple in results:
            order_ids.append(result_tuple[0])
        order_ids = list(set(order_ids))
        return [('id', 'in', order_ids)]

    magento_instance_id = fields.Many2one('magento.instance', string="Instance",
                                          help="This field relocates Magento Instance")
    magento_order_id = fields.Char(string="Magento order Ids", help="Magento Order Id")
    magento_website_id = fields.Many2one("magento.website", string="Magento Website", help="Magento Website")
    magento_order_reference = fields.Char(string="Magento Orders Reference", help="Magento Order Reference")
    store_id = fields.Many2one('magento.storeview', string="Magento Storeview", help="Magento_store_view")
    is_exported_to_magento_shipment_status = fields.Boolean(string="Is Order exported to Shipment Status",
                                                            help="Is exported to Shipment Status")
    magento_payment_method_id = fields.Many2one('magento.payment.method', string="Magento Payment Method",
                                                help="Magento Payment Method")
    magento_shipping_method_id = fields.Many2one('magento.delivery.carrier', string="Magento Shipping Method",
                                                 help="Magento Shipping Method")
    order_transaction_id = fields.Char(string="Magento Orders Transaction ID", help="Magento Orders Transaction ID")
    updated_in_magento = fields.Boolean(string="Order fulfilled in magento", compute="_get_magento_order_status",
                                        search="_search_magento_order_ids", copy=False)
    #added by SPf
    magento_carrier_name = fields.Char(compute="_carrier_name", string="Magento Carrier Name")
    magento_order_log_book_ids = fields.One2many('magento.orders.log.book', 'sale_order_id', "Log Error Messages")

    _sql_constraints = [('_magento_sale_order_unique_constraint',
                         'unique(magento_order_id,magento_instance_id,magento_order_reference)',
                         "Magento order must be unique")]

    def _cancel_order_exportable(self):
        """
        this method will check order is cancel in odoo or not, and invoice is exported or not.
        And shipment done in magento or not
        :return:
        """
        if (self.invoice_ids and True in self.invoice_ids.mapped('is_exported_to_magento')) or \
                (self.picking_ids and self.picking_ids.filtered(
                    lambda x: x.state == 'done' and x.is_exported_to_magento).ids):
            self.is_cancel_order_exportable = True
        else:
            self.is_cancel_order_exportable = False

    is_cancel_order_exportable = fields.Boolean(string="Is Invoice exportable", compute='_cancel_order_exportable',
                                                store=False)

    # @api.model
    # def check_price_list_for_order_exist(self, order_response, log_book_id, order_data_queue_line_id):
    #     """
    #     This method is used to check price list is exist or not in odoo.
    #     When import order from Magento to Odoo.
    #     :param order_response: Order Response received from Magento
    #     :param skip_order: True if any error else False
    #     :param log_book_id: Common Log book object
    #     :param order_data_queue_line_id: order data queue line id
    #     :return: Product price list object or skip order
    #     """
    #     currency_obj = self.env['res.currency']
    #     pricelist_obj = self.env['product.pricelist']
    #     skip_order = False
    #     order_currency = order_response.get('order_currency_code')
    #     order_ref = order_response.get('increment_id')
    #     currency_id = currency_obj.with_context(active_test=False).search([('name', '=', order_currency)], limit=1)
    #     if not currency_id.active:
    #         currency_id.write({'active': True})
    #     price_list = pricelist_obj.search([('currency_id', '=', currency_id.id)])
    #     if price_list:
    #         price_list = price_list[0]
    #     elif not price_list or price_list.currency_id != currency_id:
    #         skip_order = True
    #         message = "Order %s skipped due to pricelist not found for currency please synchronize metadata again." % order_ref
    #         log_book_id.add_log_line(message, order_ref, order_data_queue_line_id, "magento_order_data_queue_line_id")
    #     return price_list, skip_order

    # def get_magento_shipping_method(self, magento_instance, order_response, log_book_id, order_data_queue_line_id):
    #     """
    #     This method is used to get shipping method.
    #     if shipping method not found it will create(base on carrier_code) new shipping method.
    #     :param magento_instance: Instance of Magento
    #     :param order_response: Order Response received from Magento
    #     :param log_book_id: Common Log book object
    #     :param order_data_queue_line_id: Order data queue line object
    #     :return:
    #     """
    #     magento_delivery_carrier_obj = self.env['magento.delivery.carrier']
    #     delivery_carrier_obj = self.env["delivery.carrier"]
    #     order_reference = order_response.get('increment_id')
    #     magento_carrier = skip_order = False
    #     shipping = order_response.get('extension_attributes').get('shipping_assignments')
    #     shipping_method = shipping[0].get('shipping').get('method') or False
    #     if order_response.get('type_id') in ['simple', 'configurable']:
    #         message = ""
    #         if not shipping_method:
    #             skip_order = True
    #             message = "Delivery method is not  found in Order %s" % order_reference
    #         else:
    #             magento_carrier = magento_delivery_carrier_obj.search([
    #                 ('carrier_code', '=', shipping_method), ('magento_instance_id', '=', magento_instance.id)
    #             ], limit=1)
    #             if not magento_carrier:
    #                 skip_order = True
    #                 message = "Order %s skipped due to shipping %s not found in Delivery Methods" % (
    #                     order_reference, shipping_method)
    #         if skip_order:
    #             log_book_id.add_log_line(message, order_reference, order_data_queue_line_id,
    #                                      "magento_order_data_queue_line_id")
    #             return skip_order
    #         if magento_carrier:
    #             delivery_carrier = delivery_carrier_obj.search([('magento_carrier', '=', magento_carrier.id)], limit=1)
    #             if not delivery_carrier:
    #                 product = self.env.ref('odoo_magento2_ept.product_product_shipping')
    #                 delivery_carrier_obj.create({
    #                     'name': magento_carrier.carrier_label,
    #                     'product_id': product.id,
    #                     'magento_carrier': magento_carrier.id
    #                 })
    #     return skip_order

    # def magento_order_convert_date(self, order_response):
    #     """ This method is used to convert the order date in UTC and formate("%Y-%m-%d %H:%M:%S").
    #         :param order_response: Order response
    #     """
    #     if order_response.get("created_at", False):
    #         order_date = order_response.get("created_at", False)
    #         date_order = parser.parse(order_date).astimezone(utc).strftime("%Y-%m-%d %H:%M:%S")
    #     else:
    #         date_order = time.strftime("%Y-%m-%d %H:%M:%S")
    #         date_order = str(date_order)
    #
    #     return date_order

    # def create_magento_sales_order(self, orders, magento_invoice_customer, magento_delivery_customer, order_count,
    #                                    order_total_queue, log_book_id):
    #     """
    #     This method create orders in Odoo.
    #     :param orders: orders dictionary received from Magento API
    #     # :param magento_product_sku: Dictionary of Magento products
    #     :param magento_invoice_customer: Dictionary of Magento invoice customer
    #     :param magento_delivery_customer: Dictionary of Magento delivery customer
    #     :param order_count: Order count variable for commit after 10 orders
    #     :param order_total_queue: Total number of order in a queue
    #     :param log_book_id: common log book object
    #     :return: Inserted orders dictionary
    #     """
    #     country_dict = state_dict = {}
    #     magento_instance_id = orders.magento_instance_id
    #
    #     for order_dict in orders:
    #         order_response = json.loads(order_dict.order_data)
    #         order_ref = order_response['increment_id']
    #         if not order_ref:
    #             continue
    #
    #         existing_order = self.search([
    #             ('magento_instance_id', '=', magento_instance_id.id), ('magento_order_reference', '=', order_ref)
    #         ])
    #         if existing_order:
    #             order_dict.write({'state': 'done', 'processed_at': datetime.now(), 'sale_order_id': existing_order.id})
    #             order_total_queue -= 1
    #             continue
    #         if magento_instance_id:
    #             magento_order, skip_order = self.get_magento_order_details_and_create_sale_order(
    #                 magento_instance_id, order_dict, order_response, log_book_id, magento_invoice_customer,
    #                 magento_delivery_customer, state_dict, country_dict)
    #             if skip_order:
    #                 # here we set queue line as fail state,
    #                 # because warehouse is not set in website
    #                 order_dict.write({'state': 'failed', 'processed_at': datetime.now()})
    #                 magento_order and magento_order.sudo().unlink()
    #                 continue
    #             self.process_sale_order_workflow_based_on_status(order_response, magento_order, log_book_id)
    #             order_count += 1
    #             order_total_queue -= 1
    #             order_dict, order_count = self.check_more_order_queue_exists(order_count, order_total_queue, order_dict)
    #             order_dict.write({
    #                 'state': 'done', 'processed_at': datetime.now(),
    #                 'magento_order_id': magento_order.magento_order_reference,
    #                 'sale_order_id': magento_order.id # save sale_order_id for new order.
    #             })
    #     return magento_invoice_customer, magento_delivery_customer, order_count, order_total_queue

    # def validate_magento_order(self, order_response, magento_instance_id, order_ref, log_book_id, order_dict):
    #     skip_order = False
    #     message = ''
    #     date_order = self.magento_order_convert_date(order_response)
    #     if str(magento_instance_id.import_order_after_date) > date_order:
    #         message = "Order %s is not imported in Odoo due to configuration mismatch.\n Received order date is %s.\n" \
    #                   "Please check the order after date in Magento configuration." % (order_ref, date_order)
    #         skip_order = True
    #     elif 'is_invoice' not in order_response.get('extension_attributes'):
    #         message = "Please check Apichange extention is installed in Magento store."
    #
    #     if message:
    #         skip_order = True
    #         log_book_id.add_log_line(message, order_ref, order_dict.id, "magento_order_data_queue_line_id")
    #     return skip_order

    # def get_magento_order_details_and_create_sale_order(self, magento_instance_id, order_dict, order_response,
    #                                                     log_book_id, magento_invoice_customer,
    #                                                     magento_delivery_customer, state_dict, country_dict):
    #     """
    #     Create/ update Magento payment options, financial status, products,
    #      shipping details, customers, pricelists.
    #      Prepare Magento order values.
    #     :param magento_instance_id: Magento instance id
    #     :param order_dict: magento order data queue line object
    #     :param order_response: response received from Magento
    #     :param log_book_id: common log book object
    #     # :param magento_product_sku: Magento product SKU
    #     :param magento_invoice_customer: dictionary for invoice customer
    #     :param magento_delivery_customer: dictionary for delivery customer
    #     :param state_dict: dictionary for state
    #     :param country_dict: dictionary for country
    #     :return: orcer values dictionary, skip_order
    #     """
    #     magento_order = False
    #     price_list = False
    #     order_ref = order_response['increment_id']
    #     skip_order = self.validate_magento_order(order_response, magento_instance_id, order_ref, log_book_id, order_dict)
    #
    #     if not skip_order:
    #         skip_order = self.check_payment_and_shipping_and_product_info_of_order(
    #             order_dict.id, order_response, magento_instance_id, log_book_id, skip_order
    #         )
    #     if not skip_order:
    #         price_list, skip_order = self.check_price_list_for_order_exist(order_response, log_book_id, order_dict.id)
    #     if not skip_order:
    #         skip_order, partner_dict = self.env['res.partner'].create_or_update_magento_customer(
    #             magento_instance_id, order_response, magento_invoice_customer,
    #             magento_delivery_customer, state_dict, country_dict, skip_order, log_book_id, order_dict.id
    #         )
    #     if not skip_order:
    #         # Prepare Sale Order Values
    #         order_values, skip_order = self.create_magento_sales_order_vals(
    #             partner_dict, order_response, magento_instance_id, price_list, log_book_id, order_dict.id
    #         )
    #     if not skip_order:
    #         magento_order = self.create(order_values)
    #         skip_order = self.create_magento_sale_order_line(
    #             order_response, magento_instance_id, magento_order, log_book_id, order_dict
    #         )
    #     return magento_order, skip_order

    # def check_more_order_queue_exists(self, order_count, order_total_queue, order_dict):
    #     """
    #     Check more product queue items exists
    #     :param order_count: incremental count of order queue line
    #     :param order_total_queue: total order queue line
    #     :param order_dict: magento order data queue line object
    #     :return: order_count, order_dict
    #     """
    #     if order_count > 10 or (0 < order_count <= 10 and order_total_queue == 0):
    #         self._cr.commit()
    #         order_count = 1
    #         order_dict.magento_order_data_queue_id.is_process_queue = True
    #     return order_dict, order_count

    # def check_payment_and_shipping_and_product_info_of_order(self, order_data_queue_line_id, order_response,
    #                                                          magento_instance_id, log_book_id, skip_order):
    #     """
    #     Check Payment method, payment term and shipping method
    #     :param order_data_queue_line_id: order data queue line id
    #     :param order_response: order dictionary received from Magento API
    #     :param magento_instance_id: Instance of Magento
    #     :param log_book_id: common log book object or False
    #     # :param magento_product_sku: Magento product dictionary
    #     :param skip_order: True/False
    #     :return: skip order and job
    #     """
    #     order_ref = order_response['increment_id']
    #     payment_method = order_response['payment'].get('method')
    #     skip_order, message = self.check_magento_payment_method_configuration(magento_instance_id, order_response,
    #                                                                           payment_method, skip_order)
    #     if skip_order:
    #         log_book_id.create_order_log_lines(message, order_ref, order_data_queue_line_id)
    #         return skip_order

        # skip_order = self.get_magento_shipping_method(magento_instance_id, order_response, log_book_id,
        #                                               order_data_queue_line_id)
        # if skip_order:
        #     return skip_order
        # order_lines = order_response['items']
        # skip_order = self.check_products_exist_in_odoo(order_lines, magento_instance_id, order_ref,
        #                                                order_data_queue_line_id, log_book_id)
        # return skip_order

    # @staticmethod
    # def get_magento_financial_status(order_status, is_invoice, is_shipment):
    #     """
    #     Get Financial Status Dictionary.
    #     :param order_status: Order status received from Magento.
    #     :param is_invoice: Order is invoiced.
    #     :param is_shipment: Order is Shipped.
    #     :return: Financial Status dictionary
    #     """
    #     financial_status_code = financial_status_name = ''
    #     if order_status == "pending":
    #         financial_status_code = 'not_paid'
    #         financial_status_name = 'Pending Orders'
    #     elif order_status == "processing" and is_invoice and not is_shipment:
    #         financial_status_code = 'processing_paid'
    #         financial_status_name = 'Processing orders with Invoice'
    #     elif order_status == "processing" and is_shipment and not is_invoice:
    #         financial_status_code = 'processing_unpaid'
    #         financial_status_name = 'Processing orders with Shipping'
    #     elif order_status == "complete":
    #         financial_status_code = 'paid'
    #         financial_status_name = 'Completed Orders'
    #     return financial_status_code, financial_status_name
    #
    # def search_order_financial_status(self, order_response, magento_instance, payment_option):
    #     """
    #     Search order Financial status.
    #     :param order_response: Response received from Magento.
    #     :param magento_instance: Magento Instance.
    #     :param payment_option: Magento Order Payment Method
    #     :return: Financial Status object, Financial Status Name
    #     """
    #     is_invoice = order_response.get('extension_attributes').get('is_invoice')
    #     is_shipment = order_response.get('extension_attributes').get('is_shipment')
    #     financial_status_code, financial_status_name = self.get_magento_financial_status(order_response.get('status'),
    #                                                                                      is_invoice, is_shipment)
    #     workflow_config = self.env['magento.financial.status.ept'].search(
    #         [('magento_instance_id', '=', magento_instance.id),
    #          ('payment_method_id', '=', payment_option.id),
    #          ('financial_status', '=', financial_status_code)])
    #     return workflow_config, financial_status_name

    # @staticmethod
    # def check_order_is_processing_and_shipped_and_invoiced(order_response):
    #     """
    #     Check order is in processing state and invoice and shipment is done or not.
    #     :param order_response: order response received from Magento
    #     :return: skip_order, message
    #     """
    #     is_invoice = order_response.get('extension_attributes').get('is_invoice')
    #     is_shipment = order_response.get('extension_attributes').get('is_shipment')
    #     if not is_invoice and not is_shipment and order_response.get('status') == 'processing':
    #         message = "Order %s skipped, Order status is processing, but the order is neither " \
    #                   "invoice nor shipped." % order_response.get('increment_id')
    #     else:
    #         message = "Order %s skipped due to Partial Invoice and Shipment are not Supported." % order_response.get(
    #             'increment_id')
    #     return True, message

    # def check_magento_payment_method_configuration(self, magento_instance, order_response, payment_method, skip_order):
    #     """
    #     Check Configuration All Configuration of Payment Methods
    #     :param magento_instance: Magento Instance Object
    #     :param order_response: Order Response received from Magento.
    #     :param payment_method: Order Payment Method.
    #     :param skip_order: True/ False
    #     :return: skip_order (boolean)
    #     """
    #     payment_option = magento_instance.payment_method_ids.filtered(lambda x: x.payment_method_code == payment_method)
    #     order_ref = order_response['increment_id']
    #     message = ''
    #     import_rule = payment_option.import_rule
    #     max_days = payment_option.days_before_cancel
    #     amount_paid = order_response.get('payment').get('amount_paid', False)
    #     workflow_config, financial_status_name = self.search_order_financial_status(order_response, magento_instance,
    #                                                                                 payment_option)
    #     if not workflow_config and financial_status_name == "":
    #         skip_order, message = self.check_order_is_processing_and_shipped_and_invoiced(order_response)
    #     elif not workflow_config:
    #         skip_order = True
    #         message = "- Automatic order process workflow configuration not found for this order %s. \n -" \
    #                   " System tries to find the workflow based on combination of Payment " \
    #                   "Gateway(such as Bank Transfer etc.) and Financial Status(such as Pending Orders," \
    #                   "Completed Orders etc.).\n - In this order, Payment Gateway is %s and Financial Status is %s.\n " \
    #                   "- You can configure the Automatic order process workflow under the menu Magento > Configuration" \
    #                   " > Financial Status." % (order_response.get('increment_id'), payment_method,
    #                                             financial_status_name)
    #     elif not workflow_config.auto_workflow_id and financial_status_name != "":
    #         skip_order = True
    #         message = "Order %s skipped due to auto workflow configuration not found for payment method - %s " \
    #                   "and financial status - %s" % (order_ref, payment_method, financial_status_name)
    #     elif not workflow_config.payment_term_id and financial_status_name != "":
    #         skip_order = True
    #         message = "Order %s skipped due to Payment Term not found in payment method - %s and financial status -" \
    #                   "%s" % (order_ref, payment_method, financial_status_name)
    #     elif max_days:
    #         order_date = datetime.strptime(order_response.get('created_at'), '%Y-%m-%d %H:%M:%S')
    #         if order_date + timedelta(days=max_days) < datetime.now():
    #             skip_order = True
    #             message = '%s has not been imported because it is %d before.' % (order_ref, max_days)
    #     elif import_rule == 'never':
    #         skip_order = True
    #         message = "Orders with payment method %s have the rule never to be imported." % payment_method
    #     elif not amount_paid and import_rule == 'paid':
    #         skip_order = True
    #         message = "Order '%s' has not been paid yet, So order will be imported later" % order_ref
    #     return skip_order, message

    # def check_products_exist_in_odoo(self, order_response, magento_instance, order_ref, order_data_queue_line_id,
    #                                  log_book_id):
    #     """
    #     Check if products in imported order exist in Odoo.
    #     :param order_response: Order Response received from Magento
    #     :param magento_instance: Instance of Magento
    #     :param order_ref: Order reference
    #     :param order_data_queue_line_id: Order data queue line id
    #     :return: common log book object and skip order
    #     """
    #     skip_order = False
    #     message = ""
    #
    #     for order_item in order_response:
    #         prod_sku = order_item.get('sku')
    #         if order_item.get('product_type') not in ['simple', 'configurable']:
    #             message = "Order %s skipped due to %s product type is not supported" % (
    #                 order_ref, order_item.get('product_type')
    #             )
    #             break
    #
    #         # Check the ordered product is already exist in the magento product product layer or not.
    #         magento_product_obj = self.env['magento.product.product'].search(
    #             [('magento_instance_id', '=', magento_instance.id),
    #              ('magento_sku', '=', order_item.get('sku'))], limit=1)
    #         if not magento_product_obj:
    #             message = "Order %s skipped due to product with sku '%s' is missed " \
    #                       "in magento layer in Odoo" % (order_ref, prod_sku)
    #             break
    #
    #     if message:
    #         skip_order = True
    #         log_book_id.add_log_line(message, order_ref, order_data_queue_line_id, "magento_order_data_queue_line_id",
    #                                  prod_sku)
    #     return skip_order

    # def create_magento_sales_order_vals(self, partner_dict, order_response, magento_instance_id, price_list,
    #                                     log_book_id, order_data_queue_line_id):
    #     """
    #     Prepare dictionary for Magento sale order
    #     :param partner_dict: partner invoice address and delivery address dictionary
    #     :param order_response: order dictionary received from Magento API
    #     :param magento_instance_id: instance of Magento
    #     :param price_list: Product price list object
    #     :return: Dictionary of sale order values
    #     """
    #     skip_order = False
    #     shipping = order_response.get('extension_attributes').get('shipping_assignments')
    #     shipping_method = shipping[0].get('shipping').get('method') or False
    #     shipping_carrier = magento_instance_id.shipping_method_ids.filtered(lambda x: x.carrier_code == shipping_method)
    #     delivery_method = shipping_carrier.delivery_carrier_ids.filtered(
    #         lambda x: x.magento_carrier_code == shipping_method
    #     )
    #     payment_method = order_response['payment'].get('method')
    #     payment_option = magento_instance_id.payment_method_ids.filtered(
    #         lambda x: x.payment_method_code == payment_method
    #     )
    #     store_id = order_response.get('store_id')
    #     store_view = magento_instance_id.magento_website_ids.store_view_ids.filtered(
    #         lambda x: x.magento_storeview_id == str(store_id)
    #     )
    #     if not store_view.magento_website_id.warehouse_id.id:
    #         skip_order = True
    #         message = ("Warehouse is not set for the %s website.\n Please configure it from Magento Instance > "
    #                    "Magento Website > Select Website.") % store_view.magento_website_id.name
    #         log_book_id.add_log_line(message, order_response['increment_id'], order_data_queue_line_id,
    #                                  "magento_order_data_queue_line_id")
    #         return {}, skip_order
    #     order_values = self.prepare_order_vals_dict(magento_instance_id, partner_dict, order_response, price_list,
    #                                                 payment_option, store_view, delivery_method)
    #     order_values = self.create_sales_order_vals_ept(order_values)
    #     order_values = self.update_order_vals_dict(order_values, magento_instance_id, store_view, order_response,
    #                                                shipping_carrier, payment_option)
    #     return order_values, skip_order

    # def prepare_order_vals_dict(self, magento_instance, partner_dict, order_response, price_list, payment_option,
    #                             store_view, delivery_method):
    #     """
    #     Prepare dictionary of order values
    #     :param magento_instance: Magento Instance object
    #     :param partner_dict: Dictionary of partners
    #     :param order_response: Response received from Magento.
    #     :param price_list: Product price list object
    #     :param payment_option: Magento payment method object
    #     :param store_view: Magento store view object
    #     :param delivery_method: Delivery carrier object
    #     :return: Dictionary of order values
    #     """
    #     financial_status, financial_status_name = self.search_order_financial_status(order_response, magento_instance,
    #                                                                                  payment_option)
    #     workflow_process_id = False
    #     payment_term_id = False
    #     if financial_status and financial_status.auto_workflow_id:
    #         workflow_process_id = financial_status.auto_workflow_id
    #         payment_term_id = financial_status.payment_term_id
    #     ordervals = {
    #         'company_id': magento_instance.company_id.id,
    #         'partner_id': partner_dict.get('partner'),
    #         'partner_invoice_id': partner_dict.get('invoice_partner'),
    #         'partner_shipping_id': partner_dict.get('shipping_partner'),
    #         'warehouse_id': store_view.magento_website_id.warehouse_id.id,
    #         'picking_policy': workflow_process_id and workflow_process_id.picking_policy or False,
    #         'date_order': order_response.get('created_at', False),
    #         'pricelist_id': price_list and price_list.id or False,
    #         'team_id': store_view and store_view.team_id and store_view.team_id.id or False,
    #         'payment_term_id': payment_term_id and payment_term_id.id or False,
    #         'carrier_id': delivery_method and delivery_method.id or False,
    #         'client_order_ref': order_response.get('increment_id')
    #     }
    #     return ordervals

    # def update_order_vals_dict(self, ordervals, magento_instance, store_view, order_response, shipping_carrier,
    #                            payment_option):
    #     """
    #     Update dictionary of order values
    #     :param ordervals: Dictionary of order values
    #     :param magento_instance: Magento Instance object
    #     :param store_view: Magento Store view object
    #     :param order_response: Response received from Magento.
    #     :param shipping_carrier: Magento delivery carrier object
    #     :param payment_option: Magento payment method object
    #     :return:
    #     """
    #     order_ref = order_response.get('increment_id')
    #     financial_status, financial_status_name = self.search_order_financial_status(order_response, magento_instance,
    #                                                                                  payment_option)
    #     workflow_process_id = False
    #     if financial_status.auto_workflow_id:
    #         workflow_process_id = financial_status.auto_workflow_id.id
    #     magento_payment_method_id = False
    #     if payment_option and payment_option.id:
    #         magento_payment_method_id = payment_option.id
    #     payment_additional_info = order_response.get('extension_attributes').get('payment_additional_info') if \
    #         order_response.get('extension_attributes').get('payment_additional_info') else False
    #     transaction_id = False
    #     if payment_additional_info:
    #         for payment_info in payment_additional_info:
    #             if payment_info.get('key') == 'transaction_id':
    #                 transaction_id = payment_info.get('value')
    #     storeview_id = magento_website = False
    #     if store_view:
    #         storeview_id = store_view.id
    #         magento_website = store_view.magento_website_id.id
    #     ordervals.update({
    #         'magento_instance_id': magento_instance.id,
    #         'magento_website_id': magento_website,
    #         'store_id': storeview_id,
    #         'auto_workflow_process_id': workflow_process_id,
    #         'magento_payment_method_id': magento_payment_method_id,
    #         'magento_shipping_method_id': shipping_carrier.id,
    #         'is_exported_to_magento_shipment_status': False,
    #         'magento_order_id': order_response.get('items')[0].get('order_id'),
    #         'magento_order_reference': order_ref,
    #         'order_transaction_id': transaction_id
    #     })
    #     if store_view and not store_view.is_use_odoo_order_sequence:
    #         name = "%s%s" % (store_view and store_view.sale_prefix or '', order_ref)
    #         ordervals.update({"name": name})
    #     return ordervals

    # def create_magento_sale_order_line(self, order_response, instance, magento_order, log_book_id, order_dict):
    #     """
    #     Create shipping order line and order discount line and sale order line.
    #     :param order_response: order dictionary received from Magento API
    #     :param instance: instance of Magento
    #     :param magento_order: sale order object
    #     """
    #     skip_order, sale_order_lines = self.env[SALE_ORDER_LINE].magento_create_sale_order_line(
    #         instance, order_response, magento_order, log_book_id, order_dict
    #     )
    #     if not skip_order:
    #         skip_order = self.create_shipping_order_line(order_response, magento_order, log_book_id, order_dict)
    #         if not skip_order:
    #             skip_order = self.create_discount_order_line(order_response, magento_order, log_book_id, order_dict)
    #     return skip_order

    # def create_shipping_order_line(self, order_response, magento_order, log_book_id, order_dict):
    #     """
    #     Create Shipping order line.
    #     :param order_response: Response received from Magento.
    #     :param magento_order: Sale order object
    #     :return:
    #     """
    #     sale_order_line_obj = self.env[SALE_ORDER_LINE]
    #     shipping_amount_incl = float(order_response.get('shipping_incl_tax', 0.0))
    #     shipping_amount_excl = float(order_response.get('shipping_amount', 0.0))
    #     if shipping_amount_incl or shipping_amount_excl:
    #         account_tax_obj = self.env['account.tax']
    #         shipping_product = self.env.ref('odoo_magento2_ept.product_product_shipping')
    #         tax_id = False
    #         extension_attributes = order_response.get('extension_attributes')
    #         is_tax_included, tax_percent = self.check_shipping_has_tax_included_and_percent(extension_attributes)
    #         price = shipping_amount_incl if is_tax_included else shipping_amount_excl
    #         shipping_line = sale_order_line_obj.create_sale_order_line_vals(
    #             order_response, price, shipping_product, magento_order
    #         )
    #         if tax_percent:
    #             tax_id = account_tax_obj.get_tax_from_rate(rate=float(tax_percent), is_tax_included = is_tax_included)
    #             if tax_id and not tax_id.active:
    #                 skip_order = True
    #                 message = "Shipping Line : The system unable to find the tax '%s'. " \
    #                           "\nPlease check if the Tax is archived?." % (tax_id.name)
    #                 log_book_id.add_log_line(message, order_response['increment_id'],
    #                                          order_dict.id, "magento_order_data_queue_line_id")
    #                 return skip_order
    #             if not tax_id:
    #                 name = '%s %% ' % (tax_percent)
    #                 tax_id = account_tax_obj.sudo().create({
    #                     'name': name,
    #                     'description': name,
    #                     'amount_type': 'percent',
    #                     'price_include': is_tax_included,
    #                     'amount': float(tax_percent),
    #                     'type_tax_use': 'sale',
    #                 })
    #         if tax_id:
    #             shipping_line.update({
    #                 'tax_id': [(6, 0, tax_id.ids)]
    #             })
    #         sale_order_line_obj.create(shipping_line)
    #
    # def create_discount_order_line(self, order_response, magento_order, log_book_id, order_dict):
    #     """
    #     Create discount order line.
    #     :param order_response: Response received from Magento.
    #     :param magento_order: Sale order object
    #     :return:
    #     """
    #     sale_order_line_obj = self.env[SALE_ORDER_LINE]
    #     account_tax_obj = self.env['account.tax']
    #     discount_amount = float(order_response.get('discount_amount') or 0.0) or False
    #     if discount_amount:
    #         tax_id = False
    #         discount_product = self.env.ref('odoo_magento2_ept.magento_product_product_discount')
    #         discount_line = sale_order_line_obj.create_sale_order_line_vals(
    #             order_response, discount_amount, discount_product, magento_order
    #         )
    #         is_tax_included, tax_percent = self.check_discount_has_tax_included_and_percent(order_response)
    #         if tax_percent:
    #             tax_id = account_tax_obj.get_tax_from_rate(rate=float(tax_percent), is_tax_included = is_tax_included)
    #             if tax_id and not tax_id.active:
    #                 skip_order = True
    #                 message = "Discount Line : The system unable to find the tax '%s'. " \
    #                           "\nPlease check if the Tax is archived?." % (
    #                     tax_id.name)
    #                 log_book_id.add_log_line(message, order_response['increment_id'],
    #                                          order_dict.id, "magento_order_data_queue_line_id")
    #                 return skip_order
    #             if not tax_id:
    #                 name = '%s %% ' % (tax_percent)
    #                 tax_id = account_tax_obj.sudo().create({
    #                     'name': name,
    #                     'description': name,
    #                     'amount_type': 'percent',
    #                     'price_include': is_tax_included,
    #                     'amount': float(tax_percent),
    #                     'type_tax_use': 'sale',
    #                 })
    #         if tax_id:
    #             discount_line.update({
    #                 'tax_id': [(6, 0, tax_id.ids)]
    #             })
    #         sale_order_line_obj.create(discount_line)

    def cancel_order_from_magento_by_webhook(self):
        """
        this method will call while sale order cancel from webhook
        :return:
        """
        try:
            super(SaleOrder, self).action_cancel()
        except Exception as error:
            raise UserError("Error cancel the order via Magento admin: " +  error)
        # if not result:
        #     message = str(message) + " Odoo Sale Order : %s" \
        #                              " , Magento Order ID : %s" % (self.name, self.magento_order_id)
            # model_id = self.env['common.log.lines.ept'].sudo().get_model_id('sale.order')
            # self.env['common.log.book.ept'].sudo().create({
            #     'type': 'import',
            #     'module': 'magento_ept',
            #     'model_id': model_id,
            #     'res_id': self.id,
            #     'magento_instance_id': self.magento_instance_id.id,
            #     'log_lines': [(0, 0, {
            #         'message': message,
            #         'order_ref': self.name,
            #     })]
            # })
        return True

    def cancel_order_in_magento(self):
        """
        This method use for cancel order in magento.
        @return: result
        """
        result = super(SaleOrder, self).action_cancel()
        magento_order_id = self.magento_order_id
        if magento_order_id:
            magento_instance = self.magento_instance_id
            try:
                api_url = '/V1/orders/%s/cancel' % magento_order_id
                result = req(magento_instance, api_url, 'POST')
            except Exception:
                raise UserError("Error while requesting cancel order")
        return result

    def _prepare_invoice(self):
        """
        This method is used for set necessary value(is_exported_to_magento, magento_instance_id)
         to the invoice.
        :return:
        """
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.magento_payment_method_id:
            invoice_vals['magento_payment_method_id'] = self.magento_payment_method_id.id
        if self.magento_instance_id:
            invoice_vals.update({
                'magento_instance_id': self.magento_instance_id.id,
                # 'is_magento_invoice': True,
                'is_exported_to_magento': False
            })
        return invoice_vals

    def process_sale_order_workflow_based_on_status(self, sales_order):
        """
        Call sale order workflow based on magento order status
        :param sales_order: order response received from Magento
        """
        # auto_work_flow_obj = self.env['sale.workflow.process.ept']
        # if order_response.get('status') == 'complete' or \
        #         (order_response.get('status') == 'processing' and
        #          order_response.get('extension_attributes').get('is_shipment')):
        #     magento_order.auto_workflow_process_id.with_context(
        #         log_book_id=log_book_id.id).shipped_order_workflow_ept(magento_order)
        # else:
        #     auto_work_flow_obj.auto_workflow_process_ept(magento_order.auto_workflow_process_id.id,
        #                                                  [magento_order.id])

        message = self.auto_workflow_process_id.auto_workflow_process(self.auto_workflow_process_id.id, [self.id])

        if message:
            return message
        # else:
        #     if (sales_order.get('status') == 'processing' and
        #         sales_order.get('payment').get('amount_paid')) and self.invoice_ids:
        #         # Here the magento order is complete state or
        #         # processing state with invoice so invoice is already created
        #         # So Make the Export invoice as true to hide Export invoice button from invoice.
        #         self.invoice_ids.write({'is_exported_to_magento': True})
        return ''


    @staticmethod
    def check_discount_has_tax_included_and_percent(sales_order):
        """
        Check order tax applied is including/ excluding and tax percent.
        :param sales_order: response received from order.
        :return: True/False
        """
        is_tax_included = True
        tax_percent = False
        extension_attributes = sales_order.get('extension_attributes')
        if extension_attributes and "apply_discount_on_prices" in extension_attributes:
            if extension_attributes.get('apply_discount_on_prices', False) == 'excluding_tax':
                is_tax_included = False
        for order_items in sales_order.get('items'):
            tax_percent = order_items.get('tax_percent', False)
            break
        return is_tax_included, tax_percent

    @staticmethod
    def check_shipping_has_tax_included_and_percent(extension_attributes):
        """
        Check order tax applied is including/ excluding and tax percent.
        :param extension_attributes: extension attributes received from order.
        :return: True/False
        """
        is_tax_included = True
        tax_percent = False
        if "apply_shipping_on_prices" in extension_attributes:
            apply_shipping_on_prices = extension_attributes.get('apply_shipping_on_prices')
            if apply_shipping_on_prices == 'excluding_tax':
                is_tax_included = False
        if "item_applied_taxes" in extension_attributes:
            for order_res in extension_attributes.get("item_applied_taxes"):
                if order_res.get('type') == "shipping" and order_res.get('applied_taxes'):
                    shipping_tax_dict = order_res.get('applied_taxes')[0]
                    if shipping_tax_dict:
                        tax_percent = shipping_tax_dict.get('percent')
        return is_tax_included, tax_percent

    #added by SPf
    def _carrier_name(self):
        """"
        Computes full Magento Carrier Name
        :return:
        """
        for record in self:
            record.magento_carrier_name = str(record.magento_shipping_method_id.magento_carrier_title) + ' / ' + \
                                          str(record.magento_shipping_method_id.carrier_label)

    def process_sales_order_creation(self, magento_instance, sales_order):
        order_ref = sales_order.get('increment_id')
        payment_method = sales_order.get('payment').get('method')
        order_lines = sales_order.get('items')

        magento_order = self.search([
            ('magento_instance_id', '=', magento_instance.id),
            ('magento_order_reference', '=', order_ref)
        ])
        log_errors = self.env['magento.orders.log.book'].search([
            ('magento_instance_id', '=', magento_instance.id),
            ('magento_order_ref', '=', order_ref)
        ])

        storeview_id = self.env['magento.storeview'].search([
            ('magento_instance_id', '=', magento_instance.id),
            ('magento_storeview_id', '=', str(sales_order.get('store_id')))
        ], limit=1)
        if not storeview_id:
            message = 'Magento Order Storeview not found in Odoo. Please synch the Instance Metadata.'
            self.log_order_import_error(log_errors, order_ref, magento_instance, False, message)
            return False

        website = storeview_id.magento_website_id

        message = self.check_magento_payment_method_configuration_adj(magento_instance, sales_order, payment_method)
        if message:
            self.log_order_import_error(log_errors, order_ref, magento_instance, website, message)
            return False

        message = self.check_magento_shipping_method_adj(magento_instance, sales_order)
        if message:
            self.log_order_import_error(log_errors, order_ref, magento_instance, website, message)
            return False

        message = self.check_pricelist_for_order(sales_order, website)
        if message:
            self.log_order_import_error(log_errors, order_ref, magento_instance, website, message)
            return False

        odoo_partner, magento_partner, message = self.env['res.partner'].process_customer_creation_or_update(
            magento_instance, sales_order, website
        )
        if message:
            self.log_order_import_error(log_errors, order_ref, magento_instance, website, message)
            return False

        message = self.check_products_exist_and_prices(magento_instance, order_lines, website, odoo_partner)
        if message:
            self.log_order_import_error(log_errors, order_ref, magento_instance, website, message)
            return False

        order_values, message = self.prepare_sales_order_values(magento_instance, website, sales_order, odoo_partner)
        if message:
            self.log_order_import_error(log_errors, order_ref, magento_instance, website, message)
            return False

        # check if order exist or create new
        if magento_order:
            if log_errors.filtered(lambda x: not x.processing_error):
                magento_order.write(order_values)
            else:
                return True
        else:
            try:
                magento_order = self.create(order_values)
            except Exception as e:
                message = e

        if not magento_order:
            message = "Error while creating sales order in Magento: " + str(message)
            self.log_order_import_error(log_errors, order_ref, magento_instance, website, message)
            return False

        message = self.create_magento_sale_order_line_adj(magento_instance, sales_order, magento_order)
        if message:
            self.log_order_import_error(log_errors, order_ref, magento_instance, website, message)
            return False

        message = magento_order.process_sale_order_workflow_based_on_status(sales_order)
        if message:
            message = "Error to process order: " + str(message)
            self.log_order_import_error(log_errors, order_ref, magento_instance, website, message, True)
            return False

        # will archive log errors if any
        if log_errors:
            log_errors.write({'active': False})

        return True

    def check_magento_payment_method_configuration_adj(self, magento_instance, sales_order, payment_method):
        message = ''
        order_ref = sales_order['increment_id']
        amount_paid = sales_order.get('payment').get('amount_paid', False)
        payment_option = magento_instance.payment_method_ids.filtered(lambda x: x.payment_method_code == payment_method)
        if not payment_option:
            return "Payment method %s is not found in Magento Layer. " \
                   "Please synchronize Instance Metadata" % payment_method
        import_rule = payment_option.import_rule

        workflow_config, financial_status_name = self.search_order_financial_status_adj(magento_instance, sales_order,
                                                                                        payment_option)
        if not workflow_config:
            message = "- Automatic order process workflow configuration not found for this order %s. \n -" \
                      " System tries to find the workflow based on combination of Payment Gateway (such as" \
                      " Bank Transfer etc.) and Financial Status(such as Pending Orders, Completed Orders etc.).\n" \
                      "- In this order, Payment Gateway is %s and Financial Status is %s.\n " \
                      "- You can configure the Automatic order process workflow under the menu Magento >> Configuration" \
                      " >> Financial Status." % (sales_order.get('increment_id'), payment_method,
                                                financial_status_name)
        elif not workflow_config.auto_workflow_id and financial_status_name != "":
            message = "Order %s was not proceeded due to auto workflow configuration not found for payment method - %s " \
                      "and financial status - %s" % (order_ref, payment_method, financial_status_name)
        elif not workflow_config.payment_term_id and financial_status_name != "":
            message = "Order %s skipped due to Payment Term not found in payment method - %s and financial status -" \
                      "%s" % (order_ref, payment_method, financial_status_name)
        elif import_rule == 'never':
            message = "Orders with payment method %s have the rule never to be imported." % payment_method
        elif not amount_paid and import_rule == 'paid':
            message = "Order '%s' has not been paid yet, So order will be imported later" % order_ref
        return message

    def check_magento_shipping_method_adj(self, magento_instance, sales_order):
        message = ""
        magento_carrier = False
        order_reference = sales_order.get('increment_id')
        shipping = sales_order.get('extension_attributes').get('shipping_assignments')
        shipping_method = shipping[0].get('shipping').get('method') or False

        if not shipping_method:
            message = "Delivery method is not found in Order %s" % order_reference
        else:
            magento_carrier = magento_instance.shipping_method_ids.filtered(lambda x: x.carrier_code == shipping_method)
            if not magento_carrier:
                message = "Order %s has failed to proceed due to shipping %s not found in Delivery Methods" % (
                    order_reference, shipping_method)

        if magento_carrier:
            delivery_carrier = magento_carrier.delivery_carrier_ids.filtered(
                lambda x: x.magento_carrier_code == shipping_method
            )
            if not delivery_carrier:
                product = self.env.ref('odoo_magento2_ept.product_product_shipping')
                try:
                    self.env["delivery.carrier"].create({
                        'name': magento_carrier.carrier_label,
                        'product_id': product.id,
                        'magento_carrier': magento_carrier.id
                    })
                except Exception as err:
                    message = "Error while creating new delivery carrier: " + str(err)

        return message

    def check_products_exist_and_prices(self, magento_instance, order_lines, website, odoo_partner):
        message = ""

        for order_item in order_lines:
            prod_sku = order_item.get('sku')
            if order_item.get('product_type') != 'simple':
                message = "%s product type is not supported for the product with %s sku" % (
                    order_item.get('product_type'), prod_sku)
                break

            # Check the ordered product exist in the magento layer or not.
            magento_product = self.env['magento.product.product'].search([
                ('magento_instance_id', '=', magento_instance.id), ('magento_sku', '=', prod_sku)
            ], limit=1)
            if not magento_product:
                message = "Product with sku '%s' is missed in magento layer in Odoo" % (prod_sku)
                break

            # check if product prices are the same
            odoo_price = website.pricelist_id.get_product_price(
                magento_product.odoo_product_id,
                order_item.get('qty_invoiced', 1),
                odoo_partner
            )

            if odoo_price != order_item.get('price'):
                message = "Product prices are not matched: Odoo price - %s and Magento price - %s" % (
                    odoo_price, order_item.get('price')
                )
                break

        return message

    def check_pricelist_for_order(self, sales_order, website):
        message = ""
        order_currency = sales_order.get('order_currency_code')

        if website.pricelist_id:
            if order_currency != website.pricelist_id.currency_id.name:
                message = "Order currency in Magento %s and Price list currency in Odoo %s do not match." % (
                    order_currency, website.pricelist_id.currency_id.name)
        else:
            message = "%s website is missing Price list to be defined in Magento Configurations in Odoo" % (
                website.name)

        return message

    def prepare_sales_order_values(self, magento_instance, website, sales_order, odoo_partner):
        shipping = sales_order.get('extension_attributes').get('shipping_assignments')
        shipping_method = shipping[0].get('shipping').get('method')
        shipping_carrier = magento_instance.shipping_method_ids.filtered(lambda x: x.carrier_code == shipping_method)
        delivery_method = shipping_carrier.delivery_carrier_ids.filtered(
            lambda x: x.magento_carrier_code == shipping_method
        )
        payment_option = magento_instance.payment_method_ids.filtered(
            lambda x: x.payment_method_code == sales_order.get('payment').get('method')
        )
        store_view = magento_instance.magento_website_ids.store_view_ids.filtered(
            lambda x: x.magento_storeview_id == str(sales_order.get('store_id'))
        )
        if not website.warehouse_id.id:
            return {}, ("Warehouse is not set for the %s website.\n Please configure it from Magento Instance >> "
                       "Magento Website >> Select Website.") % website.name

        financial_status, financial_status_name = self.search_order_financial_status_adj(magento_instance, sales_order,
                                                                                         payment_option)
        workflow_process_id = financial_status.auto_workflow_id
        payment_term_id = financial_status.payment_term_id

        # get Odoo's invoice and delivery partners(addresses)
        invoice_partner = odoo_partner.magento_res_partner_ids.filtered(
            lambda x: x.magento_instance_id == magento_instance).customer_address_ids.filtered(
            lambda y: y.magento_customer_address_id == str(sales_order.get("billing_address").get("entity_id"))
        ).odoo_partner_id
        shipping_partner = odoo_partner.magento_res_partner_ids.filtered(
            lambda x: x.magento_instance_id == magento_instance).customer_address_ids.filtered(
            lambda y: y.magento_customer_address_id == str(shipping[0].get('shipping').get('address').get("entity_id"))
        ).odoo_partner_id

        order_vals = {
            'company_id': magento_instance.company_id.id,
            'partner_id': odoo_partner.id,
            'partner_invoice_id': invoice_partner.id,
            'partner_shipping_id': shipping_partner.id,
            'warehouse_id': website.warehouse_id.id,
            'picking_policy': workflow_process_id and workflow_process_id.picking_policy or False,
            'date_order': sales_order.get('created_at', False),
            'pricelist_id': website.pricelist_id.id,
            'team_id': store_view and store_view.team_id and store_view.team_id.id or False,
            'payment_term_id': payment_term_id and payment_term_id.id or False,
            'carrier_id': delivery_method and delivery_method.id or False,
            'client_order_ref': sales_order.get('increment_id')
        }

        order_values = self.create_sales_order_vals(order_vals)

        # payment_additional_info = sales_order.get('extension_attributes').get('payment_additional_info') or False
        # transaction_id = False
        # if payment_additional_info:
        #     for payment_info in payment_additional_info:
        #         if payment_info.get('key') == 'transaction_id':
        #             transaction_id = payment_info.get('value')

        order_values.update({
            'magento_instance_id': magento_instance.id,
            'magento_website_id': website.id,
            'store_id': store_view.id if store_view else False,
            'auto_workflow_process_id': workflow_process_id.id,
            'magento_payment_method_id': payment_option.id,
            'magento_shipping_method_id': shipping_carrier.id,
            'is_exported_to_magento_shipment_status': False,
            'magento_order_id': sales_order.get('entity_id'),
            'magento_order_reference': sales_order.get('increment_id'),
            # 'order_transaction_id': transaction_id
        })

        if store_view and not store_view.is_use_odoo_order_sequence:
            name = "%s%s" % (store_view and store_view.sale_prefix or '', sales_order.get('increment_id'))
            order_values.update({"name": name})

        return order_values, ''

    def create_magento_sale_order_line_adj(self, instance, sales_order, magento_order):
        if not self.env[SALE_ORDER_LINE].magento_create_sale_order_line_adj(instance, sales_order, magento_order):
            return "Error while creating Product Sales Order lines"
        else:
            message = self.create_shipping_order_line_adj(sales_order, magento_order)
            if message:
                return message
            else:
                return self.create_discount_order_line_adj(sales_order, magento_order)

    def search_order_financial_status_adj(self, magento_instance, sales_order, payment_option):
        is_invoiced = sales_order.get('payment').get('amount_paid') or False
        financial_status_code, financial_status_name = self.get_magento_financial_status_adj(
            sales_order.get('status'), is_invoiced
        )
        workflow_config = self.env['magento.financial.status.ept'].search(
            [('magento_instance_id', '=', magento_instance.id),
             ('payment_method_id', '=', payment_option.id),
             ('financial_status', '=', financial_status_code)])

        return workflow_config, financial_status_name

    @staticmethod
    def get_magento_financial_status_adj(order_status, is_invoiced):
        financial_status_code = financial_status_name = ''
        if order_status == "pending":
            financial_status_code = 'not_paid'
            financial_status_name = 'Pending Orders'
        elif order_status == "processing" and is_invoiced:
            financial_status_code = 'processing_paid'
            financial_status_name = 'Processing orders with Invoice'
        return financial_status_code, financial_status_name

    def create_shipping_order_line_adj(self, sales_order, magento_order):
        sale_order_line_obj = self.env[SALE_ORDER_LINE]
        shipping_amount_incl = float(sales_order.get('shipping_incl_tax', 0.0))
        shipping_amount_excl = float(sales_order.get('shipping_amount', 0.0))

        if shipping_amount_incl or shipping_amount_excl:
            account_tax_obj = self.env['account.tax']
            shipping_product = self.env.ref('odoo_magento2_ept.product_product_shipping')
            tax_id = False
            extension_attributes = sales_order.get('extension_attributes')
            is_tax_included, tax_percent = self.check_shipping_has_tax_included_and_percent(extension_attributes)
            price = shipping_amount_incl if is_tax_included else shipping_amount_excl
            shipping_line = sale_order_line_obj.create_sale_order_line_vals(
                sales_order, price, shipping_product, magento_order
            )
            if tax_percent:
                tax_id = account_tax_obj.get_tax_from_rate(rate=float(tax_percent), is_tax_included = is_tax_included)
                if tax_id and not tax_id.active:
                    return "Shipping Line: The system unable to find the tax '%s'.\n" \
                           "Please check if the Tax is archived?." % (tax_id.name)
                if not tax_id:
                    name = '%s %% ' % (tax_percent)
                    tax_id = account_tax_obj.sudo().create({
                        'name': name,
                        'description': name,
                        'amount_type': 'percent',
                        'price_include': is_tax_included,
                        'amount': float(tax_percent),
                        'type_tax_use': 'sale',
                    })
            if tax_id:
                shipping_line.update({
                    'tax_id': [(6, 0, tax_id.ids)]
                })
            try:
                line = sale_order_line_obj.create(shipping_line)
            except Exception as e:
                return 'Error creating shipping order line: ' + str(e)

            if not line:
                return "Error creating shipping order line."

        return ''

    def create_discount_order_line_adj(self, sales_order, magento_order):
        sale_order_line_obj = self.env[SALE_ORDER_LINE]
        account_tax_obj = self.env['account.tax']
        discount_amount = float(sales_order.get('discount_amount') or 0.0) or False
        if discount_amount:
            tax_id = False
            discount_product = self.env.ref('odoo_magento2_ept.magento_product_product_discount')
            discount_line = sale_order_line_obj.create_sale_order_line_vals(
                sales_order, discount_amount, discount_product, magento_order
            )
            is_tax_included, tax_percent = self.check_discount_has_tax_included_and_percent(sales_order)
            if tax_percent:
                tax_id = account_tax_obj.get_tax_from_rate(rate=float(tax_percent), is_tax_included = is_tax_included)
                if tax_id and not tax_id.active:
                    return "Discount Line: The system unable to find the tax '%s'.\n" \
                           "Please check if the Tax is archived?." % (tax_id.name)
                if not tax_id:
                    name = '%s %% ' % (tax_percent)
                    tax_id = account_tax_obj.sudo().create({
                        'name': name,
                        'description': name,
                        'amount_type': 'percent',
                        'price_include': is_tax_included,
                        'amount': float(tax_percent),
                        'type_tax_use': 'sale',
                    })
            if tax_id:
                discount_line.update({
                    'tax_id': [(6, 0, tax_id.ids)]
                })
            try:
                line = sale_order_line_obj.create(discount_line)
            except Exception as e:
                return 'Error creating discount order line:' + str(e)

            if not line:
                return 'Error creating discount order line'

        return ''

    def log_order_import_error(self, log_errors, order_ref, instance, website, message, processing_error=False):
        data = {
            'sale_order_id': self.id,
            'processing_error': processing_error,
            'magento_order_ref': order_ref,
            'magento_instance_id': instance.id,
            'magento_website_id': website and website.id,
            'log_message': message
        }

        if log_errors:
            log_errors.write(data)
        else:
            log_errors.create(data)
