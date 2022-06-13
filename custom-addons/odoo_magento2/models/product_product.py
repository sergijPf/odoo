# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.exceptions import UserError

MAGENTO_PRODUCT = 'magento.product.product'


class ProductProduct(models.Model):
    _inherit = 'product.product'

    magento_product_count = fields.Integer(string='# Product Counts', compute='_compute_magento_product_count')
    magento_product_ids = fields.One2many(MAGENTO_PRODUCT, 'odoo_product_id', string='Magento Products')

    def _compute_magento_product_count(self):
        magento_product_obj = self.env[MAGENTO_PRODUCT]
        for product in self:
            magento_products = magento_product_obj.search([('odoo_product_id', '=', product.id)])
            product.magento_product_count = len(magento_products) if magento_products else 0

    def write(self, vals):
        res = super(ProductProduct, self).write(vals)

        if self.magento_product_ids and ('product_variant_image_ids' in vals or 'name' in vals or 'image_1920' in vals
                                         or 'product_template_attribute_value_ids' in vals or 'weight' in vals):
            self.magento_product_ids.force_update = True

        return res

    def unlink(self):
        rejected_variants = []

        for prod in self:
            if prod.magento_product_ids:
                rejected_variants.append({c.magento_instance_id.name: c.magento_sku for c in prod.magento_product_ids})

        if rejected_variants:
            raise UserError("It's not allowed to delete these product(s) as they were already added to Magento Layer "
                            "as Simple Product(s): %s\n" % (str(rejected_variants)))

        return super(ProductProduct, self).unlink()
