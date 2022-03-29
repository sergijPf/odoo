# -*- coding: utf-8 -*-

from odoo import fields, models, api
from odoo.exceptions import UserError


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    is_ignored_in_magento = fields.Boolean(string="Ignore for Magento", default=False,
                                           help="The attribute will be ignored while Product's export to Magento")

    @api.onchange('is_ignored_in_magento')
    def onchange_magento_ignore_attribute(self):
        if self.is_ignored_in_magento and any(self.attribute_line_ids.mapped('magento_config')):
            raise UserError("It's not allowed to ignore this attribute for Magento as it's already used for"
                            " Magento configurable products as configurable attribute!")

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
