# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = "product.category"

    x_attribute_ids = fields.Many2many('config.product.attribute', 'product_category_ids', string="Product Page attributes",
                                     help="Descriptive attributes for Product page")
    product_template_ids = fields.One2many('product.template', 'categ_id')
