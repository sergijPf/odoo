# -*- coding: utf-8 -*-

from odoo import fields, models

class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    x_category_image_ids = fields.Many2many('product.image', string='Extra Category Media')
    # product_category_id = fields.Many2one('product.category')

    # x_magento_attr_ids = fields.Many2many('product.attribute', string="Configurable Attribute(s)",
    #                                       help='Attribute(s) assigned as configurable for config.product in Magento')
    # x_magento_no_create = fields.Boolean(string="Do not create in Magento", default=False,
    #                                      help="If checked the Configurable Product won't be created on Magento side")
    # x_magento_attr_set = fields.Char(string='Magento Product Attribute Set', help='Magento Attribute set',
    #                                  default="Default")
    x_show_on_www = fields.Boolean(string="Show on WWW")