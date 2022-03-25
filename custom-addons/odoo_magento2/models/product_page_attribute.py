# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductPageAttribute(models.Model):
    _name = "product.page.attribute"
    _description = 'Magento Product Page Attributes'
    _order = 'sequence, id'
    _rec_name = 'name'

    categ_group_id = fields.Many2one('product.page.attribute.group', string="Attribute Category(Group)", required=True)
    name = fields.Char("Attribute Name", required=True, translate=True, help="Attribute short name")
    attribute_value = fields.Html(string="Attribute Value", translate=True, help="Attribute full description")
    color = fields.Integer(related="categ_group_id.color", string="Color")
    sequence = fields.Integer(string="Sequence", default=10)
    product_category_ids = fields.Many2many('product.category', 'x_attribute_ids')

    def write(self, vals):
        res = super(ProductPageAttribute, self).write(vals)

        if 'attribute_value' in vals or 'sequence' in vals or 'categ_group_id' in vals:
            for categ in self.product_category_ids:
                if categ.product_template_ids and categ.product_template_ids.magento_conf_prod_ids:
                    categ.product_template_ids.magento_conf_prod_ids.write({'force_update': True})
        return res


class ProductPageAttributeGroup(models.Model):
    _name = "product.page.attribute.group"
    _description = 'Groups for Magento Product Page Attributes'
    _rec_name = 'name'

    color = fields.Integer(string='Color Index')
    active = fields.Boolean("Active", default=True)
    name = fields.Char(string="Attributes Category(Group)", help="Attribute name must match 'Attribute code' "
                                                                 "of product attribute in Magento", required=True)

    _sql_constraints = [('_config_attribute_group_name_unique_constraint',
                         'unique(name)',
                         "Product Page Attributes Group name must be unique"),
                        ('_config_attribute_group_color_unique_constraint',
                         'unique(color)',
                         "Product Page Attributes Group color must be unique")]
