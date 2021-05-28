# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields mapping to Magento products templates
"""
from odoo import models, fields


class ProductTemplate(models.Model):
    """
    Describes fields mapping to Magento products templates
    """
    _inherit = 'product.template'

    def _compute_magento_template_count(self):
        """
        calculate magento product template
        :return:
        """
        magento_template_obj = self.env['magento.product.template']
        for product in self:
            magento_products = magento_template_obj.search([('odoo_product_template_id', '=', product.id)])
            product.magento_template_count = len(magento_products) if magento_products else 0

    magento_template_count = fields.Integer(string='# Product Count', compute='_compute_magento_template_count')
    magento_product_template_ids = fields.One2many(
        'magento.product.template',
        inverse_name='odoo_product_template_id',
        string='Magento Products Templates',
        help='Magento Product Template Ids'
    )
