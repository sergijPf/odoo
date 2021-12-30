# -*- coding: utf-8 -*-

from odoo import fields, models

class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    is_ignored_in_magento = fields.Boolean(string="Ignore for Magento", default=False,
                                              help="The attribute will be ignored while Product's Export to Magento")

    def write(self, vals):
        res = super(ProductAttribute, self).write(vals)

        # check if attribute already assigned to any of magento products
        if 'is_ignored_in_magento' in vals:
            attr_id = self.id
            magento_products = self.env['magento.product.product'].search([])
            magento_products.filtered(lambda x: attr_id in x.attribute_value_ids.product_attribute_value_id.mapped(
                        'attribute_id').mapped('id')).write({'force_update': True})

        return res
