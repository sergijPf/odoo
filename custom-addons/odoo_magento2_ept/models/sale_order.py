# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields and methods for create/ update sale order
"""
from odoo import models, fields, api
from odoo.exceptions import UserError
from .api_request import req

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
    magento_carrier_name = fields.Char(compute="_carrier_name", string="Magento Carrier Name")
    magento_order_log_book_ids = fields.One2many('magento.orders.log.book', 'sale_order_id', "Log Error Messages")
    auto_workflow_process_id = fields.Many2one("sale.workflow.process.ept", string="Workflow Process", copy=False)
    moves_count = fields.Integer(compute="_compute_stock_move", string="Stock Move", store=False,
                                 help="Stock Move Count for Orders without Picking.")
    is_canceled_in_magento = fields.Boolean(string="Canceled in Magento", default=False,
                                            help="Checked, if order was canceled in Magento")

    _sql_constraints = [('_magento_sale_order_unique_constraint',
                         'unique(magento_order_id,magento_instance_id,magento_order_reference)',
                         "Magento order must be unique")]

    def _compute_stock_move(self):
        """
        Find all stock moves associated with the order.
        """
        self.moves_count = self.env["stock.move"].search_count([("picking_id", "=", False),
                                                                ("sale_line_id", "in", self.order_line.ids)])

    @api.onchange('partner_shipping_id', 'partner_id')
    def onchange_partner_shipping_id(self):
        """
        Inherited method for setting fiscal position by warehouse.
        """
        res = super(SaleOrder, self).onchange_partner_shipping_id()
        fiscal_position = self.get_fiscal_position_by_warehouse()
        self.fiscal_position_id = fiscal_position
        return res

    @api.onchange('warehouse_id')
    def onchange_warehouse_id(self):
        """
        This method for sets fiscal position, when warehouse is changed.
        """
        fiscal_position = self.get_fiscal_position_by_warehouse()
        self.fiscal_position_id = fiscal_position

    def create_sales_order_vals(self, vals):
        """
        Pass Dictionary
        vals = {'company_id':company_id,'partner_id':partner_id,
        'partner_invoice_id':partner_invoice_id,
        'partner_shipping_id':partner_shipping_id,'warehouse_id':warehouse_id,
        'company_id':company_id,
        'picking_policy':picking_policy,'date_order':date_order,'pricelist_id':pricelist_id,
        'payment_term_id':payment_term_id,'fiscal_position_id':fiscal_position_id,
        'invoice_policy':invoice_policy,'team_id':team_id,'client_order_ref':client_order_ref,
        'carrier_id':carrier_id,'invoice_shipping_on_delivery':invoice_shipping_on_delivery}
        required data in vals :- partner_id,partner_invoice_id,partner_shipping_id,company_id,warehouse_id,
        picking_policy,date_order
        """
        sale_order = self.env['sale.order']
        order_vals = {
            'company_id': vals.get('company_id', False),
            'partner_id': vals.get('partner_id', False),
            'partner_invoice_id': vals.get('partner_invoice_id', False),
            'partner_shipping_id': vals.get('partner_shipping_id', False),
            'warehouse_id': vals.get('warehouse_id', False),
        }

        new_record = sale_order.new(order_vals)
        # Return Pricelist- Payment terms- Invoice address- Delivery address
        new_record.onchange_partner_id()
        order_vals = sale_order._convert_to_write({name: new_record[name] for name in new_record._cache})

        # Return Fiscal Position
        order_vals.update({'partner_shipping_id': vals.get('partner_shipping_id', False)})
        new_record = sale_order.new(order_vals)
        new_record.onchange_partner_shipping_id()
        order_vals = sale_order._convert_to_write({name: new_record[name] for name in new_record._cache})

        fpos = order_vals.get('fiscal_position_id') or vals.get('fiscal_position_id', False)
        order_vals.update({
            'company_id': vals.get('company_id', False),
            'picking_policy': vals.get('picking_policy'),
            'partner_invoice_id': vals.get('partner_invoice_id', False),
            'partner_id': vals.get('partner_id', False),
            'partner_shipping_id': vals.get('partner_shipping_id', False),
            'date_order': vals.get('date_order', False),
            'state': 'draft',
            'pricelist_id': vals.get('pricelist_id', False),
            'fiscal_position_id': fpos,
            'payment_term_id': vals.get('payment_term_id', False),
            'team_id': vals.get('team_id', False),
            'client_order_ref': vals.get('client_order_ref', ''),
            'carrier_id': vals.get('carrier_id', False)
        })
        return order_vals

    def get_fiscal_position_by_warehouse(self):
        """
        This method will give fiscal position from warehouse.
        """
        fiscal_position = self.fiscal_position_id
        warehouse = self.warehouse_id

        # if warehouse and self.partner_id:
        if warehouse and self.partner_id and self.partner_id.allow_search_fiscal_based_on_origin_warehouse:
            origin_country_id = warehouse.partner_id and warehouse.partner_id.country_id and \
                                warehouse.partner_id.country_id.id or False
            origin_country_id = origin_country_id or (warehouse.company_id.partner_id.country_id
                                                      and warehouse.company_id.partner_id.country_id.id or False)
            fiscal_position = self.env['account.fiscal.position'].with_context({
                'origin_country_ept': origin_country_id}).with_company(
                    warehouse.company_id.id).get_fiscal_position(self.partner_id.id, self.partner_shipping_id.id)

        return fiscal_position

    def action_view_stock_move_ept(self):
        """
        List all stock moves which is associated with the Order.
        """
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

    def validate_sales_order(self):
        """
        This function validate sales order and write date_order same as previous date because Odoo changes date_order
        to current date in action confirm process.
        Added invalidate_cache line to resolve the issue of PO line description while product route has dropship and
        multi languages active in Odoo.
        """
        self.ensure_one()
        date_order = self.date_order
        self.env['product.product'].invalidate_cache(fnames=['display_name'])
        self.action_confirm()
        self.write({'date_order': date_order})
        return True

    def process_orders_and_invoices(self):
        """
        This method will confirm sale orders, create and paid related invoices.
        """
        for order in self:
            work_flow_process_record = order.auto_workflow_process_id

            if order.invoice_status and order.invoice_status == 'invoiced':
                continue
            if work_flow_process_record.validate_order:
                order.validate_sales_order()

            order_lines = order.mapped('order_line').filtered(lambda l: l.product_id.invoice_policy == 'order')
            if not order_lines.filtered(lambda l: l.product_id.type == 'product') and len(order.order_line) != len(
                    order_lines.filtered(lambda l: l.product_id.type in ['service','consu'])):
                continue

            order.validate_invoice(work_flow_process_record)
        return True

    def validate_invoice(self, work_flow_process_record):
        """
        This method will create invoices, validate it and register payment it, according to the configuration in
        workflow sets in quotation
        :param work_flow_process_record:
        :return: It will return boolean.
        """
        self.ensure_one()
        if work_flow_process_record.create_invoice:
            invoices = self._create_invoices()
            # validate invoices
            for invoice in invoices:
                invoice.action_post()

        return True

    def cancel_order_from_magento_by_webhook(self):
        """
        This method will be called while sale order cancellation from Magento
        """
        try:
            super(SaleOrder, self).action_cancel()
            self.is_canceled_in_magento = True
        except Exception as error:
            order_ref = self.magento_order_reference
            instance = self.magento_instance_id
            log_errors = self.env['magento.orders.log.book'].search([
                ('magento_instance_id', '=', instance.id),
                ('magento_order_ref', '=', order_ref)
            ])
            message = "Error to cancel the order via Magento admin: " +  str(error)
            self.log_order_import_error(log_errors, order_ref, instance, self.magento_website_id, message)
            return False

        return True

    def cancel_order_in_magento(self):
        """
        This method use for cancel order in magento.
        """
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
        """
        This method is used for set necessary value(is_exported_to_magento, magento_instance_id)
         to the invoice.
        :return:
        """
        invoice_vals = super(SaleOrder, self)._prepare_invoice()

        if self.auto_workflow_process_id:
            invoice_vals.update({'journal_id': self.auto_workflow_process_id.sale_journal_id.id})

        if self.magento_payment_method_id:
            invoice_vals['magento_payment_method_id'] = self.magento_payment_method_id.id
        if self.magento_instance_id:
            invoice_vals.update({
                'magento_instance_id': self.magento_instance_id.id,
                'is_exported_to_magento': False
            })
        return invoice_vals

    def process_sale_order_workflow_based_on_status(self):
        """
        Call sale order workflow based on magento order status
        """
        message = self.auto_workflow_process_id.auto_workflow_process(self.auto_workflow_process_id.id, [self.id])
        return message if message else ''

    @staticmethod
    def check_discount_has_tax_included_and_percent(sales_order):
        """
        Check order tax applied is including/ excluding and tax percent
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

        message = magento_order.process_sale_order_workflow_based_on_status()
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
                        'name': magento_carrier.carrier_label or magento_carrier.magento_carrier_title,
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

        order_values.update({
            'magento_instance_id': magento_instance.id,
            'magento_website_id': website.id,
            'store_id': store_view.id if store_view else False,
            'auto_workflow_process_id': workflow_process_id.id,
            'magento_payment_method_id': payment_option.id,
            'magento_shipping_method_id': shipping_carrier.id,
            'is_exported_to_magento_shipment_status': False,
            'magento_order_id': sales_order.get('entity_id'),
            'magento_order_reference': sales_order.get('increment_id')
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
        workflow_config = self.env['magento.financial.status'].search(
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
