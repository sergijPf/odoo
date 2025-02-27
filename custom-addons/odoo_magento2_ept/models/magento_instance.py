# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods for Magento Instance
"""
from datetime import datetime

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
    """
    Describes methods for Magento Instance
    """
    _name = MAGENTO_INSTANCE
    _description = 'Magento Instance'

    @api.model
    def _default_order_status(self):
        """
        Get default status for importing magento order
        :return:
        """
        order_status = self.env.ref('odoo_magento2_ept.processing')
        return [(6, 0, [order_status.id])] if order_status else False

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
    magento_stock_field = fields.Selection([
        ('free_qty', 'On Hand Quantity'),
        ('virtual_available', 'Forcast Quantity')
    ], string="Magento Stock Type", default='free_qty', help="Magento Stock Type")
    catalog_price_scope = fields.Selection([
        ('global', 'Global'),
        ('website', 'Website')
    ], string="Catalog Price Scopes", help="Scope of Price in Magento", default='website')
    pricelist_id = fields.Many2one('product.pricelist', "Pricelist", help="Product Price is set in selected Pricelist")
    access_token = fields.Char(string="Magento Access Token", help="Magento Access Token")
    last_update_stock_time = fields.Datetime(string="Last Update Product Stock Time", help="Last Update Stock Time")
    company_id = fields.Many2one('res.company', string='Magento Company', help="Magento Company")
    invoice_done_notify_customer = fields.Boolean(string="Invoices Done Notify customer", default=False,
                                                  help="while export invoice send email")
    auto_export_product_stock = fields.Boolean(string='Auto Export Product Stock?')
    auto_export_invoice = fields.Boolean(string='Auto Export Invoice?')
    auto_export_shipment_order_status = fields.Boolean(string='Auto Export Shipment Information?')
    payment_method_ids = fields.One2many("magento.payment.method", "magento_instance_id", "Payment Methods in Magento")
    shipping_method_ids = fields.One2many("magento.delivery.carrier", "magento_instance_id",
                                          "Shipping Methods in Magento")
    import_magento_order_status_ids = fields.Many2many(
        'import.magento.order.status', 'magento_instance_order_status_rel', 'magento_instance_id', 'order_status_id',
        string="Import Order Status", default=_default_order_status,
        help="Select order status in which you want to import the orders from Magento to Odoo.")
    magento_verify_ssl = fields.Boolean(string="Verify SSL", default=False,
                                        help="Check this if your Magento site is using SSL certificate")
    active = fields.Boolean(string="Status", default=True)
    color = fields.Integer(string='Color Index')
    cron_count = fields.Integer("Scheduler Count", compute="_compute_get_scheduler_list",
                                help="This Field relocates Scheduler Count.")

    def _compute_get_scheduler_list(self):
        seller_cron = self.env[IR_CRON].search([('magento_instance_id', '=', self.id)])
        for record in self:
            record.cron_count = len(seller_cron.ids)

    @api.model
    def _scheduler_update_product_stock_qty(self, args=None):
        """
        This method is used to export product stock quantity to Magento via cron job
        :param args: arguments to export product stock quantity.
        :return:
        """
        if args is None:
            args = {}
        magento_product_product = self.env['magento.product.product']
        magento_instance = self.env[MAGENTO_INSTANCE]
        magento_instance_id = args.get('magento_instance_id')
        if magento_instance_id:
            instance = magento_instance.browse(magento_instance_id)
            magento_product_product.export_products_stock_to_magento(instance)
            instance.last_update_stock_time = datetime.now()

    @api.model
    def _scheduler_update_order_status(self, args=None):
        """
        This method is used to export shipment to Magento via cron job
        :param args: arguments to export invoice
        :return:
        """
        if args is None:
            args = {}
        stock_picking = self.env['stock.picking']
        magento_instance = self.env[MAGENTO_INSTANCE]
        magento_instance_id = args.get('magento_instance_id')
        if magento_instance_id:
            instance = magento_instance.browse(magento_instance_id)
            stock_picking.export_shipments_to_magento(instance)

    @api.model
    def _scheduler_export_invoice(self, args=None):
        """
        This method is used to export invoices to Magento via cron job
        :param args: arguments to export invoice
        :return:
        """
        if args is None:
            args = {}
        account_move = self.env['account.move']
        magento_instance = self.env[MAGENTO_INSTANCE]
        magento_instance_id = args.get('magento_instance_id')
        if magento_instance_id:
            instance = magento_instance.browse(magento_instance_id)
            account_move.export_invoices_to_magento(instance)

    @staticmethod
    def _check_location_url(location_url):
        """
        Set Magento rest API URL
        :param location_url: Magento URL
        :return:
        """
        if location_url:
            location_url = location_url.strip()
            location_url = location_url.rstrip('/')
            location_vals = location_url.split('/')
            if location_vals[-1] != 'rest':
                location_url = location_url + '/rest'
        return location_url

    def write(self, vals):
        """
        Remove '/' from the magento URL if exist
        :param vals:
        :return:
        """
        if 'magento_url' in vals:
            vals['magento_url'] = vals['magento_url'].rstrip('/')
        return super(MagentoInstance, self).write(vals)

    def list_of_delivery_method(self):
        """
        This method is for list all delivery method
        :return:
        """
        tree_view = self.env.ref('odoo_magento2_ept.magento_delivery_carrier_tree_view').id

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
        """
        Opens view for cron scheduler of instance
        :return:
        """
        instance_cron = self.env[IR_CRON].search([('magento_instance_id', '=', self.id)])
        return {
            'domain': "[('id', 'in', " + str(instance_cron.ids) + " )]",
            'name': 'Cron Scheduler',
            'view_mode': 'tree,form',
            'res_model': IR_CRON,
            'type': ACTION_ACT_WINDOW,
        }

    def cron_configuration_action(self):
        """
        Return action for cron configuration
        :return:
        """
        action = self.env.ref('odoo_magento2_ept.action_magento_wizard_cron_configuration_ept').read()[0]
        context = {
            'magento_instance_id': self.id
        }
        action['context'] = context

        return action

    def magento_test_connection(self):
        """
        This method check connection in magento.
        """
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
                    'img_url': '/web/static/src/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }

    def synchronize_metadata(self):
        """
        Sync all the websites, store view , Payment methods and delivery methods
        """
        self.make_currencies_active()
        self.sync_price_scope()
        self.sync_website()
        self.sync_storeview()
        self.sync_customer_groups()
        self.payment_method_ids.import_payment_method()
        self.shipping_method_ids.import_delivery_method()
        self.env['magento.financial.status'].create_financial_status(self, 'not_paid')

    def make_currencies_active(self):
        """
        This method is used to import all currency as pricelist
        :return:
        """
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
        """
        get price attribute scope and set it in the current instance.
        :return:
        """
        api_url = "/V1/products/attributes/price"
        try:
            attributes_price = req(self, api_url, method='GET')
        except Exception as error:
            raise UserError(error)

        self.catalog_price_scope = attributes_price.get('scope')

    def sync_website(self):
        """
        Sync all the websites from magento
        """
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
        """
        This method used for import all storeviews from magento.
        """
        storeview_obj = self.env[MAGENTO_STOREVIEW]
        try:
            storeview_configs = req(self, "/V1/store/storeConfigs", method='GET')
            stores = req(self, "/V1/store/storeViews", method='GET')
        except Exception as err:
            raise UserError(err)

        for storeview_data in storeview_configs:
            magento_storeview_id = str(storeview_data.get('id'))
            if magento_storeview_id != "0":
                website = self.magento_website_ids.filtered(
                    lambda x: x.magento_website_id == str(storeview_data.get('website_id')))
                storeview = website.store_view_ids.filtered(
                    lambda x: x.magento_storeview_id == magento_storeview_id)

                self.update_currency_for_website(storeview_data, website)

                if not storeview:
                    name, language = self.get_store_view_language_and_name(stores, magento_storeview_id, storeview_data)
                    storeview_obj.create({
                        'name': name,
                        'magento_website_id': website.id,
                        'magento_storeview_id': magento_storeview_id,
                        'magento_instance_id': self.id,
                        'lang_id': language.id if language else False,
                        'magento_storeview_code': storeview_data.get('code')
                    })
                else:
                    storeview.write({
                        'magento_storeview_code': storeview_data.get('code')
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
        """
        Get Store view language and name.
        :param stores: Magento stores received from API
        :param magento_storeview_id: Magento store view id
        :param storeview_data: data received from Magento
        :return: name and res language object
        """
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
        """
        This method used for smart button for view all website.
        return : Action.
        """
        form_view_id = self.env.ref('odoo_magento2_ept.view_magento_website_form').id
        tree_view = self.env.ref('odoo_magento2_ept.view_magento_website_tree').id
        action = {
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
        return action

    def product_categories_action(self):
        """
        Return action for product categories configuration
        :return:
        """
        action = self.env.ref('odoo_magento2_ept.action_wizard_magento_product_category_configuration').read()[0]
        context = {
            'magento_instance_id': self.id
        }
        action['context'] = context
        return action
