# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, _

class ProductCategoryUpdate(models.TransientModel):
    _name = "product.category.update"

    product_categ = fields.Many2one('product.category', string="Product Category")

    def update_products_category_for_magento(self):
        active_product_ids = self._context.get("active_ids", [])
        update_products = self.env["magento.product.product"].browse(active_product_ids)
        for prod in update_products:
            prod.prod_categ_name = self.product_categ.magento_name or self.product_categ.magento_sku
            prod.magento_prod_categ = self.product_categ

