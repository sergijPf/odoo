# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from odoo.exceptions import UserError
from datetime import datetime

class ProductPublicCategoryUpdate(models.TransientModel):
    _name = "product.public.category.update"

    category_id = fields.Many2one('product.public.category', string="Assigned Product Category")

    def update_product_public_category(self):
        active_product_ids = self._context.get("active_ids", [])
        update_products = self.env["product.product"].browse(active_product_ids)
        magento_product_obj = self.env["magento.product.product"]
        magento_conf_product_obj = self.env['magento.configurable.product']

        if not self.category_id.is_magento_config:
            raise UserError("The selected Product Public Category has to have 'Magento Config.Product' field checked")
        for product in update_products:
            domain = [('magento_sku', '=', product.default_code)]
            product.config_product_id = self.category_id.id
            # check if is in Magento Layer
            magento_simp_prod = magento_product_obj.search(domain)
            if magento_simp_prod:
                # check if config.product exists
                dmn = [('odoo_prod_category', '=', self.category_id.id)]
                for prod in magento_simp_prod:
                    dmn.append(('magento_instance_id', '=', prod.magento_instance_id.id))
                    conf_prod = magento_conf_product_obj.search(dmn)
                    if not conf_prod:
                        conf_prod = magento_conf_product_obj.create({
                            'magento_instance_id': prod.magento_instance_id.id,
                            'odoo_prod_category': self.category_id.id,
                            'magento_sku': self.category_id.name,
                            'magento_product_name': self.category_id.name
                        })
                    prod.magento_conf_product = conf_prod.id

        return {
            'effect': {
                'fadeout': 'slow',
                'message': "Product Public Category was successfully updated!",
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }
