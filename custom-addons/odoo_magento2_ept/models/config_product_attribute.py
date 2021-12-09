# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from datetime import datetime


class ConfigProductAttribute(models.Model):
    _name = "config.product.attribute"
    _description = 'Magento Configurable Product Attributes'
    _order = 'color, sequence, id'
    _rec_name = 'name'

    categ_group_id = fields.Many2one('config.product.attribute.group', string="Attribute Category", required=True)
    name = fields.Char("Attribute Name", required=True, translate=True, help="Attribute short name")
    attribute_value = fields.Html(string="Attribute Value", translate=True, help="Attribute Full Description")
    color = fields.Integer(related="categ_group_id.color", string="Color")
    sequence = fields.Integer(string="Sequence", default=10)

    def write(self, vals):
        res = super(ConfigProductAttribute, self).write(vals)

        # update config.products' "write_date"
        if 'attribute_value' in vals or 'sequence' in vals:
            conf_products = self.env["product.public.category"].search([('is_magento_config', '=', True),
                                                                        ('x_magento_no_create', '=', False)])
            for prod in conf_products:
                if self.id in [a.id for a in prod.attribute_ids]:
                    prod.write_date = datetime.now()
        return res


class ConfigProductAttributeGroup(models.Model):
    _name = "config.product.attribute.group"
    _description = 'Groups for Magento Configurable Product Attributes'
    _rec_name = 'name'

    name = fields.Char(string="Attributes Category", help="Attribute name must match Attribute code in Magento",
                       required=True)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean("Active", default=True)

    _sql_constraints = [('_config_attribute_group_name_unique_constraint',
                         'unique(name)',
                         "Config.Product Attribute Group name must be unique"),
                        ('_config_attribute_group_color_unique_constraint',
                         'unique(color)',
                         "Config.Product Attribute Group color must be unique")]

