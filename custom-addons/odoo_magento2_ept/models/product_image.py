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
        ('swatch_image', "Swatch")
    ], string="Image role")

    @api.onchange('image_role')
    def onchange_image_role_check(self):
        product_tmpl_img_role = self.search([('product_tmpl_id', '=', self._origin.product_tmpl_id.id),
                                             ('image_role', '=', self.image_role)])
        if product_tmpl_img_role:
            product_tmpl_img_role.image_role = None

        product_vrnt_img_role = self.search([('product_variant_id', '=', self._origin.product_variant_id.id),
                                             ('image_role', '=', self.image_role)])
        if product_vrnt_img_role:
            product_vrnt_img_role.image_role = None

        if self._origin.product_tmpl_id and self.image_role == 'swatch_image':
            self.image_role = None

    def write(self, vals):
        res = super(ProductImage, self).write(vals)

        if 'image_role' in vals:
            for rec in self:
                if rec.product_tmpl_id and rec.product_tmpl_id.magento_conf_prod_ids:
                    rec.product_tmpl_id.magento_conf_prod_ids.write({'force_update': True})
                elif rec.product_variant_id and rec.product_variant_id.magento_product_ids:
                    rec.product_variant_id.magento_product_ids.write({'force_update': True})

        return res
