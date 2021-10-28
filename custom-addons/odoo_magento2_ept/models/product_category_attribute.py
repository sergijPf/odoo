# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductCategoryAttributeLine(models.Model):
    _name = "product.category.attribute.line"

    config_prod_id = fields.Many2one('product.public.category', string="Product Category", ondelete='cascade',
                                     required=True, index=True)
    attribute_id = fields.Many2one('product.attribute', string="Attribute", ondelete='restrict', required=True,
                                   index=True)
    value_id = fields.Many2one('product.attribute.value', string="Values", ondelete='restrict', required=True,
                                 domain="[('attribute_id', '=', attribute_id)]")

    _sql_constraints = [('_product_category_attribute_unique_constraint',
                        'unique(config_prod_id, attribute_id)',
                        "Attribute must be unique per Product")]

