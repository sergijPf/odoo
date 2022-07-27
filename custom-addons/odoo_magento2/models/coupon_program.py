# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.exceptions import UserError


class CouponProgram(models.Model):
    _inherit = 'coupon.program'

    is_in_magento = fields.Boolean("Is active in Magento?")
    magento_promotion_ids = fields.One2many('magento.promotion', "coupon_program_id")


    def toggle_active(self):
        super(CouponProgram, self).toggle_active()
        self.magento_promotion_ids.write({'active': self[0].active})

    def write(self, vals):
        magento_exported_promo = self.magento_promotion_ids.filtered(lambda x: x.export_status == 'exported')
        if magento_exported_promo:
            raise UserError(f"Current Promotion(s) cannot be updated as it has been already exported to Magento."
                            f"Please remove them first: {magento_exported_promo.mapped('name')}")

        for rec in self:
            if 'is_in_magento' in vals:
                if vals['is_in_magento']:
                    if not rec.magento_promotion_ids and rec.reward_type in ['discount', 'x_product_discount']:
                        rec.magento_promotion_ids.create({'coupon_program_id': rec.id})
                else:
                    if rec.magento_promotion_ids:
                        raise UserError(f"You're not able to disable '{rec.name}'-Promo until it's active or "
                                        f"exists in Magento Layer. Please archive/remove it first.")

        return super(CouponProgram, self).write(vals)
