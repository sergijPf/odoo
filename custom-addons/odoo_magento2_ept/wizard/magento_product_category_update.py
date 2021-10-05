# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from datetime import datetime

class ProductCategoryUpdate(models.TransientModel):
    _name = "product.category.update"

    product_categ = fields.Many2one('product.category', string="Product Category")

    def update_products_category_for_magento(self):
        active_product_ids = self._context.get("active_ids", [])
        update_products = self.env["magento.product.product"].browse(active_product_ids)
        for product in update_products:
            conf_prod = self.get_or_create_configurable_product(product)
            product.magento_conf_product = conf_prod.id
            product.update_date = datetime.now()

    def get_or_create_configurable_product(self, product):
        configurable_product_object = self.env['magento.configurable.product']
        domain = [('magento_instance_id', '=', int(product.magento_instance_id)),
                  ('magento_sku', '=', self.product_categ.magento_sku or self.product_categ.name)]
        configurable_product = configurable_product_object.search(domain)
        if not configurable_product:
            values = {
                'magento_instance_id': product.magento_instance_id.id,
                'odoo_prod_category': self.product_categ.id,
                'magento_sku': self.product_categ.magento_sku or self.product_categ.name,
                'magento_product_name': self.product_categ.name
            }
            configurable_product = configurable_product_object.create(values)
        return configurable_product
