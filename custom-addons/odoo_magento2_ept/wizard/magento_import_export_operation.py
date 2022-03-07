# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes product import export process.
"""

import re
from datetime import datetime
from odoo.exceptions import UserError
from odoo import fields, models, _

MAGENTO_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
IR_ACTION_ACT_WINDOW = 'ir.actions.act_window'
IR_MODEL_DATA = 'ir.model.data'
VIEW_MODE = 'tree,form'
MAGENTO_PRODUCT_PRODUCT = 'magento.product.product'


class MagentoImportExport(models.TransientModel):
    """
    Describes Magento Process for import/ export operations
    """
    _name = 'magento.import.export'
    _description = 'Magento Import Export'

    magento_instance_ids = fields.Many2many('magento.instance', string="Magento Instances")
    magento_website_id = fields.Many2one('magento.website', string="Magento Website")
    operations = fields.Selection([
        ('export_shipment_information', 'Export Shipment Information'),
        ('export_invoice_information', 'Export Invoice Information'),
        ('export_product_prices', 'Export Product Prices'),
        ('export_product_stock', 'Export Product Stock')
    ], string='Import/ Export Operations', help='Import/ Export Operations')
    start_date = fields.Datetime(string="From Date")
    end_date = fields.Datetime("To Date")

    def execute(self):
        """
        Execute different Magento operations based on selected operation,
        """
        magento_instance = self.env['magento.instance']
        account_move = self.env['account.move']
        picking = self.env['stock.picking']
        magento_product_obj = self.env[MAGENTO_PRODUCT_PRODUCT]
        message = ''

        if self.magento_instance_ids:
            instances = self.magento_instance_ids
        else:
            instances = magento_instance.search([])

        if self.operations == 'export_shipment_information':
            picking.export_shipments_to_magento(instances)
        elif self.operations == 'export_invoice_information':
            account_move.export_invoices_to_magento(instances)
        elif self.operations == 'export_product_prices':
            if not magento_product_obj.export_product_prices(instances):
                return {
                    'name': 'Product Prices Export Logs',
                    'view_mode': 'tree,form',
                    'res_model': 'magento.prices.log.book',
                    'type': 'ir.actions.act_window'
                }
        elif self.operations == 'export_product_stock':
            if not self.export_product_stock_operation(instances, magento_product_obj):
                return {
                    'name': 'Product Stock Export Logs',
                    'view_mode': 'tree,form',
                    'res_model': 'magento.stock.log.book',
                    'type': 'ir.actions.act_window'
                }

        title = [vals for key, vals in self._fields['operations'].selection if key == self.operations]

        return {
            'effect': {
                'fadeout': 'slow',
                'message': " {} Process Completed Successfully! {}".format(title[0], message),
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }

    def export_product_stock_operation(self, instances, magento_product_obj):
        """
        Export product stock from Odoo to Magento
        :param instances: Magento Instances
        :return:
        """
        res = True
        for instance in instances:
            if not magento_product_obj.export_products_stock_to_magento(instance):
                res = False
            instance.last_update_stock_time = datetime.now()

        return res

    def prepare_product_for_export_to_magento(self):
        """
        This method is used to export products in Magento layer as per selection.
        If "direct" is selected, then it will direct export product into Magento layer.
        """
        active_product_ids = self._context.get("active_ids", [])
        selection = self.env["product.template"].browse(active_product_ids)
        failed_products = selection.filtered(lambda product: product.type != "product" or not product.is_magento_config)

        if failed_products:
            raise UserError(_("It seems like selected product(s) are not Storable or don't have"
                            " proper Magento Config.Product setup: %s" % str([p.name for p in failed_products])))

        self.add_products_to_magento_layer(selection)

        return {
            'effect': {
                'fadeout': 'slow',
                'message': " 'Export to Magento Layer' process completed successfully! {}".format(""),
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }

    def add_products_to_magento_layer(self, odoo_products):
        """
        Add product and product categories to Magento Layer in Odoo
        :param odoo_products: Odoo product objects
        :return:
        """
        magento_product_obj = self.env[MAGENTO_PRODUCT_PRODUCT]
        ptae_obj = self.env['product.template.attribute.exclusion']
        magento_sku_missing = []
        product_dict = {}


        for instance in self.magento_instance_ids:
            product_dict.update({'instance_id': instance.id})
            for odoo_prod in odoo_products:
                product_dict.update({'odoo_product_id': odoo_prod})
                self.create_or_update_configurable_product_in_magento_layer(product_dict)
                magento_sku_missing = self.create_or_update_magento_product_variant(
                    product_dict, magento_sku_missing, magento_product_obj, ptae_obj
                )
        if magento_sku_missing:
            raise UserError(_('Missing Internal References For %s', str(magento_sku_missing)))

        return True

    def create_or_update_magento_product_variant(self, product_dict, magento_sku_missing, magento_product_obj, ptae_obj):
        product_templ = product_dict.get('odoo_product_id')
        excl_combinations = []
        excl_ptav = ptae_obj.search([('product_tmpl_id', '=', product_templ.id)])

        [[excl_combinations.append(
            (str(a.product_template_attribute_value_id.id), str(v.id))
        ) for v in a.value_ids] for a in excl_ptav]

        for product in product_templ.product_variant_ids:
            skip = False
            for combination in excl_combinations:
                if combination[0] in product.combination_indices and combination[1] in product.combination_indices:
                    skip = True
                    break
            if skip:
                continue

            magento_prod_sku = product.default_code
            if not magento_prod_sku:
                magento_sku_missing.append(product.name)
            else:
                product_dict.update({"prod_variant": product})
                domain = [('magento_instance_id', '=', product_dict.get('instance_id')),
                          ('magento_sku', '=', magento_prod_sku)]
                simple_prod = magento_product_obj.with_context(active_test=False).search(domain)
                if not simple_prod:
                    prod_vals = {
                        'magento_instance_id': product_dict['instance_id'],
                        'odoo_product_id': product.id,
                        'magento_sku': product.default_code,
                        'magento_conf_product_id': product_dict['conf_product_id'].id
                    }
                    magento_product_obj.create(prod_vals)

                elif not simple_prod.active:
                    simple_prod.write({'active': True})

        return magento_sku_missing

    def create_or_update_configurable_product_in_magento_layer(self, product_dict):
        conf_product_obj = self.env['magento.configurable.product']
        product = product_dict.get('odoo_product_id')
        domain = [('magento_instance_id', '=', product_dict.get('instance_id')),
                  ('odoo_prod_template_id', '=', product.id)]
        conf_product = conf_product_obj.with_context(active_test=False).search(domain)
        if not conf_product:
            values = {
                'magento_instance_id': product_dict.get('instance_id'),
                'odoo_prod_template_id': product.id,
                'magento_sku': product.with_context(lang='en_US').name.replace(' - ','_').replace('-','_').
                    replace('%','').replace('#','').replace('/','').replace('  ',' ').replace(' ','_')
            }
            conf_product = conf_product_obj.create(values)
        else:
            if not conf_product.active:
                conf_product.write({
                    # 'magento_sku': product.product_tmpl_id.with_context(lang='en_US').name.replace(' ','_').
                    #     replace('%','').replace('#','').replace('/',''), # to remove later
                    'active': True
                })
            conf_product.force_update = True
            # conf_product.simple_product_ids.write({'active': False})
        product_dict.update({"conf_product_id": conf_product})

    def prepare_customers_for_export_to_magento(self):
        active_ids = self._context.get("active_ids", [])
        selection = self.env["res.partner"].browse(active_ids)
        filt_customers = selection.filtered(lambda c: c.customer_rank == 1 and c.type == 'contact')

        if not filt_customers:
            raise UserError(_("It seems selected partners are not Customers or have different Address type than 'contact'"))

        failed_to_add = self.add_customers_to_magento_layer(filt_customers)

        if failed_to_add:
            raise UserError(_("Following Contacts missed or have incorrect email addresses and "
                              "were not added to magento layer: %s") % str(failed_to_add))
        else:
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': " 'Export in Magento Layer' Process Completed Successfully! {}".format(""),
                    'img_url': '/web/static/src/img/smile.svg',
                    'type': 'rainbow_man',
                }
            }

    def add_customers_to_magento_layer(self, odoo_customers):
        failed_to_add = []

        for instance in self.magento_instance_ids:
            website = self.magento_website_id
            if website.magento_instance_id.id != instance.id:
                continue
            for customer in odoo_customers:
                if not self.check_email(customer.email):
                    failed_to_add.append(customer.name)
                    continue
                elif not customer.magento_res_partner_ids or \
                        instance not in customer.magento_res_partner_ids.mapped('magento_instance_id'):
                    magento_customer = self.create_magento_customer_in_layer(customer, instance, website)
                else:
                    magento_customer = customer.magento_res_partner_ids.filtered(
                        lambda i: i.magento_instance_id.id == instance.id)

                # proceed with child partners, (contact - create new, invoice/delivery - create and link address),
                # valid only for one iteration (doesn't use hierarchy)
                for child in customer.child_ids:
                    if child.type == 'invoice':
                        self.create_and_link_customer_address(child, magento_customer, 'invoice')
                    elif child.type == 'delivery':
                        self.create_and_link_customer_address(child, magento_customer, 'delivery')

        return failed_to_add

    def create_magento_customer_in_layer(self, customer, instance, website):
        magento_partner_obj = self.env['magento.res.partner']
        res =  magento_partner_obj.create({
            'partner_id': customer.id,
            'magento_instance_id': instance.id,
            'magento_website_id': website.id,
            'status': 'to_export'
        })

        if res:
            customer.is_magento_customer = True
        return res

    def create_and_link_customer_address(self, odoo_partner, magento_customer, type):
        customer_address_obj = self.env['magento.customer.addresses']
        if odoo_partner.id in magento_customer.customer_address_ids.mapped('odoo_partner_id').ids:
            return

        if type == 'invoice':
            _type = 'billing'
        elif type == 'delivery':
            _type = 'shipping'
        else:
            return

        # create address in magento layer
        address_id = customer_address_obj.create({
            'address_type': _type,
            'customer_id': magento_customer.id,
            'odoo_partner_id': odoo_partner.id
        })

        magento_customer.write({
            'customer_address_ids': [(4, address_id.id)]
        })

    @staticmethod
    def check_email(email):
        regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        if email and (re.fullmatch(regex, email)):
            return True
        return False
