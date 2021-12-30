# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from datetime import datetime


class ConfigProductAttribute(models.Model):
    _name = "config.product.attribute"
    _description = 'Magento Configurable Product Attributes'
    _order = 'sequence, id'
    _rec_name = 'name'

    categ_group_id = fields.Many2one('config.product.attribute.group', string="Attribute Category", required=True)
    name = fields.Char("Attribute Name", required=True, translate=True, help="Attribute short name")
    attribute_value = fields.Html(string="Attribute Value", translate=True, help="Attribute Full Description")
    color = fields.Integer(related="categ_group_id.color", string="Color")
    sequence = fields.Integer(string="Sequence", default=10)
    product_category_ids = fields.Many2many('product.category', 'x_attribute_ids')

    def write(self, vals):
        res = super(ConfigProductAttribute, self).write(vals)

        # update config.products' "write_date"
        if 'attribute_value' in vals or 'sequence' in vals:
            # prod_category = self.env["product.category"].search([])
            # conf_products = self.env["product.public.category"].search([('is_magento_config', '=', True)])
            for categ in self.product_category_ids:
                if self.id in [a.id for a in categ.x_attribute_ids]:
                    categ.product_template_ids.magento_conf_prod_ids.write({'force_update': True})
        return res


class ConfigProductAttributeGroup(models.Model):
    _name = "config.product.attribute.group"
    _description = 'Groups for Magento Product Page Attributes'
    _rec_name = 'name'

    name = fields.Char(string="Attributes Category", help="Attribute name must match Attribute code in Magento",
                       required=True)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean("Active", default=True)

    _sql_constraints = [('_config_attribute_group_name_unique_constraint',
                         'unique(name)',
                         "Product Page Attributes Group name must be unique"),
                        ('_config_attribute_group_color_unique_constraint',
                         'unique(color)',
                         "Product Page Attributes Group color must be unique")]

