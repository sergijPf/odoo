# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Describes fields mapping to Magento products
"""
# import re
from odoo import fields, models, api
from odoo.exceptions import UserError
MAGENTO_PRODUCT = 'magento.product.product'


class ProductProduct(models.Model):
    """
    Describes fields mapping to Magento products
    """
    _inherit = 'product.product'

    config_product_id = fields.Many2one('product.public.category', string="Configurable Product",
                                        domain="[('is_magento_config','=',True)]")

    def _compute_magento_product_count(self):
        """
        calculate magento product count
        :return:
        """
        magento_product_obj = self.env[MAGENTO_PRODUCT]
        for product in self:
            magento_products = magento_product_obj.search([('odoo_product_id', '=', product.id)])
            product.magento_product_count = len(magento_products) if magento_products else 0

    magento_product_count = fields.Integer(string='# Product Counts', compute='_compute_magento_product_count')

    def view_magento_products(self):
        """
        This method is used to view Magento product.
        :return: Action
        """
        magento_product_ids = self.mapped('magento_product_ids')
        xmlid = ('odoo_magento2_ept', 'action_magento_stock_picking')
        action = self.env['ir.actions.act_window'].for_xml_id(*xmlid)
        action['domain'] = "[('id','in',%s)]" % magento_product_ids.ids
        if not magento_product_ids:
            return {'type': 'ir.actions.act_window_close'}
        return action

    magento_product_ids = fields.One2many(
        MAGENTO_PRODUCT,
        inverse_name='odoo_product_id',
        string='Magento Products',
        help='Magento Product Ids'
    )

    def write(self, vals):
        """
        This method will archive/unarchive Magento product based on Odoo Product
        :param vals: Dictionary of Values
        """
        magento_product_product_obj = self.env[MAGENTO_PRODUCT]
        if 'active' in vals:
            for product in self:
                magento_product = magento_product_product_obj.search(
                    [('odoo_product_id', '=', product.id)])
                if vals.get('active'):
                    magento_product = magento_product_product_obj.search(
                        [('odoo_product_id', '=', product.id), ('active', '=', False)])
                magento_product and magento_product.write({'active': vals.get('active')})

        if 'config_product_id' in vals:
            # applicable only to products which are in Magento Layer already
            magento_conf_product_obj = self.env['magento.configurable.product']
            domain = [('magento_sku', '=', self.default_code)]

            # check if product is in Magento Layer
            magento_simp_prod = magento_product_product_obj.with_context(active_test=False).search(domain)
            if magento_simp_prod:
                # check if config.product exists
                dmn = [('odoo_prod_category', '=', self.config_product_id.id)]
                for prod in magento_simp_prod:
                    dmn.append(('magento_instance_id', '=', prod.magento_instance_id.id))
                    conf_prod = magento_conf_product_obj.with_context(active_test=False).search(dmn)
                    if not conf_prod:
                        conf_prod = magento_conf_product_obj.create({
                            'magento_instance_id': prod.magento_instance_id.id,
                            'odoo_prod_category': self.config_product_id.id,
                            'magento_sku': self.config_product_id.name.replace(' ', '_').replace('%', '').
                                replace('#', '').replace('/', '')
                            # 'magento_sku': re.sub('[^a-zA-Z0-9 \n\.]', '', self.config_product_id.name),
                            # 'magento_product_name': self.config_product_id.name
                        })
                    prod.magento_conf_product = conf_prod.id

        res = super(ProductProduct, self).write(vals)

        return res
