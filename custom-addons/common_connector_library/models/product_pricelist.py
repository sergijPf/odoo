# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from odoo import models
from odoo.exceptions import UserError
# from datetime import datetime


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    # def get_product_price_ept(self, product, partner=False):
    #     """
    #     Gives price of a product from pricelist(self).
    #     :param product: product id
    #     :param partner: partner id or False
    #     :return: price
    #     Migration done by twinkalc August 2020
    #     """
    #     price = self.get_product_price(product, 1.0, partner=partner, uom_id=product.uom_id.id)
    #     return price

    # def set_product_price_ept(self, product_id, price, min_qty=1):
    #     """
    #     Creates or updates price for product in Pricelist.
    #     :param product_id: Id of product.
    #     :param price: Price
    #     :param min_qty: qty
    #     :return: product_pricelist_item
    #     Migration done by twinkalc August 2020
    #     """
    #     product_pricelist_item_obj = self.env['product.pricelist.item']
    #     domain = [('pricelist_id', '=', self.id), ('product_id', '=', product_id), ('min_quantity', '=', min_qty)]
    #
    #     product_pricelist_item = product_pricelist_item_obj.search(domain)
    #
    #     if product_pricelist_item:
    #         product_pricelist_item.write({'fixed_price': price})
    #     else:
    #         vals = {
    #             'pricelist_id': self.id,
    #             'applied_on': '0_product_variant',
    #             'product_id': product_id,
    #             'min_quantity': min_qty,
    #             'fixed_price': price,
    #         }
    #         new_record = product_pricelist_item_obj.new(vals)
    #         new_record.item_()
    #         new_vals = product_pricelist_item_obj._convert_to_write(
    #             {name: new_record[name] for name in new_record._cache})
    #         product_pricelist_item = product_pricelist_item_obj.create(new_vals)
    #     return product_pricelist_item

    # applied_on = fields.Selection([
    #     ('3_global', 'All Products'),
    #     ('2_product_category', 'Product Category'),
    #     ('1_product', 'Product'),
    #     ('0_product_variant', 'Product Variant')], "Apply On",
    #     default='3_global', required=True,
    #     help='Pricelist Item applicable on selected option')

class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    # def write(self, vals):
    #     res = super(ProductPricelistItem, self).write(vals)
    #
    #     magento_instances = self.env['magento.instance'].search([])
    #     for rec in self:
    #         for instance in magento_instances:
    #             is_in_instance = False
    #             if instance.catalog_price_scope == 'global':
    #                 if instance.pricelist_id == rec.pricelist_id.id:
    #                     is_in_instance = True
    #             elif instance.catalog_price_scope == 'website':
    #                 for website in instance.magento_website_ids:
    #                     if rec.pricelist_id.id in [pl.id for pl in website.pricelist_ids]:
    #                         is_in_instance = True
    #
    #             if is_in_instance:
    #                 magento_products = self.env['magento.product.product'].search([])
    #                 magento_products.search([("magento_instance_id", "=", instance.id)]).write({
    #                     "force_update": True
    #                 })
    #
    #     return res