# -*- coding: utf-8 -*-

import secrets
import string

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import ustr
from ..python_library.api_request import req

ACTION_ACT_WINDOW = 'ir.actions.act_window'
MAGENTO_STOREVIEW = 'magento.storeview'
MAGENTO_INSTANCE = 'magento.instance'
MAGENTO_WEBSITE = 'magento.website'
IR_CRON = 'ir.cron'


class MagentoInstance(models.Model):
    _name = MAGENTO_INSTANCE
    _description = 'Magento Instance'

    name = fields.Char("Instance Name", required=True)
    magento_url = fields.Char(string='Magento URLs', required=False, help="URL of Magento")
    location_ids = fields.Many2many('stock.location', string="Locations", required=True,
                                    help='Locations used to compute the stock quantities. If Location is not '
                                         'selected then it is taken from Website')
    magento_website_ids = fields.One2many(MAGENTO_WEBSITE, 'magento_instance_id', string='Website', readonly=True,
                                          help="Magento Websites")
    lang_id = fields.Many2one('res.lang', string='Default Language',
                              help="If a default language is selected, the records will be imported in the translation "
                                   "of this language.\n Note that a similar configuration exists for each storeview.")
    catalog_price_scope = fields.Selection([
        ('global', 'Global'),
        ('website', 'Website')
    ], string="Catalog Price Scopes", help="Scope of Price in Magento", default='website')
    access_token = fields.Char(string="Magento Access Token")
    odoo_token = fields.Char(string="Odoo Auto-generated Token", help="Token to be used while Sale Orders import")
    company_id = fields.Many2one('res.company', string='Magento Company')
    invoice_done_notify_customer = fields.Boolean(string="Invoices Done Notify customer", default=False,
                                                  help="Send email while export invoice")
    auto_export_product_stock = fields.Boolean(string='Auto Export Product Stock?')
    auto_export_product_prices = fields.Boolean(string='Auto Export Product Prices?')
    auto_export_invoice = fields.Boolean(string='Auto Export Invoice?')
    auto_export_shipment_order_status = fields.Boolean(string='Auto Export Shipment Information?')
    payment_method_ids = fields.One2many("magento.payment.method", "magento_instance_id", "Payment Methods in Magento")
    shipping_method_ids = fields.One2many("magento.delivery.carrier", "magento_instance_id",
                                          string="Shipping Methods in Magento")
    magento_verify_ssl = fields.Boolean(string="Verify SSL", default=False,
                                        help="Check this if your Magento site is using SSL certificate")
    active = fields.Boolean(string="Status", default=True)
    cron_count = fields.Integer("Scheduler Count", compute="_compute_get_scheduler_list")
    color = fields.Integer('Color')
    config_product_ids = fields.One2many('magento.configurable.product', 'magento_instance_id')
    simple_product_ids = fields.One2many('magento.product.product', 'magento_instance_id')
    sale_order_ids = fields.One2many('sale.order', 'magento_instance_id')
    sale_order_error_ids = fields.One2many('magento.orders.log.book', 'magento_instance_id')
    invoice_ids = fields.One2many('account.move', 'magento_instance_id')
    shipment_ids = fields.One2many('stock.picking', 'magento_instance_id')
    disabled_config_prods_count = fields.Integer(compute="_compute_products_count")
    update_config_prods_count = fields.Integer(compute="_compute_products_count")
    disabled_simple_prods_count = fields.Integer(compute="_compute_products_count")
    update_simple_prods_count = fields.Integer(compute="_compute_products_count")
    active_special_prices_count = fields.Integer(compute="_compute_active_special_prices_count")
    pending_sale_orders_count = fields.Integer(compute="_compute_pending_sale_info")
    pending_invoices_count = fields.Integer(compute="_compute_pending_sale_info")
    invoices_pending_payment_count = fields.Integer(compute="_compute_pending_sale_info")
    pending_shipments_count = fields.Integer(compute="_compute_pending_sale_info")
    sale_orders_with_errors_count = fields.Integer(compute="_compute_sale_orders_invoices_and_shipments_with_errors_count")
    invoices_with_errors_count = fields.Integer(compute="_compute_sale_orders_invoices_and_shipments_with_errors_count")
    shipments_with_errors_count = fields.Integer(compute="_compute_sale_orders_invoices_and_shipments_with_errors_count")
    image_resolution = fields.Selection([
        ('image_1920', '1920px'),
        ('image_1024', '1024px'),
        ('image_512', '512px'),
        ('image_256', '256px'),
        ('image_128', '128px')
    ], string="Image Resolution", default='image_1024')

    def _compute_products_count(self):
        for rec in self:
            rec.disabled_config_prods_count = len(rec.config_product_ids.filtered(
                lambda x: not x.is_enabled and x.magento_status != 'no_need'))
            rec.disabled_simple_prods_count = len(rec.simple_product_ids.filtered(lambda x: not x.is_enabled))
            rec.update_config_prods_count = len(rec.config_product_ids.filtered(
                lambda x: x.magento_product_id and  x.magento_status != 'in_magento'
            ))
            rec.update_simple_prods_count = len(rec.simple_product_ids.filtered(
                lambda x: x.magento_product_id and x.magento_status != 'in_magento'
            ))

    def _compute_active_special_prices_count(self):
        spec_prices_obj = self.env['magento.special.pricing']
        for rec in self:
            rec.active_special_prices_count = len(spec_prices_obj.search([
                ('export_status', '=', 'exported'),
                ('magento_instance_id', '=', rec.id)
            ]))

    def _compute_sale_orders_invoices_and_shipments_with_errors_count(self):
        for rec in self:
            rec.sale_orders_with_errors_count = len(rec.sale_order_error_ids)
            rec.invoices_with_errors_count = len(rec.invoice_ids.magento_invoice_log_book_ids)
            rec.shipments_with_errors_count = len(rec.shipment_ids.magento_shipment_log_book_ids)

    def _compute_pending_sale_info(self):
        for rec in self:
            rec.pending_sale_orders_count = len(rec.sale_order_ids.filtered(lambda x: x.invoice_status != 'invoiced'))
            rec.pending_invoices_count = len(rec.invoice_ids.filtered(lambda x: x.state == 'draft'))
            rec.invoices_pending_payment_count = len(rec.invoice_ids.filtered(lambda x: x.payment_state != 'paid'))
            rec.pending_shipments_count = len(rec.shipment_ids.filtered(lambda x: x.state not in ['done', 'cancel']))

    def _compute_get_scheduler_list(self):
        seller_cron = self.env[IR_CRON].search([('magento_instance_id', '=', self.id)])
        for record in self:
            record.cron_count = len(seller_cron.ids)

    @api.model
    def _scheduler_update_product_stock_qty(self, args=None):
        args = {} if args is None else args
        magento_instance_id = args.get('magento_instance_id')

        if magento_instance_id:
            instance = self.browse(magento_instance_id)
            self.env['magento.product.product'].export_products_stock_to_magento(instance)

    @api.model
    def _scheduler_update_product_prices(self, args=None):
        args = {} if args is None else args
        magento_instance_id = args.get('magento_instance_id')

        if magento_instance_id:
            instance = self.browse(magento_instance_id)
            self.env['magento.product.product'].export_product_prices_to_magento(instance)

    @api.model
    def _scheduler_update_order_status(self, args=None):
        args = {} if args is None else args
        magento_instance_id = args.get('magento_instance_id')

        if magento_instance_id:
            instance = self.env[MAGENTO_INSTANCE].browse(magento_instance_id)
            self.env['stock.picking'].export_shipments_to_magento(instance, True)

    @api.model
    def _scheduler_export_invoice(self, args=None):
        args = {} if args is None else args
        magento_instance_id = args.get('magento_instance_id')

        if magento_instance_id:
            instance = self.env[MAGENTO_INSTANCE].browse(magento_instance_id)
            self.env['account.move'].export_invoices_to_magento(instance, True)

    @staticmethod
    def _append_rest_suffix_to_url(location_url):
        if location_url:
            location_url = location_url.strip().rstrip('/')
            location_vals = location_url.split('/')
            if location_vals[-1] != 'rest':
                location_url = location_url + '/rest'

        return location_url

    def write(self, vals):
        if 'magento_url' in vals:
            vals['magento_url'] = vals['magento_url'].rstrip('/')

        return super(MagentoInstance, self).write(vals)

    def action_generate_token(self):
        alphabet = string.ascii_letters + string.digits

        while True:
            token = ''.join(secrets.choice(alphabet) for i in range(30))
            if (any(c.islower() for c in token) and any(c.isupper() for c in token)
                    and sum(c.isdigit() for c in token) >= 3):
                break

        self.odoo_token = token

    def list_of_delivery_method(self):
        tree_view = self.env.ref('odoo_magento2.magento_delivery_carrier_tree_view').id

        return {
            'name': 'Magento Carriers Views',
            'type': ACTION_ACT_WINDOW,
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'magento.delivery.carrier',
            'views': [(tree_view, 'tree')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [("magento_instance_id", "=", self.id)]
        }

    def list_of_instance_cron(self):
        instance_cron = self.env[IR_CRON].search([('magento_instance_id', '=', self.id)])

        return {
            'domain': "[('id', 'in', " + str(instance_cron.ids) + " )]",
            'name': 'Cron Scheduler',
            'view_mode': 'tree,form',
            'res_model': IR_CRON,
            'type': ACTION_ACT_WINDOW,
        }

    def cron_configuration_action(self):
        action = self.env.ref('odoo_magento2.action_magento_wizard_cron_configuration').read()[0]
        action['context'] = {
            'magento_instance_id': self.id
        }

        return action

    def magento_test_connection(self):
        self.ensure_one()
        try:
            api_url = "/V1/store/websites"
            website_response = req(self, api_url, method='GET')
        except Exception as error:
            raise UserError(_("Connection Test Failed! Here is what we got instead:\n \n%s") % ustr(error))

        if website_response:
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': "Connection Test Succeeded! Everything seems properly set up!",
                    'img_url': '/web/static/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }

    def synchronize_metadata(self):
        self.make_currencies_active()
        self.sync_price_scope()
        self.sync_website()
        self.sync_storeview()
        self.sync_customer_groups()
        self.payment_method_ids.import_payment_methods(self)
        self.shipping_method_ids.import_delivery_methods(self)

        return {
            'effect': {
                'fadeout': 'slow',
                'message': "Data synchronized Successfully! Everything seems to be ok!",
                'img_url': '/web/static/img/smile.svg',
                'type': 'rainbow_man',
            }
        }

    def make_currencies_active(self):
        try:
            url = '/V1/directory/currency'
            magento_currency = req(self, url)
        except Exception as e:
            raise UserError(e)

        for active_currency in magento_currency.get('exchange_rates', []):
            domain = [('name', '=', active_currency.get('currency_to'))]
            currency_id = self.env['res.currency'].with_context(active_test=False).search(domain, limit=1)

            if not currency_id.active:
                currency_id.write({'active': True})

    def sync_price_scope(self):
        api_url = "/V1/products/attributes/price"
        try:
            attributes_price = req(self, api_url, method='GET')
        except Exception as error:
            raise UserError(error)

        self.catalog_price_scope = attributes_price.get('scope')

    def sync_website(self):
        try:
            website_response = req(self, "/V1/store/websites", method='GET')
        except Exception as error:
            raise UserError(error)

        for data in website_response:
            website_id = str(data.get('id'))
            if website_id and website_id != "0":
                if website_id not in self.magento_website_ids.mapped("magento_website_id"):
                    self.magento_website_ids.create({
                        'name': data.get('name'),
                        'magento_website_id': website_id,
                        'magento_instance_id': self.id
                    })

    def sync_storeview(self):
        storeview_obj = self.env[MAGENTO_STOREVIEW]
        try:
            storeview_configs = req(self, "/V1/store/storeConfigs", method='GET')
            stores = req(self, "/V1/store/storeViews", method='GET')
        except Exception as err:
            raise UserError(err)

        for store_data in storeview_configs:
            magento_storeview_id = str(store_data.get('id'))
            if magento_storeview_id != "0":
                website = self.magento_website_ids.filtered(
                    lambda x: x.magento_website_id == str(store_data.get('website_id')))
                storeview = website.store_view_ids.filtered(lambda x: x.magento_storeview_id == magento_storeview_id)

                self.update_currency_for_website(store_data, website)

                if not storeview:
                    name, language = self.get_store_view_language_and_name(stores, magento_storeview_id, store_data)
                    storeview_obj.create({
                        'name': name,
                        'magento_website_id': website.id,
                        'magento_storeview_id': magento_storeview_id,
                        'magento_instance_id': self.id,
                        'lang_id': language.id if language else False,
                        'magento_storeview_code': store_data.get('code')
                    })
                else:
                    storeview.write({
                        'magento_storeview_code': store_data.get('code')
                    })

    def update_currency_for_website(self, storeview_data, website):
        currency_id = self.env['res.currency'].with_context(active_test=False).search([
            ('name', '=', storeview_data.get('default_display_currency_code'))], limit=1)

        if currency_id and not currency_id.active:
            currency_id.write({'active': True})
        elif not currency_id:
            currency_id = self.env.user.currency_id

        website.write({
            'magento_base_currency': currency_id
        })

    def get_store_view_language_and_name(self, stores, magento_storeview_id, storeview_data):
        name = ''
        res_lang_obj = self.env['res.lang']
        lang = storeview_data.get('locale')

        for store in stores:
            if str(store.get('id')) == magento_storeview_id:
                name = store.get('name')
                break

        language = res_lang_obj.with_context(active_test=False).search([('code', '=', lang)])
        if language and not language.active:
            language.write({'active': True})

        return name, language

    def sync_customer_groups(self):
        api_url = "/V1/customerGroups/search?searchCriteria[pageSize]=200&searchCriteria[currentPage]=1"
        try:
            magento_customer_groups = req(self, api_url, method='GET')
        except Exception as error:
            raise UserError(error)

        if magento_customer_groups.get('items'):
            customer_group_obj = self.env['magento.customer.groups']
            domain = [(), ('magento_instance_id', '=', self.id)]

            for mag_group in magento_customer_groups['items']:
                domain[0] = ('group_id', '=', str(mag_group.get('id')))
                odoo_cust_group = customer_group_obj.search(domain)

                if odoo_cust_group:
                    if odoo_cust_group.group_name != mag_group.get('code'):
                        odoo_cust_group.group_name = mag_group.get('code')
                else:
                    customer_group_obj.create({
                        'group_id': str(mag_group.get('id')),
                        'group_name': mag_group.get('code'),
                        'magento_instance_id': self.id
                    })

    def open_all_websites(self):
        form_view_id = self.env.ref('odoo_magento2.view_magento_website_form').id
        tree_view = self.env.ref('odoo_magento2.view_magento_website_tree').id

        return {
            'name': 'Magento Website',
            'type': ACTION_ACT_WINDOW,
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': MAGENTO_WEBSITE,
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', self.magento_website_ids.ids)]
        }

    def product_categories_action(self):
        action = self.env.ref('odoo_magento2.action_wizard_magento_product_category_configuration').read()[0]
        action['context'] = {'magento_instance_id': self.id}

        return action

    def get_all_conf_products(self):
        return self._get_configurable_products(self.config_product_ids)

    def get_disabled_conf_products(self):
        disabled_conf_prods = self.config_product_ids.filtered(lambda x: not x.is_enabled and x.magento_status != 'no_need')
        return self._get_configurable_products(disabled_conf_prods)

    def get_conf_products_to_be_updated(self):
        to_be_updated_prods = self.config_product_ids.filtered(
            lambda x:x.magento_product_id and  x.magento_status != 'in_magento'
        )
        return self._get_configurable_products(to_be_updated_prods)

    def _get_configurable_products(self, product_ids):
        form_view_id = self.env.ref('odoo_magento2.view_magento_configurable_product_form').id
        tree_view = self.env.ref('odoo_magento2.view_magento_configurable_product_tree').id

        return {
            'name': 'Configurable Products',
            'type': ACTION_ACT_WINDOW,
            'view_mode': 'tree, form',
            'res_model': 'magento.configurable.product',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', product_ids.ids)]
        }

    def get_all_simple_products(self):
        return self._get_simple_products(self.simple_product_ids)

    def get_disabled_simple_products(self):
        disabled_prods = self.simple_product_ids.filtered(lambda x: not x.is_enabled)
        return self._get_simple_products(disabled_prods)

    def get_simple_products_to_be_updated(self):
        to_be_updated_prods = self.simple_product_ids.filtered(
            lambda x: x.magento_product_id and x.magento_status != 'in_magento'
        )
        return self._get_simple_products(to_be_updated_prods)

    def _get_simple_products(self, product_ids):
        form_view_id = self.env.ref('odoo_magento2.view_magento_product_form').id
        tree_view = self.env.ref('odoo_magento2.view_magento_product_tree').id

        return {
            'name': 'Simple Products',
            'type': ACTION_ACT_WINDOW,
            'view_mode': 'tree, form',
            'res_model': 'magento.product.product',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', product_ids.ids)]
        }

    def get_special_prices_for_simple_products(self):
        form_view_id = self.env.ref('odoo_magento2.view_magento_special_pricing_form').id
        tree_view = self.env.ref('odoo_magento2.view_magento_special_pricing_tree').id

        return {
            'name': 'Advance Prices applied to products',
            'type': ACTION_ACT_WINDOW,
            'view_mode': 'tree, form',
            'res_model': 'magento.special.pricing',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('magento_instance_id', '=', self.id)]
        }

    def get_all_sale_orders(self):
        return self._get_magento_sale_orders(self.sale_order_ids)

    def get_pending_sale_orders(self):
        orders = self.sale_order_ids.filtered(lambda x: x.invoice_status != 'invoiced')
        return self._get_magento_sale_orders(orders)

    def _get_magento_sale_orders(self, order_ids):
        form_view_id = self.env.ref('odoo_magento2.magento_view_order_form').id
        tree_view = self.env.ref('odoo_magento2.magento_sale_order_tree_view').id

        return {
            'name': 'Magento Sale Orders',
            'type': ACTION_ACT_WINDOW,
            'view_mode': 'tree, form',
            'res_model': 'sale.order',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', order_ids.ids)]
        }

    def get_sale_order_with_errors(self):
        form_view_id = self.env.ref('odoo_magento2.view_magento_imported_orders_log_book_form').id
        tree_view = self.env.ref('odoo_magento2.view_magento_imported_orders_log_book_tree').id

        return {
            'name': 'Imported Sale Orders with Errors ',
            'type': ACTION_ACT_WINDOW,
            'view_mode': 'tree, form',
            'res_model': 'magento.orders.log.book',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('magento_instance_id', '=', self.id)]
        }

    def get_all_invoices(self):
        return self._get_magento_invoices(self.invoice_ids)

    def get_pending_invoices(self):
        return self._get_magento_invoices(self.invoice_ids.filtered(lambda x: x.state == 'draft'))

    def get_invoices_with_pending_payments(self):
        pending_payment_invoices = self.invoice_ids.filtered(lambda x: x.payment_state != 'paid')
        return self._get_magento_invoices(pending_payment_invoices)

    def _get_magento_invoices(self, invoice_ids):
        form_view_id = self.env.ref('odoo_magento2.inherited_account_invoice_form_view').id
        tree_view = self.env.ref('odoo_magento2.magento_invoice_tree_view').id

        return {
            'name': 'Magento Invoices',
            'type': ACTION_ACT_WINDOW,
            'view_mode': 'tree, form',
            'res_model': 'account.move',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', invoice_ids.ids)]
        }

    def get_invoices_with_errors(self):
        form_view_id = self.env.ref('odoo_magento2.view_magento_invoice_errors_log_book_form').id
        tree_view = self.env.ref('odoo_magento2.view_magento_invoices_error_log_book_tree').id

        return {
            'name': 'Invoice export Errors',
            'type': ACTION_ACT_WINDOW,
            'view_mode': 'tree, form',
            'res_model': 'magento.invoices.log.book',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', self.invoice_ids.magento_invoice_log_book_ids.ids)]
        }

    def get_magento_pending_shipments(self):
        shipment_ids = self.shipment_ids.filtered(lambda x: x.state not in ['done', 'cancel'])
        return self._get_magento_shipments(shipment_ids)

    def get_all_magento_shipments(self):
        return self._get_magento_shipments(self.shipment_ids)

    def _get_magento_shipments(self, shipment_ids):
        form_view_id = self.env.ref('odoo_magento2.magento_view_stock_picking_form').id
        tree_view = self.env.ref('odoo_magento2.magento_view_stock_picking_tree').id

        return {
            'name': 'Magento Shipments Info',
            'type': ACTION_ACT_WINDOW,
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', shipment_ids.ids)]
        }

    def get_shipments_with_errors(self):
        form_view_id = self.env.ref('odoo_magento2.view_magento_shipment_errors_log_book_form').id
        tree_view = self.env.ref('odoo_magento2.view_magento_shipment_errors_log_book_tree').id

        return {
            'name': 'Invoice export Errors',
            'type': ACTION_ACT_WINDOW,
            'view_mode': 'tree, form',
            'res_model': 'magento.shipments.log.book',
            'views': [(tree_view, 'tree'), (form_view_id, 'form')],
            'view_id': tree_view,
            'target': 'current',
            'domain': [('id', 'in', self.shipment_ids.magento_shipment_log_book_ids.ids)]
        }
