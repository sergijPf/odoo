# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from datetime import datetime

class ProductCategoryLinks(models.TransientModel):
    _name = "product.category.links"

    # magento_product = fields.Many2many('magento.product.product', "Magento Product")
    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance',
                                          help="This field relocates magento instance")
    category_links = fields.Many2many('magento.product.category', string="Magento Product Category Links",
                                      domain="[('instance_id','=',magento_instance_id)]")

    def update_product_category_links(self):
        active_product_ids = self._context.get("active_ids", [])
        update_products = self.env["magento.product.product"].browse(active_product_ids)
        for product in update_products:
            product.category_ids = [(6, 0, [cat.id for cat in self.category_links if product.magento_instance_id == self.magento_instance_id])]
            product.update_date = datetime.now()

