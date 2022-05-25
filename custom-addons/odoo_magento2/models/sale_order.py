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
    payment_transaction_id = fields.Char(string="Payment Transact. ID", help="Magento Payment System Transaction ID")
    order_currency_code = fields.Char(string="Order Currency")
    order_total_amount = fields.Float(string="Order Amount")
    magento_carrier_name = fields.Char(compute="_compute_magento_carrier_name", string="Magento Carrier Name")
    magento_order_log_book_ids = fields.One2many('magento.orders.log.book', 'sale_order_id', "Log Error Messages")
    auto_workflow_process_id = fields.Many2one("sale.workflow.process", string="Workflow Process", copy=False)
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
            work_flow_process_rec = order.auto_workflow_process_id

            if order.invoice_status == 'invoiced':
                continue

            if work_flow_process_rec.validate_order:
                date_order = order.date_order
                order.action_confirm()
                order.write({'date_order': date_order})

            if work_flow_process_rec.create_invoice:
                if order.invoice_ids:
                    invoices = order.invoice_ids
                else:
                    invoices = self._create_invoices()
                # confirm invoices
                # for invoice in invoices:
                #     invoice.action_post()

            if work_flow_process_rec.register_payment:
                if not order.transaction_ids:
                    currency = self.env['res.currency'].search([('name', '=', order.order_currency_code)])
                    vals = {
                        'acquirer_id': order.magento_payment_method_id.payment_method_line_id.payment_acquirer_id.id,
                        'reference': order.name,
                        'state': 'done',
                        'acquirer_reference': order.payment_transaction_id,
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
                        print(e)

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
        magento_order = self.search([
            ('magento_instance_id', '=', magento_instance.id),
            ('magento_order_reference', '=', order_ref)
        ])
        so_log_book_rec = self.env['magento.orders.log.book'].with_context(active_test=False).search([
            ('magento_instance_id', '=', magento_instance.id),
            ('magento_order_ref', '=', order_ref)
        ])
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

        auto_workflow, odoo_partner, message = self.check_sales_order_data(magento_instance, sales_order, website)
        if message:
            self.log_order_import_error(so_log_book_rec, order_ref, magento_instance, website, message)
            return False

        order_values = self.prepare_and_generate_sales_order_values(
            magento_instance, website, sales_order, odoo_partner, auto_workflow
        )

        # proceed order creation/update
        if not magento_order or magento_order.state in ['draft', 'sent']:
            try:
                if magento_order:
                    magento_order.with_context(tracking_disable=True).write(order_values)
                else:
                    magento_order = self.with_context(tracking_disable=True).create(order_values)
            except Exception as e:
                message = "Error while creating/updating sales order in Magento: " + str(e)
                self.log_order_import_error(so_log_book_rec, order_ref, magento_instance, website, message)
                return False

            message = magento_order.create_magento_sales_order_lines(magento_instance, sales_order, magento_order)
            if message:
                self.log_order_import_error(so_log_book_rec, order_ref, magento_instance, website, message)
                return False

        auto_workflow = magento_order.auto_workflow_process_id
        if auto_workflow:
            auto_workflow.auto_workflow_process([magento_order.id])

        if so_log_book_rec:
            so_log_book_rec.write({'active': False})

        return True

    def check_sales_order_data(self, instance, sales_order, website):
        order_lines = sales_order.get('items')
        payment_method = sales_order.get('payment', {}).get('method')
        odoo_partner = False

        allowed_flow, message = self.check_payment_method_and_order_flow_configurations(
            instance, sales_order, payment_method
        )
        if message:
            return allowed_flow, odoo_partner, message

        message = self.check_magento_shipping_method(instance, sales_order)
        if message:
            return allowed_flow, odoo_partner, message

        if not website.warehouse_id:
            return allowed_flow, odoo_partner, ("Warehouse is not set for the %s website.\n Please configure it first: "
                        "Settings >> Magento Websites. ") % website.name

        message = self.check_pricelist_and_currency_of_sales_order(sales_order, website)
        if message:
            return allowed_flow, odoo_partner, message

        odoo_partner, magento_partner, message = self.env['res.partner'].check_customer_and_addresses_exist(
            instance, sales_order, website
        )
        if message:
            return allowed_flow, odoo_partner, message

        message = self.check_products_exist_and_prices(instance, order_lines, website)

        return allowed_flow, odoo_partner, message

    def check_payment_method_and_order_flow_configurations(self, instance, sales_order, payment_method):
        order_ref = sales_order.get('increment_id')
        amount_paid = sales_order.get('payment', {}).get('amount_paid', 0)
        order_status = sales_order.get('status')
        payment_option = instance.payment_method_ids.filtered(lambda x: x.payment_method_code == payment_method)

        if not payment_option:
            return False, "Payment method %s is not found in Magento Layer. Please synchronize Instance " \
                          "Metadata" % payment_method

        allowed_flow = self.env['magento.financial.status'].search([
            ('magento_instance_id', '=', instance.id),
            ('payment_method_id', '=', payment_option.id),
            ('financial_status', '=', order_status)
        ])

        if not allowed_flow:
            return  False, "- Automatic 'Order Processing Workflow' configuration not found for this order. \n -" \
                           " System tries to find the workflow based on combination of Payment Method (such as PayPal, " \
                           "P24 etc.) and Order's Financial Status(such as Pending, Processing Orders etc.).\n " \
                           "- For current Sales Order: Payment Method is '%s' and Order's Financial Status is '%s'.\n  " \
                           "- You can configure the Automatic Order Processing Workflow under the menu Magento >> " \
                           "Configuration >> Orders Processing Gateway." % (payment_option.payment_method_name,
                                                                            order_status)

        if not allowed_flow.auto_workflow_id:
            return False, "Order %s was not proceeded due to missed Order Auto Workflow configuration for payment " \
                          " method - %s and order's financial status - %s" % (order_ref, payment_method, order_status)

        import_rule = payment_option.import_rule

        if import_rule == 'never':
            return False, "Orders with payment method %s have the rule never to be imported." % payment_method
        elif not amount_paid and import_rule == 'paid':
            return False, "Order '%s' hasn't been paid yet. Thus, it'll be imported after payment is done." % order_ref

        return allowed_flow, ''

    def check_magento_shipping_method(self, magento_instance, sales_order):
        order_ref = sales_order.get('increment_id')
        shipping = sales_order.get('extension_attributes').get('shipping_assignments')
        shipping_method = shipping[0].get('shipping').get('method') or False

        if not shipping_method:
            return "Delivery method is not found in Order - %s." % order_ref

        mag_deliv_carrier = magento_instance.shipping_method_ids.filtered(lambda x: x.carrier_code == shipping_method)
        if not mag_deliv_carrier:
            return "Order %s has failed to proceed due to shipping method - %s wasn't found within Magento " \
                   "Delivery Methods. Please synchronize Instance Metadata." % (order_ref, shipping_method)

        odoo_delivery_carrier = mag_deliv_carrier.delivery_carrier_ids
        delivery_carrier = odoo_delivery_carrier[0] if odoo_delivery_carrier else False
        if not delivery_carrier:
            try:
                product = self.env.ref('odoo_magento2.product_product_shipping')
                self.env["delivery.carrier"].create({
                    'name': mag_deliv_carrier.magento_carrier or mag_deliv_carrier.magento_carrier_title,
                    'product_id': product.id,
                    'magento_carrier': mag_deliv_carrier.id
                })
            except Exception as err:
                return "Error while new Delivery Method creation in Odoo: %s. Please create it manually and link " \
                       "'Magento Delivery Carrier' field with %s shipping method code. " % (str(err), shipping_method)

        return ''

    def check_products_exist_and_prices(self, magento_instance, order_lines, website):
        message = ""

        for order_item in order_lines:
            prod_sku = order_item.get('sku')
            prod_type = order_item.get('product_type')
            if prod_type != 'simple':
                message = "%s product type is not supported for the product with %s sku" % (prod_type, prod_sku)
                break

            # Check the ordered product exist in the magento layer or not.
            magento_product = self.env['magento.product.product'].search([
                ('magento_instance_id', '=', magento_instance.id), ('magento_sku', '=', prod_sku)
            ], limit=1)
            if not magento_product:
                message = "Product with sku '%s' doesn't exist in magento layer in Odoo" % prod_sku
                break

            # check if product prices are ok
            odoo_product = magento_product.odoo_product_id
            odoo_base_price = self.env['magento.product.product'].get_product_price_for_website(website, odoo_product)
            order_base_price = order_item.get('original_price')

            if odoo_base_price != order_base_price:
                message = "Product's base prices do not match: Odoo price - %s and " \
                          "Magento price - %s" % (odoo_base_price, order_base_price)
                break

        return message

    def check_pricelist_and_currency_of_sales_order(self, sales_order, website):
        if website.pricelist_id:
            order_currency = sales_order.get('order_currency_code')
            pricelist_currency = website.pricelist_id.currency_id.name

            if order_currency != pricelist_currency:
                return "Order currency - %s and Price list currency in Odoo %s do not match." % (order_currency,
                                                                                                 pricelist_currency)
        else:
            return "%s website is missing Price list to be defined in Instance Configurations in Odoo" % (website.name)

        return ''

    def prepare_and_generate_sales_order_values(self, instance, website, sales_order, odoo_partner, auto_workflow):
        so_increment_id = sales_order.get('increment_id', '')
        workflow_process_id = auto_workflow.auto_workflow_id
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
        invoice_partner = odoo_partner.magento_res_partner_ids.filtered(
            lambda x: x.magento_instance_id == instance).customer_address_ids.filtered(
            lambda y: y.magento_customer_address_id == str(sales_order.get("billing_address").get("entity_id"))
        ).odoo_partner_id
        shipping_partner = odoo_partner.magento_res_partner_ids.filtered(
            lambda x: x.magento_instance_id == instance).customer_address_ids.filtered(
            lambda y: y.magento_customer_address_id == str(shipping[0].get('shipping').get('address').get("entity_id"))
        ).odoo_partner_id

        order_vals = {
            'client_order_ref': so_increment_id,
            'state': 'draft',
            'date_order': sales_order.get('created_at', False),
            'partner_id': odoo_partner.id,
            'partner_invoice_id': invoice_partner.id,
            'partner_shipping_id': shipping_partner.id,
            'pricelist_id': website.pricelist_id.id,
            'company_id': instance.company_id.id,
            'picking_policy': workflow_process_id and workflow_process_id.picking_policy or False,
            'warehouse_id': website.warehouse_id.id
        }

        sale_order = self.env['sale.order']
        new_record = sale_order.new(order_vals)
        new_record.onchange_partner_id()
        new_record.onchange_partner_shipping_id()  # updates fiscal position
        order_vals = sale_order._convert_to_write(new_record._cache)

        order_vals.update({
            'name': "%s%s" % (store_view and store_view.sale_prefix or '', so_increment_id),
            'magento_instance_id': instance.id,
            'magento_website_id': website.id,
            'store_id': store_view.id if store_view else False,
            'team_id': store_view.team_id.id if store_view and store_view.team_id else False,
            'carrier_id': odoo_delivery_carrier.id if odoo_delivery_carrier else False,
            'payment_term_id': payment_term_id.id if payment_term_id else False,
            'payment_transaction_id': sales_order.get('payment', {}).get('last_trans_id', False),
            'auto_workflow_process_id': workflow_process_id.id,
            'order_currency_code': sales_order.get("order_currency_code"),
            'order_total_amount': sales_order.get("grand_total", 0),
            'magento_payment_method_id': payment_method.id,
            'magento_shipping_method_id': mag_deliv_carrier.id,
            'magento_order_id': sales_order.get('entity_id'),
            'magento_order_status': sales_order.get('status'),
            'magento_order_reference': so_increment_id
        })

        return order_vals

    def create_magento_sales_order_lines(self, instance, sales_order, magento_order):
        sales_order_line = self.env['sale.order.line']

        message = sales_order_line.create_product_sales_order_line(instance, sales_order, magento_order)
        if message:
            return message

        return sales_order_line.create_shipping_sales_order_line(sales_order, magento_order)

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
