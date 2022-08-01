# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from ..python_library.api_request import req


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    magento_instance_id = fields.Many2one('magento.instance', string="Magento Instance")
    magento_order_id = fields.Char(string="Order Id")
    magento_order_status = fields.Char(string="Order Status")
    magento_website_id = fields.Many2one("magento.website", string="Magento Website")
    magento_order_reference = fields.Char(string="Magento Order Ref.", help="Order Reference in Magento")
    store_id = fields.Many2one('magento.storeview', string="Magento Storeview")
    magento_payment_method_id = fields.Many2one('magento.payment.method', string="Payment Method")
    magento_shipping_method_id = fields.Many2one('magento.delivery.carrier', string="Shipping Method")
    payment_transaction_code = fields.Char(string="Payment Trans. Code", help="Magento Payment System Transaction ID")
    order_currency_code = fields.Char(string="Order Currency")
    order_total_amount = fields.Float(string="Order Amount")
    magento_carrier_name = fields.Char(compute="_compute_magento_carrier_name", string="Magento Carrier Name")
    magento_order_log_book_ids = fields.One2many('magento.orders.log.book', 'sale_order_id', "Logged Error Messages")
    auto_workflow_process_id = fields.Many2one("sale.workflow.process", string="Workflow Process", copy=False)
    paym_trans_ids_nbr = fields.Integer(compute='_compute_paym_trans_ids_nbr', string='# of Payment Transactions')
    moves_count = fields.Integer(compute="_compute_stock_move", string="Stock Move", store=False,
                                 help="Stock Move Count for Orders without Picking.")
    is_canceled_in_magento = fields.Boolean(string="Canceled in Magento", default=False,
                                            help="Checked, if order was canceled in Magento")

    _sql_constraints = [('_magento_sale_order_unique_constraint',
                         'unique(magento_order_id,magento_instance_id,magento_order_reference)',
                         "Magento order must be unique")]

    @api.depends('magento_shipping_method_id')
    def _compute_magento_carrier_name(self):
        for record in self:
            record.magento_carrier_name = str(record.magento_shipping_method_id.magento_carrier_title) + ' / ' + \
                                          str(record.magento_shipping_method_id.carrier_label)

    def _compute_stock_move(self):
        stock_move_obj = self.env["stock.move"]
        for rec in self:
            rec.moves_count = stock_move_obj.search_count([("picking_id", "=", False),
                                                           ("sale_line_id", "in", self.order_line.ids)])

    @api.depends('transaction_ids')
    def _compute_paym_trans_ids_nbr(self):
        for order in self:
            order.paym_trans_ids_nbr = len(order.transaction_ids)

    def action_view_stock_move_(self):
        stock_move_obj = self.env['stock.move']
        move_ids = stock_move_obj.search([('picking_id', '=', False), ('sale_line_id', 'in', self.order_line.ids)]).ids
        action = {
            'domain': "[('id', 'in', " + str(move_ids) + " )]",
            'name': 'Order Stock Move',
            'view_mode': 'tree,form',
            'res_model': 'stock.move',
            'type': 'ir.actions.act_window',
        }
        return action

    def process_orders_and_invoices(self):
        for order in self:
            message = ''
            work_flow_process_rec = order.auto_workflow_process_id

            if order.invoice_status == 'invoiced':
                continue

            if order.state in ['draft', 'sent'] and work_flow_process_rec.validate_order:
                date_order = order.date_order
                order.action_confirm()
                order.write({'date_order': date_order})

            if work_flow_process_rec.create_invoice:
                if order.invoice_ids:
                    invoices = order.invoice_ids
                else:
                    invoices = self._create_invoices()

            if work_flow_process_rec.register_payment:
                if not order.transaction_ids:
                    if order.magento_payment_method_id.payment_acquirer_id:
                        currency = self.env['res.currency'].search([('name', '=', order.order_currency_code)])
                        paym_trans = self.env['payment.transaction'].search([('reference', '=', order.name)])

                        if paym_trans:
                            cnt = len(self.env['payment.transaction'].search([('reference', 'ilike', order.name + '%')]))
                            ref = order.name + f'-{cnt}'
                        else:
                            ref = order.name

                        vals = {
                            'acquirer_id': order.magento_payment_method_id.payment_acquirer_id.id,
                            'reference': ref,
                            'state': 'done',
                            'acquirer_reference': order.payment_transaction_code,
                            'amount': order.order_total_amount,
                            'currency_id': currency.id if currency else False,
                            'partner_id': order.partner_id.id,
                            'sale_order_ids': [order.id]
                        }

                        if work_flow_process_rec.create_invoice and invoices:
                            vals.update({'invoice_ids': invoices.ids})

                        try:
                            self.env['payment.transaction'].create(vals)
                        except Exception as e:
                            message += f"Failed to create Payment Transaction: {e} "
                    else:
                        message = f"Failed to create Payment Transaction because of missed Payment Acquirer setup for" \
                                  f" {order.magento_payment_method_id.payment_method_name} Payment Method."

            if message:
                self.log_order_import_error(
                    order.magento_order_log_book_ids,
                    order.client_order_ref,
                    order.magento_instance_id,
                    order.magento_website_id,
                    message
                )
            elif order.magento_order_log_book_ids:
                order.magento_order_log_book_ids.write({'active': False})

    def cancel_order_from_magento_by_webhook(self):
        try:
            super(SaleOrder, self).action_cancel()
            self.is_canceled_in_magento = True
        except Exception as error:
            order_ref = self.magento_order_reference
            instance = self.magento_instance_id
            message = "Error to cancel the order via Magento admin: " + str(error)
            so_log_book_rec = self.env['magento.orders.log.book'].with_context(active_test=False).search([
                ('magento_instance_id', '=', instance.id),
                ('magento_order_ref', '=', order_ref)
            ])

            self.log_order_import_error(so_log_book_rec, order_ref, instance, self.magento_website_id, message)

            return False

        return True

    def cancel_order_in_magento(self):
        magento_order_id = self.magento_order_id

        if magento_order_id:
            try:
                api_url = '/V1/orders/%s/cancel' % magento_order_id
                res = req(self.magento_instance_id, api_url, 'POST')
                if res is True:
                    self.is_canceled_in_magento = True
            except Exception:
                raise UserError("Error while requesting order cancellation in Magento!")

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()

        if self.magento_instance_id:
            invoice_vals.update({'magento_instance_id': self.magento_instance_id.id})

            if self.magento_order_status == 'processing':
                invoice_vals.update({'is_in_magento': True})

            if self.magento_payment_method_id:
                invoice_vals['magento_payment_method_id'] = self.magento_payment_method_id.id

            if self.auto_workflow_process_id and self.auto_workflow_process_id.sale_journal_id:
                invoice_vals.update({'journal_id': self.auto_workflow_process_id.sale_journal_id.id})

        return invoice_vals

    def process_sales_order_creation(self, magento_instance, sales_order):
        order_ref = sales_order.get('increment_id')
        order_rec = self.search([
            ('magento_instance_id', '=', magento_instance.id),
            ('magento_order_reference', '=', order_ref)
        ])
        so_log_book_rec = self.env['magento.orders.log.book'].with_context(active_test=False).search([
            ('magento_instance_id', '=', magento_instance.id),
            ('magento_order_ref', '=', order_ref)
        ])

        # proceed order creation/update
        if not order_rec or order_rec.state in ['draft', 'sent']:
            storeview = magento_instance.magento_website_ids.store_view_ids.filtered(
                lambda x: x.magento_storeview_id == str(sales_order.get('store_id'))
            )
            if not storeview:
                message = "Magento Storeview specified in Sales Order doesn't exist in Odoo. Need to synch Instance Metadata."
                self.log_order_import_error(so_log_book_rec, order_ref, magento_instance, False, message)
                return False
            else:
                storeview = storeview[0]

            website = storeview.magento_website_id
            so_metadict = {'website': website, 'storeview': storeview}

            message = self.check_sales_order_data(magento_instance, sales_order, so_metadict)
            if message:
                self.log_order_import_error(so_log_book_rec, order_ref, magento_instance, website, message)
                return False

            order_values = self.prepare_and_generate_sales_order_values(magento_instance, sales_order, so_metadict)

            try:
                if order_rec:
                    order_rec.with_context(tracking_disable=True).write(order_values)
                else:
                    order_rec = self.with_context(tracking_disable=True).create(order_values)
            except Exception as e:
                message = f"Error while creating/updating sales order in Odoo: {str(e)}"
                self.log_order_import_error(so_log_book_rec, order_ref, magento_instance, website, message)
                return False

            message = order_rec.create_magento_sales_order_lines(magento_instance, sales_order)
            if message:
                self.log_order_import_error(so_log_book_rec, order_ref, magento_instance, website, message)
                return False

        message = order_rec.auto_workflow_process_id.auto_workflow_process([order_rec.id])
        if message:
            self.log_order_import_error(so_log_book_rec, order_ref, magento_instance, website, message)

        if so_log_book_rec:
            so_log_book_rec.write({'active': False})

        return True

    def check_sales_order_data(self, instance, sales_order, so_metadict):
        order_lines = sales_order.get('items')
        website = so_metadict['website']

        message = self.check_payment_method_and_order_flow_configurations(instance, sales_order, so_metadict)
        if message:
            return message

        message = self.check_magento_shipping_method(instance, sales_order)
        if message:
            return message

        if not website.warehouse_id:
            return f"Warehouse is not set for the {website.name} website. Please configure it first: Settings >> Magento Websites. "

        message = self.check_pricelist_and_currency_of_sales_order(sales_order, website)
        if message:
            return message

        message = self.env['res.partner'].check_customer_and_addresses_exist(instance, sales_order, so_metadict)
        if message:
            return message

        return self.check_products_exist_and_prices(instance, order_lines, website)

    def check_payment_method_and_order_flow_configurations(self, instance, sales_order, so_metadict):
        so_metadict.update({'allowed_flow': False})
        order_ref = sales_order.get('increment_id')
        amount_paid = sales_order.get('payment', {}).get('amount_paid', 0)
        order_status = sales_order.get('status')
        payment_method = sales_order.get('payment', {}).get('method')

        payment_option = instance.payment_method_ids.filtered(lambda x: x.payment_method_code == payment_method)

        if not payment_option:
            return "Payment method %s is not found in Magento Layer. Please synchronize Instance " \
                   "Metadata or unarchive it." % payment_method

        allowed_flow = self.env['magento.financial.status'].search([
            ('magento_instance_id', '=', instance.id),
            ('payment_method_id', '=', payment_option.id),
            ('financial_status', '=', order_status)
        ])

        if not allowed_flow:
            return  "- Automatic 'Order Processing Workflow' configuration not found for this order. \n -" \
                    " System tries to find a workflow based on combination of Payment Method (such as PayPal, " \
                    "P24 etc.) and Order's Financial Status(such as Pending, Processing etc.).\n " \
                    "- For current Sales Order: Payment Method is '%s' and Order's Financial Status is '%s'.\n  " \
                    "- You can configure the Automatic Order Processing Workflow under the menu Magento >> " \
                    "Configuration >> Orders Processing Gateway." % (payment_option.payment_method_name, order_status)

        if not allowed_flow.auto_workflow_id:
            return "Order %s was not proceeded due to missed Order Auto Workflow configuration for payment " \
                   " method - %s and order's financial status - %s" % (order_ref, payment_method, order_status)

        import_rule = payment_option.import_rule

        if import_rule == 'never':
            return "Orders with payment method %s have the rule never to be imported." % payment_method
        elif not amount_paid and import_rule == 'paid':
            return False, "Order '%s' hasn't been paid yet. Thus, it'll be imported after payment is done." % order_ref

        so_metadict['allowed_flow'] = allowed_flow

        return ''

    def check_magento_shipping_method(self, magento_instance, sales_order):
        order_ref = sales_order.get('increment_id')
        shipping = sales_order.get('extension_attributes', {}).get('shipping_assignments')
        shipping_method = shipping[0].get('shipping', {}).get('method') if shipping else False

        if not shipping_method:
            return f"Delivery method is not found within imported Order({order_ref}) info."

        mag_deliv_carrier = magento_instance.shipping_method_ids.filtered(lambda x: x.carrier_code == shipping_method)
        if not mag_deliv_carrier:
            return f"Order {order_ref} has failed to proceed due to shipping method - {shipping_method} wasn't found " \
                   f"within Magento Delivery Methods. Please synchronize Instance Metadata."

        odoo_delivery_carrier = mag_deliv_carrier.delivery_carrier_ids
        delivery_carrier = odoo_delivery_carrier[0] if odoo_delivery_carrier else False
        if not delivery_carrier:
            try:
                product = self.env.ref('odoo_magento2.product_product_shipping')
                self.env["delivery.carrier"].create({
                    'name': mag_deliv_carrier.carrier_label or mag_deliv_carrier.magento_carrier_title,
                    'product_id': product.id,
                    'magento_carrier': mag_deliv_carrier.id
                })
            except Exception as err:
                return f"Error while new Delivery Method creation in Odoo: {err}. Please create it manually and link " \
                       f"'Magento Delivery Carrier' field with {shipping_method} shipping method code. "

        if shipping_method == "inpostlocker_standard":
            locker_code = sales_order.get('extension_attributes', {}).get('inpost_locker_id', '')
            inpost_point_id = self.env['inpost.point'].search([('name', '=', locker_code)])

            if not inpost_point_id:
                inpost_api = self.env['delivery.carrier'].inpost_get_api_client()
                InpostPoint = self.env['inpost.point']

                try:
                    response = inpost_api.get_point(locker_code)
                except Exception as e:
                    return f"Error to get '{locker_code}' locker info from Inpost - {str(e)}."

                if response and response.get('items'):
                    InpostPoint.create(InpostPoint.convert_api_data(response['items']))
                else:
                    return f"Inpost response with locker: '{locker_code}' details doesn't contain appropriate info."

        return ''

    def check_products_exist_and_prices(self, magento_instance, order_lines, website):
        message = ""
        simple_prod_obj = self.env['magento.product.product']

        for line in order_lines:
            prod_sku = line.get('sku')
            prod_type = line.get('product_type')
            if prod_type != 'simple':
                message = "%s product type is not supported for the product with %s sku" % (prod_type, prod_sku)
                break

            # Check the ordered product exist in the magento layer or not.
            magento_product = simple_prod_obj.search([('magento_instance_id', '=', magento_instance.id),
                                                      ('magento_sku', '=', prod_sku)], limit=1)
            if not magento_product:
                message = "Product with sku '%s' doesn't exist in magento layer in Odoo" % prod_sku
                break

            # check if product prices are ok
            odoo_base_price = simple_prod_obj.get_product_price_for_website(website, magento_product.odoo_product_id)
            order_base_price = line.get('original_price')

            if odoo_base_price != order_base_price:
                message = f"Product's base prices do not match for {prod_sku}: Odoo price - {odoo_base_price} and " \
                          f"Magento price - {order_base_price}"
                break

        return message

    @staticmethod
    def check_pricelist_and_currency_of_sales_order(sales_order, website):
        if website.pricelist_id:
            order_currency = sales_order.get('order_currency_code')
            pricelist_currency = website.pricelist_id.currency_id.name

            if order_currency != pricelist_currency:
                return f"{order_currency} order currency and Odoo's Price list currency {pricelist_currency} don't match."
        else:
            return f"{website.name} website is missing Price list to be defined in Instance Configurations in Odoo."

        return ''

    def prepare_and_generate_sales_order_values(self, instance, sales_order, so_metadict):
        sale_order_obj = self.env['sale.order']
        website = so_metadict['website']
        so_increment_id = sales_order.get('increment_id', '')
        workflow_process_id = so_metadict['allowed_flow'].auto_workflow_id
        shipping = sales_order.get('extension_attributes').get('shipping_assignments')
        shipping_method = shipping[0].get('shipping').get('method')
        payment_term_id = self.env.ref("account.account_payment_term_immediate") or False

        mag_deliv_carrier = instance.shipping_method_ids.filtered(
            lambda x: x.carrier_code == shipping_method
        )
        odoo_delivery_carrier = mag_deliv_carrier.delivery_carrier_ids.filtered(
            lambda x: x.magento_carrier_code == shipping_method
        )
        payment_method = instance.payment_method_ids.filtered(
            lambda x: x.payment_method_code == sales_order.get('payment').get('method')
        )
        store_view = instance.magento_website_ids.store_view_ids.filtered(
            lambda x: x.magento_storeview_id == str(sales_order.get('store_id'))
        )
        invoice_partner_id = so_metadict['bill_addr'].id if so_metadict['bill_addr'] else False
        shipping_partner_id = so_metadict['ship_addr'].id if so_metadict['ship_addr'] else False

        order_vals = {
            'state': 'draft',
            'date_order': sales_order.get('created_at', False),
            'partner_id': so_metadict['odoo_partner'].id,
            'partner_invoice_id': invoice_partner_id,
            'partner_shipping_id': shipping_partner_id,
            'pricelist_id': website.pricelist_id.id,
            'company_id': instance.company_id.id,
            'picking_policy': workflow_process_id and workflow_process_id.picking_policy or False,
            'warehouse_id': website.warehouse_id.id
        }

        new_record = sale_order_obj.new(order_vals)
        new_record.onchange_partner_shipping_id()  # updates fiscal position
        order_vals = sale_order_obj._convert_to_write(new_record._cache)

        order_vals.update({
            'client_order_ref': so_increment_id,
            'name': "%s%s" % (store_view and store_view.sale_prefix or '', so_increment_id),
            'team_id': store_view.team_id.id if store_view and store_view.team_id else False,
            'payment_term_id': payment_term_id.id if payment_term_id else False,
            'carrier_id': odoo_delivery_carrier.id if odoo_delivery_carrier else False,
            'magento_instance_id': instance.id,
            'magento_website_id': website.id,
            'store_id': store_view.id if store_view else False,
            'payment_transaction_code': sales_order.get('payment', {}).get('last_trans_id', False),
            'auto_workflow_process_id': workflow_process_id.id,
            'order_currency_code': sales_order.get("order_currency_code"),
            'order_total_amount': sales_order.get("grand_total", 0),
            'magento_payment_method_id': payment_method.id,
            'magento_shipping_method_id': mag_deliv_carrier.id,
            'magento_order_id': sales_order.get('entity_id'),
            'magento_order_status': sales_order.get('status'),
            'magento_order_reference': so_increment_id
        })

        if shipping_method == "inpostlocker_standard":
            locker_code = sales_order.get('extension_attributes', {}).get('inpost_locker_id', '')
            inpost_point_id = self.env['inpost.point'].search([('name', '=', locker_code)])

            if inpost_point_id:
                order_vals.udpate({'inpost_locker_id': inpost_point_id.id})

        return order_vals

    def create_magento_sales_order_lines(self, instance, sales_order):
        sales_order_line = self.env['sale.order.line']

        message = sales_order_line.create_product_sales_order_line(instance, sales_order, self)
        if message:
            return message

        return sales_order_line.create_shipping_sales_order_line(sales_order, self)

    def log_order_import_error(self, log_book_rec, order_ref, instance, website, message):
        data = {
            'sale_order_id': self.id,
            'magento_website_id': website.id if website else False,
            'log_message': message,
            'active': True
        }

        if log_book_rec:
            log_book_rec.write(data)
        else:
            data.update({
                'magento_order_ref': order_ref,
                'magento_instance_id': instance.id,
            })
            log_book_rec.create(data)

    def action_view_payment_transactions(self):
        action = self.env['ir.actions.act_window']._for_xml_id('payment.action_payment_transaction')

        if len(self.transaction_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.transaction_ids.id
            action['views'] = []
        else:
            action['domain'] = [('id', 'in', self.transaction_ids.ids)]

        return action
