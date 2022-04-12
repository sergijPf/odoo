# -*- coding: utf-8 -*-

import re

from datetime import datetime
from odoo import fields, models, api
from odoo.exceptions import UserError
from ..python_library.api_request import req


class MagentoSpecialPricing(models.Model):

    _name = 'magento.special.pricing'
    _description = 'Magento special products pricing'
    _rec = 'name'

    name = fields.Char("Name", required=True)
    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance', required=True)
    applied_on = fields.Selection([
        ('3_global', 'All products'),
        ('2_product_category', 'Category'),
        ('1_product_config', 'Config.product'),
        ('0_product_simple', 'Simple product')
    ], string="Applied on", help="Price list applied on scope", required=True)
    prod_category_ids = fields.Many2many('magento.product.category', string='Magento Product Category', copy=False,
                                         domain="[('instance_id','=',magento_instance_id)]")
    config_product_ids = fields.Many2many('magento.configurable.product', string='Magento Config. Product', copy=False,
                                          domain="[('magento_instance_id','=',magento_instance_id)]")
    simple_product_ids = fields.Many2many(comodel_name='magento.product.product', relation='simple_product_special_price_rel',
                                          column1='simple_product_id', column2='special_pricing_id',
                                          string='Magento Simp Product', copy=False,
                                          domain="[('magento_instance_id','=',magento_instance_id)]")
    product_ids = fields.Many2many(comodel_name='magento.product.product', relation='product_price_rel',
                                   column1='product_id', column2='price_id', string='Magento Products',
                                   compute="_compute_products", store=True)
    min_qty = fields.Float("Min.quantity", default=1)
    is_special_price = fields.Boolean("Is special price?")
    fixed_price = fields.Float("Special Price", copy=False)
    percent_price = fields.Float("Discount,%", copy=False)
    price_type = fields.Selection([('fixed', 'Fixed'), ('discount', 'Discount')], string='Discount Type',
                                  default='discount', required=True)
    store_id = fields.Many2one('magento.storeview', string="Magento Storeview",
                               domain="[('magento_instance_id','=',magento_instance_id)]")
    website_id = fields.Many2one(related='store_id.magento_website_id', string='Magento Websites')
    customer_group_id = fields.Many2one('magento.customer.groups', string='Customer group',
                                        domain="[('magento_instance_id','=',magento_instance_id)]")
    price_from = fields.Datetime("Price valid from")
    price_to = fields.Datetime("Price valid to")
    active = fields.Boolean("Active", default=True)
    export_status = fields.Selection([
        ('not_exported', 'not Exported'),
        ('error', "Error"),
        ('exported', 'Exported')
    ], string='Export Status', help='The status of Product Advanced Pricing export to Magento ',
        default='not_exported', copy=False)

    @api.depends('applied_on', 'prod_category_ids', 'config_product_ids', 'simple_product_ids')
    def _compute_products(self):
        for rec in self:
            rec.product_ids = rec.get_related_simple_products()

    def get_related_simple_products(self):
        products = self.env['magento.product.product']
        inst_products = products.search([('magento_instance_id', '=', self.magento_instance_id.id)])

        if self.applied_on == '3_global':
            products = inst_products
        elif self.applied_on == '2_product_category':
            for categ in self.prod_category_ids:
                products += inst_products.browse([p.id for p in inst_products if categ in p.prod_category_ids])
        elif self.applied_on == '1_product_config':
            products = inst_products.filtered(lambda x: x.magento_conf_product_id in self.config_product_ids)
        else:
            products = self.simple_product_ids

        return products

    def toggle_active(self):
        for rec in self:
            if rec.export_status == 'exported':
                raise UserError("Please delete special price in Magento first (by clicking 'Delete in Magento' button)")
        return super(MagentoSpecialPricing, self).toggle_active()

    def export_adv_prices(self):
        all_records = self if self.env.context.get('single_req') else self.search([])
        all_records.active = True

        for instance in {i.magento_instance_id for i in all_records}:
            adv_prices = all_records.filtered(lambda x: x.magento_instance_id.id == instance.id)

            for rec in adv_prices:
                response = []
                data_prices, api_url = rec.prepare_data_to_export(False)

                # Magento max export of 20 at once
                count = (len(data_prices) // 20) + 1
                for c in range(count):
                    try:
                        res = req(instance, api_url, 'POST', {"prices": data_prices[c*(20):20*(c+1)]})
                        if res and type(res) is list:
                            response += res
                    except Exception as err:
                        print(err)
                        return

                if not response:
                    rec.export_status = 'exported'
                else:
                    rec.log_error(response)

        return True

    def prepare_data_to_export(self, is_deletion):
        data_prices = []
        if self.is_special_price:
            store_id = self.store_id
            store_code = store_id.magento_storeview_code if store_id else 'all'
            api_url = '/%s/V1/products/special-price%s' % (store_code, '-delete' if is_deletion else '')
            price_item = {
                "price": self.fixed_price,
                "store_id": store_id.magento_storeview_id if store_id else 0,
                "price_from": datetime.strftime(self.price_from, '%Y-%m-%d %H:%M:%S') if self.price_from else "",
                "price_to": datetime.strftime(self.price_to, '%Y-%m-%d %H:%M:%S') if self.price_to else ""
            }
        else:
            api_url = '/all/V1/products/tier-prices%s' % ('-delete' if is_deletion else '')
            price_item = {
                "price": self.fixed_price if self.price_type == "fixed" else self.percent_price,
                "price_type": self.price_type,  # fixed/discount
                "website_id": self.website_id.magento_website_id if self.website_id else 0,
                "customer_group": self.customer_group_id.group_name if self.customer_group_id else "ALL GROUPS",
                "quantity": self.min_qty if self.min_qty else 1
            }

        for prod in self.product_ids:
            price_item.update({"sku": prod.magento_sku})
            data_prices.append(price_item.copy())

        return data_prices, api_url

    def delete_in_magento(self):
        self.ensure_one()

        data_prices, api_url = self.prepare_data_to_export(True)
        response = []

        # Magento max export of 20 at once
        count = (len(data_prices) // 20) + 1
        for c in range(count):
            try:
                res = req(self.magento_instance_id, api_url, 'POST', {"prices": data_prices[c * (20):20 * (c + 1)]})
                if res and type(res) is list:
                    response += res
            except Exception as err:
                print(err)
                return

        if not response:
            self.export_status = 'not_exported'
        else:
            self.log_error(response)

    def log_error(self, response):
        self.export_status = 'error'
        for resp in response:
            message = resp.get('message')
            params = resp.get('parameters')
            for p in reversed(params):
                message = self.replace_last(message, '%', f"'{p}' ")

            print(message)

    def replace_last(self, message, old_txt, new_txt):
        head, _sep, tail = message.rpartition(old_txt)
        return head + new_txt + tail

    def view_simple_products(self):
        if self.product_ids:
            return {
                'name': 'Simple Products',
                'type': 'ir.actions.act_window',
                'res_model': 'magento.product.product',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'domain': [('magento_instance_id', '=', self.magento_instance_id.id),
                           ('id', 'in', self.product_ids.mapped('id'))],
            }
