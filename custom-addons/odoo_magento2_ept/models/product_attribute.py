# -*- coding: utf-8 -*-

from odoo import fields, models, api
from odoo.exceptions import UserError

class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    is_ignored_in_magento = fields.Boolean(string="Ignore for Magento", default=False,
                                           help="The attribute will be ignored while Product's export to Magento")

    def write(self, vals):
        res = super(ProductAttribute, self).write(vals)

        # check if attribute already assigned to any of magento products
        if 'is_ignored_in_magento' in vals:
            attr_id = self.id
            magento_products = self.env['magento.product.product'].search([])
            magento_products.filtered(lambda x: attr_id in x.attribute_value_ids.product_attribute_value_id.mapped(
                        'attribute_id').mapped('id')).write({'force_update': True})
        return res


# class ProductAttributeValue(models.Model):
#     _inherit = "product.attribute.value"
#
#     attr_name = fields.Char(related='attribute_id.name')
#     grouped_color = fields.Many2one('product.attribute.grouped.color', "Grouping color")
#
#
#
# class ProductAttributeGroupedColor(models.Model):
#     _name = 'product.attribute.grouped.color'
#     _description = 'Product Grouped Color Attribute'
#     _rec_name = 'color_name'
#
#     color_name = fields.Char("Unique Color")
#     active = fields.Boolean("Active", default=True)
#
#     _sql_constraints = [
#         ('unique_color_name', 'unique(color_name)',
#          'The color name must be unique')]
#
#     @api.model
#     def create(self, vals):
#         if len(self.search([])) > 11:
#             raise UserError("It's not allowed to create more than 12 'grouped' colors")
#         else:
#             return super(ProductAttributeGroupedColor, self).create(vals)