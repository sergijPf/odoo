from odoo import fields, models


class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"

    pcav_attribute_line_ids = fields.One2many('product.category.attribute.line', 'value_id', string="Lines", copy=False)