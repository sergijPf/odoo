# -*- coding: utf-8 -*-
"""For Odoo Magento2 Connector Module"""
from odoo import models, fields, api
from odoo.exceptions import UserError


class ProductImage(models.Model):
    """Inherited account tax model to calculate tax."""
    _inherit = 'product.image'

    image_role = fields.Selection([
        ('small_image', "Small"),
        ('image', "Base"),
        ('thumbnail', "Thumbnail"),
        ('swatch_image', "Swatch (Variants only)")
    ], string="Image role")

    def write(self, vals):
        if 'image_role' in vals:
            if self.product_tmpl_id:
                if vals['image_role'] == 'swatch_image':
                    vals['image_role'] = None

                if vals['image_role']:
                    product_tmpl_img_role = self.search([('product_tmpl_id', '=', self.product_tmpl_id.id),
                                                         ('image_role', '=', vals['image_role'])])
                    if product_tmpl_img_role:
                        product_tmpl_img_role.image_role = None

                if self.product_tmpl_id.magento_conf_prod_ids:
                    self.product_tmpl_id.magento_conf_prod_ids.write({'force_update': True})

            elif self.product_variant_id:
                if vals['image_role']:
                    product_vrnt_img_role = self.search([('product_variant_id', '=', self.product_variant_id.id),
                                                         ('image_role', '=', vals['image_role'])])
                    if product_vrnt_img_role:
                        product_vrnt_img_role.image_role = None

                if self.product_variant_id.magento_product_ids:
                    self.product_variant_id.magento_product_ids.write({'force_update': True})

        return super(ProductImage, self).write(vals)

    @api.model
    def create(self, vals):
        if vals.get('product_tmpl_id'):
            if vals.get('image_role') == 'swatch_image':
                vals['image_role'] = None

            if vals.get('image_role'):
                product_tmpl_img_role = self.search([('product_tmpl_id', '=', vals['product_tmpl_id']),
                                                     ('image_role', '=', vals['image_role'])])
                if product_tmpl_img_role:
                    product_tmpl_img_role.image_role = None
        elif vals.get('product_variant_id'):
            if vals.get('image_role'):
                product_vrnt_img_role = self.search([('product_variant_id', '=', vals['product_variant_id']),
                                                     ('image_role', '=', vals['image_role'])])
                if product_vrnt_img_role:
                    product_vrnt_img_role.image_role = None

        return super(ProductImage, self).create(vals)
