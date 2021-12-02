# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
# from datetime import datetime

class MagentoProductCategoryUpdate(models.TransientModel):
    _name = "magento.product.category.update"
    _description = "Update Product Category in Magento Layer"

    magento_instance_id = fields.Many2one('magento.instance', 'Magento Instance', help="This field relocates magento instance")
    product_categ = fields.Many2many('magento.product.category', string="Product Categories",
                                     domain="[('instance_id','=',magento_instance_id)]")

    def update_products_category_for_magento(self):
        active_product_ids = self._context.get("active_ids", [])
        products_to_update = self.env['magento.configurable.product'].browse(active_product_ids)
        if products_to_update:
            update_data = {
                'category_ids': [(6, 0, [c.id for c in self.product_categ])],
                # 'update_date': datetime.now()
                'force_update': True
            }
            products_to_update.write(update_data)
