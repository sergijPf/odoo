# -*- coding: utf-8 -*-

from odoo import fields, models

class ProductPublicCategory(models.Model):
    _inherit = "product.category"

    # ecommerce_category_id = fields.Many2one('product.public.category')