# -*- coding: utf-8 -*-

from odoo import models, fields, api


class MagentoProductCategory(models.Model):
    _name = "magento.product.category"
    _description = "Magento Product Categories"
    _rec_name = 'complete_category_name'

    instance_id = fields.Many2one('magento.instance', 'Magento Instance', ondelete="cascade")
    magento_category = fields.Char(string="Magento ID")
    magento_parent_id = fields.Many2one('magento.product.category', 'Parent Category', ondelete='cascade')
    magento_child_ids = fields.One2many(comodel_name='magento.product.category', inverse_name='magento_parent_id',
                                        string='Child Categories')
    complete_category_name = fields.Char("Full Category Name", help="Complete Category Path(Name)",
                                         compute="_compute_complete_name", recursive=True)
    active = fields.Boolean(string="Status", default=True)
    product_public_categ_id = fields.Many2one('product.public.category', string="Product Public Category")
    name = fields.Char("Name", related="product_public_categ_id.name")

    @api.depends('name', 'magento_parent_id.complete_category_name')
    def _compute_complete_name(self):
        for category in self:
            if category.magento_parent_id:
                category.complete_category_name = '%s / %s' % (category.magento_parent_id.complete_category_name,
                                                               category.name)
            else:
                category.complete_category_name = category.name
