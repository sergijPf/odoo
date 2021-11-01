# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

class ConfigProductAttributesUpdate(models.TransientModel):
    _name = "config.product.attributes.update"

    config_prod_attr = fields.Many2many('config.product.attribute', string="Config.Product Attributes Update")

    def update_product_attributes(self):
        active_product_ids = self._context.get("active_ids", [])
        products_to_update = self.env['product.public.category'].browse(active_product_ids).filtered(lambda x: x.is_magento_config)
        update_data = {
            'attribute_ids': [(6, 0, [c.id for c in self.config_prod_attr])]
        }
        products_to_update.write(update_data)
