# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
# from odoo.exceptions import UserError
# from datetime import datetime

class ProductPublicCategoryUpdate(models.TransientModel):
    _name = "product.public.category.update"

    category_id = fields.Many2one('product.public.category', string="Assigned Product Category",
                                  domain="[('is_magento_config','=',True)]")

    def update_product_public_category(self):
        active_product_ids = self._context.get("active_ids", [])
        update_products = self.env["product.product"].browse(active_product_ids)
        magento_product_obj = self.env["magento.product.product"]
        magento_conf_product_obj = self.env['magento.configurable.product']

        # if not self.category_id.is_magento_config:
        #     raise UserError("The selected Product Public Category has to have 'Magento Config.Product' field checked")
        for product in update_products:
            product.config_product_id = self.category_id.id
            # check if is in Magento Layer
            domain = [('magento_sku', '=', product.default_code)]
            magento_simp_prod = magento_product_obj.with_context(active_test=False).search(domain)

            # check if config.product exists, create if not
            for prod in magento_simp_prod:
                dmn = [('magento_instance_id', '=', prod.magento_instance_id.id),
                       ('odoo_prod_category', '=', self.category_id.id)]
                conf_prod = magento_conf_product_obj.with_context(active_test=False).search(dmn)
                if not conf_prod:
                    conf_prod = magento_conf_product_obj.create({
                        'magento_instance_id': prod.magento_instance_id.id,
                        'odoo_prod_category': self.category_id.id,
                        'magento_sku': self.category_id.with_context(lang='en_US').name.replace(' ','_').
                            replace('%','').replace('#','').replace('/','')
                        # 'magento_product_name': self.category_id.name
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
