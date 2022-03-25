# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes methods for importing magento customers into Odoo.
"""
from odoo import models, fields, api


class MagentoProductCategory(models.Model):
    _name = "magento.product.category"
    _description = "Magento Product Categories"
    _rec_name = 'name'

    instance_id = fields.Many2one('magento.instance', 'Magento Instance', ondelete="cascade")
    magento_category = fields.Char(string="Magento ID")
    magento_parent_id = fields.Many2one('magento.product.category', 'Parent Category', ondelete='cascade')
    magento_child_ids = fields.One2many(comodel_name='magento.product.category', inverse_name='magento_parent_id',
                                        string='Child Categories')
    complete_category_name = fields.Char("Full Category Name", help="Complete Category Path(Name)",
                                         compute="_compute_complete_name")
    active = fields.Boolean(string="Status", default=True)
    product_public_categ_id = fields.Many2one('product.public.category', string="Product Public Category")
    name = fields.Char("Name", related="product_public_categ_id.name")

    @api.depends('name', 'magento_parent_id.complete_category_name')
    def _compute_complete_name(self):
        for category in self:
            if category.magento_parent_id:
                category.complete_category_name = '%s / %s' % (category.magento_parent_id.complete_category_name, category.name)
            else:
                category.complete_category_name = category.name


class ProductCategory(models.Model):
    _inherit = "product.category"

    x_attribute_ids = fields.Many2many('config.product.attribute', 'product_category_ids',
                                       string="Product Page attributes",
                                       help="Descriptive attributes for Product page")
    product_template_ids = fields.One2many('product.template', 'categ_id')


    def write(self, vals):
        res = super(ProductCategory, self).write(vals)

        if 'x_attribute_ids' in vals :
            self.product_template_ids.magento_conf_prod_ids.force_update = True

        return res